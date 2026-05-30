#!/usr/bin/env python3
"""Run a fixed-profile PaperFlow ablation on clean benchmark inputs.

This ablation reuses the PaperFlow daily-push scorer with the initial role
profiles, but freezes profile state across all days. It does not update
interest vectors, topic weights, author/institution heat, drift state, reading
history, or reading signals.
"""

from __future__ import annotations

import argparse
import contextlib
import copy
import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from experiments.benchmark import evaluate_simulation_metrics as eval_metrics
from experiments.simulation import simulate_historical_episodes as sim
from scripts import init_profiles_from_roles


METHOD_KEY = "paperflow_fixed_profile"
METHOD_NAME = "PaperFlow-Fixed Profile Ablation"
DEFAULT_TOP_K = 20
CLEAN_CANDIDATE_FILE = "candidate_pools.jsonl"
CLEAN_LABEL_FILE = "labels_for_eval.jsonl"


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
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


def paper_identity(row: Dict[str, Any]) -> str:
    explicit_identity = str(row.get("paper_identity") or "").strip()
    if explicit_identity:
        return explicit_identity
    for key in ("paper_id", "doi", "arxiv_id", "url"):
        value = str(row.get(key) or "").strip().casefold()
        if value:
            return f"{key}:{value}"
    title = " ".join(str(row.get("title") or "").strip().casefold().split())
    return f"title:{title}"


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


def build_initial_users(input_dir: Path, roles_path: Path) -> Dict[str, Dict[str, Any]]:
    roles = init_profiles_from_roles.load_roles(str(roles_path))
    metadata = load_json(input_dir / "users.json").get("users") or []
    users: Dict[str, Dict[str, Any]] = {}
    for item in metadata:
        if not isinstance(item, dict):
            continue
        user_id = str(item.get("user_id") or "").strip()
        role_name = str(item.get("role_name") or user_id.replace("user_", "")).strip()
        if not user_id:
            continue
        role = copy.deepcopy(roles.get(role_name, {}))
        if not role:
            role = {
                "user_id": user_id,
                "description": item.get("description", ""),
                "seed_directions": [
                    {"canonical_name": key, "weight": value}
                    for key, value in (item.get("seed_directions") or {}).items()
                ]
                if isinstance(item.get("seed_directions"), dict)
                else item.get("seed_directions", []),
            }
        role["user_id"] = user_id
        profile = init_profiles_from_roles.build_profile_from_role(role_name, role)
        users[user_id] = {
            "user_id": user_id,
            "role_name": role_name,
            "version": profile.get("version", "0.1"),
            "profile": profile,
        }
    return users


def prepare_fixed_profile_features(rows: Sequence[Dict[str, Any]], embedding_dim: int = 768) -> List[Dict[str, Any]]:
    prepared: List[Dict[str, Any]] = []
    for row in rows:
        paper = copy.deepcopy(row)
        paper["embedding"] = [0.0] * embedding_dim
        paper["source"] = sim._infer_simulation_paper_source(paper)
        paper["institution"] = str(paper.get("institution") or "")
        paper["quality_score"] = sim.daily_push_agent.estimate_quality_score(paper)

        existing_topics = sim._normalize_string_values(paper.get("topics"))
        title_topics = sim.daily_push_agent.extract_topics_from_title(str(paper.get("title") or ""))
        semantic_topics = sim.direction_lexicon.canonicalize_direction_terms(
            existing_topics + title_topics,
            keep_unknown=True,
        )
        source_categories = sim._normalize_string_values(paper.get("categories"))
        if paper.get("source") == "openreview":
            source_categories.append(str(paper.get("venue") or "conference"))
        elif paper.get("source") == "journal":
            source_categories.append(str(paper.get("journal") or paper.get("venue") or "journal"))

        paper["topics"] = list(dict.fromkeys(semantic_topics))
        paper["keywords"] = sim.daily_push_agent.dedupe_preserve_order(
            sim._normalize_string_values(paper.get("keywords")) + source_categories + paper["topics"]
        )
        paper["direction_terms"] = sim.daily_push_agent.expand_direction_terms(paper["topics"])
        prepared.append(paper)
    return prepared


