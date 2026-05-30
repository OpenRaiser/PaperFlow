# Natural-Language User Profile BM25 Baseline Design

## Purpose

This baseline represents a paper-faithful natural-language user profile retrieval setting inspired by SciNUP. It is used as the official NL-profile baseline in the PaperFlow main experiment.

Unlike the stronger `baselines/nl_profile` adaptation, this strict baseline does not use PaperFlow-specific direction expansion, keyphrase boosts, aspect coverage, feedback updates, interest drift, must-read rules, reading reports, or oracle labels during ranking.

## Inputs

The runner only reads the clean baseline package:

```text
<benchmark_output>/baseline_clean_input/
  candidate_pools.jsonl
  labels_for_eval.jsonl
  episodes.jsonl
  users.json
  manifest.json
```

`candidate_pools.jsonl` is used for ranking. `labels_for_eval.jsonl` is used only after ranking for evaluation.

## Ranking

For each user, the baseline builds one frozen text query from cold-start profile text and seed direction phrases. For each daily episode, it ranks candidate papers with BM25 over `title + abstract`.

The output method name is:

```text
Natural-Language User Profile Recommendation
```

## Command

```cmd
python scripts\run_scinup_strict_baseline.py ^
  --input-dir <benchmark_output>\baseline_clean_input ^
  --output-dir <benchmark_output>\main_experiment\nl_profile
```

Convenience command:

```cmd
run_nl_profile_baseline_clean.cmd
```
