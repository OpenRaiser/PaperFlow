#!/usr/bin/env python3
"""
Citation-Enhanced Literature Recommendation baseline runner.

This runner reranks clean frozen PaperFlow candidate pools with a citation-aware
literature recommendation baseline. It uses only clean paper metadata,
fixed cold-start evidence, and previous-day selected papers.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from config import direction_lexicon
except Exception:  # pragma: no cover - keeps exported artifacts runnable.
    direction_lexicon = None

from experiments.benchmark import evaluate_simulation_metrics as eval_metrics


METHOD_KEY = "citation_enhanced"
METHOD_NAME = "Citation-Enhanced Literature Recommendation"
DEFAULT_TOP_K = 20
CLEAN_CANDIDATE_FILE = "candidate_pools.jsonl"
CLEAN_LABEL_FILE = "labels_for_eval.jsonl"

SCORE_WEIGHTS = {
    "content": 0.50,
    "citation_relation": 0.25,
    "impact": 0.20,
    "source_prior": 0.05,
}

LABEL_THRESHOLDS = {
    "high_relevant": 0.70,
    "maybe_interested": 0.45,
}

TOKEN_RE = re.compile(r"[a-z0-9]+(?:[-_][a-z0-9]+)*", flags=re.IGNORECASE)

CITATION_COUNT_FIELDS = (
    "cited_by_count",
    "citation_count",
    "citations",
    "influential_citation_count",
)

REFERENCE_FIELDS = (
    "references",
    "reference_ids",
    "cited_references",
    "outbound_citations",
)

INBOUND_CITATION_FIELDS = (
    "citation_ids",
    "cited_by_ids",
    "inbound_citations",
)


def clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            payload = json.loads(line)
            if isinstance(payload, dict):
                rows.append(payload)
    return rows


def write_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def parse_string_list(raw_value: Any) -> List[str]:
    if raw_value in (None, "", []):
        return []
    if isinstance(raw_value, list):
        return [str(item).strip() for item in raw_value if str(item).strip()]
    if isinstance(raw_value, dict):
        values: List[str] = []
        for key, value in raw_value.items():
            values.append(str(key))
            values.extend(parse_string_list(value))
        return [item.strip() for item in values if item.strip()]
    if isinstance(raw_value, str):
        try:
            parsed = json.loads(raw_value)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, (list, dict)):
            return parse_string_list(parsed)
        return [item.strip() for item in re.split(r"[,;|\s]+", raw_value) if item.strip()]
    return [str(raw_value).strip()] if str(raw_value).strip() else []


def normalize_phrase_text(value: Any) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).split())


def normalize_id(value: Any) -> str:
    value_text = str(value or "").strip().casefold()
    if not value_text:
        return ""
    value_text = re.sub(r"^https?://doi\.org/", "doi:", value_text)
    value_text = re.sub(r"^doi:\s*", "doi:", value_text)
    value_text = re.sub(r"^arxiv:\s*", "arxiv:", value_text)
    return re.sub(r"\s+", "", value_text)


def tokenize(text: Any) -> List[str]:
    tokens: List[str] = []
    for raw_token in TOKEN_RE.findall(str(text or "").casefold()):
        token = raw_token.replace("_", "-")
        if len(token) <= 1:
            continue
        tokens.append(token)
        if "-" in token:
            tokens.extend(part for part in token.split("-") if len(part) > 1)
    return tokens


def paper_text(row: Dict[str, Any]) -> str:
    return " ".join(str(part or "") for part in (row.get("title"), row.get("abstract")) if part)


def paper_identity(row: Dict[str, Any]) -> str:
    explicit_identity = str(row.get("paper_identity") or "").strip()
    if explicit_identity:
        return explicit_identity
    for key in ("paper_id", "doi", "arxiv_id", "openalex_id", "semantic_scholar_id", "url"):
        value = str(row.get(key) or "").strip().casefold()
        if value:
            return f"{key}:{value}"
    return "title:" + normalize_phrase_text(row.get("title"))


def identity_aliases(row: Dict[str, Any]) -> set[str]:
    aliases = {normalize_id(paper_identity(row))}
    for key in ("paper_id", "doi", "arxiv_id", "openalex_id", "semantic_scholar_id", "corpus_id", "url"):
        value = row.get(key)
        if value not in (None, ""):
            aliases.add(normalize_id(f"{key}:{value}"))
            aliases.add(normalize_id(value))
    external_ids = row.get("external_ids")
    if isinstance(external_ids, (dict, list, str)):
        aliases.update(normalize_id(item) for item in parse_string_list(external_ids))
    return {item for item in aliases if item}


def extract_id_set(row: Dict[str, Any], fields: Sequence[str]) -> set[str]:
    values: set[str] = set()
    for field_name in fields:
        for item in parse_string_list(row.get(field_name)):
            normalized = normalize_id(item)
            if normalized:
                values.add(normalized)
    return values


def citation_count(row: Dict[str, Any]) -> Optional[float]:
    for field_name in CITATION_COUNT_FIELDS:
        value = row.get(field_name)
        if value in (None, ""):
            continue
        count = safe_float(value, -1.0)
        if count >= 0:
            return count
    return None


def source_prior(row: Dict[str, Any]) -> float:
    source = str(row.get("source") or row.get("venue") or row.get("journal") or "").casefold()
    if any(token in source for token in ("nature", "science", "cell")):
        return 0.80
    if any(token in source for token in ("pnas", "acm", "ieee", "springer", "elsevier")):
        return 0.68
    if "openreview" in source:
        return 0.55
    if "arxiv" in source:
        return 0.45
    if row.get("doi"):
        return 0.50
    return 0.35


def impact_score(row: Dict[str, Any], max_log_citations: float) -> Tuple[float, bool]:
    count = citation_count(row)
    if count is not None and max_log_citations > 0:
        return clamp(math.log1p(count) / max_log_citations), True

    # If no citation count exists in the frozen metadata, use only publication
    # metadata as a weak impact proxy. Do not query live APIs, which would leak
    # information unavailable on the simulated recommendation day.
    identifier_bonus = 0.12 if row.get("doi") else 0.0
    return clamp(0.65 * source_prior(row) + identifier_bonus), False


def build_idf_from_texts(texts: Sequence[Any]) -> Dict[str, float]:
    doc_frequency: Counter[str] = Counter()
    doc_count = 0
    for text in texts:
        unique_tokens = set(tokenize(text))
        if not unique_tokens:
            continue
        doc_count += 1
        doc_frequency.update(unique_tokens)
    if doc_count <= 0:
        return {}
    return {
        token: math.log((doc_count + 1.0) / (freq + 1.0)) + 1.0
        for token, freq in doc_frequency.items()
    }


def vectorize_text(text: Any, idf: Dict[str, float]) -> Dict[str, float]:
    counts = Counter(tokenize(text))
    if not counts:
        return {}
    default_idf = math.log(max(2.0, len(idf) + 1.0))
    vector = {
        token: (1.0 + math.log(freq)) * idf.get(token, default_idf)
        for token, freq in counts.items()
    }
    return normalize_vector(vector)


def normalize_vector(vector: Dict[str, float]) -> Dict[str, float]:
    norm = math.sqrt(sum(value * value for value in vector.values()))
    if norm <= 0:
        return {}
    return {key: value / norm for key, value in vector.items() if value}


def add_weighted_vector(target: Dict[str, float], vector: Dict[str, float], weight: float) -> None:
    if weight <= 0:
        return
    for key, value in vector.items():
        target[key] = target.get(key, 0.0) + value * weight


def cosine(left: Dict[str, float], right: Dict[str, float]) -> float:
    if not left or not right:
        return 0.0
    if len(left) > len(right):
        left, right = right, left
    return sum(value * right.get(key, 0.0) for key, value in left.items())


def scaled_similarity(left: Dict[str, float], right: Dict[str, float]) -> float:
    return clamp(cosine(left, right) * 4.0)


def jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def load_roles(roles_file: Path) -> Dict[str, Dict[str, Any]]:
    payload = load_json(roles_file)
    roles = payload.get("roles") if isinstance(payload, dict) else {}
    return roles if isinstance(roles, dict) else {}


def _direction_terms(direction: Any) -> List[str]:
    direction_text = str(direction or "").strip()
    if not direction_text:
        return []
    terms = [direction_text, direction_text.replace("-", " ")]
    if direction_lexicon is None:
        return terms
    try:
        expanded = direction_lexicon.expand_direction_terms([direction_text])
    except Exception:
        return terms
    for entry in expanded.values():
        terms.extend(parse_string_list(entry.get("aliases")))
        terms.extend(parse_string_list(entry.get("paper_terms")))
        terms.append(str(entry.get("name") or ""))
        terms.append(str(entry.get("name_cn") or ""))
    return [term for term in terms if term.strip()]


def dedupe_strings(values: Iterable[Any]) -> List[str]:
    result: List[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = str(value or "").strip()
        if not cleaned:
            continue
        marker = cleaned.casefold()
        if marker in seen:
            continue
        seen.add(marker)
        result.append(cleaned)
    return result


def build_initial_profile(user_meta: Dict[str, Any], role: Dict[str, Any]) -> Dict[str, Any]:
    directions: Dict[str, float] = {}
    seed_directions = user_meta.get("seed_directions")
    if isinstance(seed_directions, dict):
        for key, value in seed_directions.items():
            directions[str(key)] = max(directions.get(str(key), 0.0), safe_float(value, 0.6))
    elif isinstance(seed_directions, list):
        for item in seed_directions:
            if isinstance(item, dict):
                key = str(item.get("canonical_name") or item.get("bootstrap_phrase") or "").strip()
                weight = safe_float(item.get("weight"), 0.6)
            else:
                key = str(item or "").strip()
                weight = 0.6
            if key:
                directions[key] = max(directions.get(key, 0.0), weight)

    for item in role.get("core_directions", []) or []:
        if isinstance(item, dict):
            key = str(item.get("canonical_name") or item.get("bootstrap_phrase") or "").strip()
            weight = safe_float(item.get("weight"), 0.6)
        else:
            key = str(item or "").strip()
            weight = 0.6
        if key:
            directions[key] = max(directions.get(key, 0.0), weight)

    terms: List[str] = []
    for direction in directions:
        terms.extend(_direction_terms(direction))
    terms.extend(parse_string_list(role.get("positive_keywords")))
    terms.extend(parse_string_list(role.get("must_read_keywords")))
    terms.extend(parse_string_list(user_meta.get("description")))
    terms.append(str(role.get("description") or ""))
    terms.append(str(role.get("bootstrap_summary") or ""))
    return {
        "directions": directions,
        "terms": dedupe_strings(terms),
        "description": str(user_meta.get("description") or role.get("description") or ""),
    }


def make_profile_text(profile: Dict[str, Any]) -> str:
    parts = [
        profile.get("description", ""),
        " ".join(profile.get("terms", []) or []),
        " ".join(profile.get("directions", {}).keys()),
    ]
    return " ".join(str(part or "") for part in parts if part)


@dataclass
class UserCitationState:
    profile_text: str
    profile_vector: Dict[str, float] = field(default_factory=dict)
    selected_sum: Dict[str, float] = field(default_factory=dict)
    selected_texts: List[str] = field(default_factory=list)
    selected_identities: set[str] = field(default_factory=set)
    selected_reference_sets: List[set[str]] = field(default_factory=list)
    selected_count: int = 0

    def selected_centroid(self) -> Dict[str, float]:
        return normalize_vector(self.selected_sum)

    def feedback_texts(self) -> List[str]:
        return list(self.selected_texts)

    def prepare_vectors(self, idf: Dict[str, float]) -> None:
        self.profile_vector = vectorize_text(self.profile_text, idf)
        self.selected_sum = {}
        for text in self.selected_texts:
            add_weighted_vector(self.selected_sum, vectorize_text(text, idf), 1.0)

    def update_selected(self, row: Dict[str, Any]) -> None:
        self.selected_texts.append(paper_text(row))
        self.selected_identities.update(identity_aliases(row))
        self.selected_reference_sets.append(extract_id_set(row, REFERENCE_FIELDS))
        self.selected_count += 1


def content_score(row_vector: Dict[str, float], state: UserCitationState) -> float:
    profile_score = scaled_similarity(row_vector, state.profile_vector)
    if state.selected_count <= 0:
        return profile_score
    feedback_score = scaled_similarity(row_vector, state.selected_centroid())
    return clamp(0.65 * feedback_score + 0.35 * profile_score)


def citation_relation_score(row: Dict[str, Any], state: UserCitationState) -> Tuple[float, bool, float]:
    if state.selected_count <= 0:
        return 0.0, False, 0.0

    row_aliases = identity_aliases(row)
    references = extract_id_set(row, REFERENCE_FIELDS)
    inbound_citations = extract_id_set(row, INBOUND_CITATION_FIELDS)

    direct_link = bool(
        (references & state.selected_identities)
        or (inbound_citations & state.selected_identities)
        or any(row_aliases & selected_refs for selected_refs in state.selected_reference_sets)
    )
    best_bibliographic_overlap = max(
        (jaccard(references, selected_refs) for selected_refs in state.selected_reference_sets),
        default=0.0,
    )
    score = clamp((0.75 if direct_link else 0.0) + 0.35 * best_bibliographic_overlap)
    return score, direct_link, best_bibliographic_overlap


def label_for_score(score: float) -> str:
    if score >= LABEL_THRESHOLDS["high_relevant"]:
        return "high_relevant"
    if score >= LABEL_THRESHOLDS["maybe_interested"]:
        return "maybe_interested"
    return "edge_relevant"


def score_row(
    row: Dict[str, Any],
    row_vector: Dict[str, float],
    state: UserCitationState,
    *,
    max_log_citations: float,
) -> Dict[str, Any]:
    content = content_score(row_vector, state)
    relation, direct_link, bibliographic_overlap = citation_relation_score(row, state)
    impact, has_citation_count = impact_score(row, max_log_citations)
    source = source_prior(row)
    final_score = clamp(
        SCORE_WEIGHTS["content"] * content
        + SCORE_WEIGHTS["citation_relation"] * relation
        + SCORE_WEIGHTS["impact"] * impact
        + SCORE_WEIGHTS["source_prior"] * source
    )
    return {
        "system_score": final_score,
        "system_label": label_for_score(final_score),
        "content_score": content,
        "citation_relation_score": relation,
        "citation_direct_link": direct_link,
        "bibliographic_overlap": bibliographic_overlap,
        "impact_score": impact,
        "has_citation_count": has_citation_count,
        "citation_count": citation_count(row),
        "source_prior": source,
        "training_selected_count": state.selected_count,
    }


def load_user_metadata(input_dir: Path) -> Dict[str, Dict[str, Any]]:
    payload = load_json(input_dir / "users.json")
    users = payload.get("users") if isinstance(payload, dict) else []
    metadata: Dict[str, Dict[str, Any]] = {}
    if isinstance(users, list):
        for item in users:
            if not isinstance(item, dict):
                continue
            user_id = str(item.get("user_id") or "").strip()
            if user_id:
                metadata[user_id] = item
    return metadata


def build_user_states(
    user_metadata: Dict[str, Dict[str, Any]],
    roles: Dict[str, Dict[str, Any]],
    episode_rows: Sequence[Dict[str, Any]],
) -> Dict[str, UserCitationState]:
    user_ids = sorted(
        {
            str(row.get("user_id") or "").strip()
            for row in episode_rows
            if str(row.get("user_id") or "").strip()
        }
        | set(user_metadata.keys())
    )
    states: Dict[str, UserCitationState] = {}
    for user_id in user_ids:
        meta = user_metadata.get(user_id, {"user_id": user_id})
        role_name = str(meta.get("role_name") or user_id.replace("user_", "")).strip()
        profile = build_initial_profile(meta, roles.get(role_name, {}))
        states[user_id] = UserCitationState(profile_text=make_profile_text(profile))
    return states


def clone_output_row(
    row: Dict[str, Any],
    label: Dict[str, Any],
    score_payload: Dict[str, Any],
    rank: int,
    top_k: int,
) -> Dict[str, Any]:
    output = dict(row)
    shown = rank <= top_k
    output.update(
        {
            "baseline_method": METHOD_NAME,
            "ranking_source": "baselines.citation_enhanced.runner",
            "ranking_fallback": False,
            "shown": shown,
            "pool_rank": rank,
            "system_rank": rank if shown else None,
            "system_score": round(float(score_payload["system_score"]), 6),
            "system_label": score_payload["system_label"],
            "show_target_count": top_k,
            "drift_bonus": 0.0,
            "drift_topics": [],
            "reading_signal_bonus": 0.0,
            "reading_signal_topics": [],
            "selected": bool(label.get("selected")),
            "oracle_score": label.get("oracle_score", 0.0),
            "oracle_label": label.get("oracle_label", "irrelevant"),
            "select_probability": 0.0,
        }
    )
    for key, value in score_payload.items():
        if key in {"system_score", "system_label"}:
            continue
        if isinstance(value, float):
            output[key] = round(value, 6)
        else:
            output[key] = value
    return output


def group_by_episode(rows: Sequence[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        episode_id = str(row.get("episode_id") or "").strip()
        if episode_id:
            grouped[episode_id].append(row)
    return grouped


def label_key(row: Dict[str, Any]) -> Tuple[str, str]:
    return (str(row.get("episode_id") or ""), paper_identity(row))


def build_label_map(label_rows: Sequence[Dict[str, Any]]) -> Dict[Tuple[str, str], Dict[str, Any]]:
    labels: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for row in label_rows:
        labels[label_key(row)] = {
            "selected": bool(row.get("selected")),
            "oracle_score": row.get("oracle_score", 0.0),
            "oracle_label": row.get("oracle_label", "irrelevant"),
        }
    return labels


def load_clean_benchmark_inputs(input_dir: Path) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    candidate_path = input_dir / CLEAN_CANDIDATE_FILE
    label_path = input_dir / CLEAN_LABEL_FILE
    if candidate_path.exists() and label_path.exists():
        return load_jsonl(candidate_path), load_jsonl(label_path)

    raise FileNotFoundError(
        "Citation-Enhanced baseline refuses to read Full PaperFlow episode_papers.jsonl directly. "
        "Export clean input first with: "
        "python scripts\\export_clean_baseline_benchmark.py --input-dir <benchmark_output>. "
        f"Missing clean files: {candidate_path} and/or {label_path}"
    )


def episode_sort_key(item: Tuple[str, List[Dict[str, Any]]]) -> Tuple[str, str, str]:
    episode_id, rows = item
    first = rows[0] if rows else {}
    return (
        str(first.get("user_id") or episode_id.split("::", 1)[0]),
        str(first.get("date") or ""),
        episode_id,
    )


def max_log_citations_for_day(rows: Sequence[Dict[str, Any]]) -> float:
    counts = [citation_count(row) for row in rows]
    observed = [float(count) for count in counts if count is not None and count > 0]
    return math.log1p(max(observed)) if observed else 0.0


def update_feedback_state(
    state: UserCitationState,
    source_rows: List[Dict[str, Any]],
    label_map: Dict[Tuple[str, str], Dict[str, Any]],
) -> None:
    for row in source_rows:
        label = label_map.get(label_key(row), {})
        if label.get("selected"):
            state.update_selected(row)


def rerank_episodes(
    rows: List[Dict[str, Any]],
    label_rows: List[Dict[str, Any]],
    *,
    top_k: int,
    roles_file: Path,
    input_dir: Path,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    roles = load_roles(roles_file)
    user_metadata = load_user_metadata(input_dir)
    states = build_user_states(user_metadata, roles, rows)
    label_map = build_label_map(label_rows)

    output_rows: List[Dict[str, Any]] = []
    grouped = group_by_episode(rows)
    method_stats = {
        "method_key": METHOD_KEY,
        "method_name": METHOD_NAME,
        "episodes": 0,
        "top_k": top_k,
        "uses_live_citation_api": False,
        "users": {},
    }

    for episode_id, episode_rows in sorted(grouped.items(), key=episode_sort_key):
        if not episode_rows:
            continue
        user_id = str(episode_rows[0].get("user_id") or "").strip()
        if user_id not in states:
            states[user_id] = UserCitationState(profile_text="")
        state = states[user_id]

        day_texts = [paper_text(row) for row in episode_rows]
        idf = build_idf_from_texts([state.profile_text, *state.feedback_texts(), *day_texts])
        state.prepare_vectors(idf)
        max_log_citations = max_log_citations_for_day(episode_rows)

        scored_rows: List[Tuple[float, str, Dict[str, Any], Dict[str, Any]]] = []
        for row in episode_rows:
            identity = paper_identity(row)
            row_vector = vectorize_text(paper_text(row), idf)
            score_payload = score_row(
                row,
                row_vector,
                state,
                max_log_citations=max_log_citations,
            )
            scored_rows.append((score_payload["system_score"], identity, row, score_payload))

        scored_rows.sort(
            key=lambda item: (
                -float(item[0]),
                str(item[2].get("date") or ""),
                str(item[2].get("title") or ""),
                hashlib.sha1(item[1].encode("utf-8")).hexdigest(),
            )
        )

        for rank, (_, _, row, score_payload) in enumerate(scored_rows, start=1):
            label = label_map.get(label_key(row), {})
            output_rows.append(clone_output_row(row, label, score_payload, rank, top_k))

        update_feedback_state(state, episode_rows, label_map)
        method_stats["episodes"] += 1

    for user_id, state in states.items():
        method_stats["users"][user_id] = {
            "selected_count": state.selected_count,
            "selected_identity_count": len(state.selected_identities),
        }

    return output_rows, method_stats


def write_evaluation(output_dir: Path, rows: List[Dict[str, Any]], episode_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    grouped = group_by_episode(rows)
    episode_metrics = {
        episode_id: eval_metrics.evaluate_episode(episode_group, [5, 10, 20])
        for episode_id, episode_group in grouped.items()
        if episode_id
    }
    summary = eval_metrics.aggregate_metrics(episode_metrics, [5, 10, 20])
    dataset_summary = eval_metrics.build_dataset_summary(rows, episode_rows)
    result = {
        "summary": summary,
        "dataset_summary": dataset_summary,
        "episodes": episode_metrics,
    }
    (output_dir / "evaluation_metrics.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "dataset_summary.json").write_text(
        json.dumps(dataset_summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "dataset_summary.md").write_text(
        eval_metrics.build_dataset_summary_markdown(dataset_summary),
        encoding="utf-8",
    )
    (output_dir / "main_experiment_table_top20.md").write_text(
        eval_metrics.build_main_experiment_table(summary, METHOD_NAME),
        encoding="utf-8",
    )
    (output_dir / "case_metrics_table_top20.md").write_text(
        eval_metrics.build_case_metrics_table(summary, METHOD_NAME),
        encoding="utf-8",
    )
    return result


def run_baseline(
    input_dir: Path,
    output_dir: Path,
    *,
    roles_file: Path,
    top_k: int = DEFAULT_TOP_K,
) -> Dict[str, Any]:
    input_dir = input_dir.resolve()
    output_dir = output_dir.resolve()
    episodes_path = input_dir / "episodes.jsonl"
    if not episodes_path.exists():
        raise FileNotFoundError(f"Missing benchmark episodes: {episodes_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    rows, label_rows = load_clean_benchmark_inputs(input_dir)
    episode_rows = load_jsonl(episodes_path)
    reranked_rows, method_stats = rerank_episodes(
        rows,
        label_rows,
        top_k=top_k,
        roles_file=roles_file,
        input_dir=input_dir,
    )

    write_jsonl(output_dir / "episode_papers.jsonl", reranked_rows)
    shutil.copy2(episodes_path, output_dir / "episodes.jsonl")
    if (input_dir / "users.json").exists():
        shutil.copy2(input_dir / "users.json", output_dir / "users.json")

    evaluation = write_evaluation(output_dir, reranked_rows, episode_rows)
    method_stats["input_dir"] = str(input_dir)
    method_stats["output_dir"] = str(output_dir)
    method_stats["roles_file"] = str(roles_file)
    method_stats["using_clean_input"] = True
    (output_dir / "citation_enhanced_summary.json").write_text(
        json.dumps(method_stats, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {"method_stats": method_stats, "evaluation": evaluation}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Citation-Enhanced main-experiment baseline.")
    parser.add_argument("--input-dir", required=True, help="Clean baseline input directory.")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory. Defaults to <input-dir>/../main_experiment/citation_enhanced.",
    )
    parser.add_argument(
        "--roles-file",
        default=str(PROJECT_ROOT / "data" / "roles.json"),
        help="Initial role/profile metadata used for cold-start construction.",
    )
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K, help="Number of papers shown per episode.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_dir = Path(args.input_dir)
    output_dir = (
        Path(args.output_dir)
        if args.output_dir
        else input_dir.parent / "main_experiment" / METHOD_KEY
    )
    result = run_baseline(
        input_dir=input_dir,
        output_dir=output_dir,
        roles_file=Path(args.roles_file),
        top_k=args.top_k,
    )
    summary = result["evaluation"]["summary"]
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\nCitation-Enhanced outputs written to: {output_dir}")


if __name__ == "__main__":
    main()
