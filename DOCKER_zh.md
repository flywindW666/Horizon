# Docker 构建与运行

此 Fork 沿用上游 Dockerfile，并修正入口：直接运行构建时安装的 `/app/.venv/bin/horizon`，避免容器启动时通过 `uv run` 重新同步依赖、下载构建工具。应用以非 root 用户（UID 10001）运行。

## 直接拉取预编译镜像

镜像公开发布，支持 `linux/amd64`、`linux/arm64`，无需自行编译：

```bash
docker pull ghcr.io/flywindw666/horizon:latest
# 或者 Docker Hub
docker pull ryantj/horizon:latest
```

按下文配置 `.env` 和 `data/config.json`，并设置数据目录写权限后运行：

```bash
docker run --rm --env-file .env -e TZ=Asia/Shanghai \
  -v "$PWD/data:/app/data" ghcr.io/flywindw666/horizon:latest --hours 24
```

## 自动同步与发布

工作流 `.github/workflows/docker-publish.yml` 每 6 小时检查上游 `Thysrael/Horizon` 的 `main`，有更新时合并到本 Fork。当前上游没有 Release 或版本标签，因此跟踪主分支提交，而非仅跟踪正式发布。也支持 Actions 页面手动运行，以及镜像相关文件推送后触发。

合并成功后执行测试套件、Docker 构建和离线启动检查，再发布两个仓库的 `latest` 与 `sha-完整提交号` 标签。使用 SHA 标签或镜像 digest 可固定部署版本。合并冲突或测试失败将终止流程；已有发布镜像不会因此删除。

GHCR 使用 Actions 内置 `GITHUB_TOKEN`；Docker Hub 凭据位于仓库 Secrets 的 `DOCKERHUB_USERNAME` 和 `DOCKERHUB_TOKEN`。更换或撤销凭据后需要更新 Secrets。请只向此仓库推送可信代码，并在信任上游变更的前提下启用自动合并和构建。

GitHub 公共仓库长时间无活动时可能停用定时工作流，请留意 Actions 状态及失败通知。推送新镜像不会自动更新你的部署主机；主机仍需拉取并重新运行。

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
