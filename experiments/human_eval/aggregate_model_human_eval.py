#!/usr/bin/env python3
"""Aggregate LLM model-comparison human evaluation scores."""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from experiments.human_eval import aggregate_main_human_eval as common


REC_DIMS = ["HumanRelevance", "HumanUsefulness", "RecommendationDecisionHelpfulness"]
REPORT_DIMS = ["ReportFaithfulness", "ReportSpecificity", "ReportDecisionHelpfulness"]
AUTO_FIELDS = [
    "RecommendationScore",
    "ReportAutoScore",
    "ParsingSuccess",
    "TokenCost",
    "CostUSDProxy",
    "ModelAutoScore",
]


def parse_optional_float(value: object) -> Optional[float]:
    text = str(value or "").strip()
    if not text or text.upper() == "N/A":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def scale_to_percent(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return value * 100.0 if 0.0 <= value <= 1.0 else value


def report_auto_score(row: Dict[str, str]) -> Optional[float]:
    direct = parse_optional_float(row.get("ReportAutoScore"))
    if direct is not None:
        return direct
    section = parse_optional_float(row.get("ReportStructureScore"))
    evidence = parse_optional_float(row.get("ReportEvidenceRate"))
    if section is not None and evidence is not None:
        return 100.0 * (0.70 * section + 0.30 * evidence)
    return parse_optional_float(row.get("ReportProxyScore"))


def parsing_success(row: Dict[str, str]) -> Optional[float]:
    direct = parse_optional_float(row.get("ParsingSuccess"))
    if direct is not None:
        return scale_to_percent(direct)
    return scale_to_percent(parse_optional_float(row.get("ReportSuccessRate")))


def model_auto_score(row: Dict[str, str]) -> Optional[float]:
    direct = parse_optional_float(row.get("ModelAutoScore"))
    if direct is not None:
        return direct
    rec = parse_optional_float(row.get("RecommendationScore"))
    report = report_auto_score(row)
    parsing = parsing_success(row)
    if rec is None or report is None or parsing is None:
        return None
    return 0.75 * rec + 0.15 * report + 0.10 * parsing


def load_auto_summary(path: Optional[Path]) -> Dict[str, Dict[str, str]]:
    if path is None:
        return {}
    rows = common.read_csv(path)
    lookup: Dict[str, Dict[str, str]] = {}
    for row in rows:
        enriched = dict(row)
        auto = model_auto_score(enriched)
        if auto is not None:
            enriched["ModelAutoScore"] = f"{auto:.4f}"
        report = report_auto_score(enriched)
        if report is not None:
            enriched["ReportAutoScore"] = f"{report:.4f}"
        parsing = parsing_success(enriched)
        if parsing is not None:
            enriched["ParsingSuccess"] = f"{parsing:.4f}"
        if not enriched.get("TokenCost") and enriched.get("CostUSDProxy"):
            enriched["TokenCost"] = enriched["CostUSDProxy"]
        for key_field in ("model_key", "ModelKey", "method_key", "Method", "model_name", "Model Backbone"):
            key = str(enriched.get(key_field) or "").strip()
            if key:
                lookup[key] = enriched
    return lookup


def auto_for_model(auto_lookup: Dict[str, Dict[str, str]], model_key: str, model_name: str) -> Dict[str, str]:
    row = auto_lookup.get(model_key) or auto_lookup.get(model_name) or {}
    return {field: str(row.get(field) or "") for field in AUTO_FIELDS}


def build_scored_reports(blind_rows: List[Dict[str, str]], key_rows: List[Dict[str, str]]) -> List[Dict[str, object]]:
    key_by_sample = common.index_by_sample(key_rows)
    scored: List[Dict[str, object]] = []
    for blind in blind_rows:
        sample_id = str(blind.get("sample_id") or "")
        key = key_by_sample.get(sample_id)
        if not key:
            raise ValueError(f"Missing key row for sample {sample_id}")
        rec = {field: common.parse_score(str(blind.get(field, "")), field, sample_id) for field in REC_DIMS}
        report = {field: common.parse_score(str(blind.get(field, "")), field, sample_id) for field in REPORT_DIMS}
        human_rec = 20.0 * mean(rec.values())
        report_human = 20.0 * mean(report.values())
        model_human = 0.6 * human_rec + 0.4 * report_human
        scored.append(
            {
                **key,
                **{field: f"{value:.4f}" for field, value in rec.items()},
                **{field: f"{value:.4f}" for field, value in report.items()},
                "HumanRecommendationScore": f"{human_rec:.4f}",
                "ReportHumanScore": f"{report_human:.4f}",
                "ModelHumanScore": f"{model_human:.4f}",
                "comments": blind.get("comments", ""),
            }
        )
    return scored


def aggregate_model_scores(
    scored_rows: List[Dict[str, object]],
    auto_lookup: Optional[Dict[str, Dict[str, str]]] = None,
) -> List[Dict[str, object]]:
    buckets: Dict[str, List[Dict[str, object]]] = defaultdict(list)
    for row in scored_rows:
        buckets[str(row["model_key"])].append(row)

    output: List[Dict[str, object]] = []
    auto_lookup = auto_lookup or {}
    for model_key, rows in sorted(buckets.items()):
        first = rows[0]
        model_name = str(first["model_name"])
        output.append(
            {
                "model_key": model_key,
                "model_name": model_name,
                "n_reports": len(rows),
                **auto_for_model(auto_lookup, model_key, model_name),
                "HumanRecommendationScore": f"{mean(float(row['HumanRecommendationScore']) for row in rows):.4f}",
                "ReportHumanScore": f"{mean(float(row['ReportHumanScore']) for row in rows):.4f}",
                "ModelHumanScore": f"{mean(float(row['ModelHumanScore']) for row in rows):.4f}",
                "HumanRelevance": f"{mean(float(row['HumanRelevance']) for row in rows):.4f}",
                "HumanUsefulness": f"{mean(float(row['HumanUsefulness']) for row in rows):.4f}",
                "RecommendationDecisionHelpfulness": (
                    f"{mean(float(row['RecommendationDecisionHelpfulness']) for row in rows):.4f}"
                ),
                "ReportFaithfulness": f"{mean(float(row['ReportFaithfulness']) for row in rows):.4f}",
                "ReportSpecificity": f"{mean(float(row['ReportSpecificity']) for row in rows):.4f}",
                "ReportDecisionHelpfulness": f"{mean(float(row['ReportDecisionHelpfulness']) for row in rows):.4f}",
            }
        )
    output.sort(key=lambda row: float(row["ModelHumanScore"]), reverse=True)
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aggregate model-comparison human evaluation annotations.")
    parser.add_argument("--blind-csv", required=True)
    parser.add_argument("--key-csv", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument(
        "--auto-summary-csv",
        default=None,
        help="Optional model automatic-metrics CSV. If provided, joins ModelAutoScore for correlation analysis.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    scored = build_scored_reports(common.read_csv(Path(args.blind_csv)), common.read_csv(Path(args.key_csv)))
    auto_lookup = load_auto_summary(Path(args.auto_summary_csv)) if args.auto_summary_csv else None
    summary = aggregate_model_scores(scored, auto_lookup)
    common.write_csv(output_dir / "model_human_eval_scored_reports.csv", scored)
    common.write_csv(output_dir / "model_human_eval_model_summary.csv", summary)
    print(f"Scored reports: {output_dir / 'model_human_eval_scored_reports.csv'}")
    print(f"Model summary: {output_dir / 'model_human_eval_model_summary.csv'}")


if __name__ == "__main__":
    main()
