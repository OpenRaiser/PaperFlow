#!/usr/bin/env python3
"""Build the LLM model-comparison table.

This script is intentionally separate from the main-experiment and ablation
tables. It compares only LLM backbones under the PaperFlow pipeline.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from experiments.main_experiment import build_main_experiment_extended_table as metrics_lib


CLOSED_MODELS = [
    {
        "group": "Closed API Model",
        "model_key": "gpt5_4",
        "model_backbone": "GPT-5.4",
        "package_glob": "paperflow_gpt5_4_llm_model_experiment_package_*",
    },
    {
        "group": "Closed API Model",
        "model_key": "qwen3_5_plus",
        "model_backbone": "qwen3.5-plus",
        "package_glob": "paperflow_qwen3_5_plus_llm_model_experiment_package_*",
    },
    {
        "group": "Closed API Model",
        "model_key": "gemini_3_1_pro_preview",
        "model_backbone": "gemini-3.1pro-preview",
        "package_glob": "paperflow_gemini_3_1_pro_preview_llm_model_experiment_package_*",
    },
    {
        "group": "Closed API Model",
        "model_key": "claude_sonnet_4_6",
        "model_backbone": "Claude Sonnet 4.6",
        "package_glob": "paperflow_claude_sonnet_4_6_llm_model_experiment_package_*",
    },
    {
        "group": "Closed API Model",
        "model_key": "qwen3_6_plus",
        "model_backbone": "Qwen3.6-Plus",
        "package_glob": "paperflow_qwen3_6_plus_llm_model_experiment_package_*",
    },
    {
        "group": "Closed API Model",
        "model_key": "qwen3_6_max_preview",
        "model_backbone": "Qwen3.6-Max-Preview",
        "package_glob": "paperflow_qwen3_6_max_preview_llm_model_experiment_package_*",
    },
    {
        "group": "Closed API Model",
        "model_key": "grok_4_3",
        "model_backbone": "grok-4.3",
        "package_glob": "paperflow_grok_4_3_llm_model_experiment_package_*",
    },
    {
        "group": "Closed API Model",
        "model_key": "paperflow_default",
        "model_backbone": "PaperFlow default (gemini-3-flash-preview)",
        "result_dir": "data/benchmark_full_24users_20260301_20260419_show20_with_reading",
        "token_log": "data/token_usage.jsonl",
    },
]


OPEN_MODELS = [
    {
        "group": "Open/Open-access Model",
        "model_key": "mimo2_5pro",
        "model_backbone": "Mimo2.5pro",
        "package_glob": "paperflow_mimo_v2_5_pro_llm_model_experiment_package_*",
    },
    {
        "group": "Open/Open-access Model",
        "model_key": "deepseek_v4_pro",
        "model_backbone": "deepseek-v4-pro",
        "package_glob": "paperflow_deepseek_v4_pro_llm_model_experiment_package_*",
    },
    {
        "group": "Open/Open-access Model",
        "model_key": "deepseek_v4_flash",
        "model_backbone": "deepseek-v4-flash",
        "package_glob": "paperflow_deepseek_v4_flash_llm_model_experiment_package_*",
    },
    {
        "group": "Open/Open-access Model",
        "model_key": "kimi_k2_6",
        "model_backbone": "kimi-k2.6",
        "package_glob": "paperflow_kimi_k2_6_llm_model_experiment_package_*",
    },
    {
        "group": "Open/Open-access Model",
        "model_key": "glm_5_1",
        "model_backbone": "GLM-5.1",
        "package_glob": "paperflow_glm_5_1_llm_model_experiment_package_*",
    },
    {
        "group": "Open/Open-access Model",
        "model_key": "minimax_m2_7",
        "model_backbone": "MiniMax-M2.7",
        "package_glob": "paperflow_minimax_m2_7_llm_model_experiment_package_*",
    },
]


OUTPUT_HEADERS = [
    "Group",
    "ModelKey",
    "Model Backbone",
    "Status",
    "RecommendationScore",
    "ReportAutoScore",
    "ModelAutoScore",
    "ModelHumanScore",
    "TokenCost",
    "TokenCostUnit",
    "LLMTokens",
    "EstimatedCostUSD",
    "ResultDir",
]


def as_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def scale_to_percent(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return value * 100.0 if 0.0 <= value <= 1.0 else value


def latest_matching_package(packages_dir: Path, pattern: str) -> Optional[Path]:
    matches = sorted(
        [path for path in packages_dir.glob(pattern) if path.is_dir()],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return matches[0] if matches else None


def configured_output_dir(package_dir: Path) -> Optional[Path]:
    config_path = package_dir / "experiment_config.json"
    if config_path.exists():
        config = metrics_lib.read_json(config_path)
        output = str(config.get("output_dir") or "").strip()
        if output:
            return package_dir / output
    return None


def discover_result_dir(spec: Dict[str, str], packages_dir: Path, root: Path) -> Optional[Path]:
    explicit = spec.get("result_dir")
    if explicit:
        result_dir = root / explicit
        return result_dir if (result_dir / "evaluation_metrics.json").exists() else None

    package_glob = spec.get("package_glob")
    if not package_glob:
        return None

    package_dir = latest_matching_package(packages_dir, package_glob)
    if not package_dir:
        return None

    candidates: List[Path] = []
    configured = configured_output_dir(package_dir)
    if configured:
        candidates.append(configured)
    results_dir = package_dir / "results"
    if results_dir.exists():
        candidates.extend(path.parent for path in results_dir.rglob("evaluation_metrics.json"))
    # Some standalone model packages are archived with an extra nested package
    # directory. Fall back to a package-wide search so completed results are not
    # missed when the outer directory does not directly contain results/.
    for metrics_path in package_dir.rglob("evaluation_metrics.json"):
        parent = metrics_path.parent
        if parent not in candidates:
            candidates.append(parent)

    for candidate in candidates:
        if (candidate / "evaluation_metrics.json").exists():
            return candidate
    return None


def recommendation_score(result_dir: Path, lift_cap: float) -> Optional[float]:
    metrics_path = result_dir / "evaluation_metrics.json"
    if not metrics_path.exists():
        return None
    metrics = metrics_lib.top20_metrics(metrics_path)
    return metrics_lib.recommendation_score(metrics, lift_cap)


def report_auto_score(report_stats: Dict[str, Any]) -> Optional[float]:
    section_completeness = as_float(report_stats.get("ReportStructureScore"))
    evidence_coverage = as_float(report_stats.get("ReportEvidenceRate"))
    if section_completeness is None or evidence_coverage is None:
        return None
    return 100.0 * (0.70 * section_completeness + 0.30 * evidence_coverage)


def model_auto_score(
    recommendation: Optional[float],
    report_auto: Optional[float],
) -> Optional[float]:
    if recommendation is None or report_auto is None:
        return None
    return 0.80 * recommendation + 0.20 * report_auto


def estimate_llm_cost_proxy(llm_tokens: int, llm_model: Optional[str], llm_output_share: float) -> Optional[float]:
    llm_prices = metrics_lib.MODEL_PRICES_PER_1K.get(str(llm_model or ""))
    if not llm_prices:
        return None
    input_price = as_float(llm_prices.get("input"))
    output_price = as_float(llm_prices.get("output"))
    if input_price is None or output_price is None:
        return None
    output_share = min(max(llm_output_share, 0.0), 1.0)
    blended_price = (1.0 - output_share) * input_price + output_share * output_price
    return llm_tokens * blended_price / 1000.0


def token_usage(
    result_dir: Path,
    token_log_path: Path,
    token_cost_mode: str,
    llm_output_share: float,
) -> Dict[str, Any]:
    usage = metrics_lib.token_usage_for_row(
        benchmark_dir=result_dir,
        output_dir=result_dir,
        token_log_path=token_log_path,
        llm_output_share=llm_output_share,
    )
    llm_tokens = as_float(usage.get("LLMTokens"))
    llm_cost = estimate_llm_cost_proxy(
        int(llm_tokens or 0),
        str(usage.get("LLMModel") or ""),
        llm_output_share,
    )
    if token_cost_mode == "usd":
        return {
            "TokenCost": llm_cost,
            "TokenCostUnit": "estimated_usd",
            "LLMTokens": llm_tokens,
            "EstimatedCostUSD": llm_cost,
        }
    return {
        "TokenCost": llm_tokens,
        "TokenCostUnit": "llm_tokens",
        "LLMTokens": llm_tokens,
        "EstimatedCostUSD": llm_cost,
    }


def build_row(
    spec: Dict[str, str],
    *,
    packages_dir: Path,
    root: Path,
    lift_cap: float,
    token_cost_mode: str,
    llm_output_share: float,
) -> Dict[str, Any]:
    result_dir = discover_result_dir(spec, packages_dir, root)
    row: Dict[str, Any] = {
        "Group": spec["group"],
        "ModelKey": spec["model_key"],
        "Model Backbone": spec["model_backbone"],
        "Status": "missing",
        "ModelHumanScore": "",
    }
    if result_dir is None:
        return row

    rec = recommendation_score(result_dir, lift_cap)
    stats = metrics_lib.report_stats(result_dir)
    report_auto = report_auto_score(stats)
    auto = model_auto_score(rec, report_auto)
    row.update(
        {
            "Status": "complete" if auto is not None else "partial",
            "RecommendationScore": rec,
            "ReportAutoScore": report_auto,
            "ModelAutoScore": auto,
            "ResultDir": str(result_dir),
        }
    )
    token_log_path = root / str(spec.get("token_log") or result_dir / "token_usage.jsonl")
    row.update(token_usage(result_dir, token_log_path, token_cost_mode, llm_output_share))
    return row


def build_rows(
    *,
    packages_dir: Path,
    root: Path,
    lift_cap: float,
    token_cost_mode: str,
    llm_output_share: float,
) -> List[Dict[str, Any]]:
    rows = []
    for spec in [*CLOSED_MODELS, *OPEN_MODELS]:
        rows.append(
            build_row(
                spec,
                packages_dir=packages_dir,
                root=root,
                lift_cap=lift_cap,
                token_cost_mode=token_cost_mode,
                llm_output_share=llm_output_share,
            )
        )
    return rows


def format_value(value: Any, header: str) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, str):
        return value
    numeric = as_float(value)
    if numeric is None:
        return "N/A"
    if header in {"RecommendationScore", "ReportAutoScore", "ModelAutoScore"}:
        return f"{numeric:.2f}"
    if header in {"EstimatedCostUSD"}:
        return f"{numeric:.4f}"
    if header in {"TokenCost"}:
        return f"{numeric:.4f}" if abs(numeric) < 100000 else f"{numeric:.0f}"
    if header in {"LLMTokens"}:
        return f"{numeric:.0f}"
    return str(value)


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_HEADERS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({header: format_value(row.get(header), header) for header in OUTPUT_HEADERS})


def markdown_lines(rows: List[Dict[str, Any]], title: str) -> List[str]:
    display_headers = [
        "Model Backbone",
        "RecommendationScore",
        "ReportAutoScore",
        "ModelAutoScore",
        "ModelHumanScore",
        "TokenCost &darr;",
    ]
    source_headers = [
        "Model Backbone",
        "RecommendationScore",
        "ReportAutoScore",
        "ModelAutoScore",
        "ModelHumanScore",
        "TokenCost",
    ]
    lines = [
        f"## {title}",
        "",
        "| " + " | ".join(display_headers) + " |",
        "|" + "|".join("---" if header == "Model Backbone" else "---:" for header in display_headers) + "|",
    ]
    for row in rows:
        lines.append("| " + " | ".join(format_value(row.get(header), header) for header in source_headers) + " |")
    return lines


def write_markdown(path: Path, rows: List[Dict[str, Any]]) -> None:
    closed = [row for row in rows if row["Group"] == "Closed API Model"]
    open_rows = [row for row in rows if row["Group"] == "Open/Open-access Model"]
    lines = []
    lines.extend(markdown_lines(closed, "Closed Models"))
    lines.extend([""])
    lines.extend(markdown_lines(open_rows, "Open Models"))
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_definitions(path: Path, token_cost_mode: str) -> None:
    token_text = (
        "estimated API cost in USD"
        if token_cost_mode == "usd"
        else "total LLM tokens, excluding the fixed embedding model"
    )
    text = f"""# LLM Model-Comparison Metrics

