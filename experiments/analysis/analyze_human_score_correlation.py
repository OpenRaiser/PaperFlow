#!/usr/bin/env python3
"""Analyze agreement between automatic overall scores and human scores."""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
from pathlib import Path
from typing import Dict, Iterable, List, Tuple


def read_scores(path: Path, auto_column: str, human_column: str) -> List[Tuple[float, float]]:
    rows: List[Tuple[float, float]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for item in reader:
            auto_raw = str(item.get(auto_column, "")).strip()
            human_raw = str(item.get(human_column, "")).strip()
            if not auto_raw or not human_raw:
                continue
            rows.append((float(auto_raw), float(human_raw)))
    return rows


def pearson(pairs: Iterable[Tuple[float, float]]) -> float:
    xs, ys = zip(*pairs)
    x_mean = sum(xs) / len(xs)
    y_mean = sum(ys) / len(ys)
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
    x_den = math.sqrt(sum((x - x_mean) ** 2 for x in xs))
    y_den = math.sqrt(sum((y - y_mean) ** 2 for y in ys))
    if x_den <= 0 or y_den <= 0:
        return 0.0
    return numerator / (x_den * y_den)


def ranks(values: List[float]) -> List[float]:
    indexed = sorted(enumerate(values), key=lambda item: item[1])
    result = [0.0] * len(values)
    i = 0
    while i < len(indexed):
        j = i
        while j + 1 < len(indexed) and indexed[j + 1][1] == indexed[i][1]:
            j += 1
        rank = (i + j + 2) / 2.0
        for k in range(i, j + 1):
            result[indexed[k][0]] = rank
        i = j + 1
    return result


def spearman(pairs: List[Tuple[float, float]]) -> float:
    xs, ys = zip(*pairs)
    ranked_pairs = list(zip(ranks(list(xs)), ranks(list(ys))))
    return pearson(ranked_pairs)


def kendall_tau(pairs: List[Tuple[float, float]]) -> float:
    concordant = 0
    discordant = 0
    for i in range(len(pairs)):
        for j in range(i + 1, len(pairs)):
            x_delta = pairs[i][0] - pairs[j][0]
            y_delta = pairs[i][1] - pairs[j][1]
            product = x_delta * y_delta
            if product > 0:
                concordant += 1
            elif product < 0:
                discordant += 1
    total = concordant + discordant
    if total <= 0:
        return 0.0
    return (concordant - discordant) / total


def bootstrap_ci(
    pairs: List[Tuple[float, float]],
    fn,
    *,
    iterations: int,
    seed: int,
) -> Dict[str, float]:
    rng = random.Random(seed)
    if not pairs or iterations <= 0:
        return {"low": 0.0, "high": 0.0}
    values = []
    for _ in range(iterations):
        sample = [pairs[rng.randrange(len(pairs))] for _ in pairs]
        values.append(fn(sample))
    values.sort()
    low_idx = max(0, int(0.025 * len(values)) - 1)
    high_idx = min(len(values) - 1, int(0.975 * len(values)))
    return {"low": values[low_idx], "high": values[high_idx]}


def build_result(pairs: List[Tuple[float, float]], bootstrap: int, seed: int) -> Dict[str, object]:
    result = {
        "n": len(pairs),
        "pearson": pearson(pairs),
        "spearman": spearman(pairs),
        "kendall_tau": kendall_tau(pairs),
    }
    if bootstrap > 0:
        result["bootstrap_ci"] = {
            "pearson": bootstrap_ci(pairs, pearson, iterations=bootstrap, seed=seed),
            "spearman": bootstrap_ci(pairs, spearman, iterations=bootstrap, seed=seed + 1),
            "kendall_tau": bootstrap_ci(pairs, kendall_tau, iterations=bootstrap, seed=seed + 2),
        }
    return result


def write_markdown(path: Path, result: Dict[str, object]) -> None:
    lines = [
        "| Statistic | Value |",
        "|---|---:|",
        f"| n | {result['n']} |",
        f"| Pearson r | {float(result['pearson']):.4f} |",
        f"| Spearman rho | {float(result['spearman']):.4f} |",
        f"| Kendall tau | {float(result['kendall_tau']):.4f} |",
    ]
    ci = result.get("bootstrap_ci")
    if isinstance(ci, dict):
        for key, label in (("pearson", "Pearson 95% CI"), ("spearman", "Spearman 95% CI"), ("kendall_tau", "Kendall 95% CI")):
            bounds = ci.get(key, {})
            if isinstance(bounds, dict):
                lines.append(f"| {label} | [{float(bounds['low']):.4f}, {float(bounds['high']):.4f}] |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Correlate automatic and human scores.")
    parser.add_argument("--input-csv", required=True, help="CSV containing automatic and human scores.")
    parser.add_argument("--auto-column", default="OverallScore", help="Automatic score column name.")
    parser.add_argument("--human-column", default="HumanScore", help="Human score column name.")
    parser.add_argument("--output-json", default=None, help="Optional JSON output path.")
    parser.add_argument("--output-md", default=None, help="Optional Markdown output path.")
    parser.add_argument("--bootstrap", type=int, default=1000, help="Bootstrap iterations for confidence intervals.")
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    pairs = read_scores(Path(args.input_csv), args.auto_column, args.human_column)
    if len(pairs) < 3:
        raise SystemExit("Need at least 3 paired scores for correlation analysis.")
    result = build_result(pairs, args.bootstrap, args.seed)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.output_json:
        Path(args.output_json).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.output_md:
        write_markdown(Path(args.output_md), result)


if __name__ == "__main__":
    main()

