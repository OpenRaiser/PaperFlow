# SciTaste 整体验证流程

> 用于验证系统所有核心功能是否正常工作

---

## 📋 验证前检查清单

### 1. 环境变量检查

```bash
# 检查 .env 文件配置
cat .env

# 必须配置的环境变量：
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx
FEISHU_VERIFICATION_TOKEN=xxx
OPENAI_API_KEY=sk-xxx  # 可选，仅 LLM 兜底需要
```

### 2. 数据库检查

```bash
python -c "from skills.storage-helper.scripts.db_ops import get_profile; print(get_profile('user_rolea'))"
```

**预期结果**：返回 user_rolea 的用户画像 JSON

### 3. 角色配置检查

```bash
cat data/roles.json
```

**预期结果**：包含 rolea, roleb, rolec, roled 四个角色及其 feishu_chat_id

---

## 🚀 验证流程

### Step 1: 启动 Webhook 服务器

```bash
# 方式 1：前台运行（方便看日志）
cd c:\Users\48290\Desktop\scitaste
python services/webhook-server/scripts/webhook_server.py

# 方式 2：后台运行
nohup python services/webhook-server/scripts/webhook_server.py > webhook.log 2>&1 &

# 验证服务器启动
curl http://localhost:8080/health
```

**预期结果**：
- 服务器启动，监听 8080 端口
- 日志显示 "Webhook server started on port 8080"

---

### Step 2: 验证冷启动功能

#### 2.1 自然语言冷启动

**在飞书角色群聊中发送：**
```
我关注 data-native scientific discovery，做生物分子数据基础设施
```

**预期结果**：
```
📋 你的学术画像（v0.1 - 冷启动）

━━━ 核心方向 ━━━
data-native Scientific Discovery [████████████████████] 0.80
Bio-molecular Data Infrastructure [██████████████████░░] 0.75

━━━ 必读清单 ━━━
作者：（空，待你添加）
机构：（空，待你添加）
关键词：（空，待你添加）
```

#### 2.2 PDF 冷启动（可选）

**在飞书中发送 PDF 文件**

**预期结果**：
- 系统下载 PDF 并解析
- 返回基于 PDF 内容的学术画像

---

### Step 3: 验证每日推送功能

```bash
# 命令行测试
python agents/daily-push-agent/main.py --user-id user_rolea --send-feishu
```

**预期结果**（飞书收到）：
```
📰 今日论文 | 04-12 | 抓取 312 篇 → 筛后 47 篇

━━━ 🔒 必读清单命中（5 篇）━━━
01 Author — Paper Title 1
02 Author — Paper Title 2
...

━━━ 🔴 高度相关（9 篇）━━━
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
```

---

### Step 4: 验证反馈处理功能

#### 4.1 命令行模拟反馈

```bash
python agents/feedback-agent/main.py --user-id user_rolea --push-id test_001 --reply "1 2 4 6"
```

#### 4.2 飞书自然反馈

**在飞书推送下方回复：**
```
1 2 4 6 9
```

**预期结果**：
```
收到，5 篇进入精读队列。

📊 今日反馈已记录：
  选择：01, 02, 04, 06, 09（5 篇）
  跳过：其余论文
  
  学到的信号：
  ✓ 你选了 🔴 高度相关的论文
  → 继续优化推荐算法
```

---

### Step 5: 验证精读报告功能

```bash
# 命令行测试
python agents/reading-agent/main.py --user-id user_rolea --paper-ids "1,2,3"
```

**预期结果**：
- 为每篇论文创建飞书文档
- 返回文档链接列表

---

### Step 6: 验证周报功能

#### 6.1 命令行触发周报

```bash
# 单个角色
python agents/profile-report-agent/main.py --role rolea --send-feishu

# 所有角色
python agents/profile-report-agent/main.py --all-roles --send-feishu
```

#### 6.2 飞书自然语言触发

**在角色群聊中发送：**
```
周报
```
或
```
weekly report
```

**预期结果**（飞书收到）：
```
📊 你的学术画像周度报告 | 2026-04-05 ~ 2026-04-12

━━━ 方向权重变化 ━━━
data-native  [████████████████████]  0.95 (→0.97 ↑)
bio-molecular [██████████████████░░] 0.90 (→0.92 ↑)

━━━ 本周阅读统计 ━━━
推送论文总数：312
你选择精读：18（选择率 5.8%）

━━━ 推荐准确率 ━━━
🔴高度相关中你选择了：25%
🟡可能感兴趣中你选择了：0%
🔵边缘相关中你选择了：0%

━━━ 画像调整建议 ━━━
• 画像状态良好，继续保持！

━━━━━━━━━━━━
新的一周，继续探索！
```

