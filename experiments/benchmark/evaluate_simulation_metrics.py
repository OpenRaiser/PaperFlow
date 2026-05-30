#!/usr/bin/env python3
"""
Evaluate simulation recommendation metrics from episode_papers.jsonl.
"""

import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List


RELEVANT_LABELS = {"strong_relevant", "relevant"}
USEFUL_LABELS = {"strong_relevant", "relevant", "weak_relevant"}
LOW_RELEVANCE_LABELS = {"irrelevant"}
GAIN_BY_LABEL = {
    "strong_relevant": 2.0,
    "relevant": 1.0,
    "weak_relevant": 0.5,
    "irrelevant": 0.0,
}
CATEGORY_KEYS = ("must_read", "high_relevant", "maybe_interested", "edge_relevant")
SYSTEM_HIGH_LABELS = {"must_read", "high_relevant"}
MAIN_EXPERIMENT_METHODS = (
    "Scholar Inbox Pipeline",
    "Citation-Enhanced Literature Recommendation",
    "Discourse-Aware Content Recommendation",
    "Natural-Language User Profile Recommendation",
    "Knowledge-Entity Enhanced Recommendation",
    "Full PaperFlow Pipeline",
)


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            payload = json.loads(line)
            if isinstance(payload, dict):
                rows.append(payload)
    return rows


def oracle_gain(row: Dict[str, Any]) -> float:
    return GAIN_BY_LABEL.get(str(row.get("oracle_label") or "irrelevant"), 0.0)


def is_oracle_useful(row: Dict[str, Any]) -> bool:
    return str(row.get("oracle_label") or "") in USEFUL_LABELS


def is_oracle_strict_relevant(row: Dict[str, Any]) -> bool:
    return str(row.get("oracle_label") or "") in RELEVANT_LABELS


def selected_gain(row: Dict[str, Any]) -> float:
    return 1.0 if row.get("selected") else 0.0


def is_low_relevance(row: Dict[str, Any]) -> bool:
    """Common low-relevance marker for fixed-budget push quality."""
    oracle_label = row.get("oracle_label")
    if oracle_label is not None:
        return str(oracle_label or "irrelevant") in LOW_RELEVANCE_LABELS
    if str(row.get("system_label") or "") == "edge_relevant":
        return True
    relevance_signal = row.get("relevance_signal")
    if relevance_signal is not None:
        try:
            return float(relevance_signal) < 0.08
        except (TypeError, ValueError):
            return False
    return False


def is_system_high(row: Dict[str, Any]) -> bool:
    return str(row.get("system_label") or "") in SYSTEM_HIGH_LABELS


def dcg(rows: List[Dict[str, Any]], gain_fn) -> float:
    score = 0.0
    for idx, row in enumerate(rows, start=1):
        gain = float(gain_fn(row))
        if gain <= 0:
            continue
        score += gain / math.log2(idx + 1)
    return score


def reciprocal_rank(rows: List[Dict[str, Any]], gain_fn, k: int) -> float:
    for idx, row in enumerate(rows[: min(k, len(rows))], start=1):
        if float(gain_fn(row)) > 0:
            return 1.0 / idx
    return 0.0


