#!/usr/bin/env python3
"""
ColdStart Agent

Bootstraps and incrementally updates a user's academic profile from:
- natural language self-description
- uploaded PDFs
- future scholar links
"""

import copy
import html
import hashlib
import importlib
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import requests

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ROLE_META_PATH = PROJECT_ROOT / "data" / "roles.json"
sys.path.insert(0, str(PROJECT_ROOT))

db_ops = importlib.import_module("skills.storage-helper.scripts.db_ops")
create_profile = db_ops.create_profile
update_profile = db_ops.update_profile
get_profile = db_ops.get_profile
profile_updater = importlib.import_module("skills.profile-updater.scripts.update_profile")
build_default_drift_state = profile_updater.build_default_drift_state

pdf_parser = importlib.import_module("skills.pdf-parser.scripts.parse_pdf")
parse_paper_for_coldstart = pdf_parser.parse_paper_for_coldstart

feishu_reporter = importlib.import_module("deployments.feishu.feishu-reporter.scripts.feishu_reporter")


DIRECTION_KEYWORDS = {
    "gui-agent": ["gui agent", "gui", "interface agent", "computer use", "screen agent", "action agent"],
    "multimodal-reasoning": ["multimodal", "vision-language", "vision and language", "cross-modal"],
    "vision": ["vision", "visual", "image", "video", "cv", "computer vision"],
    "language": ["language", "llm", "nlp", "text", "transformer"],
    "machine-learning": ["machine learning", "ml", "classification", "regression"],
    "deep-learning": ["deep learning", "neural", "cnn", "transformer"],
    "reinforcement-learning": ["reinforcement", "rl", "reward", "policy", "actor", "critic"],
    "reasoning": ["reasoning", "chain of thought", "cot", "thought"],
    "agent": ["agent", "agents", "autonomous"],
    "optimization": ["optimization", "optimize", "efficient", "optimizer"],
    "retrieval": ["retrieval", "retrieve", "search", "rag"],
    "generation": ["generation", "generate", "diffusion", "generative"],
    "data-native": ["data-native", "data native", "data-centric", "data centric", "infrastructure"],
    "bio-molecular": ["bio", "protein", "molecular", "drug", "compound", "molecule"],
    "science-discovery": ["scientific", "science", "discovery", "hypothesis"],
}

METHODOLOGY_KEYWORDS = {
    "data_driven": [
        "data-driven",
        "empirical",
        "experimental",
        "large-scale",
        "data-native",
        "data native",
        "dataset",
        "infrastructure",
    ],
    "theory": ["theoretical", "theory", "analysis", "proof"],
    "systematic": ["systematic", "comprehensive", "benchmark", "framework", "infrastructure", "platform", "map", "graph"],
    "incremental": ["improvement", "enhancement", "better", "incremental"],
    "open_source": ["open source", "opensource", "code available", "github"],
    "application": ["application", "applied", "real-world", "case study"],
}

BASELINE_PDF_ENV_VAR = "PAPERFLOW_BASELINE_PDF"
PDF_DIRECTION_WEIGHT_CAP = 0.70
PDF_INCREMENT_BLEND = 0.25
PDF_NEW_DIRECTION_CAP = 0.55
PDF_NEW_DIRECTION_SCALE = 0.85
TEXT_INCREMENT_BLEND = 0.35
TEXT_NEW_DIRECTION_CAP = 0.65
SCHOLAR_TIMEOUT_SECONDS = 20
SCHOLAR_PUBLICATION_LIMIT = 12
SCHOLAR_MAX_PAGES = 3
HOMEPAGE_TIMEOUT_SECONDS = 20
BOOTSTRAP_MAX_CORE_DIRECTIONS = 6
BOOTSTRAP_PUBLICATION_CAP = 0.45
GENERIC_PUBLICATION_DIRECTIONS = {
    "vision",
    "language",
    "machine-learning",
    "deep-learning",
    "generation",
    "optimization",
    "reasoning",
    "retrieval",
    "science-discovery",
}
SCHOLAR_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}
COLD_START_COMMAND_HINTS = {"冷启动", "重新冷启动", "cold start", "cold-start"}
COLD_START_MUST_READ_NOTE = "说明：普通“冷启动”会保留这份必读清单；只有“重新冷启动”才会重置。"
CLEAR_READING_LIST_HINT = '  "清空精读列表"'


def build_empty_profile(user_id: str) -> Dict[str, Any]:
    """Create an empty profile payload with the full schema."""
    now = datetime.now().isoformat()
    return {
        "user_id": user_id,
        "version": "0.1",
        "created_at": now,
        "updated_at": now,
        "core_directions": {},
        "methodology_preferences": {},
        "must_read": {
            "authors": [],
            "institutions": [],
            "keywords": [],
        },
        "topic_weights": {},
        "author_heat": {},
        "institution_heat": {},
        "interest_vector": [],
        "taste_profile": {},
        "reading_history": [],
        "behavior_logs": [],
        "drift_state": build_default_drift_state(now),
    }


def ensure_profile_shape(profile: Optional[Dict[str, Any]], user_id: str) -> Dict[str, Any]:
    """Normalize a stored profile into the current schema."""
    normalized = copy.deepcopy(profile) if profile else build_empty_profile(user_id)
    normalized["user_id"] = user_id
    normalized.setdefault("version", "0.1")
    normalized.setdefault("created_at", normalized.get("updated_at", datetime.now().isoformat()))
    normalized["updated_at"] = datetime.now().isoformat()

    for key in ("core_directions", "methodology_preferences", "topic_weights", "author_heat", "institution_heat", "taste_profile"):
        value = normalized.get(key)
        normalized[key] = value if isinstance(value, dict) else {}

    must_read = normalized.get("must_read")
    normalized["must_read"] = must_read if isinstance(must_read, dict) else {}
    for key in ("authors", "institutions", "keywords"):
        value = normalized["must_read"].get(key)
        normalized["must_read"][key] = value if isinstance(value, list) else []

    for key in ("interest_vector", "reading_history", "behavior_logs"):
        value = normalized.get(key)
        normalized[key] = value if isinstance(value, list) else []

    drift_state = normalized.get("drift_state")
    normalized["drift_state"] = drift_state if isinstance(drift_state, dict) else {}
    for key, default_value in build_default_drift_state(normalized["updated_at"]).items():
        normalized["drift_state"].setdefault(key, copy.deepcopy(default_value))

    raw_core_directions = dict(normalized.get("core_directions") or {})
    raw_topic_weights = dict(normalized.get("topic_weights") or {})
    normalized["core_directions"] = _normalize_direction_weight_map(raw_core_directions)
    normalized["topic_weights"] = _normalize_direction_weight_map(raw_topic_weights)

    if normalized["core_directions"] and normalized["core_directions"] != raw_core_directions:
        normalized["interest_vector"] = generate_interest_vector(normalized["core_directions"])

    return normalized


def _normalize_direction_weight_map(raw_weights: Any) -> Dict[str, float]:
    """Collapse duplicate direction aliases into canonical keys while preserving unknown topics."""
    if not isinstance(raw_weights, dict):
        return {}

    try:
        direction_lexicon = importlib.import_module("config.direction_lexicon")
        resolve_canonical_direction = getattr(direction_lexicon, "resolve_canonical_direction", None)
    except Exception:
        resolve_canonical_direction = None

    normalized: Dict[str, float] = {}
    for raw_key, raw_weight in raw_weights.items():
        key_text = _collapse_whitespace(raw_key)
        if not key_text:
            continue
        try:
            weight = round(float(raw_weight or 0.0), 4)
        except (TypeError, ValueError):
            continue

        canonical_key = key_text
        if callable(resolve_canonical_direction):
            try:
                resolved = resolve_canonical_direction(key_text, include_paper_terms=True)
            except Exception:
                resolved = None
            canonical_key = str((resolved or {}).get("canonical_name") or key_text).strip() or key_text

        normalized[canonical_key] = round(max(float(normalized.get(canonical_key, 0.0)), weight), 4)

    return normalized


def _resolve_role_meta_path() -> Path:
    """Return the role metadata path as a Path object."""
    return Path(str(ROLE_META_PATH))


def _load_roles_meta() -> Dict[str, Any]:
    """Load role metadata when available."""
    roles_path = _resolve_role_meta_path()
    if roles_path.exists():
        with open(roles_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"roles": {}, "current_role": None}


