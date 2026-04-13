# 飞书 Webhook 配置指南

这份文档对应 SciTaste 当前唯一保留的本地联调方案：

`webhook + ngrok`

## 1. 填好 `.env`

最少需要：

```bash
FEISHU_APP_ID=cli_xxxxxxxxxxxxx
FEISHU_APP_SECRET=xxxxxxxxxxxxxxxxxxxxxxxx
FEISHU_VERIFICATION_TOKEN=xxxxxxxxxxxxxxxx
FEISHU_BOT_NAME=SciTaste Bot
```

如果希望脚本自动刷新 ngrok token，也可以额外配置：

```bash
NGROK_AUTHTOKEN=xxxxxxxxxxxxxxxx
```

## 2. 确认 ngrok 已可用

```bash
ngrok version
ngrok config add-authtoken <your-token>
```

## 3. 启动 SciTaste 的联调入口

```bash
python services/webhook-server/start-with-ngrok.py
```

成功后会看到：

- 本地 webhook 地址
- 当前 ngrok 公网地址
- 可直接填写到飞书后台的 `Request URL`

同时脚本会把地址写到：

```text
data/ngrok_url.txt
data/feishu_request_url.txt
```

## 4. 配置飞书开放平台

打开：

`飞书开放平台 -> 你的应用 -> Event Subscription`

然后：

1. 把 `data/feishu_request_url.txt` 里的内容粘进去
2. 勾选事件 `Receive Messages v1.0 (im.message.receive_v1)`
3. 点击保存

## 5. 本地自检

### webhook 是否活着

```bash
curl http://127.0.0.1:8080/health
```

### ngrok 是否真的转到本地 8080

```bash
curl http://127.0.0.1:4040/api/tunnels
```

看返回内容里是否有：

```text
localhost:8080
```

## 6. 在飞书里做真实测试

给 bot 所在群发任意一条文本消息，例如：

```text
推送
```

如果飞书里能看到你发出的消息，但本地 webhook 没有收到 `POST /`，通常就是飞书后台还挂着旧的 ngrok 地址。

## 7. 常见问题

### Request URL 验证失败

优先检查：

1. `.env` 里的 `FEISHU_VERIFICATION_TOKEN`
2. 飞书后台里的 Verification Token
3. webhook 是否已经启动

### 每次都要改 URL

免费 ngrok 的域名会变，这是正常现象。调试阶段按当前 URL 更新即可；后续如果要长期固定，就要换 ngrok 固定域名方案。
