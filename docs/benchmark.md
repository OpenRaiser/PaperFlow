# PaperFlow-Bench

PaperFlow-Bench evaluates dynamic personalized scientific reading as
sequential user-day Top-20 recommendation.

## Dataset Summary

The main benchmark contains:

| Quantity | Value |
| --- | ---: |
| Simulated research users | 24 |
| Daily paper streams | 50 |
| User-day episodes | 1,200 |
| Unique papers | 20,727 |
| Episode-paper records | 497,448 |
| PaperFlow reading reports | 3,104 |
| Display budget | Top-20 |

The benchmark fixes users, dates, candidate pools, visible inputs, hidden
pseudo-oracle labels, and simulated behavior labels.

## Local Source Data

The full local benchmark lives under:

```text
data/benchmark_full_24users_20260301_20260419_show20_with_reading/
```

Important files:

| File | Purpose |
| --- | --- |
| `users.json` | Simulated user metadata and seed directions. |
| `episodes.jsonl` | One row per user-day episode. |
| `paper_pools.jsonl` | Date-level candidate paper pools. |
| `episode_papers.jsonl` | Full episode-paper records with labels and behavior. |
| `reading_reports.jsonl` | Full PaperFlow-generated reading reports for selected papers. |
| `evaluation_metrics.json` | Full PaperFlow metric output. |
| `main_experiment/` | Baseline and ablation outputs. |

The original files are not meant for GitHub. Use the packaging script to create
a HuggingFace-ready release:

```bash
python experiments/benchmark/prepare_hf_benchmark_package.py
```

## HuggingFace Package Layout

The script writes:

```text
release/huggingface/PaperFlow-Bench/
|-- README.md
|-- VERSION
|-- data/
|   |-- users.json
|   |-- episodes.jsonl
|   |-- papers.jsonl
|   |-- episode_labels.jsonl
|   `-- drift_timeline.jsonl
|-- reference_outputs/
|   `-- paperflow_reading_reports.jsonl
`-- evaluation/
    |-- evaluate.py
    |-- make_submission.py
    |-- evaluate_reports.py
    `-- README.md
```

## Label Fields

`papers.jsonl` contains deduplicated paper metadata. Each row includes
`paper_id`, `arxiv_id`, `abs_url`, `pdf_url`, `title`, `abstract`, `authors`,
`institution`, `venue`, `source`, `url`, and `publish_date`.

`episode_labels.jsonl` contains one row per episode-paper pair:

| Field | Meaning |
| --- | --- |
| `episode_id` | User-day episode id. |
| `user_id` | User id. |
| `date` | Recommendation date. |
| `paper_id` | Candidate paper id. |
| `oracle_label` | Pseudo-oracle relevance label. |
| `oracle_score` | Numeric pseudo-oracle score. |
| `selected` | Whether the simulated user selected the paper. |
| `shown` | Whether PaperFlow displayed it in the source Top-20 list. |
| `system_label` | Diagnostic system tier. |

Pseudo-oracle labels:

```text
strong_relevant > relevant > weak_relevant > irrelevant
```

## Submission Format

Each submission file uses JSONL:

```json
{"episode_id": "user_role1::2026-03-01", "paper_ids": [37, 12, 88]}
```

`paper_ids` are interpreted as ranked predictions. The evaluator truncates to
Top-20.

To generate a valid pool-rank example submission from the packaged benchmark:

```bash
python evaluation/make_submission.py \
  --benchmark-dir release/huggingface/PaperFlow-Bench \
  --output predictions_pool_rank.jsonl
```

To convert a method output written as episode-paper rows, use the same helper
with the method output file:

```bash
python experiments/benchmark/make_benchmark_submission.py \
  --source results/my_method/episode_papers.jsonl \
  --rank-field system_rank \
  --score-field system_score \
  --output predictions_my_method.jsonl
```

Then evaluate:

```bash
paperflow eval \
  --benchmark-dir release/huggingface/PaperFlow-Bench \
  --predictions predictions_pool_rank.jsonl \
  --output paperflow_eval.json
```

## Reading-Report Outputs

The package also includes all PaperFlow-generated reading reports:

```text
reference_outputs/paperflow_reading_reports.jsonl
```

These records are reference system outputs for the reading-assist component,
not gold summaries. They allow readers to inspect the full recommendation to
feedback to report-generation loop and to compare report-generation runs with
the same automatic report metrics.

Run:

```bash
python evaluation/evaluate_reports.py \
  --benchmark-dir release/huggingface/PaperFlow-Bench \
  --reports reference_outputs/paperflow_reading_reports.jsonl
```

The report evaluator computes coverage, non-empty success rate, full-text
source rate, evidence coverage, structure completeness, `ReportAutoScore`, and
`ReportProxyScore`.
