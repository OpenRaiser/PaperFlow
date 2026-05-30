# Discourse-Aware Content Recommendation Baseline Design

## Purpose

This document defines the `Discourse-Aware Content Recommendation` baseline for the PaperFlow main experiment.

The goal is to represent scholarly recommendation methods that improve content matching by modeling paper discourse structure, such as problem, method, result, contribution, and resource signals. This baseline is intentionally narrower than Full PaperFlow: it does not maintain structured profile updates, does not model interest drift states, and does not use reading-report generation or feedback.

## Reference Method

This baseline is aligned with the method family represented by:

```text
Wang and Yin.
Discourse-Aware Scientific Paper Recommendation via QA-Style Summarization and Multi-Level Contrastive Learning.
arXiv, 2025.
https://arxiv.org/abs/2511.03330
```

The original paper emphasizes discourse-aware scientific-paper representations. In the PaperFlow benchmark, candidates are frozen daily paper pools with title and abstract metadata. Therefore, this baseline implements the same high-level method family as a deterministic offline reranker over clean benchmark inputs, rather than reproducing the original paper's full QA-style summarization and contrastive training pipeline.

## Method Family

This baseline corresponds to content-understanding enhanced scholarly recommendation methods that combine:

- Paper text matching between the user profile/history and candidate papers.
- Discourse or rhetorical-role signals extracted from the paper title and abstract.
- Stronger weighting for method/contribution/result-bearing text than for generic background text.
- A fixed daily ranking procedure over the same candidate pool.

## Clean Input Contract

This baseline uses the same clean input package as the other main-experiment baselines:

```text
<benchmark_output>/baseline_clean_input/
  candidate_pools.jsonl
  labels_for_eval.jsonl
  episodes.jsonl
  users.json
  manifest.json
```

`candidate_pools.jsonl` is the only file used for same-day scoring. It excludes Full PaperFlow method fields such as `shown`, `system_score`, `system_label`, `system_rank`, `drift_bonus`, `reading_signal_bonus`, and `ranking_source`.

`labels_for_eval.jsonl` is used only after ranking for chronological feedback updates and post-ranking evaluation. `oracle_label` and `oracle_score` are evaluation-only fields and must never be used for scoring or training.

`users.json` is sanitized to cold-start metadata only. Dynamic profile snapshots, drift states, report preferences, and updated profile fields are stripped before the baseline can read them.

## Allowed Inputs

For each `user x day` episode, the baseline may use:

- The frozen daily paper pool from clean `candidate_pools.jsonl`.
- Paper title and abstract.
- Fixed cold-start user evidence from sanitized `users.json` and `data/roles.json`.
- Previous selected papers from earlier days only.
- Rule-based discourse facets extracted from title and abstract.

## Forbidden Inputs

The baseline must not use:

- Current-day selected papers before ranking.
- Future user feedback.
- `oracle_label` or `oracle_score` during ranking.
- Full PaperFlow `shown`, `system_score`, `system_label`, `system_rank`, `drift_bonus`, or `reading_signal_bonus`.
- PaperFlow-updated dynamic profiles, drift states, reading reports, report quality feedback, or weekly reports.
- PDF enrichment, source-page parsing, or LLM-generated reading reports.
- Live external APIs during ranking.

## Discourse Facets

The implementation extracts deterministic discourse facets from `title + abstract`:

| Facet | Meaning | Example cues |
|---|---|---|
| `title` | Paper title signal | title text |
| `problem` | Research gap or challenge | challenge, limitation, gap, difficult |
| `method` | Proposed method or system | we propose, framework, model, algorithm |
| `result` | Empirical or analytical result | experiments, outperform, demonstrate |
| `contribution` | Claimed novelty or contribution | contribution, novel, first, insight |
| `resource` | Dataset, benchmark, code, corpus | dataset, benchmark, code, release |
| `background` | General motivation or prior work | recent, prior, existing |
| `general` | Sentences without a specific cue | fallback facet |

The facet extractor is intentionally rule-based so that the baseline is deterministic, reproducible, and runnable without extra LLM cost.

## Ranking Model

The baseline scores each candidate paper with three components:

```text
DiscourseAwareScore(p, u, t) =
  0.70 * FacetSimilarity(p, u, <t)
+ 0.20 * DiscourseCoverage(p)
+ 0.10 * ContributionSignal(p)
```

Where:

- `FacetSimilarity` is TF-IDF similarity computed facet-by-facet against the fixed initial profile and previous selected papers.
- Previous selected papers are split into the same discourse facets and used only after the corresponding day has already been ranked.
- `DiscourseCoverage` rewards candidates whose abstracts expose more key scientific facets, especially problem/method/result/contribution/resource.
- `ContributionSignal` rewards papers that explicitly state method, result, contribution, or resource information.

The weights remain fixed across all users and days.

## Daily Episode Procedure

For each user, process episodes chronologically.

For each day:

1. Load the daily candidate pool for the `user x day` episode.
2. Extract discourse facets from each candidate title and abstract.
3. Build facet-level TF-IDF representations using the fixed cold-start profile and previous selected papers only.
4. Score every candidate paper with discourse-aware content signals.
5. Sort by `DiscourseAwareScore` descending.
6. Mark the top 20 papers as `shown = true`.
7. Assign `system_rank` from 1 to 20 for shown papers.
8. Preserve `oracle_*` fields only for evaluation compatibility.
9. After the day has been ranked, update historical selected-paper memory for the next day.

Important: current-day labels are used only after ranking.

## System Labels

The baseline outputs the same system-label vocabulary used by the evaluation script:

```text
score >= 0.70 -> high_relevant
0.45 <= score < 0.70 -> maybe_interested
score < 0.45 -> edge_relevant
```

This baseline should not emit `must_read`, because it has no hard must-read mechanism.

## Expected Behavior

Expected strengths:

- Should perform better than plain content matching when abstracts clearly expose method/result/contribution cues.
- Should favor papers whose discourse facets align with the user's profile and selected-paper history.
- Should be a strong content-understanding baseline without using PaperFlow's dynamic reading loop.

Expected weaknesses:

- It depends on title/abstract cues and does not parse full PDFs.
- It cannot adapt to interest drift except through previous selected papers.
- It cannot use reading-report quality feedback.
- It cannot represent user-specific must-read constraints.

## Difference From Full PaperFlow Pipeline

| Capability | Discourse-Aware Baseline | Full PaperFlow Pipeline |
|---|---:|---:|
| Daily personalized ranking | yes | yes |
| Fixed cold-start support | yes | yes |
| Previous selected-paper feedback | yes | yes |
| Discourse/content-structure signals | yes | partial |
| Structured profile updates | no | yes |
| Hard must-read priority | no | yes |
| Interest drift state | no | yes |
| Reading-report generation | no | yes |
| Reading-report feedback | no | yes |
| Weekly explanation/report | no | yes |

## Implementation Notes

Runnable script:

```text
python scripts/export_clean_baseline_benchmark.py --input-dir <benchmark_output>
python scripts/run_discourse_aware_baseline.py --input-dir <benchmark_output>/baseline_clean_input
```

Recommended command:

```cmd
run_discourse_aware_baseline_clean.cmd
```

Recommended output directory:

```text
<benchmark_output>/main_experiment/discourse_aware/
```

Current implementation:

```text
baselines/discourse_aware/runner.py
scripts/run_discourse_aware_baseline.py
```
