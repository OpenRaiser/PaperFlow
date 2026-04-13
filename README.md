# SciTaste

SciTaste 是一个运行在飞书群聊里的论文助手。

它基于 `Feishu webhook + ngrok` 接收消息，完成这些事情：

- 冷启动学术画像
- 每日论文推送
- 反馈学习
- 精读报告生成
- 周报生成
- 多角色 / 多群聊独立画像

当前仓库保留并推荐的唯一启动方案是：

`python services\webhook-server\start-with-ngrok.py`

这个入口会自动完成运行时自举，包括：

- 自动创建 `data/`、`models/`、`data/webhook_task_locks/`
- 自动创建 `data/scitaste.db`
- 自动从 `config/roles.example.json` 复制出 `data/roles.json`
- 自动为 `roles.json` 里的角色初始化基础学术画像

## 功能概览

- 冷启动
  - 支持自然语言初始化画像
  - 支持基于角色描述自动生成基础方向
  - 支持 PDF 冷启动补充
- 每日推送
  - 聚合 arXiv、OpenReview、期刊源
  - 按相关度分组输出到飞书
  - 支持 `all red`、`none`、编号选择
- 反馈学习
  - 根据选择和跳过动态更新画像
  - 支持“我对 XXX 不感兴趣”“我最近对 XXX 更感兴趣了”这类自然语言修正
- 精读报告
  - 用户选中文献后自动生成飞书文档
  - 自动回发文档链接到群聊
- 周报
  - 汇总近期推送、选择率、画像变化
- 定时任务
  - 默认每天 `09:00` 推送每日论文
  - 默认每周一 `10:00` 推送周报

## 项目结构

```text
scitaste/
├─ agents/                       # 各业务 Agent
├─ skills/                       # 抓取、嵌入、飞书发送、数据库等基础能力
├─ services/webhook-server/      # 飞书 webhook 服务与 ngrok 启动入口
├─ scripts/                      # 初始化、清库、调试辅助脚本
├─ config/                       # 示例角色配置、词典、配置文件
├─ tests/                        # 自动化测试
├─ data/                         # 运行时数据，不提交
├─ models/                       # 本地模型目录，不提交
├─ .env.example                  # 环境变量模板
├─ environment.yml               # 推荐 conda 环境
├─ requirements.txt              # Python 依赖
└─ README.md
```

## 1. 前置条件

至少需要这些：

- Python 3.10
- Conda 或 Miniconda
- Node.js 18+
- `ngrok`
- `lark-cli`
- 一个飞书开放平台应用

可选但推荐：

- OpenAI-compatible 大模型 / embedding API
- OpenReview 账号
- IEEE API Key

## 2. 安装步骤

### 2.1 克隆仓库

```powershell
git clone https://github.com/YOUR_USERNAME/scitaste.git
cd scitaste
```

### 2.2 创建 conda 环境

推荐直接使用仓库里的环境定义：

```powershell
conda env create -f environment.yml
conda activate scitaste
```

如果环境已经存在，更新方式：

```powershell
conda activate scitaste
conda env update -f environment.yml --prune
```

如果你想手动创建，也可以：

```powershell
conda create -n scitaste python=3.10 -y
conda activate scitaste
pip install -r requirements.txt
```

## 3. 安装外部工具

### 3.1 安装 ngrok

下载并安装 ngrok 之后，先完成一次授权：

```powershell
ngrok config add-authtoken YOUR_NGROK_TOKEN
ngrok version
```

也可以不写入全局配置，而是在 `.env` 里填写：

```env
NGROK_AUTHTOKEN=your_ngrok_token_here
```

### 3.2 安装 lark-cli

```powershell
npm install -g @larksuite/cli
lark-cli --version
```

登录并授权：

```powershell
lark-cli auth login --domain im,docs,drive --recommend
lark-cli auth status
```

如果系统找不到 `lark-cli`，可以在 `.env` 中手动指定：

```env
FEISHU_CLI_CMD=C:\path\to\lark-cli.cmd
```

## 4. 配置飞书开放平台

你需要创建一个飞书应用，并至少拿到：

