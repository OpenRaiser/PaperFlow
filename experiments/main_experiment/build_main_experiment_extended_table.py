#!/usr/bin/env python3
"""Build the extended main-experiment metrics table.

The recommendation-only table stays focused on ranking metrics. This script
adds system-level metrics that are only available for end-to-end PaperFlow runs:
reading-report coverage, report-completeness proxies, token/cost proxies, and
an overall score that can later be compared against human ratings.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


KNOWN_METHODS: List[Dict[str, Any]] = [
    {
        "Group": "Full System",
        "Method": "Full PaperFlow Pipeline",
        "MetricsPath": "evaluation_metrics.json",
        "OutputPath": ".",
        "Status": "complete",
    },
    {
        "Group": "External Baseline",
        "Method": "Scholar Inbox Pipeline",
        "MetricsPath": "main_experiment/scholar_inbox/evaluation_metrics.json",
        "OutputPath": "main_experiment/scholar_inbox",
        "Status": "complete",
    },
    {
        "Group": "External Baseline",
        "Method": "Citation-Enhanced Literature Recommendation",
        "MetricsPath": "main_experiment/citation_enhanced/evaluation_metrics.json",
        "OutputPath": "main_experiment/citation_enhanced",
        "Status": "complete",
    },
    {
        "Group": "External Baseline",
        "Method": "Discourse-Aware Content Recommendation",
        "MetricsPath": "main_experiment/discourse_aware/evaluation_metrics.json",
        "OutputPath": "main_experiment/discourse_aware",
        "Status": "complete",
    },
    {
        "Group": "External Baseline",
        "Method": "Natural-Language User Profile Recommendation",
        "MetricsPath": "main_experiment/nl_profile/evaluation_metrics.json",
        "OutputPath": "main_experiment/nl_profile",
        "Status": "complete",
    },
    {
        "Group": "External Baseline",
        "Method": "Knowledge-Entity Enhanced Recommendation",
        "MetricsPath": "main_experiment/knowledge_entity/evaluation_metrics.json",
        "OutputPath": "main_experiment/knowledge_entity",
        "Status": "complete",
    },
    {
        "Group": "Ablation",
        "Method": "PaperFlow No Drift Ablation",
        "MetricsPath": "main_experiment/paperflow_no_drift/evaluation_metrics.json",
        "OutputPath": "main_experiment/paperflow_no_drift",
        "Status": "planned",
    },
    {
        "Group": "Ablation",
        "Method": "PaperFlow No Reading Signal Ablation",
        "MetricsPath": "main_experiment/paperflow_no_reading_signal/evaluation_metrics.json",
        "OutputPath": "main_experiment/paperflow_no_reading_signal",
        "Status": "planned",
    },
    {
        "Group": "Ablation",
        "Method": "PaperFlow No Explicit Preference Matching Ablation",
        "MetricsPath": "main_experiment/paperflow_no_explicit_preference/evaluation_metrics.json",
        "OutputPath": "main_experiment/paperflow_no_explicit_preference",
        "Status": "planned",
    },
]


MODEL_PRICES_PER_1K = {
    "qwen3.5-plus": {"input": 0.002, "output": 0.006},
    "qwen3-plus": {"input": 0.002, "output": 0.006},
    "qwen-max": {"input": 0.04, "output": 0.12},
    "qwen-plus": {"input": 0.001, "output": 0.003},
    "gemini-3-flash-preview": {"input": 0.000075, "output": 0.0003},
    "gemini-2.0-flash": {"input": 0.000075, "output": 0.0003},
    "Qwen/Qwen3-Embedding-8B": {"input": 0.0007, "output": 0.0},
    "Qwen/Qwen3-Embedding-0.6B": {"input": 0.0007, "output": 0.0},
    "gpt-4o": {"input": 0.005, "output": 0.015},
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
}


RECOMMENDATION_HEADERS = [
    "gNDCG@20",
    "Useful@5",
    "Useful@20",
    "Lift@20",
    "StrictR@20+",
    "MRR@20",
]

OUTPUT_HEADERS = [
    "Rank",
    "Group",
    "Method",
    "Status",
    "RecommendationScore",
    *RECOMMENDATION_HEADERS,
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


def read_json(path: Path) -> Dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def iter_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                yield payload


def as_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None:
            return default
        result = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(result):
        return default
    return result


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


def recommendation_score(metrics: Dict[str, float], lift_cap: float) -> float:
    lift_score = min(metrics["Lift@20"] / max(lift_cap, 1e-9), 1.0)
    return 100.0 * (
        0.25 * metrics["gNDCG@20"]
        + 0.15 * metrics["Useful@5"]
        + 0.15 * metrics["Useful@20"]
        + 0.20 * metrics["StrictR@20+"]
        + 0.15 * metrics["MRR@20"]
        + 0.10 * lift_score
    )


def selected_report_key(user_id: str, paper_id: Any, title: Any) -> Optional[Tuple[str, str, str]]:
    if paper_id not in (None, ""):
        return (user_id, "paper", str(paper_id))
    title_key = " ".join(str(title or "").strip().lower().split())
    if title_key:
        return (user_id, "title", title_key)
    return None


def length_fit_score(char_count: int) -> float:
    if char_count <= 0:
        return 0.0
    if char_count < 2000:
        return 0.25 + 0.50 * (char_count / 2000)
    if char_count < 8000:
        return 0.75 + 0.25 * ((char_count - 2000) / 6000)
    if char_count <= 22000:
        return 1.0
    if char_count >= 40000:
        return 0.80
    return 1.0 - 0.20 * ((char_count - 22000) / 18000)


def report_stats(output_dir: Path) -> Dict[str, Any]:
    reports_path = output_dir / "reading_reports.jsonl"
    episodes_path = output_dir / "episodes.jsonl"
    if not reports_path.exists() or not episodes_path.exists():
        return {}

    expected_keys = set()
    episode_count = 0
    dates: List[str] = []
    selected_total = 0
    for episode in iter_jsonl(episodes_path):
        episode_count += 1
        date = str(episode.get("date") or "")
        if date:
            dates.append(date)
        user_id = str(episode.get("user_id") or "")
        ids = episode.get("selected_paper_ids") or []
        titles = episode.get("selected_paper_titles") or []
        selected_total += int(episode.get("selected_papers") or len(ids) or 0)
        for index, paper_id in enumerate(ids):
            title = titles[index] if index < len(titles) else ""
            key = selected_report_key(user_id, paper_id, title)
            if key:
                expected_keys.add(key)

    report_count = 0
    nonempty_count = 0
    full_text_count = 0
    evidence_count = 0
    structure_scores: List[float] = []
    length_scores: List[float] = []
    char_counts: List[int] = []
    estimated_minutes: List[float] = []
    source_counts: Counter[str] = Counter()
    label_counts: Counter[str] = Counter()

    required_fields = [
        "one_sentence_summary",
        "research_background",
        "main_contributions",
        "core_method",
        "key_results",
        "limitations",
        "relevance_points",
        "reading_focus",
        "recommendation_label",
        "estimated_reading_minutes",
    ]

    for report in iter_jsonl(reports_path):
        report_count += 1
        content = str(report.get("report_content") or "").strip()
        char_count = len(content)
        char_counts.append(char_count)
        length_scores.append(length_fit_score(char_count))
        if content:
            nonempty_count += 1

        source = str(report.get("analysis_source") or "unknown").strip() or "unknown"
        source_counts[source] += 1
        if source in {"pdf", "full_text"} and not report.get("pdf_error"):
            full_text_count += 1

        payload = report.get("report_payload") or {}
        retrieved_evidence = payload.get("retrieved_evidence") or []
        evidence_anchors = payload.get("report_evidence_anchors") or []
        if retrieved_evidence or evidence_anchors:
            evidence_count += 1

        filled = 0
        for field in required_fields:
            value = payload.get(field)
            if isinstance(value, (list, dict)):
                filled += 1 if value else 0
            else:
                filled += 1 if str(value or "").strip() else 0
        structure_scores.append(filled / len(required_fields))

        minutes = as_float(payload.get("estimated_reading_minutes"))
        if minutes is not None:
            estimated_minutes.append(minutes)
        label_counts[str(payload.get("recommendation_label") or "unknown")] += 1

    expected_count = len(expected_keys) or selected_total
    report_coverage = report_count / expected_count if expected_count else None
    report_success = nonempty_count / expected_count if expected_count else None
    full_text_rate = full_text_count / report_count if report_count else None
    evidence_rate = evidence_count / report_count if report_count else None
    structure_score = sum(structure_scores) / len(structure_scores) if structure_scores else None
    avg_length_score = sum(length_scores) / len(length_scores) if length_scores else None
    avg_chars = sum(char_counts) / len(char_counts) if char_counts else None

    proxy_components = [
        (0.30, report_coverage),
        (0.20, full_text_rate),
        (0.20, evidence_rate),
        (0.20, structure_score),
        (0.10, avg_length_score),
    ]
    if all(value is not None for _, value in proxy_components):
        report_proxy_score = 100.0 * sum(weight * float(value) for weight, value in proxy_components)
    else:
        report_proxy_score = None

    return {
        "Episodes": episode_count,
        "DateStart": min(dates) if dates else None,
        "DateEnd": max(dates) if dates else None,
        "SelectedReportsExpected": expected_count,
        "ReportCount": report_count,
        "ReportCoverage": report_coverage,
        "ReportSuccessRate": report_success,
        "FullTextSourceRate": full_text_rate,
        "ReportEvidenceRate": evidence_rate,
        "ReportStructureScore": structure_score,
        "AvgReportChars": avg_chars,
        "AvgEstimatedReadingMinutes": (
            sum(estimated_minutes) / len(estimated_minutes) if estimated_minutes else None
        ),
        "ReportProxyScore": report_proxy_score,
        "ReportSourceCounts": dict(source_counts),
        "ReportLabelCounts": dict(label_counts),
    }


def date_range_from_episodes(output_dir: Path) -> Tuple[Optional[str], Optional[str], int]:
    episodes_path = output_dir / "episodes.jsonl"
    if not episodes_path.exists():
        return None, None, 0
    dates: List[str] = []
    count = 0
    for episode in iter_jsonl(episodes_path):
        count += 1
        date = str(episode.get("date") or "")
        if date:
            dates.append(date)
    return (min(dates) if dates else None, max(dates) if dates else None, count)


def read_token_log_usage(token_log_path: Path, start_date: str, end_date: str) -> Dict[str, Any]:
    if not token_log_path.exists():
        return {}
    embedding_tokens = 0
    llm_tokens = 0
    total_tokens = 0
    call_count = 0
    days = 0
    for row in iter_jsonl(token_log_path):
        date = str(row.get("date") or "")
        if not (start_date <= date <= end_date):
            continue
        days += 1
        embedding_tokens += int(row.get("embedding_tokens") or 0)
        llm_tokens += int(row.get("llm_tokens") or 0)
        total_tokens += int(row.get("total_tokens") or 0)
        call_count += int(row.get("call_count") or 0)
    if days == 0:
        return {}
    return {
        "EmbeddingTokens": embedding_tokens,
        "LLMTokens": llm_tokens,
        "TotalTokens": total_tokens,
        "CallCount": call_count,
        "TokenScope": f"token_log:{start_date}..{end_date}",
    }


def read_summary_usage(output_dir: Path) -> Dict[str, Any]:
    summary_path = output_dir / "simulation_summary.json"
    if not summary_path.exists():
        return {}
    summary = read_json(summary_path)
    token_usage = summary.get("token_usage") or {}
    if not token_usage:
        return {}
    return {
        "EmbeddingTokens": int(token_usage.get("embedding_tokens") or 0),
        "LLMTokens": int(token_usage.get("llm_tokens") or 0),
        "TotalTokens": int(token_usage.get("total_tokens") or 0),
        "CallCount": None,
        "EmbeddingModel": token_usage.get("embedding_model"),
        "LLMModel": token_usage.get("llm_model"),
        "TokenScope": "simulation_summary",
    }


def estimate_cost_proxy(
    *,
    embedding_tokens: int,
    llm_tokens: int,
    embedding_model: Optional[str],
    llm_model: Optional[str],
    llm_output_share: float,
) -> Optional[float]:
    embedding_price = MODEL_PRICES_PER_1K.get(str(embedding_model or ""), {}).get("input")
    llm_prices = MODEL_PRICES_PER_1K.get(str(llm_model or ""))
    llm_input_price = llm_prices.get("input") if llm_prices else None
    llm_output_price = llm_prices.get("output") if llm_prices else None
    if embedding_price is None or llm_input_price is None or llm_output_price is None:
        return None
    output_share = min(max(llm_output_share, 0.0), 1.0)
    blended_llm_price = (1.0 - output_share) * llm_input_price + output_share * llm_output_price
    return (embedding_tokens * embedding_price + llm_tokens * blended_llm_price) / 1000.0


def token_usage_for_row(
    *,
    benchmark_dir: Path,
    output_dir: Path,
    token_log_path: Path,
    llm_output_share: float,
) -> Dict[str, Any]:
    start_date, end_date, episode_count = date_range_from_episodes(output_dir)
    usage: Dict[str, Any] = {}
    if output_dir.resolve() == benchmark_dir.resolve() and start_date and end_date:
        usage = read_token_log_usage(token_log_path, start_date, end_date)
    if not usage:
        usage = read_summary_usage(output_dir)
    if not usage:
        return {}

    summary_usage = read_summary_usage(output_dir)
    embedding_model = usage.get("EmbeddingModel") or summary_usage.get("EmbeddingModel") or "Qwen/Qwen3-Embedding-8B"
    llm_model = usage.get("LLMModel") or summary_usage.get("LLMModel") or "gemini-3-flash-preview"
    usage["EmbeddingModel"] = embedding_model
    usage["LLMModel"] = llm_model
    cost = estimate_cost_proxy(
        embedding_tokens=int(usage.get("EmbeddingTokens") or 0),
        llm_tokens=int(usage.get("LLMTokens") or 0),
        embedding_model=str(embedding_model),
        llm_model=str(llm_model),
        llm_output_share=llm_output_share,
    )
    usage["CostUSDProxy"] = cost
    total_tokens = as_float(usage.get("TotalTokens"))
    call_count = as_float(usage.get("CallCount"))
    usage["TokensPerEpisode"] = total_tokens / episode_count if total_tokens is not None and episode_count else None
    usage["CallsPerEpisode"] = call_count / episode_count if call_count is not None and episode_count else None
    return usage


def method_name_from_dir(method_dir: Path) -> str:
    summary_files = sorted(method_dir.glob("*_summary.json"))
    for path in summary_files:
        payload = read_json(path)
        for key in ("method_name", "Method", "name"):
            value = str(payload.get(key) or "").strip()
            if value:
                return value
    return method_dir.name.replace("_", " ").title()


def discover_extra_methods(benchmark_dir: Path, known_metric_paths: Sequence[str]) -> List[Dict[str, Any]]:
    main_dir = benchmark_dir / "main_experiment"
    if not main_dir.exists():
        return []
    known = set(known_metric_paths)
    rows = []
    for metrics_path in sorted(main_dir.glob("*/evaluation_metrics.json")):
        relative = metrics_path.relative_to(benchmark_dir).as_posix()
        if relative in known:
            continue
        method_dir = metrics_path.parent
        group = "Model Variant" if "model" in method_dir.name.lower() else "Extra"
        rows.append(
            {
                "Group": group,
                "Method": method_name_from_dir(method_dir),
                "MetricsPath": relative,
                "OutputPath": method_dir.relative_to(benchmark_dir).as_posix(),
                "Status": "complete",
            }
        )
    return rows


def build_rows(
    *,
    benchmark_dir: Path,
    token_log_path: Path,
    lift_cap: float,
    llm_output_share: float,
) -> List[Dict[str, Any]]:
    known_paths = [row["MetricsPath"] for row in KNOWN_METHODS]
    catalog = KNOWN_METHODS + discover_extra_methods(benchmark_dir, known_paths)
    rows: List[Dict[str, Any]] = []
    for method in catalog:
        metrics_path = benchmark_dir / method["MetricsPath"]
        output_dir = benchmark_dir / str(method.get("OutputPath") or "")
        if not metrics_path.exists():
            row = {
                "Group": method["Group"],
                "Method": method["Method"],
                "Status": method.get("Status", "planned"),
            }
            rows.append(row)
            continue

        metrics = top20_metrics(metrics_path)
        row = {
            "Group": method["Group"],
            "Method": method["Method"],
            "Status": "complete",
            **metrics,
            "RecommendationScore": recommendation_score(metrics, lift_cap),
        }
        row.update(report_stats(output_dir))
        row.update(
            token_usage_for_row(
                benchmark_dir=benchmark_dir,
                output_dir=output_dir,
                token_log_path=token_log_path,
                llm_output_share=llm_output_share,
            )
        )
        rows.append(row)

    fill_efficiency_scores(rows)
    fill_overall_scores(rows)
    rows.sort(key=row_sort_key)
    for rank, row in enumerate(rows, start=1):
        row["Rank"] = rank
    return rows


def fill_efficiency_scores(rows: List[Dict[str, Any]]) -> None:
    cost_values = [float(row["CostUSDProxy"]) for row in rows if as_float(row.get("CostUSDProxy")) is not None]
    call_values = [
        float(row["CallsPerEpisode"])
        for row in rows
        if as_float(row.get("CallsPerEpisode")) is not None and float(row["CallsPerEpisode"]) > 0
    ]
    min_cost = min(cost_values) if cost_values else None
    min_calls = min(call_values) if call_values else None

    for row in rows:
        cost = as_float(row.get("CostUSDProxy"))
        calls = as_float(row.get("CallsPerEpisode"))
        success_rate = as_float(row.get("ReportSuccessRate"))
        cost_score = 100.0 * min_cost / cost if min_cost is not None and cost and cost > 0 else None
        latency_score = 100.0 * min_calls / calls if min_calls is not None and calls and calls > 0 else None
        success_score = 100.0 * success_rate if success_rate is not None else None
        row["CostScore"] = min(cost_score, 100.0) if cost_score is not None else None
        row["LatencyProxyScore"] = min(latency_score, 100.0) if latency_score is not None else None
        row["SuccessScore"] = success_score
        if row["CostScore"] is not None and row["LatencyProxyScore"] is not None and success_score is not None:
            row["CostEfficiencyScore"] = (
                0.40 * float(row["CostScore"])
                + 0.30 * float(row["LatencyProxyScore"])
                + 0.30 * success_score
            )
        else:
            row["CostEfficiencyScore"] = None


def fill_overall_scores(rows: List[Dict[str, Any]]) -> None:
    for row in rows:
        rec = as_float(row.get("RecommendationScore"))
        report_proxy = as_float(row.get("ReportProxyScore"))
        cost_eff = as_float(row.get("CostEfficiencyScore"))
        if rec is None or report_proxy is None or cost_eff is None:
            row["OverallScore"] = None
            row["OverallScoreSource"] = None
            continue
        row["OverallScore"] = 0.50 * rec + 0.30 * report_proxy + 0.20 * cost_eff
        row["OverallScoreSource"] = "report_proxy"


def row_sort_key(row: Dict[str, Any]) -> Tuple[int, float, str]:
    group_order = {
        "Full System": 0,
        "Model Variant": 1,
        "External Baseline": 2,
        "Ablation": 3,
        "Extra": 4,
    }.get(str(row.get("Group") or ""), 9)
    score = as_float(row.get("OverallScore"))
    if score is None:
        score = as_float(row.get("RecommendationScore"), -1.0)
    return (group_order, -float(score or -1.0), str(row.get("Method") or ""))


def format_cell(value: Any, header: str) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, str):
        return value
    numeric = as_float(value)
    if numeric is None:
        return "N/A"
    if header in {"Rank", "TotalTokens", "AvgReportChars"}:
        return f"{numeric:.0f}"
    if header == "CostUSDProxy":
        return f"{numeric:.4f}"
    if header in {
        "RecommendationScore",
        "ReportProxyScore",
        "CostScore",
        "LatencyProxyScore",
        "CostEfficiencyScore",
        "OverallScore",
    }:
        return f"{numeric:.2f}"
    return f"{numeric:.4f}"


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_HEADERS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({header: format_cell(row.get(header), header) for header in OUTPUT_HEADERS})


def write_markdown(path: Path, rows: List[Dict[str, Any]]) -> None:
    lines = [
        "| " + " | ".join(OUTPUT_HEADERS) + " |",
        "|"
        + "|".join(
            "---:" if header not in {"Group", "Method", "Status", "OverallScoreSource"} else "---"
            for header in OUTPUT_HEADERS
        )
        + "|",
    ]
    for row in rows:
        lines.append("| " + " | ".join(format_cell(row.get(header), header) for header in OUTPUT_HEADERS) + " |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_metric_definitions(path: Path, llm_output_share: float) -> None:
    text = f"""# Extended Main-Experiment Metrics

