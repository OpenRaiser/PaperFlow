# /add-must-read

## 命令描述

快速添加必读项（作者/机构/关键词）到用户画像的必读清单。

## 使用方法

### 方式一：Slash 命令

```
/add-must-read [类型] [内容]
```

| 类型 | 说明 | 示例 |
|------|------|------|
| `author` | 添加作者 | `/add-must-read author Mohammed AlQuraishi` |
| `institution` | 添加机构 | `/add-must-read institution Shanghai AI Lab` |
| `keyword` | 添加关键词 | `/add-must-read keyword phase transition` |

### 方式二：自然语言消息（推荐）

直接发送自然语言消息，无需使用 slash 命令：

```
加个必读作者：Mohammed AlQuraishi
加几个必读作者：AlQuraishi, Bonnie Berger, Jian Tang
再加个机构：Shanghai AI Lab 的所有论文我都要看标题
加个关键词：phase transition
```

## 处理流程

```
1. 接收输入
   │
   └─→ 解析消息内容（意图 + 实体）
   │
2. 识别操作类型
   │
   └─→ add → 添加到必读清单
   │
3. 读取当前画像
   │
   └─→ storage-helper 读取 profile
   │
4. 执行添加
   │
   ├─→ 检查是否已存在
   ├─→ 添加到 must_read 字段
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

### 添加作者

```
已添加。当前必读作者清单：
🔒 Mohammed AlQuraishi (Columbia) — bio structure
🔒 Bonnie Berger (MIT) — computational biology
🔒 Jian Tang (Mila) — molecular ML
🔒 James Evans (UChicago) — science of science

这些作者的新论文会无条件出现在每日清单最顶部。
```

### 添加机构

```
已添加。上海 AI Lab 的论文会全部保留在清单中（标记为 🏢 机构关注）。
```

### 添加关键词

```
已添加。当前必读关键词清单：
🔒 phase transition
🔒 data-native
🔒 emergence

包含这些关键词的论文会获得额外权重加成。
```

### 错误处理

**已存在：**
```
Mohammed AlQuraishi 已在必读作者清单中。
```

**格式错误：**
```
未识别添加类型。请使用以下格式：
  "加个必读作者：xxx"
  "加个机构：xxx"
  "加个关键词：xxx"
```

## 相关 Agent

- [`must-read-manager`](../agents/must-read-manager.md) - 必读清单管理

## 相关 Skills

- [`storage-helper`](../skills/storage-helper/SKILL.md) - 数据读写
- [`feishu-reporter`](../skills/feishu-reporter/SKILL.md) - 飞书消息