- `FEISHU_APP_ID`
- `FEISHU_APP_SECRET`
- `FEISHU_VERIFICATION_TOKEN`

事件订阅至少打开：

- `im.message.receive_v1`

后面启动成功后，把生成的 `Request URL` 填回飞书后台。

## 5. 配置环境变量

先复制模板：

```powershell
Copy-Item .env.example .env
```

然后填写 `.env`。

### 5.1 最小必填项

下面这些是必须的：

```env
FEISHU_APP_ID=cli_xxxxxxxxxxxxx
FEISHU_APP_SECRET=your_app_secret_here
FEISHU_VERIFICATION_TOKEN=your_verification_token_here
FEISHU_BOT_NAME=SciTaste Bot
NGROK_AUTHTOKEN=your_ngrok_token_here
```

### 5.2 推荐的 API 配置

当前项目已经验证通过的模式是 OpenAI-compatible 接口：

```env
OPENAI_API_KEY=your_api_key_here
OPENAI_BASE_URL=https://api.boyuerichdata.opensphereai.com/v1
OPENAI_API_TIMEOUT=60

EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=Qwen/Qwen3-Embedding-8B
EMBEDDING_DIMENSIONS=1024

LLM_PARSER_PROVIDER=openai
LLM_PARSER_OPENAI_MODEL=qwen3.5-plus
READING_REPORT_LLM_TIMEOUT=180
```

如果你的网关同时兼容 Anthropic，也可以保留：

```env
ANTHROPIC_API_KEY=your_api_key_here
ANTHROPIC_BASE_URL=https://api.boyuerichdata.opensphereai.com
```

如果你不用这个网关，把 `OPENAI_BASE_URL` / `ANTHROPIC_BASE_URL` 改成你自己的服务地址即可。

### 5.3 可选配置

如果你要启用定时任务自定义时间：

```env
SCITASTE_SCHEDULER_ENABLED=true
SCITASTE_TIMEZONE=Asia/Shanghai
SCITASTE_DAILY_PUSH_TIME=09:00
SCITASTE_WEEKLY_REPORT_TIME=10:00
SCITASTE_WEEKLY_REPORT_WEEKDAY=0
SCITASTE_SCHEDULER_POLL_SECONDS=30
SCITASTE_SCHEDULER_GRACE_MINUTES=10
```

如果你要指定冷启动基线 PDF：

```env
SCITASTE_BASELINE_PDF=C:\path\to\baseline.pdf
```

如果你要调阅读报告解析参数：

```env
READING_REPORT_PDF_MODE=always
READING_REPORT_PDF_TIMEOUT=60
READING_REPORT_ARXIV_TIMEOUT=12
READING_REPORT_ABSTRACT_CHARS=1200
READING_REPORT_SECTION_CHARS=1800
```

## 6. 角色配置

第一次启动时，如果 `data/roles.json` 不存在，系统会自动从 [`config/roles.example.json`](config/roles.example.json) 复制一份。

你只需要改这两个字段：
//群id
- `description`
- `feishu_chat_id`

示例：

```json
{
  "roles": {
    "rolea": {
      "user_id": "user_rolea",
      "description": "direction: data-native scientific discovery, bio-molecular data infrastructure, gui agent",
      "feishu_chat_id": "oc_xxxxxxxxxxxxxxxxxxxxx"
    }
  },
  "current_role": "rolea"
}
```

说明：

- `description` 会在首次启动时用于生成该角色的基础学术画像
- `feishu_chat_id` 为空时，定时推送无法发到群里
- 每个角色对应一个独立画像

## 7. 启动系统

推荐的一键启动命令只有这一条：

```powershell
python services\webhook-server\start-with-ngrok.py
```

启动成功后，终端会打印：

- 本地 webhook 地址
- 健康检查地址
- ngrok 公网地址
- 飞书事件订阅要填的 `Request URL`
- 当前自动调度时间表

同时也会生成两个本地文件：

- `data/ngrok_url.txt`
- `data/feishu_request_url.txt`

如果你只想验证环境，不带 ngrok：

