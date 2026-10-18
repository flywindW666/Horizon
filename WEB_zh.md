# Web 日报与管理后台

本 Fork 新增 `/` Web 控制台，包含历史日报阅读、原始 JSON 配置编辑与校验、手动任务执行、状态和日志查看。不改变原有 CLI 镜像入口。

## 启动

```bash
git clone https://github.com/flywindW666/Horizon.git
cd Horizon
cp .env.example .env
mkdir -p data
```

编辑 `.env`，除了所用模型 API 密钥，增加：

```dotenv
HORIZON_WEB_USER=admin
HORIZON_WEB_PASSWORD=替换为至少16个字符的随机密码
HORIZON_BIND_ADDRESS=127.0.0.1
HORIZON_PORT=8080
```

请使用随机长密码（例如 `openssl rand -hex 24` 生成），不要直接使用示例文字。管理后台可修改信息源、外部服务地址和读取运行日志，应视为高权限接口，只允许可信管理员登录。

首次可不创建 `data/config.json`：后台配置页会加载镜像内置示例，修改后保存为真实配置。API 密钥通过 `.env` 注入，配置中用 `api_key_env` 或 `${VAR}` 引用；后台不会提供 `.env` 下载接口，但配置 JSON 中直接写入的密钥以及应用日志仍可能对管理员可见。

Linux 绑定目录需允许 UID 10001 写入（`setfacl` 需要主机安装 acl）：

```bash
sudo setfacl -R -m u:10001:rwX data
sudo setfacl -m d:u:10001:rwX data
docker compose -f compose.web.yaml pull
docker compose -f compose.web.yaml up -d
```

访问 `http://127.0.0.1:8080`，浏览器会提示输入上述用户名和密码。

默认只绑定本机。远程访问优先使用 SSH 隧道：

```bash
ssh -L 8080:127.0.0.1:8080 your-user@your-server
```

然后访问本机 `http://127.0.0.1:8080`。需要通过域名访问时，在本机绑定前设置 HTTPS 反向代理。HTTP Basic 在普通 HTTP 中不加密，不要直接暴露到公网。确需局域网访问时，可在 `.env` 中设置 `HORIZON_BIND_ADDRESS=0.0.0.0` 并通过防火墙限制可信网段。

## 功能与限制

- 日报读取实际 `data/summaries/horizon-*.md`；没有日报时显示空状态，不伪造示例新闻。
- 日报内容以安全文本方式展示 Markdown，避免来自新闻内容的脚本执行。
- 配置保存前使用上游 Config 模型和 Profile 校验；保留 `${ENV}` 引用，不将环境变量展开后的秘密写回文件。
- 同一服务仅允许运行一个任务，运行中不允许修改配置。日志只保留本服务最近一次运行的内存尾部（最多 200000 字符），重启即清空。
- 重启后台不会自动恢复或重跑上次任务；暂不包含自动定时任务和多用户角色管理。
- 完整日报生成仍需有效 AI 密钥和可访问的数据源；后台启动成功不表示外部服务已配置成功。

## 更新

```bash
docker compose -f compose.web.yaml pull
docker compose -f compose.web.yaml up -d
```

两个仓库提供同一多架构镜像：`ghcr.io/flywindw666/horizon:latest` 与 `ryantj/horizon:latest`。
