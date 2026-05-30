#!/usr/bin/env python3
"""Build a HuggingFace-ready PaperFlow-Bench dataset package."""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = PROJECT_ROOT / "data" / "benchmark_full_24users_20260301_20260419_show20_with_reading"
DEFAULT_OUTPUT = PROJECT_ROOT / "release" / "huggingface" / "PaperFlow-Bench"


def iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def write_jsonl(path: Path, rows) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
            count += 1
    return count


def copy_if_exists(src: Path, dst: Path) -> None:
    if src.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def strip_replacement_chars(value):
    """Recursively remove U+FFFD chars from any string inside dicts/lists."""
    if isinstance(value, str):
        return value.replace("�", "")
    if isinstance(value, dict):
        return {k: strip_replacement_chars(v) for k, v in value.items()}
    if isinstance(value, list):
        return [strip_replacement_chars(v) for v in value]
    return value


def copy_reading_reports(src: Path, dst: Path) -> None:
    """Copy reading_reports.jsonl, removing U+FFFD artifacts from PDF extraction."""
    if not src.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    with src.open("r", encoding="utf-8") as src_handle, dst.open("w", encoding="utf-8") as dst_handle:
        for line in src_handle:
            line = line.strip()
            if not line:
                continue
            row = strip_replacement_chars(json.loads(line))
            dst_handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def copy_tree_files(src: Path, dst: Path, patterns: tuple[str, ...]) -> None:
    if not src.exists():
        return
    for pattern in patterns:
        for path in src.rglob(pattern):
            if path.is_file():
                copy_if_exists(path, dst / path.relative_to(src))


def arxiv_urls(arxiv_id: object) -> tuple[str | None, str | None]:
    arxiv = str(arxiv_id or "").strip()
    if not arxiv:
        return None, None
    arxiv = arxiv.removeprefix("arXiv:").removeprefix("arxiv:")
    return f"https://arxiv.org/abs/{arxiv}", f"https://arxiv.org/pdf/{arxiv}.pdf"


def sanitize_release_text_files(output_dir: Path) -> None:
    """Remove local machine paths from small copied summary artifacts."""
    text_suffixes = {".csv", ".json", ".md", ".txt"}
    replacements = {
        str(PROJECT_ROOT): "<PAPERFLOW_REPO>",
        str(PROJECT_ROOT).replace("\\", "/"): "<PAPERFLOW_REPO>",
    }
    legacy_root_name = "sci" + "taste_dataset_fullcode_20260428_142645"
    project_path_patterns = [
        re.compile(r"[A-Z]:\\[^\"\r\n]*paperflow_dataset_fullcode_20260428_142645", re.IGNORECASE),
        re.compile(rf"[A-Z]:\\[^\"\r\n]*{legacy_root_name}", re.IGNORECASE),
        re.compile(r"[A-Z]:\\Users\\[^\\\"\r\n]+", re.IGNORECASE),
        re.compile(r"[A-Z]:/Users/[^/\"\r\n]+", re.IGNORECASE),
    ]
    for path in output_dir.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in text_suffixes:
            continue
        if path.stat().st_size > 10_000_000:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        sanitized = text
        for old, new in replacements.items():
            sanitized = sanitized.replace(old, new)
        for pattern in project_path_patterns:
            sanitized = pattern.sub("<PAPERFLOW_REPO>", sanitized)
        if sanitized != text:
            path.write_text(sanitized, encoding="utf-8")


def paper_rows(source_dir: Path):
    seen: set[str] = set()
    for pool in iter_jsonl(source_dir / "paper_pools.jsonl"):
        for paper in pool.get("papers") or []:
            paper_id = str(paper.get("paper_id") or "")
            if not paper_id or paper_id in seen:
                continue
            seen.add(paper_id)
            abs_url, pdf_url = arxiv_urls(paper.get("arxiv_id"))
            yield {
                "paper_id": paper.get("paper_id"),
                "arxiv_id": paper.get("arxiv_id"),
                "doi": paper.get("doi"),
                "abs_url": abs_url,
                "pdf_url": pdf_url,
                "title": paper.get("title"),
                "abstract": paper.get("abstract"),
                "authors": paper.get("authors"),
                "institution": paper.get("institution"),
                "venue": paper.get("venue"),
                "source": paper.get("source"),
                "url": paper.get("url"),
                "publish_date": paper.get("publish_date"),
            }


