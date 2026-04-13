# /remove-must-read

## 命令描述

从用户画像的必读清单中移除作者/机构/关键词。

## 使用方法

### 方式一：Slash 命令

```
/remove-must-read [类型] [内容]
```

| 类型 | 说明 | 示例 |
|------|------|------|
| `author` | 移除作者 | `/remove-must-read author Bonnie Berger` |
| `institution` | 移除机构 | `/remove-must-read institution Shanghai AI Lab` |
| `keyword` | 移除关键词 | `/remove-must-read keyword phase transition` |

### 方式二：自然语言消息（推荐）

直接发送自然语言消息，无需使用 slash 命令：

```
把 Bonnie Berger 从必读清单去掉
移除必读作者：Jian Tang
删除机构：Shanghai AI Lab
去掉关键词：phase transition
```

## 处理流程

```
1. 接收输入
   │
   └─→ 解析消息内容（意图 + 实体）
   │
2. 识别操作类型
   │
   └─→ remove → 从必读清单移除
   │
3. 读取当前画像
   │
   └─→ storage-helper 读取 profile
   │
4. 执行移除
   │
   ├─→ 检查是否存在
   ├─→ 从 must_read 字段移除
   └─→ 递增版本号
   │
5. 存储画像
   │
   └─→ storage-helper 写入更新后的画像
   │
6. 发送确认回复
   │
   └─→ feishu-reporter 发送确认卡片
```

## 输出示例

### 移除作者

```
已移除 Bonnie Berger。

当前必读作者清单：
🔒 Mohammed AlQuraishi (Columbia)
🔒 Jian Tang (Mila)
🔒 James Evans (UChicago)
```

### 移除机构

```
已移除 Shanghai AI Lab。

当前必读机构清单：
🔒 DeepMind
🔒 OpenAI
```

### 移除关键词

```
已移除关键词 "phase transition"。

当前必读关键词清单：
🔒 data-native
🔒 emergence
```

### 错误处理

**不存在：**
```
Bonnie Berger 不在必读作者清单中。
当前必读作者：Mohammed AlQuraishi, Jian Tang, James Evans
```

**格式错误：**
```
未识别移除类型。请使用以下格式：
  "把 xxx 从必读清单去掉"
  "移除必读作者：xxx"
  "删除机构：xxx"
```

## 相关 Agent

- [`must-read-manager`](../agents/must-read-manager.md) - 必读清单管理

## 相关 Skills

- [`storage-helper`](../skills/storage-helper/SKILL.md) - 数据读写
- [`feishu-reporter`](../skills/feishu-reporter/SKILL.md) - 飞书消息
