# SciTaste 数据集使用指南

## 快速开始

### 1. 导出数据集

```bash
# 导出当前数据库快照
cd d:\scitaste
python scripts/export_dataset_snapshot.py

# 查看导出的数据
ls data/dataset_exports/
```

### 2. 导出到指定位置

```bash
python scripts/export_dataset_snapshot.py \
  --db-path data/scitaste.db \
  --roles-path data/roles.json \
  --output-root data/dataset_exports
```

### 3. 加载数据进行分析

```python
import pandas as pd
import json
from pathlib import Path

# 找到最新的导出目录
export_root = Path("data/dataset_exports")
latest_export = max(export_root.glob("scitaste_snapshot_*"), key=lambda x: x.name)

print(f"Loading data from: {latest_export}")

# 加载论文池
papers = pd.read_csv(latest_export / "paper_pool.csv")
print(f"Papers: {len(papers)}")

# 加载用户画像摘要
profiles = pd.read_csv(latest_export / "profile_summary.csv")
print(f"Profiles: {len(profiles)}")

# 加载 Episode 统计
episodes = pd.read_csv(latest_export / "episodes.csv")
print(f"Episodes: {len(episodes)}")

# 加载行为日志
behaviors = pd.read_csv(latest_export / "behavior_logs.csv")
print(f"Behavior logs: {len(behaviors)}")

# 加载评测结果（如果存在）
eval_dir = latest_export / "evaluation"
if eval_dir.exists():
    if (eval_dir / "main_experiment_results.csv").exists():
        eval_results = pd.read_csv(eval_dir / "main_experiment_results.csv")
        print(f"Evaluation results: {len(eval_results)}")
```

---

## 四层数据分析示例

### 论文池层分析

```python
import pandas as pd

papers = pd.read_csv("paper_pool.csv")

# 统计论文来源分布
print("论文来源统计:")
print(f"  总论文数：{len(papers)}")
print(f"  已推送：{papers['pushed'].sum()}")
print(f"  有 arXiv ID: {papers['arxiv_id'].notna().sum()}")
print(f"  有 DOI: {papers['doi'].notna().sum()}")

# 按发表年份统计
papers['publish_year'] = pd.to_datetime(papers['publish_date']).dt.year
year_dist = papers['publish_year'].value_counts().sort_index()
print("\n按年份分布:")
print(year_dist)

# 按机构统计
institution_counts = papers['institution'].value_counts().head(10)
print("\nTop 10 机构:")
print(institution_counts)
```

### 用户画像层分析

```python
import pandas as pd
import json

profiles = pd.read_csv("profile_summary.csv")

# 统计画像基本信息
print("用户画像统计:")
print(f"  总画像数：{len(profiles)}")
print(f"  平均核心方向数：{profiles['core_direction_count'].mean():.2f}")
print(f"  平均主题权重数：{profiles['topic_count'].mean():.2f}")
print(f"  有必读规则：{(profiles['must_read_total_count'] > 0).sum()}")
print(f"  有漂移状态：{profiles['drift_status'].notna().sum()}")

# 分析漂移状态分布
drift_dist = profiles['drift_status'].value_counts()
print("\n漂移状态分布:")
print(drift_dist)

# 解析核心方向权重
def parse_directions(json_str):
    if pd.isna(json_str):
        return {}
    return json.loads(json_str)

profiles['directions'] = profiles['core_directions_json'].apply(parse_directions)

# 统计最常见的研究方向
all_directions = {}
for dirs in profiles['directions']:
    for direction, weight in dirs.items():
        if direction not in all_directions:
            all_directions[direction] = []
        all_directions[direction].append(weight)

direction_stats = {
    k: {
        'count': len(v),
        'avg_weight': sum(v) / len(v),
        'max_weight': max(v)
    }
    for k, v in all_directions.items()
}

print("\n研究方向统计:")
for direction, stats in sorted(direction_stats.items(), key=lambda x: -x[1]['count'])[:10]:
    print(f"  {direction}: {stats['count']} 用户，平均权重 {stats['avg_weight']:.2f}")
```