def label_rows(source_dir: Path):
    keep = [
        "date",
        "episode_id",
        "user_id",
        "role_name",
        "paper_id",
        "pool_rank",
        "system_rank",
        "shown",
        "selected",
        "system_score",
        "system_label",
        "oracle_score",
        "oracle_label",
        "select_probability",
        "drift_bonus",
        "reading_signal_bonus",
    ]
    for row in iter_jsonl(source_dir / "episode_papers.jsonl"):
        yield {key: row.get(key) for key in keep}


def dataset_card() -> str:
    return """---
pretty_name: PaperFlow-Bench
license: mit
task_categories:
- text-retrieval
- text-ranking
- summarization
language:
- en
size_categories:
- 100K<n<1M
tags:
- recommender-systems
- scientific-paper-recommendation
- personalization
- benchmark
configs:
- config_name: users
  data_files:
  - split: test
    path: data/users.jsonl
- config_name: episodes
  data_files:
  - split: test
    path: data/episodes.jsonl
- config_name: papers
  data_files:
  - split: test
    path: data/papers.jsonl
- config_name: episode_labels
  data_files:
  - split: test
    path: data/episode_labels.jsonl
- config_name: drift_timeline
  data_files:
  - split: test
    path: data/drift_timeline.jsonl
- config_name: paperflow_reading_reports
  data_files:
  - split: test
    path: reference_outputs/paperflow_reading_reports.jsonl
---

# PaperFlow-Bench

This dataset packages PaperFlow-Bench as a Hugging Face dataset repo.

## Included

- `data/users.jsonl`: simulated user metadata and seed profiles (one user per line).
- `data/episodes.jsonl`: one row per user-day episode.
- `data/papers.jsonl`: deduplicated paper metadata with arXiv abstract/PDF URLs.
- `data/episode_labels.jsonl`: episode-paper labels, shown flags, and simulated reading selections.
- `data/drift_timeline.jsonl`: interest-drift diagnostic timeline.
- `reference_outputs/paperflow_reading_reports.jsonl`: full PaperFlow-generated reading reports for selected papers.
- `evaluation/evaluate.py`: standalone evaluator for Top-20 prediction files.
- `evaluation/make_submission.py`: helper for creating valid Top-20 prediction files.
- `evaluation/evaluate_reports.py`: standalone evaluator for reading-report outputs.

## Current Snapshot

- Simulated research users: 24
- Daily paper streams: 50
- User-day episodes: 1,200
- Unique papers: 20,727
- Episode-paper records: 497,448
- PaperFlow reading reports: 3,104
- Display budget: Top-20

## Loading

```python
from datasets import load_dataset

repo_id = "OpenRaiser/PaperFlow"

users = load_dataset(repo_id, "users", split="test")
episodes = load_dataset(repo_id, "episodes", split="test")
papers = load_dataset(repo_id, "papers", split="test")
labels = load_dataset(repo_id, "episode_labels", split="test")
drift = load_dataset(repo_id, "drift_timeline", split="test")
reports = load_dataset(repo_id, "paperflow_reading_reports", split="test")
```

## Evaluation

Prediction files use JSONL:

```json
{"episode_id": "user_role1::2026-03-01", "paper_ids": [37, 12, 88]}
```

Create a simple pool-rank example submission:

```bash
python evaluation/make_submission.py \\
  --benchmark-dir . \\
  --output predictions_pool_rank.jsonl
```

```bash
python evaluation/evaluate.py \\
  --benchmark-dir . \\
  --predictions predictions_pool_rank.jsonl \\
  --output paperflow_eval_check.json
```

The evaluator reports `gNDCG@20`, `Useful@5`, `Useful@20`,
`SelectedNDCG@20`, `StrictR@20+`, `MRR@20`, `Lift@20`, and
`RecommendationScore`.

Reading-report outputs can be evaluated with:

```bash
python evaluation/evaluate_reports.py \\
  --benchmark-dir . \\
  --reports reference_outputs/paperflow_reading_reports.jsonl
```

The report evaluator computes coverage, non-empty success rate,
full-text source rate, evidence coverage, structure completeness,
`ReportAutoScore`, and `ReportProxyScore`.

## Notes

- Published metadata has local absolute paths removed.
- `paper_ids` are ranked and truncated to Top-20 by the evaluator.
- Pseudo-oracle labels are controlled evaluation targets, not human ground truth.
- Reference reading reports are PaperFlow-generated outputs, not gold summaries.
- Paper experiment summaries are released with the PaperFlow code repository.
"""


