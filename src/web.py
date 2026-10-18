"""Authenticated single-instance dashboard; run with python -m src.web."""
import base64
import hmac
import json
import os
import re
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from ._file_utils import _atomic_write_text
from .models import Config
from .processing.profiles import ProfileRegistry
from .storage.manager import _expand_env_vars


class Dashboard:
    def __init__(self, data_dir, username, password):
        if not username or len(password) < 16:
            raise ValueError('Set HORIZON_WEB_USER and HORIZON_WEB_PASSWORD (at least 16 characters)')
        self.data = Path(data_dir).resolve()
        self.data.mkdir(parents=True, exist_ok=True)
        self.config = self.data / 'config.json'
        self.username, self.password = username, password
        self.lock = threading.Lock()
        self.process = None
        self.log = ''

    def status(self):
        with self.lock:
            code = self.process.poll() if self.process else None
            return {'running': self.process is not None and code is None,
                    'exit_code': code, 'log': self.log}

    def run(self, hours):
        if type(hours) is not int or not 1 <= hours <= 720:
            raise ValueError('hours must be an integer between 1 and 720')
        with self.lock:
            if self.process is not None and self.process.poll() is None:
                return False
            self.log = ''
            self.process = subprocess.Popen(
                [sys.executable, '-m', 'src.main', '--data-dir', str(self.data), '--hours', str(hours)],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                encoding='utf-8', errors='replace', env={**os.environ, 'PYTHONUNBUFFERED': '1'},
            )
            threading.Thread(target=self._collect, args=(self.process,), daemon=True).start()
            return True

    def _collect(self, process):
        for line in process.stdout:
            with self.lock:
                if self.process is process:
                    self.log = (self.log + line)[-200000:]
        process.wait()

    def close(self):
        with self.lock:
            process = self.process
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def make_server(app, host='0.0.0.0', port=8080):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            # Do not log URLs, report contents, credentials or request bodies.
            pass

        def send(self, code, value, content_type='application/json; charset=utf-8', extra=None):
            payload = value.encode() if isinstance(value, str) else json.dumps(value, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(payload)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('X-Frame-Options', 'DENY')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'")
            for key, val in (extra or {}).items():
                self.send_header(key, val)
            self.end_headers()
            self.wfile.write(payload)

        def authorized(self):
            try:
                kind, value = self.headers.get('Authorization', '').split(' ', 1)
                decoded = base64.b64decode(value, validate=True).decode()
                user, password = decoded.split(':', 1)
                ok = kind == 'Basic' and hmac.compare_digest(user.encode(), app.username.encode()) and hmac.compare_digest(password.encode(), app.password.encode())
            except (ValueError, UnicodeError):
                ok = False
            if not ok:
                self.send(401, {'error': 'Authentication required'}, extra={'WWW-Authenticate': 'Basic realm="Horizon", charset="UTF-8"'})
            return ok

        def body(self):
            if self.headers.get('X-Horizon-Request') != '1':
                raise PermissionError('Missing same-origin request header')
            if 'application/json' not in self.headers.get('Content-Type', ''):
                raise ValueError('Expected application/json')
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 1048576:
                raise ValueError('JSON body must be between 1 byte and 1 MiB')
            return json.loads(self.rfile.read(length))

        def do_GET(self):
            if not self.authorized():
                return
            url = urlsplit(self.path)
            if url.path == '/':
                self.send(200, Path(__file__).with_name('web_ui.html').read_text(), 'text/html; charset=utf-8')
            elif url.path == '/api/status':
                self.send(200, app.status())
            elif url.path == '/api/config':
                path = app.config if app.config.exists() else Path('data/config.example.json')
                self.send(200, json.loads(path.read_text()))
            elif url.path == '/api/reports':
                root = app.data / 'summaries'
                names = sorted((p.name for p in root.glob('horizon-*.md') if p.is_file() and not p.is_symlink()), reverse=True)
                self.send(200, {'reports': [{'name': n} for n in names]})
            elif url.path == '/api/report':
                name = parse_qs(url.query).get('name', [''])[0]
                root = (app.data / 'summaries').resolve()
                path = root / name
                if not re.fullmatch(r'horizon-[A-Za-z0-9_-]+\.md', name) or path.is_symlink() or path.resolve().parent != root or not path.is_file():
                    self.send(404, {'error': 'Report not found'})
                else:
                    self.send(200, {'name': name, 'content': path.read_text(encoding='utf-8')})
            else:
                self.send(404, {'error': 'Not found'})

        def mutate(self):
            if not self.authorized():
                return
            try:
                data = self.body()
                route = urlsplit(self.path).path
                if self.command == 'PUT' and route == '/api/config':
                    config = Config.model_validate(_expand_env_vars(data))
                    ProfileRegistry.load(Path(config.processing.profiles_dir), config.processing.default_profile).validate_source_references(data.get('sources', {}))
                    with app.lock:
                        if app.process is not None and app.process.poll() is None:
                            self.send(409, {'error': 'Cannot change configuration during a run'})
                            return
                        # Preserve ${ENV} references, rather than persisting expanded secrets.
                        _atomic_write_text(app.config, json.dumps(data, ensure_ascii=False, indent=2) + '\n')
                    self.send(200, {'saved': True})
                elif self.command == 'POST' and route == '/api/run':
                    if not isinstance(data, dict):
                        raise ValueError('Expected object')
                    started = app.run(data.get('hours', 24))
                    self.send(202 if started else 409, {'started': started})
                else:
                    self.send(404, {'error': 'Not found'})
            except PermissionError:
                self.send(403, {'error': 'Missing same-origin request header'})
            except (ValueError, TypeError, AttributeError):
                self.send(400, {'error': 'Invalid JSON, configuration, profile or hours; check config schema'})

        do_POST = mutate
        do_PUT = mutate

    server = ThreadingHTTPServer((host, port), Handler)
    return server


def main():
    from dotenv import load_dotenv
    load_dotenv()
    app = Dashboard(os.getenv('HORIZON_DATA_DIR', '/app/data'), os.getenv('HORIZON_WEB_USER', 'admin'), os.getenv('HORIZON_WEB_PASSWORD', ''))
    server = make_server(app, os.getenv('HORIZON_WEB_HOST', '0.0.0.0'), int(os.getenv('HORIZON_WEB_PORT', '8080')))
    try:
        server.serve_forever()
    finally:
        server.server_close()
        app.close()


if __name__ == '__main__':
    main()