### Episode 层分析

```python
import pandas as pd
import json

episodes = pd.read_csv("episodes.csv")
behaviors = pd.read_csv("behavior_logs.csv")

# Episode 基本统计
print("Episode 统计:")
print(f"  总 Episode 数：{len(episodes)}")
print(f"  日均推送 Episode: {(episodes['episode_type'] == 'daily_push').sum()}")
print(f"  平均每轮候选论文数：{episodes['candidate_papers'].mean():.2f}")
print(f"  平均每轮选中文献数：{episodes['selected_papers'].mean():.2f}")
print(f"  总体选择率：{episodes['selection_rate'].mean():.2f}")

# 按 Episode 类型统计
type_stats = episodes.groupby('episode_type').agg({
    'candidate_papers': 'sum',
    'selected_papers': 'sum',
    'reports_created': 'sum',
}).reset_index()

print("\n按类型统计:")
print(type_stats)

# 分析分类表现（🔴🟡🔵）
category_cols = ['selected_must_read', 'selected_high_relevant', 
                 'selected_maybe_interested', 'selected_edge_relevant']
category_totals = episodes[category_cols].sum()

print("\n按分类选择统计:")
print(f"  必读 (🔴): {category_totals['selected_must_read']}")
print(f"  高相关 (🔴): {category_totals['selected_high_relevant']}")
print(f"  可能感兴趣 (🟡): {category_totals['selected_maybe_interested']}")
print(f"  边缘相关 (🔵): {category_totals['selected_edge_relevant']}")

# 兴趣漂移分析
drift_updates = episodes['drift_updates'].sum()
print(f"\n兴趣漂移更新次数：{drift_updates}")

# 解析漂移状态序列
def parse_json_list(json_str):
    if pd.isna(json_str) or json_str == '':
        return []
    try:
        return json.loads(json_str)
    except:
        return []

episodes['drift_topics'] = episodes['drift_top_shift_topics_json'].apply(parse_json_list)

all_drift_topics = []
for topics in episodes['drift_topics']:
    all_drift_topics.extend(topics)

from collections import Counter
topic_counts = Counter(all_drift_topics)
print("\n最常见的漂移主题:")
for topic, count in topic_counts.most_common(10):
    print(f"  {topic}: {count} 次")
```

### 行为日志分析

```python
import pandas as pd

behaviors = pd.read_csv("behavior_logs.csv")

# 行为类型统计
action_counts = behaviors['action'].value_counts()
print("行为类型统计:")
print(action_counts)

# 按分类统计选择率
def calc_selection_rate(group):
    selected = (group['action'] == 'selected').sum()
    pushed = (group['action'] == 'pushed').sum()
    return selected / pushed if pushed > 0 else 0

category_rates = behaviors.groupby('category').apply(calc_selection_rate)
print("\n按分类选择率:")
print(category_rates)

# 精读报告分析
report_actions = behaviors[behaviors['action'].isin(['created_report', 'opened_report'])]
report_stats = report_actions['action'].value_counts()
print("\n精读报告统计:")
print(f"  生成报告：{report_stats.get('created_report', 0)}")
print(f"  打开报告：{report_stats.get('opened_report', 0)}")

# 反馈延迟分析
latency_col = 'feedback_latency_seconds'
if latency_col in behaviors.columns:
    latencies = pd.to_numeric(behaviors[latency_col], errors='coerce')
    print(f"\n反馈延迟统计 (秒):")
    print(f"  平均：{latencies.mean():.1f}")
    print(f"  中位数：{latencies.median():.1f}")
    print(f"  最快：{latencies.min():.1f}")
    print(f"  最慢：{latencies.max():.1f}")
```

### 评测层分析

