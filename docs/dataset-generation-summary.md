# SciTaste 4 层数据集生成完成总结

## 完成时间
2026-04-19

## 数据集概览

### 导出路径
```
data/dataset_exports/scitaste_snapshot_20260419_140602/
```

### 文件清单
| 文件 | 大小 | 说明 |
|------|------|------|
| `paper_pool.csv` | 256 KB | 论文池层 - 186 篇论文 |
| `profiles.jsonl` | 46 KB | 用户画像层 - 完整 JSON |
| `profile_summary.csv` | 23 KB | 用户画像层 - 摘要 |
| `must_read_profiles.csv` | 2 KB | 用户画像层 - 必读规则 |
| `behavior_logs.csv` | 8.5 MB | Episode 层 - 10472 条行为日志 |
| `episodes.csv` | 67 KB | Episode 层 - 265 个 Episode 统计 |
| `drift_events.csv` | 11 KB | Episode 层 - 19 个漂移事件 |
| `evaluation/main_experiment_results.csv` | 38 KB | 评测层 - 主实验结果 |
| `evaluation/ablation_study.csv` | 1 KB | 评测层 - 消融实验模板 |
| `evaluation/human_eval_results.csv` | <1 KB | 评测层 - 人工评估模板 |
| `evaluation/correlation_analysis.csv` | <1 KB | 评测层 - 相关性分析模板 |
| `manifest.json` | 2 KB | 数据清单和统计信息 |

---

## 四层数据统计

### 第一层：论文池层 (Paper Pool Layer)
| 指标 | 数值 |
|------|------|
| 总论文数 | 186 |
| 已推送论文 | 186 (100%) |
| 有 arXiv ID | 93 (50%) |
| 有 DOI | 33 (18%) |

### 第二层：用户画像层 (User Profile Layer)
| 指标 | 数值 |
|------|------|
| 总用户数 | 24 |
| 有漂移状态 | 24 (100%) |
| 平均核心方向数 | 2.12 |
| 平均主题权重数 | 2.12 |

### 第三层：Episode 轮次层 (Episode Layer) ⭐ 核心层
| 指标 | 数值 |
|------|------|
| **Episode 总数** | **265** |
| 每日推送 (daily_push) | 217 |
| 精读报告 (reading_report) | 24 |
| 必读更新 (must_read_update) | 24 |
| 平均每轮候选论文数 | 19.57 |
| 平均每轮选中论文数 | 3.54 |
| **总体选择率** | **18.07%** |
| 精读报告生成数 | 48 |
| 打开报告数 | 36 |
| 报告打开率 | 75% |
| 漂移更新事件 | 19 |

### 第四层：交互层 (Interaction Layer)
| 指标 | 数值 |
|------|------|
| **总行为数** | **10,472** |
| 选中 (selected) | 937 |
| 跳过 (skipped) | 4,247 |
| 创建报告 (created_report) | 48 |
| 打开报告 (opened_report) | 36 |
| 漂移更新 (drift_update) | 19 |

### 第五层：评测层 (Evaluation Layer)
| 指标 | 数值 |
|------|------|
| 主实验结果记录 | 217 条 (对应 daily_push episodes) |
| 消融实验模板 | 3 个 |
| 人工评估模板 | 空 (待标注) |
| 相关性分析模板 | 空 (待计算) |

---

## Episode 类型分布

```
daily_push:       217 (81.9%)
reading_report:    24 (9.1%)
must_read_update:  24 (9.1%)
```

---

## 用户覆盖

24 个用户全部覆盖，每个用户 12 个 Episode：
- user_role1 ~ user_role24
- 涵盖 24 个不同科学方向（AI+Bio, AI+Science, Robotics, VLM, NLP, 计算生物学，蛋白质结构，基因组学，神经科学，气候科学，材料科学，化学，物理学，医学影像，流行病学，农业，海洋学，心理学，经济学，教育学，天文学，能源研究，科学学）

---

## 数据质量指标

### 选择率分析
- 总体选择率：18.07%
- 符合预期范围 (15-25%)
- 每 Episode 平均选中 3.54 篇论文

### 精读参与度
- 精读报告生成：48 次
- 精读报告打开：36 次
- 报告打开率：75%

