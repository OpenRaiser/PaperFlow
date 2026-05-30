#!/usr/bin/env python3
"""
Export a balanced human-audit subset from simulation episode_papers.jsonl.
"""

import argparse
import csv
import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List


AUDIT_FIELDS = [
    "episode_id",
    "user_id",
    "role_name",
    "date",
    "paper_id",
    "pool_rank",
    "system_rank",
    "shown",
    "selected",
    "oracle_label",
    "oracle_score",
    "system_label",
    "system_score",
    "title",
    "abstract",
    "authors",
    "url",
    "human_label",
    "human_notes",
]


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            payload = json.loads(line)
            if isinstance(payload, dict):
                rows.append(payload)
    return rows


def truncate(value: Any, limit: int) -> str:
    text = json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else str(value or "")
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)] + "..."


def balanced_sample(rows: List[Dict[str, Any]], sample_size: int, seed: int) -> List[Dict[str, Any]]:
    rng = random.Random(seed)
    strata: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        label = str(row.get("oracle_label") or "missing")
        shown_key = "shown" if row.get("shown") else "pool"
        strata[f"{shown_key}:{label}"].append(row)

    for bucket in strata.values():
        rng.shuffle(bucket)

    selected: List[Dict[str, Any]] = []
    strata_keys = sorted(strata)
    if not strata_keys or sample_size <= 0:
        return selected

    per_stratum = max(1, sample_size // len(strata_keys))
    selected_ids = set()

    for key in strata_keys:
        for row in strata[key][:per_stratum]:
            row_id = (row.get("episode_id"), row.get("paper_id"), row.get("title"))
            if row_id not in selected_ids:
                selected.append(row)
                selected_ids.add(row_id)
            if len(selected) >= sample_size:
                return selected

    leftovers = []
    for key in strata_keys:
        leftovers.extend(strata[key][per_stratum:])
    rng.shuffle(leftovers)
    for row in leftovers:
        row_id = (row.get("episode_id"), row.get("paper_id"), row.get("title"))
        if row_id in selected_ids:
            continue
        selected.append(row)
        selected_ids.add(row_id)
        if len(selected) >= sample_size:
            break

    return selected


def normalize_for_audit(row: Dict[str, Any], abstract_chars: int) -> Dict[str, Any]:
    return {
        "episode_id": row.get("episode_id"),
        "user_id": row.get("user_id"),
        "role_name": row.get("role_name"),
        "date": row.get("date"),
        "paper_id": row.get("paper_id"),
        "pool_rank": row.get("pool_rank"),
        "system_rank": row.get("system_rank"),
        "shown": bool(row.get("shown")),
        "selected": bool(row.get("selected")),
        "oracle_label": row.get("oracle_label"),
        "oracle_score": row.get("oracle_score"),
        "system_label": row.get("system_label"),
        "system_score": row.get("system_score"),
        "title": truncate(row.get("title"), 500),
        "abstract": truncate(row.get("abstract"), abstract_chars),
        "authors": truncate(row.get("authors"), 500),
        "url": truncate(row.get("url"), 500),
        "human_label": "",
        "human_notes": "",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Export a balanced human-audit subset from simulation outputs.")
    parser.add_argument("--input-dir", required=True, help="Simulation output directory")
    parser.add_argument("--output-file", default=None, help="Output CSV path. Defaults to <input-dir>/human_audit_subset.csv")
    parser.add_argument("--sample-size", type=int, default=200, help="Maximum audit rows to export")
    parser.add_argument("--seed", type=int, default=42, help="Sampling seed")
    parser.add_argument("--start-date", default=None, help="Optional YYYY-MM-DD start date")
    parser.add_argument("--end-date", default=None, help="Optional YYYY-MM-DD end date")
    parser.add_argument("--shown-only", action="store_true", help="Sample only Top-20 shown papers")
    parser.add_argument("--abstract-chars", type=int, default=1200, help="Maximum abstract characters in the CSV")
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    rows = load_jsonl(input_dir / "episode_papers.jsonl")
    if args.start_date:
        rows = [row for row in rows if str(row.get("date") or "") >= args.start_date]
    if args.end_date:
        rows = [row for row in rows if str(row.get("date") or "") <= args.end_date]
    if args.shown_only:
        rows = [row for row in rows if row.get("shown")]

    sampled = balanced_sample(rows, args.sample_size, args.seed)
    output_file = Path(args.output_file) if args.output_file else input_dir / "human_audit_subset.csv"
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with output_file.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=AUDIT_FIELDS)
        writer.writeheader()
        for row in sampled:
            writer.writerow(normalize_for_audit(row, args.abstract_chars))

    print(f"Human audit subset written to: {output_file}")
    print(f"Rows exported: {len(sampled)}")


if __name__ == "__main__":
    main()