```python
import pandas as pd
from pathlib import Path

eval_dir = Path("evaluation")

# 主实验结果分析
if (eval_dir / "main_experiment_results.csv").exists():
    results = pd.read_csv(eval_dir / "main_experiment_results.csv")
    
    print("主实验结果:")
    print(f"  实验总数：{len(results)}")
    print(f"  平均 NDCG@5: {results['ndcg_at_5'].mean():.4f}")
    print(f"  平均 NDCG@10: {results['ndcg_at_10'].mean():.4f}")
    print(f"  平均 HitRate@5: {results['hit_rate_at_5'].mean():.4f}")
    print(f"  平均 HitRate@10: {results['hit_rate_at_10'].mean():.4f}")
    
    # 按任务类型分析
    task_metrics = results.groupby('task_type')[
        ['ndcg_at_5', 'ndcg_at_10', 'hit_rate_at_5', 'hit_rate_at_10']
    ].mean()
    print("\n按任务类型指标:")
    print(task_metrics)

# 消融实验分析
if (eval_dir / "ablation_study.csv").exists():
    ablations = pd.read_csv(eval_dir / "ablation_study.csv")
    
    print("\n消融实验:")
    for _, row in ablations.iterrows():
        print(f"  {row['ablation_id']}: {row['description']}")
        print(f"    假设：{row['hypothesis']}")
        print(f"    结论：{row['conclusion'] or '待填充'}")
```

---

## 论文层统计分析

### 计算推荐覆盖率

```python
import pandas as pd

papers = pd.read_csv("paper_pool.csv")
episodes = pd.read_csv("episodes.csv")

# 计算被推送过的论文比例
pushed_papers = papers[papers['pushed'] == 1]
print(f"论文池总数：{len(papers)}")
print(f"已推送论文数：{len(pushed_papers)}")
print(f"推送覆盖率：{len(pushed_papers) / len(papers) * 100:.1f}%")
```

### 分析用户选择偏好

```python
import pandas as pd

behaviors = pd.read_csv("behavior_logs.csv")

# 按分类计算选择率
selected = behaviors[behaviors['action'] == 'selected']
pushed = behaviors[behaviors['action'] == 'pushed']

category_stats = []
for category in behaviors['category'].unique():
    cat_selected = selected[selected['category'] == category]
    cat_pushed = pushed[pushed['category'] == category]
    
    rate = len(cat_selected) / len(cat_pushed) if len(cat_pushed) > 0 else 0
    category_stats.append({
        'category': category,
        'selected': len(cat_selected),
        'pushed': len(cat_pushed),
        'selection_rate': rate
    })

stats_df = pd.DataFrame(category_stats)
print(stats_df.sort_values('selection_rate', ascending=False))
```

---

## 兴趣漂移分析

### 检测漂移事件

```python
import pandas as pd
import json

drift_events = pd.read_csv("drift_events.csv")

# 统计漂移状态转换
def parse_status_sequence(json_str):
    if pd.isna(json_str):
        return []
    try:
        return json.loads(json_str)
    except:
        return []

drift_events['status_seq'] = drift_events['drift_status_sequence_json'].apply(parse_status_sequence)

# 统计状态转换次数
transitions = {}
for seq in drift_events['status_seq']:
    for i in range(len(seq) - 1):
        key = f"{seq[i]} -> {seq[i+1]}"
        transitions[key] = transitions.get(key, 0) + 1

print("漂移状态转换:")
for transition, count in sorted(transitions.items(), key=lambda x: -x[1])[:10]:
    print(f"  {transition}: {count}")
```

---

## 导出 Manifest 信息

```python
import json
from pathlib import Path

# 读取 manifest
export_root = Path("data/dataset_exports")
latest_export = max(export_root.glob("scitaste_snapshot_*"), key=lambda x: x.name)
manifest = json.loads((latest_export / "manifest.json").read_text())

print(f"数据集名称：{manifest['dataset_name']}")
print(f"导出时间：{manifest['exported_at']}")
print(f"论文数：{manifest['paper_count']}")
print(f"用户数：{manifest['unique_user_count']}")
print(f"Episode 数：{manifest['episode_count']}")
print(f"行为日志数：{manifest['behavior_log_count']}")

# 打印分层统计
if 'layer_statistics' in manifest:
    print("\n分层统计:")
    for layer, stats in manifest['layer_statistics'].items():
        print(f"\n  {layer}:")
        for key, value in stats.items():
            print(f"    {key}: {value}")
```