def clone_output_row(
    row: Dict[str, Any],
    label: Dict[str, Any],
    *,
    method_name: str = METHOD_NAME,
) -> Dict[str, Any]:
    output = dict(row)
    output.pop("embedding", None)
    output.update(
        {
            "baseline_method": method_name,
            "ranking_source": "paperflow_fixed_profile_ablation",
            "selected": bool(label.get("selected")),
            "oracle_score": label.get("oracle_score", 0.0),
            "oracle_label": label.get("oracle_label", "irrelevant"),
            "system_score": row.get("relevance_score", 0.0),
            "system_label": row.get("relevance_level", "edge_relevant"),
            "select_probability": 0.0,
        }
    )
    return output


def run_ablation(
    *,
    input_dir: Path,
    output_dir: Path,
    roles_path: Path,
    top_k: int = DEFAULT_TOP_K,
) -> Dict[str, Any]:
    candidate_rows = load_jsonl(input_dir / CLEAN_CANDIDATE_FILE)
    label_rows = load_jsonl(input_dir / CLEAN_LABEL_FILE)
    episode_rows = load_jsonl(input_dir / "episodes.jsonl")
    label_map = build_label_map(label_rows)
    users = build_initial_users(input_dir, roles_path)
    grouped = group_by_episode(candidate_rows)

    output_rows: List[Dict[str, Any]] = []
    method_stats = {
        "method_key": METHOD_KEY,
        "method_name": METHOD_NAME,
        "episodes": 0,
        "top_k": top_k,
        "profile_update": "frozen",
        "interest_vector_initialization": "zero_vector_from_current_paperflow_init",
    }

    for episode_id, episode_rows_for_day in sorted(grouped.items(), key=episode_sort_key):
        if not episode_rows_for_day:
            continue
        user_id = str(episode_rows_for_day[0].get("user_id") or "").strip()
        user = users.get(user_id)
        if not user:
            continue
        embedding_dim = len((user.get("profile") or {}).get("interest_vector") or []) or 768
        prepared_rows = prepare_fixed_profile_features(episode_rows_for_day, embedding_dim=embedding_dim)
        with open(os.devnull, "w", encoding="utf-8") as sink, contextlib.redirect_stdout(sink):
            _, ranked_pool = sim.prepare_episode_candidates_with_metrics(
                prepared_rows,
                copy.deepcopy(user),
                show_count=top_k,
            )
        for row in ranked_pool:
            label = label_map.get((episode_id, paper_identity(row)), {})
            output_rows.append(clone_output_row(row, label))
        method_stats["episodes"] += 1

    output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(output_dir / "episode_papers.jsonl", output_rows)
    write_jsonl(output_dir / "episodes.jsonl", episode_rows)
    users_payload = load_json(input_dir / "users.json")
    (output_dir / "users.json").write_text(json.dumps(users_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    grouped_output = group_by_episode(output_rows)
    episode_metrics = {
        episode_id: eval_metrics.evaluate_episode(rows, [5, 10, 20])
        for episode_id, rows in grouped_output.items()
        if episode_id
    }
    summary = eval_metrics.aggregate_metrics(episode_metrics, [5, 10, 20])
    dataset_summary = eval_metrics.build_dataset_summary(output_rows, episode_rows)
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
    (output_dir / "paperflow_fixed_profile_summary.json").write_text(
        json.dumps(method_stats, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return method_stats


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run PaperFlow fixed-profile ablation.")
    parser.add_argument("--input-dir", required=True, help="Clean baseline input directory.")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory. Defaults to <input-dir>/../main_experiment/paperflow_fixed_profile.",
    )
    parser.add_argument("--roles-path", default="data/roles.json", help="Role configuration path.")
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
    result = run_ablation(
        input_dir=input_dir,
        output_dir=output_dir,
        roles_path=Path(args.roles_path),
        top_k=args.top_k,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
