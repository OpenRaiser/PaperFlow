# /weekly-report

## 命令描述

手动生成周报，统计周期内用户阅读行为与画像变化，生成周度总结报告并推送。

## 使用方法

```
/weekly-report [可选参数]
```

### 可选参数

| 参数 | 说明 | 示例 |
|------|------|------|
| `--days` | 指定天数 | `/weekly-report --days 7` |
| `--start-date` | 指定开始日期 | `/weekly-report --start-date 2026-04-01` |
| `--end-date` | 指定结束日期 | `/weekly-report --end-date 2026-04-07` |

默认生成过去 7 天的周报。

## 处理流程

```
1. 收集数据
   │
   ├─→ storage-helper 读取当前画像
   ├─→ storage-helper 读取 7 天前画像
   ├─→ storage-helper 读取本周行为日志
   └─→ storage-helper 读取本周推送记录
   │
2. 计算变化
   │
   ├─→ 方向权重对比
   ├─→ 识别新增/下降方向
   └─→ 计算推荐准确率
   │
3. 检测遗漏
   │
   ├─→ 查询跳过论文的引用情况
   └─→ 筛选值得关注的遗漏论文
   │
4. 生成建议
   │
   ├─→ 连续下降方向 → 询问是否保留
   ├─→ 连续跳过作者 → 建议移出必读
   └─→ 新增方向 → 建议正式加入
   │
5. 生成周报文档
   │
   └─→ 按照模板格式化报告
   │
6. 发送推送
   │
   └─→ feishu-reporter 发送飞书卡片
```

## 输出示例

```
📊 你的学术画像周度报告 | 2026 年 4 月 7 日

━━━ 方向权重变化 ━━━
data-native discovery  ████████████████████  0.95 (→0.97 ↑)
FineBio/bio-molecular  ██████████████████░░  0.90 (→0.92 ↑)
S4S/science of science ████████████████░░░░  0.85 (不变)
AutoRes                ████████████████░░░░  0.80 (→0.83 ↑)
GUI agent              ██████████████░░░░░░  0.70 (→0.62 ↓) ← 本月选择率下降
Optimizer              ████████████░░░░░░░░  0.60 (不变)

【新增】RL for science  ████████░░░░░░░░░░░░  0.40 ← 本月新出现的兴趣

━━━ 本月阅读统计 ━━━
推送论文总数：1,247
你选择精读：89（选择率 7.1%）
按来源：arXiv 62 | 顶会 18 | 顶刊 9
按方向：FineBio 31 | S4S 15 | AutoRes 22 | GUI 8 | 其他 13

━━━ 推荐准确率 ━━━
🔴高度相关中你选择了：72%（上月 65%，在变好）
🟡可能感兴趣中你选择了：18%
🔵边缘相关中你选择了：3%
→ 分类准确率在提升，🟡中有些该升为🔴

━━━ 你可能遗漏的 ━━━
以下论文你跳过了，但后来被高引或被你必读清单作者引用：
[论文 X] 你 4/3 跳过，目前已被引 12 次，AlQuraishi 在 Twitter 讨论
→ 要补读吗？

━━━ 画像调整建议 ━━━
• GUI agent 权重持续下降，是否还保留？
• 建议将"RL for science"正式加入关注方向
• 建议将"Bonnie Berger"从必读清单移到普通关注（你连续跳过她 3 篇）

请确认/修改。
```

## 定时任务

周报默认每周一上午 10 点自动推送，无需手动触发。

使用 `/weekly-report` 可手动生成周报（例如补发或测试）。

## 相关 Agent

- [`profile-report-agent`](../agents/profile-report-agent.md) - 画像周报

## 相关 Skills

- [`storage-helper`](../skills/storage-helper/SKILL.md) - 数据读取
- [`profile-updater`](../skills/profile-updater/SKILL.md) - 计算变化
- [`feishu-reporter`](../skills/feishu-reporter/SKILL.md) - 飞书消息
