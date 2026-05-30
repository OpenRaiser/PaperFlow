#!/usr/bin/env python3
"""Evaluate PaperFlow reading-report outputs against benchmark episodes."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple


REQUIRED_REPORT_FIELDS = [
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


def iter_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def selected_report_key(user_id: str, paper_id: Any, title: Any) -> Optional[Tuple[str, str, str]]:
    if paper_id not in (None, ""):
        return (user_id, "paper", str(paper_id))
    title_key = " ".join(str(title or "").strip().lower().split())
    if title_key:
        return (user_id, "title", title_key)
    return None


def report_key(report: Dict[str, Any]) -> Optional[Tuple[str, str, str]]:
    user_id = str(report.get("user_id") or "")
    if not user_id:
        return None
    paper_id = report.get("paper_id")
    title = report.get("title")
    return selected_report_key(user_id, paper_id, title)


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


def expected_report_keys(episodes_path: Path) -> set[Tuple[str, str, str]]:
    keys: set[Tuple[str, str, str]] = set()
    for episode in iter_jsonl(episodes_path):
        user_id = str(episode.get("user_id") or "")
        paper_ids = episode.get("selected_paper_ids") or []
        titles = episode.get("selected_paper_titles") or []
        for index, paper_id in enumerate(paper_ids):
            title = titles[index] if index < len(titles) else ""
            key = selected_report_key(user_id, paper_id, title)
            if key:
                keys.add(key)
    return keys


def evaluate_reports(episodes_path: Path, reports_path: Path) -> Dict[str, Any]:
    expected = expected_report_keys(episodes_path)
    seen: set[Tuple[str, str, str]] = set()
    duplicate_count = 0
    report_count = 0
    matched_count = 0
    nonempty_matched_count = 0
    full_text_count = 0
    evidence_count = 0
    structure_scores: list[float] = []
    length_scores: list[float] = []
    char_counts: list[int] = []
    source_counts: Counter[str] = Counter()

    for report in iter_jsonl(reports_path):
        report_count += 1
        key = report_key(report)
        if key:
            if key in seen:
                duplicate_count += 1
            seen.add(key)
        is_expected = key in expected if key else False
        if is_expected:
            matched_count += 1

        content = str(report.get("report_content") or "").strip()
        char_count = len(content)
        char_counts.append(char_count)
        length_scores.append(length_fit_score(char_count))
        if is_expected and content:
            nonempty_matched_count += 1

        source = str(report.get("analysis_source") or "unknown").strip() or "unknown"
        source_counts[source] += 1
        if source in {"pdf", "full_text"} and not report.get("pdf_error"):
            full_text_count += 1

        payload = report.get("report_payload") or {}
        if payload.get("retrieved_evidence") or payload.get("report_evidence_anchors"):
            evidence_count += 1

        filled = 0
        for field in REQUIRED_REPORT_FIELDS:
            value = payload.get(field)
            if isinstance(value, (list, dict)):
                filled += 1 if value else 0
            else:
                filled += 1 if str(value or "").strip() else 0
        structure_scores.append(filled / len(REQUIRED_REPORT_FIELDS))

    expected_count = len(expected)
    coverage = matched_count / expected_count if expected_count else None
    success_rate = nonempty_matched_count / expected_count if expected_count else None
    full_text_rate = full_text_count / report_count if report_count else None
    evidence_rate = evidence_count / report_count if report_count else None
    structure_score = sum(structure_scores) / len(structure_scores) if structure_scores else None
    length_score = sum(length_scores) / len(length_scores) if length_scores else None
    avg_chars = sum(char_counts) / len(char_counts) if char_counts else None
    report_auto_score = None
    report_proxy_score = None

    if structure_score is not None and evidence_rate is not None:
        report_auto_score = 100.0 * (0.70 * structure_score + 0.30 * evidence_rate)
    if all(v is not None for v in [coverage, full_text_rate, evidence_rate, structure_score, length_score]):
        report_proxy_score = 100.0 * (
            0.30 * float(coverage)
            + 0.20 * float(full_text_rate)
            + 0.20 * float(evidence_rate)
            + 0.20 * float(structure_score)
            + 0.10 * float(length_score)
        )

    return {
        "SelectedReportsExpected": expected_count,
        "ReportCount": report_count,
        "MatchedReportCount": matched_count,
        "DuplicateReportCount": duplicate_count,
        "ExtraReportCount": max(report_count - matched_count, 0),
        "ReportCoverage": coverage,
        "ReportSuccessRate": success_rate,
        "FullTextSourceRate": full_text_rate,
        "ReportEvidenceRate": evidence_rate,
        "ReportStructureScore": structure_score,
        "AvgReportChars": avg_chars,
        "ReportAutoScore": report_auto_score,
        "ReportProxyScore": report_proxy_score,
        "ReportSourceCounts": dict(source_counts),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark-dir", type=Path, default=Path("."))
    parser.add_argument(
        "--reports",
        type=Path,
        default=Path("reference_outputs") / "paperflow_reading_reports.jsonl",
        help="Reading-report JSONL file to evaluate.",
    )
    parser.add_argument("--output", type=Path, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    benchmark_dir = args.benchmark_dir
    reports_path = args.reports
    if not reports_path.is_absolute() and not reports_path.exists():
        reports_path = benchmark_dir / reports_path
    metrics = evaluate_reports(benchmark_dir / "data" / "episodes.jsonl", reports_path)
    text = json.dumps(metrics, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
