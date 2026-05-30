# Webhook Server

这里是 PaperFlow 的飞书消息入口服务。

推荐启动方式：

```powershell
python deployments\feishu\webhook-server\start-with-ngrok.py
```

它会同时完成：

- 运行时目录自举
- 数据库初始化
- `roles.json` 自动生成
- webhook 服务启动
- ngrok 隧道创建或复用
- 输出飞书需要的 `Request URL`

## 文件说明

- [`start-with-ngrok.py`](start-with-ngrok.py)
  - 推荐入口
  - 同时启动 webhook 和 ngrok
- [`start.py`](start.py)
  - 仅启动本地 webhook
  - 支持 `--verify`
- [`scripts/webhook_server.py`](scripts/webhook_server.py)
  - 实际 HTTP 处理逻辑
- [`scripts/scheduler.py`](scripts/scheduler.py)
  - 每日推送 / 周报调度逻辑

## 快速命令

### 检查环境变量

```powershell
python deployments\feishu\webhook-server\start.py --verify
```

### 启动本地 webhook

```powershell
python deployments\feishu\webhook-server\start.py
```

### 启动 webhook + ngrok

```powershell
python deployments\feishu\webhook-server\start-with-ngrok.py
```

## 输出文件

启动成功后会生成：

- `data/ngrok_url.txt`
- `data/feishu_request_url.txt`
- `data/ngrok_runtime.log`

其中 `data/feishu_request_url.txt` 里的地址要填到飞书开放平台事件订阅的 `Request URL`。

## 静态域名（推荐：URL 永不变动）

ngrok 免费账号送一个永久静态域名，配一次飞书 `Request URL` 之后就不再需要每次重新粘贴。

一次性设置：

1. 注册 / 登录：<https://dashboard.ngrok.com/signup> 或 <https://dashboard.ngrok.com/login>
2. 配置 authtoken（每台机器一次）：<https://dashboard.ngrok.com/get-started/your-authtoken>

   ```powershell
   ngrok config add-authtoken <your-token>
   ```

3. 在 <https://dashboard.ngrok.com/domains> 点 **+ New Domain**，复制返回的 `xxx-yyy-zzz.ngrok-free.app`。
4. 在 `.env` 中加入：

   ```env
   NGROK_DOMAIN=xxx-yyy-zzz.ngrok-free.app
   ```

5. 飞书开放平台 → 事件订阅 → `Request URL` 填一次：

   ```
   https://xxx-yyy-zzz.ngrok-free.app/
   ```

之后每次只需运行：

```powershell
python deployments\feishu\webhook-server\start-with-ngrok.py
```

也可以临时通过命令行覆盖：

```powershell
python deployments\feishu\webhook-server\start-with-ngrok.py --ngrok-domain other-domain.ngrok-free.app
```

## 调度默认值

- 每日推送：`09:00`
- 周报：每周一 `10:00`
- 时区：`Asia/Shanghai`

可以通过 `.env` 调整：

```env
PAPERFLOW_SCHEDULER_ENABLED=true
PAPERFLOW_TIMEZONE=Asia/Shanghai
PAPERFLOW_DAILY_PUSH_TIME=09:00
PAPERFLOW_WEEKLY_REPORT_TIME=10:00
PAPERFLOW_WEEKLY_REPORT_WEEKDAY=0
```

## 详细部署说明

完整安装、飞书配置、角色配置、联调和 GitHub 发布流程见根目录 [`README.md`](../../README.md)。