---

## 常见分析场景

### 场景 1：分析推荐质量随时间的变化

```python
import pandas as pd
import matplotlib.pyplot as plt

episodes = pd.read_csv("episodes.csv")
episodes['started_at'] = pd.to_datetime(episodes['started_at'])

# 按日期聚合选择率
daily_stats = episodes.groupby(episodes['started_at'].dt.date).agg({
    'candidate_papers': 'sum',
    'selected_papers': 'sum',
}).reset_index()

daily_stats['selection_rate'] = (
    daily_stats['selected_papers'] / daily_stats['candidate_papers']
)

# 绘制趋势图
plt.figure(figsize=(12, 4))
plt.plot(daily_stats['started_at'], daily_stats['selection_rate'], marker='o')
plt.xlabel('Date')
plt.ylabel('Selection Rate')
plt.title('Daily Selection Rate Trend')
plt.xticks(rotation=45)
plt.tight_layout()
plt.savefig('selection_rate_trend.png')
```

### 场景 2：分析必读规则的影响

```python
import pandas as pd

episodes = pd.read_csv("episodes.csv")

# 比较有必读和无必读的 episode
with_must_read = episodes[episodes['candidate_must_read'] > 0]
without_must_read = episodes[episodes['candidate_must_read'] == 0]

print("必读规则影响分析:")
print(f"  有必读的 Episode 数：{len(with_must_read)}")
print(f"  无必读的 Episode 数：{len(without_must_read)}")
print(f"\n  有必读的选择率：{with_must_read['selection_rate'].mean():.3f}")
print(f"  无必读的选择率：{without_must_read['selection_rate'].mean():.3f}")
```

### 场景 3：精读报告参与度分析

```python
import pandas as pd

episodes = pd.read_csv("episodes.csv")

# 分析精读报告生成和打开情况
report_episodes = episodes[episodes['reports_created'] > 0]

print("精读报告参与分析:")
print(f"  生成报告的 Episode 数：{len(report_episodes)}")
print(f"  平均每个 Episode 生成报告数：{report_episodes['reports_created'].mean():.2f}")
print(f"  平均报告打开率：{report_episodes['report_open_rate'].mean():.2f}")

# 分析打开率分布
high_engagement = report_episodes[report_episodes['report_open_rate'] > 0.5]
low_engagement = report_episodes[report_episodes['report_open_rate'] < 0.5]

print(f"\n  高参与度 (>50%): {len(high_engagement)}")
print(f"  低参与度 (<50%): {len(low_engagement)}")
```

---

## 故障排查

### 问题：导出失败

```bash
# 检查数据库是否存在
ls data/scitaste.db

# 检查数据库完整性
python -c "import sqlite3; conn = sqlite3.connect('data/scitaste.db'); print(conn.execute('SELECT COUNT(*) FROM papers').fetchone())"
```

### 问题：数据为空

```bash
# 检查各表记录数
python -c "
import sqlite3
conn = sqlite3.connect('data/scitaste.db')
for table in ['papers', 'profiles', 'behavior_logs']:
    count = conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
    print(f'{table}: {count}')
"
```

### 问题：评测层文件缺失

评测层文件是模板化的，如果主实验结果表为空，检查：
1. 是否有 `daily_push` 类型的 Episode
2. 候选论文数是否大于 0

---

## 最佳实践

1. **定期导出**: 每周或每月导出一次数据集，跟踪系统使用情况
2. **版本管理**: 为重要实验节点保存数据集快照
3. **备份**: 将导出的数据集备份到版本控制系统或云存储
4. **自动化**: 可以配置定时任务自动导出数据集
