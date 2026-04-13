# /daily-push

## 命令描述

触发每日推送流程，抓取 arXiv/顶会/期刊新论文，基于用户画像进行个性化排序和分类，发送飞书推送卡片。

## 使用方法

```
/daily-push
```

### 可选参数

| 参数 | 说明 | 示例 |
|------|------|------|
| `--date` | 指定日期范围 | `/daily-push --date 2026-04-07,2026-04-08` |
| `--limit` | 限制论文数量 | `/daily-push --limit 100` |
| `--category` | 指定类别 | `/daily-push --category cs.AI,cs.LG` |

## 处理流程

```
1. 读取用户画像
   │
   └─→ storage-helper 读取 profile
   │
2. 抓取新论文
   │
   ├─→ arxiv-fetcher 抓取 arXiv
   ├─→ openreview-fetcher 抓取顶会（如有新公布）
   └─→ journal-fetcher 抓取期刊（如有新发布）
   │
3. 论文处理
   │
   ├─→ paper-processor 清洗摘要
   ├─→ paper-processor 生成 embedding
   └─→ storage-helper 缓存论文
   │
4. 排序分类
   │
   ├─→ profile-updater 计算 score
   ├─→ 分类：🔒必读 / 🔴高度相关 / 🟡可能感兴趣 / 🔵边缘相关
   └─→ 生成推送列表
   │
5. 发送推送
   │
   └─→ feishu-reporter 发送飞书卡片
```

## 输出示例

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
...

━━━ 🟡 可能感兴趣（18 篇）━━━
...

━━━ 🔵 边缘相关（15 篇）━━━
...

━━━━━━━━━━━━
选择方式（任选）：
  直接回复编号：1 2 4 6 7 9 11
  范围选择：1-5 6 9 11
  快捷命令：all lock（所有必读）
           all red（所有高度相关）
           none（今天都不看）
```

## 相关 Agent

- [`daily-push-agent`](../agents/daily-push-agent.md) - 每日推送

## 相关 Skills

- [`arxiv-fetcher`](../skills/arxiv-fetcher/SKILL.md) - arXiv 抓取
- [`openreview-fetcher`](../skills/openreview-fetcher/SKILL.md) - OpenReview 抓取
- [`journal-fetcher`](../skills/journal-fetcher/SKILL.md) - 期刊抓取
- [`paper-processor`](../skills/paper-processor/SKILL.md) - 论文处理
- [`profile-updater`](../skills/profile-updater/SKILL.md) - 排序计算
- [`storage-helper`](../skills/storage-helper/SKILL.md) - 数据存储
- [`feishu-reporter`](../skills/feishu-reporter/SKILL.md) - 飞书消息
