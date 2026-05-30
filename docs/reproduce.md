# Reproducing the Paper

This guide covers reproducing the paper experiments and the public benchmark
evaluation. For the full step-by-step protocol, see also
[../experiments/REPRODUCE.md](../experiments/REPRODUCE.md).

## 1. Verify the install

```bash
pip install -e ".[all]"
paperflow demo
pytest -q
```

`paperflow demo` runs the bundled mock providers end-to-end. If it succeeds,
your install is good even before any API keys are configured.

## 2. Fetch the benchmark

PaperFlow-Bench is published on HuggingFace as
[OpenRaiser/PaperFlow](https://huggingface.co/datasets/OpenRaiser/PaperFlow).
Download it locally:

```bash
python experiments/benchmark/fetch_benchmark.py \
  --output-dir data/PaperFlow-Bench
```

The release contains:

- 24 simulated researchers
- 50 daily paper streams
- 1,200 user-day episodes
- 20,727 unique papers
- 497,448 episode-paper records
- pseudo-oracle relevance labels
- simulated reading selections and drift diagnostics

## 3. Evaluate a Top-20 submission

Prediction files use JSONL with one row per episode:

```json
{"episode_id": "user_role1::2026-03-01", "paper_ids": [37, 12, 88]}
```

Create a valid pool-rank example submission:

```bash
python experiments/benchmark/make_benchmark_submission.py \
  --benchmark-dir data/PaperFlow-Bench \
  --output predictions_pool_rank.jsonl
```

Convert a method output written as `episode_papers.jsonl`:

```bash
python experiments/benchmark/make_benchmark_submission.py \
  --source results/my_method/episode_papers.jsonl \
  --rank-field system_rank \
  --score-field system_score \
  --output predictions_my_method.jsonl
```

Run the evaluator:

```bash
paperflow eval \
  --benchmark-dir data/PaperFlow-Bench \
  --predictions predictions_pool_rank.jsonl \
  --output paperflow_eval.json
```

Or call the underlying script directly:

```bash
python experiments/benchmark/evaluate_benchmark_predictions.py \
  --benchmark-dir data/PaperFlow-Bench \
  --predictions predictions_pool_rank.jsonl \
  --output paperflow_eval.json
```

### Metrics

| Metric                | Meaning                                                       |
|-----------------------|---------------------------------------------------------------|
| `gNDCG@20`            | Graded oracle relevance ranking quality                       |
| `Useful@5`            | Fraction of Top-5 with non-zero oracle usefulness             |
| `Useful@20`           | Fraction of Top-20 with non-zero oracle usefulness            |
| `SelectedNDCG@20`     | Agreement with simulated downstream selections                |
| `StrictR@20+`         | Recall over strong oracle labels on positive episodes         |
| `MRR@20`              | Reciprocal rank of the first useful oracle item               |
| `Lift@20`             | Useful@20 relative to candidate-pool useful rate              |
| `RecommendationScore` | 0–100 composite score reported in the paper                   |

## 4. Reproduce the main experiment

```bash
# Linux / macOS
bash experiments/main_experiment/run_main_experiment.sh

# Windows
experiments\main_experiment\run_main_experiment.cmd
```

This runs all six baselines plus the PaperFlow main system, exports clean
benchmark outputs, and combines per-baseline tables into the paper-ready
summary.

## 5. Reproduce ablations

```bash
bash experiments/ablation/run_ablation.sh
```

The ablation runner walks through the component-removal configurations
described in the paper (drift on/off, anchor on/off, freshness term on/off,
etc.) and aggregates the results into a combined ablation table.

## 6. Reproduce drift, LLM comparison, and token cost

```bash
bash experiments/drift/run_drift_experiment.sh
bash experiments/llm_comparison/run_llm_comparison.sh
bash experiments/token_cost/run_token_cost.sh
```

Each runner is self-contained and writes its summary table under
`results/<experiment-name>/` with both raw per-episode outputs and aggregated
summaries.

## 7. Reproduce reading-report quality

```bash
bash experiments/reading_reports/run_reading_reports.sh
```

This generates reading reports across the benchmark sample, evaluates them
using the bundled rubric prompts, and writes a per-rubric summary CSV.

## 8. Rebuild HuggingFace package (maintainers)

```bash
python experiments/benchmark/prepare_hf_benchmark_package.py
```

Output goes to `release/huggingface/PaperFlow-Bench/`. This directory can be
uploaded to a HuggingFace dataset repository as a single push.

## 9. Notes for the LLM-comparison runtime

Full LLM runtime packages are intentionally not released. They are reproducible
artifacts, not source code, and may contain API-specific logs or generated
reading-report caches. Re-run them from `experiments/llm_comparison/` and
summarize the resulting output instead of committing per-model caches.
