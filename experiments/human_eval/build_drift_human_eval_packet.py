#!/usr/bin/env python3
"""Build a blind annotation packet for drift-adaptation human evaluation."""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Set, Tuple


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from experiments.human_eval import build_main_human_eval_packet as common


DEFAULT_BENCHMARK_DIR = common.DEFAULT_BENCHMARK_DIR
DEFAULT_METHOD_DIRS = [
    ("full_paperflow", "Full PaperFlow", "."),
    ("paperflow_no_drift", "w/o Drift", "main_experiment/paperflow_no_drift"),
    ("paperflow_fixed_profile", "Fixed Profile", "main_experiment/paperflow_fixed_profile"),
]


def normalize_topic(value: Any) -> str:
    text = str(value or "").strip().lower().replace("_", "-")
    text = " ".join(text.split()).replace(" ", "-")
    while "--" in text:
        text = text.replace("--", "-")
    return text.strip("-")


def parse_date(value: Any) -> datetime:
    text = str(value or "")
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise ValueError(f"Invalid date: {value}")


def iso_date(value: datetime) -> str:
    return value.strftime("%Y-%m-%d")


def flatten_topics(value: Any) -> Iterable[str]:
    if value is None:
        return
    if isinstance(value, str):
        yield value
        return
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            if isinstance(item, dict):
                for nested in ("canonical_name", "name", "name_cn"):
                    if item.get(nested):
                        yield str(item[nested])
        return
    if isinstance(value, list):
        for item in value:
            yield from flatten_topics(item)


def row_topics(row: Dict[str, Any]) -> Set[str]:
    topics: Set[str] = set()
    for key in ("topics", "keywords", "direction_terms", "oracle_matched_topics", "drift_topics", "reading_signal_topics"):
        for value in flatten_topics(row.get(key)):
            normalized = normalize_topic(value)
            if normalized:
                topics.add(normalized)
    return topics


def topic_match(row: Dict[str, Any], target_topics: Set[str]) -> bool:
    if not target_topics:
        return False
    if row_topics(row).intersection(target_topics):
        return True
    text = normalize_topic(f"{row.get('title', '')} {row.get('abstract', '')}")
    return any(topic and topic in text for topic in target_topics)


