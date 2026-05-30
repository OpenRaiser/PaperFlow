#!/usr/bin/env python3
"""Aggregate main-experiment human evaluation scores."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Dict, Iterable, List


HUMAN_DIMENSIONS = ["HumanRelevance", "HumanUsefulness", "DecisionHelpfulness"]


def read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: List[Dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0].keys()) if rows else []
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def parse_score(value: str, field: str, sample_id: str) -> float:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"Missing {field} for sample {sample_id}")
    score = float(text)
    if score < 1 or score > 5:
        raise ValueError(f"{field} for sample {sample_id} must be in [1, 5], got {score}")
    return score


def index_by_sample(rows: Iterable[Dict[str, str]]) -> Dict[str, Dict[str, str]]:
    return {str(row.get("sample_id")): row for row in rows if row.get("sample_id")}


def build_scored_papers(blind_rows: List[Dict[str, str]], key_rows: List[Dict[str, str]]) -> List[Dict[str, object]]:
    key_by_sample = index_by_sample(key_rows)
    scored: List[Dict[str, object]] = []
    for blind in blind_rows:
        sample_id = str(blind.get("sample_id") or "")
        key = key_by_sample.get(sample_id)
        if not key:
            raise ValueError(f"Missing key row for sample {sample_id}")
        dims = {field: parse_score(str(blind.get(field, "")), field, sample_id) for field in HUMAN_DIMENSIONS}
        human_eval = 20.0 * mean(dims.values())
        scored.append(
            {
                **key,
                **{field: f"{value:.4f}" for field, value in dims.items()},
                "HumanEval": f"{human_eval:.4f}",
                "comments": blind.get("comments", ""),
            }
        )
    return scored


def aggregate_episode_scores(scored_rows: List[Dict[str, object]]) -> List[Dict[str, object]]:
    buckets: Dict[tuple, List[Dict[str, object]]] = defaultdict(list)
    for row in scored_rows:
        buckets[(row["method_key"], row["episode_id"])].append(row)

    output: List[Dict[str, object]] = []
    for (method_key, episode_id), rows in sorted(buckets.items()):
        first = rows[0]
        output.append(
            {
                "method_key": method_key,
                "method_name": first["method_name"],
                "episode_id": episode_id,
                "user_id": first["user_id"],
                "date": first["date"],
                "n_papers": len(rows),
                "RecommendationScore": first["RecommendationScore"],
                "HumanRelevance": f"{mean(float(row['HumanRelevance']) for row in rows):.4f}",
                "HumanUsefulness": f"{mean(float(row['HumanUsefulness']) for row in rows):.4f}",
                "DecisionHelpfulness": f"{mean(float(row['DecisionHelpfulness']) for row in rows):.4f}",
                "HumanEval": f"{mean(float(row['HumanEval']) for row in rows):.4f}",
            }
        )
    return output


def aggregate_method_scores(episode_rows: List[Dict[str, object]]) -> List[Dict[str, object]]:
    buckets: Dict[str, List[Dict[str, object]]] = defaultdict(list)
    for row in episode_rows:
        buckets[str(row["method_key"])].append(row)

    output: List[Dict[str, object]] = []
    for method_key, rows in sorted(buckets.items()):
        first = rows[0]
        output.append(
            {
                "method_key": method_key,
                "method_name": first["method_name"],
                "n_episodes": len(rows),
                "RecommendationScore": f"{mean(float(row['RecommendationScore']) for row in rows):.4f}",
                "HumanRelevance": f"{mean(float(row['HumanRelevance']) for row in rows):.4f}",
                "HumanUsefulness": f"{mean(float(row['HumanUsefulness']) for row in rows):.4f}",
                "DecisionHelpfulness": f"{mean(float(row['DecisionHelpfulness']) for row in rows):.4f}",
                "HumanEval": f"{mean(float(row['HumanEval']) for row in rows):.4f}",
            }
        )
    output.sort(key=lambda row: float(row["HumanEval"]), reverse=True)
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aggregate main human evaluation annotations.")
    parser.add_argument("--blind-csv", required=True, help="Filled blind annotation CSV.")
    parser.add_argument("--key-csv", required=True, help="Internal key CSV generated with the packet.")
    parser.add_argument("--output-dir", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    scored_papers = build_scored_papers(read_csv(Path(args.blind_csv)), read_csv(Path(args.key_csv)))
    episode_scores = aggregate_episode_scores(scored_papers)
    method_scores = aggregate_method_scores(episode_scores)
    write_csv(output_dir / "main_human_eval_scored_papers.csv", scored_papers)
    write_csv(output_dir / "main_human_eval_episode_scores.csv", episode_scores)
    write_csv(output_dir / "main_human_eval_method_summary.csv", method_scores)
    print(f"Scored papers: {output_dir / 'main_human_eval_scored_papers.csv'}")
    print(f"Episode scores: {output_dir / 'main_human_eval_episode_scores.csv'}")
    print(f"Method summary: {output_dir / 'main_human_eval_method_summary.csv'}")


if __name__ == "__main__":
    main()
