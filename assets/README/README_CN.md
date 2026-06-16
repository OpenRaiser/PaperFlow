<div align="center">

# PaperFlow

**动态个性化科研论文推荐、精读与报告系统。**

PaperFlow 把每天的论文发现变成一个闭环研究工作流：建立画像、排序当天论文、精读有价值的论文、收集反馈，并让第二天的推荐继续适应你的研究方向。

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB.svg)](https://www.python.org/downloads/)
[![Package](https://img.shields.io/badge/package-paperflow-2E7D32.svg)](https://github.com/OpenRaiser/PaperFlow/blob/main/pyproject.toml)
[![HF Dataset](https://img.shields.io/badge/HF%20Dataset-OpenRaiser%2FPaperFlow-FFD21E.svg)](https://huggingface.co/datasets/OpenRaiser/PaperFlow)
[![License: MIT](https://img.shields.io/badge/License-MIT-111111.svg)](https://github.com/OpenRaiser/PaperFlow/blob/main/LICENSE)

![Personalized Recommendation](https://img.shields.io/badge/personalized-recommendation-2E7D32.svg)
![Scientific Reading](https://img.shields.io/badge/scientific-reading-1565C0.svg)
![Daily Digest](https://img.shields.io/badge/daily-paper%20digest-F9A825.svg)
![Feedback Learning](https://img.shields.io/badge/feedback-learning-6A5ACD.svg)
![Interest Drift](https://img.shields.io/badge/interest-drift-00897B.svg)
![Feishu/Lark](https://img.shields.io/badge/Feishu%2FLark-bot-00A1E9.svg)

**语言**:
[English](https://github.com/OpenRaiser/PaperFlow#readme) ·
[简体中文](https://github.com/OpenRaiser/PaperFlow/blob/main/assets/README/README_CN.md) ·
[日本語](https://github.com/OpenRaiser/PaperFlow/blob/main/assets/README/README_JA.md) ·
[Español](https://github.com/OpenRaiser/PaperFlow/blob/main/assets/README/README_ES.md) ·
[Français](https://github.com/OpenRaiser/PaperFlow/blob/main/assets/README/README_FR.md) ·
[Português](https://github.com/OpenRaiser/PaperFlow/blob/main/assets/README/README_PT.md) ·
[한국어](https://github.com/OpenRaiser/PaperFlow/blob/main/assets/README/README_KO.md)

[快速开始](#快速开始) | [桌面预览](#桌面预览) | [本地 GUI](#本地-gui) |
[GUI 预览](https://openraiser.github.io/PaperFlow/deployments/desktop/static/index.html?demo=1) |
[CLI 用法](#cli-用法) |
[反馈闭环](https://github.com/OpenRaiser/PaperFlow/blob/main/docs/feedback-loop.md) |
[飞书/Lark Bot](#飞书--lark-bot) |
[PaperFlow-Bench](#paperflow-bench) | [复现实验](https://github.com/OpenRaiser/PaperFlow/blob/main/experiments/REPRODUCE.md)

<img src="https://github.com/user-attachments/assets/fd31a62b-00a4-4210-82cb-1ffd080de254" alt="PaperFlow 个性化科研阅读横幅" width="100%">

</div>

---

## 当前版本

首个公开版本包含 **CLI + 本地浏览器 GUI + 可选飞书/Lark Bot**。你可以完全在终端运行 PaperFlow，也可以打开本地 GUI 进行交互式论文选择，或者保持飞书/Lark webhook 服务运行以接收定时推送。

| 项目 | 说明 |
| --- | --- |
| 输入 | 研究画像、论文、PDF、个人主页、Google Scholar 页面 |
| 输出 | 每日论文摘要、精读报告、周度画像报告 |
| 运行时 | 本地 Python CLI、本地浏览器 GUI、SQLite、可选飞书/Lark webhook + ngrok |
| Benchmark | HuggingFace 上的 PaperFlow-Bench 与公开评测脚本 |

## 桌面预览

PaperFlow 现在提供离线优先的桌面浏览器 GUI。它使用和 CLI 相同的本地 SQLite 状态与后端工作流，因此 UI 不是静态 mock：论文拉取、反馈、精读报告、Wiki 图谱更新和设置都会经过本地后端。

<div align="center">
  <img src="https://github.com/user-attachments/assets/c852c134-5ddb-478e-8a13-3fa313dcd812" alt="PaperFlow 离线桌面工作流演示" width="92%">
</div>

<br>

<details>
<summary>查看桌面截图</summary>

| 每日论文流 | 知识 Wiki 图谱 |
| --- | --- |
| <img src="https://github.com/user-attachments/assets/018aa646-41fa-4967-b4d4-6d6a54df51cf" alt="PaperFlow 每日论文推荐流"> | <img src="https://github.com/user-attachments/assets/305279b3-1350-4169-887c-99c0cac29a15" alt="PaperFlow 知识 Wiki 图谱"> |
| 支持日期感知拉取、来源筛选、候选指标、论文动作和后端任务状态。 | 展示后端生成的论文、主题、方法、画像和引用关系。 |

| 带引用的 Wiki 问答 | 本地设置 |
| --- | --- |
| <img src="https://github.com/user-attachments/assets/6685dd75-e2e2-45d1-b440-1ca5325eca1d" alt="PaperFlow 带引用的本地 Wiki 问答"> | <img src="https://github.com/user-attachments/assets/a629cc1e-e26e-4878-9eb3-97565153b711" alt="PaperFlow 本地设置与来源配置"> |
| 流式回答、可点击引用标记和来源卡片。 | Provider key、存储路径、论文来源模式、会议访问和导出控制。 |

</details>

### 产品框架

<img src="https://github.com/user-attachments/assets/60ff5a52-5d09-46c2-be0d-1933c19515b6" alt="PaperFlow 产品框架图" width="100%">

桌面闭环默认是本地优先：画像状态、论文推送、反馈、精读报告和 Wiki 节点都保存在磁盘上，除非你显式启用外部 Provider 或飞书/Lark 导出。

## 为什么是 PaperFlow

科研论文推荐不是一次性的排序问题。真实研究者问的是一个动态问题：**今天我应该读什么，系统明天应该如何适应？**

| 传统论文提醒 | PaperFlow |
| --- | --- |
| 静态关键词或画像匹配 | 带反馈更新的结构化画像 |
| 每天同样的信息流 | 按日期构造候选池和每日摘要预算 |
| 只做推荐 | 推荐 + 精读报告 + 反馈闭环 |
| 没有显式漂移处理 | 短期与长期兴趣漂移建模 |
| 纵向复现困难 | 公开 PaperFlow-Bench episode 与评测器 |

## 核心能力

| 能力 | 作用 |
| --- | --- |
| 画像冷启动 | 从文本、PDF、主页或 Google Scholar 页面建立学术画像 |
| 每日推荐 | 拉取 arXiv、OpenReview 和期刊论文，并排序个性化每日摘要 |
| 精读报告 | 基于元数据和 PDF 内容生成个性化论文报告 |
| 反馈学习 | 从 CLI、GUI、飞书/Lark、选择、跳过、已读和自然语言反馈更新同一画像 |
| 本地研究 Wiki | 将论文推送、报告、引用、反馈和画像信号写入可查询的本地图谱 |
| 带引用 Wiki 问答 | 需要检索时使用本地证据回答，支持可点击引用和 `@` 式显式引用 |
| 离线桌面 GUI | 提供每日拉取、反馈、报告阅读、Wiki 图谱、问答和设置的本地 UI |
| 漂移适应 | 跨天跟踪短窗口与长窗口兴趣变化 |
| 飞书/Lark Bot | 发送每日推送和周报，并处理聊天反馈和 PDF 请求 |
| Benchmark 工具 | 打包、下载、预测并评测 PaperFlow-Bench 提交 |

## 快速开始

PaperFlow 的每日流程有五步。第 1-3 步只需要运行一次，第 4-5 步是日常使用流程。

```bash
# 1. 安装
git clone https://github.com/OpenRaiser/PaperFlow.git
cd PaperFlow
pip install -e ".[all]"          # 完整安装；最小 CLI 可用 `pip install -e .`

# 2. 配置 provider（先用 no-download 设置；详见下文）
cp .env.example .env
# 编辑 .env，设置 PAPERFLOW_LLM_PROVIDER；生产环境还需要 embedding 后端

# 3. 初始化运行时 + 创建用户画像（必需）
paperflow init
paperflow doctor
paperflow profile \
  --user-id user_alice \
  --natural-language "I work on LLM agents for scientific discovery, \
literature mining, and automated paper reading."

# 4. 每日论文推送
paperflow daily --user-id user_alice

# 5. 精读选中的论文
paperflow read 1 3 7 --user-id user_alice

# 可选：用本地浏览器 GUI 完成第 4-5 步
paperflow gui
```

> **第 3 步是必需的。** `paperflow daily / read / feedback` 都会读取 `paperflow profile` 创建的画像。跳过画像就没有个性化评分信号，`paperflow read` 也没有可读取的 push。四种画像冷启动方式见 [初始化用户画像](#初始化用户画像)。

### 离线烟测（无需 API key）

```bash
paperflow demo
```

Demo 使用确定性的 mock/hash provider，因此不需要 API key 或网络。建议在配置真实 provider 前先用它确认安装是否正常。

## 配置 Provider

复制环境变量模板：

```bash
cp .env.example .env
```

`PAPERFLOW_*` 变量是标准配置入口。新安装默认使用 no-download embedding，便于快速运行 `paperflow demo` 和检查；但真实推荐质量需要语义 embedding 后端。

### 选项 A：推荐的生产配置

使用一个 OpenAI 兼容网关同时处理生成和 embedding：

```env
PAPERFLOW_LLM_PROVIDER=openai
PAPERFLOW_LLM_MODEL=gpt-4o-mini

PAPERFLOW_EMBED_PROVIDER=openai
PAPERFLOW_EMBED_MODEL=text-embedding-3-small

OPENAI_API_KEY=sk-...
# OPENAI_BASE_URL=https://your-openai-compatible-gateway/v1
```

通过 `OPENAI_BASE_URL` 支持 OpenAI、DashScope、Azure OpenAI、vLLM 等 OpenAI 兼容服务。如果凭据缺失或仍是占位符，PaperFlow 会在可行处回退到 mock/hash provider，使本地流程仍可测试。

### 选项 B：no-download 烟测

用于安装检查、GUI demo 或不能下载模型权重的课堂环境：

```env
PAPERFLOW_LLM_PROVIDER=mock
PAPERFLOW_EMBED_PROVIDER=hash
```

该模式确定且快速，但 hash 向量不具备真实语义相似性，不建议用于评估推荐质量。

### 选项 C：高质量本地 embedding

仅在机器允许下载并缓存本地模型权重时使用：

```env
PAPERFLOW_EMBED_PROVIDER=sentence_transformers
PAPERFLOW_EMBED_MODEL=BAAI/bge-m3
PAPERFLOW_EMBED_DIMENSIONS=1024
```

本地模式不需要 embedding API key，但首次运行会下载模型权重。`BAAI/bge-m3` 约 2.3GB，不适合快速课堂 demo 或首次安装检查。

修改 provider 后运行：

```bash
paperflow doctor
```

`paperflow doctor` 会打印解析后的 provider 配置。运行时数据保存在 `data/` 下，并被 Git 忽略。

## 初始化用户画像

PaperFlow 对每个 `user_id` 维护一个画像，所有其他命令（`daily`、`read`、`feedback`）都会读取该画像。**第一次每日运行前必须至少创建一个画像**，否则 `paperflow daily` 没有评分依据，`paperflow read` 也没有可读取的 push。

可以用以下四种来源创建画像，也可以组合使用：

```bash
# (a) 自然语言自述（最快）
paperflow profile \
  --user-id user_alice \
  --natural-language "I work on LLM agents for scientific discovery, \
literature mining, and automated paper reading."

# (b) 一篇或多篇你写过或关心的论文
paperflow profile --user-id user_alice --pdf /path/to/my-paper.pdf

# (c) Google Scholar 主页（PaperFlow 抓取公开页面）
paperflow profile \
  --user-id user_alice \
  --scholar-url "https://scholar.google.com/citations?user=..."

# (d) 个人实验室或主页
paperflow profile \
  --user-id user_alice \
  --homepage-url "https://example.edu/~alice"
```

重复运行 `paperflow profile` 默认会把新信号合并进已有画像。只有需要从头重建时才使用 `--reset-existing`。

随时查看画像：

```bash
python scripts/show_profile.py user_alice
```

## 本地 GUI

启动本地浏览器 GUI：

```bash
paperflow gui
```

无需安装即可预览 mock 数据界面：
[PaperFlow GUI Preview](https://openraiser.github.io/PaperFlow/deployments/desktop/static/index.html?demo=1)。

GUI 使用和 CLI 相同的本地 SQLite 数据库，面向真实每日流程而不是独立 mock：

- 选择用户画像并查看画像方向摘要
- 拉取今天的论文，或主动拉取过去某个日期窗口
- 长时间每日拉取在后端任务状态中运行，UI 轮询进度
- 将论文标记为精读、不感兴趣或稍后看
- 提交反馈并更新本地画像/Wiki 信号路径
- 从论文卡生成或重新打开精读报告
- 查看后端生成的 Wiki 图谱并搜索本地知识节点
- 基于本地 Wiki 提问，并获得可点击引用
- 配置 provider、来源模式、存储路径和导出行为

桌面 GUI 不负责后台定时任务。定时飞书/Lark 投递仍使用 `deployments/feishu/`。

常用参数：

```bash
paperflow gui --port 8766
paperflow gui --host 0.0.0.0 --no-browser
```

详细 GUI 说明见 [deployments/desktop/README.md](https://github.com/OpenRaiser/PaperFlow/blob/main/deployments/desktop/README.md)。

## CLI 用法

```bash
paperflow --help
```

| 命令 | 用途 |
| --- | --- |
| `paperflow init` | 创建本地运行目录和 SQLite 表 |
| `paperflow doctor` | 检查依赖、凭据和运行路径 |
| `paperflow demo` | 运行离线 provider demo |
| `paperflow profile` | 从文本、PDF、Scholar 或主页创建/更新用户画像 |
| `paperflow daily` | 生成每日个性化论文推送 |
| `paperflow read` | 生成个性化精读报告 |
| `paperflow wiki` | 列出、搜索并查看本地阅读 Wiki |
| `paperflow feedback` | 为历史 push 记录反馈 |
| `paperflow gui` | 启动本地浏览器 GUI |
| `paperflow eval` | 评测 PaperFlow-Bench 预测 |

生成每日推荐卡但不发送：

```bash
paperflow daily \
  --user-id user_role1 \
  --days 1 \
  --output data/daily_push.txt \
  --dry-run
```

根据上一次推送里的论文编号生成精读报告：

```bash
paperflow read 1 3 7 --user-id user_role1 --no-feishu
```

默认情况下，`paperflow read` 使用该用户在 `data/paperflow.db` 中的最新 push。指定历史 push：

```bash
paperflow read 1 3 7 --user-id user_role1 --push-id push_20260401_090000 --no-feishu
```

每日推送、精读报告、反馈信号和画像漂移快照也会写入本地 PaperFlow Wiki：

```bash
paperflow wiki backfill --user-id user_role1
paperflow wiki topics --user-id user_role1
paperflow wiki stats --user-id user_role1
paperflow wiki search "graph rag" --user-id user_role1
paperflow wiki ask "What have I read about graph RAG?" --user-id user_role1
```

PDF、精读报告 Markdown、月报和 Topic Index 可以直接保存到 Obsidian vault。把四个导出变量指向同一个上级目录：

```env
PAPERFLOW_PDF_DIR=/Users/mario/Documents/Obsidian Vault/Daily Note/Daily Note 2026
PAPERFLOW_READING_REPORTS_DIR=/Users/mario/Documents/Obsidian Vault/Daily Note/Daily Note 2026
PAPERFLOW_MONTHLY_REPORT_DIR=/Users/mario/Documents/Obsidian Vault/Daily Note/Daily Note 2026
PAPERFLOW_TOPIC_INDEX_DIR=/Users/mario/Documents/Obsidian Vault/Daily Note/Daily Note 2026
PAPERFLOW_STORAGE_ROLE_SUBDIR=true
PAPERFLOW_STORAGE_CATEGORY_SUBDIR=true
PAPERFLOW_STORAGE_MONTHLY_SUBDIR=true
```

本地导出默认按 role 分目录。如果 `data/roles.json` 把 `role1` 映射到 `user_role1`，则 `--user-id user_role1` 会写入 `role1/pdf/arXiv - May 2026/`、`role1/reading_reports/arXiv - May 2026/`、`role1/monthly_reports/` 和 `role1/topic_index/`。月报和 Topic Index 文件名也包含目标月份，例如 `PaperFlow Monthly Report - role1 - 2026-05.md`。只有想回到更扁平的旧布局时才设置 `PAPERFLOW_STORAGE_ROLE_SUBDIR=false` 或 `PAPERFLOW_STORAGE_CATEGORY_SUBDIR=false`。

导出 Obsidian 月度阅读摘要和 Topic Index：

```bash
paperflow wiki monthly --user-id user_role1
```

不提供 `--month` 时，PaperFlow 导出当前自然月。只有需要重新生成旧月份时才使用 `--month 2026-05`。

飞书/Lark 文档导出是可选功能，独立于 GUI 和 CLI 核心。配置见 [docs/feishu-doc-export.md](https://github.com/OpenRaiser/PaperFlow/blob/main/docs/feishu-doc-export.md)。配置后 CLI 用法：

```bash
paperflow read 1 --user-id user_role1
paperflow read 1 --user-id user_role1 --folder-id <feishu_folder_token>
```

在 GUI 中，生成精读报告时勾选“同时尝试写入飞书文档”。

记录反馈：

```bash
paperflow feedback \
  --user-id user_role1 \
  --push-id push_20260401_090000 \
  --reply "1, 3"
```

CLI、GUI 和飞书/Lark bot 回复产生的反馈都会存入同一个 SQLite 数据库，并更新该 `user_id` 的同一份画像。完整学习路径见 [docs/feedback-loop.md](https://github.com/OpenRaiser/PaperFlow/blob/main/docs/feedback-loop.md)。

## 飞书 / Lark Bot

飞书/Lark 集成是可选的。需要让 PaperFlow 作为聊天 bot 定时推送论文和周报时使用。

如果只需要把精读报告导出为飞书/Lark 文档，请使用 [docs/feishu-doc-export.md](https://github.com/OpenRaiser/PaperFlow/blob/main/docs/feishu-doc-export.md)，该路径不需要 ngrok 或 webhook 回调。

把飞书/Lark 与 ngrok 参数写入 `.env`：

```env
FEISHU_APP_ID=
FEISHU_APP_SECRET=
FEISHU_VERIFICATION_TOKEN=
FEISHU_USER_ID=

NGROK_AUTHTOKEN=
NGROK_DOMAIN=
```

在 `data/roles.json` 里绑定 role chat ID，然后启动本地 webhook 服务：

```bash
python deployments/feishu/webhook-server/start-with-ngrok.py
```

脚本会打印公网 Request URL。把它填入飞书/Lark 事件订阅页面，并启用 `im.message.receive_v1`。

如果需要定时任务，请保持进程运行：

| 任务 | 默认计划 |
| --- | --- |
| 每日论文推送 | Asia/Shanghai 09:00 |
| 周报 | Asia/Shanghai 周一 10:00 |

查看实时日志：

```powershell
Get-Content data/webhook_stderr.log -Wait
```

常用聊天命令：

```text
profile
daily push
weekly report
1 3
read 1
```

详细设置见 [docs/feishu-webhook-setup.md](https://github.com/OpenRaiser/PaperFlow/blob/main/docs/feishu-webhook-setup.md)。

## PaperFlow-Bench

PaperFlow-Bench 发布在 HuggingFace：[OpenRaiser/PaperFlow](https://huggingface.co/datasets/OpenRaiser/PaperFlow)。

下载：

```bash
python experiments/benchmark/fetch_benchmark.py \
  --output-dir data/PaperFlow-Bench
```

按候选池顺序生成一个简单合法预测文件：

```bash
python experiments/benchmark/make_benchmark_submission.py \
  --benchmark-dir data/PaperFlow-Bench \
  --output data/PaperFlow-Bench/example_predictions.jsonl
```

评测：

```bash
paperflow eval \
  --benchmark-dir data/PaperFlow-Bench \
  --predictions data/PaperFlow-Bench/example_predictions.jsonl \
  --output data/PaperFlow-Bench/example_metrics.json
```

更多 benchmark 说明：

- [docs/benchmark.md](https://github.com/OpenRaiser/PaperFlow/blob/main/docs/benchmark.md)
- [experiments/REPRODUCE.md](https://github.com/OpenRaiser/PaperFlow/blob/main/experiments/REPRODUCE.md)

## 工作流

```text
research profile
      |
      v
daily candidate pool  ->  scoring + drift adjustment  ->  paper digest
      |                                                       |
      v                                                       v
arXiv / OpenReview / journals                         reading reports
                                                              |
                                                              v
                                                     feedback + profile update
                                                              |
                                                              v
                                                     tomorrow's recommendation
```

## 仓库结构

```text
PaperFlow/
  paperflow/                 CLI 与 provider 抽象
  agents/                    核心工作流 agent
  skills/                    抓取、解析、画像和存储 helper
  deployments/desktop/       可选本地浏览器 GUI
  deployments/feishu/        可选飞书/Lark bot 部署
  experiments/               Benchmark 与论文复现实验脚本
  scripts/                   运维工具
  config/                    来源、打分和方向配置
  docs/                      设置与 benchmark 文档
  tests/                     单元和集成测试
```

## 开发检查

```bash
pytest tests -q
pytest experiments/tests -q
```

GitHub Actions 会运行主测试套件。实验测试放在 `experiments/tests/`，用于 benchmark 和复现实验验证。

## 文档

完整导览见 [docs/README.md](https://github.com/OpenRaiser/PaperFlow/blob/main/docs/README.md)。常用后续文档：

- [docs/quickstart.md](https://github.com/OpenRaiser/PaperFlow/blob/main/docs/quickstart.md)：首次本地运行
- [docs/configuration.md](https://github.com/OpenRaiser/PaperFlow/blob/main/docs/configuration.md)：环境变量和路径
- [docs/feedback-loop.md](https://github.com/OpenRaiser/PaperFlow/blob/main/docs/feedback-loop.md)：CLI / GUI / 飞书画像学习
- [deployments/desktop/README.md](https://github.com/OpenRaiser/PaperFlow/blob/main/deployments/desktop/README.md)：本地 GUI 行为
- [PaperFlow GUI Preview](https://openraiser.github.io/PaperFlow/deployments/desktop/static/index.html?demo=1)：无需安装的 UI 预览
- [docs/feishu-doc-export.md](https://github.com/OpenRaiser/PaperFlow/blob/main/docs/feishu-doc-export.md)：飞书文档导出
- [docs/feishu-webhook-setup.md](https://github.com/OpenRaiser/PaperFlow/blob/main/docs/feishu-webhook-setup.md)：webhook + ngrok bot 部署

## 引用

如果你在学术工作中使用 PaperFlow 或 PaperFlow-Bench，请引用：

```bibtex
@article{wang2026paperflow,
  title={PaperFlow: Profiling, Recommending, and Adapting Across Daily Paper Streams},
  author={Wang, Fuqiang and Tan, Song and Guo, Zheng and Fu, Jiaohao and Xu, Xinglong and Yu, Bihui and Dong, Jie and Sun, Zheng and Li, Siyuan and Wei, Jingxuan and others},
  journal={arXiv preprint arXiv:2606.07454},
  year={2026}
}
```

正式引用信息会在论文发表后更新。

## License

PaperFlow 使用 MIT License 发布。详见 [LICENSE](https://github.com/OpenRaiser/PaperFlow/blob/main/LICENSE)。
