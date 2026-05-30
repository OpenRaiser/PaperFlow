# PaperFlow Experiments

This directory contains every experiment reported in the PaperFlow paper, in
runnable form. Each script reads the public PaperFlow-Bench dataset and writes
its outputs under `data/`.

## Layout

Experiments are organized by purpose. Each subfolder owns one slice of the
paper's empirical work, and its contents are self-contained.

```
experiments/
├── README.md              # This file (overview).
├── REPRODUCE.md           # Step-by-step reproduction recipe.
├── baselines/             # Six recommendation baselines (per-method runners + design.md).
├── benchmark/             # Benchmark fetch / evaluate / submit + full + reading runs.
├── main_experiment/       # Top-20 main comparison + per-baseline launchers + table builders.
├── ablation/              # Profile ablations + mechanism ablation (resumable).
├── drift/                 # Drift adaptation table.
├── llm_comparison/        # LLM cost / quality comparison table.
├── token_cost/            # Per-day and aggregate token-usage measurements.
├── simulation/            # Historical / case / feedback simulators.
├── analysis/              # Human-vs-auto score correlation analysis.
├── human_eval/            # Aggregated human-evaluation analysis + figure scripts.
├── results/               # Public, PII-free aggregate results for sanity-checking.
├── tests/                 # Tests pinned to experiment-only modules (baselines, simulators).
└── data/                  # Generated experiment artifacts (git-ignored, with `.gitkeep`).
```

### Per-folder contents

```
benchmark/
├── fetch_benchmark.py
├── make_benchmark_submission.py
├── evaluate_benchmark_predictions.py
├── evaluate_report_outputs.py
├── evaluate_simulation_metrics.py
├── export_clean_baseline_benchmark.py
├── export_daily_data.py
├── export_human_audit_subset.py
├── prepare_hf_benchmark_package.py
├── run_full_benchmark.{cmd,sh}
└── run_reading_benchmark.{cmd,sh}

main_experiment/
├── _combine_baseline_tables.py            # Shared helper used by both shell launchers.
├── build_main_experiment_overall_table.py
├── build_main_experiment_extended_table.py
├── build_main_experiment_metric_suite.py
├── run_baselines/                         # Per-baseline Python launchers.
├── run_clean/                             # Single-baseline shell wrappers (.cmd + .sh).
└── run_main_experiment.{cmd,ps1,sh}       # Full main experiment with combined table.

ablation/
├── run_paperflow_fixed_profile_ablation.py
├── run_paperflow_fixed_profile_ablation_resumable.py
└── run_paperflow_mechanism_ablation_resumable.py

drift/
└── build_drift_adaptation_experiment.py

llm_comparison/
└── build_llm_model_comparison_table.py

token_cost/
├── measure_day_token_usage.py
└── token_usage_tracker.py

simulation/
├── simulate_historical_episodes.py
├── simulate_case_episodes.py
└── simulate_feedback.py

analysis/
└── analyze_human_score_correlation.py
```

## Provided Experiments

| Script | What it produces |
|--------|------------------|
| `main_experiment/run_main_experiment.{cmd,ps1,sh}` | All five reranking baselines + Full PaperFlow rows in one comparison table (`main_experiment_comparison_top20.{md,csv}`). |
| `main_experiment/run_clean/run_<baseline>.{cmd,sh}` | A single baseline (Scholar Inbox / Citation-Enhanced / Discourse-Aware / NL-Profile / Knowledge-Entity / SciNUP-Strict) on the contamination-safe input. |
| `benchmark/run_full_benchmark.{cmd,sh}` | End-to-end PaperFlow simulation, evaluation, and human-audit subset export. |
| `benchmark/run_reading_benchmark.{cmd,sh}` | Reading-report benchmark in `case` (3 users) or `full` (24 users) mode. |
| `ablation/run_paperflow_*_ablation*.py` | Profile-ablation and mechanism-ablation studies. |
| `drift/build_drift_adaptation_experiment.py` | Drift adaptation table. |
| `llm_comparison/build_llm_model_comparison_table.py` | LLM cost / quality comparison table. |
| `simulation/simulate_*.py` | Historical / case / feedback simulators. |
| `token_cost/measure_day_token_usage.py`, `token_cost/token_usage_tracker.py` | Token-cost accounting. |
| `main_experiment/build_*.py`, `drift/build_*.py`, `llm_comparison/build_*.py` | Generate the markdown/CSV tables that appear in the paper. |
| `human_eval/aggregate_*.py` + `human_eval/draw_*.py` | Recompute aggregated human-evaluation tables and rendered figures. |

## Quick Start

```bash
# 1. Pull the published benchmark.
python experiments/benchmark/fetch_benchmark.py --output-dir data/PaperFlow-Bench

# 2. Make a sample submission and evaluate it (sanity check).
python experiments/benchmark/make_benchmark_submission.py \
  --benchmark-dir data/PaperFlow-Bench \
  --output predictions_pool_rank.jsonl

python experiments/benchmark/evaluate_benchmark_predictions.py \
  --benchmark-dir data/PaperFlow-Bench \
  --predictions predictions_pool_rank.jsonl \
  --output paperflow_eval_check.json

# 3. Run the full main experiment (all five baselines + Full PaperFlow).
#    Pick the launcher for your platform.
experiments/main_experiment/run_main_experiment.sh \
  data/benchmark_full_24users_20260301_20260419_show20_with_reading

experiments\main_experiment\run_main_experiment.cmd ^
  data\benchmark_full_24users_20260301_20260419_show20_with_reading
```

For the complete recipe — including how to regenerate the benchmark from
scratch, run ablations, and reproduce the human-evaluation figures — see
[`REPRODUCE.md`](./REPRODUCE.md).

## Notes

- All Python scripts anchor `PROJECT_ROOT` from `__file__`, so they work
  regardless of the current working directory.
- The shell launchers always change into the project root before invoking
  Python, so paths like `data/...` resolve consistently across platforms.
- Per-rater raw human-evaluation scores are intentionally not redistributed.
  Only the PII-free aggregated results live under `experiments/human_eval/results/`.
- Set `PYTHON=...` to point the launchers at a specific interpreter
  (e.g. `PYTHON=python3.11 experiments/main_experiment/run_main_experiment.sh`).
