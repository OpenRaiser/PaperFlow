#!/usr/bin/env python3
"""Build main-experiment composite score tables from evaluation outputs."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, List


METHODS = [
    ("Scholar Inbox Pipeline", "main_experiment/scholar_inbox/evaluation_metrics.json"),
    ("Citation-Enhanced Literature Recommendation", "main_experiment/citation_enhanced/evaluation_metrics.json"),
    ("Discourse-Aware Content Recommendation", "main_experiment/discourse_aware/evaluation_metrics.json"),
    ("Natural-Language User Profile Recommendation", "main_experiment/nl_profile/evaluation_metrics.json"),
    ("Knowledge-Entity Enhanced Recommendation", "main_experiment/knowledge_entity/evaluation_metrics.json"),
    ("Full PaperFlow Pipeline", "evaluation_metrics.json"),
]


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def top20_metrics(metrics_path: Path) -> Dict[str, float]:
    payload = read_json(metrics_path)
    summary = payload.get("summary", payload)
    case_per_k = summary["macro"]["case_per_k"]
    case5 = case_per_k["5"]
    case20 = case_per_k["20"]
    return {
        "gNDCG@20": float(case20["gndcg"]),
        "Useful@5": float(case5["useful_rate"]),
        "Useful@20": float(case20["useful_rate"]),
        "Lift@20": float(case20["lift"]),
        "StrictR@20+": float(case20["strict_recall_positive"]),
        "MRR@20": float(case20["mrr"]),
    }


def recommendation_score(row: Dict[str, float], lift_cap: float) -> float:
    lift_score = min(row["Lift@20"] / max(lift_cap, 1e-9), 1.0)
    score = (
        0.25 * row["gNDCG@20"]
        + 0.15 * row["Useful@5"]
        + 0.15 * row["Useful@20"]
        + 0.20 * row["StrictR@20+"]
        + 0.15 * row["MRR@20"]
        + 0.10 * lift_score
    )
    return 100.0 * score


def format_float(value: float) -> str:
    return f"{value:.4f}"


def build_rows(benchmark_dir: Path, lift_cap: float) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for method, relative_path in METHODS:
        metrics_path = benchmark_dir / relative_path
        if not metrics_path.exists():
            continue
        metrics = top20_metrics(metrics_path)
        rows.append(
            {
                "Method": method,
                **metrics,
                "RecommendationScore": recommendation_score(metrics, lift_cap),
            }
        )
    rows.sort(key=lambda item: float(item["RecommendationScore"]), reverse=True)
    for rank, row in enumerate(rows, start=1):
        row["Rank"] = rank
    return rows


def write_markdown(path: Path, rows: List[Dict[str, Any]]) -> None:
    headers = [
        "Rank",
        "Method",
        "RecommendationScore",
        "gNDCG@20",
        "Useful@5",
        "Useful@20",
        "Lift@20",
        "StrictR@20+",
        "MRR@20",
    ]
    lines = [
        "| " + " | ".join(headers) + " |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        values = []
        for header in headers:
            value = row[header]
            values.append(str(value) if header in {"Rank", "Method"} else format_float(float(value)))
        lines.append("| " + " | ".join(values) + " |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    headers = [
        "Rank",
        "Method",
        "RecommendationScore",
        "gNDCG@20",
        "Useful@5",
        "Useful@20",
        "Lift@20",
        "StrictR@20+",
        "MRR@20",
    ]
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: row[key] if key in {"Rank", "Method"} else format_float(float(row[key]))
                    for key in headers
                }
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build main-experiment composite recommendation score table.")
    parser.add_argument(
        "--benchmark-dir",
        default="data/benchmark_full_24users_20260301_20260419_show20_with_reading",
        help="Frozen benchmark output directory.",
    )
    parser.add_argument("--lift-cap", type=float, default=15.0, help="Cap used to normalize Lift@20.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    benchmark_dir = Path(args.benchmark_dir)
    output_dir = benchmark_dir / "main_experiment"
    rows = build_rows(benchmark_dir, args.lift_cap)
    md_path = output_dir / "main_experiment_recommendation_score_table.md"
    csv_path = output_dir / "main_experiment_recommendation_score_table.csv"
    write_markdown(md_path, rows)
    write_csv(csv_path, rows)
    print(f"Wrote {md_path}")
    print(f"Wrote {csv_path}")


if __name__ == "__main__":
    main()