This table compares model backbones inside the same PaperFlow pipeline.
It does not include main-experiment baselines or ablation variants.

`RecommendationScore = 100 * (0.25*gNDCG@20 + 0.15*Useful@5 + 0.15*Useful@20 + 0.20*StrictR@20+ + 0.15*MRR@20 + 0.10*min(Lift@20/15, 1))`.

`ReportAutoScore = 100 * (0.70*SectionCompleteness + 0.30*EvidenceCoverage)`.
In the current logs, `SectionCompleteness` is implemented with `ReportStructureScore`,
and `EvidenceCoverage` is implemented with `ReportEvidenceRate`.

`ModelAutoScore = 0.80*RecommendationScore + 0.20*ReportAutoScore`.

`ParsingSuccess` is omitted from the main model-comparison table because all
completed runs currently achieve 100% non-empty report generation success. It
can be reported in diagnostic appendix tables alongside `SectionCompleteness`,
`EvidenceCoverage`, PDF-source rate, and abstract-fallback rate.

`ModelHumanScore` is filled after blind human evaluation.

`TokenCost` is reported separately as {token_text}. It is not included in
`ModelAutoScore` or `ModelHumanScore`.
"""
    path.write_text(text, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build LLM model-comparison metrics tables.")
    parser.add_argument("--packages-dir", default="llm_model_experiment_packages")
    parser.add_argument("--output-dir", default="results/model_comparison")
    parser.add_argument("--lift-cap", type=float, default=15.0)
    parser.add_argument(
        "--token-cost-mode",
        choices=["tokens", "usd"],
        default="tokens",
        help="Use total LLM tokens or estimated USD cost for the TokenCost column.",
    )
    parser.add_argument("--llm-output-share", type=float, default=0.30)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = Path.cwd()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = build_rows(
        packages_dir=Path(args.packages_dir),
        root=root,
        lift_cap=args.lift_cap,
        token_cost_mode=args.token_cost_mode,
        llm_output_share=args.llm_output_share,
    )

    write_csv(output_dir / "llm_model_comparison_auto_metrics.csv", rows)
    write_markdown(output_dir / "llm_model_comparison_auto_metrics.md", rows)
    (output_dir / "llm_model_comparison_auto_metrics.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_definitions(output_dir / "llm_model_comparison_metric_definitions.md", args.token_cost_mode)

    print(f"Wrote {output_dir / 'llm_model_comparison_auto_metrics.csv'}")
    print(f"Wrote {output_dir / 'llm_model_comparison_auto_metrics.md'}")
    print(f"Wrote {output_dir / 'llm_model_comparison_auto_metrics.json'}")
    print(f"Wrote {output_dir / 'llm_model_comparison_metric_definitions.md'}")


if __name__ == "__main__":
    main()
