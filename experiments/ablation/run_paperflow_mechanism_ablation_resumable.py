#!/usr/bin/env python3
"""Run mechanism ablations for PaperFlow with progress and resume support.

Supported ablations:
- no_drift: disable drift-state ranking signals.
- no_reading_signal: disable short-term reading-signal ranking bonus.
- no_explicit_preference: disable explicit preference matching, including
  must-read priority plus canonical direction lexicon matching and topic
  expansion.

The runner uses the clean candidate pools and labels, plus dynamic profile
snapshots from the full PaperFlow run. For each episode, it uses the most recent
profile snapshot before that episode date, then removes the mechanism being
ablated before reranking the same candidate pool.
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
from bisect import bisect_left
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from experiments.ablation import run_paperflow_fixed_profile_ablation as fixed_base
from experiments.benchmark import evaluate_simulation_metrics as eval_metrics
from experiments.simulation import simulate_historical_episodes as sim


DEFAULT_TOP_K = 20
PROGRESS_FILE = "progress.json"
CLEAN_CANDIDATE_FILE = "candidate_pools.jsonl"
CLEAN_LABEL_FILE = "labels_for_eval.jsonl"

METHODS = {
    "no_drift": {
        "key": "paperflow_no_drift",
        "name": "PaperFlow No Drift Ablation",
        "description": "dynamic profile with drift-state ranking signals disabled",
    },
    "no_reading_signal": {
        "key": "paperflow_no_reading_signal",
        "name": "PaperFlow No Reading Signal Ablation",
        "description": "dynamic profile with short-term reading signal disabled",
    },
    "no_explicit_preference": {
        "key": "paperflow_no_explicit_preference",
        "name": "PaperFlow No Explicit Preference Matching Ablation",
        "description": (
            "dynamic profile with must-read priority plus direction lexicon "
            "canonicalization and topic expansion disabled"
        ),
    },
}


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


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def resolve_project_path(path_like: str) -> Path:
    path = Path(path_like)
    return path if path.is_absolute() else PROJECT_ROOT / path


def write_text_ensuring_parent(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    target = str(path.resolve())
    if os.name == "nt" and not target.startswith("\\\\?\\"):
        target = "\\\\?\\" + target
    with open(target, "w", encoding="utf-8") as handle:
        handle.write(text)


def load_progress(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"completed_episode_ids": []}
    payload = load_json(path)
    return payload if payload else {"completed_episode_ids": []}


def save_progress(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def reset_output_dir(output_dir: Path) -> None:
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)


def build_initial_users(input_dir: Path, roles_path: Path) -> Dict[str, Dict[str, Any]]:
    return fixed_base.build_initial_users(input_dir, roles_path)


def load_profile_timeline(
    profile_state_path: Path,
    initial_users: Dict[str, Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    timelines: Dict[str, List[Tuple[str, Dict[str, Any]]]] = {}
    for user_id, user in initial_users.items():
        timelines.setdefault(user_id, []).append(("0000-00-00", copy.deepcopy(user.get("profile") or {})))

    for row in iter_jsonl(profile_state_path):
        user_id = str(row.get("user_id") or "").strip()
        date = str(row.get("date") or "").strip()
        profile = row.get("profile_json") or {}
        if user_id and date and isinstance(profile, dict):
            timelines.setdefault(user_id, []).append((date, profile))

    prepared: Dict[str, Dict[str, Any]] = {}
    for user_id, rows in timelines.items():
        rows.sort(key=lambda item: item[0])
        prepared[user_id] = {
            "dates": [date for date, _profile in rows],
            "profiles": [profile for _date, profile in rows],
        }
    return prepared


def profile_before_episode(
    profile_timeline: Dict[str, Dict[str, Any]],
    user_id: str,
    episode_date: str,
    initial_users: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    timeline = profile_timeline.get(user_id) or {}
    dates = timeline.get("dates") or []
    profiles = timeline.get("profiles") or []
    index = bisect_left(dates, episode_date) - 1
    if index >= 0 and index < len(profiles):
        return copy.deepcopy(profiles[index])
    return copy.deepcopy((initial_users.get(user_id) or {}).get("profile") or {})


def apply_profile_ablation(profile: Dict[str, Any], ablation: str) -> Dict[str, Any]:
    result = copy.deepcopy(profile)

    if ablation == "no_drift":
        result["drift_state"] = {
            "status": "stable",
            "score": 0.0,
            "drift_enabled": False,
            "short_term_topics": {},
            "top_shift_topics": [],
            "anchor_topics": [],
            "hidden_anchor": None,
            "anchor_topic": None,
        }
        result["anchor_behavior"] = {
            "target_topic": None,
            "suppressed_topics": [],
            "decayed_topics": {},
            "score_bonus": 0.0,
            "category_bonus": 0.0,
            "suppression_penalty": 0.0,
        }
        return result

    if ablation == "no_reading_signal":
        result["reading_signal_state"] = {"short_term_topics": {}}
        result["reading_history"] = []
        return result

    if ablation == "no_explicit_preference":
        result["must_read"] = {"authors": [], "institutions": [], "keywords": []}
        return result

    raise ValueError(f"Unsupported ablation: {ablation}")


def apply_weight_ablation(weights: Dict[str, Any], ablation: str) -> Dict[str, Any]:
    result = copy.deepcopy(weights)
    if ablation == "no_drift":
        result["drift_bonus_shifting"] = 0.0
        result["drift_bonus_recovered"] = 0.0
        result["drift_short_topic_bonus"] = 0.0
    elif ablation == "no_reading_signal":
        result["reading_signal_short_term_bonus"] = 0.0
    elif ablation == "no_explicit_preference":
        result["bonus_must_read"] = 0.0
    return result


def feature_cache_key(row: Dict[str, Any]) -> str:
    return fixed_base.paper_identity(row)


def build_source_categories(paper: Dict[str, Any], source: str) -> List[str]:
    source_categories = sim._normalize_string_values(paper.get("categories"))
    if source == "openreview":
        source_categories.append(str(paper.get("venue") or "conference"))
    elif source == "journal":
        source_categories.append(str(paper.get("journal") or paper.get("venue") or "journal"))
    return source_categories


def prepare_features_cached(
    rows: Sequence[Dict[str, Any]],
    *,
    ablation: str,
    embedding_dim: int,
    feature_cache: Dict[str, Dict[str, Any]],
    zero_embedding: List[float],
) -> List[Dict[str, Any]]:
    prepared: List[Dict[str, Any]] = []
    for row in rows:
        paper = dict(row)
        key = f"{ablation}:{feature_cache_key(row)}"
        cached = feature_cache.get(key)
        if cached is None:
            source = sim._infer_simulation_paper_source(paper)
            source_categories = build_source_categories(paper, source)
            if ablation == "no_explicit_preference":
                keywords = sim.daily_push_agent.dedupe_preserve_order(
                    sim._normalize_string_values(paper.get("keywords")) + source_categories
                )
                cached = {
                    "source": source,
                    "institution": str(paper.get("institution") or ""),
                    "quality_score": sim.daily_push_agent.estimate_quality_score(paper),
                    "topics": [],
                    "keywords": keywords,
                    "direction_terms": {},
                }
            else:
                existing_topics = sim._normalize_string_values(paper.get("topics"))
                title_topics = sim.daily_push_agent.extract_topics_from_title(str(paper.get("title") or ""))
                topics = list(
                    dict.fromkeys(
                        sim.direction_lexicon.canonicalize_direction_terms(
                            existing_topics + title_topics,
                            keep_unknown=True,
                        )
                    )
                )
                keywords = sim.daily_push_agent.dedupe_preserve_order(
                    sim._normalize_string_values(paper.get("keywords")) + source_categories + topics
                )
                cached = {
                    "source": source,
                    "institution": str(paper.get("institution") or ""),
                    "quality_score": sim.daily_push_agent.estimate_quality_score(paper),
                    "topics": topics,
                    "keywords": keywords,
                    "direction_terms": sim.daily_push_agent.expand_direction_terms(topics),
                }
            feature_cache[key] = cached
        paper.update(cached)
        paper["embedding"] = zero_embedding
        prepared.append(paper)
    return prepared


def paper_with_score_to_candidate(item: Any, *, ranking_fallback: bool = False) -> Dict[str, Any]:
    return sim._paper_with_real_score_to_candidate(item, ranking_fallback=ranking_fallback)


def rerank_candidates(
    papers: List[Dict[str, Any]],
    profile: Dict[str, Any],
    *,
    top_k: int,
    ablation: str,
) -> List[Dict[str, Any]]:
    ranking_profile = sim._ranking_profile(profile)
    weights = apply_weight_ablation(sim._load_real_daily_push_weights(), ablation)
    target_show_count = max(1, int(top_k or DEFAULT_TOP_K))
    weights["push_target_count"] = target_show_count
    weights["push_max_count"] = target_show_count

    if ablation == "no_explicit_preference":
        ranking_papers = [copy.deepcopy(paper) for paper in papers]
    else:
        ranking_papers = sim._build_user_ranking_papers(papers, ranking_profile)
    pool_scored_items = sim._score_daily_push_candidate_pool(ranking_papers, ranking_profile, weights)
    real_shown_scored_items = sim.daily_push_agent.sort_and_categorize(ranking_papers, ranking_profile, weights)
    shown_scored_items = list(real_shown_scored_items[:target_show_count])
    shown_keys = {sim._paper_identity(item.paper) for item in shown_scored_items}
    if len(shown_scored_items) < target_show_count:
        for item in pool_scored_items:
            paper_key = sim._paper_identity(item.paper)
            if paper_key in shown_keys:
                continue
            shown_scored_items.append(item)
            shown_keys.add(paper_key)
            if len(shown_scored_items) >= target_show_count:
                break

    shown_positions = {sim._paper_identity(item.paper): idx for idx, item in enumerate(shown_scored_items, start=1)}
    shown_items_by_key = {sim._paper_identity(item.paper): item for item in shown_scored_items}
    real_shown_keys = {sim._paper_identity(item.paper) for item in real_shown_scored_items}

    all_candidates: List[Dict[str, Any]] = []
    for pool_rank, item in enumerate(pool_scored_items, start=1):
        paper_key = sim._paper_identity(item.paper)
        source_item = shown_items_by_key.get(paper_key, item)
        candidate = paper_with_score_to_candidate(
            source_item,
            ranking_fallback=paper_key in shown_positions and paper_key not in real_shown_keys,
        )
        candidate["pool_rank"] = pool_rank
        candidate["shown"] = paper_key in shown_positions
        candidate["system_rank"] = shown_positions.get(paper_key)
        candidate["show_target_count"] = target_show_count
        candidate["ranking_source"] = f"paperflow_{ablation}_ablation"
        all_candidates.append(candidate)
    return all_candidates


def write_rows(handle: Any, rows: Iterable[Dict[str, Any]]) -> int:
    count = 0
    for row in rows:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        count += 1
    handle.flush()
    return count


def clone_output_row(row: Dict[str, Any], label: Dict[str, Any], *, method_name: str, ablation: str) -> Dict[str, Any]:
    output = dict(row)
    output.pop("embedding", None)
    output.update(
        {
            "baseline_method": method_name,
            "ablation": ablation,
            "selected": bool(label.get("selected")),
            "oracle_score": label.get("oracle_score", 0.0),
            "oracle_label": label.get("oracle_label", "irrelevant"),
            "system_score": row.get("relevance_score", 0.0),
            "system_label": row.get("relevance_level", "edge_relevant"),
            "select_probability": 0.0,
        }
    )
    return output


def finalize_outputs(*, input_dir: Path, output_dir: Path, method_stats: Dict[str, Any], method_name: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    episode_rows = fixed_base.load_jsonl(input_dir / "episodes.jsonl")
    output_rows = fixed_base.load_jsonl(output_dir / "episode_papers.jsonl")
    grouped_output = fixed_base.group_by_episode(output_rows)
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
    write_text_ensuring_parent(
        output_dir / "evaluation_metrics.json",
        json.dumps(result, ensure_ascii=False, indent=2),
    )
    write_text_ensuring_parent(
        output_dir / "dataset_summary.json",
        json.dumps(dataset_summary, ensure_ascii=False, indent=2),
    )
    write_text_ensuring_parent(
        output_dir / "dataset_summary.md",
        eval_metrics.build_dataset_summary_markdown(dataset_summary),
    )
    write_text_ensuring_parent(
        output_dir / "main_experiment_table_top20.md",
        eval_metrics.build_main_experiment_table(summary, method_name),
    )
    write_text_ensuring_parent(
        output_dir / "case_metrics_table_top20.md",
        eval_metrics.build_case_metrics_table(summary, method_name),
    )
    write_text_ensuring_parent(
        output_dir / "users.json",
        json.dumps(fixed_base.load_json(input_dir / "users.json"), ensure_ascii=False, indent=2),
    )
    method_stats["completed"] = True
    method_stats["output_rows"] = len(output_rows)
    write_text_ensuring_parent(
        output_dir / f"{method_stats['method_key']}_summary.json",
        json.dumps(method_stats, ensure_ascii=False, indent=2),
    )


def run_ablation(
    *,
    ablation: str,
    input_dir: Path,
    output_dir: Path,
    profile_state_path: Path,
    roles_path: Path,
    top_k: int = DEFAULT_TOP_K,
    reset: bool = False,
    progress_every: int = 10,
    max_episodes: Optional[int] = None,
) -> Dict[str, Any]:
    method = METHODS[ablation]
    candidate_file = input_dir / CLEAN_CANDIDATE_FILE
    label_file = input_dir / CLEAN_LABEL_FILE
    episode_file = input_dir / "episodes.jsonl"
    total_episodes = count_jsonl(episode_file)
    if max_episodes:
        total_episodes = min(total_episodes, int(max_episodes))

    if reset:
        reset_output_dir(output_dir)
    else:
        output_dir.mkdir(parents=True, exist_ok=True)

    progress_path = output_dir / PROGRESS_FILE
    progress = load_progress(progress_path)
    completed_ids = set(str(item) for item in progress.get("completed_episode_ids", []) or [])
    initial_completed_count = len(completed_ids)

    label_map = fixed_base.build_label_map(fixed_base.load_jsonl(label_file))
    initial_users = build_initial_users(input_dir, roles_path)
    profile_timeline = load_profile_timeline(profile_state_path, initial_users)
    feature_cache: Dict[str, Dict[str, Any]] = {}
    zero_embeddings_by_dim: Dict[int, List[float]] = {}

    method_stats = {
        "method_key": method["key"],
        "method_name": method["name"],
        "description": method["description"],
        "ablation": ablation,
        "episodes": len(completed_ids),
        "top_k": top_k,
        "profile_source": str(profile_state_path),
        "resumable": True,
        "completed": False,
    }

    output_file = output_dir / "episode_papers.jsonl"
    mode = "a" if output_file.exists() and not reset else "w"
    start_time = time.time()
    rows_written = 0
    processed_this_run = 0

    print(
        f"Running {method['name']}: {len(completed_ids)}/{total_episodes} episodes already complete.",
        flush=True,
    )
    with output_file.open(mode, encoding="utf-8") as output_handle:
        for episode_index, (episode_id, episode_rows_for_day) in enumerate(iter_episode_groups(candidate_file), start=1):
            if max_episodes and episode_index > max_episodes:
                break
            if episode_id in completed_ids:
                continue
            if not episode_rows_for_day:
                continue

            user_id = str(episode_rows_for_day[0].get("user_id") or "").strip()
            episode_date = str(episode_rows_for_day[0].get("date") or "").strip()
            base_profile = profile_before_episode(profile_timeline, user_id, episode_date, initial_users)
            profile = apply_profile_ablation(base_profile, ablation)
            embedding_dim = len(profile.get("interest_vector") or []) or 768
            zero_embedding = zero_embeddings_by_dim.setdefault(embedding_dim, [0.0] * embedding_dim)
            prepared_rows = prepare_features_cached(
                episode_rows_for_day,
                ablation=ablation,
                embedding_dim=embedding_dim,
                feature_cache=feature_cache,
                zero_embedding=zero_embedding,
            )
            with open(os.devnull, "w", encoding="utf-8") as sink, contextlib.redirect_stdout(sink):
                ranked_pool = rerank_candidates(prepared_rows, profile, top_k=top_k, ablation=ablation)

            output_rows = []
            for row in ranked_pool:
                label = label_map.get((episode_id, fixed_base.paper_identity(row)), {})
                output_rows.append(clone_output_row(row, label, method_name=method["name"], ablation=ablation))
            rows_written += write_rows(output_handle, output_rows)
            processed_this_run += 1

            completed_ids.add(episode_id)
            method_stats["episodes"] = len(completed_ids)
            elapsed = max(0.001, time.time() - start_time)
            save_progress(
                progress_path,
                {
                    **method_stats,
                    "completed_episode_ids": sorted(completed_ids),
                    "rows_written_this_run": rows_written,
                    "feature_cache_size": len(feature_cache),
                    "elapsed_seconds_this_run": round(elapsed, 2),
                    "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                },
            )

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

    if max_episodes and len(completed_ids) < count_jsonl(episode_file):
        print(f"Stopped early after max_episodes={max_episodes}; metrics not finalized.", flush=True)
        return method_stats

    finalize_outputs(input_dir=input_dir, output_dir=output_dir, method_stats=method_stats, method_name=method["name"])
    save_progress(progress_path, {**method_stats, "completed_episode_ids": sorted(completed_ids), "completed": True})
    print(json.dumps(method_stats, ensure_ascii=False, indent=2), flush=True)
    return method_stats


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run resumable PaperFlow mechanism ablations.")
    parser.add_argument("--ablation", required=True, choices=sorted(METHODS), help="Ablation to run.")
    parser.add_argument("--input-dir", required=True, help="Clean baseline input directory.")
    parser.add_argument("--profile-state-file", required=True, help="Full-run profiles_state.jsonl.")
    parser.add_argument("--output-dir", default=None, help="Output directory. Defaults to <benchmark>/main_experiment/<method>.")
    parser.add_argument("--roles-path", default="data/roles.json", help="Role configuration path.")
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K, help="Displayed papers per episode.")
    parser.add_argument("--reset", action="store_true", help="Delete existing output dir before running.")
    parser.add_argument("--progress-every", type=int, default=10, help="Print progress every N completed episodes.")
    parser.add_argument("--max-episodes", type=int, default=None, help="Optional smoke-test limit; does not finalize metrics.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_dir = resolve_project_path(args.input_dir)
    output_dir = (
        resolve_project_path(args.output_dir)
        if args.output_dir
        else input_dir.parent / "main_experiment" / METHODS[args.ablation]["key"]
    )
    run_ablation(
        ablation=str(args.ablation),
        input_dir=input_dir,
        output_dir=output_dir,
        profile_state_path=resolve_project_path(args.profile_state_file),
        roles_path=resolve_project_path(args.roles_path),
        top_k=int(args.top_k),
        reset=bool(args.reset),
        progress_every=int(args.progress_every),
        max_episodes=args.max_episodes,
    )


if __name__ == "__main__":
    main()
