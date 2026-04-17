# SciTaste 任务清单
## 最近同步（2026-04-17）

- 已完成第二期整理：清理 `coldstart-agent` / `master-coordinator` 中的重复旧函数、死分支和历史意图解析块，只保留当前正式实现。
- README 与 TODO 已同步到“主页优先 + Scholar 结构化融合”的冷启动现状，不再把第一期能力写成未实现。
- 当前回归结果：`python -m py_compile` 已覆盖本轮主要修改模块；全量 `pytest -q` 为 `285 passed`。


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
- `must-read` 已恢复为硬优先：命中后固定保留并排到每日清单顶部；推送日志仍额外保存 `keywords/topics` 供漂移窗口复用
- 日推卡片与精读结果列表里的论文标题已改为完整显示，不再按固定长度截断
- `coldstart-agent --scholar-url` 与飞书直贴 Scholar 链接已接入增强版冷启动解析，可抓取兴趣标签、分页发表记录、合作作者与引用统计并写入初始画像
- Scholar / 主页冷启动后的角色元信息已最小化回写到 `roles.json`：仅保留 `bootstrap_summary`、`seed_directions`、`cold_start_updated_at` 等复用字段
- 角色再次执行“冷启动”时，系统会优先复用 role 元信息中的 `bootstrap_summary`，避免 Scholar 初始化结果只留在运行时画像里
- 飞书里的冷启动展示已收敛为统一画像卡片，不再在用户可见消息里额外强调 Google Scholar 抓取说明
- 精读报告的 PDF / source page 若已拿到完整摘要，现会尽量完整保留，不再因为默认长度阈值统一截断
- `reading-agent` 会优先用更完整的 PDF 摘要替换短 teaser 摘要，source page fallback 也同步放开为尽量保留全摘要
- 扫描版 PDF 的 OCR 补链已接入：当文本层抽取过少时，`pdf-parser` 会自动尝试 OCR fallback，尽量补全扫描版 PDF 的摘要与全文文本
- ACM / 付费 publisher 全文增强首轮已接入：当 DOI 官方页被 403 / 反爬拦截时，系统会继续尝试 OpenAlex OA 落地页 / 作者稿 URL，为精读报告提供 source page 或 PDF 全文 fallback
- 统一方向层第二轮增强已完成：方向显示、冷启动 `seed_directions`、角色 `bootstrap_summary`、周报与精读中的方向标签已统一复用 canonical registry
- 调度器运维增强已完成：支持失败后重试、错过窗口补偿执行、scheduler 运行态快照，以及 `/health` 返回调度状态
- 兴趣迁移与推荐排序的联动已继续打磨：`shifting / recovered` 状态下会对命中迁移主题的论文施加 drift bonus，并在日推卡片中解释迁移主题
- 周报增强已接入：可结合 OpenAlex 影响力信号识别“遗漏但重要”的论文，并补充推荐准确率解释、趋势解释、引用次数解释与被必读作者引用等更强关系信号
- 精读报告正文的 embedding 驱动增强已接入：用户兴趣 embedding 已进入全文 chunk 检索主链，并作为正文证据排序信号之一
- 飞书直传 PDF 已接入阅读信号侧链：单篇上传只记弱正信号，不直接触发兴趣漂移；同方向连续上传会进入 upload short-term interest
- 用户在直传 PDF 后补充“这类我最近想多看”等话术时，系统会复用最近上传论文的方向做强信号强化，并联动后续日推排序
- 飞书里直接发送 PDF 文本链接现也可进入精读链路，会复用 reading-agent 的下载解析、去重、阅读信号与后续排序联动
- `must-read` 已切回硬优先：命中后不会再被低分过滤、多源配额或推送数量限制裁掉，并固定排在每日清单最顶部
- Scholar 冷启动深层信号已增强：高引代表作与更细粒度合作网络（合作频次 / 合作论文累计引用 / 最近年份 / 常见 venue）已进入解析结果与冷启动说明
- 反馈解释已新增更细的对比信号：会尝试生成“你选了 06 但跳过了 08，所以当前更偏 X 而非 Y”这类逐条说明