def evaluation_readme() -> str:
    return """# Evaluation

## Recommendation Ranking

Prediction files use JSONL:

```json
{"episode_id": "user_role1::2026-03-01", "paper_ids": [37, 12, 88]}
```

Create a valid pool-rank example submission:

```bash
python evaluation/make_submission.py \\
  --benchmark-dir . \\
  --output predictions_pool_rank.jsonl
```

Evaluate a submission:

```bash
python evaluation/evaluate.py \\
  --benchmark-dir . \\
  --predictions predictions_pool_rank.jsonl
```

The evaluator is copied from the PaperFlow repository's
`scripts/evaluate_benchmark_predictions.py`.

## Reading Reports

Reading-report files use JSONL with one report per selected paper. The bundled
reference file is:

```text
reference_outputs/paperflow_reading_reports.jsonl
```

Run:

```bash
python evaluation/evaluate_reports.py \\
  --benchmark-dir . \\
  --reports reference_outputs/paperflow_reading_reports.jsonl
```

The script reports coverage, non-empty success rate, full-text source rate,
evidence coverage, structure completeness, `ReportAutoScore`, and
`ReportProxyScore`.
"""


def user_rows(source_dir: Path):
    """Yield one user dict per row from the source users.json wrapper."""
    src = source_dir / "users.json"
    if not src.exists():
        return
    with src.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    for user in payload.get("users") or []:
        yield user


def prepare(source_dir: Path, output_dir: Path, clean: bool = True) -> None:
    if clean and output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"[package] source={source_dir}")
    print(f"[package] output={output_dir}")

    print("[package] writing users.jsonl")
    user_count = write_jsonl(output_dir / "data" / "users.jsonl", user_rows(source_dir))
    print(f"[package] users={user_count}")
    copy_if_exists(source_dir / "episodes.jsonl", output_dir / "data" / "episodes.jsonl")
    copy_if_exists(source_dir / "drift_timeline.jsonl", output_dir / "data" / "drift_timeline.jsonl")
    print("[package] writing papers.jsonl")
    paper_count = write_jsonl(output_dir / "data" / "papers.jsonl", paper_rows(source_dir))
    print(f"[package] papers={paper_count}")

    print("[package] writing episode_labels.jsonl")
    label_count = write_jsonl(output_dir / "data" / "episode_labels.jsonl", label_rows(source_dir))
    print(f"[package] episode_labels={label_count}")

    reports_src = source_dir / "reading_reports.jsonl"
    reports_dst = output_dir / "reference_outputs" / "paperflow_reading_reports.jsonl"
    copy_reading_reports(reports_src, reports_dst)

    eval_src = PROJECT_ROOT / "experiments" / "benchmark" / "evaluate_benchmark_predictions.py"
    copy_if_exists(eval_src, output_dir / "evaluation" / "evaluate.py")
    submission_src = PROJECT_ROOT / "experiments" / "benchmark" / "make_benchmark_submission.py"
    copy_if_exists(submission_src, output_dir / "evaluation" / "make_submission.py")
    report_eval_src = PROJECT_ROOT / "experiments" / "benchmark" / "evaluate_report_outputs.py"
    copy_if_exists(report_eval_src, output_dir / "evaluation" / "evaluate_reports.py")
    (output_dir / "evaluation" / "README.md").write_text(evaluation_readme(), encoding="utf-8")
    (output_dir / "README.md").write_text(dataset_card(), encoding="utf-8")
    (output_dir / "VERSION").write_text("0.1.0\n", encoding="utf-8")
    (output_dir / ".gitignore").write_text("__pycache__/\n*.py[cod]\n*$py.class\n", encoding="utf-8")
    sanitize_release_text_files(output_dir)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--no-clean", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    prepare(args.source_dir, args.output_dir, clean=not args.no_clean)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
