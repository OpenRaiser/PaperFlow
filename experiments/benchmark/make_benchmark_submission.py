#!/usr/bin/env python3
"""Create PaperFlow-Bench Top-20 prediction JSONL files."""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable


def iter_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def as_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number):
        return None
    return number


def row_sort_key(row: Dict[str, Any], rank_field: str | None, score_field: str | None) -> tuple:
    rank = as_float(row.get(rank_field)) if rank_field else None
    score = as_float(row.get(score_field)) if score_field else None
    pool_rank = as_float(row.get("pool_rank"))
    paper_id = str(row.get("paper_id") or "")
    if rank is not None:
        return (0, rank, 0.0, pool_rank if pool_rank is not None else float("inf"), paper_id)
    if score is not None:
        return (1, 0.0, -score, pool_rank if pool_rank is not None else float("inf"), paper_id)
    return (2, 0.0, 0.0, pool_rank if pool_rank is not None else float("inf"), paper_id)


def make_submission(
    source: Path,
    output: Path,
    rank_field: str | None,
    score_field: str | None,
    shown_only: bool,
    top_k: int,
) -> int:
    grouped: dict[str, list[Dict[str, Any]]] = defaultdict(list)
    for row in iter_jsonl(source):
        episode_id = str(row.get("episode_id") or "")
        paper_id = row.get("paper_id")
        if not episode_id or paper_id in (None, ""):
            continue
        if shown_only and not bool(row.get("shown")):
            continue
        grouped[episode_id].append(row)

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for episode_id in sorted(grouped):
            rows = sorted(grouped[episode_id], key=lambda row: row_sort_key(row, rank_field, score_field))
            paper_ids: list[Any] = []
            seen: set[str] = set()
            for row in rows:
                paper_id = row.get("paper_id")
                key = str(paper_id)
                if key in seen:
                    continue
                seen.add(key)
                paper_ids.append(paper_id)
                if len(paper_ids) >= top_k:
                    break
            handle.write(json.dumps({"episode_id": episode_id, "paper_ids": paper_ids}, ensure_ascii=False) + "\n")
    return len(grouped)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark-dir", type=Path, default=Path("."))
    parser.add_argument(
        "--source",
        type=Path,
        default=None,
        help="Input episode-paper JSONL. Defaults to <benchmark-dir>/data/episode_labels.jsonl.",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--rank-field",
        default="pool_rank",
        help="Ascending rank field to use. Use system_rank for PaperFlow/baseline episode_papers outputs.",
    )
    parser.add_argument("--score-field", default=None, help="Descending score field fallback, for example system_score.")
    parser.add_argument("--shown-only", action="store_true", help="Keep only rows with shown=true before ranking.")
    parser.add_argument("--top-k", type=int, default=20)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = args.source or (args.benchmark_dir / "data" / "episode_labels.jsonl")
    episodes = make_submission(
        source=source,
        output=args.output,
        rank_field=args.rank_field,
        score_field=args.score_field,
        shown_only=args.shown_only,
        top_k=args.top_k,
    )
    print(f"Wrote {episodes} episode predictions to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
