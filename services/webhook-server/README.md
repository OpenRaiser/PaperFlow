# Webhook Server

这里是 SciTaste 的飞书消息入口服务。

推荐启动方式：

```powershell
python services\webhook-server\start-with-ngrok.py
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
python services\webhook-server\start.py --verify
```

### 启动本地 webhook

```powershell
python services\webhook-server\start.py
```

### 启动 webhook + ngrok

```powershell
python services\webhook-server\start-with-ngrok.py
```

## 输出文件

启动成功后会生成：

- `data/ngrok_url.txt`
- `data/feishu_request_url.txt`
- `data/ngrok_runtime.log`

其中 `data/feishu_request_url.txt` 里的地址要填到飞书开放平台事件订阅的 `Request URL`。

## 调度默认值

- 每日推送：`09:00`
- 周报：每周一 `10:00`
- 时区：`Asia/Shanghai`

可以通过 `.env` 调整：

```env
SCITASTE_SCHEDULER_ENABLED=true
SCITASTE_TIMEZONE=Asia/Shanghai
SCITASTE_DAILY_PUSH_TIME=09:00
SCITASTE_WEEKLY_REPORT_TIME=10:00
SCITASTE_WEEKLY_REPORT_WEEKDAY=0
```

## 详细部署说明

完整安装、飞书配置、角色配置、联调和 GitHub 发布流程见根目录 [`README.md`](../../README.md)。
