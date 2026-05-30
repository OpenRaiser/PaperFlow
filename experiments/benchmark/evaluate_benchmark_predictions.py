#!/usr/bin/env python3
"""Evaluate Top-20 recommendation predictions for PaperFlow-Bench."""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable


USEFUL_LABELS = {"strong_relevant", "relevant", "weak_relevant"}
STRICT_LABELS = {"strong_relevant", "relevant"}
GAIN_BY_LABEL = {
    "strong_relevant": 2.0,
    "relevant": 1.0,
    "weak_relevant": 0.5,
    "irrelevant": 0.0,
}


def iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def safe_div(num: float, den: float) -> float:
    return num / den if den > 0 else 0.0


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def mean_defined(values: list[float | None]) -> float:
    defined = [float(value) for value in values if value is not None]
    return mean(defined)


def dcg(items: list[Any], gain_fn: Callable[[Any], float]) -> float:
    score = 0.0
    for rank, item in enumerate(items, start=1):
        gain = float(gain_fn(item))
        if gain > 0:
            score += gain / math.log2(rank + 1)
    return score


def reciprocal_rank(items: list[Any], gain_fn: Callable[[Any], float]) -> float:
    for rank, item in enumerate(items, start=1):
        if gain_fn(item) > 0:
            return 1.0 / rank
    return 0.0


def label_gain(row: dict[str, Any] | None) -> float:
    if not row:
        return 0.0
    return GAIN_BY_LABEL.get(str(row.get("oracle_label") or "irrelevant"), 0.0)


def selected_gain(row: dict[str, Any] | None) -> float:
    return 1.0 if row and row.get("selected") else 0.0


def is_useful(row: dict[str, Any] | None) -> bool:
    return bool(row and str(row.get("oracle_label") or "") in USEFUL_LABELS)


def is_strict(row: dict[str, Any] | None) -> bool:
    return bool(row and str(row.get("oracle_label") or "") in STRICT_LABELS)


def resolve_labels_path(benchmark_dir: Path) -> Path:
    candidates = [
        benchmark_dir / "data" / "episode_labels.jsonl",
        benchmark_dir / "episode_labels.jsonl",
        benchmark_dir / "episode_papers.jsonl",
    ]
    for path in candidates:
        if path.exists():
            return path
    raise FileNotFoundError(f"Could not find labels in {benchmark_dir}")


def load_labels(benchmark_dir: Path) -> dict[str, dict[str, dict[str, Any]]]:
    labels_path = resolve_labels_path(benchmark_dir)
    episodes: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in iter_jsonl(labels_path):
        episode_id = str(row.get("episode_id") or "")
        paper_id = str(row.get("paper_id") or "")
        if not episode_id or not paper_id:
            continue
        episodes[episode_id][paper_id] = {
            "oracle_label": row.get("oracle_label", "irrelevant"),
            "oracle_score": row.get("oracle_score"),
            "selected": bool(row.get("selected")),
            "system_label": row.get("system_label"),
        }
    return dict(episodes)


def load_predictions(path: Path) -> dict[str, list[str]]:
    predictions: dict[str, list[str]] = {}
    for row in iter_jsonl(path):
        episode_id = str(row.get("episode_id") or "")
        paper_ids = row.get("paper_ids") or []
        if not episode_id:
            continue
        predictions[episode_id] = [str(paper_id) for paper_id in paper_ids][:20]
    return predictions


def evaluate_episode(
    label_rows: dict[str, dict[str, Any]],
    predicted_ids: list[str],
    k: int = 20,
) -> dict[str, float | None]:
    topk_rows = [label_rows.get(paper_id) for paper_id in predicted_ids[:k]]
    ideal_oracle = sorted(label_rows.values(), key=label_gain, reverse=True)[:k]
    # Match the paper's SelectedNDCG protocol: behavior alignment is normalized
    # within the submitted Top-20 list, not against every selected paper in the
    # full candidate pool.
    ideal_selected = sorted([row for row in topk_rows if row], key=selected_gain, reverse=True)[:k]

    useful_total = sum(1 for row in label_rows.values() if is_useful(row))
    strict_total = sum(1 for row in label_rows.values() if is_strict(row))
    pool_useful_rate = safe_div(useful_total, len(label_rows))

    useful_at_5 = sum(1 for row in topk_rows[:5] if is_useful(row))
    useful_at_20 = sum(1 for row in topk_rows[:20] if is_useful(row))
    strict_at_20 = sum(1 for row in topk_rows[:20] if is_strict(row))

    return {
        "gNDCG@20": safe_div(dcg(topk_rows[:20], label_gain), dcg(ideal_oracle, label_gain)),
        "Useful@5": safe_div(useful_at_5, 5),
        "Useful@20": safe_div(useful_at_20, 20),
        "SelectedNDCG@20": safe_div(dcg(topk_rows[:20], selected_gain), dcg(ideal_selected, selected_gain)),
        "StrictR@20+": safe_div(strict_at_20, strict_total) if strict_total > 0 else None,
        "MRR@20": reciprocal_rank(topk_rows[:20], label_gain),
        "Lift@20": safe_div(safe_div(useful_at_20, 20), pool_useful_rate) if pool_useful_rate > 0 else None,
    }


def recommendation_score(metrics: dict[str, float], lift_cap: float = 15.0) -> float:
    lift_score = min(metrics["Lift@20"] / max(lift_cap, 1e-9), 1.0)
    return 100.0 * (
        0.25 * metrics["gNDCG@20"]
        + 0.15 * metrics["Useful@5"]
        + 0.15 * metrics["Useful@20"]
        + 0.20 * metrics["StrictR@20+"]
        + 0.15 * metrics["MRR@20"]
        + 0.10 * lift_score
    )


def evaluate(benchmark_dir: Path, predictions_path: Path) -> dict[str, Any]:
    labels = load_labels(benchmark_dir)
    predictions = load_predictions(predictions_path)

    episode_metrics = []
    missing_predictions = 0
    for episode_id, label_rows in labels.items():
        predicted_ids = predictions.get(episode_id)
        if predicted_ids is None:
            missing_predictions += 1
            predicted_ids = []
        episode_metrics.append(evaluate_episode(label_rows, predicted_ids))

    summary = {
        "episodes": len(labels),
        "predicted_episodes": len(predictions),
        "missing_predictions": missing_predictions,
    }
    for metric in [
        "gNDCG@20",
        "Useful@5",
        "Useful@20",
        "SelectedNDCG@20",
        "StrictR@20+",
        "MRR@20",
        "Lift@20",
    ]:
        summary[metric] = mean_defined([row.get(metric) for row in episode_metrics])
    summary["RecommendationScore"] = recommendation_score(summary)
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark-dir", required=True, type=Path)
    parser.add_argument("--predictions", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    metrics = evaluate(args.benchmark_dir, args.predictions)
    text = json.dumps(metrics, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
