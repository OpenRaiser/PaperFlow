# SciTaste 数据集四层架构整理完成总结

## 完成时间
2026-04-19

## 完成内容

### 1. 数据集 Schema 文档
📄 `docs/dataset-schema.md`

详细定义了四层数据集的结构：

```
论文池层 (Paper Pool Layer)
├── 统一多来源学术元数据
├── arXiv, OpenReview, 期刊网页，DOI 页面
└── 输出：paper_pool.csv

用户画像层 (User Profile Layer)
├── 核心研究方向
├── 主题权重 / 作者热度 / 机构热度
├── Must-read 规则
├── 兴趣向量 / 报告偏好
└── 输出：profiles.jsonl, profile_summary.csv, must_read_profiles.csv

Episode 轮次层 (Episode Layer) ⭐ 核心层
├── 完整"推送—反馈—画像更新"闭环
├── Episode 统计表
├── 交互行为统计表
└── 输出：episodes.csv, behavior_logs.csv, drift_events.csv

评测层 (Evaluation Layer)
├── 主实验结果表
├── 消融实验表
├── 人工评估结果表
└── 输出：evaluation/*.csv
```

### 2. 导出脚本增强
📄 `scripts/export_dataset_snapshot.py`

新增功能：
- ✅ 四层统计指标计算（`layer_statistics`）
- ✅ 评测层主实验结果表自动生成
- ✅ 消融实验模板生成
- ✅ 人工评估和相关性分析模板
- ✅ evaluation 子目录自动创建

### 3. 使用指南文档
📄 `docs/dataset-usage-guide.md`

包含：
- 快速开始示例
- 四层数据分析示例代码
- 常见分析场景（趋势分析/必读规则影响/精读参与度）
- 故障排查指南
- 最佳实践建议

---

## 导出结果示例

```
data/dataset_exports/scitaste_snapshot_20260419_131139/
├── manifest.json              # 1.3 KB - 包含四层统计
├── paper_pool.csv             # 260 KB - 186 篇论文
├── profiles.jsonl             # 227 KB - 8 个用户画像
├── profile_summary.csv        # 100 KB
├── must_read_profiles.csv     # 810 B
├── behavior_logs.csv          # 414 KB - 983 条行为日志
├── episodes.csv               # 7.7 KB - 23 个 episode
├── drift_events.csv           # 4.5 KB - 7 个漂移事件
└── evaluation/
    ├── main_experiment_results.csv  # 3.5 KB - 18 个实验结果
    ├── ablation_study.csv           # 785 B - 3 个消融模板
    ├── human_eval_results.csv       # 91 B - 人工评估模板
    └── correlation_analysis.csv     # 66 B - 相关性分析模板
```

### 当前数据统计

| 层级 | 指标 | 数值 |
|------|------|------|
| 论文池层 | 论文总数 | 186 |
|  | 有 arXiv ID | 93 (50%) |
|  | 有 DOI | 32 (17%) |
| 用户画像层 | 用户画像数 | 8 |
|  | 有漂移状态 | 7 (88%) |
|  | 平均核心方向数 | 2.88 |
| Episode 层 | Episode 总数 | 23 |
|  | 日均推送 Episode | 18 |
|  | 平均每轮候选论文 | 17.26 |
|  | 平均每轮选中 | 2.57 |
|  | 总体选择率 | 14.86% |
|  | 精读报告生成 | 23 |
| 交互层 | 总行为数 | 983 |
|  | 选中 | 59 |
|  | 跳过 | 490 |
|  | 创建报告 | 23 |
|  | 打开报告 | 5 |
|  | 漂移更新 | 7 |

---

## 四层数据关系

```
评测层 (Evaluation)
    ↑ 基于前三层生成实验结果
Episode 轮次层 (Episode) ⭐ 核心分析单位
    ↑ 记录完整交互闭环
用户画像层 (User Profile)
    ↑ 描述用户兴趣状态
论文池层 (Paper Pool)
```

### Episode 作为核心样本单位的优势

与传统推荐数据集只记录用户点击行为不同，**Episode 层**记录的是完整的"推送 - 反馈 - 画像更新"闭环：

1. **保留上下文**: 每个 Episode 包含推荐前画像、候选集、排序结果、用户反馈、画像更新
2. **支持兴趣迁移分析**: 通过 drift_status_sequence 追踪兴趣变化轨迹
3. **支持精读联动分析**: 记录 reports_created / reports_opened 等精读行为
4. **支持因果推断**: 区分推送导致的曝光和用户主动选择

---

## 评测层说明

### 主实验结果表 (`evaluation/main_experiment_results.csv`)

自动生成的推荐任务评估指标：

| 字段 | 说明 |
|------|------|
| `ndcg_at_5/10` | 归一化折损累计增益（占位符，待接入真实计算） |
| `hit_rate_at_5/10` | 命中率（占位符） |
| `selection_rate` | 实际选择率 |
| `must_read_hits` | 必读命中数 |
| `high_relevant_selected` | 🔴 高相关选中数 |
| `maybe_interested_selected` | 🟡 可能感兴趣选中数 |
| `edge_relevant_selected` | 🔵 边缘相关选中数 |

### 消融实验模板 (`evaluation/ablation_study.csv`)

预定义的消融实验：

| Ablation ID | 被消融组件 | 假设 |
|-------------|------------|------|
| `ablation_no_drift` | 兴趣漂移检测 | 移除后会降低兴趣演化用户的个性化质量 |
| `ablation_no_must_read` | 必读规则 | 移除后会降低核心兴趣的精确度 |
| `ablation_no_category_ranking` | 🔴🟡🔵 分类排序 | 移除后会降低用户满意度 |

### 人工评估模板 (`evaluation/human_eval_results.csv`)

用于后续人工标注：
- `relevance_score`: 相关性评分 (1-5)
- `diversity_score`: 多样性评分 (1-5)
- `novelty_score`: 新颖性评分 (1-5)
- `comments`: 评语

### 主客观相关性分析 (`evaluation/correlation_analysis.csv`)

用于分析客观指标（NDCG/HitRate）与人工评分的相关性。

---

## 后续工作建议

### 1. 指标计算完善
- [ ] 接入真实的 NDCG/HitRate 计算（当前为占位符）
- [ ] 计算 MRR（Mean Reciprocal Rank）
- [ ] 计算 Precision@K / Recall@K

### 2. 数据集扩展
- [ ] 定期导出（每周/每月）形成时间序列
- [ ] 添加更多用户角色
- [ ] 收集人工评估结果

### 3. 分析深度增强
- [ ] 兴趣迁移路径可视化
- [ ] 必读规则影响因果分析
- [ ] 精读报告质量与用户满意度相关性

---

## 使用方法

```bash
# 1. 导出数据集
python scripts/export_dataset_snapshot.py

# 2. 查看导出结果
ls data/dataset_exports/

# 3. 加载数据进行分析（Python）
import pandas as pd
from pathlib import Path

export_root = Path("data/dataset_exports")
latest_export = max(export_root.glob("scitaste_snapshot_*"), key=lambda x: x.name)

papers = pd.read_csv(latest_export / "paper_pool.csv")
episodes = pd.read_csv(latest_export / "episodes.csv")
behaviors = pd.read_csv(latest_export / "behavior_logs.csv")
```

详细使用示例请参考 `docs/dataset-usage-guide.md`。