def safe_div(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def mean(values: List[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def mean_defined(values: List[Any]) -> float:
    defined = [float(value) for value in values if value is not None]
    return mean(defined)


def evaluate_episode(rows: List[Dict[str, Any]], ks: List[int]) -> Dict[str, Any]:
    pool_rows = list(rows)
    shown_rows = [row for row in pool_rows if row.get("shown")]
    shown_rows.sort(key=lambda row: int(row.get("system_rank") or 10**9))

    selected_total = sum(1 for row in pool_rows if row.get("selected"))
    oracle_relevant_total = sum(1 for row in pool_rows if is_oracle_strict_relevant(row))
    oracle_useful_total = sum(1 for row in pool_rows if is_oracle_useful(row))
    pool_useful_rate = safe_div(oracle_useful_total, len(pool_rows))
    selected_ideal_rows = sorted(
        shown_rows,
        key=selected_gain,
        reverse=True,
    )
    oracle_ideal_rows = sorted(
        pool_rows,
        key=oracle_gain,
        reverse=True,
    )

    metrics: Dict[str, Any] = {
        "metric_basis": "selected",
        "pool_size": len(pool_rows),
        "shown_size": len(shown_rows),
        "selected_total": selected_total,
        "relevant_total": selected_total,
        "oracle_relevant_total": oracle_relevant_total,
        "oracle_useful_total": oracle_useful_total,
        "pool_useful_rate": pool_useful_rate,
        "per_k": {},
        "oracle_per_k": {},
        "case_per_k": {},
        "selection_rate": {},
    }

    for k in ks:
        topk = shown_rows[: min(k, len(shown_rows))]
        selected_at_k = sum(1 for row in topk if row.get("selected"))
        low_relevance_at_k = sum(1 for row in topk if is_low_relevance(row))
        system_high_at_k = sum(1 for row in topk if is_system_high(row))
        selected_ideal_topk = selected_ideal_rows[: min(k, len(selected_ideal_rows))]
        selected_ndcg = safe_div(dcg(topk, selected_gain), dcg(selected_ideal_topk, selected_gain))
        metrics["per_k"][str(k)] = {
            "precision": safe_div(selected_at_k, k),
            "recall": safe_div(selected_at_k, selected_total),
            "ndcg": selected_ndcg,
            "mrr": reciprocal_rank(shown_rows, selected_gain, k),
            "low_relevance_rate": safe_div(low_relevance_at_k, k),
        }

        oracle_retrieved_relevant = sum(1 for row in topk if is_oracle_strict_relevant(row))
        oracle_retrieved_useful = sum(1 for row in topk if is_oracle_useful(row))
        oracle_ideal_topk = oracle_ideal_rows[: min(k, len(oracle_ideal_rows))]
        oracle_ndcg = safe_div(dcg(topk, oracle_gain), dcg(oracle_ideal_topk, oracle_gain))
        useful_rate = safe_div(oracle_retrieved_useful, k)
        strict_recall = (
            safe_div(oracle_retrieved_relevant, oracle_relevant_total)
            if oracle_relevant_total > 0
            else None
        )
        metrics["oracle_per_k"][str(k)] = {
            "precision": safe_div(oracle_retrieved_relevant, k),
            "recall": safe_div(oracle_retrieved_relevant, oracle_relevant_total),
            "ndcg": oracle_ndcg,
            "mrr": reciprocal_rank(shown_rows, oracle_gain, k),
        }
        metrics["case_per_k"][str(k)] = {
            "gndcg": oracle_ndcg,
            "useful_rate": useful_rate,
            "lift": safe_div(useful_rate, pool_useful_rate) if pool_useful_rate > 0 else None,
            "strict_recall_positive": strict_recall,
            "mrr": reciprocal_rank(shown_rows, oracle_gain, k),
            "low_relevance_rate": safe_div(low_relevance_at_k, k),
            "system_high_rate": safe_div(system_high_at_k, k),
        }

    for category in CATEGORY_KEYS:
        category_rows = [row for row in shown_rows if str(row.get("system_label") or "") == category]
        selected_count = sum(1 for row in category_rows if row.get("selected"))
        metrics["selection_rate"][category] = {
            "selected": selected_count,
            "shown": len(category_rows),
            "rate": safe_div(selected_count, len(category_rows)),
        }

    return metrics


def aggregate_metrics(episodes: Dict[str, Dict[str, Any]], ks: List[int]) -> Dict[str, Any]:
    summary: Dict[str, Any] = {
        "episodes": len(episodes),
        "metric_basis": "episode_macro",
        "macro": {"per_k": {}, "oracle_per_k": {}, "case_per_k": {}, "selection_rate": {}},
    }
    if not episodes:
        return summary

    for k in ks:
        precision_values = [episode["per_k"][str(k)]["precision"] for episode in episodes.values()]
        recall_values = [episode["per_k"][str(k)]["recall"] for episode in episodes.values()]
        ndcg_values = [episode["per_k"][str(k)]["ndcg"] for episode in episodes.values()]
        mrr_values = [episode["per_k"][str(k)]["mrr"] for episode in episodes.values()]
        low_relevance_values = [episode["per_k"][str(k)]["low_relevance_rate"] for episode in episodes.values()]
        summary["macro"]["per_k"][str(k)] = {
            "precision": mean(precision_values),
            "recall": mean(recall_values),
            "ndcg": mean(ndcg_values),
            "mrr": mean(mrr_values),
            "low_relevance_rate": mean(low_relevance_values),
        }
        oracle_precision_values = [episode["oracle_per_k"][str(k)]["precision"] for episode in episodes.values()]
        oracle_recall_values = [episode["oracle_per_k"][str(k)]["recall"] for episode in episodes.values()]
        oracle_ndcg_values = [episode["oracle_per_k"][str(k)]["ndcg"] for episode in episodes.values()]
        oracle_mrr_values = [episode["oracle_per_k"][str(k)]["mrr"] for episode in episodes.values()]
        summary["macro"]["oracle_per_k"][str(k)] = {
            "precision": mean(oracle_precision_values),
            "recall": mean(oracle_recall_values),
            "ndcg": mean(oracle_ndcg_values),
            "mrr": mean(oracle_mrr_values),
        }
        case_values = [episode["case_per_k"][str(k)] for episode in episodes.values()]
        defined_lift = [value["lift"] for value in case_values if value.get("lift") is not None]
        defined_strict_recall = [
            value["strict_recall_positive"]
            for value in case_values
            if value.get("strict_recall_positive") is not None
        ]
        summary["macro"]["case_per_k"][str(k)] = {
            "gndcg": mean([value["gndcg"] for value in case_values]),
            "useful_rate": mean([value["useful_rate"] for value in case_values]),
            "lift": mean_defined([value.get("lift") for value in case_values]),
            "lift_support_episodes": len(defined_lift),
            "strict_recall_positive": mean_defined(
                [value.get("strict_recall_positive") for value in case_values]
            ),
            "strict_recall_support_episodes": len(defined_strict_recall),
            "mrr": mean([value["mrr"] for value in case_values]),
            "low_relevance_rate": mean([value["low_relevance_rate"] for value in case_values]),
            "system_high_rate": mean([value["system_high_rate"] for value in case_values]),
        }

    for category in CATEGORY_KEYS:
        selected = sum(episode["selection_rate"][category]["selected"] for episode in episodes.values())
        shown = sum(episode["selection_rate"][category]["shown"] for episode in episodes.values())
        summary["macro"]["selection_rate"][category] = {
            "selected": selected,
            "shown": shown,
            "rate": safe_div(selected, shown),
        }

    return summary


def format_metric(value: Any) -> str:
    if value is None:
        return ""
    return f"{float(value):.4f}"


def build_selected_legacy_table(summary: Dict[str, Any], method_name: str) -> str:
    per_k = ((summary.get("macro") or {}).get("per_k") or {})
    method_values = {
        "P@5 ↑": (per_k.get("5") or {}).get("precision"),
        "P@10 ↑": (per_k.get("10") or {}).get("precision"),
        "P@20 ↑": (per_k.get("20") or {}).get("precision"),
        "R@20 ↑": (per_k.get("20") or {}).get("recall"),
        "NDCG@20 ↑": (per_k.get("20") or {}).get("ndcg"),
        "MRR@20 ↑": (per_k.get("20") or {}).get("mrr"),
        "LowRel@20 ↓": (per_k.get("20") or {}).get("low_relevance_rate"),
    }
    headers = ["Method", *method_values.keys()]
    lines = [
        "| " + " | ".join(headers) + " |",
        "|---" + "|---:" * (len(headers) - 1) + "|",
    ]
    methods = list(MAIN_EXPERIMENT_METHODS)
    if method_name not in methods:
        methods.append(method_name)
    for method in methods:
        if method == method_name:
            values = [format_metric(method_values[header]) for header in headers[1:]]
        else:
            values = [""] * (len(headers) - 1)
        lines.append("| " + " | ".join([method, *values]) + " |")
    return "\n".join(lines) + "\n"


def _case_metric_values(summary: Dict[str, Any]) -> Dict[str, Any]:
    case_per_k = ((summary.get("macro") or {}).get("case_per_k") or {})
    return {
        "gNDCG@20 up": (case_per_k.get("20") or {}).get("gndcg"),
        "Useful@5 up": (case_per_k.get("5") or {}).get("useful_rate"),
        "Useful@20 up": (case_per_k.get("20") or {}).get("useful_rate"),
        "Lift@20 up": (case_per_k.get("20") or {}).get("lift"),
        "Strict R@20+ up": (case_per_k.get("20") or {}).get("strict_recall_positive"),
        "MRR@20 up": (case_per_k.get("20") or {}).get("mrr"),
    }


def build_case_metrics_table(summary: Dict[str, Any], method_name: str) -> str:
    method_values = _case_metric_values(summary)
    headers = ["Method", *method_values.keys()]
    values = [format_metric(method_values[header]) for header in headers[1:]]
    lines = [
        "| " + " | ".join(headers) + " |",
        "|---" + "|---:" * (len(headers) - 1) + "|",
        "| " + " | ".join([method_name, *values]) + " |",
    ]
    return "\n".join(lines) + "\n"


def build_main_experiment_table(summary: Dict[str, Any], method_name: str) -> str:
    method_values = _case_metric_values(summary)
    headers = ["Method", *method_values.keys()]
    lines = [
        "| " + " | ".join(headers) + " |",
        "|---" + "|---:" * (len(headers) - 1) + "|",
    ]
    methods = list(MAIN_EXPERIMENT_METHODS)
    if method_name not in methods:
        methods.append(method_name)
    for method in methods:
        if method == method_name:
            values = [format_metric(method_values[header]) for header in headers[1:]]
        else:
            values = [""] * (len(headers) - 1)
        lines.append("| " + " | ".join([method, *values]) + " |")
    return "\n".join(lines) + "\n"


def _counter_to_dict(counter: Counter) -> Dict[str, int]:
    return {str(key): int(value) for key, value in sorted(counter.items(), key=lambda item: str(item[0]))}


def _distribution(values: List[Any]) -> Dict[str, int]:
    return _counter_to_dict(Counter(str(value) for value in values))


def build_dataset_summary(paper_rows: List[Dict[str, Any]], episode_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    grouped_papers: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in paper_rows:
        episode_id = str(row.get("episode_id") or "")
        if episode_id:
            grouped_papers[episode_id].append(row)

    pool_sizes: List[int] = []
    shown_sizes: List[int] = []
    selected_sizes_from_papers: List[int] = []
    pool_useful_rates: List[float] = []
    shown_useful_rates: List[float] = []
    positive_strict_episodes = 0
    positive_useful_episodes = 0

    for rows in grouped_papers.values():
        pool_size = len(rows)
        shown_rows = [row for row in rows if row.get("shown")]
        selected_rows = [row for row in rows if row.get("selected")]
        pool_useful = sum(1 for row in rows if is_oracle_useful(row))
        pool_strict = sum(1 for row in rows if is_oracle_strict_relevant(row))
        shown_useful = sum(1 for row in shown_rows if is_oracle_useful(row))

        pool_sizes.append(pool_size)
        shown_sizes.append(len(shown_rows))
        selected_sizes_from_papers.append(len(selected_rows))
        pool_useful_rates.append(safe_div(pool_useful, pool_size))
        shown_useful_rates.append(safe_div(shown_useful, len(shown_rows)))
        if pool_strict > 0:
            positive_strict_episodes += 1
        if pool_useful > 0:
            positive_useful_episodes += 1

    selected_sizes_from_episodes = [
        int(row.get("selected_papers") or 0)
        for row in episode_rows
        if row.get("selected_papers") is not None
    ]

    summary = {
        "episodes": len(grouped_papers),
        "episode_rows": len(episode_rows),
        "paper_rows": len(paper_rows),
        "avg_pool_size": mean(pool_sizes),
        "avg_shown_size": mean(shown_sizes),
        "avg_selected_papers": mean(selected_sizes_from_episodes or selected_sizes_from_papers),
        "avg_pool_useful_rate": mean(pool_useful_rates),
        "avg_shown_useful_rate": mean(shown_useful_rates),
        "positive_strict_episodes": positive_strict_episodes,
        "positive_useful_episodes": positive_useful_episodes,
        "pool_size_distribution": _distribution(pool_sizes),
        "shown_size_distribution": _distribution(shown_sizes),
        "selected_size_distribution": _distribution(selected_sizes_from_episodes or selected_sizes_from_papers),
        "pool_oracle_label_counts": _counter_to_dict(
            Counter(str(row.get("oracle_label") or "missing") for row in paper_rows)
        ),
        "shown_oracle_label_counts": _counter_to_dict(
            Counter(str(row.get("oracle_label") or "missing") for row in paper_rows if row.get("shown"))
        ),
        "selected_oracle_label_counts": _counter_to_dict(
            Counter(str(row.get("oracle_label") or "missing") for row in paper_rows if row.get("selected"))
        ),
        "pool_system_label_counts": _counter_to_dict(
            Counter(str(row.get("system_label") or "missing") for row in paper_rows)
        ),
        "shown_system_label_counts": _counter_to_dict(
            Counter(str(row.get("system_label") or "missing") for row in paper_rows if row.get("shown"))
        ),
        "availability_counts": _counter_to_dict(
            Counter(str(row.get("daily_availability_type") or "missing") for row in episode_rows)
        ),
        "drift_status_counts": _counter_to_dict(
            Counter(str(row.get("drift_status") or "missing") for row in episode_rows)
        ),
    }
    return summary


def build_dataset_summary_markdown(summary: Dict[str, Any]) -> str:
    label_keys = ["strong_relevant", "relevant", "weak_relevant", "irrelevant"]
    pool_labels = summary.get("pool_oracle_label_counts") or {}
    shown_labels = summary.get("shown_oracle_label_counts") or {}
    selected_labels = summary.get("selected_oracle_label_counts") or {}

    lines = [
        "| Check | Value |",
        "|---|---:|",
        f"| Episodes | {summary.get('episodes', 0)} |",
        f"| Avg pool size | {float(summary.get('avg_pool_size') or 0.0):.2f} |",
        f"| Avg shown size | {float(summary.get('avg_shown_size') or 0.0):.2f} |",
        f"| Avg selected papers | {float(summary.get('avg_selected_papers') or 0.0):.2f} |",
        f"| Avg pool useful rate | {float(summary.get('avg_pool_useful_rate') or 0.0):.4f} |",
        f"| Avg shown useful rate | {float(summary.get('avg_shown_useful_rate') or 0.0):.4f} |",
        f"| Strict-positive episodes | {summary.get('positive_strict_episodes', 0)} |",
        f"| Useful-positive episodes | {summary.get('positive_useful_episodes', 0)} |",
        "",
        "| Oracle label | Pool | Top-20 | Selected |",
        "|---|---:|---:|---:|",
    ]
    for label in label_keys:
        lines.append(
            f"| {label} | {pool_labels.get(label, 0)} | {shown_labels.get(label, 0)} | {selected_labels.get(label, 0)} |"
        )

    lines.extend(
        [
            "",
            "| Distribution | Counts |",
            "|---|---|",
            f"| Availability | {json.dumps(summary.get('availability_counts') or {}, ensure_ascii=False)} |",
            f"| Selected papers | {json.dumps(summary.get('selected_size_distribution') or {}, ensure_ascii=False)} |",
            f"| Shown size | {json.dumps(summary.get('shown_size_distribution') or {}, ensure_ascii=False)} |",
            f"| Drift status | {json.dumps(summary.get('drift_status_counts') or {}, ensure_ascii=False)} |",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate simulation metrics from episode_papers.jsonl")
    parser.add_argument("--input-dir", type=str, required=True, help="Simulation output directory")
    parser.add_argument("--ks", nargs="*", type=int, default=[5, 10, 20], help="K values for ranking metrics")
    parser.add_argument("--start-date", type=str, default=None, help="Optional YYYY-MM-DD start date filter")
    parser.add_argument("--end-date", type=str, default=None, help="Optional YYYY-MM-DD end date filter")
    parser.add_argument(
        "--output-file",
        type=str,
        default=None,
        help="Optional output JSON path. Defaults to <input-dir>/evaluation_metrics.json",
    )
    parser.add_argument(
        "--method-name",
        type=str,
        default="Full PaperFlow Pipeline",
        help="Method row to fill when writing the main experiment markdown table",
    )
    parser.add_argument(
        "--markdown-table-file",
        type=str,
        default=None,
        help="Optional markdown table path. Defaults to <input-dir>/main_experiment_table_top20.md",
    )
    parser.add_argument(
        "--case-table-file",
        type=str,
        default=None,
        help="Optional one-row case table path. Defaults to <input-dir>/case_metrics_table_top20.md",
    )
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    rows = load_jsonl(input_dir / "episode_papers.jsonl")
    episode_rows = load_jsonl(input_dir / "episodes.jsonl")
    if args.start_date:
        rows = [row for row in rows if str(row.get("date") or "") >= args.start_date]
        episode_rows = [row for row in episode_rows if str(row.get("date") or "") >= args.start_date]
    if args.end_date:
        rows = [row for row in rows if str(row.get("date") or "") <= args.end_date]
        episode_rows = [row for row in episode_rows if str(row.get("date") or "") <= args.end_date]

    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("episode_id") or "")].append(row)

    episode_metrics = {
        episode_id: evaluate_episode(episode_rows, args.ks)
        for episode_id, episode_rows in grouped.items()
        if episode_id
    }
    summary = aggregate_metrics(episode_metrics, args.ks)
    dataset_summary = build_dataset_summary(rows, episode_rows)
    result = {
        "summary": summary,
        "dataset_summary": dataset_summary,
        "episodes": episode_metrics,
    }

    output_file = Path(args.output_file) if args.output_file else (input_dir / "evaluation_metrics.json")
    output_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    dataset_summary_file = input_dir / "dataset_summary.json"
    dataset_summary_file.write_text(json.dumps(dataset_summary, ensure_ascii=False, indent=2), encoding="utf-8")
    dataset_summary_table_file = input_dir / "dataset_summary.md"
    dataset_summary_table = build_dataset_summary_markdown(dataset_summary)
    dataset_summary_table_file.write_text(dataset_summary_table, encoding="utf-8")
    table_file = Path(args.markdown_table_file) if args.markdown_table_file else (input_dir / "main_experiment_table_top20.md")
    table = build_main_experiment_table(summary, args.method_name)
    table_file.write_text(table, encoding="utf-8")
    case_table_file = Path(args.case_table_file) if args.case_table_file else (input_dir / "case_metrics_table_top20.md")
    case_table = build_case_metrics_table(summary, args.method_name)
    case_table_file.write_text(case_table, encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\nDataset summary written to: {dataset_summary_table_file}")
    print(dataset_summary_table)
    print(f"\nMarkdown table written to: {table_file}")
    print(table)
    print(f"Case table written to: {case_table_file}")
    print(case_table)


if __name__ == "__main__":
    main()
