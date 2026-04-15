#!/usr/bin/env python3
"""
Profile updater utilities for SciTaste.

This module now supports:
- cosine similarity and safe vector resizing
- topic / author / institution preference decay
- drift-aware interest migration
- unified profile updates after selection feedback
- multi-factor paper scoring with soft must-read bonus
"""

import copy
import hashlib
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

direction_lexicon = __import__("config.direction_lexicon", fromlist=["dummy"])
canonicalize_direction_terms = direction_lexicon.canonicalize_direction_terms
canonicalize_weight_mapping = direction_lexicon.canonicalize_weight_mapping
expand_direction_terms = direction_lexicon.expand_direction_terms
get_direction_entry = direction_lexicon.get_direction_entry
resolve_canonical_direction = direction_lexicon.resolve_canonical_direction


DRIFT_BLEND_WEIGHTS = {
    "stable": {"explicit": 0.40, "long": 0.45, "short": 0.15},
    "shifting": {"explicit": 0.35, "long": 0.25, "short": 0.40},
    "recovered": {"explicit": 0.35, "long": 0.35, "short": 0.30},
}


def _get_env_int(name: str, default: int) -> int:
    raw = str(os.environ.get(name, str(default))).strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return default


def _get_env_float(name: str, default: float) -> float:
    raw = str(os.environ.get(name, str(default))).strip()
    try:
        return float(raw)
    except ValueError:
        return default


def _configured_embedding_dimensions() -> int:
    return _get_env_int("EMBEDDING_DIMENSIONS", 768)


def _drift_config() -> Dict[str, float]:
    return {
        "long_window_size": _get_env_int("SCITASTE_DRIFT_LONG_WINDOW_SIZE", 30),
        "long_window_days": _get_env_int("SCITASTE_DRIFT_LONG_WINDOW_DAYS", 60),
        "short_window_size": _get_env_int("SCITASTE_DRIFT_SHORT_WINDOW_SIZE", 8),
        "short_window_days": _get_env_int("SCITASTE_DRIFT_SHORT_WINDOW_DAYS", 14),
        "drift_threshold": _get_env_float("SCITASTE_DRIFT_THRESHOLD", 0.35),
        "recover_threshold": _get_env_float("SCITASTE_DRIFT_RECOVER_THRESHOLD", 0.20),
        "alpha_base": _get_env_float("SCITASTE_DRIFT_ALPHA_BASE", 0.08),
        "alpha_max": _get_env_float("SCITASTE_DRIFT_ALPHA_MAX", 0.35),
        "topic_decay": _get_env_float("SCITASTE_TOPIC_DECAY", 0.01),
        "author_decay": _get_env_float("SCITASTE_AUTHOR_DECAY", 0.005),
        "institution_decay": _get_env_float("SCITASTE_INSTITUTION_DECAY", 0.005),
        "selected_topic_delta": _get_env_float("SCITASTE_TOPIC_POSITIVE_DELTA", 0.02),
        "skipped_topic_delta": _get_env_float("SCITASTE_TOPIC_NEGATIVE_DELTA", 0.01),
        "author_positive_delta": _get_env_float("SCITASTE_AUTHOR_HEAT_POSITIVE_DELTA", 0.05),
        "institution_positive_delta": _get_env_float("SCITASTE_INSTITUTION_HEAT_POSITIVE_DELTA", 0.05),
    }


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, float(value)))


def _safe_iso_datetime(value: Any, fallback: Optional[datetime] = None) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value.strip():
        cleaned = value.strip().replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(cleaned)
        except ValueError:
            pass
    return fallback or datetime.now()


def _round_mapping(values: Dict[str, float], digits: int = 4) -> Dict[str, float]:
    return {
        str(key): round(float(value), digits)
        for key, value in values.items()
        if float(value) > 0
    }