**验证要点**：
- [ ] 周报发送到对应角色的群聊，不是谭松个人对话框
- [ ] 各角色的周报内容独立（选择率、方向权重不同）

---

### Step 7: 验证角色管理功能

#### 7.1 查看角色列表

**飞书发送：**
```
查看角色列表
```

**预期结果**：
```
Role List
✓ rolea - direction: data-native scientific discovery...
  roleb - 研究方向：multimodal reasoning...
  rolec - 研究方向：deep learning, NLP
  roled - 研究方向：reinforcement learning...

当前角色：rolea
```

#### 7.2 切换角色

**飞书发送：**
```
切换到 roleb
```

**预期结果**：
```
已从 rolea 切换到 roleb
当前研究方向：multimodal reasoning, vision language
```

#### 7.3 验证隔离性

**在 roleb 群聊中发送：**
```
周报
```

**预期结果**：
- 收到 roleb 的周报（不是 rolea 的）
- 内容反映 roleb 的阅读历史和方向

---

## 📊 验证结果记录表

| 功能模块 | 测试项 | 预期结果 | 实际结果 | 状态 |
|----------|--------|----------|----------|------|
| Webhook 服务器 | 启动 | 监听 8080 端口 | | ⬜ |
| 冷启动 | 自然语言 | 返回画像卡片 | | ⬜ |
| 冷启动 | PDF 文件 | 解析 PDF 生成画像 | | ⬜ |
| 每日推送 | 命令行触发 | 收到🔴🟡🔵分类推送 | | ⬜ |
| 反馈处理 | 回复编号 | 记录反馈并确认 | | ⬜ |
| 精读报告 | 命令行触发 | 创建飞书文档 | | ⬜ |
| 周报 | 命令行触发 | 收到周报卡片 | | ⬜ |
| 周报 | 飞书触发 | 发送到角色群聊 | | ⬜ |
| 角色管理 | 查看列表 | 显示 4 个角色 | | ⬜ |
| 角色管理 | 切换角色 | 成功切换 | | ⬜ |
| 角色隔离 | 各角色独立 | 数据不混 | | ⬜ |

---

## 🐛 常见问题排查

### 问题 1: Webhook 服务器无法启动

```bash
# 检查端口占用
netstat -ano | findstr :8080

# 杀掉占用进程
taskkill /PID <pid> /F

# 重启服务器
python services/webhook-server/scripts/webhook_server.py
```

### 问题 2: 飞书 API 报错 "open_id cross app"

**原因**：使用了错误的身份发送

**解决**：确保使用 `send_text_to_chat()` 发送到群聊，而非 `send_text()` 给个人

### 问题 3: 周报发送到个人对话框而非群聊

**检查**：
```bash
# 查看 master-coordinator 的 handle_weekly_report
# 确保使用 feishu_chat_id 而非 feishu_user_id
```

### 问题 4: 角色数据混淆

**检查**：
```bash
# 查看每个角色的 user_id 是否正确
cat data/roles.json

# 查看数据库中各 profile 是否独立
python -c "from skills.storage-helper.scripts.db_ops import get_profile; print('rolea:', get_profile('user_rolea')); print('roleb:', get_profile('user_roleb'))"
```

---

## ✅ 验证通过标准

全部功能验证完成后，系统应满足：

1. **Webhook 服务器**：稳定运行，端口 8080 可接收飞书事件
2. **冷启动**：自然语言/PDF 输入均能生成画像
3. **每日推送**：能抓取、筛选、分类、发送论文
4. **反馈处理**：能解析编号选择，记录行为日志
5. **精读报告**：能创建飞书文档
6. **周报**：按角色发送，内容独立，发送到对应群聊
7. **角色管理**：多角色隔离，数据不混

---

## 📝 验证报告模板

```markdown
# 验证报告

**日期**：2026-04-12
**验证人**：___
**版本**：V0.1.0

## 通过的功能

1. ...
2. ...

## 待修复的问题

1. ...
2. ...

## 建议

1. ...
2. ...
```
