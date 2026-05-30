#!/usr/bin/env python3
"""Build a blind annotation packet for LLM model-comparison human evaluation."""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from experiments.human_eval import build_main_human_eval_packet as common


DEFAULT_BENCHMARK_DIR = common.DEFAULT_BENCHMARK_DIR


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    return payload if isinstance(payload, dict) else {}


def default_model_specs(packages_dir: Path, benchmark_dir: Path) -> List[Tuple[str, str, Path]]:
    specs: List[Tuple[str, str, Path]] = []
    root_reports = benchmark_dir / "reading_reports.jsonl"
    if root_reports.exists():
        specs.append(("paperflow_default", "PaperFlow default", benchmark_dir))

    if packages_dir.exists():
        for package_dir in sorted(path for path in packages_dir.iterdir() if path.is_dir()):
            config = read_json(package_dir / "experiment_config.json")
            model_key = str(config.get("model_key") or package_dir.name)
            model_name = str(config.get("method_name") or config.get("llm_model") or model_key)
            output_dir = package_dir / str(config.get("output_dir") or "results")
            if not output_dir.is_absolute():
                output_dir = package_dir / output_dir
            specs.append((model_key, model_name, output_dir))
    return specs


def parse_model_specs(values: Sequence[str]) -> List[Tuple[str, str, Path]]:
    specs: List[Tuple[str, str, Path]] = []
    for value in values:
        parts = value.split("=", 2)
        if len(parts) not in {2, 3}:
            raise SystemExit("--model must use key=output_dir or key=output_dir=display name")
        key = parts[0]
        path = Path(parts[1])
        name = parts[2] if len(parts) == 3 else key
        specs.append((key, name, path))
    return specs


def report_jsonl_path(output_dir: Path) -> Path:
    if output_dir.is_file():
        return output_dir
    return output_dir / "reading_reports.jsonl"


def episode_papers_path(output_dir: Path) -> Path:
    if output_dir.is_file():
        return output_dir.parent / "episode_papers.jsonl"
    return output_dir / "episode_papers.jsonl"


def report_id(row: Dict[str, Any]) -> Tuple[str, str]:
    return (str(row.get("episode_id") or ""), str(row.get("paper_id") or row.get("report_key") or ""))


def reservoir_sample_reports(path: Path, sample_size: int, seed: int) -> List[Dict[str, Any]]:
    rng = random.Random(seed)
    sample: List[Dict[str, Any]] = []
    seen = 0
    for row in common.iter_jsonl(path):
        if not row.get("report_payload") and not row.get("report_content"):
            continue
        seen += 1
        if len(sample) < sample_size:
            sample.append(row)
            continue
        index = rng.randrange(seen)
        if index < sample_size:
            sample[index] = row
    return sample


def load_episode_lookup(path: Path, keys: Iterable[Tuple[str, str]]) -> Dict[Tuple[str, str], Dict[str, Any]]:
    wanted = set(keys)
    found: Dict[Tuple[str, str], Dict[str, Any]] = {}
    if not path.exists() or not wanted:
        return found
    for row in common.iter_jsonl(path):
        key = (str(row.get("episode_id") or ""), str(row.get("paper_id") or ""))
        if key in wanted:
            found[key] = row
            if len(found) >= len(wanted):
                break
    return found


def compact_report_text(row: Dict[str, Any], limit: int) -> str:
    content = str(row.get("report_content") or "").strip()
    if content:
        return common.truncate(content, limit)
    payload = row.get("report_payload")
    if isinstance(payload, dict):
        parts = []
        for field in (
            "one_sentence_summary",
            "research_background",
            "core_method",
            "key_results",
            "main_contributions",
            "limitations",
            "relevance_points",
            "reading_focus",
            "analysis_note",
        ):
            value = payload.get(field)
            if value:
                parts.append(f"{field}: {common.truncate(value, 1200)}")
        return common.truncate("\n\n".join(parts), limit)
    return ""


