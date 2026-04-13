# Profile Updater Skill

## 职责

用户画像更新：实现兴趣向量 EMA 更新算法、主题权重的时间衰减与负信号处理、多因子加权排序逻辑。

## 核心算法

### 1. 兴趣向量 EMA 更新

使用指数移动平均（Exponential Moving Average）缓慢更新用户兴趣向量：

```python
def update_interest_vector(current_vector, selected_vectors, alpha=0.1):
    """
    更新兴趣向量
    
    Args:
        current_vector: 当前兴趣向量
        selected_vectors: 用户选择的论文 embedding 列表
        alpha: 学习率（默认 0.1，缓慢漂移）
    
    Returns:
        更新后的兴趣向量
    """
    # 计算选中论文的平均 embedding
    if not selected_vectors:
        return current_vector
    
    avg_selected = np.mean(selected_vectors, axis=0)
    
    # EMA 更新
    new_vector = (1 - alpha) * current_vector + alpha * avg_selected
    
    # 归一化
    new_vector = new_vector / np.linalg.norm(new_vector)
    
    return new_vector
```

### 2. 主题权重更新

#### 正信号更新

```python
def update_topic_weight_positive(current_weight, signal_strength=0.02):
    """
    正向更新主题权重（用户选择了相关论文）
    
    Args:
        current_weight: 当前权重
        signal_strength: 信号强度（默认 0.02）
    
    Returns:
        更新后的权重（上限 1.0）
    """
    return min(1.0, current_weight + signal_strength)
```

#### 负信号更新（时间衰减）

```python
def apply_time_decay(weights, days_inactive, decay_rate=0.01):
    """
    应用时间衰减
    
    Args:
        weights: 主题权重量典
        days_inactive: 未活跃天数
        decay_rate: 衰减率（默认每天 1%）
    
    Returns:
        衰减后的权重
    """
    decayed = {}
    for topic, weight in weights.items():
        # 指数衰减
        decayed[topic] = weight * (1 - decay_rate) ** days_inactive
        # 确保不低于最小值
        decayed[topic] = max(0.1, decayed[topic])
    return decayed
```

#### 新主题检测

```python
def detect_new_topic(selected_papers, existing_topics, threshold=3):
    """
    检测新兴趣主题
    
    Args:
        selected_papers: 用户选择的论文列表
        existing_topics: 已有主题列表
        threshold: 连续天数阈值
    
    Returns:
        新主题列表
    """
    # 统计论文主题分布
    topic_counts = {}
    for paper in selected_papers:
        for topic in paper.get("topics", []):
            if topic not in existing_topics:
                topic_counts[topic] = topic_counts.get(topic, 0) + 1
    
    # 超过阈值的作为新主题
    new_topics = {
        topic: 0.4  # 新主题初始权重
        for topic, count in topic_counts.items()
        if count >= threshold
    }
    
    return new_topics
```

### 3. 多因子加权排序

```python
def calculate_paper_score(paper, user_profile, weights_config):
    """
    计算论文综合得分
    
    score = w1 * 兴趣向量相似度
          + w2 * 主题权重匹配
          + w3 * 作者/机构热度
          + w4 * 论文质量信号
          + bonus（必读清单命中）
    
    Args:
        paper: 论文字典
        user_profile: 用户画像
        weights_config: 权重配置
    
    Returns:
        综合得分
    """
    w = weights_config
    
    # 1. 兴趣向量相似度（余弦相似度）
    interest_similarity = cosine_similarity(
        paper["embedding"],
        user_profile["interest_vector"]
    )
    
    # 2. 主题权重匹配
    topic_match = 0
    for topic in paper.get("topics", []):
        if topic in user_profile["topic_weights"]:
            topic_match += user_profile["topic_weights"][topic]
    topic_match = topic_match / max(1, len(paper.get("topics", [])))
    
    # 3. 作者/机构热度
    author_score = 0
    for author in paper.get("authors", []):
        if author in user_profile["author_heat"]:
            author_score += user_profile["author_heat"][author]
    author_score = author_score / max(1, len(paper.get("authors", [])))
    
    # 4. 论文质量信号
    quality_score = paper.get("quality_score", 0.5)
    
    # 5. 必读清单加成
    bonus = 0
    if is_must_read(paper, user_profile):
        bonus = w.get("bonus_must_read", 1.0)
    
    # 综合计算
    score = (
        w.get("w1_interest_vector", 0.35) * interest_similarity +
        w.get("w2_topic_weight", 0.25) * topic_match +
        w.get("w3_author_institution", 0.20) * author_score +
        w.get("w4_quality_signal", 0.20) * quality_score +
        bonus
    )
    
    return min(1.0, score)  # 上限 1.0
```