This table combines recommendation quality with end-to-end system metrics.

## Recommendation Metrics

`RecommendationScore = 100 * (0.25*gNDCG@20 + 0.15*Useful@5 + 0.15*Useful@20 + 0.20*StrictR@20+ + 0.15*MRR@20 + 0.10*min(Lift@20/15, 1))`.

## Report Metrics

`ReportCoverage` is generated reports divided by unique selected papers.
`ReportSuccessRate` is non-empty generated reports divided by unique selected papers.
`FullTextSourceRate` is the share of reports grounded in PDF/full-text parsing.
`ReportEvidenceRate` is the share of reports with retrieved evidence or evidence anchors.
`ReportStructureScore` is the average filled-field ratio across the expected report schema.

`ReportProxyScore = 100 * (0.30*ReportCoverage + 0.20*FullTextSourceRate + 0.20*ReportEvidenceRate + 0.20*ReportStructureScore + 0.10*LengthFit)`.

This is a structural automatic proxy, not a substitute for LLM-judge or human quality scores.

## Cost / Efficiency Metrics

`CostUSDProxy` is estimated from token logs and local model-price assumptions. The current aggregate token log does not preserve prompt/completion split, so LLM tokens are priced with an assumed output-token share of `{llm_output_share:.2f}`.

`LatencyProxyScore` currently uses inverse API/model calls per episode, because wall-clock latency is not stored in the frozen benchmark. Replace it with real runtime latency once model-comparison runs record elapsed seconds.

