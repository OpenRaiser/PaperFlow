#!/usr/bin/env python3
"""Aggregate drift-adaptation human evaluation scores."""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from experiments.human_eval import aggregate_main_human_eval as common


DRIFT_DIMS = ["NewTopicFit", "AdaptationAppropriateness", "OldNewBalance", "DriftDecisionHelpfulness"]


def drift_auto_proxy(row: Dict[str, object]) -> float:
    """Sample-level automatic drift proxy for correlation QA.

    The formal table-level drift metrics remain in drift_adaptation_experiment.*.
    This proxy is only used to align sampled human ratings with automatic
    evidence available for each hidden sample.
    """
    new_topic = str(row.get("new_topic_match")).lower() == "true"
    old_topic = str(row.get("old_topic_match")).lower() == "true"
    selected = str(row.get("selected")).lower() == "true"
    try:
        rank = int(float(str(row.get("system_rank") or "20")))
    except ValueError:
        rank = 20
    rank_score = max(0.0, min(1.0, 1.0 - (rank - 1) / 19.0))
    return 100.0 * (0.40 * float(new_topic) + 0.25 * float(not old_topic) + 0.20 * float(selected) + 0.15 * rank_score)


def build_scored_rows(blind_rows: List[Dict[str, str]], key_rows: List[Dict[str, str]]) -> List[Dict[str, object]]:
    key_by_sample = common.index_by_sample(key_rows)
    scored: List[Dict[str, object]] = []
    for blind in blind_rows:
        sample_id = str(blind.get("sample_id") or "")
        key = key_by_sample.get(sample_id)
        if not key:
            raise ValueError(f"Missing key row for sample {sample_id}")
        dims = {field: common.parse_score(str(blind.get(field, "")), field, sample_id) for field in DRIFT_DIMS}
        adaptation = 20.0 * mean(dims.values())
        merged = {
            **key,
            **{field: f"{value:.4f}" for field, value in dims.items()},
            "AdaptationHumanScore": f"{adaptation:.4f}",
            "comments": blind.get("comments", ""),
        }
        merged["DriftAutoScore"] = f"{drift_auto_proxy(merged):.4f}"
        scored.append(merged)
    return scored


def aggregate_event_scores(scored_rows: List[Dict[str, object]]) -> List[Dict[str, object]]:
    buckets: Dict[tuple, List[Dict[str, object]]] = defaultdict(list)
    for row in scored_rows:
        buckets[(row["method_key"], row["event_user_id"], row["event_date"])].append(row)

    output: List[Dict[str, object]] = []
    for (method_key, event_user_id, event_date), rows in sorted(buckets.items()):
        first = rows[0]
        output.append(
            {
                "method_key": method_key,
                "method_name": first["method_name"],
                "event_user_id": event_user_id,
                "event_date": event_date,
                "n_papers": len(rows),
                "DriftAutoScore": f"{mean(float(row['DriftAutoScore']) for row in rows):.4f}",
                "NewTopicFit": f"{mean(float(row['NewTopicFit']) for row in rows):.4f}",
                "AdaptationAppropriateness": f"{mean(float(row['AdaptationAppropriateness']) for row in rows):.4f}",
                "OldNewBalance": f"{mean(float(row['OldNewBalance']) for row in rows):.4f}",
                "DriftDecisionHelpfulness": f"{mean(float(row['DriftDecisionHelpfulness']) for row in rows):.4f}",
                "AdaptationHumanScore": f"{mean(float(row['AdaptationHumanScore']) for row in rows):.4f}",
            }
        )
    return output


def aggregate_method_scores(event_rows: List[Dict[str, object]]) -> List[Dict[str, object]]:
    buckets: Dict[str, List[Dict[str, object]]] = defaultdict(list)
    for row in event_rows:
        buckets[str(row["method_key"])].append(row)

    output: List[Dict[str, object]] = []
    for method_key, rows in sorted(buckets.items()):
        first = rows[0]
        output.append(
            {
                "method_key": method_key,
                "method_name": first["method_name"],
                "n_events": len(rows),
                "DriftAutoScore": f"{mean(float(row['DriftAutoScore']) for row in rows):.4f}",
                "AdaptationHumanScore": f"{mean(float(row['AdaptationHumanScore']) for row in rows):.4f}",
                "NewTopicFit": f"{mean(float(row['NewTopicFit']) for row in rows):.4f}",
                "AdaptationAppropriateness": f"{mean(float(row['AdaptationAppropriateness']) for row in rows):.4f}",
                "OldNewBalance": f"{mean(float(row['OldNewBalance']) for row in rows):.4f}",
                "DriftDecisionHelpfulness": f"{mean(float(row['DriftDecisionHelpfulness']) for row in rows):.4f}",
            }
        )
    output.sort(key=lambda row: float(row["AdaptationHumanScore"]), reverse=True)
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aggregate drift human evaluation annotations.")
    parser.add_argument("--blind-csv", required=True)
    parser.add_argument("--key-csv", required=True)
    parser.add_argument("--output-dir", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    scored = build_scored_rows(common.read_csv(Path(args.blind_csv)), common.read_csv(Path(args.key_csv)))
    event_scores = aggregate_event_scores(scored)
    method_scores = aggregate_method_scores(event_scores)
    common.write_csv(output_dir / "drift_human_eval_scored_papers.csv", scored)
    common.write_csv(output_dir / "drift_human_eval_event_scores.csv", event_scores)
    common.write_csv(output_dir / "drift_human_eval_method_summary.csv", method_scores)
    print(f"Scored papers: {output_dir / 'drift_human_eval_scored_papers.csv'}")
    print(f"Event scores: {output_dir / 'drift_human_eval_event_scores.csv'}")
    print(f"Method summary: {output_dir / 'drift_human_eval_method_summary.csv'}")


if __name__ == "__main__":
    main()
