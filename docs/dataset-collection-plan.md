# SciTaste 四层数据集收集方案

## 截稿日期：5 月 8 日

---

## 时间规划

| 阶段 | 日期 | 天数 | 操作 |
|------|------|------|------|
| **数据收集期** | 4/19 - 5/1 | 14 天 | 每天自动收集 + 推送 |
| **数据冻结期** | 5/2 - 5/8 | 7 天 | 导出数据集 + 写论文 |

---

## 四层数据收集方式

### 第 1 层：论文池层 (Paper Pool Layer)

**收集内容**：真实学术论文元数据

**数据来源**：
- arXiv (cs.AI, cs.LG, cs.CL, cs.CV, q-bio)
- OpenReview (ICLR, NeurIPS, ICML, ACL, EMNLP)
- CVF (CVPR, ICCV)
- ECVA (ECCV)
- DBLP (ACM MM)

**收集频率**：每天增量收集

**执行命令**：
```bash
# 每天执行一次（建议上午 08:00）
python scripts/daily_paper_collection.py --days 1 --arxiv-limit 50
```

**预期规模**：
| 日期 | 新增 | 累计 |
|------|------|------|
| 4/19 (初始) | 186 | 186 |
| 4/20-5/1 (12 天) | ~30/天 | +360 |
| **总计** | | **~550 篇** |

---

### 第 2 层：用户画像层 (User Profile Layer)

**收集内容**：24 个用户的学术兴趣画像及演化

**用户分布**：
| 领域 | 用户数 | 方向示例 |
|------|--------|----------|
| AI+Bio | 4 | GUI Agent+Protein, Drug Discovery |
| AI+Science | 4 | Climate, Materials, Chemistry |
| NLP/CV | 4 | LLM, Vision-Language |
| Robotics | 3 | Manipulation, Navigation |
| Other Sciences | 9 | Neuroscience, Economics, Education, etc. |

**收集方式**：系统自动更新（无需手动操作）

- 初始画像：已从 `roles.json` 导入 24 个用户
- 每日更新：用户反馈后自动更新 `interest_vector` 和 `drift_state`
- 自动记录：每次更新写入 `profiles` 表

**预期规模**：
- 24 个用户 × 14 天 = **336 个画像快照**

---

### 第 3 层：Episode 层 (Interaction Layer)

**收集内容**：每日推送 - 反馈闭环的完整记录

**Episode 类型**：
| 类型 | 频率 | 说明 |
|------|------|------|
| daily_push | 每天 1 轮 | 每日论文推送 |
| reading_report | 用户触发 | 选中论文后生成精读报告 |
| must_read_update | 自动触发 | 必读规则更新 |
| drift_update | 自动触发 | 兴趣漂移检测 |

**收集方式**：系统自动记录（无需手动操作）

- 每天 09:00 自动推送 → 自动生成 Episode
- 用户选择/跳过 → 自动记录到 `behavior_logs`
- 画像更新 → 自动记录漂移事件

**预期规模**：
| 指标 | 计算 | 总计 |
|------|------|------|
| Episode 总数 | 24 用户 × 14 天 | **336** |
| 行为日志 | 336 Episode × ~45 条 | **~15,000** |
| 精读报告 | 336 × 0.3 | **~100** |
| 漂移事件 | 336 × 0.15 | **~50** |

---

### 第 4 层：评测层 (Evaluation Layer)

**收集内容**：推荐性能指标和实验结果

**收集方式**：截稿时一次性导出

**执行命令**：
```bash
# 5 月 1 日执行（数据冻结）
python scripts/export_final_dataset.py
```

**输出文件**：
| 文件 | 内容 | 用途 |
|------|------|------|
| `main_experiment_results.csv` | 主实验指标 | 论文 Table 2 |
| `ablation_study.csv` | 消融实验 | 论文 Table 3 |
| `human_eval_results.csv` | 人工评估（可选） | 论文 Table 4 |
| `correlation_analysis.csv` | 主客观相关性 | 补充材料 |

**预期指标**：
| 指标 | 说明 |
|------|------|
| NDCG@5/10 | 推荐排序质量 |
| HitRate@5/10 | 命中率 |
| SelectionRate | 用户选择率 |
| MustReadHits | 必读规则命中数 |
| ReportOpenRate | 精读报告打开率 |

---

## 自动化配置

### 方案 A：使用现有 scheduler（推荐）

系统已有每日推送调度器，会自动：
1. 每天 09:00 推送论文
2. 记录用户反馈
3. 更新画像

