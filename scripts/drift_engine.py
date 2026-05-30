#!/usr/bin/env python3
"""
Drift Engine - 鍏磋叮婕傜Щ鎵ц寮曟搸

鏍规嵁 checkfile 閰嶇疆锛屽鐢ㄦ埛鐢诲儚搴旂敤涓嶅悓绫诲瀷鐨勬紓绉汇€?
浣跨敤鏂规硶:
    from drift_engine import DriftEngine, load_checkfiles

    # 鍔犺浇鎵€鏈?checkfile
    checkfiles = load_checkfiles("data/drift_checkfiles")

    # 鍒涘缓寮曟搸
    engine = DriftEngine(checkfiles)

    # 瀵圭敤鎴峰簲鐢ㄦ紓绉?    drifted_profile, drift_event = engine.apply_drift(user_profile, date="2026-03-15")
"""

import json
import random
import copy
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

try:
    from config import direction_lexicon
except Exception:  # pragma: no cover - fallback for isolated imports
    direction_lexicon = None

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CHECKFILES_DIR = PROJECT_ROOT / "data" / "drift_checkfiles"


# ==================== Checkfile 鍔犺浇 ====================

def load_checkfiles(checkfiles_dir: str) -> List[Dict[str, Any]]:
    """鍔犺浇鎸囧畾鐩綍涓嬬殑鎵€鏈?checkfile"""
    checkfiles = []
    checkfiles_path = Path(checkfiles_dir)

    if not checkfiles_path.exists():
        print(f"[Warning] Checkfiles directory not found: {checkfiles_dir}")
        return []

    for f in sorted(checkfiles_path.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            data["_source_file"] = f.name
            checkfiles.append(data)
        except Exception as e:
            print(f"[Warning] Failed to load checkfile {f.name}: {e}")

    return checkfiles


DRIFT_SHIFT_THRESHOLD = 0.30
DRIFT_RECOVER_THRESHOLD = 0.12
DRIFT_STABLE_THRESHOLD = 0.03
ANCHOR_SIGNAL_WINDOW = 3
ANCHOR_REQUIRED_CONSECUTIVE_DAYS = 2
ANCHOR_SIGNAL_MIN_HITS = 2
ANCHOR_SIGNAL_MIN_RATIO = 0.30
ANCHOR_SIGNAL_MIN_MARGIN = 1
ANCHOR_INTENT_INCREMENT = 0.15
ANCHOR_INTENT_DECAY = 0.05
ANCHOR_LOCK_THRESHOLD = 0.30
ANCHOR_PROGRESS_STEP = 0.40
ANCHOR_SCORE_STEP = 0.24
ANCHOR_PRIMARY_BOOST = 0.12
ANCHOR_SECONDARY_BOOST = 0.06
ANCHOR_DOWNWEIGHT_STEP = 0.08
ANCHOR_MIN_WEIGHT = 0.05
ANCHOR_COMMITMENT_DAYS = 3
SIMULATION_OBSERVING_TO_SHIFT_PROBABILITY = 0.8
SIMULATION_CHECKFILE_COOLDOWN_EPISODES = 8
SIMULATION_MAX_DRIFT_OPPORTUNITIES = 5
STRATEGY_SIMULATION = "simulation"
STRATEGY_REAL_USER = "real_user"
CHECKFILE_ROLE_START_OBSERVING = "start_observing"
CHECKFILE_ROLE_SUPPORT_SHIFT = "support_shift"
CHECKFILE_ROLE_SUPPRESS_OLD_TOPICS = "suppress_old_topics"


def _canonicalize_topics(values: List[Any]) -> List[str]:
    if direction_lexicon and hasattr(direction_lexicon, "canonicalize_direction_terms"):
        try:
            return direction_lexicon.canonicalize_direction_terms(values, keep_unknown=True)
        except Exception:
            pass

    canonical_topics: List[str] = []
    for value in values:
        cleaned = str(value or "").strip().lower().replace("_", "-").replace(" ", "-")
        if cleaned and cleaned not in canonical_topics:
            canonical_topics.append(cleaned)
    return canonical_topics


def _direction_match_terms(direction: str) -> List[str]:
    cleaned = str(direction or "").strip()
    if not cleaned:
        return []

    terms = {
        cleaned.lower(),
        cleaned.lower().replace("-", " "),
        cleaned.lower().replace("_", " "),
    }

    if direction_lexicon and hasattr(direction_lexicon, "resolve_canonical_direction"):
        try:
            resolved = direction_lexicon.resolve_canonical_direction(cleaned, include_paper_terms=True)
        except Exception:
            resolved = None
        entry = (resolved or {}).get("entry") or {}
        for raw_term in (
            [entry.get("name"), entry.get("name_cn")]
            + list(entry.get("aliases", []) or [])
            + list(entry.get("paper_terms", []) or [])
        ):
            if raw_term:
                lowered = str(raw_term).strip().lower()
                if lowered:
                    terms.add(lowered)
                    terms.add(lowered.replace("-", " "))
                    terms.add(lowered.replace("_", " "))

    return [term for term in terms if term]


def _normalize_weight_map(weights: Dict[str, Any]) -> Dict[str, float]:
    normalized: Dict[str, float] = {}
    for key, value in (weights or {}).items():
        topic = str(key or "").strip()
        if not topic:
            continue
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            continue
        if numeric <= 0:
            continue
        normalized[topic] = round(min(1.0, numeric), 4)

    max_score = max(normalized.values(), default=0.0)
    if max_score > 1.0:
        normalized = {key: round(value / max_score, 4) for key, value in normalized.items()}

    return normalized


def _ensure_anchor_state(profile: Dict[str, Any]) -> Dict[str, Any]:
    drift_state = copy.deepcopy(profile.get("drift_state", {}) or {})
    drift_state.setdefault("status", "stable")
    drift_state.setdefault("score", 0.0)
    drift_state.setdefault("last_drift_date", None)
    drift_state.setdefault("drift_enabled", None)
    drift_state.setdefault("hidden_anchor", None)
    drift_state.setdefault("hidden_anchor_source", None)
    drift_state.setdefault("intent_score", 0.0)
    drift_state.setdefault("anchor_topic", None)
    drift_state.setdefault("anchor_topics", [])
    drift_state.setdefault("anchor_source", None)
    drift_state.setdefault("anchor_confidence", 0.0)
    drift_state.setdefault("anchor_progress", 0.0)
    drift_state.setdefault("anchor_set_date", None)
    drift_state.setdefault("commitment_days_remaining", 0)
    drift_state.setdefault("signal_window", [])
    drift_state.setdefault("top_shift_topics", [])
    drift_state.setdefault("episode_index", 0)
    drift_state.setdefault("trigger_source", None)
    drift_state.setdefault("trigger_checkfile", None)
    drift_state.setdefault("trigger_date", None)
    drift_state.setdefault("suppressed_topics", [])
    drift_state.setdefault("strategy_mode", STRATEGY_SIMULATION)
    drift_state.setdefault("completed_drift_cycles", 0)
    drift_state.setdefault("max_drift_cycles", None)
    drift_state.setdefault("drift_opportunity_count", 0)
    drift_state.setdefault("max_drift_opportunities", SIMULATION_MAX_DRIFT_OPPORTUNITIES)
    drift_state.setdefault("last_observing_failure_episode", 0)
    drift_state.setdefault("last_completed_drift_episode", 0)
    drift_state.setdefault("observing_started_episode", None)
    drift_state.setdefault("baseline_core_directions", {})
    drift_state.setdefault("recovery_mode", None)
    drift_state.setdefault("decayed_topics", [])
    drift_state.setdefault("topic_staleness", {})
    return drift_state


def _strategy_settings(strategy_mode: str) -> Dict[str, Any]:
    mode = str(strategy_mode or STRATEGY_SIMULATION).strip() or STRATEGY_SIMULATION
    if mode == STRATEGY_REAL_USER:
        return {
            "mode": STRATEGY_REAL_USER,
            "required_consecutive_days": 2,
            "intent_increment": 0.15,
            "intent_decay": 0.05,
            "lock_threshold": 0.15,
            "commitment_days": 3,
            "progress_step": 0.35,
            "score_step": 0.20,
            "max_shift_episode_start": 2,
            "max_recover_episode_start": 5,
            "max_drift_cycles": None,
        }
    return {
        "mode": STRATEGY_SIMULATION,
        "required_consecutive_days": ANCHOR_REQUIRED_CONSECUTIVE_DAYS,
        "intent_increment": ANCHOR_INTENT_INCREMENT,
        "intent_decay": ANCHOR_INTENT_DECAY,
        "lock_threshold": ANCHOR_LOCK_THRESHOLD,
        "commitment_days": ANCHOR_COMMITMENT_DAYS,
        "progress_step": ANCHOR_PROGRESS_STEP,
        "score_step": ANCHOR_SCORE_STEP,
        "max_shift_episode_start": 2,
        "max_recover_episode_start": 5,
        "max_drift_cycles": 3,
        "max_drift_opportunities": SIMULATION_MAX_DRIFT_OPPORTUNITIES,
        "checkfile_cooldown_episodes": SIMULATION_CHECKFILE_COOLDOWN_EPISODES,
        "observing_to_shift_probability": SIMULATION_OBSERVING_TO_SHIFT_PROBABILITY,
    }


def _candidate_shift_topics(profile: Dict[str, Any]) -> List[str]:
    return _canonicalize_topics(list((profile.get("drift_plan", {}) or {}).get("shift_topics", []) or []))


def _downweight_topics(profile: Dict[str, Any]) -> List[str]:
    return _canonicalize_topics(list((profile.get("drift_plan", {}) or {}).get("downweight_topics", []) or []))


def initialize_hidden_anchor(
    profile: Dict[str, Any],
    *,
    strategy_mode: str = STRATEGY_SIMULATION,
    drift_probability: float = 0.5,
) -> Dict[str, Any]:
    updated = copy.deepcopy(profile)
    drift_state = _ensure_anchor_state(updated)
    settings = _strategy_settings(strategy_mode)
    drift_state["strategy_mode"] = settings["mode"]

    if settings["mode"] == STRATEGY_REAL_USER and not drift_state.get("hidden_anchor"):
        shift_topics = _candidate_shift_topics(updated)
        drift_state["drift_enabled"] = bool(shift_topics)
        if shift_topics:
            drift_state["hidden_anchor"] = random.choice(shift_topics)
            drift_state["hidden_anchor_source"] = "drift_plan_once"
        else:
            drift_state["hidden_anchor"] = None
            drift_state["hidden_anchor_source"] = None

    updated["drift_state"] = drift_state
    return updated


def load_default_checkfiles() -> List[Dict[str, Any]]:
    return load_checkfiles(str(DEFAULT_CHECKFILES_DIR))


def classify_checkfile_role(checkfile: Dict[str, Any]) -> str:
    explicit_role = str(checkfile.get("trigger_role") or "").strip()
    if explicit_role:
        return explicit_role

    name = str(checkfile.get("name") or "").strip().lower()
    drift_method = str(checkfile.get("drift_method") or "").strip().lower()
    trigger_type = str((checkfile.get("trigger") or {}).get("type") or "").strip().lower()

    if name in {"topic_shift", "author_shift", "keyword_shift", "inactive_topic_decay"}:
        return CHECKFILE_ROLE_START_OBSERVING
    if drift_method in {"topic_weight_decay", "must_read_replace", "keyword_emergence"}:
        return CHECKFILE_ROLE_START_OBSERVING
    if trigger_type in {"selected_paper_topic_match", "keyword_frequency", "author_exposure", "inactive_topic_decay"}:
        return CHECKFILE_ROLE_START_OBSERVING

    if name == "direction_remove" or drift_method == "direction_remove" or trigger_type == "low_engagement":
        return CHECKFILE_ROLE_SUPPRESS_OLD_TOPICS

    if name == "direction_add" or drift_method == "direction_add" or trigger_type == "direction_exposure":
        return CHECKFILE_ROLE_SUPPORT_SHIFT

    return CHECKFILE_ROLE_SUPPORT_SHIFT


def filter_checkfiles_by_role(checkfiles: List[Dict[str, Any]], *roles: str) -> List[Dict[str, Any]]:
    allowed_roles = {str(role).strip() for role in roles if str(role).strip()}
    if not allowed_roles:
        return list(checkfiles)
    return [checkfile for checkfile in checkfiles if classify_checkfile_role(checkfile) in allowed_roles]


def _select_hidden_anchor_from_trigger(
    profile: Dict[str, Any],
    selected_papers: Optional[List[Dict]],
) -> Optional[str]:
    shift_topics = _candidate_shift_topics(profile)
    if not shift_topics:
        return None

    if selected_papers:
        topic_hits = {
            topic: _keyword_hit_count(selected_papers, _direction_match_terms(topic))
            for topic in shift_topics
        }
        ranked = sorted(topic_hits.items(), key=lambda item: (-item[1], item[0]))
        if ranked and ranked[0][1] > 0:
            return ranked[0][0]

    return shift_topics[0]


def _activate_anchor_from_checkfile(
    profile: Dict[str, Any],
    checkfile: Dict[str, Any],
    selected_papers: Optional[List[Dict]],
    date: str,
    strategy_mode: str,
) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    updated = copy.deepcopy(profile)
    drift_state = _ensure_anchor_state(updated)

    hidden_anchor = str(drift_state.get("hidden_anchor") or "").strip() or _select_hidden_anchor_from_trigger(updated, selected_papers)
    if not hidden_anchor:
        updated["drift_state"] = drift_state
        return updated, None

    drift_state["drift_enabled"] = True
    drift_state["hidden_anchor"] = hidden_anchor
    drift_state["hidden_anchor_source"] = "checkfile_trigger"
    drift_state["status"] = "observing"
    drift_state["trigger_source"] = checkfile.get("name")
    drift_state["trigger_checkfile"] = checkfile.get("_source_file") or checkfile.get("name")
    drift_state["trigger_date"] = date
    drift_state["suppressed_topics"] = _downweight_topics(updated)
    drift_state["last_drift_date"] = date
    drift_state["strategy_mode"] = str(strategy_mode or STRATEGY_SIMULATION)
    drift_state["observing_started_episode"] = drift_state.get("episode_index")
    updated["drift_state"] = drift_state

    trigger_signal = _extract_anchor_signal(updated, selected_papers)
    drift_state = _append_signal_window(drift_state, date=date, signal=trigger_signal)
    settings = _strategy_settings(strategy_mode)
    if trigger_signal.get("topic") == hidden_anchor:
        drift_state["intent_score"] = round(max(float(drift_state.get("intent_score", 0.0) or 0.0), float(settings["intent_increment"])), 2)
    else:
        drift_state["intent_score"] = round(max(float(drift_state.get("intent_score", 0.0) or 0.0), 0.05), 2)
    updated["drift_state"] = drift_state

    return updated, {
        "event_type": "trigger",
        "method": "checkfile_trigger",
        "trigger_source": drift_state["trigger_source"],
        "trigger_checkfile": drift_state["trigger_checkfile"],
        "hidden_anchor": hidden_anchor,
        "suppressed_topics": list(drift_state["suppressed_topics"] or []),
    }


def _reset_to_stable_after_observing(profile: Dict[str, Any], date: str) -> Dict[str, Any]:
    updated = copy.deepcopy(profile)
    drift_state = _ensure_anchor_state(updated)
    failed_episode = int(drift_state.get("episode_index", 0) or 0)
    drift_state["status"] = "stable"
    drift_state["score"] = 0.0
    drift_state["intent_score"] = 0.0
    drift_state["hidden_anchor"] = None
    drift_state["hidden_anchor_source"] = None
    drift_state["anchor_topic"] = None
    drift_state["anchor_topics"] = []
    drift_state["anchor_source"] = None
    drift_state["anchor_confidence"] = 0.0
    drift_state["anchor_progress"] = 0.0
    drift_state["anchor_set_date"] = None
    drift_state["commitment_days_remaining"] = 0
    drift_state["signal_window"] = []
    drift_state["top_shift_topics"] = []
    drift_state["trigger_source"] = None
    drift_state["trigger_checkfile"] = None
    drift_state["trigger_date"] = None
    drift_state["suppressed_topics"] = []
    drift_state["observing_started_episode"] = None
    drift_state["last_observing_failure_episode"] = failed_episode
    drift_state["last_drift_date"] = date
    updated["drift_state"] = drift_state
    return updated


def _extract_anchor_signal(
    profile: Dict[str, Any],
    selected_papers: Optional[List[Dict]],
) -> Dict[str, Any]:
    plan = profile.get("drift_plan", {}) or {}
    shift_topics = _canonicalize_topics(list(plan.get("shift_topics", []) or []))
    drift_state = _ensure_anchor_state(profile)
    hidden_anchor = str(drift_state.get("hidden_anchor") or "").strip()
    total_selected = len(selected_papers or [])

    if not shift_topics or not selected_papers:
        return {
            "topic": None,
            "hits": 0,
            "ratio": 0.0,
            "source_topics": shift_topics,
            "confidence": 0.0,
            "hidden_anchor": hidden_anchor or None,
            "hidden_anchor_hits": 0,
            "hidden_anchor_ratio": 0.0,
            "hidden_anchor_is_top": False,
        }

    topic_hits: Dict[str, int] = {}
    for topic in shift_topics:
        topic_hits[topic] = _keyword_hit_count(selected_papers, _direction_match_terms(topic))

    ranked = sorted(topic_hits.items(), key=lambda item: (-item[1], item[0]))
    top_topic, top_hits = ranked[0]
    second_hits = ranked[1][1] if len(ranked) > 1 else 0
    top_ratio = top_hits / max(1, total_selected)
    qualifies = (
        top_hits >= ANCHOR_SIGNAL_MIN_HITS
        and top_ratio >= ANCHOR_SIGNAL_MIN_RATIO
        and top_hits >= second_hits + ANCHOR_SIGNAL_MIN_MARGIN
    )

    hidden_anchor_hits = topic_hits.get(hidden_anchor, 0) if hidden_anchor else 0
    hidden_anchor_ratio = hidden_anchor_hits / max(1, total_selected)
    hidden_anchor_is_top = bool(hidden_anchor and qualifies and top_topic == hidden_anchor)

    return {
        "topic": hidden_anchor if hidden_anchor_is_top else (top_topic if qualifies and not hidden_anchor else None),
        "hits": top_hits,
        "ratio": round(top_ratio, 3),
        "second_hits": second_hits,
        "source_topics": shift_topics,
        "confidence": round((top_hits - second_hits) / max(1, total_selected), 3) if qualifies else 0.0,
        "top_topic": top_topic if qualifies else None,
        "hidden_anchor": hidden_anchor or None,
        "hidden_anchor_hits": hidden_anchor_hits,
        "hidden_anchor_ratio": round(hidden_anchor_ratio, 3),
        "hidden_anchor_is_top": hidden_anchor_is_top,
    }


def _append_signal_window(
    drift_state: Dict[str, Any],
    *,
    date: str,
    signal: Dict[str, Any],
) -> Dict[str, Any]:
    window = list(drift_state.get("signal_window", []) or [])
    window.append(
        {
            "date": date,
            "topic": signal.get("topic"),
            "hits": int(signal.get("hits") or 0),
            "ratio": float(signal.get("ratio") or 0.0),
            "top_topic": signal.get("top_topic"),
            "hidden_anchor": signal.get("hidden_anchor"),
            "hidden_anchor_hits": int(signal.get("hidden_anchor_hits") or 0),
            "hidden_anchor_ratio": float(signal.get("hidden_anchor_ratio") or 0.0),
            "hidden_anchor_is_top": bool(signal.get("hidden_anchor_is_top")),
        }
    )
    drift_state["signal_window"] = window[-ANCHOR_SIGNAL_WINDOW:]

    counter = Counter(entry.get("topic") for entry in drift_state["signal_window"] if entry.get("topic"))
    drift_state["top_shift_topics"] = [topic for topic, _count in counter.most_common(3)]
    return drift_state


def _compute_topic_staleness(
    profile: Dict[str, Any],
    *,
    stale_topics_pool: List[str],
    window_episodes: int,
    min_total_selected: int,
) -> Dict[str, Any]:
    history = list(profile.get("reading_history") or [])
    if not history:
        return {"decayed_topics": [], "topic_staleness": {}}

    recent_history = history[-max(1, window_episodes):]
    selected_events = [
        entry for entry in recent_history
        if str(entry.get("action") or "").strip().lower() == "selected"
    ]
    if len(selected_events) < min_total_selected:
        return {"decayed_topics": [], "topic_staleness": {}}

    topic_staleness: Dict[str, float] = {}
    decayed_topics: List[str] = []
    for topic in stale_topics_pool:
        hits = 0
        for entry in selected_events:
            entry_topics = _canonicalize_topics(list(entry.get("topics", []) or []))
            if topic in entry_topics:
                hits += 1
        stale_ratio = 1.0 - (hits / max(1, len(selected_events)))
        topic_staleness[topic] = round(stale_ratio, 3)
        if hits == 0:
            decayed_topics.append(topic)

    return {"decayed_topics": decayed_topics, "topic_staleness": topic_staleness}


def _find_stable_anchor_candidate(drift_state: Dict[str, Any], *, required_consecutive_days: int) -> Optional[Dict[str, Any]]:
    window = list(drift_state.get("signal_window", []) or [])
    if len(window) < required_consecutive_days:
        return None

    trailing = window[-required_consecutive_days:]
    topics = [entry.get("topic") for entry in trailing]
    if any(not topic for topic in topics):
        return None
    if len(set(topics)) != 1:
        return None

    topic = str(topics[0])
    avg_ratio = sum(float(entry.get("ratio") or 0.0) for entry in trailing) / len(trailing)
    avg_hits = sum(int(entry.get("hits") or 0) for entry in trailing) / len(trailing)
    return {
        "topic": topic,
        "confidence": round(avg_ratio, 3),
        "avg_hits": round(avg_hits, 2),
        "consecutive_days": len(trailing),
    }


def _lock_anchor(
    profile: Dict[str, Any],
    candidate: Dict[str, Any],
    date: str,
    *,
    signal_topics: List[str],
    settings: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    updated = copy.deepcopy(profile)
    drift_state = _ensure_anchor_state(updated)
    anchor_topic = str(drift_state.get("hidden_anchor") or candidate.get("topic") or "").strip()

    drift_state["anchor_topic"] = anchor_topic
    drift_state["anchor_topics"] = list(signal_topics or [anchor_topic])
    drift_state["anchor_source"] = "hidden_anchor"
    drift_state["anchor_confidence"] = round(float(candidate.get("confidence") or 0.0), 3)
    drift_state["anchor_progress"] = 0.0
    drift_state["anchor_set_date"] = date
    drift_state["commitment_days_remaining"] = int(settings["commitment_days"])
    drift_state["intent_score"] = round(max(float(drift_state.get("intent_score") or 0.0), float(settings["lock_threshold"])), 2)
    drift_state["last_drift_date"] = date
    drift_state["baseline_core_directions"] = copy.deepcopy(updated.get("core_directions", {}) or {})
    drift_state["recovery_mode"] = None
    drift_state["completed_drift_cycles"] = int(drift_state.get("completed_drift_cycles", 0) or 0) + 1
    if settings.get("max_drift_cycles") is not None and drift_state.get("max_drift_cycles") is None:
        drift_state["max_drift_cycles"] = int(settings["max_drift_cycles"])
    updated["drift_state"] = drift_state

    return updated, {
        "event_type": "drift",
        "method": "anchor_lock",
        "anchor_topic": anchor_topic,
        "anchor_topics": list(signal_topics or [anchor_topic]),
        "anchor_confidence": drift_state["anchor_confidence"],
        "commitment_days": int(settings["commitment_days"]),
        "completed_drift_cycles": drift_state["completed_drift_cycles"],
    }


def _advance_anchor_profile(
    profile: Dict[str, Any],
    date: str,
    *,
    settings: Dict[str, Any],
) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    updated = copy.deepcopy(profile)
    drift_state = _ensure_anchor_state(updated)
    anchor_topic = str(drift_state.get("anchor_topic") or "").strip()
    if not anchor_topic:
        updated["drift_state"] = drift_state
        return updated, None

    plan = updated.get("drift_plan", {}) or {}
    shift_topics = _canonicalize_topics(list(plan.get("shift_topics", []) or []))
    if anchor_topic not in shift_topics:
        shift_topics = [anchor_topic, *shift_topics]
    downweight_topics = list(dict.fromkeys(list(drift_state.get("suppressed_topics", []) or []) + _canonicalize_topics(list(plan.get("downweight_topics", []) or []))))

    core_directions = _normalize_weight_map(copy.deepcopy(updated.get("core_directions", {}) or {}))
    topic_weights = _normalize_weight_map(copy.deepcopy(updated.get("topic_weights", {}) or core_directions))

    core_directions[anchor_topic] = max(float(core_directions.get(anchor_topic, 0.0) or 0.0), 0.35)
    core_directions[anchor_topic] = round(min(1.0, core_directions[anchor_topic] + ANCHOR_PRIMARY_BOOST), 4)

    for topic in shift_topics:
        if topic == anchor_topic:
            continue
        base = max(float(core_directions.get(topic, 0.0) or 0.0), ANCHOR_MIN_WEIGHT)
        core_directions[topic] = round(min(1.0, base + ANCHOR_SECONDARY_BOOST), 4)

    for topic in downweight_topics:
        if topic not in core_directions:
            continue
        core_directions[topic] = round(max(ANCHOR_MIN_WEIGHT, core_directions[topic] - ANCHOR_DOWNWEIGHT_STEP), 4)

    updated["core_directions"] = _normalize_weight_map(core_directions)
    topic_weights.update(updated["core_directions"])
    updated["topic_weights"] = _normalize_weight_map(topic_weights)

    old_progress = float(drift_state.get("anchor_progress") or 0.0)
    old_score = float(drift_state.get("score") or 0.0)
    drift_state["anchor_progress"] = round(min(1.0, old_progress + float(settings["progress_step"])), 2)
    drift_state["commitment_days_remaining"] = max(0, int(drift_state.get("commitment_days_remaining") or 0) - 1)
    drift_state["score"] = round(max(DRIFT_SHIFT_THRESHOLD, min(1.0, old_score + float(settings["score_step"]))), 2)
    drift_state["status"] = "shifting"
    drift_state["last_drift_date"] = date
    drift_state["top_shift_topics"] = list(dict.fromkeys([anchor_topic, *shift_topics]))[:3]
    updated["drift_state"] = drift_state

    if old_progress < 1.0 <= drift_state["anchor_progress"]:
        return updated, {
            "event_type": "progress",
            "method": "anchor_completed",
            "anchor_topic": anchor_topic,
            "anchor_progress": drift_state["anchor_progress"],
        }

    return updated, None


def _paper_matches_any_topic(paper: Dict[str, Any], topics: List[str]) -> bool:
    if not topics:
        return False
    return any(_keyword_hit_count([paper], _direction_match_terms(topic)) > 0 for topic in topics)


def advance_anchor_recovery(
    profile: Dict[str, Any],
    selected_papers: Optional[List[Dict[str, Any]]],
    date: Optional[str],
    *,
    strategy_mode: str,
) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    updated = copy.deepcopy(profile)
    drift_state = _ensure_anchor_state(updated)
    status = str(drift_state.get("status") or "stable")
    if status not in {"shifting", "recovered"}:
        return updated, None
    if int(drift_state.get("commitment_days_remaining", 0) or 0) > 0:
        return updated, None

    selected_papers = list(selected_papers or [])
    if not selected_papers:
        return updated, None

    anchor_topic = str(drift_state.get("anchor_topic") or "").strip()
    if not anchor_topic:
        return updated, None

    baseline_topics = [
        topic for topic in (drift_state.get("baseline_core_directions", {}) or {}).keys()
        if str(topic).strip() and str(topic).strip() != anchor_topic
    ]
    total_count = len(selected_papers)
    anchor_hits = sum(1 for paper in selected_papers if _paper_matches_any_topic(paper, [anchor_topic]))
    baseline_hits = sum(1 for paper in selected_papers if _paper_matches_any_topic(paper, baseline_topics))
    anchor_ratio = anchor_hits / max(1, total_count)
    baseline_ratio = baseline_hits / max(1, total_count)

    recovery_mode: Optional[str] = None
    if anchor_hits >= 2 and baseline_hits == 0:
        recovery_mode = "consolidate_new"
    elif anchor_hits >= 1 and baseline_hits >= 1:
        recovery_mode = "rebalance"
    elif baseline_hits >= 2:
        recovery_mode = "rollback"

    if recovery_mode is None:
        return updated, None

    baseline_core = _normalize_weight_map(copy.deepcopy(drift_state.get("baseline_core_directions", {}) or {}))
    core_directions = _normalize_weight_map(copy.deepcopy(updated.get("core_directions", {}) or {}))
    topic_weights = _normalize_weight_map(copy.deepcopy(updated.get("topic_weights", {}) or core_directions))

    if recovery_mode == "rebalance":
        for topic, weight in baseline_core.items():
            if topic == anchor_topic:
                continue
            core_directions[topic] = max(float(core_directions.get(topic, 0.0) or 0.0), round(min(1.0, weight * 0.85), 4))
    elif recovery_mode == "rollback":
        for topic, weight in baseline_core.items():
            if topic == anchor_topic:
                continue
            core_directions[topic] = max(float(core_directions.get(topic, 0.0) or 0.0), round(min(1.0, weight), 4))
        if anchor_topic in core_directions:
            core_directions[anchor_topic] = round(max(ANCHOR_MIN_WEIGHT, float(core_directions[anchor_topic]) - 0.15), 4)

    updated["core_directions"] = _normalize_weight_map(core_directions)
    topic_weights.update(updated["core_directions"])
    updated["topic_weights"] = _normalize_weight_map(topic_weights)

    old_score = float(drift_state.get("score") or 0.0)
    reduction = 0.18 if strategy_mode == STRATEGY_SIMULATION else 0.15
    new_score = max(0.0, old_score - reduction)

    if status == "shifting":
        new_status = "stable" if new_score <= DRIFT_STABLE_THRESHOLD else "recovered"
    else:
        new_status = "stable" if new_score <= DRIFT_STABLE_THRESHOLD else "recovered"

    drift_state["status"] = new_status
    drift_state["score"] = 0.0 if new_status == "stable" else round(new_score, 2)
    drift_state["last_drift_date"] = date
    drift_state["recovery_mode"] = recovery_mode
    drift_state["anchor_progress"] = round(max(0.0, float(drift_state.get("anchor_progress", 0.0) or 0.0) - 0.20), 2)

    if new_status == "stable":
        drift_state["drift_enabled"] = None
        drift_state["hidden_anchor"] = None
        drift_state["hidden_anchor_source"] = None
        drift_state["intent_score"] = 0.0
        drift_state["anchor_topic"] = None
        drift_state["anchor_topics"] = []
        drift_state["anchor_source"] = None
        drift_state["anchor_confidence"] = 0.0
        drift_state["anchor_progress"] = 0.0
        drift_state["anchor_set_date"] = None
        drift_state["commitment_days_remaining"] = 0
        drift_state["signal_window"] = []
        drift_state["top_shift_topics"] = []
        drift_state["trigger_source"] = None
        drift_state["trigger_checkfile"] = None
        drift_state["trigger_date"] = None
        drift_state["suppressed_topics"] = []
        if strategy_mode == STRATEGY_SIMULATION:
            drift_state["last_completed_drift_episode"] = int(drift_state.get("episode_index", 0) or 0)

    updated["drift_state"] = drift_state
    return updated, {
        "event_type": "recovery",
        "method": "anchor_recovery",
        "anchor_topic": anchor_topic,
        "recovery_mode": recovery_mode,
        "anchor_hits": anchor_hits,
        "baseline_hits": baseline_hits,
        "anchor_ratio": round(anchor_ratio, 2),
        "baseline_ratio": round(baseline_ratio, 2),
    }


def advance_anchor_drift(
    profile: Dict[str, Any],
    selected_papers: Optional[List[Dict]],
    date: Optional[str],
    *,
    drift_probability: float = 0.5,
    checkfiles: Optional[List[Dict[str, Any]]] = None,
    strategy_mode: str = STRATEGY_SIMULATION,
) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    """
    Evidence-driven anchored drift:
    1. Observe stable multi-day signal for the same new topic
    2. Lock an anchor topic once intent is strong enough
    3. Progress deterministically for a short commitment window
    """
    updated = initialize_hidden_anchor(
        profile,
        strategy_mode=strategy_mode,
        drift_probability=drift_probability,
    )
    drift_state = _ensure_anchor_state(updated)
    settings = _strategy_settings(strategy_mode)
    drift_state["strategy_mode"] = settings["mode"]
    drift_state["episode_index"] = int(drift_state.get("episode_index") or 0) + 1
    if settings.get("max_drift_cycles") is not None and drift_state.get("max_drift_cycles") is None:
        drift_state["max_drift_cycles"] = int(settings["max_drift_cycles"])
    updated["drift_state"] = drift_state
    drift_plan = updated.get("drift_plan", {}) or {}
    raw_shift_episode_start = max(0, int(drift_plan.get("shift_episode_start", 0) or 0))
    shift_episode_start = min(raw_shift_episode_start, int(settings["max_shift_episode_start"])) if raw_shift_episode_start else 0

    if settings["mode"] == STRATEGY_SIMULATION and str(drift_state.get("status") or "") == "observing":
        signal = _extract_anchor_signal(updated, selected_papers)
        drift_state = _append_signal_window(drift_state, date=str(date or ""), signal=signal)
        updated["drift_state"] = drift_state

        hidden_anchor_hits = int(signal.get("hidden_anchor_hits") or 0)
        if hidden_anchor_hits > 0:
            drift_state["intent_score"] = round(
                min(1.0, float(drift_state.get("intent_score") or 0.0) + float(settings["intent_increment"])),
                2,
            )
            updated["drift_state"] = drift_state
            locked_profile, lock_event = _lock_anchor(
                updated,
                {
                    "topic": str(drift_state.get("hidden_anchor") or ""),
                    "confidence": max(
                        float(signal.get("hidden_anchor_ratio") or 0.0),
                        float(signal.get("confidence") or 0.0),
                    ),
                },
                str(date or ""),
                signal_topics=list(signal.get("source_topics") or []),
                settings=settings,
            )
            progressed_profile, completion_event = _advance_anchor_profile(locked_profile, str(date or ""), settings=settings)
            return progressed_profile, completion_event or lock_event

        observing_started_episode = int(drift_state.get("observing_started_episode") or drift_state.get("episode_index") or 0)
        observing_elapsed = int(drift_state.get("episode_index") or 0) - observing_started_episode
        if observing_elapsed >= 2:
            reset_profile = _reset_to_stable_after_observing(updated, str(date or ""))
            return reset_profile, {
                "event_type": "recovery",
                "method": "observing_timeout",
                "hidden_anchor": drift_state.get("hidden_anchor"),
            }

        updated["drift_state"] = drift_state
        return updated, None

    if drift_state.get("anchor_topic") and drift_state.get("commitment_days_remaining", 0) > 0:
        return _advance_anchor_profile(updated, date or "", settings=settings)

    recovered_profile, recovery_event = advance_anchor_recovery(
        updated,
        selected_papers,
        date,
        strategy_mode=settings["mode"],
    )
    if recovery_event is not None:
        return recovered_profile, recovery_event

    if (
        settings.get("max_drift_cycles") is not None
        and int(drift_state.get("completed_drift_cycles", 0) or 0) >= int(drift_state.get("max_drift_cycles", settings["max_drift_cycles"]) or settings["max_drift_cycles"])
    ):
        drift_state["drift_enabled"] = False
        drift_state["hidden_anchor"] = None
        drift_state["hidden_anchor_source"] = None
        if not drift_state.get("anchor_topic"):
            drift_state["status"] = "stable"
        updated["drift_state"] = drift_state
        return updated, None

    if settings["mode"] == STRATEGY_REAL_USER:
        if not drift_state.get("drift_enabled") or not drift_state.get("hidden_anchor"):
            updated["drift_state"] = drift_state
            return updated, None
    elif not drift_state.get("drift_enabled") or not drift_state.get("hidden_anchor"):
        if int(drift_state.get("drift_opportunity_count", 0) or 0) >= int(
            drift_state.get("max_drift_opportunities", settings["max_drift_opportunities"]) or settings["max_drift_opportunities"]
        ):
            updated["drift_state"] = drift_state
            return updated, None

        last_completed_drift_episode = int(drift_state.get("last_completed_drift_episode", 0) or 0)
        if last_completed_drift_episode and (int(drift_state["episode_index"]) - last_completed_drift_episode) < int(settings["checkfile_cooldown_episodes"]):
            updated["drift_state"] = drift_state
            return updated, None

        last_observing_failure_episode = int(drift_state.get("last_observing_failure_episode", 0) or 0)
        if last_observing_failure_episode and (int(drift_state["episode_index"]) - last_observing_failure_episode) <= 1:
            updated["drift_state"] = drift_state
            return updated, None

        start_checkfiles = filter_checkfiles_by_role(
            list(checkfiles or []),
            CHECKFILE_ROLE_START_OBSERVING,
        )
        if start_checkfiles:
            drift_state["drift_opportunity_count"] = int(drift_state.get("drift_opportunity_count", 0) or 0) + 1
            updated["drift_state"] = drift_state
            chosen_checkfile = random.choice(start_checkfiles)
            triggered_profile, trigger_event = _activate_anchor_from_checkfile(
                updated,
                chosen_checkfile,
                selected_papers,
                str(date or ""),
                settings["mode"],
            )
            return triggered_profile, trigger_event

        return updated, None

    signal = _extract_anchor_signal(updated, selected_papers)
    drift_state = _append_signal_window(drift_state, date=str(date or ""), signal=signal)
    updated["drift_state"] = drift_state

    candidate = _find_stable_anchor_candidate(
        drift_state,
        required_consecutive_days=int(settings["required_consecutive_days"]),
    )
    if candidate and drift_state["episode_index"] >= shift_episode_start:
        drift_state["intent_score"] = round(min(1.0, float(drift_state.get("intent_score") or 0.0) + float(settings["intent_increment"])), 2)
        if not drift_state.get("anchor_topic"):
            drift_state["status"] = "observing"
        updated["drift_state"] = drift_state

        if drift_state["intent_score"] >= float(settings["lock_threshold"]):
            locked_profile, lock_event = _lock_anchor(
                updated,
                candidate,
                str(date or ""),
                signal_topics=list(signal.get("source_topics") or []),
                settings=settings,
            )
            progressed_profile, completion_event = _advance_anchor_profile(locked_profile, str(date or ""), settings=settings)
            return progressed_profile, completion_event or lock_event
    else:
        drift_state["intent_score"] = round(max(0.0, float(drift_state.get("intent_score") or 0.0) - float(settings["intent_decay"])), 2)
        if not drift_state.get("anchor_topic"):
            drift_state["status"] = "stable"
        updated["drift_state"] = drift_state

    return updated, None


# ==================== 婕傜Щ鏂规硶瀹炵幇 ====================

def topic_weight_decay(
    profile: Dict[str, Any],
    params: Dict[str, Any],
    selected_papers: Optional[List[Dict]] = None,
    date: Optional[str] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    涓婚鏉冮噸婕傜Щ锛氭棫鏍稿績鏂瑰悜鏉冮噸琛板噺锛屾柊鍏存柟鍚戞潈閲嶆彁鍗?
    Args:
        profile: 鐢ㄦ埛鐢诲儚
        params: checkfile 涓殑鍙傛暟
        selected_papers: 鐢ㄦ埛閫変腑鐨勮鏂囷紙鐢ㄤ簬妫€娴嬫柊鍏翠富棰橈級

    Returns:
        (鏇存柊鍚庣殑 profile, drift_event 鍏冩暟鎹?
    """
    updated = copy.deepcopy(profile)
    core_directions = updated.get("core_directions", {})

    # 1. 鏃ф柟鍚戣“鍑?
    for direction in list(core_directions.keys()):
        core_directions[direction] *= params.get("decay_factor", 0.7)

    # 2. 浠庤鏂囦腑鎻愬彇鏂板叴涓婚
    emerging_topics = _extract_emerging_topics(selected_papers, params)

    # 3. 鏂版柟鍚戞彁鍗?娣诲姞
    for topic in emerging_topics:
        if topic in core_directions:
            core_directions[topic] *= params.get("boost_factor", 1.5)
        else:
            core_directions[topic] = params.get("min_emerging_score", 0.4)

    # 4. 褰掍竴鍖栧埌 [0, 1]
    max_score = max(core_directions.values()) if core_directions else 1.0
    if max_score > 0:
        for k in core_directions:
            core_directions[k] = min(1.0, core_directions[k] / max_score)

    # 5. 闄愬埗鏂瑰悜鏁伴噺
    if len(core_directions) > params.get("max_topics", 5):
        sorted_dirs = sorted(core_directions.items(), key=lambda x: x[1], reverse=True)
        core_directions = dict(sorted_dirs[: params["max_topics"]])

    updated["core_directions"] = core_directions

    # 6. 鍚屾鏇存柊 topic_weights
    updated["topic_weights"] = copy.deepcopy(core_directions)

    # 7. 鏇存柊 drift_state
    updated["drift_state"] = _update_drift_state(profile, date, score_delta=0.2)

    drift_event = {
        "method": "topic_weight_decay",
        "emerging_topics": emerging_topics,
        "old_directions_count": len(profile.get("core_directions", {})),
        "new_directions_count": len(core_directions),
        "directions_added": [t for t in emerging_topics if t not in profile.get("core_directions", {})],
    }

    return updated, drift_event


def must_read_replace(
    profile: Dict[str, Any],
    params: Dict[str, Any],
    selected_papers: Optional[List[Dict]] = None,
    date: Optional[str] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    蹇呰浣滆€?鏈烘瀯婕傜Щ锛氭浛鎹㈤儴鍒嗗繀璇讳綔鑰呭拰鏈烘瀯
    """
    updated = copy.deepcopy(profile)
    must_read = updated.get("must_read", {})

    replace_ratio = params.get("replace_ratio", 0.5)

    # 鏇挎崲浣滆€?
    old_authors = list(must_read.get("authors", []))
    if old_authors and random.random() < replace_ratio:
        keep_count = max(0, int(len(old_authors) * (1 - replace_ratio)))
        new_authors_pool = params.get("new_authors_pool", [])

        # 淇濈暀閮ㄥ垎鏃т綔鑰?
        kept_authors = random.sample(old_authors, keep_count) if keep_count > 0 else []

        # 娣诲姞鏂颁綔鑰?
        new_authors_count = len(old_authors) - keep_count
        new_authors = random.sample(new_authors_pool, min(new_authors_count, len(new_authors_pool)))

        must_read["authors"] = kept_authors + new_authors

    # 鏇挎崲鏈烘瀯
    old_institutions = list(must_read.get("institutions", []))
    if old_institutions and random.random() < replace_ratio:
        keep_count = max(0, int(len(old_institutions) * (1 - replace_ratio)))
        new_institutions_pool = params.get("new_institutions_pool", [])

        kept_institutions = random.sample(old_institutions, keep_count) if keep_count > 0 else []
        new_institutions_count = len(old_institutions) - keep_count
        new_institutions = random.sample(
            new_institutions_pool, min(new_institutions_count, len(new_institutions_pool))
        )

        must_read["institutions"] = kept_institutions + new_institutions

    updated["must_read"] = must_read

    # 鏇存柊 drift_state
    updated["drift_state"] = _update_drift_state(profile, date, score_delta=0.2)

    drift_event = {
        "method": "must_read_replace",
        "authors_before": old_authors,
        "authors_after": list(must_read.get("authors", [])),
        "institutions_before": old_institutions,
        "institutions_after": list(must_read.get("institutions", [])),
    }

    return updated, drift_event


def keyword_emergence(
    profile: Dict[str, Any],
    params: Dict[str, Any],
    selected_papers: Optional[List[Dict]] = None,
    date: Optional[str] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    鍏抽敭璇嶆紓绉伙細娣诲姞鏂板叴鎶€鏈叧閿瘝鍒板繀璇绘竻鍗?    """
    updated = copy.deepcopy(profile)
    must_read = updated.get("must_read", {})

    old_keywords = list(must_read.get("keywords", []))
    new_keywords_pool = params.get("new_keywords_pool", [])
    add_count = params.get("add_count", 2)

    # 杩囨护鎺夊凡鏈夌殑鍏抽敭璇?
    available_keywords = [k for k in new_keywords_pool if k not in old_keywords]

    # 闅忔満閫夋嫨鏂板叧閿瘝
    new_keywords = random.sample(available_keywords, min(add_count, len(available_keywords)))

    must_read["keywords"] = old_keywords + new_keywords
    updated["must_read"] = must_read

    # 鏇存柊 drift_state
    updated["drift_state"] = _update_drift_state(profile, date, score_delta=0.2)

    drift_event = {
        "method": "keyword_emergence",
        "keywords_before": old_keywords,
        "keywords_added": new_keywords,
        "keywords_after": list(must_read["keywords"]),
    }

    return updated, drift_event


def direction_add(
    profile: Dict[str, Any],
    params: Dict[str, Any],
    selected_papers: Optional[List[Dict]] = None,
    date: Optional[str] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    鏂板鏍稿績鏂瑰悜锛氬湪鍘熸湁鏍稿績鏂瑰悜鍩虹涓婃坊鍔犳柊鐨勭爺绌舵柟鍚?    """
    updated = copy.deepcopy(profile)
    core_directions = updated.get("core_directions", {})

    old_directions = list(core_directions.keys())
    new_directions_pool = params.get("new_directions_pool", [])
    add_count = params.get("add_count", 1)
    initial_weight = params.get("initial_weight", 0.4)

    # 杩囨护鎺夊凡鏈夌殑鏂瑰悜
    available_directions = [d for d in new_directions_pool if d not in core_directions]

    # 闅忔満閫夋嫨鏂版柟鍚?
    new_directions = random.sample(available_directions, min(add_count, len(available_directions)))

    # 娣诲姞鏂版柟鍚?
    for direction in new_directions:
        core_directions[direction] = initial_weight

    updated["core_directions"] = core_directions
    updated["topic_weights"] = copy.deepcopy(core_directions)

    # 鏇存柊 drift_state
    updated["drift_state"] = _update_drift_state(profile, date, score_delta=0.2)

    drift_event = {
        "method": "direction_add",
        "directions_before": old_directions,
        "directions_added": new_directions,
        "directions_after": list(core_directions.keys()),
    }

    return updated, drift_event


def direction_remove(
    profile: Dict[str, Any],
    params: Dict[str, Any],
    selected_papers: Optional[List[Dict]] = None,
    date: Optional[str] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    绉婚櫎鏃ф柟鍚戯細绉婚櫎鏉冮噸浣庝簬闃堝€肩殑琛伴€€鏍稿績鏂瑰悜
    """
    updated = copy.deepcopy(profile)
    core_directions = updated.get("core_directions", {})

    weight_threshold = params.get("weight_threshold", 0.3)
    max_remove_count = params.get("max_remove_count", 2)

    old_directions = list(core_directions.keys())

    # 鎵惧嚭鏉冮噸浣庝簬闃堝€肩殑鏂瑰悜
    low_weight_directions = [
        (k, v) for k, v in core_directions.items() if v < weight_threshold
    ]

    # 鎸夋潈閲嶆帓搴忥紝绉婚櫎鏈€浣庣殑
    low_weight_directions.sort(key=lambda x: x[1])
    to_remove = [k for k, v in low_weight_directions[:max_remove_count]]

    # 绉婚櫎鏂瑰悜
    for direction in to_remove:
        del core_directions[direction]

    # 褰掍竴鍖?
    if params.get("renormalize", True) and core_directions:
        max_score = max(core_directions.values())
        if max_score > 0:
            for k in core_directions:
                core_directions[k] = min(1.0, core_directions[k] / max_score)

    updated["core_directions"] = core_directions
    updated["topic_weights"] = copy.deepcopy(core_directions)

    # 鏇存柊 drift_state
    updated["drift_state"] = _update_drift_state(profile, date, score_delta=0.2)

    drift_event = {
        "method": "direction_remove",
        "directions_before": old_directions,
        "directions_removed": to_remove,
        "directions_after": list(core_directions.keys()),
        "reason": f"weight < {weight_threshold}",
    }

    return updated, drift_event


# ==================== 杈呭姪鍑芥暟 ====================

def _extract_emerging_topics(
    selected_papers: Optional[List[Dict]],
    params: Dict[str, Any],
) -> List[str]:
    """浠庨€変腑鐨勮鏂囦腑鎻愬彇鏂板叴涓婚"""
    if not selected_papers:
        return []

    emerging_topics_pool = params.get("emerging_topics_pool", [])
    topic_scores = {}

    for paper in selected_papers:
        title = (paper.get("title") or "").lower()
        abstract = (paper.get("abstract") or "").lower()
        categories = paper.get("categories", [])
        text = f"{title} {abstract}"

        for topic in emerging_topics_pool:
            if topic.lower().replace("-", " ") in text or topic.lower() in categories:
                topic_scores[topic] = topic_scores.get(topic, 0) + 1

    # 杩斿洖鍑虹幇棰戠巼 >= 2 鐨勪富棰?
    min_count = params.get("min_emerging_score", 0.4)
    threshold = int(len(selected_papers) * min_count)

    return [topic for topic, count in topic_scores.items() if count >= max(1, threshold)]


def _paper_text(paper: Dict[str, Any]) -> str:
    title = str(paper.get("title") or "").lower()
    abstract = str(paper.get("abstract") or "").lower()
    categories = " ".join(str(item).lower() for item in (paper.get("categories") or []))
    authors = " ".join(str(item).lower() for item in (paper.get("authors") or []))
    return " ".join(part for part in (title, abstract, categories, authors) if part)


def _keyword_hit_count(selected_papers: Optional[List[Dict]], candidates: List[str]) -> int:
    if not selected_papers or not candidates:
        return 0
    total = 0
    normalized_candidates = [str(item).lower().replace("-", " ") for item in candidates if str(item).strip()]
    for paper in selected_papers:
        text = _paper_text(paper)
        if any(candidate in text for candidate in normalized_candidates):
            total += 1
    return total


def _trigger_satisfied(
    checkfile: Dict[str, Any],
    profile: Dict[str, Any],
    selected_papers: Optional[List[Dict]],
) -> bool:
    trigger = checkfile.get("trigger") or {}
    trigger_type = str(trigger.get("type") or "").strip()
    if not trigger_type:
        return True

    min_count = max(1, int(trigger.get("min_count", 1) or 1))

    if trigger_type in {"selected_paper_topic_match", "direction_exposure"}:
        pool = list((checkfile.get("params") or {}).get("new_directions_pool", []) or []) + list(
            (checkfile.get("params") or {}).get("emerging_topics_pool", []) or []
        )
        return _keyword_hit_count(selected_papers, pool) >= min_count

    if trigger_type == "keyword_frequency":
        pool = list((checkfile.get("params") or {}).get("new_keywords_pool", []) or [])
        return _keyword_hit_count(selected_papers, pool) >= min_count

    if trigger_type == "author_exposure":
        pool = list((checkfile.get("params") or {}).get("new_authors_pool", []) or [])
        return _keyword_hit_count(selected_papers, pool) >= min_count

    if trigger_type == "inactive_topic_decay":
        window_episodes = max(2, int(trigger.get("window_episodes", 5) or 5))
        min_total_selected = max(1, int(trigger.get("min_total_selected", 3) or 3))
        stale_topics_pool = _canonicalize_topics(
            list((checkfile.get("params") or {}).get("stale_topics_pool", []) or [])
        )
        if not stale_topics_pool:
            stale_topics_pool = _canonicalize_topics(
                list((profile.get("drift_plan", {}) or {}).get("downweight_topics", []) or [])
            )
        if not stale_topics_pool:
            stale_topics_pool = list((profile.get("core_directions", {}) or {}).keys())

        staleness_payload = _compute_topic_staleness(
            profile,
            stale_topics_pool=stale_topics_pool,
            window_episodes=window_episodes,
            min_total_selected=min_total_selected,
        )
        profile.setdefault("drift_state", {})
        profile["drift_state"]["decayed_topics"] = staleness_payload["decayed_topics"]
        profile["drift_state"]["topic_staleness"] = staleness_payload["topic_staleness"]
        # Time decay alone should not start observing; it only contributes
        # stale-topic evidence that later ranking and combined triggers can use.
        return False

    if trigger_type == "low_engagement":
        min_skipped = int(trigger.get("min_skipped_papers", 5) or 5)
        selected_count = len(selected_papers or [])
        return selected_count <= max(0, min_skipped // 2)

    return False


# ==================== DriftEngine 涓荤被 ====================

class DriftEngine:
    """鍏磋叮婕傜Щ鎵ц寮曟搸"""

    DRIFT_METHODS = {
        "topic_weight_decay": topic_weight_decay,
        "must_read_replace": must_read_replace,
        "keyword_emergence": keyword_emergence,
        "direction_add": direction_add,
        "direction_remove": direction_remove,
    }

    def __init__(self, checkfiles: List[Dict[str, Any]]):
        self.checkfiles = checkfiles
        self.drift_history: List[Dict[str, Any]] = []

    def select_random_checkfile(self) -> Optional[Dict[str, Any]]:
        """闅忔満閫夋嫨涓€涓?checkfile"""
        if not self.checkfiles:
            return None
        return random.choice(self.checkfiles)

    def should_drift(self, probability: float = 0.5) -> bool:
        """鍒ゆ柇鏄惁鍙戠敓婕傜Щ"""
        return random.random() < probability

    def advance_profile_drift(
        self,
        profile: Dict[str, Any],
        *,
        selected_papers: Optional[List[Dict]] = None,
        date: Optional[str] = None,
        drift_probability: float = 0.5,
        strategy_mode: str = STRATEGY_SIMULATION,
    ) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
        return advance_anchor_drift(
            profile,
            selected_papers,
            date,
            drift_probability=drift_probability,
            checkfiles=self.checkfiles,
            strategy_mode=strategy_mode,
        )

    def apply_drift(
        self,
        profile: Dict[str, Any],
        checkfile: Optional[Dict[str, Any]] = None,
        selected_papers: Optional[List[Dict]] = None,
        date: Optional[str] = None,
    ) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
        """
        瀵圭敤鎴风敾鍍忓簲鐢ㄦ紓绉?
        Args:
            profile: 鐢ㄦ埛鐢诲儚
            checkfile: 婕傜Щ閰嶇疆鏂囦欢锛堝鏋滀笉浼犲垯闅忔満閫夋嫨锛?            selected_papers: 鐢ㄦ埛閫変腑鐨勮鏂?            date: 鏃ユ湡

        Returns:
            (鏇存柊鍚庣殑 profile, drift_event 鍏冩暟鎹?
        """
        if checkfile is None:
            checkfile = self.select_random_checkfile()

        if checkfile is None:
            return profile, None

        method_name = checkfile.get("drift_method")
        if method_name not in self.DRIFT_METHODS:
            print(f"[Warning] Unknown drift method: {method_name}")
            return profile, None

        if not _trigger_satisfied(checkfile, profile, selected_papers):
            return profile, None

        drift_func = self.DRIFT_METHODS[method_name]
        params = checkfile.get("params", {})

        updated_profile, drift_event = drift_func(profile, params, selected_papers, date)

        # 娣诲姞鍏冩暟鎹?
        drift_event["date"] = date
        drift_event["checkfile_name"] = checkfile.get("name", "unknown")
        drift_event["checkfile"] = checkfile.get("_source_file", "")

        self.drift_history.append(drift_event)

        return updated_profile, drift_event


# ==================== 宸ュ叿鍑芥暟 ====================

def _update_drift_state(
    profile: Dict[str, Any],
    date: Optional[str],
    score_delta: float = 0.2,
) -> Dict[str, Any]:
    """
    鏇存柊鍥涢樁娈垫紓绉绘祦绋嬶細
    stable -> shifting -> recovered -> stable
    姝ｅ悜婕傜Щ鎻愬崌 score锛屾仮澶嶈繃绋嬮檷浣?score銆?    """
    drift_state = profile.get("drift_state", {}) or {}
    old_score = float(drift_state.get("score", 0) or 0)
    old_status = str(drift_state.get("status") or "stable")
    new_score = max(0.0, min(1.0, old_score + score_delta))

    if score_delta >= 0:
        status = "shifting" if new_score >= DRIFT_SHIFT_THRESHOLD else "stable"
    else:
        if old_status == "shifting":
            status = "stable" if new_score <= DRIFT_STABLE_THRESHOLD else "recovered"
        elif old_status == "recovered":
            status = "stable" if new_score <= DRIFT_STABLE_THRESHOLD else "recovered"
        else:
            status = "stable"

    final_score = 0.0 if status == "stable" else round(new_score, 2)
    return {
        "status": status,
        "score": final_score,
        "last_drift_date": date,
    }


def to_display_drift_status(status: Optional[str]) -> str:
    normalized = str(status or "stable").strip() or "stable"
    return normalized


def create_drift_event(
    user_id: str,
    date: str,
    drift_event: Dict[str, Any],
    profile_before: Dict[str, Any],
    profile_after: Dict[str, Any],
) -> Dict[str, Any]:
    """创建完整的漂移事件记录"""
    before_state = profile_before.get("drift_state", {}) or {}
    after_state = profile_after.get("drift_state", {}) or {}
    before_status = before_state.get("status", "stable")
    after_status = after_state.get("status", "stable")
    raw_transition = f"{before_status} → {after_status}"
    display_before_status = to_display_drift_status(before_status)
    display_status = to_display_drift_status(after_status)
    display_transition = f"{display_before_status} → {display_status}"
    display_score = 0.0 if display_status == "stable" else float(after_state.get("score", 0.0) or 0.0)

    return {
        "timestamp": f"{date}T{datetime.now().strftime('%H:%M:%S')}",
        "event_type": drift_event.get("event_type", "drift"),
        "user_id": user_id,
        "date": date,
        "transition": display_transition,
        "display_transition": display_transition,
        "display_status": display_status,
        "display_score": round(display_score, 2),
        "internal_transition": raw_transition,
        "internal_status": after_status,
        "score_delta": after_state.get("score", 0) - before_state.get("score", 0),
        **drift_event,
    }
