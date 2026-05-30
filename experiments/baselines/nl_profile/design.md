# Natural-Language User Profile Recommendation Baseline Design

## Purpose

This document defines the `Natural-Language User Profile Recommendation` baseline for the PaperFlow main experiment.

The goal is to represent scholarly recommendation methods that use explicit natural-language user interest profiles as the primary recommendation signal. This baseline is intentionally narrower than Full PaperFlow: it uses a fixed natural-language profile built from cold-start evidence, but it does not update that profile from daily feedback, does not model interest drift, and does not use reading-report feedback.

## Reference Method

This baseline is aligned with the method family represented by:

```text
Arustashvili and Balog.
SciNUP: Natural Language User Interest Profiles for Scientific Literature Recommendation.
arXiv, 2025.
https://arxiv.org/abs/2510.21352
```

SciNUP introduces a benchmark for scientific literature recommendation based on natural-language user interest profiles generated from authors' publication histories. The paper compares sparse retrieval, dense retrieval, and LLM-based reranking methods over explicit NL profiles and candidate papers.

PaperFlow's benchmark unit is `user x day`, not SciNUP's synthetic author-profile dataset. Therefore, this baseline adapts the SciNUP method family by constructing a fixed NL profile from sanitized cold-start metadata and using it to rerank the same daily candidate pools as Full PaperFlow.

## Method Family

This baseline corresponds to natural-language profile based recommendation methods that combine:

- A human-readable textual profile of the user's research interests.
- Paper text matching between the NL profile and candidate titles/abstracts.
- Soft keyphrase and aspect matching from the profile.
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

`labels_for_eval.jsonl` is used only after ranking for post-ranking evaluation. This baseline does not use selected papers to update the profile.

`users.json` is sanitized to cold-start metadata only. Dynamic profile snapshots, drift states, report preferences, and updated profile fields are stripped before the baseline can read them.

## Allowed Inputs

For each `user x day` episode, the baseline may use:

- The frozen daily paper pool from clean `candidate_pools.jsonl`.
- Paper title and abstract.
- Fixed cold-start user evidence from sanitized `users.json` and `data/roles.json`.
- A fixed natural-language profile generated before evaluation begins.
- Static profile terms derived from initial directions and role bootstrap keywords.

## Forbidden Inputs

The baseline must not use:

- Current-day selected papers before ranking.
- Previous selected papers for profile updates.
- Future user feedback.
- `oracle_label` or `oracle_score` during ranking.
- Full PaperFlow `shown`, `system_score`, `system_label`, `system_rank`, `drift_bonus`, or `reading_signal_bonus`.
- PaperFlow-updated dynamic profiles, drift states, reading reports, report quality feedback, or weekly reports.
- PDF enrichment, source-page parsing, or LLM-generated reading reports.
- Live external APIs during ranking.

## Natural-Language Profile Construction

For each user, the baseline builds a fixed NL profile from clean cold-start evidence:

```text
The researcher is interested in <seed directions>.
Research context: <sanitized user/role description>.
Profile summary: <role bootstrap summary>.
Relevant concepts include <expanded direction terms and initial keywords>.
Recommend papers whose title and abstract match these stated research interests.
```

The generated profile is transparent and text-based, matching the core motivation of NL profile recommendation. It is not edited, updated, or drift-adjusted after daily feedback.

## Ranking Model

The baseline scores each candidate paper with four components:

```text
NLProfileScore(p, u, t) =
  0.65 * ProfileSimilarity(p, NLProfile_u)
+ 0.20 * KeyphraseAlignment(p, NLProfile_u)
+ 0.10 * TitleAlignment(p, NLProfile_u)
+ 0.05 * AspectCoverage(p, NLProfile_u)
```

Where:

- `ProfileSimilarity` is TF-IDF similarity between the fixed NL profile and `title + abstract`.
- `KeyphraseAlignment` measures exact phrase matches between profile terms and candidate text.
- `TitleAlignment` gives a small boost when profile terms appear in the paper title.
- `AspectCoverage` measures how many initial research directions are represented in candidate text.

The weights remain fixed across all users and days.

This is an offline benchmark adaptation, not a full reproduction of SciNUP's dataset creation process or LLM reranking experiments. The goal is to represent the NL-profile method family fairly under PaperFlow's unified daily benchmark.

## Daily Episode Procedure

For each user, build one fixed NL profile before ranking begins.

For each day:

1. Load the daily candidate pool for the `user x day` episode.
2. Score every candidate paper against the fixed NL profile.
3. Sort by `NLProfileScore` descending.
4. Mark the top 20 papers as `shown = true`.
5. Assign `system_rank` from 1 to 20 for shown papers.
6. Preserve `oracle_*` fields only for evaluation compatibility.
7. Do not update the profile after selected or skipped papers.

Important: current-day labels are never used during ranking.

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

- Should work well when the fixed NL profile clearly matches candidate titles and abstracts.
- Produces transparent profile terms and profile-to-paper scoring diagnostics.
- Provides a clean baseline for comparing static NL-profile recommendation against PaperFlow's dynamic profile loop.

Expected weaknesses:

- It cannot learn from daily feedback.
- It cannot distinguish stable interests from new observing or shifting interests.
- It cannot use reading-report quality feedback.
- It cannot represent hard must-read constraints.
- It may underperform when the user's cold-start profile is sparse or stale.

## Difference From Full PaperFlow Pipeline

| Capability | NL Profile Baseline | Full PaperFlow Pipeline |
|---|---:|---:|
| Daily personalized ranking | yes | yes |
| Fixed cold-start support | yes | yes |
| Natural-language profile | yes | yes |
| Previous selected-paper feedback | no | yes |
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
python scripts/run_nl_profile_baseline.py --input-dir <benchmark_output>/baseline_clean_input
```

Recommended command:

```cmd
run_nl_profile_baseline_clean.cmd
```

Recommended output directory:

```text
<benchmark_output>/main_experiment/nl_profile/
```

Current implementation:

```text
baselines/nl_profile/runner.py
scripts/run_nl_profile_baseline.py
```