def build_default_drift_state(now_iso: Optional[str] = None) -> Dict[str, Any]:
    timestamp = now_iso or datetime.now().isoformat()
    return {
        "status": "stable",
        "score": 0.0,
        "detected_at": None,
        "last_updated_at": timestamp,
        "long_term_vector": [],
        "short_term_vector": [],
        "long_term_topics": {},
        "short_term_topics": {},
        "adaptive_alpha": _drift_config()["alpha_base"],
        "top_shift_topics": [],
        "explanation": "近期兴趣稳定，系统继续以长期画像为主。",
    }


def ensure_profile_schema(profile: Optional[Dict[str, Any]], now: Optional[datetime] = None) -> Dict[str, Any]:
    current_time = now or datetime.now()
    now_iso = current_time.isoformat()
    normalized = copy.deepcopy(profile) if profile else {}

    normalized.setdefault("version", "0.1")
    normalized.setdefault("created_at", normalized.get("updated_at", now_iso))
    normalized.setdefault("updated_at", normalized.get("created_at", now_iso))

    for key in (
        "core_directions",
        "methodology_preferences",
        "topic_weights",
        "author_heat",
        "institution_heat",
        "taste_profile",
    ):
        value = normalized.get(key)
        normalized[key] = value if isinstance(value, dict) else {}

    normalized["core_directions"] = canonicalize_weight_mapping(normalized.get("core_directions", {}))
    normalized["topic_weights"] = canonicalize_weight_mapping(normalized.get("topic_weights", {}))

    must_read = normalized.get("must_read")
    normalized["must_read"] = must_read if isinstance(must_read, dict) else {}
    for key in ("authors", "institutions", "keywords"):
        value = normalized["must_read"].get(key)
        normalized["must_read"][key] = value if isinstance(value, list) else []

    for key in ("interest_vector", "reading_history", "behavior_logs"):
        value = normalized.get(key)
        normalized[key] = value if isinstance(value, list) else []

    drift_state = normalized.get("drift_state")
    default_drift_state = build_default_drift_state(now_iso)
    normalized["drift_state"] = drift_state if isinstance(drift_state, dict) else {}
    for key, default_value in default_drift_state.items():
        normalized["drift_state"].setdefault(key, copy.deepcopy(default_value))
    normalized["drift_state"]["long_term_topics"] = canonicalize_weight_mapping(
        normalized["drift_state"].get("long_term_topics", {})
    )
    normalized["drift_state"]["short_term_topics"] = canonicalize_weight_mapping(
        normalized["drift_state"].get("short_term_topics", {})
    )
    normalized["drift_state"]["top_shift_topics"] = canonicalize_direction_terms(
        normalized["drift_state"].get("top_shift_topics", []),
        keep_unknown=True,
    )

    return normalized


def get_drift_blend_weights(status: str) -> Dict[str, float]:
    return copy.deepcopy(DRIFT_BLEND_WEIGHTS.get(status, DRIFT_BLEND_WEIGHTS["stable"]))


def _infer_vector_dimension(*vectors: List[float]) -> int:
    lengths = [len(vector) for vector in vectors if isinstance(vector, list) and vector]
    return max(lengths) if lengths else _configured_embedding_dimensions()


def _resize_vector(vector: List[float], target_dim: int) -> List[float]:
    if target_dim <= 0:
        return []

    values = [float(value) for value in (vector or [])]
    if len(values) == target_dim:
        return values
    if len(values) > target_dim:
        return values[:target_dim]
    return values + [0.0] * (target_dim - len(values))


def _normalize_vector(vector: List[float]) -> List[float]:
    if not vector:
        return []
    array = np.array(vector, dtype=float)
    norm = np.linalg.norm(array)
    if norm <= 0:
        return [0.0] * len(array)
    return (array / norm).tolist()


