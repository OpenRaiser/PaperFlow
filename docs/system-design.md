# SciTaste System Design

## 核心架构：一个不断学习的系统

```
┌───────────────────────────────────┐
│               你的学术画像（持续进化）                         │ 
│                                                           │ 
│   研究方向向量（从冷启动 + 每日反馈持续更新）                       │ 
│   必读清单（作者 / 机构 / 关键词，你随时可编辑）                      │ 
│   偏好模型（从你的选择 / 不选择行为中学习）                        │ 
│   品味轮廓（你偏好什么类型的工作：理论？系统？数据？应用？）           │ 
│                                                           │ 
└─────────────────┬─────────────────┘
                  │  驱动筛选和排序 
                  ▼ 
            每日/每周推送
                  │ 
                  ▼ 
         你选择/不选择  →  反馈回流  →  画像更新
```

## 冷启动后生成的初始画像格式

```
📋  你的学术画像（v0.1 - 冷启动）
━━━  核心方向  ━━━
GUI Agent [████████████░░░░] 权重：0.70
优化器 / 训练方法  [██████████░░░░░░] 权重：0.60
━━━  方法论偏好（初始猜测，待学习）━━━
├──  偏好数据驱动  > 纯理论 
├──  偏好系统性工作  > 单点改进 
├──  偏好有开源代码的工作 
└──  偏好有生物 / 科学应用场景的工作 
━━━  必读清单  ━━━
作者：（空，待你添加）
机构：（空，待你添加）
关键词：（空，待你添加）
━━━━━━━━━━━━
请确认 / 修改。你可以随时发消息调整：
  "加个必读作者：Mohammed AlQuraishi"
  "降低 GUI Agent 权重"
  "我最近对 protein language model 更感兴趣了"
```

## 每日推送格式

```
📰  今日论文  | 04-21 | 抓取 312 篇  →  筛后 47 篇
━━━  🔒  必读清单命中（5 篇）━━━
01 AlQuraishi — Geometric Pretraining for Protein Complexes
02 Jian Tang — Scaling Molecular Generation with Flow Matching  
03 Shanghai AI Lab — GUI-World: A Large-Scale GUI Understanding Benchmark
04 DeepMind (Kohli 团队) — Scientific Data Curation at Scale
05 James Evans — Quantifying Paradigm Shifts in Science
━━━  🔴  高度相关（9 篇）━━━
06 MIT — Emergence in Biological Foundation Models
07 Stanford — Data-Native Pattern Discovery in Genomics
08 Berkeley — AutoML for Scientific Experiments
09 Google — Scaling Laws for Multimodal Scientific Data
10 CMU — Agent-Driven Literature Review Systems
11 THU — Protein-Ligand Binding Prediction with 10M Data
12 Anthropic — Constitutional AI for Research Agents
13 Meta FAIR — Universal Molecular Representation Learning
14 UIUC — Automated Hypothesis Generation from Data
━━━  🟡  可能感兴趣（18 篇）━━━
15 ETH — Efficient Attention for Long Biological Sequences
16 PKU — GUI Agent with Visual Grounding
17 UofT — Optimizer Design via Learned Loss Landscapes
18 KAIST — ...
...
━━━  🔵  边缘相关（15 篇）━━━
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

## 周度画像报告格式

```
📊  你的学术画像周度报告  | 2026 年 4 月 5 日
━━━  方向权重变化  ━━━
data-native discovery  ████████████████████  0.95 (→ 0.97 ↑ ) 
FineBio/bio-molecular  ██████████████████░░  0.90 (→ 0.92 ↑ ) 
S4S/science of science ████████████████░░░░  0.85 (不变) 
AutoRes                ████████████████░░░░  0.80 (→ 0.83 ↑ ) 
GUI agent              ██████████████░░░░░░  0.70 (→ 0.62 ↓ ) ←  本月选择率下降 
Optimizer              ████████████░░░░░░░░  0.60 (不变) 
【新增】RL for science  ████████░░░░░░░░░░░░  0.40 ←  本月新出现的兴趣 
━━━  本月阅读统计  ━━━
推送论文总数：1,247
你选择精读：89（选择率 7.1% ）
按来源：arXiv 62 | 顶会 18 | 顶刊 9
按方向：FineBio 31 | S4S 15 | AutoRes 22 | GUI 8 | 其他 13
━━━  推荐准确率  ━━━
🔴 高度相关中你选择了：72%（上月 65% ，在变好）
🟡 可能感兴趣中你选择了：18%
🔵 边缘相关中你选择了：3%
→  分类准确率在提升，🟡 中有些该升为 🔴
```

## 反馈效率的关键设计

**核心问题**：论文很多时怎么高效反馈？

**设计原则**：你唯一需要做的动作就是「从清单中选编号」
- 不需要打分、不需要写理由、不需要分类
- 选了 = 正信号
- 没选 = 弱负信号
- 这就够了

## 画像数据结构

```json
{
  "user_id": "user_rolea",
  "version": "0.1",
  "created_at": "ISO8601",
  "updated_at": "ISO8601",
  "core_directions": {
    "data-native": 0.95,
    "bio-molecular": 0.90,
    "gui-agent": 0.70
  },
  "methodology_preferences": {
    "preference_data_driven_over_theory": true,
    "preference_systematic_work_over_incremental": true,
    "preference_open_source_code": true,
    "preference_bio_science_application": true
  },
  "must_read": {
    "authors": ["Mohammed AlQuraishi"],
    "institutions": ["Shanghai AI Lab"],
    "keywords": ["data-native", "scientific discovery"]
  },
  "topic_weights": {
    "data-native": 0.95,
    "bio-molecular": 0.90
  },
  "author_heat": {},
  "institution_heat": {},
  "interest_vector": [],
  "taste_profile": {
    "preferred_work_type": ["empirical", "systematic", "open_source", "applied"],
    "dispreferred_work_type": []
  },
  "reading_history": [],
  "behavior_logs": []
}
```