def build_rows(
    specs: Sequence[Tuple[str, str, Path]],
    users: Dict[str, Dict[str, Any]],
    *,
    reports_per_model: int,
    seed: int,
    abstract_chars: int,
    report_chars: int,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    blind_rows: List[Dict[str, Any]] = []
    key_rows: List[Dict[str, Any]] = []
    sample_index = 1
    for model_key, model_name, output_dir in specs:
        reports_path = report_jsonl_path(output_dir)
        if not reports_path.exists():
            print(f"Skipping missing reports for {model_key}: {reports_path}")
            continue
        reports = reservoir_sample_reports(reports_path, reports_per_model, seed + len(model_key))
        lookup = load_episode_lookup(episode_papers_path(output_dir), (report_id(row) for row in reports))
        for row in reports:
            sample_id = f"HMODEL_{sample_index:05d}"
            sample_index += 1
            key = report_id(row)
            paper_row = lookup.get(key, {})
            user_id = str(row.get("user_id") or paper_row.get("user_id") or "")
            blind_rows.append(
                {
                    "sample_id": sample_id,
                    "user_profile": common.profile_text(users.get(user_id)),
                    "paper_title": common.truncate(row.get("title") or paper_row.get("title"), 500),
                    "paper_abstract": common.truncate(
                        row.get("abstract") or paper_row.get("abstract"),
                        abstract_chars,
                    ),
                    "paper_authors": common.truncate(row.get("authors") or paper_row.get("authors"), 500),
                    "recommendation_context": common.truncate(paper_row.get("reason") or paper_row.get("explanation"), 800),
                    "reading_report": compact_report_text(row, report_chars),
                    "HumanRelevance": "",
                    "HumanUsefulness": "",
                    "RecommendationDecisionHelpfulness": "",
                    "ReportFaithfulness": "",
                    "ReportSpecificity": "",
                    "ReportDecisionHelpfulness": "",
                    "comments": "",
                }
            )
            key_rows.append(
                {
                    "sample_id": sample_id,
                    "model_key": model_key,
                    "model_name": model_name,
                    "episode_id": row.get("episode_id") or paper_row.get("episode_id"),
                    "user_id": user_id,
                    "role_name": row.get("role_name") or paper_row.get("role_name"),
                    "date": row.get("date") or paper_row.get("date"),
                    "paper_id": row.get("paper_id") or paper_row.get("paper_id"),
                    "system_rank": paper_row.get("system_rank"),
                    "system_label": paper_row.get("system_label"),
                    "system_score": paper_row.get("system_score"),
                    "oracle_label": paper_row.get("oracle_label"),
                    "oracle_score": paper_row.get("oracle_score"),
                    "selected": common.as_bool(paper_row.get("selected")),
                    "analysis_source": row.get("analysis_source"),
                    "report_key": row.get("report_key"),
                }
            )
    return blind_rows, key_rows


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0].keys()) if rows else []
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_guidelines(path: Path) -> None:
    path.write_text(
        """# Model Human Evaluation Annotation Guide

Annotators evaluate both recommendation quality and reading-report quality.
Model name, rank, oracle labels, selected flags, and automatic scores are hidden.

Use a 1-5 Likert scale:

- HumanRelevance: whether the recommended paper matches the user profile.
- HumanUsefulness: whether the paper is worth reading for the user.
- RecommendationDecisionHelpfulness: whether the recommendation context helps the user decide to read.
- ReportFaithfulness: whether the report is faithful to the paper information.
- ReportSpecificity: whether the report is specific rather than generic.
- ReportDecisionHelpfulness: whether the report helps the user's reading decision.

```text
HumanRecommendationScore = 20 * mean(
  HumanRelevance,
  HumanUsefulness,
  RecommendationDecisionHelpfulness
)

ReportHumanScore = 20 * mean(
  ReportFaithfulness,
  ReportSpecificity,
  ReportDecisionHelpfulness
)

ModelHumanScore = 0.6 * HumanRecommendationScore
                + 0.4 * ReportHumanScore
```
""",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a blind model-comparison human-evaluation packet.")
    parser.add_argument("--benchmark-dir", default=str(DEFAULT_BENCHMARK_DIR))
    parser.add_argument("--packages-dir", default="llm_model_experiment_packages")
    parser.add_argument("--model", action="append", default=[], help="Optional key=output_dir or key=output_dir=display name")
    parser.add_argument("--reports-per-model", type=int, default=12)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--abstract-chars", type=int, default=1200)
    parser.add_argument("--report-chars", type=int, default=6000)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    benchmark_dir = Path(args.benchmark_dir)
    output_dir = Path(args.output_dir) if args.output_dir else benchmark_dir / "evaluation" / "model_human_eval"
    users = common.load_users(benchmark_dir / "users.json")
    specs = parse_model_specs(args.model) if args.model else default_model_specs(Path(args.packages_dir), benchmark_dir)
    blind_rows, key_rows = build_rows(
        specs,
        users,
        reports_per_model=args.reports_per_model,
        seed=args.seed,
        abstract_chars=args.abstract_chars,
        report_chars=args.report_chars,
    )
    write_csv(output_dir / "model_human_eval_blind.csv", blind_rows)
    write_csv(output_dir / "model_human_eval_key.csv", key_rows)
    write_guidelines(output_dir / "model_human_eval_guidelines.md")
    print(f"Blind packet: {output_dir / 'model_human_eval_blind.csv'}")
    print(f"Internal key: {output_dir / 'model_human_eval_key.csv'}")
    print(f"Rows exported: {len(blind_rows)}")


if __name__ == "__main__":
    main()
