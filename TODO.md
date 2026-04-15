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

### 最近已完成
- 精读报告完整流程已打通：用户选中文献后自动生成飞书文档并回发链接
- 精读报告在 PDF 抓取失败或 LLM 超时时，仍按完整模板生成，不再退化成残缺内容
- 精读报告资源区固定输出原文 / PDF / arXiv / DOI 等可用链接
- OpenReview / CVF / ECVA 论文已接入和 arXiv 一致的全文级精读优先策略
- 期刊与会议源已支持 source page 正文 fallback，可在无 PDF 时继续生成完整精读模板
- DOI / ACM / DBLP TOC 论文已接入 OpenAlex / Crossref 元数据兜底，避免摘要和作者为空
- 飞书群 PDF 直传解析已接入 webhook 主流程，并增加重复任务拦截与已生成报告复用
- 定时调度器已接入 webhook 服务，支持每日推送 / 周报自动触发，也可通过环境变量关闭
- journal-fetcher 已压低可恢复网络重试日志，控制台输出更干净
- 飞书文档创建改为通过临时 Markdown 文件导入，修复长文档在 Windows / lark-cli 下被截断的问题
- `.env.example` 已对齐当前实际部署所用环境变量，移除多余的 DashScope 示例配置
- 反馈主链路已接入漂移感知兴趣迁移，老 `profile_json` 会自动补齐 `drift_state`
- `interest_vector` 已改为显式先验 + 长期窗口 + 短期窗口融合更新，并在反馈后写入 `profile_updated / drift_update` 行为日志
- 周报已新增“兴趣迁移状态”区块，展示状态、分数、主题与解释
- `must_read` 已从硬置顶改为软规则 bonus，推送日志额外保存 `keywords/topics` 供漂移窗口复用
- 日推卡片与精读结果列表里的论文标题已改为完整显示，不再按固定长度截断

---

## ⏳ V0.2.0 计划
### 高优先级 P0
1. **Google Scholar 冷启动解析**
   - `coldstart-agent` 已预留 `--scholar-url`
   - 但当前仅占位，尚未抓取学者主页、论文记录与研究方向信号

2. **扫描版 PDF OCR 增强**
   - 当前 PDF 精读更适合文本层可提取的论文
   - 扫描版 PDF 仍缺少 OCR 补链，容易出现摘要缺失、证据定位不足

3. **ACM / 付费 publisher 全文增强**
   - 当前已有 DOI / OpenAlex / Crossref 元数据兜底
   - 但仍需继续补“可稳定拿到正文或作者稿”的全文级 fallback，减少摘要级精读占比

### 中优先级 P1
1. **Webhook 服务器常驻部署**
   - 配置开机自启
   - 日志轮转
   - 错误告警

2. **调度器运维增强**
   - 调度失败后的重试 / 补偿机制
   - 更明确的告警与运行态可观测性

3. **交互事件增强**
   - 飞书表情反馈写回行为日志
   - 飞书菜单按钮点击后路由到对应 Agent

4. **周报增强**
   - 基于外部引用 / 影响力信号识别“遗漏但重要”的论文
   - 补齐更强的推荐准确率与趋势解释

5. **精读报告正文的 embedding 驱动增强**
   - 当前兴趣迁移 V1 已作用于推荐排序和周报解释
   - 但精读正文生成还没有把用户兴趣 embedding 检索链路作为主驱动

### 低优先级 P2
1. **ngrok 隧道持久化** - 配置固定域名

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
- 飞书接收：✅ webhook-server / ngrok 模式可用
- 精读模板：✅ 完整模板、链接区、降级提示均已接入