**只需每天手动执行一次论文收集**：
```bash
python scripts/daily_paper_collection.py --days 1 --arxiv-limit 50
```

### 方案 B：完全自动（可选）

创建 Windows 任务计划程序：

1. 打开"任务计划程序"
2. 创建任务：
   - 名称：`SciTaste Daily Collection`
   - 触发器：每天 08:00
   - 操作：`python.exe scripts/daily_paper_collection.py`
   - 起始目录：`D:\scitaste\scripts`

---

## 截稿前导出流程

### 5 月 1 日（数据冻结日）

```bash
# 1. 最后一次收集
python scripts/daily_paper_collection.py --days 1

# 2. 导出完整四层数据集
python scripts/export_final_dataset.py

# 3. 验证导出结果
ls data/dataset_exports/scitaste_final/
```

### 生成文件清单

```
data/dataset_exports/scitaste_final/
├── paper_pool.csv              # 第 1 层
├── profiles.jsonl              # 第 2 层
├── profile_summary.csv         # 第 2 层摘要
├── must_read_profiles.csv      # 第 2 层必读规则
├── episodes.csv                # 第 3 层
├── behavior_logs.csv           # 第 3 层
├── drift_events.csv            # 第 3 层漂移
├── evaluation/                 # 第 4 层
│   ├── main_experiment_results.csv
│   ├── ablation_study.csv
│   ├── human_eval_results.csv
│   └── correlation_analysis.csv
├── dataset_card.json           # 数据集说明
└── paper_statistics.csv        # 论文用统计表
```

---

## 论文章节写法

### 4. Dataset Construction

#### 4.1 Paper Pool (Layer 1)

> We collected papers continuously over 14 days (April 19 - May 1, 2026) from multiple academic sources:
> - arXiv preprints from categories cs.AI, cs.LG, cs.CL, cs.CV, and q-bio
> - OpenReview proceedings from ICLR, NeurIPS, ICML, ACL, and EMNLP
> - CVF open-access papers from CVPR and ICCV
> - ECVA papers from ECCV
>
> In total, we collected **550 papers** with full metadata including title, authors, abstract, venue, and publication date.

#### 4.2 User Profiles (Layer 2)

> We simulated **24 users** across diverse scientific domains, including AI+Bio, AI+Science, NLP, Computer Vision, Robotics, and other sciences.
>
> Each user profile contains:
> - Core research directions (2-4 topics)
> - Must-read rules (authors, institutions, keywords)
> - Interest vector for real-time personalization
> - Drift state for tracking evolving interests

#### 4.3 Interaction Episodes (Layer 3)

> Over 14 days, we recorded **336 interaction episodes** (24 users × 14 days), capturing the complete push-feedback-update cycle.
>
> Each episode includes:
> - 18 candidate papers with relevance categories
> - User selections and skips
> - Reading report generation (when triggered)
> - Interest drift updates (when detected)
>
> In total, we collected **15,000+ behavior logs** with fine-grained interaction signals.

#### 4.4 Evaluation Metrics (Layer 4)

> We computed standard recommendation metrics including NDCG@5/10, HitRate@5/10, selection rate, and must-read hit rate.
>
> Additionally, we tracked reading engagement metrics such as report generation rate and report open rate.

---

## 每日检查清单

### 每天需要做的事情（约 2 分钟）

- [ ] 早上 08:00 执行收集脚本
- [ ] 检查日志确认收集成功
- [ ] 查看飞书确认推送正常

### 每周检查

- [ ] 查看论文池增长是否正常（+200~300 篇/周）
- [ ] 查看 Episode 数量（+168/周 = 24 用户×7 天）
- [ ] 查看漂移事件是否触发

---

## 常见问题

### Q1: 如果某天忘记收集怎么办？

A: 第二天补跑即可：
```bash
python scripts/daily_paper_collection.py --days 2
```

### Q2: 用户反馈数据不够怎么办？

A: 可以用现有 24 用户的模拟数据，或者在论文中说明这是"simulated interaction dataset"。

### Q3: 论文池论文太少怎么办？

A: 增加 arXiv 限额：
```bash
python scripts/daily_paper_collection.py --days 1 --arxiv-limit 200
```

---

## 联系与支持

如有问题，查看日志：
```bash
# 查看收集日志
cat data/daily_collection.log

# 查看推送日志
cat data/webhook-server/*.log
```

---

**最后更新日期**：2026-04-19
**下次检查日期**：2026-04-20 08:00
