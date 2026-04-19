# SciTaste 数据集 Schema 文档

## 四层架构概览

```
┌─────────────────────────────────────────────────────────────┐
│                        评测层 (Evaluation)                   │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────┐ │
│  │ 主实验结果表     │  │ 消融实验表       │  │ 人工评估表   │ │
│  └─────────────────┘  └─────────────────┘  └─────────────┘ │
└─────────────────────────────────────────────────────────────┘
                              ↑
┌─────────────────────────────────────────────────────────────┐
│                   Episode 轮次层 (Interaction)               │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Episode 统计表 | 交互行为统计表 | 兴趣迁移事件表      │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              ↑
┌─────────────────────────────────────────────────────────────┐
│                    用户画像层 (User Profile)                 │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────┐ │
│  │ 核心研究方向     │  │ Must-read 规则   │  │ 兴趣向量     │ │
│  └─────────────────┘  └─────────────────┘  └─────────────┘ │
└─────────────────────────────────────────────────────────────┘
                              ↑
┌─────────────────────────────────────────────────────────────┐
│                     论文池层 (Paper Pool)                    │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ arXiv | OpenReview | 期刊网页 | DOI 页面 | 统一结构化  │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## 第一层：论文池层 (Paper Pool Layer)

### 功能定位
- 提供推荐、精读和周报分析所使用的候选论文集合
- 统一多个公开学术来源的元数据

### 数据来源
- arXiv API
- OpenReview API
- 主流期刊网页/RSS
- DOI 页面开放元数据
- OpenAlex 补全
- Crossref 补全

### 文件：`paper_pool.csv`

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `paper_id` | INTEGER | 主键，数据库自增 ID |
| `arxiv_id` | TEXT | arXiv 编号（如 2301.12345） |
| `doi` | TEXT | DOI 标识符 |
| `title` | TEXT | 论文标题 |
| `authors_json` | JSON | 作者列表 JSON 数组 |
| `author_count` | INTEGER | 作者数量 |
| `institution` | TEXT | 第一作者机构 |
| `abstract` | TEXT | 摘要全文 |
| `venue` | TEXT | 发表期刊/会议 |
| `publish_date` | DATE | 发表日期 |
| `embedding_model` | TEXT | Embedding 模型标识 |
| `fetched_at` | TIMESTAMP | 抓取时间 |
| `pushed` | BOOLEAN | 是否已推送 |
| `push_date` | DATE | 推送日期 |

### 字段说明

```json
{
  "authors_json": ["John Doe", "Jane Smith"],
  "institution": "MIT",
  "venue": "ICLR 2024",
  "publish_date": "2024-01-15"
}
```

---

## 第二层：用户画像层 (User Profile Layer)

### 功能定位
- 描述系统在某一时刻对用户科研兴趣的结构化理解
- 可持续更新的多粒度画像状态

### 包含内容
- 核心研究方向
- 主题权重
- 作者热度
- 机构热度
- Must-read 规则
- 兴趣向量
- 报告偏好
- 兴趣迁移状态

### 文件：`profiles.jsonl`

每行一个完整的用户画像快照：

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `profile_id` | INTEGER | 数据库主键 |
| `user_id` | TEXT | 用户唯一标识 |
| `role_name` | TEXT | 角色名称（如 rolea） |
| `version` | TEXT | 画像版本号 |
| `db_updated_at` | TIMESTAMP | 数据库更新时间 |
| `profile_json` | JSON | 完整画像数据 |
| `role_metadata` | JSON | 角色元信息 |

### 文件：`profile_summary.csv`

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `profile_id` | INTEGER | 数据库主键 |
| `user_id` | TEXT | 用户唯一标识 |
| `role_name` | TEXT | 角色名称 |
| `version` | TEXT | 画像版本号 |
| `db_updated_at` | TIMESTAMP | 数据库更新时间 |
| `profile_updated_at` | TEXT | 画像内时间戳 |
| `core_directions_json` | JSON | 核心研究方向及权重 |
| `core_direction_count` | INTEGER | 方向数量 |
| `topic_weights_json` | JSON | 主题权重分布 |
| `topic_count` | INTEGER | 主题数量 |
| `must_read_authors` | INTEGER | 必读作者数量 |
| `must_read_institutions` | INTEGER | 必读机构数量 |
| `must_read_keywords` | INTEGER | 必读关键词数量 |
| `must_read_authors_json` | JSON | 必读作者列表 |
| `must_read_institutions_json` | JSON | 必读机构列表 |
| `must_read_keywords_json` | JSON | 必读关键词列表 |
| `drift_status` | TEXT | 漂移状态（stable/shifting/recovered） |
| `drift_score` | FLOAT | 漂移分数 |
| `drift_last_updated_at` | TEXT | 漂移最后更新时间 |
| `drift_detected_at` | TEXT | 漂移检测时间 |
| `drift_top_shift_topics_json` | JSON | 主要漂移主题 |
| `drift_explanation` | TEXT | 漂移解释 |
| `drift_state_json` | JSON | 完整漂移状态 |
| `seed_directions_json` | JSON | 冷启动方向 |
| `bootstrap_summary` | TEXT | 冷启动摘要 |
| `description` | TEXT | 角色描述 |

### 文件：`must_read_profiles.csv`

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `profile_id` | INTEGER | 数据库主键 |
| `user_id` | TEXT | 用户唯一标识 |
| `role_name` | TEXT | 角色名称 |
| `version` | TEXT | 画像版本号 |
| `profile_updated_at` | TEXT | 画像内时间戳 |
| `must_read_authors_json` | JSON | 必读作者列表 |
| `must_read_institutions_json` | JSON | 必读机构列表 |
| `must_read_keywords_json` | JSON | 必读关键词列表 |
| `must_read_author_count` | INTEGER | 必读作者数量 |
| `must_read_institution_count` | INTEGER | 必读机构数量 |
| `must_read_keyword_count` | INTEGER | 必读关键词数量 |
| `must_read_total_count` | INTEGER | 必读规则总数 |

### 画像结构示例

```json
{
  "user_id": "user_rolea",
  "version": "0.1",
  "core_directions": {
    "gui-agent": 0.65,
    "protein-folding": 0.55
  },
  "topic_weights": {
    "gui-agent": 0.65,
    "protein-folding": 0.55
  },
  "must_read": {
    "authors": ["Geoffrey Hinton", "Yann LeCun"],
    "institutions": ["MIT", "Stanford"],
    "keywords": ["reinforcement learning", "transformer"]
  },
  "interest_vector": [...],
  "drift_state": {
    "status": "stable",
    "score": 0.23,
    "top_shift_topics": ["vision-language"],
    "explanation": "最近对视觉 - 语言模型兴趣上升"
  },
  "taste_profile": {
    "preferred_work_type": ["empirical", "systematic"],
    "dispreferred_work_type": ["pure_theory"]
  }
}
```

---

## 第三层：Episode 轮次层 (Episode Layer)

### 功能定位
- 记录完整的"推送—反馈—画像更新"闭环过程
- 核心样本单位（非单篇论文）
- 保留推荐前后的上下文

### 包含内容
- Episode 统计表
- 交互行为统计表

### 文件：`episodes.csv`

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `episode_id` | TEXT | 唯一标识：`{user_id}::{push_id}` |
| `user_id` | TEXT | 用户唯一标识 |
| `role_name` | TEXT | 角色名称 |
| `push_id` | TEXT | 推送批次 ID |
| `episode_type` | TEXT | 类型（daily_push/reading_report/must_read_update） |
| `started_at` | TIMESTAMP | 开始时间 |
| `ended_at` | TIMESTAMP | 结束时间 |
| `log_count` | INTEGER | 日志条数 |
| `candidate_papers` | INTEGER | 候选论文数 |
| `selected_papers` | INTEGER | 选中的论文数 |
| `skipped_papers` | INTEGER | 跳过的论文数 |
| `selection_rate` | FLOAT | 选择率 |
| `candidate_must_read` | INTEGER | 必读候选数 |
| `candidate_high_relevant` | INTEGER | 高相关候选数（🔴） |
| `candidate_maybe_interested` | INTEGER | 可能感兴趣候选数（🟡） |
| `candidate_edge_relevant` | INTEGER | 边缘相关候选数（🔵） |
| `selected_must_read` | INTEGER | 选中的必读数 |
| `selected_high_relevant` | INTEGER | 选中的高相关数 |
| `selected_maybe_interested` | INTEGER | 选中的可能感兴趣数 |
| `selected_edge_relevant` | INTEGER | 选中的边缘相关数 |
| `must_read_retention_rate` | FLOAT | 必读保留率 |
| `must_read_selection_rate` | FLOAT | 必读选择率 |
| `must_read_top_positions_json` | JSON | 必读推送位置列表 |
| `must_read_selected_positions_json` | JSON | 必读选中位置列表 |
| `reports_created` | INTEGER | 生成的精读报告数 |
| `reports_opened` | INTEGER | 打开的精读报告数 |
| `report_open_rate` | FLOAT | 报告打开率 |
| `drift_updates` | INTEGER | 兴趣漂移更新次数 |
| `must_read_updates` | INTEGER | 必读规则更新次数 |
| `latest_drift_status` | TEXT | 最终漂移状态 |
| `latest_drift_score` | FLOAT | 最终漂移分数 |
| `latest_drift_explanation` | TEXT | 最终漂移解释 |
| `drift_status_sequence_json` | JSON | 漂移状态变化序列 |
| `drift_score_sequence_json` | JSON | 漂移分数变化序列 |
| `drift_top_shift_topics_json` | JSON | 漂移主题列表 |
| `paper_coverage` | INTEGER | 涉及的独立论文数 |
| `categories_seen_json` | JSON | 出现的分类标签 |
| `selected_paper_ids_json` | JSON | 选中的论文 ID 列表 |
| `selected_paper_numbers_json` | JSON | 选中的论文编号列表 |

### 文件：`behavior_logs.csv`

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `log_id` | INTEGER | 日志主键 |
| `user_id` | TEXT | 用户唯一标识 |
| `role_name` | TEXT | 角色名称 |
| `push_id` | TEXT | 推送批次 ID |
| `paper_id` | INTEGER | 论文 ID |
| `action` | TEXT | 行为类型（pushed/selected/skipped/created_report/opened_report） |
| `action_type` | TEXT | 行为大类（selected/skipped/reading/doc_open/drift_update） |
| `category` | TEXT | 分类标签（must_read/high_relevant/maybe_interested/edge_relevant） |
| `timestamp` | TIMESTAMP | 时间戳 |
| `is_must_read` | BOOLEAN | 是否必读 |
| `paper_number` | INTEGER | 论文编号（用户可见序号） |
| `rank` | INTEGER | 推荐排名 |
| `score` | FLOAT | 推荐分数 |
| `relevance_signal` | TEXT | 相关性信号 |
| `arxiv_id` | TEXT | arXiv 编号 |
| `push_context` | TEXT | 推送上下文 |
| `drift_status` | TEXT | 漂移状态 |
| `drift_score` | FLOAT | 漂移分数 |
| `adaptive_alpha` | FLOAT | 自适应学习率 |
| `top_shift_topics_json` | JSON | 漂移主题列表 |
| `drift_explanation` | TEXT | 漂移解释 |
| `selected_count` | INTEGER | 本轮选择总数 |
| `skipped_count` | INTEGER | 本轮跳过总数 |
| `feedback_latency_seconds` | FLOAT | 反馈延迟（秒） |
| `doc_token` | TEXT | 文档 Token（精读报告） |
| `doc_url` | TEXT | 文档链接（飞书） |
| `paper_title` | TEXT | 论文标题 |
| `metadata_json` | JSON | 完整元数据 |

### 文件：`drift_events.csv`

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `log_id` | INTEGER | 日志主键 |
| `user_id` | TEXT | 用户唯一标识 |
| `role_name` | TEXT | 角色名称 |
| `push_id` | TEXT | 推送批次 ID |
| `timestamp` | TIMESTAMP | 时间戳 |
| `drift_status` | TEXT | 漂移状态 |
| `drift_score` | FLOAT | 漂移分数 |
| `adaptive_alpha` | FLOAT | 自适应学习率 |
| `selected_count` | INTEGER | 选择数 |
| `skipped_count` | INTEGER | 跳过数 |
| `feedback_latency_seconds` | FLOAT | 反馈延迟 |
| `interest_vector_descriptor` | TEXT | 兴趣向量描述 |
| `top_shift_topics_json` | JSON | 漂移主题列表 |
| `drift_explanation` | TEXT | 漂移解释 |
| `metadata_json` | JSON | 完整元数据 |

### Episode 类型说明

| 类型 | 说明 |
|------|------|
| `daily_push` | 每日推送 episode |
| `reading_report` | 精读报告生成 episode |
| `must_read_update` | 必读规则更新 episode |
| `reading_signal` | 阅读信号强化 episode |
| `other` | 其他类型 |

---

## 第四层：评测层 (Evaluation Layer)

### 功能定位
- 从前三层整理出的实验评估数据
- 支持主实验、消融实验和案例分析

### 包含内容
- 主实验结果表
- 消融实验表
- 人工评估结果表
- 主客观相关性分析表

### 文件：`evaluation/main_experiment_results.csv`

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `experiment_id` | TEXT | 实验唯一标识 |
| `task_type` | TEXT | 任务类型（recommendation/interest_drift/reading_engagement） |
| `model_config` | JSON | 模型配置 |
| `user_id` | TEXT | 用户 ID |
| `episode_id` | TEXT | Episode ID |
| `prediction` | JSON | 预测结果（如排序列表） |
| `ground_truth` | JSON | 真实标签（如用户选择） |
| `metrics` | JSON | 评价指标（NDCG/HitRate/等） |
| `created_at` | TIMESTAMP | 生成时间 |

### 文件：`evaluation/ablation_study.csv`

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `ablation_id` | TEXT | 消融实验标识 |
| `base_experiment_id` | TEXT | 基础实验 ID |
| `ablated_component` | TEXT | 被消融的组件（如 no_drift/no_must_read） |
| `metric_delta` | JSON | 指标变化 |
| `conclusion` | TEXT | 结论 |

### 文件：`evaluation/human_eval_results.csv`

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `eval_id` | TEXT | 评估标识 |
| `episode_id` | TEXT | Episode ID |
| `annotator_id` | TEXT | 标注者 ID |
| `relevance_score` | INTEGER | 相关性评分（1-5） |
| `diversity_score` | INTEGER | 多样性评分（1-5） |
| `novelty_score` | INTEGER | 新颖性评分（1-5） |
| `comments` | TEXT | 评语 |

### 文件：`evaluation/correlation_analysis.csv`

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `analysis_id` | TEXT | 分析标识 |
| `metric_a` | TEXT | 指标 A 名称 |
| `metric_b` | TEXT | 指标 B 名称 |
| `correlation` | FLOAT | 相关系数 |
| `p_value` | FLOAT | P 值 |
| `sample_size` | INTEGER | 样本量 |

---

## 导出文件清单

运行导出脚本后生成的文件结构：

```
data/dataset_exports/scitaste_snapshot_{timestamp}/
├── manifest.json              # 数据清单和统计信息
├── paper_pool.csv             # 论文池层
├── profiles.jsonl             # 用户画像层（完整）
├── profile_summary.csv        # 用户画像层（摘要）
├── must_read_profiles.csv     # 用户画像层（必读规则）
├── behavior_logs.csv          # Episode 层（行为日志）
├── episodes.csv               # Episode 层（聚合统计）
├── drift_events.csv           # Episode 层（漂移事件）
└── evaluation/                # 评测层（子目录）
    ├── main_experiment_results.csv
    ├── ablation_study.csv
    ├── human_eval_results.csv
    └── correlation_analysis.csv
