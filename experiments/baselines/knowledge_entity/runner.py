#!/usr/bin/env python3
"""
Knowledge-Entity Enhanced Recommendation baseline runner.

This runner reranks clean frozen PaperFlow candidate pools with fine-grained
entity and multifaceted document signals. It does not use PaperFlow dynamic
profiles, interest drift states, must-read priority, reading reports, or oracle
labels for ranking.
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


METHOD_KEY = "knowledge_entity"
METHOD_NAME = "Knowledge-Entity Enhanced Recommendation"
DEFAULT_TOP_K = 20
CLEAN_CANDIDATE_FILE = "candidate_pools.jsonl"
CLEAN_LABEL_FILE = "labels_for_eval.jsonl"

SCORE_WEIGHTS = {
    "profile_entity": 0.30,
    "history_entity": 0.25,
    "multifacet_similarity": 0.30,
    "metadata_signal": 0.10,
    "entity_density": 0.05,
}

LABEL_THRESHOLDS = {
    "high_relevant": 0.70,
    "maybe_interested": 0.45,
}

TOKEN_RE = re.compile(r"[a-z0-9]+(?:[-_][a-z0-9]+)*", flags=re.IGNORECASE)

METADATA_ENTITY_FIELDS = (
    "topics",
    "keywords",
    "institutions",
    "affiliations",
)

CITATION_COUNT_FIELDS = (
    "cited_by_count",
    "citation_count",
    "citations",
    "influential_citation_count",
)

STOPWORDS = {
    "about",
    "after",
    "again",
    "against",
    "also",
    "among",
    "based",
    "because",
    "been",
    "being",
    "between",
    "both",
    "cannot",
    "could",
    "data",
    "different",
    "does",
    "during",
    "each",
    "from",
    "have",
    "into",
    "large",
    "learning",
    "many",
    "more",
    "most",
    "paper",
    "papers",
    "performance",
    "present",
    "propose",
    "proposed",
    "research",
    "result",
    "results",
    "show",
    "shows",
    "study",
    "system",
    "systems",
    "that",
    "their",
    "these",
    "this",
    "through",
    "using",
    "with",
    "within",
    "without",
}


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
        values: List[str] = []
        for item in raw_value:
            if isinstance(item, dict):
                values.extend(parse_string_list(item))
            else:
                values.append(str(item))
        return [item.strip() for item in values if item.strip()]
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
        return [item.strip() for item in re.split(r"[,;|\n]+", raw_value) if item.strip()]
    return [str(raw_value).strip()] if str(raw_value).strip() else []


def normalize_phrase_text(value: Any) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).split())


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
    for key in ("paper_id", "doi", "arxiv_id", "url"):
        value = str(row.get(key) or "").strip().casefold()
        if value:
            return f"{key}:{value}"
    return "title:" + normalize_phrase_text(row.get("title"))


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


def dedupe_strings(values: Iterable[Any]) -> List[str]:
    result: List[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = str(value or "").strip()
        if not cleaned:
            continue
        normalized = normalize_phrase_text(cleaned)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(cleaned)
    return result


def citation_count(row: Dict[str, Any]) -> Optional[float]:
    for field_name in CITATION_COUNT_FIELDS:
        value = row.get(field_name)
        if value in (None, ""):
            continue
        count = safe_float(value, -1.0)
        if count >= 0:
            return count
    return None


def normalized_citation_signal(row: Dict[str, Any], max_log_citations: float) -> Tuple[float, bool]:
    count = citation_count(row)
    if count is not None and max_log_citations > 0:
        return clamp(math.log1p(count) / max_log_citations), True
    identifier_bonus = 0.12 if row.get("doi") or row.get("arxiv_id") else 0.0
    metadata_bonus = 0.10 if row.get("venue") or row.get("journal") else 0.0
    return clamp(identifier_bonus + metadata_bonus), False


def metadata_entities(row: Dict[str, Any]) -> List[str]:
    values: List[str] = []
    for field_name in METADATA_ENTITY_FIELDS:
        values.extend(parse_string_list(row.get(field_name)))
    return dedupe_strings(values)


def candidate_entity_phrases(text: Any, *, max_entities: int = 28) -> List[str]:
    raw_tokens = tokenize(text)
    filtered = [
        token for token in raw_tokens
        if token not in STOPWORDS and not token.isdigit() and len(token) > 2
    ]
    counts: Counter[str] = Counter()
    for ngram_size in (3, 2):
        for index in range(0, max(0, len(filtered) - ngram_size + 1)):
            phrase_tokens = filtered[index:index + ngram_size]
            if any(token in STOPWORDS for token in phrase_tokens):
                continue
            phrase = " ".join(phrase_tokens)
            if len(phrase) >= 7:
                counts[phrase] += 1 + 0.25 * (ngram_size - 1)
    for token in filtered:
        if "-" in token or len(token) >= 8:
            counts[token.replace("-", " ")] += 0.75
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [phrase for phrase, _ in ranked[:max_entities]]


def extract_entities(row: Dict[str, Any]) -> List[str]:
    entities = metadata_entities(row)
    entities.extend(candidate_entity_phrases(f"{row.get('title') or ''}. {row.get('abstract') or ''}"))
    return dedupe_strings(entities)


def entities_text(entities: Sequence[str]) -> str:
    return " ".join(normalize_phrase_text(entity) for entity in entities if normalize_phrase_text(entity))


def load_roles(roles_file: Path) -> Dict[str, Dict[str, Any]]:
    payload = load_json(roles_file)
    roles = payload.get("roles") if isinstance(payload, dict) else {}
    return roles if isinstance(roles, dict) else {}


def _seed_direction_entries(raw_value: Any) -> List[Tuple[str, float]]:
    entries: List[Tuple[str, float]] = []
    if isinstance(raw_value, dict):
        for key, value in raw_value.items():
            entries.append((str(key), safe_float(value, 0.6)))
    elif isinstance(raw_value, list):
        for item in raw_value:
            if isinstance(item, dict):
                key = str(item.get("canonical_name") or item.get("bootstrap_phrase") or "").strip()
                weight = safe_float(item.get("weight"), 0.6)
            else:
                key = str(item or "").strip()
                weight = 0.6
            if key:
                entries.append((key, weight))
    return entries


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


def build_initial_profile(user_meta: Dict[str, Any], role: Dict[str, Any]) -> Dict[str, Any]:
    directions: Dict[str, float] = {}
    for key, weight in _seed_direction_entries(user_meta.get("seed_directions")):
        directions[key] = max(directions.get(key, 0.0), weight)
    for key, weight in _seed_direction_entries(role.get("seed_directions")):
        directions[key] = max(directions.get(key, 0.0), weight)
    for key, weight in _seed_direction_entries(role.get("core_directions")):
        directions[key] = max(directions.get(key, 0.0), weight)

    terms: List[str] = []
    for direction in directions:
        terms.extend(_direction_terms(direction))
    terms.extend(parse_string_list(user_meta.get("initial_topics")))
    terms.extend(parse_string_list(role.get("secondary_topics")))
    terms.extend(parse_string_list(role.get("positive_keywords")))
    terms.extend(parse_string_list(role.get("must_read_keywords")))
    terms.extend(parse_string_list(user_meta.get("description")))
    terms.append(str(role.get("description") or ""))
    terms.append(str(role.get("bootstrap_summary") or ""))
    entity_terms = dedupe_strings([*directions.keys(), *terms])
    profile_text = " ".join(entity_terms)
    return {
        "directions": directions,
        "entity_terms": entity_terms,
        "profile_text": profile_text,
    }


@dataclass
class PaperRepresentation:
    title_vector: Dict[str, float]
    abstract_vector: Dict[str, float]
    entity_vector: Dict[str, float]
    metadata_vector: Dict[str, float]
    entities: List[str]


@dataclass
class UserKnowledgeEntityState:
    profile_text: str
    profile_entities: List[str]
    profile_vector: Dict[str, float] = field(default_factory=dict)
    profile_entity_vector: Dict[str, float] = field(default_factory=dict)
    selected_texts: List[str] = field(default_factory=list)
    selected_entity_texts: List[str] = field(default_factory=list)
    selected_entities: set[str] = field(default_factory=set)
    selected_text_sum: Dict[str, float] = field(default_factory=dict)
    selected_entity_sum: Dict[str, float] = field(default_factory=dict)
    selected_count: int = 0

    def feedback_texts(self) -> List[str]:
        return [*self.selected_texts, *self.selected_entity_texts]

    def prepare_vectors(self, idf: Dict[str, float]) -> None:
        self.profile_vector = vectorize_text(self.profile_text, idf)
        self.profile_entity_vector = vectorize_text(entities_text(self.profile_entities), idf)
        self.selected_text_sum = {}
        self.selected_entity_sum = {}
        for text in self.selected_texts:
            add_weighted_vector(self.selected_text_sum, vectorize_text(text, idf), 1.0)
        for text in self.selected_entity_texts:
            add_weighted_vector(self.selected_entity_sum, vectorize_text(text, idf), 1.0)

    def selected_text_centroid(self) -> Dict[str, float]:
        return normalize_vector(self.selected_text_sum)

    def selected_entity_centroid(self) -> Dict[str, float]:
        return normalize_vector(self.selected_entity_sum)

    def update_selected(self, row: Dict[str, Any]) -> None:
        entities = extract_entities(row)
        self.selected_texts.append(paper_text(row))
        self.selected_entity_texts.append(entities_text(entities))
        self.selected_entities.update(normalize_phrase_text(entity) for entity in entities)
        self.selected_count += 1


def build_paper_representation(row: Dict[str, Any], idf: Dict[str, float]) -> PaperRepresentation:
    entities = extract_entities(row)
    metadata_text = " ".join(
        parse_string_list(row.get("topics"))
        + parse_string_list(row.get("keywords"))
        + parse_string_list(row.get("source"))
        + parse_string_list(row.get("venue"))
        + parse_string_list(row.get("journal"))
    )
    return PaperRepresentation(
        title_vector=vectorize_text(row.get("title"), idf),
        abstract_vector=vectorize_text(row.get("abstract"), idf),
        entity_vector=vectorize_text(entities_text(entities), idf),
        metadata_vector=vectorize_text(metadata_text, idf),
        entities=entities,
    )


def multifacet_similarity(rep: PaperRepresentation, state: UserKnowledgeEntityState) -> float:
    profile_score = (
        0.25 * scaled_similarity(rep.title_vector, state.profile_vector)
        + 0.30 * scaled_similarity(rep.abstract_vector, state.profile_vector)
        + 0.35 * scaled_similarity(rep.entity_vector, state.profile_entity_vector)
        + 0.10 * scaled_similarity(rep.metadata_vector, state.profile_entity_vector)
    )
    if state.selected_count <= 0:
        return clamp(profile_score)
    history_score = (
        0.35 * scaled_similarity(rep.entity_vector, state.selected_entity_centroid())
        + 0.25 * scaled_similarity(rep.abstract_vector, state.selected_text_centroid())
        + 0.25 * scaled_similarity(rep.title_vector, state.selected_text_centroid())
        + 0.15 * scaled_similarity(rep.metadata_vector, state.selected_entity_centroid())
    )
    return clamp(0.55 * history_score + 0.45 * profile_score)


def profile_entity_score(rep: PaperRepresentation, state: UserKnowledgeEntityState) -> float:
    profile_entities = {normalize_phrase_text(entity) for entity in state.profile_entities}
    row_entities = {normalize_phrase_text(entity) for entity in rep.entities}
    overlap = jaccard(profile_entities, row_entities)
    vector_score = scaled_similarity(rep.entity_vector, state.profile_entity_vector)
    return clamp(0.55 * vector_score + 0.45 * overlap)


def history_entity_score(rep: PaperRepresentation, state: UserKnowledgeEntityState) -> float:
    if state.selected_count <= 0:
        return 0.0
    row_entities = {normalize_phrase_text(entity) for entity in rep.entities}
    overlap = jaccard(row_entities, state.selected_entities)
    vector_score = scaled_similarity(rep.entity_vector, state.selected_entity_centroid())
    return clamp(0.60 * vector_score + 0.40 * overlap)


def metadata_signal_score(row: Dict[str, Any], rep: PaperRepresentation, max_log_citations: float) -> Tuple[float, bool]:
    citation_signal, has_count = normalized_citation_signal(row, max_log_citations)
    explicit_metadata = metadata_entities(row)
    metadata_coverage = clamp(len(explicit_metadata) / 8.0)
    doi_signal = 0.10 if row.get("doi") else 0.0
    return clamp(0.55 * citation_signal + 0.35 * metadata_coverage + doi_signal), has_count


def entity_density_score(rep: PaperRepresentation) -> float:
    return clamp(len(rep.entities) / 24.0)


def label_for_score(score: float) -> str:
    if score >= LABEL_THRESHOLDS["high_relevant"]:
        return "high_relevant"
    if score >= LABEL_THRESHOLDS["maybe_interested"]:
        return "maybe_interested"
    return "edge_relevant"


def score_row(
    row: Dict[str, Any],
    rep: PaperRepresentation,
    state: UserKnowledgeEntityState,
    *,
    max_log_citations: float,
) -> Dict[str, Any]:
    profile_entity = profile_entity_score(rep, state)
    history_entity = history_entity_score(rep, state)
    multifacet = multifacet_similarity(rep, state)
    metadata_signal, has_citation_count = metadata_signal_score(row, rep, max_log_citations)
    density = entity_density_score(rep)
    final_score = clamp(
        SCORE_WEIGHTS["profile_entity"] * profile_entity
        + SCORE_WEIGHTS["history_entity"] * history_entity
        + SCORE_WEIGHTS["multifacet_similarity"] * multifacet
        + SCORE_WEIGHTS["metadata_signal"] * metadata_signal
        + SCORE_WEIGHTS["entity_density"] * density
    )
    return {
        "system_score": final_score,
        "system_label": label_for_score(final_score),
        "profile_entity_score": profile_entity,
        "history_entity_score": history_entity,
        "multifacet_similarity_score": multifacet,
        "metadata_signal_score": metadata_signal,
        "entity_density_score": density,
        "entity_count": len(rep.entities),
        "top_entities": rep.entities[:10],
        "has_citation_count": has_citation_count,
        "citation_count": citation_count(row),
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
) -> Dict[str, UserKnowledgeEntityState]:
    user_ids = sorted(
        {
            str(row.get("user_id") or "").strip()
            for row in episode_rows
            if str(row.get("user_id") or "").strip()
        }
        | set(user_metadata.keys())
    )
    states: Dict[str, UserKnowledgeEntityState] = {}
    for user_id in user_ids:
        meta = user_metadata.get(user_id, {"user_id": user_id})
        role_name = str(meta.get("role_name") or user_id.replace("user_", "")).strip()
        profile = build_initial_profile(meta, roles.get(role_name, {}))
        states[user_id] = UserKnowledgeEntityState(
            profile_text=str(profile.get("profile_text") or ""),
            profile_entities=list(profile.get("entity_terms") or []),
        )
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
            "ranking_source": "baselines.knowledge_entity.runner",
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
        "Knowledge-Entity baseline refuses to read Full PaperFlow episode_papers.jsonl directly. "
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
    state: UserKnowledgeEntityState,
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
        "uses_dynamic_profile": False,
        "uses_reading_reports": False,
        "uses_live_entity_api": False,
        "users": {},
    }

    for episode_id, episode_rows in sorted(grouped.items(), key=episode_sort_key):
        if not episode_rows:
            continue
        user_id = str(episode_rows[0].get("user_id") or "").strip()
        if user_id not in states:
            states[user_id] = UserKnowledgeEntityState(profile_text="", profile_entities=[])
        state = states[user_id]

        entity_texts = [entities_text(extract_entities(row)) for row in episode_rows]
        day_texts = [paper_text(row) for row in episode_rows]
        idf = build_idf_from_texts([
            state.profile_text,
            entities_text(state.profile_entities),
            *state.feedback_texts(),
            *entity_texts,
            *day_texts,
        ])
        state.prepare_vectors(idf)
        max_log_citations = max_log_citations_for_day(episode_rows)

        scored_rows: List[Tuple[float, str, Dict[str, Any], Dict[str, Any]]] = []
        for row in episode_rows:
            identity = paper_identity(row)
            rep = build_paper_representation(row, idf)
            score_payload = score_row(
                row,
                rep,
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
            "profile_entity_count": len(state.profile_entities),
            "selected_entity_count": len(state.selected_entities),
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
    (output_dir / "knowledge_entity_summary.json").write_text(
        json.dumps(method_stats, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {"method_stats": method_stats, "evaluation": evaluation}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Knowledge-Entity main-experiment baseline.")
    parser.add_argument("--input-dir", required=True, help="Clean baseline input directory.")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory. Defaults to <input-dir>/../main_experiment/knowledge_entity.",
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
    print(f"\nKnowledge-Entity outputs written to: {output_dir}")


if __name__ == "__main__":
    main()
