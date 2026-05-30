#!/usr/bin/env python3
"""Build a drift-adaptation specialty table from existing PaperFlow outputs.

The script does not rerun recommendation. It reads existing episode outputs,
uses the full-system drift timeline to define drift events, then compares how
each method behaves before/after those events.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from experiments.benchmark.evaluate_simulation_metrics import evaluate_episode


DEFAULT_BENCHMARK_DIR = (
    PROJECT_ROOT
    / "data"
    / "benchmark_full_24users_20260301_20260419_show20_with_reading"
)


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


def parse_date(value: Any) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def iso_date(value: datetime) -> str:
    return value.strftime("%Y-%m-%d")


def mean(values: Sequence[Optional[float]]) -> Optional[float]:
    clean = [float(value) for value in values if value is not None and math.isfinite(float(value))]
    if not clean:
        return None
    return sum(clean) / len(clean)


def safe_div(numerator: float, denominator: float) -> Optional[float]:
    if denominator <= 0:
        return None
    return numerator / denominator


def format_cell(value: Any, digits: int = 4) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            return "N/A"
        return f"{value:.{digits}f}"
    return str(value)


def normalize_topic(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = text.replace("_", "-")
    text = " ".join(text.split())
    text = text.replace(" ", "-")
    while "--" in text:
        text = text.replace("--", "-")
    return text.strip("-")


def flatten_topic_values(value: Any) -> Iterable[str]:
    if value is None:
        return
    if isinstance(value, str):
        if value.strip():
            yield value
        return
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            if isinstance(item, dict):
                for nested_key in ("canonical_name", "name", "name_cn"):
                    if item.get(nested_key):
                        yield str(item[nested_key])
                aliases = item.get("aliases")
                if isinstance(aliases, list):
                    for alias in aliases:
                        yield str(alias)
                paper_terms = item.get("paper_terms")
                if isinstance(paper_terms, list):
                    for term in paper_terms:
                        yield str(term)
        return
    if isinstance(value, list):
        for item in value:
            yield from flatten_topic_values(item)


def row_topic_set(row: Dict[str, Any]) -> Set[str]:
    topics: Set[str] = set()
    for key in (
        "topics",
        "keywords",
        "direction_terms",
        "oracle_matched_topics",
        "drift_topics",
        "reading_signal_topics",
    ):
        for raw in flatten_topic_values(row.get(key)):
            normalized = normalize_topic(raw)
            if normalized:
                topics.add(normalized)
    return topics


def topic_match(row: Dict[str, Any], target_topics: Set[str]) -> bool:
    if not target_topics:
        return False
    row_topics = row_topic_set(row)
    if row_topics.intersection(target_topics):
        return True

    # As a fallback, allow exact normalized phrase hits in title/abstract.
    text = normalize_topic(f"{row.get('title', '')} {row.get('abstract', '')}")
    return any(topic and topic in text for topic in target_topics)


def episode_id_for(row: Dict[str, Any]) -> str:
    episode_id = str(row.get("episode_id") or "").strip()
    if episode_id:
        return episode_id
    user_id = str(row.get("user_id") or "").strip()
    date = str(row.get("date") or "").strip()
    return f"{user_id}::{date}" if user_id and date else ""


def group_episode_rows(path: Path) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in load_jsonl(path):
        episode_id = episode_id_for(row)
        if episode_id:
            grouped[episode_id].append(row)
    return dict(grouped)


def read_episode_metadata(benchmark_dir: Path) -> Dict[str, Dict[str, Any]]:
    metadata: Dict[str, Dict[str, Any]] = {}
    for row in load_jsonl(benchmark_dir / "episodes.jsonl"):
        episode_id = str(row.get("episode_id") or "").strip()
        if episode_id:
            metadata[episode_id] = row
    return metadata


def first_trigger_by_user(timeline_rows: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    triggers: Dict[str, Dict[str, Any]] = {}
    for row in timeline_rows:
        if str(row.get("event_type") or "") != "trigger":
            continue
        user_id = str(row.get("user_id") or "")
        date = parse_date(row.get("date"))
        if not user_id or date is None:
            continue
        current = triggers.get(user_id)
        current_date = parse_date(current.get("date")) if current else None
        if current is None or current_date is None or date < current_date:
            triggers[user_id] = row
    return triggers


def read_drift_events(benchmark_dir: Path) -> Dict[str, Dict[str, Any]]:
    """Return first anchor-lock drift event per user, enriched with trigger info."""
    timeline_rows = load_jsonl(benchmark_dir / "drift_timeline.jsonl")
    triggers = first_trigger_by_user(timeline_rows)
    events: Dict[str, Dict[str, Any]] = {}
    for row in timeline_rows:
        if str(row.get("event_type") or "") != "drift":
            continue
        if str(row.get("method") or "") != "anchor_lock":
            continue
        user_id = str(row.get("user_id") or "")
        date = parse_date(row.get("date"))
        if not user_id or date is None:
            continue
        current = events.get(user_id)
        current_date = parse_date(current.get("date")) if current else None
        if current is not None and current_date is not None and date >= current_date:
            continue

        trigger = triggers.get(user_id) or {}
        anchor_topics = set()
        for raw in flatten_topic_values(row.get("anchor_topics")):
            normalized = normalize_topic(raw)
            if normalized:
                anchor_topics.add(normalized)
        if row.get("anchor_topic"):
            anchor_topics.add(normalize_topic(row.get("anchor_topic")))
        if not anchor_topics and trigger.get("hidden_anchor"):
            anchor_topics.add(normalize_topic(trigger.get("hidden_anchor")))

        suppressed_topics = {
            normalize_topic(raw)
            for raw in flatten_topic_values(trigger.get("suppressed_topics"))
            if normalize_topic(raw)
        }

        events[user_id] = {
            "user_id": user_id,
            "date": iso_date(date),
            "anchor_topic": normalize_topic(row.get("anchor_topic")),
            "anchor_topics": sorted(topic for topic in anchor_topics if topic),
            "suppressed_topics": sorted(suppressed_topics),
            "trigger_source": trigger.get("trigger_source"),
            "trigger_checkfile": trigger.get("trigger_checkfile"),
        }
    return events


def default_methods(benchmark_dir: Path) -> List[Tuple[str, Path]]:
    candidates = [
        ("Full PaperFlow", benchmark_dir),
        ("w/o Drift", benchmark_dir / "main_experiment" / "paperflow_no_drift"),
        ("Fixed Profile", benchmark_dir / "main_experiment" / "paperflow_fixed_profile"),
    ]
    return [(name, path) for name, path in candidates if (path / "episode_papers.jsonl").exists()]


def parse_method_arg(raw: str) -> Tuple[str, Path]:
    if "=" not in raw:
        path = Path(raw)
        return (path.name.replace("_", " ").title(), path)
    name, path_text = raw.split("=", 1)
    return name.strip(), Path(path_text.strip())


def method_episode_metrics(
    grouped_rows: Dict[str, List[Dict[str, Any]]],
    episode_ids: Sequence[str],
    k: int,
) -> Dict[str, Any]:
    values: Dict[str, List[Optional[float]]] = defaultdict(list)
    present = 0
    for episode_id in episode_ids:
        rows = grouped_rows.get(episode_id)
        if not rows:
            continue
        present += 1
        metrics = evaluate_episode(rows, [k])
        case = (metrics.get("case_per_k") or {}).get(str(k)) or {}
        selected = (metrics.get("per_k") or {}).get(str(k)) or {}
        oracle = (metrics.get("oracle_per_k") or {}).get(str(k)) or {}
        values["gNDCG@20"].append(case.get("gndcg"))
        values["Useful@20"].append(case.get("useful_rate"))
        values["OracleRecall@20"].append(oracle.get("recall"))
        values["StrictR@20+"].append(case.get("strict_recall_positive"))
        values["MRR@20"].append(case.get("mrr"))
        values["SelectedNDCG@20"].append(selected.get("ndcg"))
    return {
        "EpisodeCount": present,
        "gNDCG@20": mean(values["gNDCG@20"]),
        "Useful@20": mean(values["Useful@20"]),
        "OracleRecall@20": mean(values["OracleRecall@20"]),
        "StrictR@20+": mean(values["StrictR@20+"]),
        "MRR@20": mean(values["MRR@20"]),
        "SelectedNDCG@20": mean(values["SelectedNDCG@20"]),
    }


def topic_window_metrics(
    grouped_rows: Dict[str, List[Dict[str, Any]]],
    episode_ids: Sequence[str],
    events: Dict[str, Dict[str, Any]],
    k: int,
) -> Dict[str, Any]:
    new_recalls: List[Optional[float]] = []
    old_rates: List[Optional[float]] = []
    new_hits: List[float] = []
    old_hits: List[float] = []

    for episode_id in episode_ids:
        rows = grouped_rows.get(episode_id)
        if not rows:
            continue
        user_id = episode_id.split("::", 1)[0]
        event = events.get(user_id) or {}
        new_topics = {normalize_topic(topic) for topic in event.get("anchor_topics") or [] if normalize_topic(topic)}
        old_topics = {normalize_topic(topic) for topic in event.get("suppressed_topics") or [] if normalize_topic(topic)}
        if not new_topics and not old_topics:
            continue

        shown = [row for row in rows if row.get("shown")]
        shown.sort(key=lambda row: int(row.get("system_rank") or 10**9))
        topk = shown[:k]

        if new_topics:
            pool_new = sum(1 for row in rows if topic_match(row, new_topics))
            shown_new = sum(1 for row in topk if topic_match(row, new_topics))
            new_recalls.append(safe_div(shown_new, pool_new))
            new_hits.append(float(shown_new))

        if old_topics:
            shown_old = sum(1 for row in topk if topic_match(row, old_topics))
            old_rates.append(safe_div(shown_old, k))
            old_hits.append(float(shown_old))

    return {
        "NewTopicRecall@20": mean(new_recalls),
        "OldTopicRate@20": mean(old_rates),
        "NewTopicHits@20": mean(new_hits),
        "OldTopicHits@20": mean(old_hits),
    }


def adaptation_delay_days(
    grouped_rows: Dict[str, List[Dict[str, Any]]],
    events: Dict[str, Dict[str, Any]],
    metadata: Dict[str, Dict[str, Any]],
    *,
    k: int,
    post_days: int,
    min_new_topic_hits: int,
) -> Optional[float]:
    delays: List[float] = []
    episode_ids_by_user_date: Dict[Tuple[str, str], str] = {}
    for episode_id, meta in metadata.items():
        user_id = str(meta.get("user_id") or episode_id.split("::", 1)[0])
        date = str(meta.get("date") or "")
        episode_ids_by_user_date[(user_id, date)] = episode_id

    for user_id, event in events.items():
        drift_date = parse_date(event.get("date"))
        new_topics = {normalize_topic(topic) for topic in event.get("anchor_topics") or [] if normalize_topic(topic)}
        if drift_date is None or not new_topics:
            continue

        found: Optional[int] = None
        for offset in range(0, post_days + 1):
            date = iso_date(drift_date + timedelta(days=offset))
            episode_id = episode_ids_by_user_date.get((user_id, date))
            rows = grouped_rows.get(episode_id or "")
            if not rows:
                continue
            shown = [row for row in rows if row.get("shown")]
            shown.sort(key=lambda row: int(row.get("system_rank") or 10**9))
            hits = sum(1 for row in shown[:k] if topic_match(row, new_topics))
            if hits >= min_new_topic_hits:
                found = offset
                break
        if found is not None:
            delays.append(float(found))
    return mean(delays)


def select_window_episode_ids(
    metadata: Dict[str, Dict[str, Any]],
    events: Dict[str, Dict[str, Any]],
    *,
    pre_days: int,
    post_days: int,
) -> Dict[str, List[str]]:
    windows: Dict[str, List[str]] = defaultdict(list)
    for episode_id, meta in metadata.items():
        user_id = str(meta.get("user_id") or episode_id.split("::", 1)[0])
        date = parse_date(meta.get("date"))
        if date is None:
            continue
        status = str(meta.get("drift_status") or "missing")
        if status == "stable":
            windows["Stable"].append(episode_id)
        if status in {"observing", "shifting"}:
            windows["ActiveDrift"].append(episode_id)
        if status == "recovered":
            windows["Recovered"].append(episode_id)

        event = events.get(user_id)
        drift_date = parse_date(event.get("date")) if event else None
        if drift_date is None:
            continue
        if drift_date - timedelta(days=pre_days) <= date < drift_date:
            windows["PreDriftWindow"].append(episode_id)
        if drift_date <= date <= drift_date + timedelta(days=post_days):
            windows["PostDriftWindow"].append(episode_id)
    return dict(windows)


def build_rows(
    benchmark_dir: Path,
    method_specs: Sequence[Tuple[str, Path]],
    *,
    pre_days: int,
    post_days: int,
    k: int,
    min_new_topic_hits: int,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    metadata = read_episode_metadata(benchmark_dir)
    events = read_drift_events(benchmark_dir)
    windows = select_window_episode_ids(metadata, events, pre_days=pre_days, post_days=post_days)

    rows: List[Dict[str, Any]] = []
    for method_name, output_dir in method_specs:
        episode_path = output_dir / "episode_papers.jsonl"
        if not episode_path.exists():
            continue
        grouped = group_episode_rows(episode_path)
        post = method_episode_metrics(grouped, windows.get("PostDriftWindow", []), k)
        active = method_episode_metrics(grouped, windows.get("ActiveDrift", []), k)
        stable = method_episode_metrics(grouped, windows.get("Stable", []), k)
        recovered = method_episode_metrics(grouped, windows.get("Recovered", []), k)
        topics = topic_window_metrics(grouped, windows.get("PostDriftWindow", []), events, k)
        delay = adaptation_delay_days(
            grouped,
            events,
            metadata,
            k=k,
            post_days=post_days,
            min_new_topic_hits=min_new_topic_hits,
        )

        rows.append(
            {
                "Method": method_name,
                "PostEpisodes": post.get("EpisodeCount"),
                "PostDrift_gNDCG@20": post.get("gNDCG@20"),
                "PostDrift_Useful@20": post.get("Useful@20"),
                "PostDrift_OracleRecall@20": post.get("OracleRecall@20"),
                "PostDrift_StrictR@20+": post.get("StrictR@20+"),
                "PostDrift_SelectedNDCG@20": post.get("SelectedNDCG@20"),
                "NewTopicRecall@20": topics.get("NewTopicRecall@20"),
                "NewTopicHits@20": topics.get("NewTopicHits@20"),
                "OldTopicRate@20": topics.get("OldTopicRate@20"),
                "AdaptationDelayDays": delay,
                "ActiveDrift_gNDCG@20": active.get("gNDCG@20"),
                "ActiveDrift_SelectedNDCG@20": active.get("SelectedNDCG@20"),
                "Recovered_gNDCG@20": recovered.get("gNDCG@20"),
                "Stable_gNDCG@20": stable.get("gNDCG@20"),
                "Stable_SelectedNDCG@20": stable.get("SelectedNDCG@20"),
            }
        )

    context = {
        "benchmark_dir": str(benchmark_dir),
        "drift_events": len(events),
        "windows": {key: len(value) for key, value in sorted(windows.items())},
        "pre_days": pre_days,
        "post_days": post_days,
        "k": k,
        "min_new_topic_hits": min_new_topic_hits,
        "events": events,
    }
    return rows, context


def write_csv(path: Path, rows: Sequence[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_markdown(path: Path, rows: Sequence[Dict[str, Any]], context: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "Method",
        "PostEpisodes",
        "PostDrift_gNDCG@20",
        "PostDrift_Useful@20",
        "PostDrift_OracleRecall@20",
        "PostDrift_StrictR@20+",
        "PostDrift_SelectedNDCG@20",
        "NewTopicRecall@20",
        "OldTopicRate@20",
        "AdaptationDelayDays",
        "Stable_gNDCG@20",
        "Stable_SelectedNDCG@20",
    ]
    lines = [
        "# Drift Adaptation Experiment",
        "",
        f"- Drift events: {context.get('drift_events')}",
        f"- Pre-window days: {context.get('pre_days')}",
        f"- Post-window days: {context.get('post_days')}",
        f"- Top-k: {context.get('k')}",
        f"- Window episode counts: {json.dumps(context.get('windows') or {}, ensure_ascii=False)}",
        "",
        "| " + " | ".join(fields) + " |",
        "| " + " | ".join(["---"] + ["---:"] * (len(fields) - 1)) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(format_cell(row.get(field)) for field in fields) + " |")
    lines.extend(
        [
            "",
            "## Metric Notes",
            "",
            "- PostDrift_* metrics are computed only on each drift user's post-drift window.",
            "- NewTopicRecall@20 uses drift anchor topics from `drift_timeline.jsonl`.",
            "- OldTopicRate@20 uses suppressed topics from the corresponding drift trigger.",
            "- AdaptationDelayDays is the first post-drift day with at least the configured number of new-topic hits in Top-20.",
            "- Stable_* metrics use episodes whose full-system metadata has `drift_status=stable`.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a PaperFlow drift-adaptation specialty table.")
    parser.add_argument("--benchmark-dir", type=Path, default=DEFAULT_BENCHMARK_DIR)
    parser.add_argument("--method", action="append", default=[], help="Extra method as Name=output_dir.")
    parser.add_argument("--pre-days", type=int, default=3)
    parser.add_argument("--post-days", type=int, default=7)
    parser.add_argument("--k", type=int, default=20)
    parser.add_argument("--min-new-topic-hits", type=int, default=3)
    parser.add_argument("--output-prefix", type=Path, default=None)
    args = parser.parse_args()

    benchmark_dir = args.benchmark_dir.resolve()
    method_specs = default_methods(benchmark_dir)
    method_specs.extend(parse_method_arg(raw) for raw in args.method)
    if not method_specs:
        raise SystemExit("No method episode_papers.jsonl files found.")

    rows, context = build_rows(
        benchmark_dir,
        method_specs,
        pre_days=max(0, args.pre_days),
        post_days=max(0, args.post_days),
        k=max(1, args.k),
        min_new_topic_hits=max(1, args.min_new_topic_hits),
    )

    output_prefix = args.output_prefix
    if output_prefix is None:
        output_prefix = benchmark_dir / "main_experiment" / "drift_adaptation_experiment"
    output_prefix = output_prefix.resolve()

    write_csv(output_prefix.with_suffix(".csv"), rows)
    write_markdown(output_prefix.with_suffix(".md"), rows, context)
    output_prefix.with_suffix(".json").write_text(
        json.dumps({"context": context, "rows": rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Wrote {output_prefix.with_suffix('.md')}")
    print(f"Wrote {output_prefix.with_suffix('.csv')}")
    print(f"Wrote {output_prefix.with_suffix('.json')}")


if __name__ == "__main__":
    main()