## API

| 函数 | 参数 | 返回 | 说明 |
|------|------|------|------|
| `update_profile_with_feedback(profile, selected_papers, skipped_papers)` | 画像，选中论文，跳过论文 | updated_profile | 基于反馈更新画像 |
| `update_interest_vector(current_vector, selected_vectors, alpha)` | 当前向量，选中向量，学习率 | new_vector | EMA 更新兴趣向量 |
| `apply_time_decay(weights, days, decay_rate)` | 权重，天数，衰减率 | decayed_weights | 时间衰减 |
| `calculate_paper_score(paper, profile, weights_config)` | 论文，画像，权重配置 | score | 计算论文得分 |
| `detect_new_topic(selected_papers, existing_topics)` | 选中论文，已有主题 | new_topics | 检测新主题 |
| `is_must_read(paper, profile)` | 论文，画像 | boolean | 是否必读清单命中 |

## 脚本实现 (scripts/update_profile.py)

```python
#!/usr/bin/env python3
"""
Profile Updater: User profile update algorithms
"""

import numpy as np
from typing import Dict, List, Any
from datetime import datetime, timedelta
import json

def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """计算余弦相似度"""
    v1 = np.array(vec1)
    v2 = np.array(vec2)
    return float(np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2)))

def update_interest_vector(
    current_vector: List[float],
    selected_vectors: List[List[float]],
    alpha: float = 0.1
) -> List[float]:
    """
    使用 EMA 更新兴趣向量
    """
    if not selected_vectors:
        return current_vector
    
    # 计算平均 embedding
    avg_vector = np.mean(selected_vectors, axis=0)
    
    # EMA 更新
    current = np.array(current_vector)
    new_vector = (1 - alpha) * current + alpha * avg_vector
    
    # 归一化
    norm = np.linalg.norm(new_vector)
    if norm > 0:
        new_vector = new_vector / norm
    
    return new_vector.tolist()

def update_topic_weights(
    current_weights: Dict[str, float],
    selected_papers: List[Dict],
    skipped_papers: List[Dict],
    positive_delta: float = 0.02,
    negative_delta: float = 0.01
) -> Dict[str, float]:
    """
    更新主题权重
    """
    weights = current_weights.copy()
    
    # 正向更新（选中的论文）
    for paper in selected_papers:
        for topic in paper.get("keywords", []):
            if topic in weights:
                weights[topic] = min(1.0, weights[topic] + positive_delta)
            else:
                weights[topic] = 0.4  # 新主题初始权重
    
    # 负向更新（跳过的论文）
    for paper in skipped_papers:
        for topic in paper.get("keywords", []):
            if topic in weights:
                weights[topic] = max(0.1, weights[topic] - negative_delta)
    
    return weights

def apply_time_decay(
    weights: Dict[str, float],
    days_inactive: int,
    decay_rate: float = 0.01
) -> Dict[str, float]:
    """
    应用时间衰减
    """
    decayed = {}
    for topic, weight in weights.items():
        decayed[topic] = weight * ((1 - decay_rate) ** days_inactive)
        decayed[topic] = max(0.1, decayed[topic])  # 不低于 0.1
    return decayed

def calculate_paper_score(
    paper: Dict,
    profile: Dict,
    weights_config: Dict = None
) -> float:
    """
    计算论文综合得分
    """
    if weights_config is None:
        weights_config = {
            "w1_interest_vector": 0.35,
            "w2_topic_weight": 0.25,
            "w3_author_institution": 0.20,
            "w4_quality_signal": 0.20,
            "bonus_must_read": 1.0
        }
    
    # 兴趣向量相似度
    interest_sim = cosine_similarity(
        paper.get("embedding", [0] * 768),
        profile.get("interest_vector", [0] * 768)
    )
    
    # 主题权重匹配
    topic_match = 0
    paper_topics = paper.get("keywords", [])
    if paper_topics:
        for topic in paper_topics:
            if topic in profile.get("topic_weights", {}):
                topic_match += profile["topic_weights"][topic]
        topic_match /= len(paper_topics)
    
    # 作者/机构热度
    author_score = 0
    paper_authors = paper.get("authors", [])
    if paper_authors:
        author_heat = profile.get("author_heat", {})
        for author in paper_authors:
            author_score += author_heat.get(author, 0)
        author_score /= len(paper_authors)
    
    # 质量信号
    quality_score = paper.get("quality_score", 0.5)
    
    # 必读清单加成
    bonus = 0
    if is_must_read(paper, profile):
        bonus = weights_config.get("bonus_must_read", 1.0)
    
    # 综合计算
    score = (
        weights_config.get("w1_interest_vector", 0.35) * interest_sim +
        weights_config.get("w2_topic_weight", 0.25) * topic_match +
        weights_config.get("w3_author_institution", 0.20) * author_score +
        weights_config.get("w4_quality_signal", 0.20) * quality_score +
        bonus
    )
    
    return min(1.0, score)

def is_must_read(paper: Dict, profile: Dict) -> bool:
    """
    检查论文是否是必读清单命中
    """
    must_read = profile.get("must_read", {})
    
    # 检查作者
    must_authors = must_read.get("authors", [])
    paper_authors = paper.get("authors", [])
    for author in paper_authors:
        for must_author in must_authors:
            if must_author.lower() in author.lower():
                return True
    
    # 检查机构
    must_institutions = must_read.get("institutions", [])
    paper_institution = paper.get("institution", "")
    for inst in must_institutions:
        if inst.lower() in paper_institution.lower():
            return True
    
    # 检查关键词
    must_keywords = must_read.get("keywords", [])
    paper_keywords = paper.get("keywords", [])
    for keyword in must_keywords:
        if keyword.lower() in [k.lower() for k in paper_keywords]:
            return True
    
    return False

def update_profile_with_feedback(
    profile: Dict,
    selected_papers: List[Dict],
    skipped_papers: List[Dict]
) -> Dict:
    """
    基于用户反馈更新画像
    """
    updated = profile.copy()
    
    # 更新兴趣向量
    selected_embeddings = [p.get("embedding", []) for p in selected_papers if p.get("embedding")]
    if selected_embeddings:
        updated["interest_vector"] = update_interest_vector(
            profile.get("interest_vector", [0] * 768),
            selected_embeddings,
            alpha=0.1
        )
    
    # 更新主题权重
    updated["topic_weights"] = update_topic_weights(
        profile.get("topic_weights", {}),
        selected_papers,
        skipped_papers
    )
    
    # 更新时间戳
    updated["updated_at"] = datetime.now().isoformat()
    
    # 递增版本号
    version = updated.get("version", "0.1")
    major, minor = map(int, version.split("."))
    updated["version"] = f"{major}.{minor + 1}"
    
    return updated

if __name__ == "__main__":
    # 测试
    test_profile = {
        "interest_vector": [0.5, 0.3, 0.2],
        "topic_weights": {"machine learning": 0.8, "biology": 0.6},
        "author_heat": {"John Smith": 0.7}
    }
    
    test_paper = {
        "embedding": [0.4, 0.4, 0.2],
        "keywords": ["machine learning"],
        "authors": ["John Smith"],
        "quality_score": 0.8
    }
    
    score = calculate_paper_score(test_paper, test_profile)
    print(f"Paper score: {score:.3f}")

```

