#!/usr/bin/env python3
"""
Natural-Language User Profile Recommendation baseline runner.

This runner reranks clean frozen PaperFlow candidate pools using a fixed
natural-language user profile. It does not use chronological feedback,
interest drift, must-read priority, reading reports, or oracle labels.
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
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple


PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from config import direction_lexicon
except Exception:  # pragma: no cover - keeps exported artifacts runnable.
    direction_lexicon = None

from experiments.benchmark import evaluate_simulation_metrics as eval_metrics


METHOD_KEY = "nl_profile"
METHOD_NAME = "Natural-Language User Profile Recommendation"
DEFAULT_TOP_K = 20
CLEAN_CANDIDATE_FILE = "candidate_pools.jsonl"
CLEAN_LABEL_FILE = "labels_for_eval.jsonl"

SCORE_WEIGHTS = {
    "profile_similarity": 0.65,
    "keyphrase_alignment": 0.20,
    "title_alignment": 0.10,
    "aspect_coverage": 0.05,
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


def cosine(left: Dict[str, float], right: Dict[str, float]) -> float:
    if not left or not right:
        return 0.0
    if len(left) > len(right):
        left, right = right, left
    return sum(value * right.get(key, 0.0) for key, value in left.items())


def scaled_similarity(left: Dict[str, float], right: Dict[str, float]) -> float:
    return clamp(cosine(left, right) * 4.0)


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


def build_natural_language_profile(user_meta: Dict[str, Any], role: Dict[str, Any]) -> Dict[str, Any]:
    directions: Dict[str, float] = {}
    for key, weight in _seed_direction_entries(user_meta.get("seed_directions")):
        directions[key] = max(directions.get(key, 0.0), weight)
    for key, weight in _seed_direction_entries(role.get("seed_directions")):
        directions[key] = max(directions.get(key, 0.0), weight)
    for key, weight in _seed_direction_entries(role.get("core_directions")):
        directions[key] = max(directions.get(key, 0.0), weight)

    core_directions = [
        direction for direction, _ in sorted(directions.items(), key=lambda item: (-item[1], item[0]))
    ]
    expanded_terms: List[str] = []
    for direction in core_directions:
        expanded_terms.extend(_direction_terms(direction))
    expanded_terms.extend(parse_string_list(user_meta.get("initial_topics")))
    expanded_terms.extend(parse_string_list(role.get("secondary_topics")))
    expanded_terms.extend(parse_string_list(role.get("positive_keywords")))
    expanded_terms.extend(parse_string_list(role.get("must_read_keywords")))
    expanded_terms = dedupe_strings(expanded_terms)

    description = str(user_meta.get("description") or role.get("description") or "").strip()
    bootstrap_summary = str(role.get("bootstrap_summary") or "").strip()
    direction_text = ", ".join(core_directions) if core_directions else "the user's stated research interests"
    term_text = ", ".join(expanded_terms[:24])
    profile_parts = [
        f"The researcher is interested in {direction_text}.",
        f"Research context: {description}." if description else "",
        f"Profile summary: {bootstrap_summary}." if bootstrap_summary and bootstrap_summary != description else "",
        f"Relevant concepts include {term_text}." if term_text else "",
        "Recommend papers whose title and abstract match these stated research interests.",
    ]
    profile_text = " ".join(part for part in profile_parts if part)
    return {
        "profile_text": profile_text,
        "directions": core_directions,
        "terms": expanded_terms,
        "description": description,
    }


@dataclass
class UserNaturalProfileState:
    profile_text: str
    directions: List[str]
    terms: List[str]
    profile_vector: Dict[str, float]


def make_state(profile: Dict[str, Any], idf: Dict[str, float]) -> UserNaturalProfileState:
    return UserNaturalProfileState(
        profile_text=str(profile.get("profile_text") or ""),
        directions=list(profile.get("directions") or []),
        terms=list(profile.get("terms") or []),
        profile_vector=vectorize_text(profile.get("profile_text"), idf),
    )


def phrase_alignment_score(text: str, phrases: Sequence[str]) -> float:
    normalized_text = normalize_phrase_text(text)
    if not normalized_text or not phrases:
        return 0.0
    weighted_hits = 0.0
    total_weight = 0.0
    for phrase in phrases:
        normalized_phrase = normalize_phrase_text(phrase)
        if not normalized_phrase:
            continue
        weight = 1.0 + min(2.0, max(0, len(normalized_phrase.split()) - 1) * 0.35)
        total_weight += weight
        if contains_phrase(normalized_text, normalized_phrase):
            weighted_hits += weight
    if total_weight <= 0:
        return 0.0
    return clamp(weighted_hits / min(total_weight, 8.0))


def aspect_coverage_score(text: str, directions: Sequence[str]) -> float:
    if not directions:
        return 0.0
    normalized_text = normalize_phrase_text(text)
    covered = 0
    for direction in directions:
        direction_terms = _direction_terms(direction)
        if any(contains_phrase(normalized_text, term) for term in direction_terms):
            covered += 1
    return clamp(covered / min(len(directions), 3))


def label_for_score(score: float) -> str:
    if score >= LABEL_THRESHOLDS["high_relevant"]:
        return "high_relevant"
    if score >= LABEL_THRESHOLDS["maybe_interested"]:
        return "maybe_interested"
    return "edge_relevant"


def score_row(row: Dict[str, Any], idf: Dict[str, float], state: UserNaturalProfileState) -> Dict[str, Any]:
    row_text = paper_text(row)
    title = str(row.get("title") or "")
    row_vector = vectorize_text(row_text, idf)
    profile_similarity = scaled_similarity(row_vector, state.profile_vector)
    keyphrase_alignment = phrase_alignment_score(row_text, state.terms)
    title_alignment = phrase_alignment_score(title, state.terms)
    aspect_coverage = aspect_coverage_score(row_text, state.directions)
    final_score = clamp(
        SCORE_WEIGHTS["profile_similarity"] * profile_similarity
        + SCORE_WEIGHTS["keyphrase_alignment"] * keyphrase_alignment
        + SCORE_WEIGHTS["title_alignment"] * title_alignment
        + SCORE_WEIGHTS["aspect_coverage"] * aspect_coverage
    )
    return {
        "system_score": final_score,
        "system_label": label_for_score(final_score),
        "profile_similarity_score": profile_similarity,
        "keyphrase_alignment_score": keyphrase_alignment,
        "title_alignment_score": title_alignment,
        "aspect_coverage_score": aspect_coverage,
        "profile_term_count": len(state.terms),
        "profile_direction_count": len(state.directions),
        "uses_feedback_update": False,
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


def build_profile_map(
    user_metadata: Dict[str, Dict[str, Any]],
    roles: Dict[str, Dict[str, Any]],
    episode_rows: Sequence[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    user_ids = sorted(
        {
            str(row.get("user_id") or "").strip()
            for row in episode_rows
            if str(row.get("user_id") or "").strip()
        }
        | set(user_metadata.keys())
    )
    profiles: Dict[str, Dict[str, Any]] = {}
    for user_id in user_ids:
        meta = user_metadata.get(user_id, {"user_id": user_id})
        role_name = str(meta.get("role_name") or user_id.replace("user_", "")).strip()
        profiles[user_id] = build_natural_language_profile(meta, roles.get(role_name, {}))
    return profiles


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
            "ranking_source": "baselines.nl_profile.runner",
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
        "Natural-Language User Profile baseline refuses to read Full PaperFlow episode_papers.jsonl directly. "
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
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    roles = load_roles(roles_file)
    user_metadata = load_user_metadata(input_dir)
    profile_map = build_profile_map(user_metadata, roles, rows)
    label_map = build_label_map(label_rows)

    output_rows: List[Dict[str, Any]] = []
    grouped = group_by_episode(rows)
    method_stats = {
        "method_key": METHOD_KEY,
        "method_name": METHOD_NAME,
        "episodes": 0,
        "top_k": top_k,
        "uses_dynamic_feedback": False,
        "uses_reading_reports": False,
        "users": {},
    }

    for episode_id, episode_rows in sorted(grouped.items(), key=episode_sort_key):
        if not episode_rows:
            continue
        user_id = str(episode_rows[0].get("user_id") or "").strip()
        profile = profile_map.get(user_id, {"profile_text": "", "directions": [], "terms": []})

        day_texts = [paper_text(row) for row in episode_rows]
        idf = build_idf_from_texts([profile.get("profile_text", ""), *profile.get("terms", []), *day_texts])
        state = make_state(profile, idf)

        scored_rows: List[Tuple[float, str, Dict[str, Any], Dict[str, Any]]] = []
        for row in episode_rows:
            identity = paper_identity(row)
            score_payload = score_row(row, idf, state)
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

        method_stats["episodes"] += 1

    for user_id, profile in profile_map.items():
        method_stats["users"][user_id] = {
            "profile_direction_count": len(profile.get("directions", [])),
            "profile_term_count": len(profile.get("terms", [])),
            "profile_text": profile.get("profile_text", ""),
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
    (output_dir / "nl_profile_summary.json").write_text(
        json.dumps(method_stats, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {"method_stats": method_stats, "evaluation": evaluation}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Natural-Language User Profile main-experiment baseline.")
    parser.add_argument("--input-dir", required=True, help="Clean baseline input directory.")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory. Defaults to <input-dir>/../main_experiment/nl_profile.",
    )
    parser.add_argument(
        "--roles-file",
        default=str(PROJECT_ROOT / "data" / "roles.json"),
        help="Initial role/profile metadata used for fixed NL profile construction.",
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
    print(f"\nNatural-Language User Profile outputs written to: {output_dir}")


if __name__ == "__main__":
    main()
