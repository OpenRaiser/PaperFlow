# Human Evaluation Scripts

This folder contains reproducible utilities for PaperFlow human evaluation.

For multi-annotator distribution, use the self-contained packages under
`scripts/human_eval/packages/`. The main-experiment package is already bundled
with its sampled evaluation data, and the drift package is bundled with its
sampled drift-evaluation data plus three annotator packet folders:

```text
scripts/human_eval/packages/main_human_eval
scripts/human_eval/packages/drift_human_eval
```

## Main Experiment: HumanEval

Build the blind annotation packet:

```powershell
python scripts/human_eval/build_main_human_eval_packet.py `
  --episodes-per-method 12 `
  --papers-per-episode 2 `
  --output-dir data/benchmark_full_24users_20260301_20260419_show20_with_reading/evaluation/main_human_eval
```

Annotators fill only:

- `HumanRelevance`
- `HumanUsefulness`
- `DecisionHelpfulness`
- `comments`

Aggregate the filled annotations:

```powershell
python scripts/human_eval/aggregate_main_human_eval.py `
  --blind-csv data/benchmark_full_24users_20260301_20260419_show20_with_reading/evaluation/main_human_eval/main_human_eval_blind.csv `
  --key-csv data/benchmark_full_24users_20260301_20260419_show20_with_reading/evaluation/main_human_eval/main_human_eval_key.csv `
  --output-dir data/benchmark_full_24users_20260301_20260419_show20_with_reading/evaluation/main_human_eval
```

`main_human_eval_episode_scores.csv` is the correlation-ready file for
`RecommendationScore` vs. `HumanEval`.

## LLM Model Comparison: ModelHumanScore

Build the blind model-comparison packet:

```powershell
python scripts/human_eval/build_model_human_eval_packet.py `
  --reports-per-model 12 `
  --output-dir data/benchmark_full_24users_20260301_20260419_show20_with_reading/evaluation/model_human_eval
```

Annotators fill only:

- `HumanRelevance`
- `HumanUsefulness`
- `RecommendationDecisionHelpfulness`
- `ReportFaithfulness`
- `ReportSpecificity`
- `ReportDecisionHelpfulness`
- `comments`

Aggregate the filled annotations:

```powershell
python scripts/human_eval/aggregate_model_human_eval.py `
  --blind-csv data/benchmark_full_24users_20260301_20260419_show20_with_reading/evaluation/model_human_eval/model_human_eval_blind.csv `
  --key-csv data/benchmark_full_24users_20260301_20260419_show20_with_reading/evaluation/model_human_eval/model_human_eval_key.csv `
  --output-dir data/benchmark_full_24users_20260301_20260419_show20_with_reading/evaluation/model_human_eval
```

If a model automatic-metrics CSV is available, pass it with
`--auto-summary-csv`. The aggregator will derive:

```text
ReportAutoScore = 100 * (0.70 * SectionCompleteness + 0.30 * EvidenceCoverage)
ModelAutoScore = 0.80 * RecommendationScore
               + 0.20 * ReportAutoScore
```

where `SectionCompleteness` is implemented by `ReportStructureScore` and
`EvidenceCoverage` is implemented by `ReportEvidenceRate` in the current logs.
`ParsingSuccess` is treated as a diagnostic field rather than a main-table
metric because completed model runs currently achieve 100% non-empty report
generation success.
`model_human_eval_model_summary.csv` is the correlation-ready file for
`ModelAutoScore` vs. `ModelHumanScore`.

## Drift Adaptation: AdaptationHumanScore

Build the blind drift-adaptation packet:

```powershell
python scripts/human_eval/build_drift_human_eval_packet.py `
  --papers-per-event 2 `
  --post-days 7 `
  --output-dir data/benchmark_full_24users_20260301_20260419_show20_with_reading/evaluation/drift_human_eval
```

Annotators fill only:

- `NewTopicFit`
- `AdaptationAppropriateness`
- `OldNewBalance`
- `DriftDecisionHelpfulness`
- `comments`

Aggregate the filled annotations:

```powershell
python scripts/human_eval/aggregate_drift_human_eval.py `
  --blind-csv data/benchmark_full_24users_20260301_20260419_show20_with_reading/evaluation/drift_human_eval/drift_human_eval_blind.csv `
  --key-csv data/benchmark_full_24users_20260301_20260419_show20_with_reading/evaluation/drift_human_eval/drift_human_eval_key.csv `
  --output-dir data/benchmark_full_24users_20260301_20260419_show20_with_reading/evaluation/drift_human_eval
```

`drift_human_eval_event_scores.csv` is the correlation-ready file for
`DriftAutoScore` vs. `AdaptationHumanScore` on sampled method-drift-event
pairs. In this human-evaluation folder, `DriftAutoScore` is a sample-aligned
automatic proxy derived from new-topic match, old-topic suppression, selected
status, and rank.

## Consolidated Results

The summarized results tables live in `scripts/human_eval/results/`:

- `results_overview.csv`
- `results.md`
- `listwise_annotator_agreement.csv`

The main experiment human eval is the three-file listwise behavior set:
`listwise_behavior_human_filled_1.csv`, `listwise_behavior_human_filled_2.csv`,
and `listwise_behavior_human_filled_3.csv`.
