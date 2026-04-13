# Daily Push Agent

## 职责

每日推送：拉取 arXiv/顶会/期刊新论文，基于用户画像进行筛选、排序、分类，生成飞书推送卡片。

## 触发条件

- 用户执行 `/daily-push` 命令
- 定时任务（每日上午 9 点）

## 输入

| 输入源 | 来源 | 内容 |
|--------|------|------|
| 用户画像 | `storage-helper` 读取 | 研究方向、必读清单、偏好模型 |
| 新论文元数据 | `arxiv-fetcher` / `openreview-fetcher` / `journal-fetcher` | 论文标题、作者、摘要、embedding |

## 输出

### 飞书推送卡片

```
📰 今日论文 | 04-21 | 抓取 312 篇 → 筛后 47 篇

━━━ 🔒 必读清单命中（5 篇）━━━
01 AlQuraishi — Geometric Pretraining for Protein Complexes
02 Jian Tang — Scaling Molecular Generation with Flow Matching  
03 Shanghai AI Lab — GUI-World: A Large-Scale GUI Understanding Benchmark
04 DeepMind (Kohli 团队) — Scientific Data Curation at Scale
05 James Evans — Quantifying Paradigm Shifts in Science

━━━ 🔴 高度相关（9 篇）━━━
06 MIT — Emergence in Biological Foundation Models
07 Stanford — Data-Native Pattern Discovery in Genomics
08 Berkeley — AutoML for Scientific Experiments
09 Google — Scaling Laws for Multimodal Scientific Data
10 CMU — Agent-Driven Literature Review Systems
11 THU — Protein-Ligand Binding Prediction with 10M Data
12 Anthropic — Constitutional AI for Research Agents
13 Meta FAIR — Universal Molecular Representation Learning
14 UIUC — Automated Hypothesis Generation from Data

━━━ 🟡 可能感兴趣（18 篇）━━━
15 ETH — Efficient Attention for Long Biological Sequences
16 PKU — GUI Agent with Visual Grounding
17 UofT — Optimizer Design via Learned Loss Landscapes
18 KAIST — ...
...

━━━ 🔵 边缘相关（15 篇）━━━
33 ...
...
47 ...

━━━━━━━━━━━━
选择方式（任选）：
  直接回复编号：1 2 4 6 7 9 11
  范围选择：1-5 6 9 11
  快捷命令：all lock（所有必读）
           all red（所有高度相关）
           none（今天都不看）
```

## 排序公式

```python
score = w1 * 兴趣向量相似度
      + w2 * 主题权重匹配
      + w3 * 作者/机构热度
      + w4 * 论文本身质量信号（引用预期/机构声誉/venue）
      + bonus（必读清单命中 → 置顶）
```

### 权重参数 (config/scoring_weights.yaml)

```yaml
w1_interest_vector: 0.35
w2_topic_weight: 0.25
w3_author_institution: 0.20
w4_quality_signal: 0.20
bonus_must_read: 1.0
```

## 分类阈值

| 分类 | 阈值 | 说明 |
|------|------|------|
| 🔒 必读清单命中 | - | 作者/机构/关键词命中必读清单 |
| 🔴 高度相关 | score >= 0.75 | 强相关，优先推荐 |
| 🟡 可能感兴趣 | 0.50 <= score < 0.75 | 中等相关 |
| 🔵 边缘相关 | score < 0.50 | 弱相关，但保留以防遗漏 |

## 工作流程

```
1. 获取用户画像
   │
   └─→ storage-helper 读取最新画像 JSON
   │
2. 抓取新论文
   │
   ├─→ arxiv-fetcher 获取 arXiv 新论文（按日期范围）
   ├─→ openreview-fetcher 获取顶会论文（如有新公布）
   └─→ journal-fetcher 获取期刊论文（如有新发布）
   │
3. 论文去重
   │
   ├─→ 基于 arxiv_id / doi / title 相似度
   └─→ 移除已推送过的论文
   │
4. 计算相关度
   │
   ├─→ paper-processor 生成论文 embedding
   ├─→ 计算与用户兴趣向量的余弦相似度
   ├─→ 匹配主题权重
   ├─→ 匹配作者/机构热度
   └─→ 综合计算 score
   │
5. 分类排序
   │
   ├─→ 必读清单命中 → 🔒（置顶）
   ├─→ score >= 0.75 → 🔴
   ├─→ 0.50 <= score < 0.75 → 🟡
   └─→ score < 0.50 → 🔵
   │
6. 生成推送卡片
   │
   └─→ feishu-reporter 发送飞书卡片
```

## 依赖的 Skills

| Skill | 用途 |
|-------|------|
| `arxiv-fetcher` | 抓取 arXiv 新论文 |
| `openreview-fetcher` | 抓取顶会论文 |
| `journal-fetcher` | 抓取期刊论文 |
| `paper-processor` | 论文处理、embedding 生成 |
| `storage-helper` | 读取用户画像、缓存论文 |
| `feishu-reporter` | 发送推送卡片 |

## 注意事项

1. **推送时间**：默认每日上午 9 点，可通过配置修改
2. **推送数量**：目标 30-50 篇，过多则提高阈值，过少则降低阈值
3. **必读清单优先**：必读清单命中的论文永远置顶，不受 score 影响
4. **去重逻辑**：已推送过的论文不再推送，除非用户明确要求