def load_drift_events(path: Path) -> List[Dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    events = payload.get("context", {}).get("events", {}) if isinstance(payload, dict) else {}
    result: List[Dict[str, Any]] = []
    for user_id, event in events.items():
        if isinstance(event, dict):
            result.append(
                {
                    "user_id": str(event.get("user_id") or user_id),
                    "date": str(event.get("date") or ""),
                    "anchor_topic": event.get("anchor_topic"),
                    "anchor_topics": event.get("anchor_topics") or [event.get("anchor_topic")],
                    "suppressed_topics": event.get("suppressed_topics") or [],
                    "trigger_source": event.get("trigger_source"),
                }
            )
    return result


def parse_method_specs(values: Sequence[str], benchmark_dir: Path) -> List[Tuple[str, str, Path]]:
    if not values:
        return [(key, name, benchmark_dir / rel) for key, name, rel in DEFAULT_METHOD_DIRS]
    specs: List[Tuple[str, str, Path]] = []
    for value in values:
        parts = value.split("=", 2)
        if len(parts) not in {2, 3}:
            raise SystemExit("--method must use key=output_dir or key=output_dir=display name")
        key = parts[0]
        path = Path(parts[1])
        name = parts[2] if len(parts) == 3 else key
        specs.append((key, name, path))
    return specs


def collect_candidates(path: Path, events: Sequence[Dict[str, Any]], post_days: int) -> Dict[Tuple[str, str], List[Dict[str, Any]]]:
    event_by_user = {event["user_id"]: event for event in events}
    windows: Dict[str, Tuple[datetime, datetime]] = {}
    for event in events:
        start = parse_date(event["date"])
        windows[event["user_id"]] = (start, start + timedelta(days=post_days))

    candidates: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    episode_path = path if path.is_file() else path / "episode_papers.jsonl"
    if not episode_path.exists():
        return candidates
    for row in common.iter_jsonl(episode_path):
        if not common.as_bool(row.get("shown")):
            continue
        user_id = str(row.get("user_id") or "")
        if user_id not in windows:
            continue
        try:
            row_date = parse_date(row.get("date"))
        except ValueError:
            continue
        start, end = windows[user_id]
        if row_date < start or row_date > end:
            continue
        candidates.setdefault((user_id, event_by_user[user_id]["date"]), []).append(row)
    return candidates


def choose_event_rows(rows: List[Dict[str, Any]], event: Dict[str, Any], count: int, rng: random.Random) -> List[Dict[str, Any]]:
    new_topics = {normalize_topic(topic) for topic in event.get("anchor_topics", []) if topic}
    old_topics = {normalize_topic(topic) for topic in event.get("suppressed_topics", []) if topic}
    scored = []
    for row in rows:
        new_hit = topic_match(row, new_topics)
        old_hit = topic_match(row, old_topics)
        rank = int(row.get("system_rank") or 99)
        priority = (int(new_hit), int(not old_hit), -rank, rng.random())
        scored.append((priority, row))
    scored.sort(reverse=True)
    return [row for _, row in scored[:count]]


def build_rows(
    specs: Sequence[Tuple[str, str, Path]],
    events: Sequence[Dict[str, Any]],
    users: Dict[str, Dict[str, Any]],
    *,
    papers_per_event: int,
    post_days: int,
    seed: int,
    abstract_chars: int,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    rng = random.Random(seed)
    blind_rows: List[Dict[str, Any]] = []
    key_rows: List[Dict[str, Any]] = []
    sample_index = 1
    event_lookup = {(event["user_id"], event["date"]): event for event in events}
    for method_key, method_name, path in specs:
        candidates = collect_candidates(path, events, post_days)
        for event_key, event in event_lookup.items():
            for paper in choose_event_rows(candidates.get(event_key, []), event, papers_per_event, rng):
                sample_id = f"HDRIFT_{sample_index:05d}"
                sample_index += 1
                user_id = str(event["user_id"])
                new_topics = {normalize_topic(topic) for topic in event.get("anchor_topics", []) if topic}
                old_topics = {normalize_topic(topic) for topic in event.get("suppressed_topics", []) if topic}
                new_hit = topic_match(paper, new_topics)
                old_hit = topic_match(paper, old_topics)
                blind_rows.append(
                    {
                        "sample_id": sample_id,
                        "user_profile": common.profile_text(users.get(user_id)),
                        "drift_event_date": event.get("date"),
                        "new_interest_topics": ", ".join(str(topic) for topic in event.get("anchor_topics", []) if topic),
                        "downweighted_old_topics": ", ".join(str(topic) for topic in event.get("suppressed_topics", []) if topic),
                        "recommendation_date": paper.get("date"),
                        "paper_title": common.truncate(paper.get("title"), 500),
                        "paper_abstract": common.truncate(paper.get("abstract"), abstract_chars),
                        "paper_authors": common.truncate(paper.get("authors"), 500),
                        "NewTopicFit": "",
                        "AdaptationAppropriateness": "",
                        "OldNewBalance": "",
                        "DriftDecisionHelpfulness": "",
                        "comments": "",
                    }
                )
                key_rows.append(
                    {
                        "sample_id": sample_id,
                        "method_key": method_key,
                        "method_name": method_name,
                        "event_user_id": user_id,
                        "event_date": event.get("date"),
                        "episode_id": paper.get("episode_id"),
                        "recommendation_date": paper.get("date"),
                        "paper_id": paper.get("paper_id"),
                        "system_rank": paper.get("system_rank"),
                        "system_label": paper.get("system_label"),
                        "system_score": paper.get("system_score"),
                        "oracle_label": paper.get("oracle_label"),
                        "oracle_score": paper.get("oracle_score"),
                        "selected": common.as_bool(paper.get("selected")),
                        "new_topic_match": new_hit,
                        "old_topic_match": old_hit,
                    }
                )
    return blind_rows, key_rows


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0].keys()) if rows else []
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_guidelines(path: Path) -> None:
    path.write_text(
        """# Drift Human Evaluation Annotation Guide

Annotators see the user's profile, the drift direction, old downweighted topics,
and a post-drift recommended paper. Method names and automatic scores are hidden.

Use a 1-5 Likert scale:

- NewTopicFit: whether the recommendation fits the new interest direction.
- AdaptationAppropriateness: whether the response to the interest change is appropriate.
- OldNewBalance: whether the balance between old and new interests is reasonable.
- DriftDecisionHelpfulness: whether the recommendation helps the user decide whether to continue the new direction.

```text
AdaptationHumanScore = 20 * mean(
  NewTopicFit,
  AdaptationAppropriateness,
  OldNewBalance,
  DriftDecisionHelpfulness
)
```
""",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a blind drift human-evaluation packet.")
    parser.add_argument("--benchmark-dir", default=str(DEFAULT_BENCHMARK_DIR))
    parser.add_argument("--drift-json", default=None)
    parser.add_argument("--method", action="append", default=[])
    parser.add_argument("--papers-per-event", type=int, default=2)
    parser.add_argument("--post-days", type=int, default=7)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--abstract-chars", type=int, default=1200)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    benchmark_dir = Path(args.benchmark_dir)
    drift_json = Path(args.drift_json) if args.drift_json else benchmark_dir / "main_experiment" / "drift_adaptation_experiment.json"
    output_dir = Path(args.output_dir) if args.output_dir else benchmark_dir / "evaluation" / "drift_human_eval"
    events = load_drift_events(drift_json)
    users = common.load_users(benchmark_dir / "users.json")
    specs = parse_method_specs(args.method, benchmark_dir)
    blind_rows, key_rows = build_rows(
        specs,
        events,
        users,
        papers_per_event=args.papers_per_event,
        post_days=args.post_days,
        seed=args.seed,
        abstract_chars=args.abstract_chars,
    )
    write_csv(output_dir / "drift_human_eval_blind.csv", blind_rows)
    write_csv(output_dir / "drift_human_eval_key.csv", key_rows)
    write_guidelines(output_dir / "drift_human_eval_guidelines.md")
    print(f"Blind packet: {output_dir / 'drift_human_eval_blind.csv'}")
    print(f"Internal key: {output_dir / 'drift_human_eval_key.csv'}")
    print(f"Rows exported: {len(blind_rows)}")


if __name__ == "__main__":
    main()
