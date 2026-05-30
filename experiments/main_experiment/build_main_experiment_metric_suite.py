#!/usr/bin/env python3
"""Export every currently computable main-experiment metric.

This script does not launch new model runs. It only reads existing
`evaluation_metrics.json`, `episodes.jsonl`, `episode_papers.jsonl`,
`reading_reports.jsonl`, and the daily token log, then writes supplemental
tables for the main experiment.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from experiments.main_experiment.build_main_experiment_extended_table import (
    KNOWN_METHODS,
    as_float,
    build_rows as build_extended_rows,
    format_cell,
    iter_jsonl,
    read_json,
    recommendation_score,
)


KS = (5, 10, 20)
CASE_METRICS = ("gndcg", "useful_rate", "lift", "strict_recall_positive", "mrr", "low_relevance_rate", "system_high_rate")
SELECTED_METRICS = ("precision", "recall", "ndcg", "mrr", "low_relevance_rate")
ORACLE_METRICS = ("precision", "recall", "ndcg", "mrr")
SOURCE_KEYS = ("arxiv", "openreview", "journal")


def safe_div(numerator: float, denominator: float) -> Optional[float]:
    if denominator == 0:
        return None
    return numerator / denominator


def mean(values: Sequence[float]) -> Optional[float]:
    clean = [float(value) for value in values if math.isfinite(float(value))]
    if not clean:
        return None
    return sum(clean) / len(clean)


def stddev(values: Sequence[float]) -> Optional[float]:
    clean = [float(value) for value in values if math.isfinite(float(value))]
    if len(clean) <= 1:
        return 0.0 if clean else None
    avg = sum(clean) / len(clean)
    return math.sqrt(sum((value - avg) ** 2 for value in clean) / len(clean))


def entropy(counts: Counter[str]) -> Optional[float]:
    total = sum(counts.values())
    if total <= 0:
        return None
    score = 0.0
    for count in counts.values():
        if count <= 0:
            continue
        p = count / total
        score -= p * math.log(p, 2)
    return score


def method_catalog(benchmark_dir: Path) -> List[Dict[str, Any]]:
    known_paths = {row["MetricsPath"] for row in KNOWN_METHODS}
    rows = [dict(row) for row in KNOWN_METHODS]
    main_dir = benchmark_dir / "main_experiment"
    if not main_dir.exists():
        return rows

    for metrics_path in sorted(main_dir.glob("*/evaluation_metrics.json")):
        relative = metrics_path.relative_to(benchmark_dir).as_posix()
        if relative in known_paths:
            continue
        method_dir = metrics_path.parent
        rows.append(
            {
                "Group": "Model Variant" if "model" in method_dir.name.lower() else "Extra",
                "Method": method_dir.name.replace("_", " ").title(),
                "MetricsPath": relative,
                "OutputPath": method_dir.relative_to(benchmark_dir).as_posix(),
                "Status": "complete",
            }
        )
    return rows


def metric_path_exists(benchmark_dir: Path, method: Dict[str, Any]) -> bool:
    return (benchmark_dir / str(method["MetricsPath"])).exists()


def output_dir_for(benchmark_dir: Path, method: Dict[str, Any]) -> Path:
    return benchmark_dir / str(method.get("OutputPath") or "")


def flatten_eval_metrics(summary: Dict[str, Any], lift_cap: float) -> Dict[str, Any]:
    macro = summary.get("macro") or {}
    case_per_k = macro.get("case_per_k") or {}
    selected_per_k = macro.get("per_k") or {}
    oracle_per_k = macro.get("oracle_per_k") or {}
    selection_rate = macro.get("selection_rate") or {}

    row: Dict[str, Any] = {
        "Episodes": summary.get("episodes"),
        "RecommendationScore": None,
    }
    case20 = case_per_k.get("20") or {}
    case5 = case_per_k.get("5") or {}
    if case20 and case5:
        metrics = {
            "gNDCG@20": float(case20.get("gndcg") or 0.0),
            "Useful@5": float(case5.get("useful_rate") or 0.0),
            "Useful@20": float(case20.get("useful_rate") or 0.0),
            "Lift@20": float(case20.get("lift") or 0.0),
            "StrictR@20+": float(case20.get("strict_recall_positive") or 0.0),
            "MRR@20": float(case20.get("mrr") or 0.0),
        }
        row.update(metrics)
        row["RecommendationScore"] = recommendation_score(metrics, lift_cap)

    for k in KS:
        selected = selected_per_k.get(str(k)) or {}
        oracle = oracle_per_k.get(str(k)) or {}
        case = case_per_k.get(str(k)) or {}
        for metric in SELECTED_METRICS:
            row[f"Selected.{metric}@{k}"] = selected.get(metric)
        for metric in ORACLE_METRICS:
            row[f"Oracle.{metric}@{k}"] = oracle.get(metric)
        for metric in CASE_METRICS:
            row[f"Case.{metric}@{k}"] = case.get(metric)
        row[f"Case.lift_support@{k}"] = case.get("lift_support_episodes")
        row[f"Case.strict_support@{k}"] = case.get("strict_recall_support_episodes")

    for category in ("must_read", "high_relevant", "maybe_interested", "edge_relevant"):
        category_payload = selection_rate.get(category) or {}
        label = category.replace("_", "")
        row[f"SelectRate.{label}"] = category_payload.get("rate")
        row[f"SelectShown.{label}"] = category_payload.get("shown")
        row[f"SelectCount.{label}"] = category_payload.get("selected")
    return row


def load_method_eval(benchmark_dir: Path, method: Dict[str, Any]) -> Dict[str, Any]:
    metrics_path = benchmark_dir / str(method["MetricsPath"])
    if not metrics_path.exists():
        return {}
    payload = read_json(metrics_path)
    return payload if isinstance(payload, dict) else {}


def dataset_summary_metrics(payload: Dict[str, Any]) -> Dict[str, Any]:
    dataset = payload.get("dataset_summary") or {}
    if not dataset:
        return {}
    return {
        "EpisodeRows": dataset.get("episode_rows"),
        "PaperRows": dataset.get("paper_rows"),
        "AvgPoolSize": dataset.get("avg_pool_size"),
        "AvgShownSize": dataset.get("avg_shown_size"),
        "AvgSelectedPapers": dataset.get("avg_selected_papers"),
        "AvgPoolUsefulRate": dataset.get("avg_pool_useful_rate"),
        "AvgShownUsefulRate": dataset.get("avg_shown_useful_rate"),
        "StrictPositiveEpisodes": dataset.get("positive_strict_episodes"),
        "UsefulPositiveEpisodes": dataset.get("positive_useful_episodes"),
    }


def read_episode_metadata(output_dir: Path) -> Dict[str, Dict[str, Any]]:
    path = output_dir / "episodes.jsonl"
    metadata: Dict[str, Dict[str, Any]] = {}
    if not path.exists():
        return metadata
    for row in iter_jsonl(path):
        episode_id = str(row.get("episode_id") or "")
        if episode_id:
            metadata[episode_id] = row
    return metadata


def split_eval_by_metadata(
    eval_payload: Dict[str, Any],
    output_dir: Path,
    fallback_metadata: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    episodes = eval_payload.get("episodes") or {}
    metadata = read_episode_metadata(output_dir)
    if not episodes or not metadata:
        return {}

    by_status: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    by_user_g: Dict[str, List[float]] = defaultdict(list)
    by_user_useful: Dict[str, List[float]] = defaultdict(list)
    by_date_g: Dict[str, List[float]] = defaultdict(list)
    by_date_useful: Dict[str, List[float]] = defaultdict(list)
    drift_detected = 0

    for episode_id, metrics in episodes.items():
        meta = dict((fallback_metadata or {}).get(str(episode_id)) or {})
        meta.update(metadata.get(str(episode_id)) or {})
        status = str(meta.get("drift_status") or "missing")
        user_id = str(meta.get("user_id") or str(episode_id).split("::", 1)[0])
        date = str(meta.get("date") or "")
        if meta.get("drift_detected"):
            drift_detected += 1
        case20 = ((metrics.get("case_per_k") or {}).get("20") or {})
        gndcg = as_float(case20.get("gndcg"))
        useful = as_float(case20.get("useful_rate"))
        if gndcg is None or useful is None:
            continue
        by_status[status].append({"gndcg": gndcg, "useful": useful})
        by_user_g[user_id].append(gndcg)
        by_user_useful[user_id].append(useful)
        if date:
            by_date_g[date].append(gndcg)
            by_date_useful[date].append(useful)

    def group_mean(status_names: Sequence[str], metric: str) -> Optional[float]:
        values: List[float] = []
        for status_name in status_names:
            values.extend(float(row[metric]) for row in by_status.get(status_name, []))
        return mean(values)

    stable_g = group_mean(["stable"], "gndcg")
    active_g = group_mean(["observing", "shifting", "recovering"], "gndcg")
    stable_useful = group_mean(["stable"], "useful")
    active_useful = group_mean(["observing", "shifting", "recovering"], "useful")
    user_g_means = [mean(values) for values in by_user_g.values()]
    user_useful_means = [mean(values) for values in by_user_useful.values()]
    day_g_means = [mean(values) for values in by_date_g.values()]
    day_useful_means = [mean(values) for values in by_date_useful.values()]

    user_g_clean = [float(value) for value in user_g_means if value is not None]
    user_useful_clean = [float(value) for value in user_useful_means if value is not None]
    day_g_clean = [float(value) for value in day_g_means if value is not None]
    day_useful_clean = [float(value) for value in day_useful_means if value is not None]

    total_episodes = len(episodes)
    return {
        "DriftDetectedRate": safe_div(drift_detected, total_episodes),
        "StableEpisodes": len(by_status.get("stable", [])),
        "ActiveDriftEpisodes": sum(len(by_status.get(name, [])) for name in ("observing", "shifting", "recovering")),
        "StableG@20": stable_g,
        "ActiveDriftG@20": active_g,
        "DriftGGap@20": active_g - stable_g if active_g is not None and stable_g is not None else None,
        "StableUseful@20": stable_useful,
        "ActiveDriftUseful@20": active_useful,
        "DriftUsefulGap@20": active_useful - stable_useful if active_useful is not None and stable_useful is not None else None,
        "WorstUserG@20": min(user_g_clean) if user_g_clean else None,
        "UserGStd@20": stddev(user_g_clean),
        "WorstUserUseful@20": min(user_useful_clean) if user_useful_clean else None,
        "UserUsefulStd@20": stddev(user_useful_clean),
        "DayGStd@20": stddev(day_g_clean),
        "DayUsefulStd@20": stddev(day_useful_clean),
    }


def source_and_signal_metrics(output_dir: Path) -> Dict[str, Any]:
    path = output_dir / "episode_papers.jsonl"
    if not path.exists():
        return {}

    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in iter_jsonl(path):
        if row.get("shown"):
            grouped[str(row.get("episode_id") or "")].append(row)
    if not grouped:
        return {}

    source_entropy_values: List[float] = []
    unique_sources: List[int] = []
    source_counts: Counter[str] = Counter()
    shown_count = 0
    fallback_count = 0
    fallback_known = 0
    drift_bonus_count = 0
    reading_signal_count = 0
    oracle_anchor_count = 0
    suppressed_count = 0
    drift_bonus_values: List[float] = []
    reading_signal_values: List[float] = []
    select_probability_values: List[float] = []
    selected_probability_values: List[float] = []

    for rows in grouped.values():
        rows = sorted(rows, key=lambda item: int(item.get("system_rank") or 10**9))[:20]
        per_episode_sources = Counter(str(row.get("source") or "missing") for row in rows)
        source_entropy = entropy(per_episode_sources)
        if source_entropy is not None:
            source_entropy_values.append(source_entropy)
        unique_sources.append(len(per_episode_sources))

        for row in rows:
            shown_count += 1
            source_counts[str(row.get("source") or "missing")] += 1
            if "ranking_fallback" in row:
                fallback_known += 1
                fallback_count += 1 if row.get("ranking_fallback") else 0
            drift_bonus = as_float(row.get("drift_bonus"), 0.0) or 0.0
            reading_bonus = as_float(row.get("reading_signal_bonus"), 0.0) or 0.0
            drift_bonus_values.append(drift_bonus)
            reading_signal_values.append(reading_bonus)
            if drift_bonus > 0:
                drift_bonus_count += 1
            if reading_bonus > 0:
                reading_signal_count += 1
            if row.get("oracle_anchor_match"):
                oracle_anchor_count += 1
            if row.get("oracle_suppressed_hit"):
                suppressed_count += 1
            select_probability = as_float(row.get("select_probability"))
            if select_probability is not None:
                select_probability_values.append(select_probability)
                if row.get("selected"):
                    selected_probability_values.append(select_probability)

    result: Dict[str, Any] = {
        "ShownRows": shown_count,
        "SourceEntropy@20": mean(source_entropy_values),
        "UniqueSources@20": mean(unique_sources),
        "RankingFallbackRate@20": safe_div(fallback_count, fallback_known) if fallback_known else None,
        "DriftBonusRate@20": safe_div(drift_bonus_count, shown_count),
        "ReadingSignalRate@20": safe_div(reading_signal_count, shown_count),
        "AvgDriftBonus@20": mean(drift_bonus_values),
        "AvgReadingSignalBonus@20": mean(reading_signal_values),
        "OracleAnchorMatchRate@20": safe_div(oracle_anchor_count, shown_count),
        "OracleSuppressedHitRate@20": safe_div(suppressed_count, shown_count),
        "AvgSelectProbability@20": mean(select_probability_values),
        "AvgSelectedProbability": mean(selected_probability_values),
    }
    for source in SOURCE_KEYS:
        result[f"{source.title()}Share@20"] = safe_div(source_counts.get(source, 0), shown_count)
    return result


def build_recommendation_rows(benchmark_dir: Path, lift_cap: float) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for method in method_catalog(benchmark_dir):
        if not metric_path_exists(benchmark_dir, method):
            continue
        payload = load_method_eval(benchmark_dir, method)
        summary = payload.get("summary") or payload
        row = {
            "Group": method["Group"],
            "Method": method["Method"],
            "Status": "complete",
        }
        row.update(flatten_eval_metrics(summary, lift_cap))
        row.update(dataset_summary_metrics(payload))
        rows.append(row)
    rows.sort(key=lambda row: -(as_float(row.get("RecommendationScore"), -1.0) or -1.0))
    for rank, row in enumerate(rows, start=1):
        row["Rank"] = rank
    return rows


def build_behavior_rows(benchmark_dir: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    fallback_metadata = read_episode_metadata(benchmark_dir)
    for method in method_catalog(benchmark_dir):
        if not metric_path_exists(benchmark_dir, method):
            continue
        output_dir = output_dir_for(benchmark_dir, method)
        payload = load_method_eval(benchmark_dir, method)
        row = {
            "Group": method["Group"],
            "Method": method["Method"],
            "Status": "complete",
        }
        row.update(dataset_summary_metrics(payload))
        row.update(split_eval_by_metadata(payload, output_dir, fallback_metadata))
        row.update(source_and_signal_metrics(output_dir))
        rows.append(row)
    group_order = {
        "Full System": 0,
        "Model Variant": 1,
        "External Baseline": 2,
        "Ablation": 3,
        "Extra": 4,
    }
    rows.sort(
        key=lambda row: (
            group_order.get(str(row.get("Group") or ""), 9),
            -(as_float(row.get("AvgShownUsefulRate"), -1.0) or -1.0),
            str(row.get("Method") or ""),
        )
    )
    for rank, row in enumerate(rows, start=1):
        row["Rank"] = rank
    return rows


def compact_recommendation_headers() -> List[str]:
    return [
        "Rank",
        "Group",
        "Method",
        "RecommendationScore",
        "gNDCG@20",
        "Useful@5",
        "Useful@20",
        "Lift@20",
        "StrictR@20+",
        "MRR@20",
        "Selected.precision@5",
        "Selected.precision@20",
        "Selected.recall@20",
        "Selected.ndcg@20",
        "Oracle.precision@20",
        "Oracle.recall@20",
        "Oracle.ndcg@20",
        "Case.low_relevance_rate@20",
        "Case.system_high_rate@20",
        "SelectRate.mustread",
        "SelectRate.highrelevant",
        "SelectRate.maybeinterested",
        "SelectRate.edgerelevant",
    ]


def all_recommendation_headers(rows: List[Dict[str, Any]]) -> List[str]:
    priority = compact_recommendation_headers()
    keys = sorted({key for row in rows for key in row.keys()})
    return priority + [key for key in keys if key not in priority]


def behavior_headers() -> List[str]:
    return [
        "Rank",
        "Group",
        "Method",
        "EpisodeRows",
        "PaperRows",
        "AvgPoolSize",
        "AvgShownSize",
        "AvgSelectedPapers",
        "AvgPoolUsefulRate",
        "AvgShownUsefulRate",
        "StrictPositiveEpisodes",
        "UsefulPositiveEpisodes",
        "DriftDetectedRate",
        "StableEpisodes",
        "ActiveDriftEpisodes",
        "StableG@20",
        "ActiveDriftG@20",
        "DriftGGap@20",
        "StableUseful@20",
        "ActiveDriftUseful@20",
        "DriftUsefulGap@20",
        "WorstUserG@20",
        "UserGStd@20",
        "WorstUserUseful@20",
        "UserUsefulStd@20",
        "DayGStd@20",
        "DayUsefulStd@20",
        "SourceEntropy@20",
        "UniqueSources@20",
        "ArxivShare@20",
        "OpenreviewShare@20",
        "JournalShare@20",
        "RankingFallbackRate@20",
        "DriftBonusRate@20",
        "ReadingSignalRate@20",
        "AvgDriftBonus@20",
        "AvgReadingSignalBonus@20",
        "OracleAnchorMatchRate@20",
        "OracleSuppressedHitRate@20",
        "AvgSelectProbability@20",
        "AvgSelectedProbability",
    ]


def report_efficiency_headers() -> List[str]:
    return [
        "Rank",
        "Group",
        "Method",
        "Status",
        "RecommendationScore",
        "ReportCoverage",
        "ReportSuccessRate",
        "FullTextSourceRate",
        "ReportEvidenceRate",
        "ReportStructureScore",
        "AvgReportChars",
        "ReportProxyScore",
        "TotalTokens",
        "CostUSDProxy",
        "CallsPerEpisode",
        "CostScore",
        "LatencyProxyScore",
        "CostEfficiencyScore",
        "OverallScore",
        "OverallScoreSource",
    ]


def write_csv(path: Path, rows: List[Dict[str, Any]], headers: List[str]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({header: format_cell(row.get(header), header) for header in headers})


def write_markdown(path: Path, rows: List[Dict[str, Any]], headers: List[str]) -> None:
    lines = [
        "| " + " | ".join(headers) + " |",
        "|"
        + "|".join("---" if header in {"Group", "Method", "Status", "OverallScoreSource"} else "---:" for header in headers)
        + "|",
    ]
    for row in rows:
        lines.append("| " + " | ".join(format_cell(row.get(header), header) for header in headers) + " |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_metric_index(path: Path) -> None:
    text = """# Main-Experiment Metric Suite

