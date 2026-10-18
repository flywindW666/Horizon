import base64
import http.client
import json
import threading
from pathlib import Path

import pytest

from src.web import Dashboard, make_server


@pytest.fixture
def dashboard(tmp_path):
    app = Dashboard(tmp_path, 'admin', 'test-password-long-enough')
    server = make_server(app, '127.0.0.1', 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    def request(method, path, value=None, auth=True, csrf=True):
        connection = http.client.HTTPConnection(*server.server_address, timeout=5)
        headers = {'Content-Type': 'application/json'}
        if auth:
            headers['Authorization'] = 'Basic ' + base64.b64encode(b'admin:test-password-long-enough').decode()
        if csrf:
            headers['X-Horizon-Request'] = '1'
        connection.request(method, path, json.dumps(value) if value is not None else None, headers)
        response = connection.getresponse()
        body = response.read().decode()
        connection.close()
        return response.status, body
    yield app, request
    server.shutdown()
    server.server_close()
    app.close()
    thread.join()


def test_password_required(tmp_path):
    with pytest.raises(ValueError):
        Dashboard(tmp_path, 'admin', '')


def test_auth_and_status(dashboard):
    _, request = dashboard
    assert request('GET', '/api/status', auth=False)[0] == 401
    code, body = request('GET', '/api/status')
    assert code == 200
    assert json.loads(body) == {'running': False, 'exit_code': None, 'log': ''}


def test_reports_and_traversal(dashboard, tmp_path):
    _, request = dashboard
    root = tmp_path / 'summaries'
    root.mkdir()
    (root / 'horizon-2026-10-18-zh.md').write_text('# 新闻\n<script>alert(1)</script>')
    (root / 'horizon-secret.md').symlink_to(tmp_path / 'secret')
    (tmp_path / 'secret').write_text('SECRET')
    code, body = request('GET', '/api/reports')
    assert code == 200
    assert len(json.loads(body)['reports']) == 1
    assert request('GET', '/api/report?name=../../secret')[0] == 404
    assert request('GET', '/api/report?name=horizon-secret.md')[0] == 404
    assert request('GET', '/api/report?name=horizon-2026-10-18-zh.md')[0] == 200


def test_config_validation_and_env_preservation(dashboard, monkeypatch):
    app, request = dashboard
    config = json.loads(Path('data/config.example.json').read_text())
    config['ai']['base_url'] = '${HORIZON_TEST_ENDPOINT}'
    monkeypatch.setenv('HORIZON_TEST_ENDPOINT', 'https://api.example.com/v1')
    assert request('PUT', '/api/config', config, csrf=False)[0] == 403
    assert request('PUT', '/api/config', {'bad': True})[0] == 400
    assert request('PUT', '/api/config', config)[0] == 200
    assert '${HORIZON_TEST_ENDPOINT}' in app.config.read_text()
    assert 'https://api.example.com/v1' not in app.config.read_text()
    assert request('GET', '/api/config')[0] == 200


def test_run_bounds_and_single_job(dashboard, monkeypatch):
    app, request = dashboard
    assert request('POST', '/api/run', {'hours': 0})[0] == 400
    assert request('POST', '/api/run', {'hours': '24'})[0] == 400
    assert request('POST', '/api/run', {'hours': 24}, csrf=False)[0] == 403
    class Process:
        def poll(self): return None
    app.process = Process()
    assert request('POST', '/api/run', {'hours': 24})[0] == 409
    app.process = None


def test_actual_subprocess_failure_is_observable(dashboard):
    import time
    app, request = dashboard
    assert request('POST', '/api/run', {'hours': 24})[0] == 202
    deadline = time.monotonic() + 10
    while app.status()['running'] and time.monotonic() < deadline:
        time.sleep(0.05)
    status = app.status()
    assert not status['running']
    assert status['exit_code'] == 1
    assert 'Configuration file not found' in status['log']
