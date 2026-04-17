# SciTaste
## 最新状态（2026-04）

- 冷启动第一期已落地：优先解析个人主页研究方向，再融合 Google Scholar 的兴趣标签、代表论文、分页发表记录、合作作者和引用统计信号。
- 飞书侧已经可以直接粘贴个人主页链接或 Google Scholar 链接触发增强冷启动；没有 Scholar 的用户仍可继续使用自然语言/PDF 冷启动。
- 第二期代码清理已完成：`agents/coldstart-agent/main.py` 与 `agents/master-coordinator/main.py` 中用于冷启动、画像展示和命令识别的重复旧实现已收敛为单一正式版本。
- 统一方向层、兴趣迁移推荐联动、周报解释增强、精读正文 embedding 检索增强、调度器重试 / 补偿与 `/health` 运行态快照均已接入主流程。
- 飞书直传 PDF 现已接入“阅读信号侧链”：单篇上传只记弱正信号；同方向连续上传/精读会进入短期兴趣；若再补一句“这类我最近想多看”会按强信号强化。
- 飞书里直接发送 PDF 文本链接现也可触发精读，不再局限于文件直传；该入口同样会复用去重、阅读信号与后续排序联动。
- 必读清单已切回硬优先：命中后会稳定保留并排到推送顶部；Scholar 冷启动也已补入高引代表作与更细合作网络信号。
- 当前全量回归已通过：`pytest -q` 共 `285 passed`；`python -m py_compile` 已覆盖本轮主要修改模块。
- README / TODO 已同步到当前实现状态；Scholar 后续增强重点保留在更强反爬 fallback、跨源补全和更细粒度合作网络信号。

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
  - 显式偏好 + 隐式反馈 + 时间衰减 + 漂移检测共同更新画像
  - `interest_vector` 会随反馈主链路更新，并直接影响下一轮推荐排序
  - `must_read` 已改为软规则加分，不再硬性置顶压过所有高相关论文
  - 支持“我对 XXX 不感兴趣”“我最近对 XXX 更感兴趣了”这类自然语言修正
- 精读报告
  - 用户选中文献后自动生成飞书文档
  - 自动回发文档链接到群聊
  - 优先对 arXiv / OpenReview / CVF / ECVA 可用 PDF 做全文级精读
  - 当 PDF 不可用时，尽量回退到 source page 正文分节生成完整模板
  - 对 DOI / ACM 类受限页面，优先回退 OpenAlex / Crossref 元数据，避免精读退化成空壳
  - 支持在飞书群里直接上传 PDF，并走本地解析 + 精读文档生成链路
  - 支持在飞书群里直接发送 PDF 文本链接，并走下载解析 + 精读文档生成链路
- 周报
  - 汇总近期推送、选择率、画像变化
  - 展示兴趣迁移状态、漂移分数、漂移主题与更新解释
- 定时任务
  - 默认每天 `09:00` 推送每日论文
  - 默认每周一 `10:00` 推送周报
  - 可通过 `SCITASTE_SCHEDULER_ENABLED=false` 关闭

## 当前仍需增强项

- Google Scholar 冷启动首轮已完成；后续仍可继续增强更强的反爬兜底、跨源补全和更细粒度的合作网络信号
- 扫描版 PDF 的 OCR 增强首轮已接入；后续仍可继续增强对公式、表格、多语言和大文档的精细化支持
- ACM / 付费 publisher 全文增强首轮已接入；后续仍可继续增强更多发表商与仓储源的作者稿探测
- Webhook 服务的生产化部署能力还缺开机自启、日志轮转、错误告警
- 飞书表情反馈写回行为日志、菜单按钮路由到 Agent 仍未接入
- ngrok 固定域名 / 持久化隧道尚未配置

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

### 2.1 创建 conda 环境

先进入项目目录，再创建并激活环境。

推荐直接使用项目里的环境定义：

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

说明：
- `READING_REPORT_PDF_MODE=always` 会尽量优先解析 PDF；`smart` 会在元数据已足够时跳过部分 PDF 抓取
- OpenAlex / Crossref 的 DOI 元数据回退默认启用，不需要额外环境变量
- 对 ACM / 受限 publisher 页面，如果正文和 PDF 都不可得，系统会至少补回摘要、作者、DOI、PDF 链接

### 5.4 兴趣迁移 / 漂移参数

默认情况下这一组参数不用改；只有你想调兴趣迁移的敏感度、恢复速度和热度衰减速度时才需要配置：