def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Calculate cosine similarity."""
    target_dim = _infer_vector_dimension(vec1, vec2)
    v1 = np.array(_resize_vector(vec1, target_dim))
    v2 = np.array(_resize_vector(vec2, target_dim))
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
    Update interest vector using EMA.

    Args:
        current_vector: Current interest vector
        selected_vectors: Target vectors to blend in
        alpha: Learning rate

    Returns:
        Updated interest vector
    """
    if not selected_vectors:
        return current_vector

    target_dim = _infer_vector_dimension(current_vector, *selected_vectors)
    resized_selected = [_resize_vector(vector, target_dim) for vector in selected_vectors if vector]
    if not resized_selected:
        return _resize_vector(current_vector, target_dim)

    avg_vector = np.mean(resized_selected, axis=0)
    current = np.array(_resize_vector(current_vector, target_dim))
    new_vector = (1 - alpha) * current + alpha * avg_vector
    return _normalize_vector(new_vector.tolist())


def _normalize_string_list(values: Any) -> List[str]:
    if not values:
        return []
    if isinstance(values, list):
        return [str(value).strip() for value in values if str(value).strip()]
    if isinstance(values, str):
        stripped = values.strip()
        if not stripped:
            return []
        if stripped.startswith("[") and stripped.endswith("]"):
            try:
                parsed = __import__("json").loads(stripped)
            except Exception:
                parsed = None
            if isinstance(parsed, list):
                return [str(value).strip() for value in parsed if str(value).strip()]
        separators = [";", "；", ",", "，", "|"]
        parts = [stripped]
        for separator in separators:
            if separator in stripped:
                parts = [part for chunk in parts for part in chunk.split(separator)]
        return [part.strip() for part in parts if part.strip()]
    return [str(values).strip()]


def _normalize_topic_values(paper: Dict[str, Any]) -> List[str]:
    topic_candidates = _normalize_string_list(paper.get("topics"))
    if not topic_candidates:
        topic_candidates = _normalize_string_list(paper.get("keywords"))
    return canonicalize_direction_terms(topic_candidates, keep_unknown=True)


def _normalize_keywords(paper: Dict[str, Any]) -> List[str]:
    merged_values: List[str] = []
    for key in ("keywords", "topics", "categories"):
        merged_values.extend(_normalize_string_list(paper.get(key)))
    return canonicalize_direction_terms(merged_values, keep_unknown=True)


def _paper_timestamp(paper: Dict[str, Any], now: datetime) -> datetime:
    for key in ("selected_at", "timestamp", "updated_at", "publish_date"):
        value = paper.get(key)
        if value:
            return _safe_iso_datetime(value, fallback=now)
    return now


def _window_papers(
    papers: List[Dict[str, Any]],
    *,
    max_size: int,
    max_days: int,
    now: datetime,
) -> List[Dict[str, Any]]:
    cutoff = now - timedelta(days=max_days)
    recent = [
        paper for paper in papers
        if _paper_timestamp(paper, now) >= cutoff
    ]
    recent.sort(key=lambda paper: _paper_timestamp(paper, now))
    return recent[-max_size:]


def _collect_embeddings(papers: List[Dict[str, Any]], target_dim: int) -> List[List[float]]:
    vectors: List[List[float]] = []
    for paper in papers:
        embedding = paper.get("embedding")
        if not embedding:
            continue
        vectors.append(_resize_vector(embedding, target_dim))
    return vectors


def _average_vector(
    papers: List[Dict[str, Any]],
    *,
    fallback_vector: Optional[List[float]] = None,
) -> List[float]:
    target_dim = _infer_vector_dimension(fallback_vector or [], *[paper.get("embedding", []) for paper in papers])
    embeddings = _collect_embeddings(papers, target_dim)
    if not embeddings:
        return _normalize_vector(_resize_vector(fallback_vector or [], target_dim))
    return _normalize_vector(np.mean(embeddings, axis=0).tolist())


def _topic_distribution(papers: List[Dict[str, Any]]) -> Dict[str, float]:
    topic_counts: Dict[str, float] = {}
    for paper in papers:
        for topic in _normalize_topic_values(paper):
            topic_counts[topic] = topic_counts.get(topic, 0.0) + 1.0
    total = sum(topic_counts.values())
    if total <= 0:
        return {}
    return {topic: count / total for topic, count in topic_counts.items()}


