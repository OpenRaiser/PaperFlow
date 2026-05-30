# Reproducing the PaperFlow Paper

Every table and figure in the paper is reachable from a launcher under
`experiments/`. Each kind of experiment lives in its own purpose folder —
`benchmark/`, `main_experiment/`, `ablation/`, `drift/`, `llm_comparison/`,
`token_cost/`, `simulation/`, `analysis/`, and `human_eval/`. This document
is the linear recipe for reproducing the headline results.

## 0. Prerequisites

```bash
# Create a fresh environment (conda or venv).
conda env create -f environment.yml
conda activate paperflow

# Or with pip:
pip install -r requirements.txt
pip install -e .

# Configure credentials. Copy .env.example -> .env and fill in your provider
# choice (PAPERFLOW_LLM_PROVIDER / PAPERFLOW_EMBED_PROVIDER + the matching
# API key or local model path).
cp .env.example .env
```

## 1. Fetch the published benchmark

```bash
python experiments/benchmark/fetch_benchmark.py --output-dir data/PaperFlow-Bench
```

This downloads `OpenRaiser/PaperFlow` from Hugging Face into
`data/PaperFlow-Bench/`. The directory follows the same layout the original
benchmark was built with:

```
data/PaperFlow-Bench/
├── data/
│   ├── users.jsonl
│   ├── episodes.jsonl
│   ├── papers.jsonl
│   ├── episode_labels.jsonl
│   └── drift_timeline.jsonl
├── reference_outputs/
│   └── paperflow_reading_reports.jsonl
└── evaluation/
    ├── evaluate.py
    ├── make_submission.py
    └── evaluate_reports.py
```

## 2. Sanity-check the evaluator

```bash
python experiments/benchmark/make_benchmark_submission.py \
  --benchmark-dir data/PaperFlow-Bench \
  --output predictions_pool_rank.jsonl

python experiments/benchmark/evaluate_benchmark_predictions.py \
  --benchmark-dir data/PaperFlow-Bench \
  --predictions predictions_pool_rank.jsonl \
  --output paperflow_eval_check.json
```

`paperflow_eval_check.json` should contain `gNDCG@20`, `Useful@5`,
`Useful@20`, `SelectedNDCG@20`, `StrictR@20+`, `MRR@20`, `Lift@20`, and
`RecommendationScore`.

## 3. Main experiment (Table: Top-20 comparison)

The full main experiment exports the contamination-safe baseline input,
runs all five reranking baselines, and combines their metrics with the Full
PaperFlow row.

```bash
# Linux / macOS
experiments/main_experiment/run_main_experiment.sh \
  data/benchmark_full_24users_20260301_20260419_show20_with_reading

# Windows (cmd)
experiments\main_experiment\run_main_experiment.cmd ^
  data\benchmark_full_24users_20260301_20260419_show20_with_reading

# Windows (PowerShell)
experiments\main_experiment\run_main_experiment.ps1 `
  -BenchmarkDir data\benchmark_full_24users_20260301_20260419_show20_with_reading
```

Outputs:
- `<BENCHMARK_DIR>/main_experiment/<baseline>/evaluation_metrics.json`
- `<BENCHMARK_DIR>/main_experiment/main_experiment_comparison_top20.md`
- `<BENCHMARK_DIR>/main_experiment/main_experiment_comparison_top20.csv`

To regenerate just one baseline:

```bash
experiments/main_experiment/run_clean/run_scholar_inbox.sh
```

## 4. Reading-report benchmark

```bash
# 3-user case (faster).
experiments/benchmark/run_reading_benchmark.sh case

# Full 24-user run.
experiments/benchmark/run_reading_benchmark.sh full
```

Each mode writes to `data/benchmark_<mode>_*` with `reading_reports.jsonl`,
`evaluation_metrics.json`, and `main_experiment_table_top20.md`.

To re-run the full PaperFlow pipeline (simulation + evaluation +
human-audit export):

```bash
experiments/benchmark/run_full_benchmark.sh
```

## 5. Ablations

```bash
# Profile ablations (with checkpointing).
python experiments/ablation/run_paperflow_fixed_profile_ablation_resumable.py \
  --benchmark-dir data/benchmark_full_24users_20260301_20260419_show20_with_reading

# Mechanism ablation (with checkpointing).
python experiments/ablation/run_paperflow_mechanism_ablation_resumable.py \
  --benchmark-dir data/benchmark_full_24users_20260301_20260419_show20_with_reading
```

## 6. Drift adaptation table

```bash
python experiments/drift/build_drift_adaptation_experiment.py \
  --benchmark-dir data/benchmark_full_24users_20260301_20260419_show20_with_reading
```

## 7. LLM-model cost / quality table

```bash
python experiments/llm_comparison/build_llm_model_comparison_table.py
```

## 8. Token usage

```bash
# Per-day measurement.
python experiments/token_cost/measure_day_token_usage.py

# Aggregate from the running token log.
python experiments/token_cost/token_usage_tracker.py \
  --start-date 20260301 --end-date 20260420
```

## 9. Human-evaluation aggregates and figures

The aggregated, PII-free results live under
`experiments/human_eval/results/`. To recompute them or redraw the paper
figures:

```bash
# Recompute aggregates from raw packets (raw packets are not redistributed).
python experiments/human_eval/aggregate_main_human_eval.py
python experiments/human_eval/aggregate_drift_human_eval.py
python experiments/human_eval/aggregate_model_human_eval.py

# Redraw the figures.
python experiments/human_eval/draw_error_analysis_figure.py
python experiments/human_eval/draw_interest_drift_paperflow_style.py
python experiments/human_eval/draw_llm_token_cost_bar.py
python experiments/human_eval/draw_model_eval_ggbench_style.py
```

## 10. Repackage the HuggingFace dataset (maintainers only)

```bash
python experiments/benchmark/prepare_hf_benchmark_package.py
```

This rewrites `release/huggingface/PaperFlow-Bench/` from the local
benchmark output. Only the project maintainers need to run this.
