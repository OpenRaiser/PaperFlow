# PaperFlow 本地 GUI

这是 PaperFlow 的本地浏览器工作台，不额外引入前端依赖。它会启动一个
Python 标准库 HTTP 服务，并从本目录提供静态 HTML/CSS/JS。

```bash
paperflow gui
```

不下载代码也可以先看界面预览：

<https://openraiser.github.io/PaperFlow/deployments/desktop/static/index.html?demo=1>

这个链接使用模拟数据，不会调用本地 API，也不会访问真实飞书或模型服务。
需要在 GitHub 仓库 Settings → Pages 中启用 `main` branch / root 后才会生效。

使用自定义端口，并且不自动打开浏览器：

```bash
paperflow gui --port 8766 --no-browser
```

GUI 与 CLI 共用同一套 SQLite 数据库和运行目录：

- `data/paperflow.db`
- `PAPERFLOW_PDF_DIR`
- `PAPERFLOW_READING_REPORTS_DIR`
- `PAPERFLOW_WIKI_DIR`
- `PAPERFLOW_MONTHLY_REPORT_DIR`
- `PAPERFLOW_TOPIC_INDEX_DIR`

## 精读报告保存地址

GUI 里填写的 `arXiv ID / URL` 或 `PDF 路径` 是**输入地址**，不是输出地址。
精读报告生成之后保存到哪里，由 `.env` 里的路径变量控制：

```env
# 下载或缓存的论文 PDF 保存到这里
PAPERFLOW_PDF_DIR=./data/exports

# 生成的精读 Markdown 报告保存到这里
PAPERFLOW_READING_REPORTS_DIR=./data/exports

# 月报和 Topic Index 也填同一个上级目录
PAPERFLOW_MONTHLY_REPORT_DIR=./data/exports
PAPERFLOW_TOPIC_INDEX_DIR=./data/exports

# 默认按角色名 / user_id 分目录，避免多个角色互相覆盖
PAPERFLOW_STORAGE_ROLE_SUBDIR=true

# 默认按输出类别分目录，形成 role1/pdf、role1/reading_reports 等结构
PAPERFLOW_STORAGE_CATEGORY_SUBDIR=true

# 默认让 PDF 和精读报告按月份进入 arXiv - May 2026 这样的子目录
PAPERFLOW_STORAGE_MONTHLY_SUBDIR=true
```

默认还会按 `data/roles.json` 里的角色名分目录。例如 `role1 -> user_role1`
时，`--user-id user_role1` 的 PDF、精读 Markdown、月报和 Topic Index 会写到
`role1/pdf/arXiv - May 2026/`、`role1/reading_reports/arXiv - May 2026/`、
`role1/monthly_reports/` 和 `role1/topic_index/` 下。月报和 Topic Index 的文件名
会继续带 `2026-05` 这样的月份。如果确定要扁平化旧结构，设置
`PAPERFLOW_STORAGE_ROLE_SUBDIR=false` 或 `PAPERFLOW_STORAGE_CATEGORY_SUBDIR=false`。

如果想写入 Obsidian，可以把四个路径都改成同一个 vault 上级目录，例如：

```env
PAPERFLOW_PDF_DIR=/Users/mario/Documents/Obsidian Vault/Daily Note/Daily Note 2026
PAPERFLOW_READING_REPORTS_DIR=/Users/mario/Documents/Obsidian Vault/Daily Note/Daily Note 2026
PAPERFLOW_MONTHLY_REPORT_DIR=/Users/mario/Documents/Obsidian Vault/Daily Note/Daily Note 2026
PAPERFLOW_TOPIC_INDEX_DIR=/Users/mario/Documents/Obsidian Vault/Daily Note/Daily Note 2026
PAPERFLOW_STORAGE_ROLE_SUBDIR=true
PAPERFLOW_STORAGE_CATEGORY_SUBDIR=true
PAPERFLOW_STORAGE_MONTHLY_SUBDIR=true
```

改完 `.env` 后重新启动 `paperflow gui`。GUI 的 `运行设置` 面板只负责查看当前路径，
不负责在浏览器里改 `.env`。

主流程：

1. 选择或创建用户画像。
2. 运行每日推送，或加载最近一次推送。
3. 勾选要精读的论文，并显式标记“不感兴趣”的论文。
4. 提交反馈，可选择同步生成本地 Markdown 精读报告。
   勾选“同时尝试写入飞书文档”后，GUI 会在本地报告生成后尝试创建飞书文档。
5. 检索或询问本地 PaperFlow Wiki。

GUI 里的选择、标记“不感兴趣”和提交反馈，会和 CLI / 飞书反馈一样更新同一个
`user_id` 对应的用户画像和 drift 状态。完整反馈闭环见
[../../docs/feedback-loop.md](../../docs/feedback-loop.md)。

如果需要把本月论文简介和 Topic Index 写入 Obsidian，先在 `.env` 中配置
`PAPERFLOW_MONTHLY_REPORT_DIR` 和可选的 `PAPERFLOW_TOPIC_INDEX_DIR`，再运行：

```bash
paperflow wiki monthly --user-id user_role1
```

不传 `--month` 时会自动导出当前日历月份；只有补生成历史月份时才需要传
`--month 2026-05`。

其他面板：

- `精读论文`：从 arXiv ID/URL 或本地 PDF 路径生成精读报告。
- `必读规则`：添加或移除强约束作者、机构、关键词。
- `角色管理`：创建、切换、删除本地研究角色。
- `反馈历史`：筛选已保存的反馈、报告和画像漂移记录。
- `运行设置`：查看存储路径，并手动运行 LLM/Embedding 烟测。

GUI 不负责后台定时任务。飞书/Lark 的每日定时推送仍然位于 `deployments/feishu/`。

GUI 只提供一个调用入口：勾选“同时尝试写入飞书文档”后，精读报告会先生成
本地 Markdown，再尝试创建飞书文档；不勾选时只生成本地 Markdown。

飞书应用、`lark-cli`、云文档权限、文件夹 token 的配置独立维护，见
[../../docs/feishu-doc-export.md](../../docs/feishu-doc-export.md)。如果飞书文档写入失败，
本地 Markdown 仍会保留，GUI 会显示失败原因。