```

---

## 使用示例

### 导出数据集

```bash
# 导出当前数据库快照
python scripts/export_dataset_snapshot.py

# 指定数据库路径
python scripts/export_dataset_snapshot.py \
  --db-path /path/to/scitaste.db \
  --roles-path /path/to/roles.json \
  --output-root /path/to/exports
```

### 加载数据进行分析（Python）

```python
import pandas as pd
import json

# 加载论文池
papers = pd.read_csv("paper_pool.csv")

# 加载用户画像
profiles = []
with open("profiles.jsonl") as f:
    for line in f:
        profiles.append(json.loads(line))

# 加载 episode 统计
episodes = pd.read_csv("episodes.csv")

# 加载行为日志
behaviors = pd.read_csv("behavior_logs.csv")
```

### 计算推荐准确率

```python
# 按 episode 聚合选择率
episode_metrics = episodes.groupby('episode_type').agg({
    'selected_papers': 'sum',
    'candidate_papers': 'sum',
}).assign(selection_rate=lambda x: x['selected_papers'] / x['candidate_papers'])

print(episode_metrics)
```

---

## 统计指标说明

### Episode 层统计

| 指标 | 计算方式 | 说明 |
|------|----------|------|
| Episode 总数 | COUNT(DISTINCT episode_id) | 推送轮次总数 |
| 平均每轮候选论文数 | AVG(candidate_papers) | 每次推送的平均候选数 |
| 平均每轮选中文献数 | AVG(selected_papers) | 每次推送的平均选择数 |
| 选择率 | selected_papers / candidate_papers | 用户选择比例 |
| Must-read 命中率 | selected_must_read / candidate_must_read | 必读规则命中情况 |
| 精读生成数 | SUM(reports_created) | 生成的精读报告总数 |

### 交互行为统计

| 指标 | 计算方式 | 说明 |
|------|----------|------|
| selected 总数 | COUNT(action='selected') | 总选择次数 |
| skipped 总数 | COUNT(action='skipped') | 总跳过次数 |
| 显式修正数 | COUNT(action_type='preference_update') | 显式偏好修正 |
| Must-read 更新数 | COUNT(action_type='must_read_update') | 必读规则更新 |
| Report feedback 数 | COUNT(action='report_feedback') | 报告质量反馈 |
| Doc open 数 | COUNT(action='opened_report') | 文档打开次数 |
| Dwell proxy 数 | COUNT(action='doc_dwell_proxy') | 阅读停留代理 |
