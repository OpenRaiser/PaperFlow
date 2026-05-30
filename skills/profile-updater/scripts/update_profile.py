#!/usr/bin/env python3
"""
Profile updater utilities for PaperFlow.

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
import re
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

direction_lexicon = __import__("config.direction_lexicon", fromlist=["dummy"])
canonicalize_direction_terms = direction_lexicon.canonicalize_direction_terms
canonicalize_weight_mapping = direction_lexicon.canonicalize_weight_mapping
expand_direction_terms = direction_lexicon.expand_direction_terms
get_direction_entry = direction_lexicon.get_direction_entry
get_lexicon_keywords = direction_lexicon.get_lexicon_keywords
resolve_canonical_direction = direction_lexicon.resolve_canonical_direction
drift_engine = __import__("scripts.drift_engine", fromlist=["dummy"])


DRIFT_BLEND_WEIGHTS = {
    "stable": {"explicit": 0.40, "long": 0.45, "short": 0.15},
    "observing": {"explicit": 0.38, "long": 0.37, "short": 0.25},
    "shifting": {"explicit": 0.35, "long": 0.25, "short": 0.40},
    "committed_shift": {"explicit": 0.30, "long": 0.22, "short": 0.48},
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
        "long_window_size": _get_env_int("PAPERFLOW_DRIFT_LONG_WINDOW_SIZE", 30),
        "long_window_days": _get_env_int("PAPERFLOW_DRIFT_LONG_WINDOW_DAYS", 60),
        "short_window_size": _get_env_int("PAPERFLOW_DRIFT_SHORT_WINDOW_SIZE", 8),
        "short_window_days": _get_env_int("PAPERFLOW_DRIFT_SHORT_WINDOW_DAYS", 14),
        "drift_threshold": _get_env_float("PAPERFLOW_DRIFT_THRESHOLD", 0.35),
        "recover_threshold": _get_env_float("PAPERFLOW_DRIFT_RECOVER_THRESHOLD", 0.20),
        "alpha_base": _get_env_float("PAPERFLOW_DRIFT_ALPHA_BASE", 0.08),
        "alpha_max": _get_env_float("PAPERFLOW_DRIFT_ALPHA_MAX", 0.35),
        "topic_decay": _get_env_float("PAPERFLOW_TOPIC_DECAY", 0.01),
        "author_decay": _get_env_float("PAPERFLOW_AUTHOR_DECAY", 0.005),
        "institution_decay": _get_env_float("PAPERFLOW_INSTITUTION_DECAY", 0.005),
        "selected_topic_delta": _get_env_float("PAPERFLOW_TOPIC_POSITIVE_DELTA", 0.02),
        "skipped_topic_delta": _get_env_float("PAPERFLOW_TOPIC_NEGATIVE_DELTA", 0.01),
        "author_positive_delta": _get_env_float("PAPERFLOW_AUTHOR_HEAT_POSITIVE_DELTA", 0.05),
        "institution_positive_delta": _get_env_float("PAPERFLOW_INSTITUTION_HEAT_POSITIVE_DELTA", 0.05),
        "reading_signal_window_days": _get_env_int("PAPERFLOW_READING_SIGNAL_WINDOW_DAYS", 21),
        "reading_signal_activation_count": _get_env_int("PAPERFLOW_READING_SIGNAL_ACTIVATION_COUNT", 2),
        "reading_signal_topic_seed_weak": _get_env_float("PAPERFLOW_READING_SIGNAL_TOPIC_SEED_WEAK", 0.18),
        "reading_signal_topic_seed_strong": _get_env_float("PAPERFLOW_READING_SIGNAL_TOPIC_SEED_STRONG", 0.38),
        "reading_signal_topic_delta_weak": _get_env_float("PAPERFLOW_READING_SIGNAL_TOPIC_DELTA_WEAK", 0.03),
        "reading_signal_topic_delta_strong": _get_env_float("PAPERFLOW_READING_SIGNAL_TOPIC_DELTA_STRONG", 0.08),
        "reading_signal_core_seed_strong": _get_env_float("PAPERFLOW_READING_SIGNAL_CORE_SEED_STRONG", 0.45),
        "reading_signal_core_delta_strong": _get_env_float("PAPERFLOW_READING_SIGNAL_CORE_DELTA_STRONG", 0.08),
        "reading_signal_short_term_base": _get_env_float("PAPERFLOW_READING_SIGNAL_SHORT_TERM_BASE", 0.35),
        "reading_signal_short_term_step": _get_env_float("PAPERFLOW_READING_SIGNAL_SHORT_TERM_STEP", 0.18),
        "reading_signal_short_term_strong_bonus": _get_env_float("PAPERFLOW_READING_SIGNAL_SHORT_TERM_STRONG_BONUS", 0.22),
        "anchor_user_probability": _get_env_float("PAPERFLOW_ANCHOR_DRIFT_PROBABILITY", 0.5),
        "real_decay_observing_days": _get_env_int("PAPERFLOW_REAL_DECAY_OBSERVING_DAYS", 7),
        "real_decay_strong_days": _get_env_int("PAPERFLOW_REAL_DECAY_STRONG_DAYS", 15),
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
        "drift_enabled": None,
        "hidden_anchor": None,
        "hidden_anchor_source": None,
        "intent_score": 0.0,
        "anchor_topic": None,
        "anchor_topics": [],
        "anchor_source": None,
        "anchor_confidence": 0.0,
        "anchor_progress": 0.0,
        "anchor_set_date": None,
        "commitment_days_remaining": 0,
        "signal_window": [],
        "episode_index": 0,
        "completed_drift_cycles": 0,
        "max_drift_cycles": None,
        "manual_suppressed_topics": [],
        "explanation": "近期兴趣稳定，系统继续以长期画像为主。",
    }


def build_default_reading_signal_state() -> Dict[str, Any]:
    return {
        "recent_topics": {},
        "short_term_topics": {},
        "last_signal_at": None,
        "last_explicit_signal_at": None,
        "last_signal": {
            "timestamp": None,
            "topics": [],
            "activated_topics": [],
            "strength": "",
            "source_type": "",
            "source_key": "",
            "explicit_note": "",
        },
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
    normalized["drift_state"]["hidden_anchor"] = next(
        iter(canonicalize_direction_terms([normalized["drift_state"].get("hidden_anchor")], keep_unknown=True)),
        None,
    )
    normalized["drift_state"]["anchor_topic"] = next(
        iter(canonicalize_direction_terms([normalized["drift_state"].get("anchor_topic")], keep_unknown=True)),
        None,
    )
    normalized["drift_state"]["anchor_topics"] = canonicalize_direction_terms(
        normalized["drift_state"].get("anchor_topics", []),
        keep_unknown=True,
    )
    normalized["drift_state"]["manual_suppressed_topics"] = canonicalize_direction_terms(
        normalized["drift_state"].get("manual_suppressed_topics", []),
        keep_unknown=True,
    )

    reading_signal_state = normalized.get("reading_signal_state")
    default_reading_signal_state = build_default_reading_signal_state()
    normalized["reading_signal_state"] = (
        copy.deepcopy(reading_signal_state)
        if isinstance(reading_signal_state, dict)
        else copy.deepcopy(default_reading_signal_state)
    )
    for key, default_value in default_reading_signal_state.items():
        normalized["reading_signal_state"].setdefault(key, copy.deepcopy(default_value))

    raw_recent_topics = normalized["reading_signal_state"].get("recent_topics")
    normalized_recent_topics: Dict[str, Dict[str, Any]] = {}
    if isinstance(raw_recent_topics, dict):
        for topic, payload in raw_recent_topics.items():
            canonical_topics = canonicalize_direction_terms([topic], keep_unknown=False)
            if not canonical_topics or not isinstance(payload, dict):
                continue
            canonical_topic = canonical_topics[0]
            normalized_recent_topics[canonical_topic] = {
                "count": max(0, int(payload.get("count", 0) or 0)),
                "strong_count": max(0, int(payload.get("strong_count", 0) or 0)),
                "last_seen_at": str(payload.get("last_seen_at") or ""),
            }
    normalized["reading_signal_state"]["recent_topics"] = normalized_recent_topics
    normalized["reading_signal_state"]["short_term_topics"] = canonicalize_weight_mapping(
        normalized["reading_signal_state"].get("short_term_topics", {})
    )

    last_signal = normalized["reading_signal_state"].get("last_signal")
    normalized["reading_signal_state"]["last_signal"] = (
        copy.deepcopy(last_signal)
        if isinstance(last_signal, dict)
        else copy.deepcopy(default_reading_signal_state["last_signal"])
    )
    normalized["reading_signal_state"]["last_signal"]["topics"] = canonicalize_direction_terms(
        normalized["reading_signal_state"]["last_signal"].get("topics", []),
        keep_unknown=False,
    )
    normalized["reading_signal_state"]["last_signal"]["activated_topics"] = canonicalize_direction_terms(
        normalized["reading_signal_state"]["last_signal"].get("activated_topics", []),
        keep_unknown=False,
    )
    for key in ("strength", "source_type", "source_key", "explicit_note", "timestamp"):
        normalized["reading_signal_state"]["last_signal"][key] = str(
            normalized["reading_signal_state"]["last_signal"].get(key) or ""
        )

    return normalized


def get_drift_blend_weights(status: str) -> Dict[str, float]:
    return copy.deepcopy(DRIFT_BLEND_WEIGHTS.get(status, DRIFT_BLEND_WEIGHTS["stable"]))


def _profile_has_anchor_plan(profile: Dict[str, Any]) -> bool:
    shift_topics = canonicalize_direction_terms(
        list((profile.get("drift_plan", {}) or {}).get("shift_topics", []) or []),
        keep_unknown=True,
    )
    return bool(shift_topics)


def _paper_matches_anchor_topic(paper: Dict[str, Any], topic: Optional[str]) -> bool:
    topic_text = str(topic or "").strip()
    if not topic_text:
        return False
    paper_topics = _normalize_keywords(paper)
    if topic_text in paper_topics:
        return True
    match_terms = set(drift_engine._direction_match_terms(topic_text))
    title = str(paper.get("title") or "").lower()
    abstract = str(paper.get("abstract") or "").lower()
    text = f"{title} {abstract}"
    return any(term in text for term in match_terms)


def get_anchor_behavior(profile: Dict[str, Any]) -> Dict[str, Any]:
    drift_state = ensure_profile_schema({"drift_state": (profile or {}).get("drift_state", {})})["drift_state"]
    strategy_mode = str(drift_state.get("strategy_mode") or drift_engine.STRATEGY_REAL_USER)
    target_topic = None
    score_bonus = 0.0
    category_bonus = 0.0
    suppression_penalty = 0.0
    suppressed_topics = canonicalize_direction_terms(drift_state.get("suppressed_topics", []), keep_unknown=True)
    manual_suppressed_topics = canonicalize_direction_terms(drift_state.get("manual_suppressed_topics", []), keep_unknown=True)
    suppressed_topics = canonicalize_direction_terms(suppressed_topics + manual_suppressed_topics, keep_unknown=True)
    if not suppressed_topics and (drift_state.get("drift_enabled") or drift_state.get("anchor_topic")):
        suppressed_topics = canonicalize_direction_terms(
            list(((profile or {}).get("drift_plan", {}) or {}).get("downweight_topics", []) or []),
            keep_unknown=True,
        )

    if drift_state.get("anchor_topic"):
        target_topic = str(drift_state.get("anchor_topic") or "").strip()
        progress = float(drift_state.get("anchor_progress", 0.0) or 0.0)
        if int(drift_state.get("commitment_days_remaining", 0) or 0) > 0:
            if strategy_mode == drift_engine.STRATEGY_REAL_USER:
                score_bonus = 0.08 + min(0.04, progress * 0.04)
                category_bonus = 0.04
                suppression_penalty = 0.10
            else:
                score_bonus = 0.16 + min(0.08, progress * 0.08)
                category_bonus = 0.10
                suppression_penalty = 0.28
        else:
            if strategy_mode == drift_engine.STRATEGY_REAL_USER:
                score_bonus = 0.05 + min(0.03, progress * 0.03)
                category_bonus = 0.02
                suppression_penalty = 0.06
            else:
                score_bonus = 0.10 + min(0.05, progress * 0.05)
                category_bonus = 0.06
                suppression_penalty = 0.18
    elif drift_state.get("drift_enabled") and drift_state.get("hidden_anchor"):
        target_topic = str(drift_state.get("hidden_anchor") or "").strip()
        if drift_state.get("status") == "observing":
            if strategy_mode == drift_engine.STRATEGY_REAL_USER:
                score_bonus = 0.03
                category_bonus = 0.01
                suppression_penalty = 0.0
            else:
                score_bonus = 0.08
                category_bonus = 0.04
                suppression_penalty = 0.12
        else:
            if strategy_mode == drift_engine.STRATEGY_REAL_USER:
                score_bonus = 0.02
                category_bonus = 0.01
                suppression_penalty = 0.0
            else:
                score_bonus = 0.05
                category_bonus = 0.02
                suppression_penalty = 0.08

    return {
        "target_topic": target_topic or None,
        "score_bonus": round(score_bonus, 4),
        "category_bonus": round(category_bonus, 4),
        "suppressed_topics": suppressed_topics,
        "suppression_penalty": round(max(suppression_penalty, 0.22 if manual_suppressed_topics else suppression_penalty), 4),
    }


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


def _normalize_match_text(values: Any) -> str:
    if isinstance(values, (list, tuple, set)):
        parts: List[str] = []
        for value in values:
            parts.extend(_normalize_string_list(value))
    else:
        parts = _normalize_string_list(values)
    text = " ".join(parts).lower().replace("&", " and ")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _contains_match_term(text: str, term: Any) -> bool:
    normalized_term = _normalize_match_text(term)
    if not normalized_term or not text:
        return False
    return f" {normalized_term} " in f" {text} "


@lru_cache(maxsize=1024)
def _must_read_keyword_terms(keyword: str) -> Tuple[str, ...]:
    candidate_terms: List[Any] = [keyword]
    resolved_keyword = resolve_canonical_direction(keyword, include_paper_terms=True)
    canonical_keyword = resolved_keyword["canonical_name"] if resolved_keyword else None
    expanded = expand_direction_terms([keyword])
    expanded_entry = expanded.get(canonical_keyword) if canonical_keyword else None
    if expanded_entry:
        candidate_terms.extend(
            [
                expanded_entry.get("canonical_name"),
                expanded_entry.get("name"),
                expanded_entry.get("name_cn"),
            ]
        )
    normalized_terms = []
    seen = set()
    for term in candidate_terms:
        normalized = _normalize_match_text(term)
        if normalized and normalized not in seen:
            normalized_terms.append(normalized)
            seen.add(normalized)
    return tuple(normalized_terms)


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


def _latest_topic_activity_days(
    reading_history: List[Dict[str, Any]],
    now: datetime,
) -> Dict[str, int]:
    latest_seen: Dict[str, datetime] = {}
    for entry in reading_history or []:
        if str(entry.get("action") or "").strip().lower() != "selected":
            continue
        entry_time = _safe_iso_datetime(entry.get("selected_at"), fallback=now)
        entry_topics = canonicalize_direction_terms(entry.get("topics", []), keep_unknown=True)
        for topic in entry_topics:
            existing = latest_seen.get(topic)
            if existing is None or entry_time > existing:
                latest_seen[topic] = entry_time

    return {
        topic: max(0, int((now - seen_at).total_seconds() // 86400))
        for topic, seen_at in latest_seen.items()
    }


def _apply_real_user_inactivity_decay(profile: Dict[str, Any], *, now: datetime) -> Dict[str, Any]:
    updated = copy.deepcopy(profile)
    drift_state = updated.get("drift_state", {}) or {}
    strategy_mode = str(drift_state.get("strategy_mode") or drift_engine.STRATEGY_REAL_USER)
    if strategy_mode != drift_engine.STRATEGY_REAL_USER:
        return updated

    config = _drift_config()
    observing_days = int(config["real_decay_observing_days"])
    strong_days = int(config["real_decay_strong_days"])
    reading_history = list(updated.get("reading_history", []) or [])
    activity_days = _latest_topic_activity_days(reading_history, now)

    protected_topics = set()
    if drift_state.get("hidden_anchor"):
        protected_topics.add(str(drift_state.get("hidden_anchor")).strip())
    if drift_state.get("anchor_topic"):
        protected_topics.add(str(drift_state.get("anchor_topic")).strip())

    core_directions = canonicalize_weight_mapping(updated.get("core_directions", {}))
    topic_weights = canonicalize_weight_mapping(updated.get("topic_weights", {}))
    must_read = copy.deepcopy(updated.get("must_read", {}) or {})
    must_keywords = canonicalize_direction_terms(must_read.get("keywords", []), keep_unknown=True)

    for topic in list(core_directions.keys()):
        if topic in protected_topics:
            continue
        inactive_days = activity_days.get(topic, strong_days + 1)
        if inactive_days >= strong_days:
            core_directions[topic] = round(max(0.10, float(core_directions.get(topic, 0.0)) - 0.20), 4)
            topic_weights[topic] = round(max(0.10, float(topic_weights.get(topic, 0.0)) - 0.20), 4)
        elif inactive_days >= observing_days:
            core_directions[topic] = round(max(0.10, float(core_directions.get(topic, 0.0)) - 0.08), 4)
            topic_weights[topic] = round(max(0.10, float(topic_weights.get(topic, 0.0)) - 0.08), 4)

    trimmed_keywords = []
    for keyword in must_keywords:
        if keyword in protected_topics:
            trimmed_keywords.append(keyword)
            continue
        inactive_days = activity_days.get(keyword, strong_days + 1)
        if inactive_days < strong_days:
            trimmed_keywords.append(keyword)

    updated["core_directions"] = canonicalize_weight_mapping(core_directions)
    updated["topic_weights"] = canonicalize_weight_mapping(topic_weights)
    must_read["keywords"] = trimmed_keywords
    updated["must_read"] = must_read
    return updated


def infer_reading_signal_topics(
    paper: Optional[Dict[str, Any]] = None,
    parsed_pdf: Optional[Dict[str, Any]] = None,
    *,
    max_topics: int = 6,
) -> List[str]:
    """Infer stable canonical topics from a direct-upload reading signal."""
    candidates: List[str] = []
    paper = paper or {}
    parsed_pdf = parsed_pdf or {}

    for key in ("topics", "keywords", "categories"):
        candidates.extend(_normalize_string_list(paper.get(key)))
    candidates.extend(_normalize_string_list(parsed_pdf.get("inferred_topics")))

    for direction in parsed_pdf.get("inferred_directions", []) or []:
        if not isinstance(direction, dict):
            continue
        candidates.append(direction.get("canonical_name") or direction.get("name"))

    canonical_topics = canonicalize_direction_terms(candidates, keep_unknown=False)
    if canonical_topics:
        return canonical_topics[:max_topics]

    # Fallback: scan title/abstract/full-text snippets against the shared lexicon.
    text_parts = [
        str(paper.get("title") or ""),
        str(paper.get("abstract") or ""),
        str(parsed_pdf.get("abstract") or ""),
        str(parsed_pdf.get("full_text") or "")[:4000],
    ]
    probe_text = " ".join(part for part in text_parts if part).lower()
    if not probe_text:
        return []

    inferred: List[str] = []
    for canonical_name, keywords in get_lexicon_keywords().items():
        for keyword in keywords:
            keyword_text = str(keyword or "").strip().lower()
            if keyword_text and keyword_text in probe_text:
                inferred.append(canonical_name)
                break

    return canonicalize_direction_terms(inferred, keep_unknown=False)[:max_topics]


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
    if status == "observing":
        if shift_topics:
            return f"系统已观察到你在{', '.join(shift_topics)}上出现连续新信号，正在等待更多证据来确认是否形成稳定迁移。"
        return "系统已观察到连续的新兴趣信号，正在等待更多证据来确认是否形成稳定迁移。"
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


def _bump_topic_weight(
    current_weights: Dict[str, float],
    topic: str,
    *,
    delta: float,
    seed_weight: float,
) -> Dict[str, float]:
    updated = {str(key): float(value) for key, value in (current_weights or {}).items()}
    existing = float(updated.get(topic, 0.0) or 0.0)
    if existing > 0:
        updated[topic] = min(1.0, existing + float(delta))
    else:
        updated[topic] = min(1.0, float(seed_weight))
    return _round_mapping(updated)


def update_profile_with_reading_signal(
    profile: Dict,
    *,
    paper: Optional[Dict[str, Any]] = None,
    parsed_pdf: Optional[Dict[str, Any]] = None,
    signal_topics: Optional[List[str]] = None,
    signal_strength: str = "weak",
    explicit_text: str = "",
    current_time: Optional[datetime] = None,
    source_type: str = "",
    source_key: str = "",
) -> Dict[str, Any]:
    """
    Apply a conservative reading-side interest signal without touching drift status.

    Rules:
    - single upload -> weak positive signal only
    - repeated same-topic uploads/readings -> activate upload short-term interests
    - explicit phrasing after upload -> strong signal for the same topics
    """
    now = current_time or datetime.now()
    now_iso = now.isoformat()
    config = _drift_config()
    updated = ensure_profile_schema(profile, now=now)

    strength = "strong" if str(signal_strength or "").strip().lower() == "strong" or explicit_text.strip() else "weak"
    topics = canonicalize_direction_terms(
        signal_topics or infer_reading_signal_topics(paper=paper, parsed_pdf=parsed_pdf),
        keep_unknown=False,
    )
    if not topics:
        return updated

    state = copy.deepcopy(updated.get("reading_signal_state") or build_default_reading_signal_state())
    recent_topics: Dict[str, Dict[str, Any]] = {}
    cutoff = now - timedelta(days=int(config["reading_signal_window_days"]))

    for topic, payload in (state.get("recent_topics") or {}).items():
        if not isinstance(payload, dict):
            continue
        last_seen = _safe_iso_datetime(payload.get("last_seen_at"), fallback=cutoff - timedelta(days=1))
        if last_seen < cutoff:
            continue
        canonical_topics = canonicalize_direction_terms([topic], keep_unknown=False)
        if not canonical_topics:
            continue
        canonical_topic = canonical_topics[0]
        recent_topics[canonical_topic] = {
            "count": max(0, int(payload.get("count", 0) or 0)),
            "strong_count": max(0, int(payload.get("strong_count", 0) or 0)),
            "last_seen_at": str(payload.get("last_seen_at") or ""),
        }

    activated_topics: Dict[str, float] = {}
    for topic in topics:
        payload = recent_topics.get(
            topic,
            {"count": 0, "strong_count": 0, "last_seen_at": now_iso},
        )
        payload["count"] = int(payload.get("count", 0) or 0) + 1
        if strength == "strong":
            payload["strong_count"] = int(payload.get("strong_count", 0) or 0) + 1
        payload["last_seen_at"] = now_iso
        recent_topics[topic] = payload

        updated["topic_weights"] = _bump_topic_weight(
            updated.get("topic_weights", {}),
            topic,
            delta=float(
                config["reading_signal_topic_delta_strong"]
                if strength == "strong"
                else config["reading_signal_topic_delta_weak"]
            ),
            seed_weight=float(
                config["reading_signal_topic_seed_strong"]
                if strength == "strong"
                else config["reading_signal_topic_seed_weak"]
            ),
        )

        if strength == "strong":
            existing_core = float(updated.get("core_directions", {}).get(topic, 0.0) or 0.0)
            core_seed = float(config["reading_signal_core_seed_strong"])
            core_delta = float(config["reading_signal_core_delta_strong"])
            updated["core_directions"][topic] = round(
                min(1.0, max(core_seed, existing_core + core_delta if existing_core > 0 else core_seed)),
                4,
            )

    activation_count = int(config["reading_signal_activation_count"])
    short_term_topics: Dict[str, float] = {}
    for topic, payload in recent_topics.items():
        count = int(payload.get("count", 0) or 0)
        strong_count = int(payload.get("strong_count", 0) or 0)
        if count < activation_count and strong_count <= 0:
            continue

        strength_score = float(config["reading_signal_short_term_base"])
        strength_score += max(0, count - activation_count) * float(config["reading_signal_short_term_step"])
        strength_score += strong_count * float(config["reading_signal_short_term_strong_bonus"])
        short_term_topics[topic] = round(min(1.0, strength_score), 4)
        if topic in topics:
            activated_topics[topic] = short_term_topics[topic]

    state["recent_topics"] = recent_topics
    state["short_term_topics"] = _round_mapping(short_term_topics)
    state["last_signal_at"] = now_iso
    if strength == "strong":
        state["last_explicit_signal_at"] = now_iso
    state["last_signal"] = {
        "timestamp": now_iso,
        "topics": topics,
        "activated_topics": list(activated_topics.keys()),
        "strength": strength,
        "source_type": str(source_type or ""),
        "source_key": str(source_key or ""),
        "explicit_note": str(explicit_text or "").strip(),
    }
    updated["reading_signal_state"] = state

    reading_history = list(updated.get("reading_history", []))
    reading_history.append(
        {
            "paper_id": (paper or {}).get("id"),
            "arxiv_id": (paper or {}).get("arxiv_id"),
            "selected_at": now_iso,
            "action": "reading_signal_strong" if strength == "strong" else "reading_signal_weak",
            "topics": topics,
            "source_type": str(source_type or ""),
        }
    )
    updated["reading_history"] = reading_history[-200:]

    updated["updated_at"] = now_iso
    updated["version"] = _increment_version(updated.get("version", "0.1"))
    return updated


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
    anchor_behavior = get_anchor_behavior(profile)
    anchor_bonus = 0.0
    if anchor_behavior["target_topic"] and _paper_matches_anchor_topic(paper, anchor_behavior["target_topic"]):
        anchor_bonus = float(anchor_behavior["score_bonus"])
    suppression_penalty = 0.0
    if anchor_behavior["suppressed_topics"]:
        suppressed_hit = any(_paper_matches_anchor_topic(paper, topic) for topic in anchor_behavior["suppressed_topics"])
        if suppressed_hit and not (anchor_behavior["target_topic"] and _paper_matches_anchor_topic(paper, anchor_behavior["target_topic"])):
            suppression_penalty = float(anchor_behavior["suppression_penalty"])

    bonus = weights_config.get("bonus_must_read", 0.15) if is_must_read(paper, profile) else 0.0

    score = (
        weights_config.get("w1_interest_vector", 0.35) * interest_sim
        + weights_config.get("w2_topic_weight", 0.25) * topic_match
        + weights_config.get("w3_author_institution", 0.20) * max(author_score, institution_score)
        + weights_config.get("w4_quality_signal", 0.20) * quality_score
        + bonus
        + anchor_bonus
        - suppression_penalty
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
            if _contains_match_term(_normalize_match_text(author), must_author) and must_author not in matches["authors"]:
                matches["authors"].append(must_author)

    must_institutions = must_read.get("institutions", [])
    paper_institution_values: List[Any] = []
    paper_institution_values.extend(_normalize_string_list(paper.get("institution")))
    paper_institution_values.extend(_normalize_string_list(paper.get("institutions")))
    paper_institution_values.extend(_normalize_string_list(paper.get("affiliations")))
    paper_institution = _normalize_match_text(paper_institution_values)
    for institution in must_institutions:
        if _contains_match_term(paper_institution, institution) and institution not in matches["institutions"]:
            matches["institutions"].append(institution)

    must_keywords = must_read.get("keywords", [])
    paper_text = _normalize_match_text(
        [
            paper.get("title"),
            paper.get("abstract"),
            paper.get("venue"),
            paper.get("keywords"),
            paper.get("topics"),
            paper.get("categories"),
        ]
    )
    paper_topics: Optional[set] = None
    paper_keywords_lower: Optional[List[str]] = None
    for keyword in must_keywords:
        for term in _must_read_keyword_terms(str(keyword)):
            if f" {term} " in f" {paper_text} ":
                if keyword not in matches["keywords"]:
                    matches["keywords"].append(keyword)
                break
        if keyword in matches["keywords"]:
            continue

        if paper.get("topics") or paper.get("keywords"):
            if paper_topics is None:
                paper_topics = set(_normalize_topic_values(paper))
            if paper_keywords_lower is None:
                paper_keywords_lower = [value.lower() for value in _normalize_keywords(paper)]
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
    feedback_strength_multiplier: float = 1.0,
    apply_anchor_drift: bool = True,
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
    strength_multiplier = _clamp(float(feedback_strength_multiplier or 1.0), 0.5, 1.5)
    adaptive_alpha = round(_clamp(adaptive_alpha * strength_multiplier, 0.02, float(config["alpha_max"])), 4)

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
        positive_delta=float(config["selected_topic_delta"]) * strength_multiplier,
        negative_delta=float(config["skipped_topic_delta"]) * strength_multiplier,
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
        delta=float(config["author_positive_delta"]) * strength_multiplier,
        touched_keys=recent_short_authors,
    )
    updated["institution_heat"] = _update_heat_map(
        updated.get("institution_heat", {}),
        positive_hits=selected_institutions,
        decay_rate=float(config["institution_decay"]),
        days_inactive=inactivity_days,
        delta=float(config["institution_positive_delta"]) * strength_multiplier,
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
    updated = _apply_real_user_inactivity_decay(updated, now=now)

    anchor_state = copy.deepcopy(previous_drift_state)
    if apply_anchor_drift and _profile_has_anchor_plan(updated):
        anchor_result_profile = copy.deepcopy(updated)
        anchor_result_profile["drift_state"] = copy.deepcopy(previous_drift_state)
        engine = drift_engine.DriftEngine(drift_engine.load_default_checkfiles())
        anchor_result_profile, _anchor_event = engine.advance_profile_drift(
            anchor_result_profile,
            selected_papers=selected_papers,
            date=now_iso,
            drift_probability=float(config["anchor_user_probability"]),
            strategy_mode=drift_engine.STRATEGY_REAL_USER,
        )
        anchor_state = ensure_profile_schema(
            {
                "drift_state": anchor_result_profile.get("drift_state", {}),
                "drift_plan": updated.get("drift_plan", {}),
            },
            now=now,
        )["drift_state"]
        updated["core_directions"] = canonicalize_weight_mapping(anchor_result_profile.get("core_directions", updated.get("core_directions", {})))
        updated["topic_weights"] = canonicalize_weight_mapping(anchor_result_profile.get("topic_weights", updated.get("topic_weights", {})))
        anchor_must_read = anchor_result_profile.get("must_read", updated.get("must_read", {}))
        updated["must_read"] = anchor_must_read if isinstance(anchor_must_read, dict) else updated.get("must_read", {})

    shift_topics = _top_shift_topics(short_term_topics, long_term_topics)
    merged_shift_topics = canonicalize_direction_terms(
        list(shift_topics) + list(anchor_state.get("top_shift_topics", []) or []),
        keep_unknown=True,
    )[:3]
    final_status = drift_status
    final_score = round(float(drift_score), 4)
    final_detected_at = detected_at if drift_status in {"shifting", "recovered"} else previous_drift_state.get("detected_at")
    if _profile_has_anchor_plan(updated):
        final_status = str(anchor_state.get("status") or drift_status)
        final_score = round(float(anchor_state.get("score", drift_score) or drift_score), 4)
        final_detected_at = (
            anchor_state.get("anchor_set_date")
            if final_status in {"observing", "shifting", "recovered"} and anchor_state.get("anchor_set_date")
            else final_detected_at
        )

    explanation = _describe_drift_state(final_status, merged_shift_topics)

    updated["drift_state"] = {
        "status": final_status,
        "score": final_score,
        "detected_at": final_detected_at,
        "last_updated_at": now_iso,
        "long_term_vector": _resize_vector(long_term_vector, target_dim),
        "short_term_vector": _resize_vector(short_term_vector, target_dim),
        "long_term_topics": _round_mapping(long_term_topics),
        "short_term_topics": _round_mapping(short_term_topics),
        "adaptive_alpha": adaptive_alpha,
        "top_shift_topics": merged_shift_topics,
        "drift_enabled": anchor_state.get("drift_enabled"),
        "hidden_anchor": anchor_state.get("hidden_anchor"),
        "hidden_anchor_source": anchor_state.get("hidden_anchor_source"),
        "intent_score": round(float(anchor_state.get("intent_score", 0.0) or 0.0), 4),
        "anchor_topic": anchor_state.get("anchor_topic"),
        "anchor_topics": canonicalize_direction_terms(anchor_state.get("anchor_topics", []), keep_unknown=True),
        "anchor_source": anchor_state.get("anchor_source"),
        "anchor_confidence": round(float(anchor_state.get("anchor_confidence", 0.0) or 0.0), 4),
        "anchor_progress": round(float(anchor_state.get("anchor_progress", 0.0) or 0.0), 4),
        "anchor_set_date": anchor_state.get("anchor_set_date"),
        "commitment_days_remaining": int(anchor_state.get("commitment_days_remaining", 0) or 0),
        "signal_window": copy.deepcopy(anchor_state.get("signal_window", []) or []),
        "episode_index": int(anchor_state.get("episode_index", 0) or 0),
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
