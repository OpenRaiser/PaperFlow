"""Combine per-baseline ``evaluation_metrics.json`` outputs into one comparison table.

Both ``run_main_experiment.ps1`` and ``run_main_experiment.sh`` shell into
this helper so the markdown/csv output stays identical across platforms.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

METHODS = [
    ("Scholar Inbox Pipeline", "scholar_inbox"),
    ("Citation-Enhanced Literature Recommendation", "citation_enhanced"),
    ("Discourse-Aware Content Recommendation", "discourse_aware"),
    ("Natural-Language User Profile Recommendation", "nl_profile"),
    ("Knowledge-Entity Enhanced Recommendation", "knowledge_entity"),
    ("Full PaperFlow Pipeline", "full_paperflow"),
]

HEADERS = [
    "Method",
    "gNDCG@20 up",
    "Useful@5 up",
    "Useful@20 up",
    "Lift@20 up",
    "Strict R@20+ up",
    "MRR@20 up",
]


def fmt(value: Any) -> str:
    if value is None or value == "":
        return ""
    try:
        return f"{float(value):.4f}"
    except (TypeError, ValueError):
        return ""


def read_top20(metrics_file: Path) -> dict[str, Any] | None:
    if not metrics_file.exists() or metrics_file.stat().st_size == 0:
        return None
    payload = json.loads(metrics_file.read_text(encoding="utf-8"))
    summary = payload.get("summary", payload)
    case_per_k = summary.get("macro", {}).get("case_per_k", {})
    case5 = case_per_k.get("5") or case_per_k.get(5) or {}
    case20 = case_per_k.get("20") or case_per_k.get(20) or {}
    return {
        "gNDCG@20 up": case20.get("gndcg"),
        "Useful@5 up": case5.get("useful_rate"),
        "Useful@20 up": case20.get("useful_rate"),
        "Lift@20 up": case20.get("lift"),
        "Strict R@20+ up": case20.get("strict_recall_positive"),
        "MRR@20 up": case20.get("mrr"),
    }


def metrics_path(main_experiment_dir: Path, benchmark_dir: Path, key: str) -> Path:
    if key == "full_paperflow":
        return benchmark_dir / "evaluation_metrics.json"
    return main_experiment_dir / key / "evaluation_metrics.json"


def build_rows(main_experiment_dir: Path, benchmark_dir: Path) -> list[list[str]]:
    rows: list[list[str]] = []
    for name, key in METHODS:
        metrics = read_top20(metrics_path(main_experiment_dir, benchmark_dir, key))
        row = [name]
        for header in HEADERS[1:]:
            row.append(fmt(metrics.get(header)) if metrics else "")
        rows.append(row)
    return rows


def write_markdown(path: Path, rows: list[list[str]]) -> None:
    align = "|---|" + "|".join(["---:"] * (len(HEADERS) - 1)) + "|"
    lines = ["| " + " | ".join(HEADERS) + " |", align]
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(HEADERS)
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark-dir", type=Path, required=True)
    parser.add_argument("--main-experiment-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows = build_rows(args.main_experiment_dir, args.benchmark_dir)
    md_path = args.main_experiment_dir / "main_experiment_comparison_top20.md"
    csv_path = args.main_experiment_dir / "main_experiment_comparison_top20.csv"
    write_markdown(md_path, rows)
    write_csv(csv_path, rows)
    print(f"[combine] wrote {md_path}")
    print(f"[combine] wrote {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
