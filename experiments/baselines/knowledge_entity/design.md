# Knowledge-Entity Enhanced Recommendation Baseline Design

## Purpose

This document defines the `Knowledge-Entity Enhanced Recommendation` baseline for the PaperFlow main experiment.

The goal is to represent scholarly recommendation methods that use fine-grained scientific entities and multifaceted document representations, rather than only a single title/abstract similarity score. This baseline is intentionally narrower than Full PaperFlow: it does not maintain structured dynamic user profiles, does not model interest drift states, and does not use reading-report feedback.

## Reference Method

This baseline is aligned with the method family represented by:

```text
Xi et al.
Enhancing Academic Paper Recommendations Using Fine-Grained Knowledge Entities and Multifaceted Document Embeddings.
Scientometrics, 2026 / arXiv, 2026.
https://arxiv.org/abs/2601.19513
```

The reference method emphasizes fine-grained knowledge entities and multifaceted document embeddings for academic paper recommendation. PaperFlow's benchmark unit is `user x day`, not a single paper-to-paper recommendation session. Therefore, this baseline adapts the method family by extracting entities from clean candidate metadata and title/abstract text, then combining entity, content, metadata, and citation/identifier signals to rerank the same daily candidate pools as Full PaperFlow.

## Method Family

This baseline corresponds to knowledge-entity enhanced scholarly recommendation methods that combine:

- Fine-grained scientific concepts from paper metadata and text.
- Multiple document facets such as title, abstract, entity text, source/venue metadata, and citation metadata.
- Similarity to a fixed cold-start user profile.
- Similarity to previously selected papers as chronological paper-level history.
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

`labels_for_eval.jsonl` is used only after ranking for chronological history updates and post-ranking evaluation. `oracle_label` and `oracle_score` are evaluation-only fields and must never be used for scoring or training.

`users.json` is sanitized to cold-start metadata only. Dynamic profile snapshots, drift states, report preferences, and updated profile fields are stripped before the baseline can read them.

## Allowed Inputs

For each `user x day` episode, the baseline may use:

- The frozen daily paper pool from clean `candidate_pools.jsonl`.
- Paper title and abstract.
- Paper metadata fields already present in the clean candidate row, such as `topics`, `keywords`, `institutions`, `venue`, `doi`, `arxiv_id`, and citation-count fields.
- Fixed cold-start user evidence from sanitized `users.json` and `data/roles.json`.
- Previous selected papers from earlier days only, used as paper-level history.
- Deterministic rule-based entity extraction from title and abstract.

## Forbidden Inputs

The baseline must not use:

- Current-day selected papers before ranking.
- Future user feedback.
- `oracle_label` or `oracle_score` during ranking.
- Full PaperFlow `shown`, `system_score`, `system_label`, `system_rank`, `drift_bonus`, or `reading_signal_bonus`.
- PaperFlow-updated dynamic profiles, drift states, reading reports, report quality feedback, or weekly reports.
- PDF enrichment, source-page parsing, or LLM-generated reading reports.
- Live external entity-linking, citation, or embedding APIs during ranking.

## Entity and Multifaceted Representation

For each candidate paper, the baseline builds four deterministic facets:

| Facet | Source | Purpose |
|---|---|---|
| `title` | title text | high-precision topical cue |
| `abstract` | abstract text | broad semantic content |
| `entity` | metadata entities plus extracted scientific phrases | fine-grained concept matching |
| `metadata` | source, venue, journal, topic, keyword, and citation metadata | external/document context |

Entities come from clean metadata fields when available and from rule-based phrase extraction over `title + abstract` otherwise. No live entity linker is used.

## Ranking Model

The baseline scores each candidate paper with five components:

```text
KnowledgeEntityScore(p, u, t) =
  0.30 * ProfileEntityMatch(p, u)
+ 0.25 * HistoryEntityMatch(p, selected_{<t})
+ 0.30 * MultifacetSimilarity(p, u, selected_{<t})
+ 0.10 * MetadataSignal(p)
+ 0.05 * EntityDensity(p)
```

Where:

- `ProfileEntityMatch` compares candidate entities with the fixed cold-start entity profile.
- `HistoryEntityMatch` compares candidate entities with entities from previous selected papers only.
- `MultifacetSimilarity` combines title, abstract, entity, and metadata TF-IDF similarities.
- `MetadataSignal` uses frozen metadata and normalized citation counts when available.
- `EntityDensity` rewards papers with richer entity evidence, capped to avoid over-counting long abstracts.

The weights remain fixed across all users and days.

This is an offline benchmark adaptation, not a full reproduction of the reference paper's full embedding training or entity-linking pipeline. The goal is to represent the knowledge-entity/multifaceted-document method family fairly under PaperFlow's unified daily benchmark.

## Daily Episode Procedure

For each user, process episodes chronologically.

For each day:

1. Load the daily candidate pool for the `user x day` episode.
2. Build candidate title, abstract, entity, and metadata facets.
3. Score every candidate paper using fixed profile entities and previous selected-paper entity history.
4. Sort by `KnowledgeEntityScore` descending.
5. Mark the top 20 papers as `shown = true`.
6. Assign `system_rank` from 1 to 20 for shown papers.
7. Preserve `oracle_*` fields only for evaluation compatibility.
8. After the day has been ranked, update historical selected-paper entity memory for the next day.

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

- Should favor papers that share fine-grained concepts with the user's cold-start profile and historical selected papers.
- Should use richer paper-side signals than pure title/abstract similarity when metadata entities exist.
- Provides a strong comparison point for PaperFlow's own multi-granularity profile design.

Expected weaknesses:

- Entity extraction is deterministic and offline, not a full neural entity linker.
- It cannot distinguish stable interests from observing or shifting interests.
- It cannot use reading-report quality feedback.
- It cannot represent user-specific hard must-read constraints.
- Its citation/metadata benefit depends on what is present in the frozen clean candidate rows.

## Difference From Full PaperFlow Pipeline

| Capability | Knowledge-Entity Baseline | Full PaperFlow Pipeline |
|---|---:|---:|
| Daily personalized ranking | yes | yes |
| Fixed cold-start support | yes | yes |
| Fine-grained paper entities | yes | yes |
| Previous selected-paper feedback | yes | yes |
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
python scripts/run_knowledge_entity_baseline.py --input-dir <benchmark_output>/baseline_clean_input
```

Recommended command:

```cmd
run_knowledge_entity_baseline_clean.cmd
```

Recommended output directory:

```text
<benchmark_output>/main_experiment/knowledge_entity/
```

Current implementation:

```text
baselines/knowledge_entity/runner.py
scripts/run_knowledge_entity_baseline.py
```
