# Docker 构建与运行

此 Fork 沿用上游 Dockerfile，并修正入口：直接运行构建时安装的 `/app/.venv/bin/horizon`，避免容器启动时通过 `uv run` 重新同步依赖、下载构建工具。应用以非 root 用户（UID 10001）运行。

## 构建与自检

```bash
git clone https://github.com/flywindW666/Horizon.git
cd Horizon
docker build -t horizon:latest .
docker run --rm --network none horizon:latest --help
```

基础镜像包含常规采集依赖及 trafilatura；OpenBB 可用 `--build-arg EXTRAS=openbb` 构建。Twitter Playwright 需要额外浏览器和系统依赖，基础镜像不包含。

## 配置

```bash
cp .env.example .env
cp data/config.example.json data/config.json
```

编辑 `.env` 添加所选模型的 API 密钥，编辑 `data/config.json` 配置信息源、模型和 Profile。不要提交密钥文件。

绑定目录需要允许容器 UID 10001 写入。Linux 主机可使用 ACL，避免更改现有文件所有者：

```bash
sudo setfacl -R -m u:10001:rwX data
sudo setfacl -m d:u:10001:rwX data
```

没有 ACL 工具时，可按本机权限管理策略为 UID 10001 设置写权限，不建议使用 `chmod 777`。

## 单次运行

```bash
docker run --rm \
  --env-file .env \
  -e TZ=Asia/Shanghai \
  -v "$PWD/data:/app/data" \
  horizon:latest --hours 24
```

或者使用仓库自带 Compose：

```bash
docker compose build
docker compose run --rm horizon --hours 24
```

这是命令行批处理程序，不是常驻 Web 服务，不需要映射端口。Compose 本身不会每天定时运行；需要调度时请另行配置主机 cron。

## 验证边界

`--help` 和 Profile 加载可以离线验证。完整新闻采集、AI 分析和消息推送仍需配置有效 API 密钥及可访问的信息源；仅构建镜像不代表这些外部服务已配置。