def _js_divergence(dist_a: Dict[str, float], dist_b: Dict[str, float]) -> float:
    if not dist_a and not dist_b:
        return 0.0

    keys = sorted(set(dist_a) | set(dist_b))
    p = np.array([float(dist_a.get(key, 0.0)) for key in keys], dtype=float)
    q = np.array([float(dist_b.get(key, 0.0)) for key in keys], dtype=float)
    p_sum = p.sum()
    q_sum = q.sum()
    if p_sum <= 0 and q_sum <= 0:
        return 0.0
    if p_sum > 0:
        p = p / p_sum
    if q_sum > 0:
        q = q / q_sum
    m = 0.5 * (p + q)

    def _kl_divergence(lhs: np.ndarray, rhs: np.ndarray) -> float:
        mask = (lhs > 0) & (rhs > 0)
        if not np.any(mask):
            return 0.0
        return float(np.sum(lhs[mask] * np.log2(lhs[mask] / rhs[mask])))

    return float(0.5 * _kl_divergence(p, m) + 0.5 * _kl_divergence(q, m))


def _hash_topic_vector(topic: str, target_dim: int) -> List[float]:
    if target_dim <= 0:
        return []
    digest = hashlib.sha256(topic.encode("utf-8")).digest()
    vector: List[float] = []
    for index in range(target_dim):
        byte = digest[index % len(digest)]
        bit = (byte >> (index % 8)) & 1
        vector.append(1.0 if bit else -1.0)
    return _normalize_vector(vector)


def _explicit_prior_vector(profile: Dict[str, Any], target_dim: int) -> List[float]:
    components: List[Tuple[str, float]] = []
    for topic, weight in (profile.get("core_directions") or {}).items():
        if float(weight or 0.0) > 0:
            components.append((str(topic), float(weight)))
    for topic, weight in (profile.get("topic_weights") or {}).items():
        if float(weight or 0.0) > 0:
            components.append((str(topic), float(weight)))

    if not components:
        return _resize_vector(profile.get("interest_vector", []), target_dim)

    accumulator = np.zeros(target_dim, dtype=float)
    for topic, weight in components:
        accumulator += np.array(_hash_topic_vector(topic, target_dim)) * float(weight)
    return _normalize_vector(accumulator.tolist())


def _blend_vectors(vector_weights: List[Tuple[List[float], float]], target_dim: int) -> List[float]:
    accumulator = np.zeros(target_dim, dtype=float)
    total_weight = 0.0
    for vector, weight in vector_weights:
        if not vector or weight <= 0:
            continue
        accumulator += np.array(_resize_vector(vector, target_dim)) * weight
        total_weight += weight
    if total_weight <= 0:
        return [0.0] * target_dim
    return _normalize_vector(accumulator.tolist())