def _save_roles_meta(meta: Dict[str, Any]) -> None:
    """Persist role metadata to disk."""
    roles_path = _resolve_role_meta_path()
    roles_path.parent.mkdir(parents=True, exist_ok=True)
    with open(roles_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def _find_role_entry_by_user_id(meta: Dict[str, Any], user_id: str) -> Optional[tuple[str, Dict[str, Any]]]:
    """Find the role entry that belongs to a given profile user."""
    for role_name, role_info in (meta.get("roles") or {}).items():
        if str(role_info.get("user_id") or "").strip() == str(user_id or "").strip():
            return role_name, role_info
    return None


def _direction_to_seed_phrase(direction_key: str) -> str:
    """Turn a canonical direction key into reusable bootstrap text."""
    try:
        direction_lexicon = importlib.import_module("config.direction_lexicon")
        return str(direction_lexicon.format_direction_label(direction_key, prefer_chinese=False) or "").strip()
    except Exception:
        cleaned = str(direction_key or "").strip()
        if not cleaned:
            return ""
        return cleaned.replace("_", " ").replace("-", " ")


def _build_seed_directions(profile: Dict[str, Any], limit: int = 8) -> List[Dict[str, Any]]:
    """Serialize the strongest directions back into role metadata."""
    try:
        direction_lexicon = importlib.import_module("config.direction_lexicon")
    except Exception:
        direction_lexicon = None

    items = sorted(
        (profile.get("core_directions") or {}).items(),
        key=lambda item: (-float(item[1]), str(item[0])),
    )
    result: List[Dict[str, Any]] = []
    for direction_key, weight in items[:limit]:
        if not direction_key:
            continue
        entry = (
            direction_lexicon.get_direction_entry(direction_key)
            if direction_lexicon and hasattr(direction_lexicon, "get_direction_entry")
            else None
        )
        result.append(
            {
                "canonical_name": direction_key,
                "name": str((entry or {}).get("name") or _direction_to_seed_phrase(direction_key)).strip(),
                "name_cn": str((entry or {}).get("name_cn") or (entry or {}).get("name") or _direction_to_seed_phrase(direction_key)).strip(),
                "bootstrap_phrase": _direction_to_seed_phrase(direction_key),
                "weight": round(float(weight or 0.0), 4),
            }
        )
    return result


def _build_role_bootstrap_summary(
    profile: Dict[str, Any],
    *,
    explicit_text: Optional[str] = None,
    seed_directions: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Build a reusable bootstrap summary for future cold starts."""
    cleaned_explicit = re.sub(r"\s+", " ", str(explicit_text or "")).strip()
    if cleaned_explicit and cleaned_explicit.lower() not in COLD_START_COMMAND_HINTS:
        return cleaned_explicit

    directions = seed_directions or _build_seed_directions(profile)
    try:
        direction_lexicon = importlib.import_module("config.direction_lexicon")
        phrases = [str(entry.get("canonical_name") or "").strip() for entry in directions if entry.get("canonical_name")]
        return direction_lexicon.build_bootstrap_summary(phrases, prefer_chinese=False, limit=6)
    except Exception:
        phrases = [str(entry.get("bootstrap_phrase") or "").strip() for entry in directions if entry.get("bootstrap_phrase")]
        if not phrases:
            return ""
        return f"direction: {', '.join(phrases[:6])}"


def sync_role_metadata_from_cold_start(
    user_id: str,
    profile: Dict[str, Any],
    *,
    explicit_text: Optional[str] = None,
    scholar_url: Optional[str] = None,
    homepage_url: Optional[str] = None,
    scholar_result: Optional[Dict[str, Any]] = None,
    homepage_result: Optional[Dict[str, Any]] = None,
) -> bool:
    """Write structured cold-start seed data back into roles.json for the matching role."""
    roles_meta = _load_roles_meta()
    role_match = _find_role_entry_by_user_id(roles_meta, user_id)
    if not role_match:
        return False

    role_name, role_info = role_match
    changed = False
    seed_directions = _build_seed_directions(profile)
    bootstrap_summary = _build_role_bootstrap_summary(
        profile,
        explicit_text=explicit_text,
        seed_directions=seed_directions,
    )

    if bootstrap_summary and role_info.get("bootstrap_summary") != bootstrap_summary:
        role_info["bootstrap_summary"] = bootstrap_summary
        changed = True

    if not str(role_info.get("description") or "").strip() and bootstrap_summary:
        role_info["description"] = bootstrap_summary
        changed = True

    if seed_directions and role_info.get("seed_directions") != seed_directions:
        role_info["seed_directions"] = seed_directions
        changed = True

    for obsolete_key in ("scholar_url", "homepage_url", "scholar_seed", "homepage_seed"):
        if obsolete_key in role_info:
            del role_info[obsolete_key]
            changed = True

    if not changed:
        return False

    role_info["cold_start_updated_at"] = datetime.now().isoformat()
    roles_meta.setdefault("roles", {})[role_name] = role_info
    _save_roles_meta(roles_meta)
    return True


def resolve_baseline_pdf_path(user_id: str) -> Optional[str]:
    """Return the configured baseline PDF for the given user."""
    candidate_paths: List[Path] = []

    configured = os.environ.get(BASELINE_PDF_ENV_VAR)
    if configured:
        candidate_paths.append(Path(configured).expanduser())

    if user_id == "user_rolea":
        candidate_paths.append(Path.home() / "Desktop" / "Research Infra.pdf")

    for candidate in candidate_paths:
        if candidate.exists():
            return str(candidate)

    return None


def _blend_weight(
    existing_weight: float,
    incoming_weight: float,
    blend: float,
    new_direction_cap: float,
    new_direction_scale: float,
) -> float:
    """Blend a new signal into an existing direction without letting one PDF dominate."""
    incoming = min(max(float(incoming_weight or 0.0), 0.0), PDF_DIRECTION_WEIGHT_CAP)
    existing = max(float(existing_weight or 0.0), 0.0)

    if existing > 0:
        blended = existing + blend * (incoming - existing)
        return round(max(existing, min(PDF_DIRECTION_WEIGHT_CAP, blended)), 4)

    seeded = min(PDF_DIRECTION_WEIGHT_CAP, incoming * new_direction_scale, new_direction_cap)
    return round(seeded, 4)


def _apply_full_text_methodology_hints(profile: Dict[str, Any], result: Dict[str, Any]) -> None:
    """Use explicit PDF phrases as extra methodology hints."""
    full_text = (result.get("full_text") or "").lower()

    if any(keyword in full_text for keyword in ("dataset", "data-driven", "empirical", "experiment", "benchmark")):
        profile["methodology_preferences"]["preference_data_driven_over_theory"] = True

    if any(keyword in full_text for keyword in ("framework", "system", "comprehensive", "benchmark", "pipeline", "platform")):
        profile["methodology_preferences"]["preference_systematic_work_over_incremental"] = True

    if any(keyword in full_text for keyword in ("github", "open source", "code available", "code release")):
        profile["methodology_preferences"]["preference_open_source_code"] = True

    if any(keyword in full_text for keyword in ("bio", "protein", "molecular", "drug", "scientific", "computational biology")):
        profile["methodology_preferences"]["preference_bio_science_application"] = True


def merge_parsed_profile_into_profile(
    profile: Dict[str, Any],
    parsed: Dict[str, Any],
    blend: float = TEXT_INCREMENT_BLEND,
    new_direction_cap: float = TEXT_NEW_DIRECTION_CAP,
) -> None:
    """Merge natural-language signals into an existing profile."""
    normalized_profile = ensure_profile_shape(profile, profile.get("user_id", "user_001"))
    profile.clear()
    profile.update(normalized_profile)

    for direction_key, weight in (parsed.get("core_directions") or {}).items():
        merged_weight = _blend_weight(
            existing_weight=profile["core_directions"].get(direction_key, 0.0),
            incoming_weight=weight,
            blend=blend,
            new_direction_cap=new_direction_cap,
            new_direction_scale=1.0,
        )
        if merged_weight > 0:
            profile["core_directions"][direction_key] = merged_weight
            profile["topic_weights"][direction_key] = max(
                merged_weight,
                float(profile["topic_weights"].get(direction_key, 0.0)),
            )

    for key, value in (parsed.get("methodology_preferences") or {}).items():
        if value is None:
            continue
        profile["methodology_preferences"][key] = bool(value)

    for topic_key, weight in (parsed.get("topic_weights") or {}).items():
        existing_weight = float(profile["topic_weights"].get(topic_key, 0.0))
        incoming_weight = min(float(weight or 0.0), new_direction_cap)
        profile["topic_weights"][topic_key] = round(max(existing_weight, incoming_weight), 4)

    for author, weight in (parsed.get("author_heat") or {}).items():
        if not author:
            continue
        existing_weight = float(profile["author_heat"].get(author, 0.0))
        profile["author_heat"][author] = round(max(existing_weight, float(weight or 0.0)), 4)

    for institution, weight in (parsed.get("institution_heat") or {}).items():
        if not institution:
            continue
        existing_weight = float(profile["institution_heat"].get(institution, 0.0))
        profile["institution_heat"][institution] = round(max(existing_weight, float(weight or 0.0)), 4)

    if not profile["interest_vector"] and parsed.get("interest_vector"):
        profile["interest_vector"] = parsed["interest_vector"]

    parsed_taste_profile = parsed.get("taste_profile") or {}
    for key, values in parsed_taste_profile.items():
        if not isinstance(values, list):
            continue
        current_values = profile["taste_profile"].setdefault(key, [])
        for value in values:
            if value not in current_values:
                current_values.append(value)


def merge_pdf_result_into_profile(profile: Dict[str, Any], result: Dict[str, Any]) -> None:
    """Merge a parsed PDF result into the existing profile conservatively."""
    normalized_profile = ensure_profile_shape(profile, profile.get("user_id", "user_001"))
    profile.clear()
    profile.update(normalized_profile)

    for direction in result.get("research_directions", []):
        name = direction.get("name", "")
        direction_key = name.lower().replace(" ", "-")
        if not direction_key:
            continue

        merged_weight = _blend_weight(
            existing_weight=profile["core_directions"].get(direction_key, 0.0),
            incoming_weight=direction.get("confidence", 0.0),
            blend=PDF_INCREMENT_BLEND,
            new_direction_cap=PDF_NEW_DIRECTION_CAP,
            new_direction_scale=PDF_NEW_DIRECTION_SCALE,
        )
        if merged_weight > 0:
            profile["core_directions"][direction_key] = merged_weight
            profile["topic_weights"][direction_key] = max(
                merged_weight,
                float(profile["topic_weights"].get(direction_key, 0.0)),
            )

    for key, value in (result.get("methodology_preferences") or {}).items():
        if value:
            profile["methodology_preferences"][key] = True

    for topic in result.get("inferred_topics", []):
        topic_key = topic.lower().replace(" ", "-")
        if not topic_key:
            continue

        existing_weight = float(profile["topic_weights"].get(topic_key, 0.0))
        if existing_weight > 0:
            profile["topic_weights"][topic_key] = round(min(0.6, existing_weight + 0.08), 4)
        else:
            profile["topic_weights"][topic_key] = 0.30

    _apply_full_text_methodology_hints(profile, result)


def _seed_profile_from_baseline_pdf(profile: Dict[str, Any], user_id: str) -> Optional[str]:
    """Initialize an empty profile from the configured baseline PDF."""
    if profile.get("core_directions"):
        return None

    baseline_pdf_path = resolve_baseline_pdf_path(user_id)
    if not baseline_pdf_path:
        return None

    result = parse_paper_for_coldstart(baseline_pdf_path)
    for direction in result.get("research_directions", []):
        direction_key = direction.get("name", "").lower().replace(" ", "-")
        confidence = min(float(direction.get("confidence", 0.0)), PDF_DIRECTION_WEIGHT_CAP)
        if direction_key and confidence > 0:
            profile["core_directions"][direction_key] = round(confidence, 4)
            profile["topic_weights"][direction_key] = round(confidence, 4)

    for key, value in (result.get("methodology_preferences") or {}).items():
        if value:
            profile["methodology_preferences"][key] = True

    for topic in result.get("inferred_topics", []):
        topic_key = topic.lower().replace(" ", "-")
        if topic_key and topic_key not in profile["topic_weights"]:
            profile["topic_weights"][topic_key] = 0.35

    _apply_full_text_methodology_hints(profile, result)
    return baseline_pdf_path


def _empty_parsed_profile_fragment() -> Dict[str, Any]:
    """Return an empty parse result for command-only bootstrap text."""
    return {
        "core_directions": {},
        "methodology_preferences": {},
        "topic_weights": {},
        "interest_vector": [],
        "taste_profile": {},
        "inferred_topics": [],
    }


def _get_env_int(name: str, default: int) -> int:
    """Read an integer env var without failing the cold-start flow."""
    raw = str(os.environ.get(name, "")).strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _collapse_whitespace(value: Any) -> str:
    """Normalize arbitrary text into a single-line string."""
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _strip_html(value: str) -> str:
    """Convert a small HTML fragment into plain text."""
    if not value:
        return ""
    without_scripts = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", value)
    plain = re.sub(r"(?s)<[^>]+>", " ", without_scripts)
    return _collapse_whitespace(html.unescape(plain))


def _extract_first_group(pattern: str, text: str) -> str:
    """Return the first non-empty capture group for a regex search."""
    match = re.search(pattern, text or "", re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    for group in match.groups():
        if group:
            return group
    return match.group(0)


def _build_scholar_profile_url(
    scholar_url: str,
    *,
    cstart: int = 0,
    pagesize: Optional[int] = None,
    hl: str = "en",
) -> str:
    """Normalize a Scholar profile URL and request a larger publication page size."""
    candidate = _collapse_whitespace(scholar_url)
    if not candidate:
        raise ValueError("empty scholar url")
    if "://" not in candidate:
        candidate = f"https://{candidate.lstrip('/')}"

    parsed = urlsplit(candidate)
    if not parsed.netloc:
        raise ValueError("invalid scholar url")

    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["hl"] = hl or query.get("hl") or "en"
    query["cstart"] = str(max(0, int(cstart)))
    resolved_page_size = pagesize or _get_env_int("PAPERFLOW_SCHOLAR_PAGE_SIZE", 100)
    query["pagesize"] = str(max(20, int(resolved_page_size)))

    return urlunsplit(
        (
            parsed.scheme or "https",
            parsed.netloc,
            parsed.path or "/citations",
            urlencode(query),
            parsed.fragment,
        )
    )


def _parse_scholar_stats(html_text: str) -> Dict[str, int]:
    """Extract profile-level citation stats when the sidebar table is available."""
    stats: Dict[str, int] = {}
    row_pattern = (
        r'<tr[^>]*>\s*'
        r'<td[^>]*class=["\'][^"\']*\bgsc_rsb_sc1\b[^"\']*["\'][^>]*>(.*?)</td>\s*'
        r'<td[^>]*class=["\'][^"\']*\bgsc_rsb_std\b[^"\']*["\'][^>]*>(.*?)</td>'
    )
    for match in re.finditer(row_pattern, html_text or "", re.IGNORECASE | re.DOTALL):
        label = _strip_html(match.group(1)).lower().replace(" ", "_")
        value_match = re.search(r"\d+", _strip_html(match.group(2)))
        if label and value_match:
            stats[label] = int(value_match.group(0))
    return stats


def _parse_author_names(author_line: str, scholar_name: str = "") -> List[str]:
    """Split a Scholar author line into coauthor names."""
    normalized_line = _collapse_whitespace(author_line)
    if not normalized_line:
        return []

    splitter = re.sub(r"\s+(?:and|&)\s+", ",", normalized_line, flags=re.IGNORECASE)
    candidates = [segment.strip() for segment in re.split(r"[;,]", splitter) if segment.strip()]
    def _normalize_person_name(value: str) -> str:
        cleaned = _collapse_whitespace(value)
        cleaned = re.sub(r"^(?:dr|prof|professor)\.?\s+", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"[^\w\u4e00-\u9fff]+", " ", cleaned, flags=re.UNICODE)
        return _collapse_whitespace(cleaned).casefold()

    normalized_scholar_name = _normalize_person_name(scholar_name)

    names: List[str] = []
    for candidate in candidates:
        cleaned = re.sub(r"\b(?:et al\.?|…)\b", "", candidate, flags=re.IGNORECASE).strip()
        if not cleaned:
            continue
        if normalized_scholar_name and _normalize_person_name(cleaned) == normalized_scholar_name:
            continue
        if re.fullmatch(r"[\d\W_]+", cleaned):
            continue
        names.append(cleaned)
    return names


def _build_scholar_network_signals(publications: List[Dict[str, Any]], scholar_name: str = "") -> Dict[str, Any]:
    """Aggregate richer Scholar collaboration and citation signals."""
    coauthor_counter: Counter[str] = Counter()
    venue_counter: Counter[str] = Counter()
    coauthor_stats: Dict[str, Dict[str, Any]] = {}

    for publication in publications or []:
        citation_count = int(publication.get("citations") or 0)
        year = int(publication.get("year") or 0)
        venue = _collapse_whitespace(publication.get("venue", ""))
        title = _collapse_whitespace(publication.get("title", ""))

        if venue:
            venue_counter[venue] += 1

        for author_name in _parse_author_names(publication.get("authors", ""), scholar_name=scholar_name):
            coauthor_counter[author_name] += 1
            stats = coauthor_stats.setdefault(
                author_name,
                {
                    "count": 0,
                    "citation_sum": 0,
                    "last_year": 0,
                    "venues": Counter(),
                    "sample_titles": [],
                },
            )
            stats["count"] += 1
            stats["citation_sum"] += citation_count
            stats["last_year"] = max(int(stats.get("last_year") or 0), year)
            if venue:
                stats["venues"][venue] += 1
            if title and title not in stats["sample_titles"]:
                stats["sample_titles"].append(title)

    collaboration_network = []
    for author_name, stats in coauthor_stats.items():
        top_venues = [venue for venue, _ in stats["venues"].most_common(3)]
        collaboration_network.append(
            {
                "name": author_name,
                "count": int(stats["count"]),
                "citation_sum": int(stats["citation_sum"]),
                "last_year": int(stats["last_year"] or 0),
                "top_venues": top_venues,
                "sample_titles": list(stats["sample_titles"][:2]),
            }
        )

    collaboration_network.sort(
        key=lambda item: (
            int(item.get("count") or 0),
            int(item.get("citation_sum") or 0),
            int(item.get("last_year") or 0),
        ),
        reverse=True,
    )

    top_cited_publications = sorted(
        publications or [],
        key=lambda item: (
            int(item.get("citations") or 0),
            int(item.get("year") or 0),
            len(str(item.get("title") or "")),
        ),
        reverse=True,
    )[:5]

    return {
        "top_coauthors": [{"name": author, "count": count} for author, count in coauthor_counter.most_common(5)],
        "top_venues": [{"name": venue, "count": count} for venue, count in venue_counter.most_common(5)],
        "collaboration_network": collaboration_network[:8],
        "top_cited_publications": [
            {
                "title": str(item.get("title") or "").strip(),
                "citations": int(item.get("citations") or 0),
                "year": int(item.get("year") or 0) if item.get("year") else None,
                "venue": str(item.get("venue") or "").strip(),
                "authors": str(item.get("authors") or "").strip(),
            }
            for item in top_cited_publications
            if str(item.get("title") or "").strip()
        ],
    }


def _is_probable_scholar_block_page(html_text: str) -> bool:
    """Detect common anti-bot / captcha pages returned by Scholar."""
    normalized = (html_text or "").casefold()
    block_markers = (
        "unusual traffic",
        "not a robot",
        "detected unusual traffic",
        "sorry...",
        "captcha",
        "/sorry/",
        "recaptcha",
    )
    return any(marker in normalized for marker in block_markers)


def _build_scholar_fallback_excerpt(html_text: str) -> str:
    """Extract a small text excerpt when the structured page cannot be parsed."""
    title = _strip_html(_extract_first_group(r"<title[^>]*>(.*?)</title>", html_text))
    description = _strip_html(
        _extract_first_group(
            r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']',
            html_text,
        )
    )
    body_excerpt = _collapse_whitespace(_strip_html(html_text))[:600]
    return " ".join(part for part in (title, description, body_excerpt) if part).strip()


def _extract_external_homepage_url(html_text: str, base_url: str = "") -> str:
    """Return the first plausible external homepage URL from an HTML page."""
    for match in re.finditer(r'<a\b[^>]*href=["\'](.*?)["\']', html_text or "", re.IGNORECASE | re.DOTALL):
        raw_href = html.unescape(_collapse_whitespace(match.group(1)))
        if not raw_href:
            continue
        resolved = urljoin(base_url or "", raw_href)
        parsed = urlsplit(resolved)
        if parsed.scheme not in {"http", "https"}:
            continue
        netloc = (parsed.netloc or "").casefold()
        if not netloc or "scholar.google." in netloc or "google." == netloc:
            continue
        if any(token in resolved.casefold() for token in ("/citations?", "/scholar?", "view_op=")):
            continue
        return resolved
    return ""


def _parse_google_scholar_profile_html(html_text: str) -> Dict[str, Any]:
    """Extract lightweight Scholar metadata from a profile page."""
    name = _strip_html(_extract_first_group(r'<div[^>]*id=["\']gsc_prf_in["\'][^>]*>(.*?)</div>', html_text))
    affiliation = _strip_html(
        _extract_first_group(r'<div[^>]*class=["\'][^"\']*\bgsc_prf_il\b[^"\']*["\'][^>]*>(.*?)</div>', html_text)
    )

    interests_block = _extract_first_group(r'<div[^>]*id=["\']gsc_prf_int["\'][^>]*>(.*?)</div>', html_text)
    interests = [
        interest
        for interest in (
            _strip_html(match.group(1))
            for match in re.finditer(r"<a\b[^>]*>(.*?)</a>", interests_block or "", re.IGNORECASE | re.DOTALL)
        )
        if interest
    ]

    publications: List[Dict[str, Any]] = []
    row_pattern = r'<tr[^>]*class=["\'][^"\']*\bgsc_a_tr\b[^"\']*["\'][^>]*>(.*?)</tr>'
    for row_match in re.finditer(row_pattern, html_text or "", re.IGNORECASE | re.DOTALL):
        row_html = row_match.group(1)
        title = _strip_html(
            _extract_first_group(r'<a[^>]*class=["\'][^"\']*\bgsc_a_at\b[^"\']*["\'][^>]*>(.*?)</a>', row_html)
        )
        if not title:
            continue

        gray_blocks = [
            _strip_html(block.group(1))
            for block in re.finditer(
                r'<div[^>]*class=["\'][^"\']*\bgs_gray\b[^"\']*["\'][^>]*>(.*?)</div>',
                row_html,
                re.IGNORECASE | re.DOTALL,
            )
        ]
        citations_text = _strip_html(
            _extract_first_group(r'<a[^>]*class=["\'][^"\']*\bgsc_a_ac\b[^"\']*["\'][^>]*>(.*?)</a>', row_html)
        )
        year_block = _extract_first_group(r'<td[^>]*class=["\'][^"\']*\bgsc_a_y\b[^"\']*["\'][^>]*>(.*?)</td>', row_html)
        citations_match = re.search(r"\d+", citations_text)
        year_match = re.search(r"\b(19|20)\d{2}\b", _strip_html(year_block))

        publications.append(
            {
                "title": title,
                "authors": gray_blocks[0] if gray_blocks else "",
                "venue": gray_blocks[1] if len(gray_blocks) > 1 else "",
                "citations": int(citations_match.group(0)) if citations_match else 0,
                "year": int(year_match.group(0)) if year_match else None,
            }
        )

    publications.sort(
        key=lambda item: (
            int(item.get("citations") or 0),
            int(item.get("year") or 0),
            len(str(item.get("title") or "")),
        ),
        reverse=True,
    )

    network_signals = _build_scholar_network_signals(publications, scholar_name=name)

    return {
        "name": name,
        "affiliation": affiliation,
        "homepage_url": _extract_external_homepage_url(html_text),
        "interests": interests,
        "publications": publications[: max(1, _get_env_int("PAPERFLOW_SCHOLAR_PUBLICATION_LIMIT", SCHOLAR_PUBLICATION_LIMIT))],
        "all_publications": publications,
        "stats": _parse_scholar_stats(html_text),
        "top_coauthors": list(network_signals.get("top_coauthors") or []),
        "top_venues": list(network_signals.get("top_venues") or []),
        "collaboration_network": list(network_signals.get("collaboration_network") or []),
        "top_cited_publications": list(network_signals.get("top_cited_publications") or []),
        "blocked": _is_probable_scholar_block_page(html_text),
    }


def _dedupe_preserve_order(values: List[str]) -> List[str]:
    result: List[str] = []
    seen = set()
    for value in values:
        cleaned = _collapse_whitespace(value)
        if not cleaned:
            continue
        marker = cleaned.casefold()
        if marker in seen:
            continue
        seen.add(marker)
        result.append(cleaned)
    return result


def _filter_parsed_profile_fragment(
    parsed: Dict[str, Any],
    *,
    max_core_directions: int = 3,
    core_cap: float = 0.9,
    blocked_directions: Optional[set[str]] = None,
    preferred_directions: Optional[set[str]] = None,
) -> Dict[str, Any]:
    blocked = set(blocked_directions or set())
    preferred = set(preferred_directions or set())

    core_items = sorted(
        (parsed.get("core_directions") or {}).items(),
        key=lambda item: (-float(item[1]), str(item[0])),
    )
    filtered_core: Dict[str, float] = {}
    for direction, weight in core_items:
        if direction in blocked and direction not in preferred:
            continue
        filtered_core[direction] = round(min(float(weight or 0.0), core_cap), 4)
        if len(filtered_core) >= max_core_directions:
            break

    filtered_topics: Dict[str, float] = {}
    for direction, weight in (parsed.get("topic_weights") or {}).items():
        numeric_weight = round(min(float(weight or 0.0), core_cap), 4)
        if direction in filtered_core:
            filtered_topics[direction] = max(filtered_topics.get(direction, 0.0), numeric_weight)
        elif direction not in blocked and direction in preferred and numeric_weight > 0:
            filtered_topics[direction] = max(filtered_topics.get(direction, 0.0), numeric_weight)

    return {
        "core_directions": filtered_core,
        "methodology_preferences": dict(parsed.get("methodology_preferences") or {}),
        "topic_weights": filtered_topics,
        "interest_vector": generate_interest_vector(filtered_core) if filtered_core else [],
        "taste_profile": dict(parsed.get("taste_profile") or {}),
        "inferred_topics": list(parsed.get("inferred_topics") or []),
        "direction_explanations": list(parsed.get("direction_explanations") or []),
        "pending_directions": list(parsed.get("pending_directions") or []),
    }


def _trim_bootstrap_profile(profile: Dict[str, Any]) -> None:
    core_items = sorted(
        (profile.get("core_directions") or {}).items(),
        key=lambda item: (-float(item[1]), str(item[0])),
    )
    kept_core = dict(core_items[:BOOTSTRAP_MAX_CORE_DIRECTIONS])
    kept_keys = set(kept_core)

    profile["core_directions"] = kept_core
    profile["topic_weights"] = {
        key: float(value)
        for key, value in sorted(
            (profile.get("topic_weights") or {}).items(),
            key=lambda item: (-float(item[1]), str(item[0])),
        )
        if key in kept_keys or float(value or 0.0) >= 0.35
    }
    profile["interest_vector"] = generate_interest_vector(kept_core) if kept_core else []


def _build_bootstrap_fragment_from_structured_sources(
    *,
    explicit_texts: Optional[List[str]] = None,
    secondary_texts: Optional[List[str]] = None,
    publication_titles: Optional[List[str]] = None,
    use_llm: bool = True,
) -> Dict[str, Any]:
    fragment = build_empty_profile("structured_bootstrap")
    explicit_direction_keys: set[str] = set()

    for raw_text in _dedupe_preserve_order(list(explicit_texts or [])):
        parsed = parse_natural_language(raw_text, use_llm=use_llm)
        filtered = _filter_parsed_profile_fragment(
            parsed,
            max_core_directions=2,
            core_cap=0.92,
        )
        if not filtered["core_directions"]:
            continue
        explicit_direction_keys.update(filtered["core_directions"].keys())
        merge_parsed_profile_into_profile(
            fragment,
            filtered,
            blend=0.60,
            new_direction_cap=0.90,
        )

    for raw_text in _dedupe_preserve_order(list(secondary_texts or [])):
        parsed = parse_natural_language(raw_text, use_llm=use_llm)
        filtered = _filter_parsed_profile_fragment(
            parsed,
            max_core_directions=2,
            core_cap=0.78,
        )
        if not filtered["core_directions"]:
            continue
        merge_parsed_profile_into_profile(
            fragment,
            filtered,
            blend=0.35,
            new_direction_cap=0.75,
        )

    publication_blocklist = set(GENERIC_PUBLICATION_DIRECTIONS) - explicit_direction_keys
    for raw_title in _dedupe_preserve_order(list(publication_titles or [])):
        parsed = parse_natural_language(raw_title, use_llm=False)
        filtered = _filter_parsed_profile_fragment(
            parsed,
            max_core_directions=2,
            core_cap=BOOTSTRAP_PUBLICATION_CAP,
            blocked_directions=publication_blocklist,
            preferred_directions=explicit_direction_keys,
        )
        if not filtered["core_directions"]:
            continue
        merge_parsed_profile_into_profile(
            fragment,
            filtered,
            blend=0.18,
            new_direction_cap=BOOTSTRAP_PUBLICATION_CAP,
        )

    _trim_bootstrap_profile(fragment)
    return fragment


def _html_to_text_lines(html_text: str) -> List[str]:
    """Convert a webpage into clean one-line text blocks."""
    without_scripts = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", html_text or "")
    block_marked = re.sub(
        r"(?i)</?(?:br|p|div|li|ul|ol|h[1-6]|section|article|header|footer|tr|td|th|table)>",
        "\n",
        without_scripts,
    )
    plain_text = html.unescape(re.sub(r"(?s)<[^>]+>", " ", block_marked))
    return [
        line
        for line in (_collapse_whitespace(item) for item in plain_text.splitlines())
        if line and len(line) <= 240
    ]


def _classify_homepage_section(line: str) -> str:
    lowered = line.casefold().strip(" :-|")
    section_hints = {
        "research_interests": (
            "research interests",
            "interests",
            "research focus",
            "research topics",
            "研究兴趣",
        ),
        "research": (
            "research areas",
            "research area",
            "research",
            "selected research",
            "研究方向",
            "研究领域",
        ),
        "about": (
            "about",
            "bio",
            "biography",
            "about me",
            "个人简介",
            "简介",
        ),
        "projects": (
            "projects",
            "selected projects",
            "project",
            "代表项目",
            "项目",
        ),
    }
    for section_name, hints in section_hints.items():
        if any(lowered == hint or lowered.startswith(f"{hint}:") for hint in hints):
            return section_name
    return ""


def _extract_homepage_sections(html_text: str) -> Dict[str, Any]:
    title = _strip_html(_extract_first_group(r"<title[^>]*>(.*?)</title>", html_text))
    description = _strip_html(
        _extract_first_group(
            r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']',
            html_text,
        )
    )
    keywords_raw = _strip_html(
        _extract_first_group(
            r'<meta[^>]+name=["\']keywords["\'][^>]+content=["\'](.*?)["\']',
            html_text,
        )
    )
    keywords = _dedupe_preserve_order(re.split(r"\s*,\s*", keywords_raw)) if keywords_raw else []

    sections = {
        "research_interests": [],
        "research": [],
        "about": [],
        "projects": [],
    }
    lines = _html_to_text_lines(html_text)
    active_section = ""
    remaining_lines = 0

    for line in lines:
        section_name = _classify_homepage_section(line)
        if section_name:
            active_section = section_name
            remaining_lines = 6 if section_name in {"research_interests", "research"} else 4
            inline_parts = re.split(r"[:：]\s*", line, maxsplit=1)
            if len(inline_parts) == 2 and inline_parts[1].strip():
                sections[section_name].append(inline_parts[1].strip())
                remaining_lines -= 1
            continue

        if active_section and remaining_lines > 0:
            sections[active_section].append(line)
            remaining_lines -= 1
            continue

        active_section = ""

    return {
        "title": title,
        "description": description,
        "keywords": keywords,
        "sections": {key: _dedupe_preserve_order(value) for key, value in sections.items()},
    }


def parse_research_homepage(homepage_url: str, use_llm: bool = True) -> Dict[str, Any]:
    """Fetch a personal homepage and derive a homepage-first bootstrap fragment."""
    candidate_url = _collapse_whitespace(homepage_url)
    if not candidate_url:
        raise ValueError("empty homepage url")
    if "://" not in candidate_url:
        candidate_url = f"https://{candidate_url.lstrip('/')}"

    response = requests.get(
        candidate_url,
        headers=SCHOLAR_HEADERS,
        timeout=max(5, _get_env_int("PAPERFLOW_HOMEPAGE_TIMEOUT", HOMEPAGE_TIMEOUT_SECONDS)),
    )
    response.raise_for_status()

    homepage_profile = _extract_homepage_sections(response.text)
    homepage_profile["url"] = candidate_url

    explicit_texts = [
        *(homepage_profile.get("sections", {}).get("research_interests", []) or []),
        *(homepage_profile.get("sections", {}).get("research", []) or []),
        *(homepage_profile.get("keywords") or []),
    ]
    secondary_texts = [
        *(homepage_profile.get("sections", {}).get("about", []) or []),
    ]
    publication_titles = [
        *(homepage_profile.get("sections", {}).get("projects", []) or []),
    ]
    if homepage_profile.get("description"):
        secondary_texts.append(str(homepage_profile["description"]))

    parsed_profile = _build_bootstrap_fragment_from_structured_sources(
        explicit_texts=explicit_texts,
        secondary_texts=secondary_texts,
        publication_titles=publication_titles,
        use_llm=use_llm,
    )

    notes: List[str] = []
    if explicit_texts:
        notes.append("已优先根据个人主页研究方向生成冷启动画像。")
    elif secondary_texts:
        notes.append("已结合个人主页摘要信息补充冷启动画像。")

    return {
        "homepage_profile": homepage_profile,
        "parsed_profile": parsed_profile,
        "direction_explanations": notes,
    }


def _merge_scholar_page_data(base: Dict[str, Any], incoming: Dict[str, Any], publication_limit: int) -> Dict[str, Any]:
    """Merge one Scholar page parse into the accumulated profile snapshot."""
    if not base:
        base = {
            "name": incoming.get("name", ""),
            "affiliation": incoming.get("affiliation", ""),
            "homepage_url": incoming.get("homepage_url", ""),
            "interests": list(incoming.get("interests", []) or []),
            "publications": [],
            "all_publications": [],
            "stats": dict(incoming.get("stats") or {}),
            "top_coauthors": [],
            "top_venues": [],
            "collaboration_network": [],
            "top_cited_publications": [],
            "blocked": bool(incoming.get("blocked")),
        }
    else:
        if not base.get("name") and incoming.get("name"):
            base["name"] = incoming["name"]
        if not base.get("affiliation") and incoming.get("affiliation"):
            base["affiliation"] = incoming["affiliation"]
        if not base.get("homepage_url") and incoming.get("homepage_url"):
            base["homepage_url"] = incoming["homepage_url"]
        if not base.get("stats") and incoming.get("stats"):
            base["stats"] = dict(incoming.get("stats") or {})
        base["blocked"] = bool(base.get("blocked")) or bool(incoming.get("blocked"))
        for interest in incoming.get("interests", []) or []:
            if interest and interest not in base["interests"]:
                base["interests"].append(interest)

    seen_titles = {str(item.get("title") or "").casefold() for item in base.get("all_publications", [])}
    for publication in incoming.get("all_publications") or incoming.get("publications") or []:
        title_key = str(publication.get("title") or "").casefold()
        if not title_key or title_key in seen_titles:
            continue
        seen_titles.add(title_key)
        base.setdefault("all_publications", []).append(publication)

    sorted_publications = sorted(
        base.get("all_publications", []),
        key=lambda item: (
            int(item.get("citations") or 0),
            int(item.get("year") or 0),
            len(str(item.get("title") or "")),
        ),
        reverse=True,
    )
    base["all_publications"] = sorted_publications
    base["publications"] = sorted_publications[:publication_limit]

    network_signals = _build_scholar_network_signals(sorted_publications, scholar_name=str(base.get("name") or ""))
    base["top_coauthors"] = list(network_signals.get("top_coauthors") or [])
    base["top_venues"] = list(network_signals.get("top_venues") or [])
    base["collaboration_network"] = list(network_signals.get("collaboration_network") or [])
    base["top_cited_publications"] = list(network_signals.get("top_cited_publications") or [])
    return base


def _fetch_google_scholar_profile_pages(scholar_url: str) -> Dict[str, Any]:
    """Fetch one or more Scholar profile pages with lightweight fallbacks."""
    timeout_seconds = max(5, _get_env_int("PAPERFLOW_SCHOLAR_TIMEOUT", SCHOLAR_TIMEOUT_SECONDS))
    publication_limit = max(1, _get_env_int("PAPERFLOW_SCHOLAR_PUBLICATION_LIMIT", SCHOLAR_PUBLICATION_LIMIT))
    page_size = max(20, _get_env_int("PAPERFLOW_SCHOLAR_PAGE_SIZE", 100))
    max_pages = max(1, _get_env_int("PAPERFLOW_SCHOLAR_MAX_PAGES", SCHOLAR_MAX_PAGES))

    session = requests.Session()
    errors: List[str] = []
    profile: Dict[str, Any] = {}

    for page_index in range(max_pages):
        cstart = page_index * page_size
        if len(profile.get("all_publications", [])) >= publication_limit:
            break

        candidate_urls = [
            _build_scholar_profile_url(scholar_url, cstart=cstart, pagesize=page_size, hl="en"),
            _build_scholar_profile_url(scholar_url, cstart=cstart, pagesize=20, hl="en"),
            _build_scholar_profile_url(scholar_url, cstart=cstart, pagesize=20, hl="zh-CN"),
        ]

        page_data: Dict[str, Any] = {}
        page_loaded = False
        for candidate_url in candidate_urls:
            try:
                response = session.get(candidate_url, headers=SCHOLAR_HEADERS, timeout=timeout_seconds)
                response.raise_for_status()
                parsed = _parse_google_scholar_profile_html(response.text)
                if parsed.get("blocked"):
                    errors.append("Scholar returned an anti-bot / captcha page")
                    continue
                if not parsed.get("interests") and not parsed.get("all_publications") and not parsed.get("publications"):
                    fallback_excerpt = _build_scholar_fallback_excerpt(response.text)
                    if fallback_excerpt:
                        parsed["fallback_excerpt"] = fallback_excerpt
                    errors.append("Scholar page loaded but structured profile signals were empty")
                    continue
                page_data = parsed
                page_loaded = True
                break
            except requests.RequestException as exc:
                errors.append(f"{type(exc).__name__}: {exc}")

        if not page_loaded:
            if profile.get("all_publications") or profile.get("interests"):
                break
            raise ValueError("failed to fetch Google Scholar profile; " + "; ".join(errors[-3:]))

        profile = _merge_scholar_page_data(profile, page_data, publication_limit)

        current_page_publications = page_data.get("all_publications") or page_data.get("publications") or []
        if len(current_page_publications) < page_size:
            break

    if not profile.get("interests") and not profile.get("publications"):
        raise ValueError("no scholar interests or publication rows found")

    if errors:
        profile["fetch_warnings"] = errors[-3:]
    return profile


def _build_scholar_heat_maps(scholar_profile: Dict[str, Any]) -> Dict[str, Dict[str, float]]:
    """Convert coauthor and affiliation signals into profile heat maps."""
    author_heat: Dict[str, float] = {}
    institution_heat: Dict[str, float] = {}

    network_entries = scholar_profile.get("collaboration_network") or scholar_profile.get("top_coauthors") or []
    for index, entry in enumerate(network_entries):
        name = _collapse_whitespace(entry.get("name", ""))
        count = int(entry.get("count") or 0)
        citation_sum = int(entry.get("citation_sum") or 0)
        last_year = int(entry.get("last_year") or 0)
        if not name or count <= 0:
            continue
        recent_bonus = 0.03 if last_year and last_year >= datetime.now().year - 1 else 0.0
        citation_bonus = min(0.12, citation_sum / 800.0)
        seeded = min(0.82, 0.18 + 0.07 * count + citation_bonus + recent_bonus - 0.015 * index)
        author_heat[name] = round(max(0.15, seeded), 4)

    affiliation = _collapse_whitespace(scholar_profile.get("affiliation", ""))
    if affiliation:
        institution_heat[affiliation] = 0.6

    return {
        "author_heat": author_heat,
        "institution_heat": institution_heat,
    }


def parse_google_scholar_profile(scholar_url: str, use_llm: bool = True) -> Dict[str, Any]:
    """Fetch a Google Scholar profile and convert it into a bootstrap profile fragment."""
    scholar_profile = _fetch_google_scholar_profile_pages(scholar_url)

    interest_texts = [str(item) for item in scholar_profile.get("interests", []) if str(item).strip()]
    publication_titles = [
        str(paper.get("title") or "").strip()
        for paper in scholar_profile.get("publications", []) or []
        if str(paper.get("title") or "").strip()
    ]
    top_cited_titles = [
        str(paper.get("title") or "").strip()
        for paper in scholar_profile.get("top_cited_publications", []) or []
        if str(paper.get("title") or "").strip()
    ]
    secondary_texts: List[str] = []
    if scholar_profile.get("affiliation"):
        secondary_texts.append(f"Affiliation: {scholar_profile['affiliation']}")
    secondary_texts.extend(
        [f"Highly cited work: {title}" for title in top_cited_titles[:3]]
    )

    scholar_fragment = _build_bootstrap_fragment_from_structured_sources(
        explicit_texts=interest_texts,
        secondary_texts=secondary_texts,
        publication_titles=_dedupe_preserve_order(top_cited_titles + publication_titles),
        use_llm=use_llm,
    )

    scholar_fragment.update(_build_scholar_heat_maps(scholar_profile))
    scholar_fragment["interest_vector"] = generate_interest_vector(scholar_fragment.get("core_directions", {}))

    notes: List[str] = []
    if scholar_profile.get("interests"):
        notes.append("已从 Google Scholar 研究兴趣提取信号：" + "、".join(scholar_profile["interests"][:4]))
    if scholar_profile.get("publications"):
        notes.append(f"已结合 Google Scholar 代表论文 {len(scholar_profile['publications'])} 篇补充冷启动画像。")
    if scholar_profile.get("top_cited_publications"):
        top_cited_titles = [item.get("title", "") for item in scholar_profile["top_cited_publications"][:2] if item.get("title")]
        if top_cited_titles:
            notes.append("已提取高引代表作信号：" + "、".join(top_cited_titles))
    if scholar_profile.get("top_coauthors"):
        top_names = [entry.get("name", "") for entry in scholar_profile["top_coauthors"][:3] if entry.get("name")]
        if top_names:
            notes.append("已提取高频合作作者信号：" + "、".join(top_names))
    if scholar_profile.get("collaboration_network"):
        lead_network = scholar_profile["collaboration_network"][0]
        lead_name = str(lead_network.get("name") or "").strip()
        lead_count = int(lead_network.get("count") or 0)
        lead_citations = int(lead_network.get("citation_sum") or 0)
        if lead_name:
            notes.append(
                f"已构建更细粒度合作网络：当前最强合作节点为 {lead_name}"
                f"（合作 {lead_count} 篇，累计引用 {lead_citations}）"
            )
    if scholar_profile.get("stats"):
        citations = scholar_profile["stats"].get("citations")
        if citations is not None:
            notes.append(f"Scholar 概览统计：总引用 {citations}")
    if scholar_profile.get("fetch_warnings"):
        notes.append("Scholar 抓取已启用 fallback：" + "；".join(scholar_profile["fetch_warnings"]))
    if scholar_profile.get("homepage_url"):
        notes.append("已识别 Scholar 主页外链，可优先按个人主页方向继续补强。")

    return {
        "scholar_profile": scholar_profile,
        "parsed_profile": scholar_fragment,
        "direction_explanations": notes,
    }


def parse_natural_language(text: str, use_llm: bool = True) -> Dict[str, Any]:
    """Parse a natural-language self-description into a bootstrap profile fragment."""
    normalized_text = re.sub(r"\s+", " ", (text or "").strip()).lower()
    if normalized_text in COLD_START_COMMAND_HINTS:
        return _empty_parsed_profile_fragment()

    from config.direction_lexicon import get_lexicon_keywords, resolve_canonical_direction

    working_text = str(text or "")
    text_lower = working_text.lower()
    merged_directions = get_lexicon_keywords()

    core_directions: Dict[str, float] = {}
    topic_weights: Dict[str, float] = {}
    exact_direction_hits: List[str] = []

    for clause in _split_direction_clauses(working_text):
        resolved = resolve_canonical_direction(clause, include_paper_terms=True)
        if not resolved:
            continue
        direction_key = str(resolved.get("canonical_name") or "").strip()
        if not direction_key:
            continue
        exact_direction_hits.append(direction_key)
        core_directions[direction_key] = max(core_directions.get(direction_key, 0.0), 0.9)
        topic_weights[direction_key] = max(topic_weights.get(direction_key, 0.0), 0.9)
        working_text = _remove_clause_from_text(working_text, clause)

    working_text_lower = working_text.lower()
    for direction, keywords in merged_directions.items():
        match_count = sum(1 for keyword in keywords if keyword and (keyword in working_text_lower or keyword in working_text))
        if match_count <= 0:
            continue
        weight = min(0.5 + match_count * 0.1, 0.95)
        if direction in core_directions:
            weight = max(weight, core_directions[direction])
        core_directions[direction] = weight
        topic_weights[direction] = max(topic_weights.get(direction, 0.0), weight)

    llm_parse_result: Dict[str, Any] = {
        "canonical_directions": [],
        "pending_candidates": [],
        "explanations": [],
    }
    if use_llm and not core_directions:
        llm_parse_result = _parse_directions_with_llm(text)

    llm_directions = list(llm_parse_result.get("canonical_directions", []) or [])
    for direction in llm_directions:
        direction_key = str(direction.get("name") or "").strip()
        if not direction_key:
            continue
        confidence = float(direction.get("confidence", 0.5) or 0.5)
        if direction_key in core_directions:
            existing = core_directions[direction_key]
            if confidence > existing:
                core_directions[direction_key] = confidence
                topic_weights[direction_key] = confidence
        else:
            seeded_weight = min(max(confidence * 0.8, 0.4), 0.5)
            core_directions[direction_key] = seeded_weight
            topic_weights[direction_key] = seeded_weight

    methodology_preferences = _derive_methodology_preferences(text_lower)
    taste_profile = _build_taste_profile_from_methodology(methodology_preferences)

    return {
        "core_directions": core_directions,
        "methodology_preferences": methodology_preferences,
        "topic_weights": topic_weights,
        "interest_vector": generate_interest_vector(core_directions),
        "taste_profile": taste_profile,
        "inferred_topics": [d.get("name") for d in llm_directions if d.get("name")],
        "direction_explanations": list(llm_parse_result.get("explanations", []) or []),
        "pending_directions": list(llm_parse_result.get("pending_candidates", []) or []),
        "exact_direction_hits": exact_direction_hits,
    }


def _parse_directions_with_llm(text: str) -> Dict[str, Any]:
    """Use the shared canonical direction normalizer as the LLM-backed fallback."""
    try:
        llm_parser = importlib.import_module("agents.master-coordinator.scripts.llm_parser")
        return llm_parser.normalize_research_directions(
            text,
            auto_persist_known_aliases=True,
        )
    except Exception as e:
        print(f"LLM direction parsing failed: {e}")
        return {"canonical_directions": [], "pending_candidates": [], "explanations": []}


def _split_direction_clauses(text: str) -> List[str]:
    """Split short bootstrap text into direction-like clauses."""
    cleaned = _collapse_whitespace(text)
    if not cleaned:
        return []

    normalized = re.sub(r"[•·▪◦◆◇●○]+", ";", cleaned)
    raw_chunks = re.split(r"[;\n|]+", normalized)
    clauses: List[str] = []
    seen = set()

    for chunk in raw_chunks:
        chunk = _collapse_whitespace(chunk)
        if not chunk:
            continue
        chunk = re.sub(
            r"^(?:research\s+interests?|research\s+areas?|interests?|my\s+research|i\s+work\s+on|research\s+focus|research|direction[s]?|研究方向|研究兴趣|方向)[:：\-]\s*",
            "",
            chunk,
            flags=re.IGNORECASE,
        ).strip()
        if not chunk:
            continue

        sub_chunks = re.split(r"\s*(?:,|/|&| and )\s*", chunk, flags=re.IGNORECASE)
        if len(sub_chunks) <= 1:
            sub_chunks = [chunk]

        for item in sub_chunks:
            candidate = _collapse_whitespace(item).strip(".,;:()[]{}")
            if not candidate or len(candidate) < 3:
                continue
            marker = candidate.casefold()
            if marker in seen:
                continue
            seen.add(marker)
            clauses.append(candidate)

    return clauses


def _remove_clause_from_text(text: str, clause: str) -> str:
    """Remove one resolved clause from the text so generic keywords do not double-fire."""
    if not text or not clause:
        return text
    pattern = re.compile(re.escape(clause), re.IGNORECASE)
    return pattern.sub(" ", text, count=1)


def _derive_methodology_preferences(text_lower: str) -> Dict[str, Any]:
    """Infer methodology preferences while keeping no-evidence cases neutral."""
    data_driven_count = sum(1 for keyword in METHODOLOGY_KEYWORDS["data_driven"] if keyword in text_lower)
    theory_count = sum(1 for keyword in METHODOLOGY_KEYWORDS["theory"] if keyword in text_lower)
    systematic_count = sum(1 for keyword in METHODOLOGY_KEYWORDS["systematic"] if keyword in text_lower)
    incremental_count = sum(1 for keyword in METHODOLOGY_KEYWORDS["incremental"] if keyword in text_lower)
    open_source_count = sum(1 for keyword in METHODOLOGY_KEYWORDS["open_source"] if keyword in text_lower)
    bio_count = sum(1 for keyword in ("bio", "science", "scientific", "molecular", "protein") if keyword in text_lower)

    preferences: Dict[str, Any] = {}
    if data_driven_count > theory_count and data_driven_count > 0:
        preferences["preference_data_driven_over_theory"] = True
    elif theory_count > data_driven_count and theory_count > 0:
        preferences["preference_data_driven_over_theory"] = False

    if systematic_count > incremental_count and systematic_count > 0:
        preferences["preference_systematic_work_over_incremental"] = True
    elif incremental_count > systematic_count and incremental_count > 0:
        preferences["preference_systematic_work_over_incremental"] = False

    if open_source_count > 0:
        preferences["preference_open_source_code"] = True
    if bio_count > 0:
        preferences["preference_bio_science_application"] = True

    return preferences


def _build_taste_profile_from_methodology(methodology_preferences: Dict[str, Any]) -> Dict[str, List[str]]:
    """Convert methodology preferences into the existing taste-profile schema."""
    taste_profile = {
        "preferred_work_type": [],
        "dispreferred_work_type": [],
    }

    data_pref = methodology_preferences.get("preference_data_driven_over_theory")
    if data_pref is True:
        taste_profile["preferred_work_type"].append("empirical")
    elif data_pref is False:
        taste_profile["preferred_work_type"].append("theoretical")

    systematic_pref = methodology_preferences.get("preference_systematic_work_over_incremental")
    if systematic_pref is True:
        taste_profile["preferred_work_type"].append("systematic")
        taste_profile["dispreferred_work_type"].append("incremental")
    elif systematic_pref is False:
        taste_profile["dispreferred_work_type"].append("systematic")

    if methodology_preferences.get("preference_open_source_code"):
        taste_profile["preferred_work_type"].append("open_source")

    if methodology_preferences.get("preference_bio_science_application"):
        taste_profile["preferred_work_type"].append("applied")

    return taste_profile


def generate_interest_vector(core_directions: Dict[str, float]) -> List[float]:
    """Generate a deterministic pseudo-vector from the detected directions."""
    try:
        target_dim = max(1, int(str(os.environ.get("EMBEDDING_DIMENSIONS", "768")).strip()))
    except ValueError:
        target_dim = 768

    direction_str = "_".join(sorted(core_directions.keys()))
    hash_bytes = hashlib.sha256(direction_str.encode()).digest()
    vector = []

    for index in range(target_dim):
        byte_index = index % 32
        sign = 1 if (hash_bytes[byte_index] & (1 << (index % 8))) else -1
        value = sign * ((hash_bytes[byte_index] >> (index % 8)) & 1)
        vector.append(float(value))

    norm = sum(value * value for value in vector) ** 0.5
    if norm > 0:
        vector = [value / norm for value in vector]

    return vector


def format_profile_card(profile: Dict[str, Any], user_id: str = "user_001") -> str:
    """Format the cold-start profile confirmation card in the PDF-inspired layout."""
    profile_stage = "持续学习" if profile.get("core_directions") else "冷启动"
    lines = [
        f"📋 你的学术画像（v0.1 - {profile_stage}）",
        "",
        "━━━ 核心方向 ━━━",
    ]

    core_directions = profile.get("core_directions", {}) or {}
    if core_directions:
        for direction, weight in sorted(core_directions.items(), key=lambda item: -item[1]):
            direction_cn = translate_direction(direction)
            filled = max(0, min(10, int(round(float(weight) * 10))))
            bar = "█" * filled + "░" * (10 - filled)
            lines.append(f"{direction_cn} [{bar}] 权重：{float(weight):.2f}")
    else:
        lines.append("（冷启动阶段，暂时还没有稳定方向）")

    lines.extend(["", "━━━ 方法论偏好 ━━━"])
    method_prefs = profile.get("methodology_preferences", {}) or {}
    if method_prefs:
        data_pref = method_prefs.get("preference_data_driven_over_theory")
        if data_pref is True:
            lines.append("├── 偏好数据驱动 > 纯理论")
        elif data_pref is False:
            lines.append("├── 偏好纯理论 > 数据驱动")
        else:
            lines.append("├── 数据驱动 / 纯理论：暂无明确信号")

        systematic_pref = method_prefs.get("preference_systematic_work_over_incremental")
        if systematic_pref is True:
            lines.append("├── 偏好系统性工作 > 单点改进")
        elif systematic_pref is False:
            lines.append("├── 偏好单点改进 > 系统性工作")
        else:
            lines.append("├── 系统性工作 / 单点改进：暂无明确信号")

        lines.append(
            "├── 偏好有开源代码的工作"
            if method_prefs.get("preference_open_source_code")
            else "├── 对开源代码暂无明显偏好"
        )
        lines.append(
            "└── 偏好有生物/科学应用场景的工作"
            if method_prefs.get("preference_bio_science_application")
            else "└── 通用研究场景均可"
        )
    else:
        lines.append("（暂无方法论偏好信号）")

    must_read = profile.get("must_read", {"authors": [], "institutions": [], "keywords": []}) or {}
    lines.extend(
        [
            "",
            "━━━ 必读清单 ━━━",
            f"作者：{', '.join(must_read.get('authors', [])) or '（空，待你添加）'}",
            f"机构：{', '.join(must_read.get('institutions', [])) or '（空，待你添加）'}",
            f"关键词：{', '.join(must_read.get('keywords', [])) or '（空，待你添加）'}",
            COLD_START_MUST_READ_NOTE,
            "",
            "━━━━━━━━━━━━",
            "你可以直接说：",
            '  "加个必读作者：XXX"',
            CLEAR_READING_LIST_HINT,
            '  "降低 GUI Agent 权重"',
            '  "我最近对 protein language model 更感兴趣了"',
        ]
    )

    return "\n".join(lines)


def translate_direction(direction: str) -> str:
    """Translate internal direction keys into display labels."""
    try:
        direction_lexicon = importlib.import_module("config.direction_lexicon")
        formatter = getattr(direction_lexicon, "format_direction_label", None)
        if callable(formatter):
            return str(formatter(direction, prefer_chinese=True) or direction)
    except Exception:
        pass
    return direction


def cold_start(
    user_id: str = "user_001",
    natural_language: Optional[str] = None,
    pdf_paths: Optional[List[str]] = None,
    scholar_url: Optional[str] = None,
    homepage_url: Optional[str] = None,
    reset_existing: bool = False,
    send_to_feishu: bool = True,
    feishu_user_id: Optional[str] = None,
    chat_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute the cold-start / PDF-update flow."""
    print(f"Starting cold start for user: {user_id}")

    existing_profile = get_profile(user_id)
    if existing_profile and not reset_existing:
        profile = ensure_profile_shape(existing_profile, user_id)
        print("Loaded existing profile as merge base.")
    else:
        profile = build_empty_profile(user_id)
        if existing_profile and reset_existing:
            print("Resetting existing profile before cold start.")

    baseline_pdf_path = None
    try:
        baseline_pdf_path = _seed_profile_from_baseline_pdf(profile, user_id)
        if baseline_pdf_path:
            print(f"Seeded profile from baseline PDF: {baseline_pdf_path}")
    except Exception as exc:
        print(f"Failed to seed baseline PDF: {exc}")

    if natural_language:
        print("Parsing natural language...")
        parsed = parse_natural_language(natural_language)
        merge_parsed_profile_into_profile(profile, parsed)

    if pdf_paths:
        print(f"Parsing {len(pdf_paths)} PDF file(s)...")
        applied_sources = set()
        if baseline_pdf_path:
            applied_sources.add(str(Path(baseline_pdf_path).resolve()))

        for pdf_path in pdf_paths:
            if not os.path.exists(pdf_path):
                print(f"  PDF not found: {pdf_path}")
                continue

            resolved_path = str(Path(pdf_path).resolve())
            if resolved_path in applied_sources:
                print(f"  Skipping duplicate source PDF: {pdf_path}")
                continue

            try:
                result = parse_paper_for_coldstart(pdf_path)
                merge_pdf_result_into_profile(profile, result)
                applied_sources.add(resolved_path)
                print(f"  Parsed: {pdf_path}")
            except Exception as exc:
                print(f"  Failed to parse {pdf_path}: {exc}")

    scholar_result: Optional[Dict[str, Any]] = None
    homepage_result: Optional[Dict[str, Any]] = None
    if scholar_url:
        print("Parsing Google Scholar profile...")
        try:
            scholar_result = parse_google_scholar_profile(scholar_url)
            merge_parsed_profile_into_profile(profile, scholar_result.get("parsed_profile") or {})
            scholar_snapshot = scholar_result.get("scholar_profile") or {}
            if not homepage_url:
                homepage_url = str(scholar_snapshot.get("homepage_url") or "").strip() or None
            print(
                "  Scholar parsed:"
                f" {len(scholar_snapshot.get('interests') or [])} interests,"
                f" {len(scholar_snapshot.get('publications') or [])} publications"
            )
        except Exception as exc:
            print(f"  Failed to parse Google Scholar profile: {exc}")

    if homepage_url:
        print("Parsing research homepage...")
        try:
            homepage_result = parse_research_homepage(homepage_url)
            merge_parsed_profile_into_profile(profile, homepage_result.get("parsed_profile") or {})
            homepage_snapshot = homepage_result.get("homepage_profile") or {}
            print(
                "  Homepage parsed:"
                f" {len((homepage_snapshot.get('sections') or {}).get('research_interests') or [])} interest lines,"
                f" {len((homepage_snapshot.get('sections') or {}).get('research') or [])} research lines"
            )
        except Exception as exc:
            print(f"  Failed to parse research homepage: {exc}")

    if profile.get("core_directions"):
        profile["interest_vector"] = generate_interest_vector(profile["core_directions"])

    profile["updated_at"] = datetime.now().isoformat()

    print("Saving profile...")
    if existing_profile:
        update_profile(user_id, profile)
        print("Profile updated successfully!")
    else:
        create_profile(user_id, profile)
        print("Profile created successfully!")

    try:
        sync_role_metadata_from_cold_start(
            user_id,
            profile,
            explicit_text=natural_language,
            scholar_url=scholar_url,
            homepage_url=homepage_url,
            scholar_result=scholar_result,
            homepage_result=homepage_result,
        )
    except Exception as exc:
        print(f"Failed to sync role metadata: {exc}")

    if send_to_feishu:
        target_id = chat_id or feishu_user_id or os.environ.get("FEISHU_USER_ID", "")
        use_chat = chat_id is not None
        print(f"Sending to Feishu - target: {target_id[:20]}..., use_chat_id: {use_chat}")

        card_text = format_profile_card(profile, user_id)
        try:
            if use_chat:
                feishu_reporter.send_text_to_chat(target_id, card_text)
            else:
                feishu_reporter.send_text(target_id, card_text)
            print("Profile sent to Feishu successfully!")
        except Exception as exc:
            print(f"Failed to send to Feishu: {exc}")

    print("\n--- Cold Start Complete ---")
    print(f"Profile version: {profile['version']}")
    print(f"Core directions: {len(profile['core_directions'])}")
    print(f"Topic weights: {list(profile['topic_weights'].keys())}")
    return profile


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="ColdStart Agent")
    parser.add_argument("--user-id", type=str, default="user_001", help="User ID")
    parser.add_argument("--role", type=str, default="roleA", help="Role name (roleA, roleB, etc.)")
    parser.add_argument("--natural-language", type=str, help="Natural language description")
    parser.add_argument("--pdf", nargs="+", help="PDF file paths")
    parser.add_argument("--scholar-url", type=str, help="Google Scholar URL")
    parser.add_argument("--homepage-url", type=str, help="Research homepage URL")
    parser.add_argument("--send-feishu", action="store_true", help="Send to Feishu")
    parser.add_argument("--feishu-user-id", type=str, help="Feishu user ID")

    args = parser.parse_args()

    role = args.role.lower()
    user_id = f"user_{role}" if role.startswith("role") else args.user_id
    baseline_pdf_path = resolve_baseline_pdf_path(user_id)

    if role == "rolea" and not args.natural_language and not baseline_pdf_path:
        natural_language = (
            "我关注 data-native scientific discovery，"
            "具体做生物分子数据基础设施和方法论图谱，"
            "也关注 auto research 和 GUI agent"
        )
    else:
        natural_language = args.natural_language

    cold_start(
        user_id=user_id,
        natural_language=natural_language,
        pdf_paths=args.pdf,
        scholar_url=args.scholar_url,
        homepage_url=args.homepage_url,
        send_to_feishu=args.send_feishu,
        feishu_user_id=args.feishu_user_id,
    )