```env
SCITASTE_DRIFT_LONG_WINDOW_SIZE=30
SCITASTE_DRIFT_LONG_WINDOW_DAYS=60
SCITASTE_DRIFT_SHORT_WINDOW_SIZE=8
SCITASTE_DRIFT_SHORT_WINDOW_DAYS=14
SCITASTE_DRIFT_THRESHOLD=0.35
SCITASTE_DRIFT_RECOVER_THRESHOLD=0.20
SCITASTE_DRIFT_ALPHA_BASE=0.08
SCITASTE_DRIFT_ALPHA_MAX=0.35
SCITASTE_TOPIC_DECAY=0.01
SCITASTE_AUTHOR_DECAY=0.005
SCITASTE_INSTITUTION_DECAY=0.005
```

说明：
- `SCITASTE_DRIFT_LONG_WINDOW_*` 控制长期兴趣窗口，默认看最近 30 篇已选论文，且最多回看 60 天
- `SCITASTE_DRIFT_SHORT_WINDOW_*` 控制短期兴趣窗口，默认看最近 8 篇已选论文，且最多回看 14 天
- `SCITASTE_DRIFT_THRESHOLD` 是进入 `shifting` 的阈值；`SCITASTE_DRIFT_RECOVER_THRESHOLD` 是回到 `recovered` 的阈值
- `SCITASTE_DRIFT_ALPHA_BASE` 和 `SCITASTE_DRIFT_ALPHA_MAX` 控制更新器的自适应步长，数值越大，画像响应越快
- `SCITASTE_TOPIC_DECAY` / `SCITASTE_AUTHOR_DECAY` / `SCITASTE_INSTITUTION_DECAY` 控制未被近期命中的主题、作者、机构热度自然回落
- 当前漂移参数第一版只影响“推荐排序 + 周报解释”，不会直接改写精读报告正文生成逻辑

如果你想压低网络重试 warning：

```env
SCITASTE_SUPPRESS_HTTP_RETRY_WARNINGS=true
```

默认值就是 `true`，这样像 `urllib3.connectionpool` 的可恢复 SSL / retry warning 不会刷屏。

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

## 12. 精读增强策略

当前精读报告按这条优先级链路生成：

- arXiv / OpenReview / CVF / ECVA：优先走 PDF 全文精读
- Nature / Science / Springer 等期刊：优先 PDF，失败时尽量回退源站正文分节
- DOI / ACM / DBLP TOC：先尝试源站详情页；如果被 403 或反爬拦截，则回退 OpenAlex / Crossref 元数据

- 部分 ACM / 付费 publisher 页面仍可能同时拦截 HTML 正文和 PDF；当前系统已补 OpenAlex OA 落地页 / 作者稿探测，但在真正全封闭场景下仍可能退回摘要级完整报告

- `pdf`：PDF 全文 + 元数据
- `source_page`：源站正文 + 元数据
- `abstract`：摘要 + 元数据

当前已知边界：

- 某些 publisher 的 PDF 文本抽取会有断行、连字、页眉页脚混入，这是 PDF 解析层的自然限制，不影响主流程
- 冷启动里的 Google Scholar 链接当前已接入增强解析：支持命令行 `--scholar-url`、飞书直接粘贴 Scholar 链接、分页抓取、轻量 fallback，以及合作作者/引用统计信号提取；若页面被强反爬拦截，仍可能失败
- 反馈主链路已经接入漂移感知兴趣迁移，`interest_vector` 会由显式先验、长短窗反馈和混合漂移分数共同更新
- 当前这套兴趣迁移 V1 只影响推荐排序和周报解释，还没有直接驱动精读报告正文生成



## 13. 故障排查

### 13.1 飞书发消息没有反应

先检查：

- `http://127.0.0.1:8080/health` 是否正常
- `http://127.0.0.1:4040/api/tunnels` 是否有指向 `localhost:8080` 的隧道
- 飞书后台 `Request URL` 是否是最新 ngrok 地址

### 13.2 启动时报缺少环境变量

先运行：

```powershell
python services\webhook-server\start.py --verify
```

然后补齐缺失项。

### 13.3 精读报告慢

常见原因：

- 选中的论文源站不直接提供 PDF
- arXiv / 期刊页解析较慢
- 当前 LLM 网关响应慢

如果控制台里经常看到期刊详情页失败，但最后仍能抓到论文：

- 这通常不是主流程错误，而是源站详情页被拦截后，系统自动回退到了 OpenAlex / Crossref 元数据
- 只要最终有 `Fetched X papers` 且摘要不为空，就说明 fallback 生效了

### 13.4 推送结果不稳定或全红

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