def _days_since(last_updated: Any, now: datetime) -> int:
    last_dt = _safe_iso_datetime(last_updated, fallback=now)
    delta = now - last_dt
    return max(0, int(delta.total_seconds() // 86400))


def apply_time_decay(
    weights: Dict[str, float],
    days_inactive: int,
    decay_rate: float = 0.01,
    minimum_weight: float = 0.1,
) -> Dict[str, float]:
    """
    Apply exponential time decay to scalar weights.

    Args:
        weights: Weight mapping
        days_inactive: Inactive days
        decay_rate: Daily decay rate
        minimum_weight: Floor

    Returns:
        Decayed mapping
    """
    if days_inactive <= 0:
        return {
            topic: float(weight)
            for topic, weight in weights.items()
        }

    decayed: Dict[str, float] = {}
    for topic, weight in weights.items():
        value = float(weight) * ((1 - decay_rate) ** days_inactive)
        decayed[topic] = max(minimum_weight, value)
    return decayed


def _apply_selective_decay(
    weights: Dict[str, float],
    *,
    days_inactive: int,
    decay_rate: float,
    touched_keys: Optional[set] = None,
    minimum_weight: float = 0.1,
    prune_below: Optional[float] = None,
) -> Dict[str, float]:
    touched_keys = touched_keys or set()
    updated: Dict[str, float] = {}
    for key, value in weights.items():
        numeric_value = float(value)
        if key not in touched_keys and days_inactive > 0:
            numeric_value *= (1 - decay_rate) ** days_inactive
        numeric_value = max(minimum_weight, numeric_value)
        if prune_below is not None and numeric_value < prune_below:
            continue
        updated[key] = numeric_value
    return updated


def update_topic_weights(
    current_weights: Dict[str, float],
    selected_papers: List[Dict],
    skipped_papers: List[Dict],
    positive_delta: float = 0.02,
    negative_delta: float = 0.01,
) -> Dict[str, float]:
    """
    Update topic weights based on positive and weak negative feedback.
    """
    weights = {str(topic): float(value) for topic, value in (current_weights or {}).items()}

    for paper in selected_papers:
        for topic in _normalize_topic_values(paper):
            if topic in weights:
                weights[topic] = min(1.0, weights[topic] + positive_delta)
            else:
                weights[topic] = 0.4

    for paper in skipped_papers:
        for topic in _normalize_topic_values(paper):
            if topic in weights:
                weights[topic] = max(0.1, weights[topic] - negative_delta)

    return weights


def _update_heat_map(
    current_heat: Dict[str, float],
    *,
    positive_hits: List[str],
    decay_rate: float,
    days_inactive: int,
    delta: float,
    touched_keys: Optional[set] = None,
) -> Dict[str, float]:
    heat = _apply_selective_decay(
        current_heat or {},
        days_inactive=days_inactive,
        decay_rate=decay_rate,
        touched_keys=touched_keys,
        minimum_weight=0.0,
        prune_below=0.01,
    )
    for key in positive_hits:
        heat[key] = min(1.0, float(heat.get(key, 0.0)) + delta)
    return _round_mapping(heat)


def _top_shift_topics(short_topics: Dict[str, float], long_topics: Dict[str, float], limit: int = 3) -> List[str]:
    deltas = []
    for topic in set(short_topics) | set(long_topics):
        deltas.append(
            (
                abs(float(short_topics.get(topic, 0.0)) - float(long_topics.get(topic, 0.0))),
                topic,
            )
        )
    deltas.sort(key=lambda item: item[0], reverse=True)
    return [topic for score, topic in deltas[:limit] if score > 0]


def _describe_drift_state(status: str, shift_topics: List[str]) -> str:
    if status == "shifting":
        if shift_topics:
            return (
                f"近期在{', '.join(shift_topics)}上的选择显著偏离历史窗口，因此系统提高了短期兴趣权重。"
            )
        return "近期选择与历史窗口出现明显偏移，因此系统提高了短期兴趣权重。"
    if status == "recovered":
        if shift_topics:
            return (
                f"近期在{', '.join(shift_topics)}上的波动已回落，系统开始重新平衡短期兴趣与长期画像。"
            )
        return "近期兴趣波动已回落，系统开始重新平衡短期兴趣与长期画像。"
    return "近期选择与历史窗口基本一致，因此系统继续以长期画像为主。"


def _increment_version(version: str) -> str:
    try:
        major_raw, minor_raw = str(version or "0.1").split(".", 1)
        return f"{int(major_raw)}.{int(minor_raw) + 1}"
    except Exception:
        return "0.1"


def calculate_paper_score(
    paper: Dict,
    profile: Dict,
    weights_config: Dict = None
) -> float:
    """
    Calculate a multi-factor paper score.

    score = w1 * interest_vector_similarity
          + w2 * topic_weight_match
          + w3 * author_institution_heat
          + w4 * quality_signal
          + bonus (soft must_read hit)
    """
    if weights_config is None:
        weights_config = {
            "w1_interest_vector": 0.35,
            "w2_topic_weight": 0.25,
            "w3_author_institution": 0.20,
            "w4_quality_signal": 0.20,
            "bonus_must_read": 0.15,
        }

    interest_sim = cosine_similarity(
        paper.get("embedding", []),
        profile.get("interest_vector", []),
    )

    topic_match = 0.0
    paper_topics = _normalize_topic_values(paper)
    matched_weights = [
        float(profile.get("topic_weights", {}).get(topic, 0.0))
        for topic in paper_topics
        if topic in profile.get("topic_weights", {})
    ]
    if matched_weights:
        topic_match = max(matched_weights)

    author_score = 0.0
    paper_authors = _normalize_string_list(paper.get("authors"))
    if paper_authors:
        author_heat = profile.get("author_heat", {})
        scores = [float(author_heat.get(author, 0.0)) for author in paper_authors if author in author_heat]
        if scores:
            author_score = sum(scores) / len(scores)

    institution_score = 0.0
    paper_institution = str(paper.get("institution", "") or "")
    institution_heat = profile.get("institution_heat", {})
    if paper_institution:
        paper_institution_lower = paper_institution.lower()
        for institution, heat in institution_heat.items():
            if institution and str(institution).lower() in paper_institution_lower:
                institution_score = max(institution_score, float(heat))

    quality_score = float(paper.get("quality_score", 0.5))

    bonus = weights_config.get("bonus_must_read", 0.15) if is_must_read(paper, profile) else 0.0

    score = (
        weights_config.get("w1_interest_vector", 0.35) * interest_sim
        + weights_config.get("w2_topic_weight", 0.25) * topic_match
        + weights_config.get("w3_author_institution", 0.20) * max(author_score, institution_score)
        + weights_config.get("w4_quality_signal", 0.20) * quality_score
        + bonus
    )
    return min(1.0, score)


def get_must_read_matches(paper: Dict, profile: Dict) -> Dict[str, List[str]]:
    """
    Return detailed must-read matches for a paper.
    """
    must_read = profile.get("must_read", {})
    matches = {
        "authors": [],
        "institutions": [],
        "keywords": [],
    }

    must_authors = must_read.get("authors", [])
    paper_authors = _normalize_string_list(paper.get("authors"))
    for author in paper_authors:
        for must_author in must_authors:
            if str(must_author).lower() in author.lower() and must_author not in matches["authors"]:
                matches["authors"].append(must_author)

    must_institutions = must_read.get("institutions", [])
    paper_institution = str(paper.get("institution", "") or "")
    for institution in must_institutions:
        if str(institution).lower() in paper_institution.lower() and institution not in matches["institutions"]:
            matches["institutions"].append(institution)

    must_keywords = must_read.get("keywords", [])
    paper_topics = set(_normalize_topic_values(paper))
    paper_keywords_lower = [keyword.lower() for keyword in _normalize_keywords(paper)]
    for keyword in must_keywords:
        resolved_keyword = resolve_canonical_direction(keyword, include_paper_terms=True)
        canonical_keyword = resolved_keyword["canonical_name"] if resolved_keyword else None
        if canonical_keyword and canonical_keyword in paper_topics and keyword not in matches["keywords"]:
            matches["keywords"].append(keyword)
            continue
        if str(keyword).lower() in paper_keywords_lower and keyword not in matches["keywords"]:
            matches["keywords"].append(keyword)

    return matches


def is_must_read(paper: Dict, profile: Dict) -> bool:
    """
    Check if a paper matches the must-read list.
    """
    matches = get_must_read_matches(paper, profile)
    return any(matches.values())


def detect_new_topics(
    selected_papers: List[Dict],
    existing_topics: List[str],
    threshold: int = 3
) -> Dict[str, float]:
    """
    Detect repeated new topics from selected papers.
    """
    topic_counts: Dict[str, int] = {}
    for paper in selected_papers:
        for topic in _normalize_keywords(paper):
            if topic not in existing_topics:
                topic_counts[topic] = topic_counts.get(topic, 0) + 1

    return {
        topic: 0.4
        for topic, count in topic_counts.items()
        if count >= threshold
    }


def update_profile_with_feedback(
    profile: Dict,
    selected_papers: List[Dict],
    skipped_papers: List[Dict],
    historical_selected_papers: Optional[List[Dict]] = None,
    current_time: Optional[datetime] = None,
) -> Dict:
    """
    Unified drift-aware profile update entry.

    Args:
        profile: Current profile
        selected_papers: Papers selected in this feedback round
        skipped_papers: Papers skipped in this feedback round
        historical_selected_papers: Earlier selected papers used for long/short windows
        current_time: Optional override for tests

    Returns:
        Updated profile
    """
    now = current_time or datetime.now()
    now_iso = now.isoformat()
    config = _drift_config()
    updated = ensure_profile_schema(profile, now=now)

    historical = copy.deepcopy(historical_selected_papers or [])
    combined_selected = historical + [
        {
            **copy.deepcopy(paper),
            "selected_at": paper.get("selected_at") or now_iso,
        }
        for paper in selected_papers
    ]
    combined_selected.sort(key=lambda paper: _paper_timestamp(paper, now))

    short_window = _window_papers(
        combined_selected,
        max_size=int(config["short_window_size"]),
        max_days=int(config["short_window_days"]),
        now=now,
    )
    long_window = _window_papers(
        combined_selected,
        max_size=int(config["long_window_size"]),
        max_days=int(config["long_window_days"]),
        now=now,
    )

    previous_drift_state = ensure_profile_schema({"drift_state": updated.get("drift_state", {})}, now=now)["drift_state"]
    target_dim = _infer_vector_dimension(
        updated.get("interest_vector", []),
        previous_drift_state.get("long_term_vector", []),
        previous_drift_state.get("short_term_vector", []),
        *[paper.get("embedding", []) for paper in combined_selected],
    )

    long_term_vector = _average_vector(long_window, fallback_vector=previous_drift_state.get("long_term_vector", []))
    short_term_vector = _average_vector(short_window, fallback_vector=long_term_vector or previous_drift_state.get("short_term_vector", []))
    long_term_topics = _topic_distribution(long_window)
    short_term_topics = _topic_distribution(short_window)

    enough_for_detection = len(long_window) >= 5 and len(short_window) >= 3
    drift_score = 0.0
    embedding_drift = 0.0
    topic_drift = 0.0
    previous_status = str(previous_drift_state.get("status", "stable"))
    drift_status = "stable"
    detected_at = previous_drift_state.get("detected_at")

    if enough_for_detection:
        embedding_drift = _clamp(1.0 - cosine_similarity(short_term_vector, long_term_vector), 0.0, 1.0)
        topic_drift = _clamp(_js_divergence(short_term_topics, long_term_topics), 0.0, 1.0)
        drift_score = round(0.6 * embedding_drift + 0.4 * topic_drift, 4)

        if drift_score >= config["drift_threshold"]:
            drift_status = "shifting"
            if previous_status != "shifting":
                detected_at = now_iso
        elif drift_score <= config["recover_threshold"]:
            if previous_status == "shifting":
                drift_status = "recovered"
            elif previous_status == "recovered":
                drift_status = "stable"
            else:
                drift_status = "stable"
        else:
            drift_status = previous_status if previous_status in DRIFT_BLEND_WEIGHTS else "stable"
    elif previous_status == "recovered":
        drift_status = "stable"

    drift_intensity = _clamp(
        (drift_score - config["drift_threshold"]) / max(1e-6, 1.0 - config["drift_threshold"]),
        0.0,
        1.0,
    )
    adaptive_alpha = round(
        float(config["alpha_base"]) + drift_intensity * (float(config["alpha_max"]) - float(config["alpha_base"])),
        4,
    )

    explicit_prior_vector = _explicit_prior_vector(updated, target_dim)
    blend_weights = get_drift_blend_weights(drift_status)
    fused_target_vector = _blend_vectors(
        [
            (explicit_prior_vector, blend_weights["explicit"]),
            (long_term_vector, blend_weights["long"]),
            (short_term_vector, blend_weights["short"]),
        ],
        target_dim,
    )
    if not any(fused_target_vector):
        fused_target_vector = short_term_vector or long_term_vector or explicit_prior_vector or _resize_vector(updated.get("interest_vector", []), target_dim)

    updated["interest_vector"] = update_interest_vector(
        updated.get("interest_vector", []),
        [fused_target_vector],
        alpha=adaptive_alpha,
    )

    recent_short_topics = set()
    for paper in short_window:
        recent_short_topics.update(_normalize_topic_values(paper))

    last_updated_at = updated.get("updated_at") or previous_drift_state.get("last_updated_at") or now_iso
    inactivity_days = _days_since(last_updated_at, now)

    decayed_topic_weights = _apply_selective_decay(
        updated.get("topic_weights", {}),
        days_inactive=inactivity_days,
        decay_rate=float(config["topic_decay"]),
        touched_keys=recent_short_topics,
        minimum_weight=0.1,
    )
    updated["topic_weights"] = update_topic_weights(
        decayed_topic_weights,
        selected_papers,
        skipped_papers,
        positive_delta=float(config["selected_topic_delta"]),
        negative_delta=float(config["skipped_topic_delta"]),
    )

    selected_authors: List[str] = []
    selected_institutions: List[str] = []
    recent_short_authors: set = set()
    recent_short_institutions: set = set()

    for paper in short_window:
        recent_short_authors.update(_normalize_string_list(paper.get("authors")))
        institution = str(paper.get("institution", "") or "").strip()
        if institution:
            recent_short_institutions.add(institution)

    for paper in selected_papers:
        selected_authors.extend(_normalize_string_list(paper.get("authors")))
        institution = str(paper.get("institution", "") or "").strip()
        if institution:
            selected_institutions.append(institution)

    updated["author_heat"] = _update_heat_map(
        updated.get("author_heat", {}),
        positive_hits=selected_authors,
        decay_rate=float(config["author_decay"]),
        days_inactive=inactivity_days,
        delta=float(config["author_positive_delta"]),
        touched_keys=recent_short_authors,
    )
    updated["institution_heat"] = _update_heat_map(
        updated.get("institution_heat", {}),
        positive_hits=selected_institutions,
        decay_rate=float(config["institution_decay"]),
        days_inactive=inactivity_days,
        delta=float(config["institution_positive_delta"]),
        touched_keys=recent_short_institutions,
    )

    reading_history = list(updated.get("reading_history", []))
    for paper in selected_papers:
        reading_history.append(
            {
                "arxiv_id": paper.get("arxiv_id"),
                "paper_id": paper.get("id"),
                "selected_at": now_iso,
                "action": "selected",
            }
        )
    updated["reading_history"] = reading_history[-200:]

    shift_topics = _top_shift_topics(short_term_topics, long_term_topics)
    explanation = _describe_drift_state(drift_status, shift_topics)

    updated["drift_state"] = {
        "status": drift_status,
        "score": round(float(drift_score), 4),
        "detected_at": detected_at if drift_status in {"shifting", "recovered"} else previous_drift_state.get("detected_at"),
        "last_updated_at": now_iso,
        "long_term_vector": _resize_vector(long_term_vector, target_dim),
        "short_term_vector": _resize_vector(short_term_vector, target_dim),
        "long_term_topics": _round_mapping(long_term_topics),
        "short_term_topics": _round_mapping(short_term_topics),
        "adaptive_alpha": adaptive_alpha,
        "top_shift_topics": shift_topics,
        "explanation": explanation,
    }

    updated["updated_at"] = now_iso
    updated["version"] = _increment_version(updated.get("version", "0.1"))
    return updated


if __name__ == "__main__":
    test_profile = {
        "interest_vector": [0.5, 0.3, 0.2],
        "topic_weights": {"machine learning": 0.8, "biology": 0.6},
        "author_heat": {"John Smith": 0.7},
        "must_read": {"authors": [], "institutions": [], "keywords": []},
    }

    test_paper = {
        "embedding": [0.4, 0.4, 0.2],
        "keywords": ["machine learning"],
        "authors": ["John Smith"],
        "quality_score": 0.8,
    }

    score = calculate_paper_score(test_paper, test_profile)
    print(f"Paper score: {score:.3f}")

    updated = update_profile_with_feedback(
        test_profile,
        [test_paper],
        [],
    )
    print(f"Updated version: {updated['version']}")