These tables are computed from existing frozen outputs only; no new model run is launched.

## Recommendation Metrics

- Selected-behavior metrics: `Selected.precision@K`, `Selected.recall@K`, `Selected.ndcg@K`, `Selected.mrr@K`.
- Oracle metrics: `Oracle.precision@K`, `Oracle.recall@K`, `Oracle.ndcg@K`, `Oracle.mrr@K`.
- Case metrics: `Case.gndcg@K`, `Case.useful_rate@K`, `Case.lift@K`, `Case.strict_recall_positive@K`, `Case.mrr@K`, `Case.low_relevance_rate@K`, `Case.system_high_rate@K`.
- Label response metrics: `SelectRate.mustread`, `SelectRate.highrelevant`, `SelectRate.maybeinterested`, `SelectRate.edgerelevant`.

## Behavior / Drift / Robustness Metrics

- Dataset behavior: episode count, paper rows, average pool size, average shown size, average selected papers.
- Pool difficulty: average pool useful rate, average shown useful rate, strict/useful-positive episode counts.
- Drift split: stable vs active-drift episode count, `StableG@20`, `ActiveDriftG@20`, `StableUseful@20`, `ActiveDriftUseful@20`.
- Robustness/fairness: worst-user score, user-level standard deviation, day-level standard deviation.
- Source/signal diagnostics: source entropy, source shares, fallback rate, drift-bonus rate, reading-signal rate.