## 权重配置 (config/scoring_weights.yaml)

```yaml
# 排序权重配置
w1_interest_vector: 0.35    # 兴趣向量相似度
w2_topic_weight: 0.25       # 主题权重匹配
w3_author_institution: 0.20 # 作者/机构热度
w4_quality_signal: 0.20     # 论文质量信号
bonus_must_read: 1.0        # 必读清单加成

# 更新参数
ema_alpha: 0.1              # 兴趣向量学习率
topic_positive_delta: 0.02  # 主题权重正向增量
topic_negative_delta: 0.01  # 主题权重负向减量
time_decay_rate: 0.01       # 时间衰减率（每天）
new_topic_threshold: 3      # 新主题检测阈值
new_topic_init_weight: 0.4  # 新主题初始权重

# 分类阈值
threshold_high_relevant: 0.75   # 🔴 高度相关
threshold_maybe_interested: 0.50 # 🟡 可能感兴趣
# < 0.50 → 🔵 边缘相关
```

## 注意事项

1. **缓慢漂移**：EMA alpha 设为 0.1，避免被单日偏好带偏
2. **负信号谨慎**：负向增量小于正向（0.01 vs 0.02），因为不选择可能是没时间
3. **时间衰减**：30 天前的信号权重逐渐降低
4. **新主题检测**：需要连续出现才认为是新兴趣
