#!/usr/bin/env python3
"""Run the paper-faithful NL-profile sparse retrieval baseline.

It treats the fixed natural-language profile as a query, ranks each daily
candidate pool with BM25 over title + abstract, and avoids PaperFlow-specific
direction lexicon expansion, keyphrase boosts, aspect coverage, feedback,
drift, reports, and oracle labels during ranking.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple


PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from experiments.benchmark import evaluate_simulation_metrics as eval_metrics


METHOD_KEY = "nl_profile"
METHOD_NAME = "Natural-Language User Profile Recommendation"
DEFAULT_TOP_K = 20
CLEAN_CANDIDATE_FILE = "candidate_pools.jsonl"
CLEAN_LABEL_FILE = "labels_for_eval.jsonl"
TOKEN_RE = re.compile(r"[a-z0-9]+(?:[-_][a-z0-9]+)*", flags=re.IGNORECASE)


def clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


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
            values.extend(parse_string_list(item))
        return [item for item in values if item]
    if isinstance(raw_value, dict):
        values = []
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


def seed_direction_phrases(raw_value: Any) -> List[str]:
    phrases: List[str] = []
    if isinstance(raw_value, dict):
        return [str(key).strip() for key in raw_value.keys() if str(key).strip()]
    if isinstance(raw_value, list):
        for item in raw_value:
            if isinstance(item, dict):
                phrase = item.get("bootstrap_phrase") or item.get("canonical_name") or item.get("name")
                if phrase:
                    phrases.append(str(phrase))
            else:
                phrases.extend(parse_string_list(item))
    else:
        phrases.extend(parse_string_list(raw_value))
    return dedupe_strings(phrases)


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


def label_key(row: Dict[str, Any]) -> Tuple[str, str]:
    return str(row.get("episode_id") or ""), paper_identity(row)


def build_label_map(label_rows: Sequence[Dict[str, Any]]) -> Dict[Tuple[str, str], Dict[str, Any]]:
    labels: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for row in label_rows:
        labels[label_key(row)] = {
            "selected": bool(row.get("selected")),
            "oracle_score": row.get("oracle_score", 0.0),
            "oracle_label": row.get("oracle_label", "irrelevant"),
        }
    return labels


def load_roles(roles_file: Path) -> Dict[str, Dict[str, Any]]:
    payload = load_json(roles_file)
    roles = payload.get("roles") if isinstance(payload, dict) else {}
    return roles if isinstance(roles, dict) else {}


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


def build_query_profile(user_meta: Dict[str, Any], role: Dict[str, Any]) -> Dict[str, Any]:
    """Build a fixed text query without PaperFlow lexicon expansion."""
    description = str(user_meta.get("description") or role.get("description") or "").strip()
    bootstrap_summary = str(role.get("bootstrap_summary") or "").strip()
    directions = dedupe_strings(
        seed_direction_phrases(user_meta.get("seed_directions"))
        + seed_direction_phrases(role.get("seed_directions"))
        + seed_direction_phrases(role.get("core_directions"))
    )
    parts = [
        description,
        bootstrap_summary if bootstrap_summary != description else "",
        " ".join(directions),
    ]
    query_text = " ".join(part for part in parts if part).strip()
    return {
        "query_text": query_text,
        "directions": directions,
        "description": description,
    }


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
        meta = user_metadata.get(user_id, {})
        role_name = str(meta.get("role_name") or user_id.replace("user_", "")).strip()
        profiles[user_id] = build_query_profile(meta, roles.get(role_name, {}))
    return profiles


def group_by_episode(rows: Sequence[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        episode_id = str(row.get("episode_id") or "").strip()
        if episode_id:
            grouped[episode_id].append(row)
    return grouped


def episode_sort_key(item: Tuple[str, List[Dict[str, Any]]]) -> Tuple[str, str, str]:
    episode_id, rows = item
    first = rows[0] if rows else {}
    return (
        str(first.get("user_id") or episode_id.split("::", 1)[0]),
        str(first.get("date") or ""),
        episode_id,
    )


def build_bm25_state(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    docs = [tokenize(paper_text(row)) for row in rows]
    doc_freq: Counter[str] = Counter()
    for tokens in docs:
        doc_freq.update(set(tokens))
    doc_count = len(docs)
    avg_len = sum(len(tokens) for tokens in docs) / max(1, doc_count)
    idf = {
        token: math.log(1.0 + (doc_count - freq + 0.5) / (freq + 0.5))
        for token, freq in doc_freq.items()
    }
    return {"docs": docs, "idf": idf, "avg_len": avg_len}


def bm25_score(
    query_tokens: Sequence[str],
    doc_tokens: Sequence[str],
    idf: Dict[str, float],
    avg_len: float,
    *,
    k1: float = 1.2,
    b: float = 0.75,
) -> float:
    if not query_tokens or not doc_tokens:
        return 0.0
    counts = Counter(doc_tokens)
    doc_len = len(doc_tokens)
    denominator_base = k1 * (1.0 - b + b * doc_len / max(avg_len, 1e-9))
    score = 0.0
    for token in Counter(query_tokens):
        tf = counts.get(token, 0)
        if tf <= 0:
            continue
        score += idf.get(token, 0.0) * ((tf * (k1 + 1.0)) / (tf + denominator_base))
    return score


def label_for_score(score: float) -> str:
    if score >= 0.70:
        return "high_relevant"
    if score >= 0.45:
        return "maybe_interested"
    return "edge_relevant"


def clone_output_row(
    row: Dict[str, Any],
    label: Dict[str, Any],
    *,
    score: float,
    raw_score: float,
    rank: int,
    shown: bool,
    top_k: int,
    query_length: int,
) -> Dict[str, Any]:
    output = dict(row)
    output.update(
        {
            "baseline_method": METHOD_NAME,
            "ranking_source": "baselines.nl_profile.runner",
            "shown": bool(shown),
            "system_rank": rank if shown else None,
            "pool_rank": rank,
            "show_target_count": top_k,
            "system_score": round(score, 6),
            "system_label": label_for_score(score),
            "bm25_raw_score": round(raw_score, 6),
            "query_token_count": query_length,
            "uses_paperflow_direction_expansion": False,
            "uses_feedback_update": False,
            "selected": bool(label.get("selected")),
            "oracle_score": label.get("oracle_score", 0.0),
            "oracle_label": label.get("oracle_label", "irrelevant"),
            "select_probability": 0.0,
        }
    )
    return output


def load_clean_benchmark_inputs(input_dir: Path) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    candidate_path = input_dir / CLEAN_CANDIDATE_FILE
    label_path = input_dir / CLEAN_LABEL_FILE
    if not candidate_path.exists() or not label_path.exists():
        if (input_dir / "episode_papers.jsonl").exists():
            raise FileNotFoundError(
                "Natural-Language User Profile baseline refuses to read Full PaperFlow episode_papers.jsonl directly. "
                "Export clean input first with: "
                "python scripts\\export_clean_baseline_benchmark.py --input-dir <benchmark_output>."
            )
        raise FileNotFoundError(f"Missing clean files: {candidate_path} and/or {label_path}")
    return load_jsonl(candidate_path), load_jsonl(label_path)


def rerank_episodes(
    rows: Sequence[Dict[str, Any]],
    label_rows: Sequence[Dict[str, Any]],
    *,
    input_dir: Path,
    roles_file: Path,
    top_k: int,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    roles = load_roles(roles_file)
    user_metadata = load_user_metadata(input_dir)
    profile_map = build_profile_map(user_metadata, roles, rows)
    label_map = build_label_map(label_rows)
    grouped = group_by_episode(rows)
    output_rows: List[Dict[str, Any]] = []

    method_stats = {
        "method_key": METHOD_KEY,
        "method_name": METHOD_NAME,
        "episodes": 0,
        "top_k": top_k,
        "ranking_model": "BM25",
        "profile_update": "frozen",
        "uses_paperflow_direction_expansion": False,
        "uses_dynamic_feedback": False,
        "uses_oracle_during_ranking": False,
    }

    for episode_id, episode_rows in sorted(grouped.items(), key=episode_sort_key):
        if not episode_rows:
            continue
        user_id = str(episode_rows[0].get("user_id") or "").strip()
        profile = profile_map.get(user_id, {"query_text": "", "directions": []})
        query_tokens = tokenize(profile.get("query_text", ""))
        bm25_state = build_bm25_state(episode_rows)

        scored: List[Tuple[float, str, Dict[str, Any]]] = []
        for index, row in enumerate(episode_rows):
            raw_score = bm25_score(
                query_tokens,
                bm25_state["docs"][index],
                bm25_state["idf"],
                bm25_state["avg_len"],
            )
            scored.append((raw_score, paper_identity(row), row))

        max_score = max((score for score, _, _ in scored), default=0.0)
        scored.sort(key=lambda item: (-item[0], item[1]))
        for rank, (raw_score, _, row) in enumerate(scored, start=1):
            score = clamp(raw_score / max_score) if max_score > 0 else 0.0
            label = label_map.get((episode_id, paper_identity(row)), {})
            output_rows.append(
                clone_output_row(
                    row,
                    label,
                    score=score,
                    raw_score=raw_score,
                    rank=rank,
                    shown=rank <= top_k,
                    top_k=top_k,
                    query_length=len(query_tokens),
                )
            )
        method_stats["episodes"] += 1

    method_stats["profiles"] = {
        user_id: {
            "query_text": profile.get("query_text", ""),
            "direction_count": len(profile.get("directions", [])),
        }
        for user_id, profile in profile_map.items()
    }
    return output_rows, method_stats


def write_evaluation(
    output_dir: Path,
    reranked_rows: Sequence[Dict[str, Any]],
    episode_rows: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    grouped_output = group_by_episode(reranked_rows)
    episode_metrics = {
        episode_id: eval_metrics.evaluate_episode(rows, [5, 10, 20])
        for episode_id, rows in grouped_output.items()
        if episode_id
    }
    summary = eval_metrics.aggregate_metrics(episode_metrics, [5, 10, 20])
    dataset_summary = eval_metrics.build_dataset_summary(reranked_rows, episode_rows)
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


def run_baseline(input_dir: Path, output_dir: Path, roles_file: Path, top_k: int = DEFAULT_TOP_K) -> Dict[str, Any]:
    rows, label_rows = load_clean_benchmark_inputs(input_dir)
    episode_rows = load_jsonl(input_dir / "episodes.jsonl")
    output_dir.mkdir(parents=True, exist_ok=True)
    reranked_rows, method_stats = rerank_episodes(
        rows,
        label_rows,
        input_dir=input_dir,
        roles_file=roles_file,
        top_k=top_k,
    )
    write_jsonl(output_dir / "episode_papers.jsonl", reranked_rows)
    write_jsonl(output_dir / "episodes.jsonl", episode_rows)
    for file_name in ("users.json", "manifest.json"):
        source = input_dir / file_name
        if source.exists():
            shutil.copyfile(source, output_dir / file_name)
    evaluation = write_evaluation(output_dir, reranked_rows, episode_rows)
    method_stats["input_rows"] = len(rows)
    method_stats["output_rows"] = len(reranked_rows)
    method_stats["using_clean_input"] = True
    (output_dir / "nl_profile_summary.json").write_text(
        json.dumps(method_stats, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {"method_stats": method_stats, "evaluation": evaluation}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run strict SciNUP-style BM25 NL-profile baseline.")
    parser.add_argument("--input-dir", required=True, help="Clean baseline input directory.")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory. Defaults to <input-dir>/../main_experiment/scinup_strict_bm25.",
    )
    parser.add_argument("--roles-file", default="data/roles.json", help="Initial role/profile metadata.")
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K, help="Displayed papers per episode.")
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
    print(json.dumps(result["method_stats"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
