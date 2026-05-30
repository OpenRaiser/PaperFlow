#!/usr/bin/env python3
"""
Scholar Inbox Pipeline baseline runner.

This runner operationalizes the Scholar Inbox-style daily digest baseline for
the PaperFlow main experiment. It reranks clean frozen PaperFlow benchmark
candidate pools without using oracle labels, future feedback, PaperFlow dynamic
profile fields, or reading-report outputs.
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

from experiments.benchmark import evaluate_simulation_metrics as eval_metrics


METHOD_KEY = "scholar_inbox"
METHOD_NAME = "Scholar Inbox Pipeline"
DEFAULT_TOP_K = 20
DEFAULT_BACKGROUND_NEGATIVES_PER_DAY = 20
MIN_CLASSIFIER_POSITIVES = 3
MIN_CLASSIFIER_NEGATIVES = 8
CLEAN_CANDIDATE_FILE = "candidate_pools.jsonl"
CLEAN_LABEL_FILE = "labels_for_eval.jsonl"
LOGISTIC_EPOCHS = 40
LOGISTIC_LEARNING_RATE = 0.35
LOGISTIC_L2 = 0.001

SCORE_WEIGHTS = {
    "content": 0.85,
    "cold_start": 0.15,
    "author": 0.00,
    "institution": 0.00,
    "keyword": 0.00,
    "source": 0.00,
}

LABEL_THRESHOLDS = {
    "high_relevant": 0.70,
    "maybe_interested": 0.45,
}

TOKEN_RE = re.compile(r"[a-z0-9]+(?:[-_][a-z0-9]+)*", flags=re.IGNORECASE)


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


def parse_authors(raw_value: Any) -> List[str]:
    if raw_value in (None, "", []):
        return []
    if isinstance(raw_value, list):
        return [str(item).strip() for item in raw_value if str(item).strip()]
    if isinstance(raw_value, str):
        try:
            parsed = json.loads(raw_value)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
        if parsed is not None:
            return [str(parsed).strip()]
        return [item.strip() for item in raw_value.split(",") if item.strip()]
    return [str(raw_value).strip()] if str(raw_value).strip() else []


def parse_string_list(raw_value: Any) -> List[str]:
    if raw_value in (None, "", []):
        return []
    if isinstance(raw_value, list):
        return [str(item).strip() for item in raw_value if str(item).strip()]
    if isinstance(raw_value, dict):
        return [str(key).strip() for key in raw_value.keys() if str(key).strip()]
    if isinstance(raw_value, str):
        try:
            parsed = json.loads(raw_value)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, (list, dict)):
            return parse_string_list(parsed)
        return [item.strip() for item in re.split(r"[,;，；]", raw_value) if item.strip()]
    return [str(raw_value).strip()] if str(raw_value).strip() else []


def normalize_lookup(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


def normalize_phrase_text(value: Any) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).split())


def contains_phrase(text: str, phrase: str) -> bool:
    normalized_phrase = normalize_phrase_text(phrase)
    if not normalized_phrase:
        return False
    return f" {normalized_phrase} " in f" {text} "


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
    # Scholar Inbox encodes papers from title and abstract. Keep metadata out of
    # the representation so this baseline remains content-based, not source- or
    # entity-prior driven.
    parts = [row.get("title"), row.get("abstract")]
    return " ".join(str(part or "") for part in parts if part)


def paper_identity(row: Dict[str, Any]) -> str:
    explicit_identity = str(row.get("paper_identity") or "").strip()
    if explicit_identity:
        return explicit_identity
    for key in ("paper_id", "doi", "arxiv_id", "url"):
        value = str(row.get(key) or "").strip().casefold()
        if value:
            return f"{key}:{value}"
    return "title:" + normalize_phrase_text(row.get("title"))


def build_idf(rows: Sequence[Dict[str, Any]]) -> Dict[str, float]:
    return build_idf_from_texts([paper_text(row) for row in rows])


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
    # TF-IDF cosine values are naturally small on scientific abstracts; scaling
    # keeps the fixed score thresholds interpretable without changing ordering.
    return clamp(cosine(left, right) * 4.0)


def sigmoid(value: float) -> float:
    if value >= 40:
        return 1.0
    if value <= -40:
        return 0.0
    return 1.0 / (1.0 + math.exp(-value))


def sparse_dot(weights: Dict[str, float], vector: Dict[str, float]) -> float:
    if not weights or not vector:
        return 0.0
    if len(weights) > len(vector):
        return sum(value * weights.get(key, 0.0) for key, value in vector.items())
    return sum(value * vector.get(key, 0.0) for key, value in weights.items())


def balanced_logistic_samples(
    samples: Sequence[Tuple[Dict[str, float], int, float]],
) -> List[Tuple[Dict[str, float], int, float]]:
    positive_total = sum(weight for _, label, weight in samples if label == 1 and weight > 0)
    negative_total = sum(weight for _, label, weight in samples if label == 0 and weight > 0)
    if positive_total <= 0 or negative_total <= 0:
        return []
    balanced: List[Tuple[Dict[str, float], int, float]] = []
    for vector, label, weight in samples:
        if not vector or weight <= 0:
            continue
        scale = 0.5 / positive_total if label == 1 else 0.5 / negative_total
        balanced.append((vector, label, weight * scale))
    return balanced


def train_weighted_logistic_regression(
    samples: Sequence[Tuple[Dict[str, float], int, float]],
    *,
    epochs: int = LOGISTIC_EPOCHS,
    learning_rate: float = LOGISTIC_LEARNING_RATE,
    l2: float = LOGISTIC_L2,
) -> Tuple[Dict[str, float], float]:
    """Train a small deterministic sparse logistic model for one user."""
    weighted_samples = balanced_logistic_samples(samples)
    if not weighted_samples:
        return {}, 0.0

    weights: Dict[str, float] = {}
    bias = 0.0
    for _ in range(max(1, epochs)):
        for vector, label, sample_weight in weighted_samples:
            prediction = sigmoid(sparse_dot(weights, vector) + bias)
            error = (prediction - float(label)) * sample_weight
            for key, value in vector.items():
                current = weights.get(key, 0.0)
                updated = current - learning_rate * (error * value + l2 * current)
                if abs(updated) > 1e-12:
                    weights[key] = updated
                elif key in weights:
                    del weights[key]
            bias -= learning_rate * error
    return weights, bias


def load_roles(roles_file: Path) -> Dict[str, Dict[str, Any]]:
    payload = load_json(roles_file)
    roles = payload.get("roles") if isinstance(payload, dict) else {}
    return roles if isinstance(roles, dict) else {}


def _seed_direction_entries(raw_value: Any) -> List[Tuple[str, float, str]]:
    entries: List[Tuple[str, float, str]] = []
    if isinstance(raw_value, dict):
        for key, value in raw_value.items():
            text = str(key or "").strip()
            if text:
                entries.append((text, safe_float(value, 0.6), text))
    elif isinstance(raw_value, list):
        for item in raw_value:
            if isinstance(item, dict):
                canonical = str(item.get("canonical_name") or item.get("name") or "").strip()
                phrase = str(item.get("bootstrap_phrase") or canonical).strip()
                key = canonical or phrase
                if key:
                    entries.append((key, safe_float(item.get("weight"), 0.6), phrase or key))
            else:
                text = str(item or "").strip()
                if text:
                    entries.append((text, 0.6, text))
    else:
        for text in parse_string_list(raw_value):
            entries.append((text, 0.6, text))
    return entries


def build_initial_profile(user_meta: Dict[str, Any], role: Dict[str, Any]) -> Dict[str, Any]:
    directions: Dict[str, float] = {}
    direction_terms: List[str] = []

    for key, weight, phrase in (
        _seed_direction_entries(user_meta.get("seed_directions"))
        + _seed_direction_entries(role.get("seed_directions"))
        + _seed_direction_entries(role.get("core_directions"))
    ):
        if key:
            directions[key] = max(directions.get(key, 0.0), weight)
        direction_terms.extend([key, key.replace("-", " "), phrase])

    description = str(user_meta.get("description") or role.get("description") or "").strip()
    bootstrap_summary = str(role.get("bootstrap_summary") or "").strip()
    profile_terms: List[str] = dedupe_strings(
        direction_terms
        + parse_string_list(description)
        + parse_string_list(bootstrap_summary)
    )

    return {
        "directions": directions,
        "terms": profile_terms,
        "keywords": [],
        "authors": [],
        "institutions": [],
        "description": description,
        "bootstrap_summary": bootstrap_summary,
    }


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


@dataclass
class UserFeedbackState:
    profile: Dict[str, Any]
    profile_text: str
    profile_vector: Dict[str, float] = field(default_factory=dict)
    positive_sum: Dict[str, float] = field(default_factory=dict)
    negative_sum: Dict[str, float] = field(default_factory=dict)
    positive_examples: List[Tuple[str, float]] = field(default_factory=list)
    negative_examples: List[Tuple[str, float]] = field(default_factory=list)
    logistic_weights: Dict[str, float] = field(default_factory=dict)
    logistic_bias: float = 0.0
    logistic_trained: bool = False
    positive_count: int = 0
    negative_count: int = 0

    @property
    def uses_feedback_classifier(self) -> bool:
        return self.positive_count >= MIN_CLASSIFIER_POSITIVES and self.negative_count >= MIN_CLASSIFIER_NEGATIVES

    def positive_centroid(self) -> Dict[str, float]:
        return normalize_vector(self.positive_sum)

    def negative_centroid(self) -> Dict[str, float]:
        return normalize_vector(self.negative_sum)

    def prepare_vectors(self, idf: Dict[str, float]) -> None:
        self.profile_vector = vectorize_text(self.profile_text, idf)
        self.positive_sum = {}
        self.negative_sum = {}
        training_samples: List[Tuple[Dict[str, float], int, float]] = []
        for text, weight in self.positive_examples:
            vector = vectorize_text(text, idf)
            add_weighted_vector(self.positive_sum, vector, weight)
            training_samples.append((vector, 1, weight))
        for text, weight in self.negative_examples:
            vector = vectorize_text(text, idf)
            add_weighted_vector(self.negative_sum, vector, weight)
            training_samples.append((vector, 0, weight))
        if self.uses_feedback_classifier:
            self.logistic_weights, self.logistic_bias = train_weighted_logistic_regression(training_samples)
            self.logistic_trained = bool(self.logistic_weights)
        else:
            self.logistic_weights = {}
            self.logistic_bias = 0.0
            self.logistic_trained = False

    def feedback_texts(self) -> List[str]:
        return [text for text, _ in self.positive_examples + self.negative_examples]

    def update_positive_text(self, text: str, weight: float = 1.0) -> None:
        self.positive_examples.append((text, weight))
        self.positive_count += 1

    def update_negative_text(self, text: str, weight: float = 0.35) -> None:
        self.negative_examples.append((text, weight))
        self.negative_count += 1

    def predict_logistic(self, vector: Dict[str, float]) -> float:
        if not self.logistic_trained:
            return 0.0
        return sigmoid(sparse_dot(self.logistic_weights, vector) + self.logistic_bias)


def source_prior(row: Dict[str, Any]) -> float:
    source = str(row.get("source") or row.get("venue") or row.get("journal") or "").casefold()
    if "openreview" in source:
        return 0.70
    if any(token in source for token in ("journal", "nature", "science", "cell", "pnas", "acm", "ieee")):
        return 0.65
    if "arxiv" in source:
        return 0.55
    return 0.50


def author_match_score(row: Dict[str, Any], profile: Dict[str, Any]) -> float:
    profile_authors = [normalize_lookup(author) for author in profile.get("authors", [])]
    if not profile_authors:
        return 0.0
    row_authors = [normalize_lookup(author) for author in parse_authors(row.get("authors"))]
    if not row_authors:
        return 0.0
    for wanted in profile_authors:
        if any(wanted and (wanted == author or wanted in author or author in wanted) for author in row_authors):
            return 1.0
    return 0.0


def institution_match_score(row: Dict[str, Any], profile: Dict[str, Any]) -> float:
    profile_institutions = [normalize_phrase_text(item) for item in profile.get("institutions", [])]
    if not profile_institutions:
        return 0.0
    text = normalize_phrase_text(
        " ".join(
            parse_string_list(row.get("institutions"))
            + parse_string_list(row.get("affiliations"))
            + [row.get("abstract") or "", row.get("title") or ""]
        )
    )
    if not text:
        return 0.0
    return 1.0 if any(contains_phrase(text, institution) for institution in profile_institutions) else 0.0


def keyword_match_score(row: Dict[str, Any], profile: Dict[str, Any]) -> float:
    keywords = profile.get("keywords", []) or []
    if not keywords:
        return 0.0
    title = normalize_phrase_text(row.get("title"))
    full_text = normalize_phrase_text(f"{row.get('title') or ''} {row.get('abstract') or ''}")
    title_hits = sum(1 for keyword in keywords if contains_phrase(title, keyword))
    text_hits = sum(1 for keyword in keywords if contains_phrase(full_text, keyword))
    if title_hits:
        return clamp(0.65 + 0.12 * title_hits)
    return clamp(0.25 * text_hits)


def content_score(row_vector: Dict[str, float], state: UserFeedbackState) -> Tuple[float, float, float, bool]:
    cold_score = scaled_similarity(row_vector, state.profile_vector)
    if state.positive_count <= 0:
        return cold_score, cold_score, 0.0, False

    positive_score = scaled_similarity(row_vector, state.positive_centroid())
    negative_score = scaled_similarity(row_vector, state.negative_centroid()) if state.negative_count else 0.0
    if state.logistic_trained:
        return state.predict_logistic(row_vector), positive_score, negative_score, True

    learned_score = clamp(0.15 + 0.85 * positive_score - 0.30 * negative_score)

    # Before enough ratings accumulate, interpolate with cold-start similarity.
    if not state.uses_feedback_classifier:
        learned_score = 0.55 * learned_score + 0.45 * cold_score

    return learned_score, positive_score, negative_score, False


def label_for_score(score: float) -> str:
    if score >= LABEL_THRESHOLDS["high_relevant"]:
        return "high_relevant"
    if score >= LABEL_THRESHOLDS["maybe_interested"]:
        return "maybe_interested"
    return "edge_relevant"


def score_row(row: Dict[str, Any], row_vector: Dict[str, float], state: UserFeedbackState) -> Dict[str, Any]:
    content, positive, negative, uses_classifier = content_score(row_vector, state)
    cold = scaled_similarity(row_vector, state.profile_vector)
    author = author_match_score(row, state.profile)
    institution = institution_match_score(row, state.profile)
    keyword = keyword_match_score(row, state.profile)
    source = source_prior(row)
    final_score = (
        SCORE_WEIGHTS["content"] * content
        + SCORE_WEIGHTS["cold_start"] * cold
        + SCORE_WEIGHTS["author"] * author
        + SCORE_WEIGHTS["institution"] * institution
        + SCORE_WEIGHTS["keyword"] * keyword
        + SCORE_WEIGHTS["source"] * source
    )
    final_score = clamp(final_score)
    return {
        "system_score": final_score,
        "system_label": label_for_score(final_score),
        "content_score": content,
        "cold_start_score": cold,
        "positive_similarity": positive,
        "negative_similarity": negative,
        "author_match_score": author,
        "institution_match_score": institution,
        "keyword_match_score": keyword,
        "source_prior": source,
        "uses_feedback_classifier": uses_classifier,
        "training_positive_count": state.positive_count,
        "training_negative_count": state.negative_count,
    }


def stable_background_rows(rows: List[Dict[str, Any]], label_map: Dict[Tuple[str, str], Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
    if limit <= 0:
        return []
    candidates = [
        row for row in rows
        if not bool(label_map.get((str(row.get("episode_id") or ""), paper_identity(row)), {}).get("selected"))
    ]
    candidates.sort(
        key=lambda row: hashlib.sha1(
            f"{row.get('episode_id')}::{paper_identity(row)}".encode("utf-8")
        ).hexdigest()
    )
    return candidates[:limit]


def update_feedback_state(
    state: UserFeedbackState,
    source_rows: List[Dict[str, Any]],
    label_map: Dict[Tuple[str, str], Dict[str, Any]],
    *,
    background_negatives_per_day: int,
) -> None:
    for row in source_rows:
        label = label_map.get((str(row.get("episode_id") or ""), paper_identity(row)), {})
        if not label.get("selected"):
            continue
        state.update_positive_text(paper_text(row), weight=1.0)

    for row in stable_background_rows(source_rows, label_map, background_negatives_per_day):
        state.update_negative_text(paper_text(row), weight=0.10)


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


def make_profile_text(profile: Dict[str, Any]) -> str:
    parts = [
        profile.get("description", ""),
        " ".join(profile.get("terms", []) or []),
        " ".join(profile.get("keywords", []) or []),
    ]
    return " ".join(str(part or "") for part in parts if part)


def build_user_states(
    user_metadata: Dict[str, Dict[str, Any]],
    roles: Dict[str, Dict[str, Any]],
    episode_rows: Sequence[Dict[str, Any]],
) -> Dict[str, UserFeedbackState]:
    user_ids = sorted(
        {
            str(row.get("user_id") or "").strip()
            for row in episode_rows
            if str(row.get("user_id") or "").strip()
        }
        | set(user_metadata.keys())
    )
    states: Dict[str, UserFeedbackState] = {}
    for user_id in user_ids:
        meta = user_metadata.get(user_id, {"user_id": user_id})
        role_name = str(meta.get("role_name") or user_id.replace("user_", "")).strip()
        role = roles.get(role_name, {})
        profile = build_initial_profile(meta, role)
        states[user_id] = UserFeedbackState(profile=profile, profile_text=make_profile_text(profile))
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
            "ranking_source": "baselines.scholar_inbox.runner",
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
        "Scholar Inbox baseline refuses to read Full PaperFlow episode_papers.jsonl directly. "
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


def rerank_episodes(
    rows: List[Dict[str, Any]],
    label_rows: List[Dict[str, Any]],
    *,
    top_k: int,
    roles_file: Path,
    input_dir: Path,
    background_negatives_per_day: int,
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
        "background_negatives_per_day": background_negatives_per_day,
        "users": {},
    }

    for episode_id, episode_rows in sorted(grouped.items(), key=episode_sort_key):
        if not episode_rows:
            continue
        user_id = str(episode_rows[0].get("user_id") or "").strip()
        if user_id not in states:
            states[user_id] = UserFeedbackState(profile={}, profile_text="")
        state = states[user_id]
        day_texts = [paper_text(row) for row in episode_rows]
        idf = build_idf_from_texts([state.profile_text, *state.feedback_texts(), *day_texts])
        state.prepare_vectors(idf)

        scored_rows: List[Tuple[float, str, Dict[str, Any], Dict[str, Any]]] = []
        for row in episode_rows:
            identity = paper_identity(row)
            row_vector = vectorize_text(paper_text(row), idf)
            score_payload = score_row(row, row_vector, state)
            scored_rows.append((score_payload["system_score"], identity, row, score_payload))

        scored_rows.sort(
            key=lambda item: (
                -float(item[0]),
                str(item[2].get("date") or ""),
                str(item[2].get("title") or ""),
                item[1],
            )
        )

        for rank, (_, _, row, score_payload) in enumerate(scored_rows, start=1):
            label = label_map.get(label_key(row), {})
            output_rows.append(clone_output_row(row, label, score_payload, rank, top_k))

        update_feedback_state(
            state,
            episode_rows,
            label_map,
            background_negatives_per_day=background_negatives_per_day,
        )
        method_stats["episodes"] += 1

    for user_id, state in states.items():
        method_stats["users"][user_id] = {
            "positive_count": state.positive_count,
            "negative_count": state.negative_count,
            "has_classifier_training_data": state.uses_feedback_classifier,
            "uses_feedback_classifier": state.logistic_trained,
            "profile_keywords": state.profile.get("keywords", []),
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
    background_negatives_per_day: int = DEFAULT_BACKGROUND_NEGATIVES_PER_DAY,
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
        background_negatives_per_day=background_negatives_per_day,
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
    (output_dir / "scholar_inbox_summary.json").write_text(
        json.dumps(method_stats, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {"method_stats": method_stats, "evaluation": evaluation}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Scholar Inbox main-experiment baseline.")
    parser.add_argument("--input-dir", required=True, help="Frozen Full PaperFlow benchmark output directory.")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory. Defaults to <input-dir>/main_experiment/scholar_inbox.",
    )
    parser.add_argument(
        "--roles-file",
        default=str(PROJECT_ROOT / "data" / "roles.json"),
        help="Initial role/profile metadata used for cold-start construction.",
    )
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K, help="Number of papers shown per episode.")
    parser.add_argument(
        "--background-negatives-per-day",
        type=int,
        default=DEFAULT_BACKGROUND_NEGATIVES_PER_DAY,
        help="Deterministic unshown background negatives added after each day.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir) if args.output_dir else input_dir / "main_experiment" / METHOD_KEY
    result = run_baseline(
        input_dir=input_dir,
        output_dir=output_dir,
        roles_file=Path(args.roles_file),
        top_k=args.top_k,
        background_negatives_per_day=args.background_negatives_per_day,
    )
    summary = result["evaluation"]["summary"]
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\nScholar Inbox outputs written to: {output_dir}")


if __name__ == "__main__":
    main()