### 兴趣漂移
- 漂移更新事件：19 次
- 覆盖 19/265 = 7.2% 的 Episode
- 符合预期 drift 触发频率

---

## 使用方法

### 1. 加载数据集 (Python)
```python
import pandas as pd
import json
from pathlib import Path

export_root = Path("data/dataset_exports")
latest_export = max(export_root.glob("scitaste_snapshot_*"), key=lambda x: x.name)

# 加载四层数据
papers = pd.read_csv(latest_export / "paper_pool.csv")
profiles = pd.read_csv(latest_export / "profile_summary.csv")
episodes = pd.read_csv(latest_export / "episodes.csv")
behaviors = pd.read_csv(latest_export / "behavior_logs.csv")
eval_results = pd.read_csv(latest_export / "evaluation/main_experiment_results.csv")

# 加载 manifest
with open(latest_export / "manifest.json") as f:
    manifest = json.load(f)
```

### 2. 分析 Episode 统计
```python
# 按用户聚合 Episode 指标
user_metrics = episodes.groupby('user_id').agg({
    'selected_papers': 'sum',
    'candidate_papers': 'sum',
    'reports_created': 'sum',
    'drift_updates': 'sum',
}).assign(
    selection_rate=lambda x: x['selected_papers'] / x['candidate_papers']
)

print(user_metrics)
```

### 3. 分析行为模式
```python
# 按类别统计选择率
category_stats = behaviors[behaviors['action'].isin(['selected', 'skipped'])].groupby('category').agg(
    selected=('action', lambda x: (x == 'selected').sum()),
    total=('action', 'count')
).assign(
    selection_rate=lambda x: x['selected'] / x['total']
)

print(category_stats)
```

### 4. 分析兴趣漂移
```python
# 查看漂移事件
drift_events = pd.read_csv(latest_export / "drift_events.csv")
print(drift_events[['user_id', 'drift_status', 'drift_score', 'drift_explanation']].head())
```

---

## 脚本清单

| 脚本 | 用途 |
|------|------|
| `scripts/init_users_from_roles.py` | 从 roles.json 初始化 24 个用户到数据库 |
| `scripts/generate_mock_episodes.py` | 生成模拟 Episode 数据 (288 episodes, 10472 behaviors) |
| `scripts/export_dataset_snapshot.py` | 导出 4 层数据集快照 |

---

## 下一步建议

### 1. 数据验证
- [ ] 检查 Episode 分布是否合理
- [ ] 验证选择率是否符合预期
- [ ] 确认漂移事件触发逻辑

### 2. 分析实验
- [ ] 按用户聚类分析兴趣模式
- [ ] 分析必读规则命中率
- [ ] 精读报告参与度相关性分析

### 3. 评测层完善
- [ ] 计算真实 NDCG/HitRate 指标
- [ ] 填写消融实验结果
- [ ] 收集人工评估数据

### 4. 数据集扩展
- [ ] 定期导出形成时间序列
- [ ] 增加更多 Episode 轮次
- [ ] 扩展论文池到 500+ 篇

---

## 技术说明

### Episode 生成逻辑
- 每个用户 12 个 Episode
- Episode 类型：
  - `daily_push`: 每日推送 (默认)
  - `reading_report`: 每第 4 轮生成精读报告
  - `must_read_update`: 每第 12 轮触发必读更新
- 候选集大小：18 篇论文
- 选择概率按类别：
  - must_read: 85%
  - high_relevant: 60%
  - maybe_interested: 25%
  - edge_relevant: 10%

### 相关性计算
基于用户 profile 的 core_directions 和 must_read 规则，与论文标题进行关键词匹配：
- must_read 作者匹配 → must_read (0.95)
- must_read 关键词匹配 → must_read (0.90)
- 2+ 方向匹配 → high_relevant (0.80-0.95)
- 1 方向匹配 → maybe_interested (0.60-0.75)
- 无匹配 → edge_relevant (0.40-0.55)

### 漂移触发
- 每 6 轮 Episode 有 50% 概率触发
- 漂移状态：stable → shifting
- 漂移分数增加 0.15

---

**[OK] 4 层数据集生成完成！数据已导出到 `data/dataset_exports/scitaste_snapshot_20260419_140602/`**
