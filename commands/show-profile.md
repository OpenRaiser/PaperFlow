# /show-profile

## 命令描述

查看当前用户画像，包括研究方向、权重、必读清单、方法论偏好等。

## 使用方法

```
/show-profile
```

### 可选参数

| 参数 | 说明 | 示例 |
|------|------|------|
| `--version` | 查看历史版本 | `/show-profile --version 0.3` |
| `--full` | 显示完整详情 | `/show-profile --full` |

## 处理流程

```
1. 读取用户画像
   │
   └─→ storage-helper 读取 profile
   │
2. 格式化输出
   │
   ├─→ 核心方向及权重
   ├─→ 方法论偏好
   ├─→ 必读清单
   └─→ 最近更新时间
   │
3. 发送卡片
   │
   └─→ feishu-reporter 发送飞书卡片
```

## 输出示例

```
📊 你的学术画像 | v0.5 | 更新于 2026-04-08

━━━ 核心方向 ━━━
Data-native Scientific Discovery  ████████████████████  0.95
FineBio/bio-molecular             ██████████████████░░  0.90
S4S/science of science            ████████████████░░░░  0.85
AutoRes                           ████████████████░░░░  0.80
GUI agent                         ██████████████░░░░░░  0.70
Optimizer                         ████████████░░░░░░░░  0.60

━━━ 方法论偏好 ━━━
├── 偏好数据驱动 > 纯理论 ✓
├── 偏好系统性工作 > 单点改进 ✓
├── 偏好有开源代码的工作 ✓
└── 偏好有生物/科学应用场景的工作 ✓

━━━ 必读清单 ━━━
作者：
  🔒 Mohammed AlQuraishi (Columbia)
  🔒 Jian Tang (Mila)
  🔒 James Evans (UChicago)

机构：
  🔒 Shanghai AI Laboratory

关键词：
  🔒 phase transition
  🔒 data-native

━━━━━━━━━━━━
你可以随时修改：
  "加个必读作者：Bonnie Berger"
  "降低 GUI Agent 权重到 0.5"
```

## 相关 Agent

- [`must-read-manager`](../agents/must-read-manager.md) - 画像管理

## 相关 Skills

- [`storage-helper`](../skills/storage-helper/SKILL.md) - 数据读取
- [`feishu-reporter`](../skills/feishu-reporter/SKILL.md) - 飞书消息
