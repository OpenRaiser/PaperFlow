# Feishu Webhook Server

SciTaste 通过这个服务接收飞书消息事件，再路由到 `master-coordinator` 和各个业务 Agent。

当前项目只保留一条本地联调方案：

`webhook server + ngrok`

## 前置条件

1. 安装依赖

```bash
pip install -r requirements.txt
```

2. 配好 `.env`

至少需要这些变量：

```bash
FEISHU_APP_ID=cli_xxxxxxxxxxxxx
FEISHU_APP_SECRET=xxxxxxxxxxxxxxxxxxxxxxxx
FEISHU_VERIFICATION_TOKEN=xxxxxxxxxxxxxxxx
FEISHU_BOT_NAME=SciTaste Bot
```

3. 本机已安装并登录 `ngrok`

```bash
ngrok version
ngrok config add-authtoken <your-token>
```

如果你不想把 `ngrok` token 写进系统配置，也可以只在 `.env` 里放：

```bash
NGROK_AUTHTOKEN=xxxxxxxxxxxxxxxx
```

## 启动方式

推荐直接用一条命令：

```bash
python services/webhook-server/start-with-ngrok.py
```

默认行为：

1. 启动本地 webhook 服务，端口 `8080`
2. 复用已有的 ngrok agent 或自动拉起一个新的
3. 生成公网 URL
4. 把可直接填写到飞书后台的地址写入：

```text
data/ngrok_url.txt
data/feishu_request_url.txt
```

如果只想启动本地 webhook，不带 ngrok：

```bash
python services/webhook-server/start.py
```

如果只想检查环境变量：

```bash
python services/webhook-server/start.py --verify
```

## 飞书后台怎么填

启动成功后，把 `data/feishu_request_url.txt` 里的地址填到：

`飞书开放平台 -> 你的应用 -> Event Subscription -> Request URL`

事件至少勾选：

- `Receive Messages v1.0` (`im.message.receive_v1`)

## 本地验证

1. 健康检查

```bash
curl http://127.0.0.1:8080/health
```

期望返回：

```json
{"status":"healthy"}
```

2. 看 ngrok 状态

```bash
curl http://127.0.0.1:4040/api/tunnels
```

3. 在飞书群里给 bot 发消息，例如：

```text
推送
冷启动
1 2 3
```

## 常见问题

### 1. 飞书里发消息没有反应

先看两件事：

1. `http://127.0.0.1:8080/health` 是否健康
2. `http://127.0.0.1:4040/api/tunnels` 里是否真的有指向 `localhost:8080` 的 tunnel

如果 ngrok 正常、飞书群里也能看到消息，但本地 webhook 日志没有任何 `POST /`，通常就是飞书后台 `Request URL` 还没更新到当前 ngrok 地址。

### 2. 每次 ngrok 重启 URL 都变

这是 ngrok 免费域名的正常行为。调试阶段就把新的 URL 复制到飞书后台；如果后面要长期稳定，就需要 ngrok 的固定域名方案。

### 3. `start-with-ngrok.py` 启动失败

优先检查：

- `ngrok version` 是否正常
- `ngrok config add-authtoken ...` 是否做过
- `data/ngrok_runtime.log` 里有没有网络或认证错误

## 文件说明

- `start.py`: 只启动 webhook
- `start-with-ngrok.py`: 推荐入口，自动处理 webhook + ngrok
- `scripts/webhook_server.py`: 实际的 HTTP 处理逻辑
