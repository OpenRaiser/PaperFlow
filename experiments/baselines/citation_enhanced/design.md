# Citation-Enhanced Literature Recommendation Baseline Design

## Purpose

This document defines the `Citation-Enhanced Literature Recommendation` baseline for the PaperFlow main experiment.

The goal is to represent scientific-paper recommendation methods that enhance content matching with citation-network, bibliographic-coupling, and external-impact signals. This baseline is intentionally narrower than Full PaperFlow: it does not maintain structured profile updates, does not model interest drift states, and does not use reading-report feedback.

## Reference Method

This baseline is aligned with the method family represented by:

```text
Liu et al.
Academic Literature Recommendation in Large-scale Citation Networks Enhanced by Large Language Models.
arXiv, 2025.
https://arxiv.org/abs/2503.01189
```

The original paper constructs a large citation network and combines network-based citation patterns with content-based semantic similarities over titles and abstracts. Its recommendation setting starts from a matched article or keyword query, then ranks papers from the reference list and citation list using weighted title, abstract, and node-similarity signals.

PaperFlow's benchmark unit is `user x day`, not a single query-paper session. Therefore, this baseline adapts the reference method by treating the user's previous selected papers as chronological query/history evidence. This preserves the paper's citation-network plus content-similarity idea while making it comparable under the same daily personalized candidate pools used by Full PaperFlow.

## Method Family

This baseline corresponds to literature recommendation methods that combine:

- Content similarity between the user profile/history and candidate papers.
- Citation-link evidence, such as candidate papers citing previously relevant papers or sharing references with them.
- External impact evidence, such as citation counts when available.
- A fixed daily ranking procedure over the same candidate pool.

In the current PaperFlow benchmark, the frozen paper database does not contain a complete citation graph. Therefore, the implementation is designed as a safe two-level baseline:

- If clean candidate metadata contains citation fields, use them directly.
- If citation counts or graph edges are unavailable, fall back to DOI/source/venue metadata as weak external-impact proxies.

The baseline never queries live OpenAlex, Semantic Scholar, Google Scholar, or Crossref during ranking. This avoids leaking citation counts or metadata that were not available on the simulated recommendation day.

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
- Paper title and abstract for content similarity.
- Fixed cold-start user evidence from sanitized `users.json` and `data/roles.json`.
- Previous selected papers from earlier days only.
- Candidate citation metadata if it is already present in the clean frozen candidate row.
- Candidate DOI/source/venue metadata as weak impact proxies when citation metadata is absent.

## Forbidden Inputs

The baseline must not use:

- Current-day selected papers before ranking.
- Future user feedback.
- `oracle_label` or `oracle_score` during ranking.
- Full PaperFlow `shown`, `system_score`, `system_label`, `system_rank`, `drift_bonus`, or `reading_signal_bonus`.
- PaperFlow-updated dynamic profiles, drift states, reading reports, or report feedback.
- Live external citation APIs during ranking.

## Ranking Model

The baseline scores each candidate paper with four components:

```text
CitationEnhancedScore(p, u, t) =
  0.50 * ContentSimilarity(p, u, <t)
+ 0.25 * CitationRelation(p, selected_{<t})
+ 0.20 * ImpactSignal(p)
+ 0.05 * SourcePrior(p)
```

Where:

- `ContentSimilarity` is TF-IDF similarity over `title + abstract`, using the fixed initial profile and previous selected papers.
- `CitationRelation` uses direct citation/reference links and bibliographic coupling when candidate metadata includes `references`, `reference_ids`, `citation_ids`, or related fields.
- `ImpactSignal` uses normalized citation count fields such as `cited_by_count`, `citation_count`, `citations`, or `influential_citation_count` when available.
- If no citation count is available, `ImpactSignal` falls back to a weak, non-live DOI/source/venue prior.
- `SourcePrior` is a small deterministic tie-breaker based on source/venue metadata.

The weights remain fixed across all users and days.

This is an offline benchmark adaptation, not a full reproduction of the paper's original WoS-scale citation-network construction or OpenAI `text-embedding-3-small` abstract embedding pipeline. The benchmark uses only citation and metadata fields already present in the frozen clean candidate rows, so it cannot leak future or live citation information.

## Daily Episode Procedure

For each user, process episodes chronologically.

For each day:

1. Load the daily candidate pool for the `user x day` episode.
2. Build the content representation using the fixed cold-start profile and previous selected papers only.
3. Score every candidate paper using content, citation-relation, impact, and source-prior components.
4. Sort by `CitationEnhancedScore` descending.
5. Mark the top 20 papers as `shown = true`.
6. Assign `system_rank` from 1 to 20 for shown papers.
7. Preserve `oracle_*` fields only for evaluation compatibility.
8. After the day has been ranked, update historical selected-paper memory for the next day.

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

- Should favor papers connected to historically selected work when citation metadata exists.
- Should surface high-impact or well-identified papers when citation/impact metadata exists.
- Should remain stronger than pure content matching in citation-rich candidate pools.

Expected weaknesses:

- In the current PaperFlow paper database, complete citation graph fields are usually absent, so the baseline may often fall back to weak impact proxies.
- It cannot adapt to interest drift except through previous selected papers.
- It cannot use reading-report quality feedback.
- It cannot represent user-specific must-read constraints.

## Difference From Full PaperFlow Pipeline

| Capability | Citation-Enhanced Baseline | Full PaperFlow Pipeline |
|---|---:|---:|
| Daily personalized ranking | yes | yes |
| Fixed cold-start support | yes | yes |
| Previous selected-paper feedback | yes | yes |
| Citation/impact metadata | yes | partial |
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
python scripts/run_citation_enhanced_baseline.py --input-dir <benchmark_output>/baseline_clean_input
```

Recommended command:

```cmd
run_citation_enhanced_baseline_clean.cmd
```

Recommended output directory:

```text
<benchmark_output>/main_experiment/citation_enhanced/
```

Current implementation:

```text
baselines/citation_enhanced/runner.py
scripts/run_citation_enhanced_baseline.py
```