```powershell
python services\webhook-server\start.py --verify
```

如果你只想起本地 webhook：

```powershell
python services\webhook-server\start.py
```

## 8. 飞书后台填写 Request URL

启动成功后，把 `data/feishu_request_url.txt` 中的地址填到：

`飞书开放平台 -> 你的应用 -> Event Subscription -> Request URL`

然后保存。

如果你重启 ngrok，公网地址通常会变化，飞书后台的 `Request URL` 也要同步更新。（一般不会变化）

## 9. 首次联调流程

建议按这个顺序验证：

1. 启动系统
2. 打开 `http://127.0.0.1:8080/health`
3. 确认返回 `{"status":"healthy"}`
4. 在飞书群里发送 `冷启动`
5. 在飞书群里发送 `推送`
6. 回复 `1-3` 或 `all red`
7. 确认是否生成精读文档链接
8. 在飞书群里发送 `周报`

推荐再补测这几个自然语言修正：

- `我对GUI Agent不感兴趣`
- `我不需要Cold Start方向`
- `加个必读作者：Mohammed AlQuraishi`
- `去掉机构上海AI Lab`

## 10. 常用命令

### 10.1 启动

```powershell
conda activate scitaste
python services\webhook-server\start-with-ngrok.py
```

### 10.2 初始化数据库

```powershell
python scripts\init_db.py
```

### 10.3 清理数据库

```powershell
python scripts\clear_database.py --action full_reset --yes
```

### 10.4 查看数据库

```powershell
python scripts\view_db.py
```

### 10.5 查看某个角色画像

```powershell
python scripts\show_profile.py --user-id user_rolea
```

## 11. 定时任务

启动 `start-with-ngrok.py` 后，调度器会跟着 webhook 进程一起启动。

默认策略：

- 每天 `09:00` 给每个已配置 `feishu_chat_id` 的角色推送每日论文
- 每周一 `10:00` 给每个已配置 `feishu_chat_id` 的角色推送周报

如果你不想启用自动任务：

```env
SCITASTE_SCHEDULER_ENABLED=false
```

## 12. 上传到 GitHub 前要注意什么

这些内容不应该提交：

- `.env`
- `data/` 下的运行时文件
- `models/` 下的本地模型
- 本地数据库
- ngrok 临时 URL
- 本地缓存、日志、`__pycache__`

仓库已经通过 `.gitignore` 忽略这些内容。

你在公开仓库里应该保留：

- `.env.example`
- `config/roles.example.json`
- `environment.yml`
- `requirements.txt`
- `README.md`

## 13. Git 提交流程

验证通过后，推荐这样提交：

```powershell
git status
git add .
git commit -m "chore: clean repo and document deployment flow"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/scitaste.git
git push -u origin main
```

如果远程已经存在，只需要：

```powershell
git add .
git commit -m "chore: clean repo and document deployment flow"
git push
```

## 14. 故障排查

### 14.1 飞书发消息没有反应

先检查：

- `http://127.0.0.1:8080/health` 是否正常
- `http://127.0.0.1:4040/api/tunnels` 是否有指向 `localhost:8080` 的隧道
- 飞书后台 `Request URL` 是否是最新 ngrok 地址

### 14.2 启动时报缺少环境变量

先运行：

```powershell
python services\webhook-server\start.py --verify
```

然后补齐缺失项。

### 14.3 精读报告慢

常见原因：

- 选中的论文源站不直接提供 PDF
- arXiv / 期刊页解析较慢
- 当前 LLM 网关响应慢

### 14.4 推送结果不稳定或全红

先确认：

- embedding 是否真实生效
- 数据库里是否残留旧维度 embedding
- 当前画像是否过窄

必要时先清库再重启验证：

```powershell
python scripts\clear_database.py --action full_reset --yes
python services\webhook-server\start-with-ngrok.py
```


这样只需要：

1. 创建 conda 环境
2. 安装 ngrok 和 lark-cli
3. 配 `.env`
4. 填 `roles.json`
5. 运行 `python services\webhook-server\start-with-ngrok.py`

就能把整个系统跑起来。
