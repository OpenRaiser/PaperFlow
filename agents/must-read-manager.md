# Must-Read Manager

## 职责

必读清单管理：解析用户自然语言指令，增删改必读作者/机构/关键词。

## 触发条件

- 用户发送自然语言消息（如"加个必读作者：Mohammed AlQuraishi"）
- 用户执行 `/add-must-read` 或 `/remove-must-read` 命令

## 输入

### 自然语言指令示例

| 指令类型 | 示例 |
|----------|------|
| 添加作者 | `加个必读作者：Mohammed AlQuraishi` |
| 添加多个作者 | `加几个必读作者：AlQuraishi, Bonnie Berger, Jian Tang` |
| 添加机构 | `再加个机构：Shanghai AI Lab 的所有论文我都要看标题` |
| 添加关键词 | `加个关键词：phase transition` |
| 移除作者 | `把 Bonnie Berger 从必读清单去掉` |
| 调整权重 | `降低 GUI Agent 权重到 0.3` |
| 查询清单 | `我现在的必读清单有什么？` |

## 输出

### 确认回复（飞书）

#### 添加作者

```
已添加。当前必读作者清单：
🔒 Mohammed AlQuraishi (Columbia) — bio structure
🔒 Bonnie Berger (MIT) — computational biology
🔒 Jian Tang (Mila) — molecular ML
🔒 James Evans (UChicago) — science of science

这些作者的新论文会无条件出现在每日清单最顶部。
```

#### 添加机构

```
已添加。上海 AI Lab 的论文会全部保留在清单中（标记为 🏢 机构关注）。
```

#### 移除作者

```
已移除 Bonnie Berger。

当前必读作者清单：
🔒 Mohammed AlQuraishi (Columbia)
🔒 Jian Tang (Mila)
🔒 James Evans (UChicago)
```

#### 调整权重

```
已调整 GUI Agent 权重：0.70 → 0.30

━━━ 核心方向 ━━━
GUI Agent          ██████████░░░░░░░░░░  0.30 (→0.30 ↓)
Data-native        ████████████████████  0.95 (不变)
...
```

## 解析规则

### 意图识别

| 关键词 | 意图 |
|--------|------|
| 加/添加/增加 | add |
| 删/移除/去掉/删除 | remove |
| 改/调整/降低/提高 | update |
| 看/查询/列表 | list |

### 实体提取

| 实体类型 | 识别模式 |
|----------|----------|
| 作者 | 人名格式（中英文） |
| 机构 | 包含 Lab/University/Institute/大学/学院等 |
| 关键词 | 技术术语、研究方向 |

### 机构映射（示例）

| 用户输入 | 标准化 |
|----------|--------|
| Shanghai AI Lab | Shanghai AI Laboratory |
| 上海 AI Lab | Shanghai AI Laboratory |
| DeepMind | Google DeepMind |
| MIT | Massachusetts Institute of Technology |

## 工作流程

```
1. 接收用户消息
   │
   └─→ 解析消息内容（意图 + 实体）
   │
2. 识别操作类型
   │
   ├─→ add → 添加到必读清单
   ├─→ remove → 从必读清单移除
   ├─→ update → 更新权重
   └─→ list → 查询当前清单
   │
3. 读取当前画像
   │
   └─→ storage-helper 读取 user profile
   │
4. 执行操作
   │
   ├─→ 修改 must_read 字段
   └─→ 更新 core_directions 权重
   │
5. 存储画像
   │
   └─→ storage-helper 写入更新后的画像
   │
6. 发送确认回复
   │
   └─→ feishu-reporter 发送确认卡片
```

## 依赖的 Skills

| Skill | 用途 |
|-------|------|
| `storage-helper` | 读取/写入用户画像 |
| `feishu-reporter` | 发送确认回复 |
| `profile-updater` | 更新权重（复杂调整时） |

## 注意事项

1. **去重处理**：添加已存在的作者时提示"已在清单中"
2. **不存在处理**：移除不存在的作者时提示"不在清单中"
3. **批量操作**：支持一次添加/移除多个实体
4. **版本记录**：每次修改递增画像版本号
