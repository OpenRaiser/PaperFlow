# ColdStart Agent

## 职责

冷启动：解析用户输入（自然语言/PDF/Google Scholar 链接），生成初始学术画像。

## 触发条件

- 用户执行 `/cold-start` 命令
- 新用户首次使用系统

## 输入

支持以下输入方式（任选组合）：

| 方式 | 描述 | 处理逻辑 |
|------|------|----------|
| Google Scholar 主页链接 | Agent 自动抓取发表记录 | 提取研究方向、方法、合作者网络、引用高频论文 |
| 几篇重要论文 PDF | Agent 精读这些论文 | 提取主题、方法论偏好、关注的问题类型，作为"品味锚点" |
| 自然语言描述 | 用户直接描述研究方向 | Agent 解析为结构化方向标签 |
| 以上都给 | 综合所有信号 | 交叉验证，生成最准确的初始画像 |

### 自然语言描述示例

```
我关注 data-native scientific discovery，
具体做生物分子数据基础设施和方法论图谱，
也关注 auto research 和 GUI agent
```

## 输出

### 初始画像 JSON

```json
{
  "user_id": "user_001",
  "version": "0.1",
  "created_at": "2026-04-08T10:00:00Z",
  "core_directions": {
    "GUI Agent": 0.70,
    "Optimizer/Training Methods": 0.60,
    "Data-native Scientific Discovery": 0.80,
    "Bio-molecular Data Infrastructure": 0.75
  },
  "methodology_preferences": {
    "preference_data_driven_over_theory": true,
    "preference_systematic_work_over_incremental": true,
    "preference_open_source_code": true,
    "preference_bio_science_application": true
  },
  "must_read": {
    "authors": [],
    "institutions": [],
    "keywords": []
  },
  "topic_weights": {
    "data-native": 0.80,
    "bio-molecular": 0.70,
    "gui-agent": 0.60,
    "optimizer": 0.50
  },
  "author_heat": {},
  "institution_heat": {},
  "interest_vector": [],
  "taste_profile": {
    "preferred_work_type": ["empirical", "systematic", "applied"],
    "dispreferred_work_type": ["pure_theory", "incremental"]
  }
}
```

### 飞书确认卡片

```
📋 你的学术画像（v0.1 - 冷启动）

━━━ 核心方向 ━━━
GUI Agent [权重：0.70]
Optimizer/训练方法 [权重：0.60]
Data-native Scientific Discovery [权重：0.80]
Bio-molecular Data Infrastructure [权重：0.75]

━━━ 方法论偏好（初始猜测，待学习）━━━
├── 偏好数据驱动 > 纯理论
├── 偏好系统性工作 > 单点改进
├── 偏好有开源代码的工作
└── 偏好有生物/科学应用场景的工作

━━━ 必读清单 ━━━
作者：（空，待你添加）
机构：（空，待你添加）
关键词：（空，待你添加）

━━━━━━━━━━━━
请确认/修改。你可以随时发消息调整：
  "加个必读作者：Mohammed AlQuraishi"
  "降低 GUI Agent 权重"
  "我最近对 protein language model 更感兴趣了"
```

## 工作流程

```
1. 接收用户输入
   │
   ├─→ 自然语言描述 → 解析为结构化标签
   ├─→ PDF 文件 → pdf-parser 解析 → 提取主题/方法
   └─→ Google Scholar 链接 → 抓取发表记录 → 提取方向
   │
2. 综合所有信号
   │
   ├─→ 交叉验证（多种输入的一致性）
   └─→ 生成初始方向向量
   │
3. 生成画像 JSON
   │
   ├─→ 填充 core_directions
   ├─→ 填充 methodology_preferences
   └─→ 初始化 must_read 清单
   │
4. 存储画像
   │
   └─→ storage-helper 写入 data/profiles/user_001.json
   │
5. 发送确认卡片
   │
   └─→ feishu-reporter 发送画像确认
```

## 依赖的 Skills

| Skill | 用途 |
|-------|------|
| `pdf-parser` | 解析用户上传的 PDF 文件 |
| `storage-helper` | 存储生成的画像 JSON |
| `feishu-reporter` | 发送确认卡片 |

## 注意事项

1. **画像版本**：初始版本为 `0.1`，后续每次更新递增
2. **权重范围**：所有方向权重在 [0, 1] 之间
3. **默认偏好**：如果用户未明确说明，基于输入内容推断默认方法论偏好
4. **用户确认**：生成画像后必须发送确认卡片，等待用户确认或修改
