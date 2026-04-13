# SciTaste v0.1.0 发布说明

**发布日期**: 2026-04-11  
**版本**: v0.1.0 (MVP)

---

## 核心功能

### 1. 用户系统
- ✅ 多角色支持（rolea/roleb/rolec/roled）
- ✅ 角色与飞书 chat_id 绑定
- ✅ 独立用户画像存储

### 2. 冷启动
- ✅ 自然语言解析研究方向
- ✅ 方法论偏好识别
- ✅ 必读清单管理（作者/机构/关键词）
- ✅ 学术画像确认卡片

### 3. 每日推送
- ✅ 多源论文抓取（arXiv/OpenReview/期刊）
- ✅ 个性化排序（基于用户画像）
- ✅ 分类推送（必读🔒/高度相关🔴/可能感兴趣🟡/边缘相关🔵）
- ✅ 分数阈值过滤（避免低质量推送）
- ✅ 飞书推送卡片

### 4. 反馈处理
- ✅ 数字选择（"1 2 3"）
- ✅ 范围选择（"1-5 8 10"）
- ✅ 快捷命令（all red / all lock / none）
- ✅ 行为日志记录
- ✅ 画像自动更新

### 5. 精读报告
- ✅ 飞书文档创建
- ✅ 报告模板生成

### 6. 飞书集成
- ✅ Webhook 服务器（端口 8080）
- ✅ 消息路由（chat_id 回复到原对话框）
- ✅ Bot 回声过滤
- ✅ 消息去重

---

## 技术架构

### Agents
- `master-coordinator` - 主协调器
- `coldstart-agent` - 冷启动
- `daily-push-agent` - 每日推送
- `feedback-agent` - 反馈处理
- `reading-agent` - 精读报告
- `must-read-manager` - 必读管理
- `role-manager` - 角色管理

### Skills
- `arxiv-fetcher` - arXiv 抓取
- `openreview-fetcher` - OpenReview 抓取
- `journal-fetcher` - 期刊抓取
- `storage-helper` - 数据库操作
- `feishu-reporter` - 飞书交互
- `profile-updater` - 画像更新

### 数据库
- SQLite (`data/scitaste.db`)
- 表结构：papers, profiles, behavior_logs

---

## 已知限制

1. **论文源通用** - 所有角色抓取相同论文源，仅排序不同
2. **周度报告未实现** - 画像变化趋势统计（v0.2.0 计划）
3. **PDF 解析未实现** - 冷启动仅支持自然语言
4. **Google Scholar 未实现** - 学者主页解析

---

## 已修复问题

| 问题 | 状态 |
|------|------|
| 论文去重逻辑缺陷 | ✅ 修复 |
| all red/all lock 选择错误 | ✅ 修复 |
| get_latest_push 排序错误 | ✅ 修复 |
| category 字段未保存 | ✅ 修复 |
| Bot 回声消息重复处理 | ✅ 修复 |
| 反馈编号上限 50 | ✅ 修复 |
| 角色推送论文相同 | ✅ 修复（添加分数阈值） |

---

## 下一步计划 (v0.2.0)

- [ ] 周度画像报告
- [ ] 完整流程测试与文档
- [ ] 数据库清理脚本
- [ ] 精读报告完整流程
- [ ] 兴趣向量 EMA 更新
- [ ] 推荐准确率统计

---

## 运行方式

```bash
# 启动 webhook 服务器
python services/webhook-server/scripts/webhook_server.py

# 测试每日推送
python agents/daily-push-agent/main.py --user-id user_rolea --send-feishu

# 测试反馈处理
python agents/feedback-agent/main.py --user-id user_rolea --reply "all red" --push-id push_xxx
```

---

## 环境变量

```bash
FEISHU_APP_ID=...
FEISHU_APP_SECRET=...
FEISHU_VERIFICATION_TOKEN=...
DATABASE_URL=sqlite://data/scitaste.db
```

---

**完整文档**: [`docs/current_status.md`](docs/current_status.md)
