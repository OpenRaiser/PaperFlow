# /cold-start

## 命令描述

触发冷启动流程，解析用户输入（自然语言/PDF/Google Scholar 链接），生成初始学术画像。

## 使用方法

```
/cold-start [输入内容]
```

### 输入类型

| 类型 | 示例 |
|------|------|
| 自然语言描述 | `/cold-start 我关注 data-native scientific discovery，具体做生物分子数据基础设施` |
| PDF 文件 | 上传 PDF 文件后执行命令 |
| Google Scholar 链接 | `/cold-start https://scholar.google.com/citations?user=xxx` |
| 组合输入 | 自然语言 + PDF + 链接组合 |

## 处理流程

```
1. 接收用户输入
   │
2. 解析输入内容
   │
   ├─→ 自然语言 → 解析为结构化标签
   ├─→ PDF → pdf-parser 解析
   └─→ Google Scholar → 抓取发表记录
   │
3. 生成初始画像
   │
   ├─→ core_directions（方向权重）
   ├─→ methodology_preferences（方法论偏好）
   └─→ must_read（必读清单，初始为空）
   │
4. 存储画像
   │
   └─→ storage-helper 写入数据库
   │
5. 发送确认卡片
   │
   └─→ 飞书发送画像确认
```

## 输出示例

```
📋 你的学术画像（v0.1 - 冷启动）

━━━ 核心方向 ━━━
Data-native Scientific Discovery [权重：0.90]
Bio-molecular Data Infrastructure [权重：0.75]
GUI Agent [权重：0.60]

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

## 相关 Agent

- [`coldstart-agent`](../agents/coldstart-agent.md) - 冷启动画像生成

## 相关 Skills

- [`pdf-parser`](../skills/pdf-parser/SKILL.md) - PDF 解析
- [`storage-helper`](../skills/storage-helper/SKILL.md) - 数据存储
- [`feishu-reporter`](../skills/feishu-reporter/SKILL.md) - 飞书消息
