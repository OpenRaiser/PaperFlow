# SciTaste 任务清单

## ✅ 已完成 (Core - 100%)

### Agents
| Agent | 状态 | 测试 |
|-------|------|------|
| coldstart-agent | ✅ | ✅ 通过 (支持 PDF 冷启动 + 混合解析) |
| daily-push-agent | ✅ | ✅ 通过 (多数据源集成) |
| feedback-agent | ✅ | ✅ 通过 |
| reading-agent | ✅ | ✅ 通过 (飞书文档创建) |
| must-read-manager | ✅ | ✅ 通过 |
| master-coordinator | ✅ | ✅ 通过 (论文列表传递修复) |
| role-manager | ✅ | ✅ 通过 |
| profile-report-agent | ✅ | ✅ 通过 (周报生成 + 飞书发送) |

### Skills
| Skill | 状态 | 测试 |
|-------|------|------|
| arxiv-fetcher | ✅ | ✅ 通过 |
| openreview-fetcher | ✅ | ✅ 通过 (真实 API 配置完成) |
| journal-fetcher | ✅ | ✅ 通过 |
| feishu-reporter | ✅ | ✅ 通过 |
| storage-helper | ✅ | ✅ 通过 |
| profile-updater | ✅ | ✅ 通过 |
| pdf-parser | ✅ | ✅ 通过 (接口测试) |
| embedding | ✅ | ✅ 通过 (OpenAI SDK 已安装) |

### Services
| Service | 状态 | 描述 |
|---------|------|------|
| webhook-server | ✅ | 飞书事件订阅服务器 |

---

## ⏳ V0.2.0 计划

### 高优先级 P0
1. **精读报告完整流程** - reading-agent 增强
   - 用户选择论文后自动生成文档
   - 飞书发送链接

2. **兴趣向量 EMA 更新** - profile-updater 增强
   - 基于反馈持续更新用户兴趣向量
   - 推荐准确率统计

### 中优先级 P1
1. **周报定时任务** - profile-report-agent
   - 每周一上午 10 点自动发送
   - 支持 --all-roles 批量发送
1. **Webhook 服务器常驻部署**
   - 配置开机自启
   - 日志轮转
   - 错误告警

2. **定时任务调度** - daily-push-agent
   - 每日 9 点自动推送
   - 失败重试机制

3. **OpenAI API Key 配置**
   - 启用 LLM 兜底解析新方向

### 低优先级 P2
1. **PDF 解析增强** - 扫描版 PDF 支持（OCR）
2. **ngrok 隧道持久化** - 配置固定域名

---

## 📋 V0.1.0 核心功能

### 每日推送
```bash
python agents/daily-push-agent/main.py --user-id user_rolea --send-feishu
```

### 反馈处理
```bash
python agents/feedback-agent/main.py --user-id user_rolea --push-id test_001 --reply "1 2 4 6"
```

### 精读报告
```bash
python agents/reading-agent/main.py --user-id user_rolea --paper-ids "1,2,3"
```

### 多角色测试
```bash
# 创建新角色
python agents/role-manager/main.py --command "创建角色 roleC, 研究方向：reinforcement learning"

# 切换角色
python agents/role-manager/main.py --command "切换到 roleB"
```

---

## 当前系统状态

- 角色数：4 (rolea, roleb, rolec, roled)
- 数据库：已初始化
- 飞书推送：✅ 可用
- 飞书接收：⏳ webhook-server 需要重启
