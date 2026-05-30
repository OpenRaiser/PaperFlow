#!/usr/bin/env python3
"""Run fixed-profile PaperFlow ablation with progress and resume support.

This is a safer replacement for `run_paperflow_fixed_profile_ablation.py`.
It streams `episode_papers.jsonl` as each episode completes, writes a progress
file, and computes metrics at the end. The scoring logic is intentionally kept
the same as the original fixed-profile ablation.
"""

from __future__ import annotations

import argparse
import contextlib
import copy
import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from experiments.ablation import run_paperflow_fixed_profile_ablation as base
from experiments.benchmark import evaluate_simulation_metrics as eval_metrics
from experiments.simulation import simulate_historical_episodes as sim


METHOD_KEY = base.METHOD_KEY
METHOD_NAME = base.METHOD_NAME
DEFAULT_TOP_K = base.DEFAULT_TOP_K
PROGRESS_FILE = "progress.json"


def iter_jsonl(path: Path) -> Iterator[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            payload = json.loads(line)
            if isinstance(payload, dict):
                yield payload


def count_jsonl(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


def iter_episode_groups(path: Path) -> Iterator[Tuple[str, List[Dict[str, Any]]]]:
    current_episode_id: Optional[str] = None
    current_rows: List[Dict[str, Any]] = []
    for row in iter_jsonl(path):
        episode_id = str(row.get("episode_id") or "").strip()
        if not episode_id:
            continue
        if current_episode_id is None:
            current_episode_id = episode_id
        if episode_id != current_episode_id:
            yield current_episode_id, current_rows
            current_episode_id = episode_id
            current_rows = []
        current_rows.append(row)
    if current_episode_id is not None and current_rows:
        yield current_episode_id, current_rows


def load_progress(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"completed_episode_ids": []}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {"completed_episode_ids": []}


def save_progress(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def reset_output_dir(output_dir: Path) -> None:
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)


def feature_cache_key(row: Dict[str, Any]) -> str:
    return base.paper_identity(row)


def prepare_fixed_profile_features_cached(
    rows: Sequence[Dict[str, Any]],
    *,
    embedding_dim: int,
    feature_cache: Dict[str, Dict[str, Any]],
    zero_embedding: List[float],
) -> List[Dict[str, Any]]:
    prepared: List[Dict[str, Any]] = []
    for row in rows:
        paper = dict(row)
        key = feature_cache_key(row)
        cached = feature_cache.get(key)
        if cached is None:
            source = sim._infer_simulation_paper_source(paper)
            institution = str(paper.get("institution") or "")
            quality_score = sim.daily_push_agent.estimate_quality_score(paper)
            existing_topics = sim._normalize_string_values(paper.get("topics"))
            title_topics = sim.daily_push_agent.extract_topics_from_title(str(paper.get("title") or ""))
            semantic_topics = sim.direction_lexicon.canonicalize_direction_terms(
                existing_topics + title_topics,
                keep_unknown=True,
            )
            source_categories = sim._normalize_string_values(paper.get("categories"))
            if source == "openreview":
                source_categories.append(str(paper.get("venue") or "conference"))
            elif source == "journal":
                source_categories.append(str(paper.get("journal") or paper.get("venue") or "journal"))

            topics = list(dict.fromkeys(semantic_topics))
            keywords = sim.daily_push_agent.dedupe_preserve_order(
                sim._normalize_string_values(paper.get("keywords")) + source_categories + topics
            )
            cached = {
                "source": source,
                "institution": institution,
                "quality_score": quality_score,
                "topics": topics,
                "keywords": keywords,
                "direction_terms": sim.daily_push_agent.expand_direction_terms(topics),
            }
            feature_cache[key] = cached

        paper.update(cached)
        paper["embedding"] = zero_embedding
        prepared.append(paper)
    return prepared


def write_rows(handle: Any, rows: Iterable[Dict[str, Any]]) -> int:
    count = 0
    for row in rows:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        count += 1
    handle.flush()
    return count


def finalize_outputs(
    *,
    input_dir: Path,
    output_dir: Path,
    method_stats: Dict[str, Any],
) -> None:
    episode_rows = base.load_jsonl(input_dir / "episodes.jsonl")
    output_rows = base.load_jsonl(output_dir / "episode_papers.jsonl")
    grouped_output = base.group_by_episode(output_rows)
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
    (output_dir / "users.json").write_text(
        json.dumps(base.load_json(input_dir / "users.json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    method_stats["completed"] = True
    method_stats["output_rows"] = len(output_rows)
    (output_dir / "paperflow_fixed_profile_summary.json").write_text(
        json.dumps(method_stats, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def run_ablation(
    *,
    input_dir: Path,
    output_dir: Path,
    roles_path: Path,
    top_k: int = DEFAULT_TOP_K,
    reset: bool = False,
    progress_every: int = 10,
) -> Dict[str, Any]:
    candidate_file = input_dir / base.CLEAN_CANDIDATE_FILE
    label_file = input_dir / base.CLEAN_LABEL_FILE
    episode_file = input_dir / "episodes.jsonl"
    total_episodes = count_jsonl(episode_file)

    if reset:
        reset_output_dir(output_dir)
    else:
        output_dir.mkdir(parents=True, exist_ok=True)

    progress_path = output_dir / PROGRESS_FILE
    progress = load_progress(progress_path)
    completed_ids = set(str(item) for item in progress.get("completed_episode_ids", []) or [])
    initial_completed_count = len(completed_ids)

    label_map = base.build_label_map(base.load_jsonl(label_file))
    users = base.build_initial_users(input_dir, roles_path)
    feature_cache: Dict[str, Dict[str, Any]] = {}
    zero_embeddings_by_dim: Dict[int, List[float]] = {}

    method_stats = {
        "method_key": METHOD_KEY,
        "method_name": METHOD_NAME,
        "episodes": len(completed_ids),
        "top_k": top_k,
        "profile_update": "frozen",
        "interest_vector_initialization": "zero_vector_from_current_paperflow_init",
        "resumable": True,
        "completed": False,
    }

    output_file = output_dir / "episode_papers.jsonl"
    mode = "a" if output_file.exists() and not reset else "w"
    start_time = time.time()
    rows_written = 0

    print(
        f"Running {METHOD_NAME}: {len(completed_ids)}/{total_episodes} episodes already complete.",
        flush=True,
    )
    with output_file.open(mode, encoding="utf-8") as output_handle:
        for episode_index, (episode_id, episode_rows_for_day) in enumerate(iter_episode_groups(candidate_file), start=1):
            if episode_id in completed_ids:
                continue
            if not episode_rows_for_day:
                continue

            user_id = str(episode_rows_for_day[0].get("user_id") or "").strip()
            user = users.get(user_id)
            if not user:
                continue

            embedding_dim = len((user.get("profile") or {}).get("interest_vector") or []) or 768
            zero_embedding = zero_embeddings_by_dim.setdefault(embedding_dim, [0.0] * embedding_dim)
            prepared_rows = prepare_fixed_profile_features_cached(
                episode_rows_for_day,
                embedding_dim=embedding_dim,
                feature_cache=feature_cache,
                zero_embedding=zero_embedding,
            )
            with open(os.devnull, "w", encoding="utf-8") as sink, contextlib.redirect_stdout(sink):
                _, ranked_pool = sim.prepare_episode_candidates_with_metrics(
                    prepared_rows,
                    copy.deepcopy(user),
                    show_count=top_k,
                )

            output_rows = []
            for row in ranked_pool:
                label = label_map.get((episode_id, base.paper_identity(row)), {})
                output_rows.append(base.clone_output_row(row, label))
            rows_written += write_rows(output_handle, output_rows)

            completed_ids.add(episode_id)
            method_stats["episodes"] = len(completed_ids)
            elapsed = max(0.001, time.time() - start_time)
            progress_payload = {
                **method_stats,
                "completed_episode_ids": sorted(completed_ids),
                "rows_written_this_run": rows_written,
                "feature_cache_size": len(feature_cache),
                "elapsed_seconds_this_run": round(elapsed, 2),
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            save_progress(progress_path, progress_payload)

            if len(completed_ids) % max(1, progress_every) == 0 or len(completed_ids) == total_episodes:
                remaining = max(0, total_episodes - len(completed_ids))
                episodes_completed_this_run = max(1, len(completed_ids) - initial_completed_count)
                seconds_per_episode = elapsed / episodes_completed_this_run
                eta_hours = remaining * seconds_per_episode / 3600.0
                print(
                    f"[{len(completed_ids)}/{total_episodes}] "
                    f"episode={episode_id} rows_written={rows_written} "
                    f"cache={len(feature_cache)} eta={eta_hours:.2f}h",
                    flush=True,
                )

    finalize_outputs(input_dir=input_dir, output_dir=output_dir, method_stats=method_stats)
    save_progress(progress_path, {**method_stats, "completed_episode_ids": sorted(completed_ids), "completed": True})
    print(json.dumps(method_stats, ensure_ascii=False, indent=2), flush=True)
    return method_stats


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run resumable PaperFlow fixed-profile ablation.")
    parser.add_argument("--input-dir", required=True, help="Clean baseline input directory.")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory. Defaults to <input-dir>/../main_experiment/paperflow_fixed_profile.",
    )
    parser.add_argument("--roles-path", default="data/roles.json", help="Role configuration path.")
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K, help="Displayed papers per episode.")
    parser.add_argument("--reset", action="store_true", help="Delete existing output dir before running.")
    parser.add_argument("--progress-every", type=int, default=10, help="Print progress every N completed episodes.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_dir = Path(args.input_dir)
    output_dir = (
        Path(args.output_dir)
        if args.output_dir
        else input_dir.parent / "main_experiment" / METHOD_KEY
    )
    run_ablation(
        input_dir=input_dir,
        output_dir=output_dir,
        roles_path=Path(args.roles_path),
        top_k=args.top_k,
        reset=bool(args.reset),
        progress_every=int(args.progress_every),
    )


if __name__ == "__main__":
    main()