## 🔍 Research Infra 方案对照（2026-04-17）

### 已对齐
- 冷启动主链路已覆盖：自然语言、Google Scholar、个人主页、论文/PDF 冷启动四种入口都已接入
- 每日推送 + 编号反馈 + `all red / all lock / none` 主交互已接入
- 必读清单的作者 / 机构 / 关键词管理已接入
- 精读报告主链路已打通：选中文献精读、飞书直传 PDF、飞书文本 PDF 链接、PDF/source page fallback、资源链接区和完整模板均已接入
- 兴趣迁移、兴趣向量、主题权重、作者/机构热度、周报解释与遗漏论文提示已有首版实现

### 新增对齐（2026-04-17 本轮补齐）
1. **忙碌日信号门控**
   - `all lock` 现已支持“只保留阅读队列、不更新偏好模型”的低可靠度门控

2. **渐进式展开交互**
   - 已支持“再看看🟡里有没有遗漏的”
   - 已支持“展开某个分组 / 某个主题候选”的补充展开回复

3. **分类纠错交互**
   - 已支持“16 应该是 🔴 不是 🟡”这类分组纠错，并会把对应主题作为强校正信号写回画像

4. **精读报告质量反馈**
   - 已支持“这篇报告写得好 / 没抓住重点”这类显式评价
   - 负反馈会写入 `report_preferences`，后续精读会提高证据密度并偏向 evidence-first 组织

5. **文档阅读隐式反馈**
   - 已接入精读文档打开状态跟踪（通过 webhook 跳转链接记录）
   - 已接入阅读停留代理时长（通过文档打开后到下一次用户消息的时差估算）

6. **反馈时序强弱**
   - “秒回 vs 隔几小时”已进入反馈权重链路，会影响本轮画像更新强度

7. **顶会 reviewer / 活跃 reviewer 清单**
   - 已接入基于 OpenReview 公共 group 的 reviewer / AC 候选抓取首版
   - 当 venue 未公开 reviewer group 时，系统会明确提示当前无法自动追踪

8. **表情 / 菜单交互**
   - 飞书表情反馈现会写回行为日志
   - 飞书菜单按钮现可继续路由到 coordinator 命令链路

### 仍待继续增强
1. **周报里的外部影响信号进一步扩展**
   - 当前已支持 OpenAlex `cited_by_count`、被必读作者引用、已选高影响论文等周报信号
   - 如后续继续增强，可继续补更多引用关系图谱和更长期的质量趋势统计

## ⏳ V0.2.0 计划
### 高优先级 P0（已完成首轮）
1. **Google Scholar 冷启动持续增强**
   - 当前已支持 `--scholar-url`、飞书直接粘贴 Scholar 链接、分页抓取、轻量 fallback、合作作者与引用统计信号，并向个人主页继续级联增强
   - 后续可继续增强更强的反爬兜底、跨源补全和更细粒度的合作网络图谱（作为后续优化，非当前阻塞）

2. **扫描版 PDF OCR 增强**
   - 首轮 OCR 补链已接入：当文本层抽取过少时，会自动尝试 OCR fallback，优先补全扫描版 PDF 的摘要和全文文本
   - 后续可继续增强 OCR 对公式、表格、多语言和大文档的精细化支持

3. **ACM / 付费 publisher 全文增强**
   - 当前已有 DOI / OpenAlex / Crossref 元数据兜底，并能在 DOI 官方页面拦截时继续尝试 OpenAlex OA 落地页 / 作者稿 URL
   - 后续可继续增强更多发表商和仓储源的作者稿探测，进一步减少摘要级精读占比

### 中优先级 P1
1. **Webhook 服务器常驻部署**
   - 配置开机自启
   - 日志轮转
   - 错误告警

2. **交互事件增强**
   - 飞书表情反馈写回行为日志
   - 飞书菜单按钮点击后路由到对应 Agent

3. **更多可解释交互增强**
   - 将日推 / 周报中的解释语句进一步收敛成更稳定的用户可见表达
   - 继续补充方向层在更多交互入口中的统一展示与反馈提示

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