## Report / Cost / Overall Metrics

- Report metrics: coverage, success, full-text source rate, evidence rate, structure score, average report length.
- Cost/efficiency: total tokens, cost proxy, calls per episode, normalized cost score, latency proxy score.
- Overall score: recommendation + report proxy + cost efficiency. Baselines without reports keep report/cost fields as `N/A`.
"""
    path.write_text(text, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build all currently computable main-experiment metric tables.")
    parser.add_argument(
        "--benchmark-dir",
        default="data/benchmark_full_24users_20260301_20260419_show20_with_reading",
        help="Frozen benchmark output directory.",
    )
    parser.add_argument("--token-log", default="data/token_usage.jsonl", help="Daily aggregate token log.")
    parser.add_argument("--lift-cap", type=float, default=15.0, help="Cap used to normalize Lift@20.")
    parser.add_argument("--llm-output-share", type=float, default=0.30, help="Assumed output-token share for cost proxy.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    benchmark_dir = Path(args.benchmark_dir)
    output_dir = benchmark_dir / "main_experiment"
    output_dir.mkdir(parents=True, exist_ok=True)

    recommendation_rows = build_recommendation_rows(benchmark_dir, args.lift_cap)
    behavior_rows = build_behavior_rows(benchmark_dir)
    extended_rows = build_extended_rows(
        benchmark_dir=benchmark_dir,
        token_log_path=Path(args.token_log),
        lift_cap=args.lift_cap,
        llm_output_share=args.llm_output_share,
    )

    recommendation_full_headers = all_recommendation_headers(recommendation_rows)
    recommendation_compact_headers = compact_recommendation_headers()
    behavior_table_headers = behavior_headers()
    report_headers = report_efficiency_headers()

    write_csv(output_dir / "main_experiment_recommendation_all_metrics.csv", recommendation_rows, recommendation_full_headers)
    write_markdown(
        output_dir / "main_experiment_recommendation_core_metrics.md",
        recommendation_rows,
        recommendation_compact_headers,
    )
    write_csv(output_dir / "main_experiment_recommendation_core_metrics.csv", recommendation_rows, recommendation_compact_headers)

    write_csv(output_dir / "main_experiment_behavior_drift_metrics.csv", behavior_rows, behavior_table_headers)
    write_markdown(output_dir / "main_experiment_behavior_drift_metrics.md", behavior_rows, behavior_table_headers)

    write_csv(output_dir / "main_experiment_report_efficiency_metrics.csv", extended_rows, report_headers)
    write_markdown(output_dir / "main_experiment_report_efficiency_metrics.md", extended_rows, report_headers)

    write_metric_index(output_dir / "main_experiment_metric_suite_index.md")

    print(f"Wrote metric suite to {output_dir}")
    print(f"Recommendation rows: {len(recommendation_rows)}")
    print(f"Behavior/drift rows: {len(behavior_rows)}")
    print(f"Report/efficiency rows: {len(extended_rows)}")


if __name__ == "__main__":
    main()
