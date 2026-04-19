# SciTaste 人工评估与相关性分析模板

这份模板面向当前 SciTaste 项目，目标不是替代主实验，而是作为补充实验/附录中的人工评估与相关性分析材料。

当前项目最适合做的小规模人工评估维度：

- 推荐相关性
- 解释可信度
- 精读有用性
- 可选：画像符合度

不建议一开始做过多主观维度，以免与现有代码日志链路脱节。

## 一、推荐的 Excel 工作簿结构

建议建立一个 Excel 文件，包含以下 4 个 sheet：

1. `sample_registry`
2. `subjective_scores`
3. `objective_metrics`
4. `correlation_analysis`

---

## 二、Sheet 1：sample_registry

用途：
- 记录每个被抽样评估的 episode / 报告样本
- 统一人工评估样本编号，方便后续对齐客观指标

建议表头如下：

| sample_id | user_id | role_name | push_id | episode_date | evaluation_unit | paper_id | paper_title | category | must_read_hit | drift_state | report_generated | report_opened | evaluator_group | notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|

字段说明：
- `sample_id`：唯一编号，例如 `S001`
- `user_id`：对应用户
- `role_name`：例如 `rolea`
- `push_id`：对应推送轮次
- `episode_date`：该轮日期
- `evaluation_unit`：建议填 `push_level` 或 `report_level`
- `paper_id`：如果是 report-level，则填论文 ID
- `paper_title`：论文标题
- `category`：`must_read / high_relevant / maybe_interested / edge_relevant`
- `must_read_hit`：是否命中必读
- `drift_state`：`stable / shifting / recovered`
- `report_generated`：是否生成精读
- `report_opened`：是否打开精读文档
- `evaluator_group`：例如 `student_a / student_b`
- `notes`：备注

推荐抽样方案：
- 推荐排序人工评估：抽 20–30 个 push-level 样本
- 精读人工评估：抽 20–30 个 report-level 样本

---

## 三、Sheet 2：subjective_scores

用途：
- 记录人工评分结果
- 一行对应一个评测人对一个样本的打分

建议表头如下：

| sample_id | evaluator_id | recommendation_relevance | explanation_credibility | report_usefulness | profile_consistency | overall_score | comment |
|---|---|---|---|---|---|---|---|

字段说明：
- `sample_id`：关联 `sample_registry`
- `evaluator_id`：评测人编号
- `recommendation_relevance`：1–5
- `explanation_credibility`：1–5
- `report_usefulness`：1–5
- `profile_consistency`：1–5，可选
- `overall_score`：整体分，可选
- `comment`：自由文本评价

### 评分标准模板

#### 推荐相关性（recommendation_relevance）
- 5分：推荐与用户当前研究方向高度一致，且覆盖近期重点兴趣
- 4分：推荐整体相关，仅存在少量偏差
- 3分：推荐部分相关，但夹杂较多边缘论文
- 2分：推荐与用户兴趣匹配较弱
- 1分：推荐明显偏离用户真实研究方向

#### 解释可信度（explanation_credibility）
- 5分：解释准确、清晰，能够合理说明推荐原因或画像变化
- 4分：解释整体合理，但细节上略显粗糙
- 3分：解释部分成立，但存在模糊或泛化表述
- 2分：解释较弱，难以支撑推荐结论
- 1分：解释与推荐结果明显不符

#### 精读有用性（report_usefulness）
- 5分：报告完整、重点突出，对快速理解论文有明显帮助
- 4分：报告较完整，存在少量细节缺失但不影响整体理解
- 3分：报告可用，但深度或重点把握一般
- 2分：报告遗漏较多，帮助有限
- 1分：报告未能有效抓住论文核心内容

#### 画像符合度（profile_consistency，可选）
- 5分：画像能准确反映用户研究方向和近期兴趣变化
- 4分：画像整体合理，但部分方向权重略有偏差
- 3分：画像大体合理，但遗漏了部分关键方向或近期变化
- 2分：画像对用户兴趣刻画不够准确
- 1分：画像明显偏离用户真实研究方向

