#!/usr/bin/env python3
"""
Profile Updater: User profile update algorithms

Implements:
- Interest vector EMA update
- Topic weight time decay
- Multi-factor scoring
"""

import numpy as np
from typing import Dict, List, Any
from datetime import datetime, timedelta
import json


def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Calculate cosine similarity"""
    v1 = np.array(vec1)
    v2 = np.array(vec2)
    norm1 = np.linalg.norm(v1)
    norm2 = np.linalg.norm(v2)
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return float(np.dot(v1, v2) / (norm1 * norm2))


def update_interest_vector(
    current_vector: List[float],
    selected_vectors: List[List[float]],
    alpha: float = 0.1
) -> List[float]:
    """
    Update interest vector using EMA

    Args:
        current_vector: Current interest vector
        selected_vectors: Selected papers' embeddings
        alpha: Learning rate (default 0.1 for slow drift)

    Returns:
        Updated interest vector
    """
    if not selected_vectors:
        return current_vector

    # Calculate average embedding
    avg_vector = np.mean(selected_vectors, axis=0)

    # EMA update
    current = np.array(current_vector)
    new_vector = (1 - alpha) * current + alpha * avg_vector

    # Normalize
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
    Update topic weights based on feedback

    Args:
        current_weights: Current topic weights
        selected_papers: Selected papers
        skipped_papers: Skipped papers
        positive_delta: Positive increment
        negative_delta: Negative decrement

    Returns:
        Updated topic weights
    """
    weights = current_weights.copy()

    # Positive update (selected papers)
    for paper in selected_papers:
        for topic in paper.get("keywords", []):
            if topic in weights:
                weights[topic] = min(1.0, weights[topic] + positive_delta)
            else:
                weights[topic] = 0.4  # New topic initial weight

    # Negative update (skipped papers)
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
    Apply time decay to weights

    Args:
        weights: Topic weights
        days_inactive: Days of inactivity
        decay_rate: Daily decay rate

    Returns:
        Decayed weights
    """
    decayed = {}
    for topic, weight in weights.items():
        decayed[topic] = weight * ((1 - decay_rate) ** days_inactive)
        decayed[topic] = max(0.1, decayed[topic])  # Minimum 0.1
    return decayed


def calculate_paper_score(
    paper: Dict,
    profile: Dict,
    weights_config: Dict = None
) -> float:
    """
    Calculate paper score

    score = w1 * interest_vector_similarity
          + w2 * topic_weight_match
          + w3 * author_institution_heat
          + w4 * quality_signal
          + bonus (must_read hit)

    Args:
        paper: Paper dictionary
        profile: User profile
        weights_config: Weight configuration

    Returns:
        Paper score (0-1)
    """
    if weights_config is None:
        weights_config = {
            "w1_interest_vector": 0.35,
            "w2_topic_weight": 0.25,
            "w3_author_institution": 0.20,
            "w4_quality_signal": 0.20,
            "bonus_must_read": 1.0
        }

    # Interest vector similarity
    interest_sim = cosine_similarity(
        paper.get("embedding", [0] * 768),
        profile.get("interest_vector", [0] * 768)
    )

    # Topic weight match
    # 计算匹配主题的权重和（取最大值，避免被未匹配主题稀释）
    topic_match = 0
    paper_topics = paper.get("keywords", [])
    if paper_topics:
        matched_weights = []
        for topic in paper_topics:
            if topic in profile.get("topic_weights", {}):
                matched_weights.append(profile["topic_weights"][topic])
        # 使用最大匹配权重（只要有一个主题匹配就算相关）
        if matched_weights:
            topic_match = max(matched_weights)

    # Author/Institution heat
    author_score = 0
    paper_authors = paper.get("authors", [])
    if paper_authors:
        author_heat = profile.get("author_heat", {})
        for author in paper_authors:
            author_score += author_heat.get(author, 0)
        author_score /= len(paper_authors)

    # Quality signal
    quality_score = paper.get("quality_score", 0.5)

    # Must-read bonus
    bonus = 0
    if is_must_read(paper, profile):
        bonus = weights_config.get("bonus_must_read", 1.0)

    # Calculate total score
    score = (
        weights_config.get("w1_interest_vector", 0.35) * interest_sim +
        weights_config.get("w2_topic_weight", 0.25) * topic_match +
        weights_config.get("w3_author_institution", 0.20) * author_score +
        weights_config.get("w4_quality_signal", 0.20) * quality_score +
        bonus
    )

    return min(1.0, score)  # Cap at 1.0


def get_must_read_matches(paper: Dict, profile: Dict) -> Dict[str, List[str]]:
    """
    Return detailed must-read matches for a paper.

    Args:
        paper: Paper dictionary
        profile: User profile

    Returns:
        Matched authors / institutions / keywords
    """
    must_read = profile.get("must_read", {})
    matches = {
        "authors": [],
        "institutions": [],
        "keywords": [],
    }

    # Check authors
    must_authors = must_read.get("authors", [])
    paper_authors = paper.get("authors", [])
    for author in paper_authors:
        for must_author in must_authors:
            if must_author.lower() in author.lower():
                if must_author not in matches["authors"]:
                    matches["authors"].append(must_author)

    # Check institutions
    must_institutions = must_read.get("institutions", [])
    paper_institution = str(paper.get("institution", "") or "")
    for inst in must_institutions:
        if inst.lower() in paper_institution.lower():
            if inst not in matches["institutions"]:
                matches["institutions"].append(inst)

    # Check keywords
    must_keywords = must_read.get("keywords", [])
    paper_keywords = [str(keyword or "") for keyword in paper.get("keywords", [])]
    paper_keywords_lower = [keyword.lower() for keyword in paper_keywords]
    for keyword in must_keywords:
        if keyword.lower() in paper_keywords_lower:
            if keyword not in matches["keywords"]:
                matches["keywords"].append(keyword)

    return matches


def is_must_read(paper: Dict, profile: Dict) -> bool:
    """
    Check if paper is in must-read list

    Args:
        paper: Paper dictionary
        profile: User profile

    Returns:
        True if must-read
    """
    matches = get_must_read_matches(paper, profile)

    return any(matches.values())


def detect_new_topics(
    selected_papers: List[Dict],
    existing_topics: List[str],
    threshold: int = 3
) -> Dict[str, float]:
    """
    Detect new topics from selected papers

    Args:
        selected_papers: Selected papers
        existing_topics: Existing topic list
        threshold: Minimum occurrences to consider as new topic

    Returns:
        New topics with initial weights
    """
    topic_counts = {}
    for paper in selected_papers:
        for topic in paper.get("keywords", []):
            if topic not in existing_topics:
                topic_counts[topic] = topic_counts.get(topic, 0) + 1

    new_topics = {
        topic: 0.4  # Initial weight for new topics
        for topic, count in topic_counts.items()
        if count >= threshold
    }

    return new_topics


def update_profile_with_feedback(
    profile: Dict,
    selected_papers: List[Dict],
    skipped_papers: List[Dict]
) -> Dict:
    """
    Update profile based on feedback

    Args:
        profile: Current profile
        selected_papers: Selected papers
        skipped_papers: Skipped papers

    Returns:
        Updated profile
    """
    updated = profile.copy()

    # Update interest vector
    selected_embeddings = [
        p.get("embedding", [])
        for p in selected_papers
        if p.get("embedding")
    ]
    if selected_embeddings:
        updated["interest_vector"] = update_interest_vector(
            profile.get("interest_vector", [0] * 768),
            selected_embeddings,
            alpha=0.1
        )

    # Update topic weights
    updated["topic_weights"] = update_topic_weights(
        profile.get("topic_weights", {}),
        selected_papers,
        skipped_papers
    )

    # Update timestamp
    updated["updated_at"] = datetime.now().isoformat()

    # Increment version
    version = updated.get("version", "0.1")
    major, minor = map(int, version.split("."))
    updated["version"] = f"{major}.{minor + 1}"

    return updated


if __name__ == "__main__":
    # Test
    test_profile = {
        "interest_vector": [0.5, 0.3, 0.2],
        "topic_weights": {"machine learning": 0.8, "biology": 0.6},
        "author_heat": {"John Smith": 0.7},
        "must_read": {"authors": [], "institutions": [], "keywords": []}
    }

    test_paper = {
        "embedding": [0.4, 0.4, 0.2],
        "keywords": ["machine learning"],
        "authors": ["John Smith"],
        "quality_score": 0.8
    }

    score = calculate_paper_score(test_paper, test_profile)
    print(f"Paper score: {score:.3f}")

    # Test profile update
    updated = update_profile_with_feedback(
        test_profile,
        [test_paper],
        []
    )
    print(f"Updated version: {updated['version']}")