`CostEfficiencyScore = 0.40*CostScore + 0.30*LatencyProxyScore + 0.30*SuccessRate`, where `SuccessRate` is the report success rate on a 0-100 scale.

## Overall Score

`OverallScore = 0.50*RecommendationScore + 0.30*ReportProxyScore + 0.20*CostEfficiencyScore`.

Rows without generated reports or token/runtime evidence keep these fields as `N/A`, rather than zero.
"""
    path.write_text(text, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build extended main-experiment metrics table.")
    parser.add_argument(
        "--benchmark-dir",
        default="data/benchmark_full_24users_20260301_20260419_show20_with_reading",
        help="Frozen benchmark output directory.",
    )
    parser.add_argument("--token-log", default="data/token_usage.jsonl", help="Daily aggregate token log.")
    parser.add_argument("--lift-cap", type=float, default=15.0, help="Cap used to normalize Lift@20.")
    parser.add_argument(
        "--llm-output-share",
        type=float,
        default=0.30,
        help="Assumed output-token share for aggregate LLM token cost proxy.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    benchmark_dir = Path(args.benchmark_dir)
    output_dir = benchmark_dir / "main_experiment"
    output_dir.mkdir(parents=True, exist_ok=True)

    rows = build_rows(
        benchmark_dir=benchmark_dir,
        token_log_path=Path(args.token_log),
        lift_cap=args.lift_cap,
        llm_output_share=args.llm_output_share,
    )

    csv_path = output_dir / "main_experiment_extended_metrics_table.csv"
    md_path = output_dir / "main_experiment_extended_metrics_table.md"
    json_path = output_dir / "main_experiment_extended_metrics_table.json"
    definitions_path = output_dir / "main_experiment_extended_metric_definitions.md"

    write_csv(csv_path, rows)
    write_markdown(md_path, rows)
    json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    write_metric_definitions(definitions_path, args.llm_output_share)

    print(f"Wrote {csv_path}")
    print(f"Wrote {md_path}")
    print(f"Wrote {json_path}")
    print(f"Wrote {definitions_path}")


if __name__ == "__main__":
    main()