---

## 四、Sheet 3：objective_metrics

用途：
- 记录与人工评分对应的客观指标
- 后续用于相关性分析

建议表头如下：

| sample_id | precision_at_k | recall_at_k | ndcg_at_k | high_relevant_selection_rate | maybe_interested_selection_rate | edge_relevant_selection_rate | must_read_top_placement_rate | must_read_retention_rate | drift_trigger_count | adaptation_lag | report_open_rate | avg_dwell_proxy | report_feedback_positive_rate | high_impact_miss_count | high_impact_selected_count | cited_by_must_read_count |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|

说明：
- 如果某个样本是 `push_level`，则主要填推荐相关指标
- 如果某个样本是 `report_level`，则主要填报告打开率、停留代理和报告正反馈率
- 与样本无关的指标可以留空

当前项目能直接从代码/日志支持的客观指标主要包括：
- `Precision@K`
- `Recall@K`
- `NDCG@K`
- `High-Relevant Selection Rate`
- `Maybe-Interested Selection Rate`
- `Edge-Relevant Selection Rate`
- `Must-Read Top Placement Rate`
- `Must-Read Retention Rate`
- `Drift Trigger Count`
- `Adaptation Lag`
- `Reading Report Open Rate`
- `Average Dwell Proxy`
- `Report Feedback Positive Rate`
- `High-Impact Miss Count`
- `High-Impact Selected Count`
- `Cited-by-Must-Read Count`

---

## 五、Sheet 4：correlation_analysis

用途：
- 分析人工评分与客观指标之间是否一致
- 证明客观指标确实能反映系统可用性

建议表头如下：

| analysis_id | subjective_metric | objective_metric | correlation_type | correlation_value | p_value | interpretation |
|---|---|---|---|---|---|---|

推荐分析组合：

| subjective_metric | objective_metric | 推荐原因 |
|---|---|---|
| recommendation_relevance | ndcg_at_k | 排序质量是否和人工感知一致 |
| recommendation_relevance | precision_at_k | 推荐命中率是否反映主观相关性 |
| explanation_credibility | must_read_top_placement_rate | 推荐解释和规则执行是否一致 |
| report_usefulness | report_open_rate | 人工觉得有用的报告是否更容易被打开 |
| report_usefulness | avg_dwell_proxy | 人工觉得有用的报告是否停留更久 |
| report_usefulness | report_feedback_positive_rate | 显式好评与人工打分是否一致 |
| profile_consistency | adaptation_lag | 适应更快的系统是否更符合用户认知 |

相关性方法建议：
- 样本量较小时：`Spearman`
- 样本量较大且分布较稳定时：`Pearson`

---

## 六、推荐的最低可行人工评估方案

如果时间有限，建议只做下面这组：

### 人工评估维度
- 推荐相关性
- 解释可信度
- 精读有用性

### 样本量
- 20 个 push-level 样本
- 20 个 report-level 样本
- 每个样本 2 名评测人

### 相关性分析
- 推荐相关性 vs NDCG@K
- 推荐相关性 vs Precision@K
- 精读有用性 vs Average Dwell Proxy
- 精读有用性 vs Report Feedback Positive Rate

---

## 七、和当前项目代码的对应关系

当前代码直接支持或可较低成本整理出的信号包括：

- 推荐排序结果：`daily-push-agent`
- must-read 顶置与保留：`daily-push-agent`
- 兴趣迁移状态与触发次数：`profile-updater` + `behavior_logs`
- 精读报告打开率与停留代理：`reading-agent` + `webhook-server` + `db_ops`
- 报告显式正负反馈：`master-coordinator` + `behavior_logs`
- 高影响遗漏论文与被必读作者引用：`profile-report-agent`

因此，这份人工评估模板与当前代码链路是对齐的，不需要额外发明脱离系统实现的新指标。

---

## 八、最建议你先填的三张表

1. `sample_registry`
2. `subjective_scores`
3. `objective_metrics`

等这三张表填好以后，再做 `correlation_analysis`。
