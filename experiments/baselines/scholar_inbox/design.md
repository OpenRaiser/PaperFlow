# Scholar Inbox Pipeline Baseline Design

## Purpose

This document defines the `Scholar Inbox Pipeline` baseline for the PaperFlow main experiment.

The goal is not to reimplement the full Scholar Inbox product, but to operationalize the core recommendation paradigm described in `Scholar Inbox: Personalized Paper Recommendations for Scientists` as a fair, reproducible baseline on the PaperFlow benchmark.

In the main experiment, `Full PaperFlow Pipeline` is produced by the full benchmark run. `Scholar Inbox Pipeline` is evaluated afterward by reranking the same frozen `user x day` candidate pools.

## Paper Reference

Reference paper:

```text
Flicke et al. 2025. Scholar Inbox: Personalized Paper Recommendations for Scientists.
ACL 2025 System Demonstrations.
https://arxiv.org/abs/2504.08385
```

Relevant design points from the paper:

- Scholar Inbox provides daily or weekly paper digests ranked by predicted relevance for the current user.
- Its recommender is content-based and trains a user-specific classifier from paper ratings.
- Users can explicitly upvote and downvote papers, and the model is retrained as feedback arrives.
- Cold start is handled through onboarding with user publications, related authors, paper selection, and a map of science.
- Paper representations are based on title and abstract embeddings; the paper reports experiments with TF-IDF, SPECTER2, and GTE embeddings.
- Scholar Inbox includes additional product features such as semantic search, paper maps, figure previews, bookmarks, collections, and email digests.

For PaperFlow, only the recommendation mechanism relevant to daily personalized paper ranking is used as the baseline.

## Main Experiment Role

`Scholar Inbox Pipeline` represents a strong personalized paper recommendation platform baseline.

It is stronger than a simple keyword alert because it can learn a user-specific content classifier from historical feedback. However, it is still narrower than PaperFlow because it does not maintain a structured research profile, does not model interest drift states, does not use must-read priority as a hard mechanism, and does not connect recommendation with reading-report feedback.

The core question this baseline answers is:

```text
Can a content-based daily digest recommender trained on historical user ratings match PaperFlow under the same dynamic scientific reading benchmark?
```

## Clean Baseline Input Contract

To avoid contamination from the Full PaperFlow pipeline, baselines should not read `episode_papers.jsonl` directly. First export a clean baseline package:

```text
python scripts/export_clean_baseline_benchmark.py --input-dir <benchmark_output>
```

This creates:

```text
<benchmark_output>/baseline_clean_input/
  candidate_pools.jsonl
  labels_for_eval.jsonl
  episodes.jsonl
  users.json
  manifest.json
```

`candidate_pools.jsonl` is the only file used for same-day ranking. It excludes Full PaperFlow method fields such as `shown`, `system_score`, `system_label`, `system_rank`, `drift_bonus`, `reading_signal_bonus`, and `ranking_source`.

`labels_for_eval.jsonl` is used only after ranking for chronological feedback updates and post-ranking evaluation. `oracle_label` and `oracle_score` are evaluation-only fields and must never be used for scoring or training.

`users.json` is sanitized to cold-start metadata only. Dynamic profile snapshots, drift states, report preferences, and updated profile fields are stripped before any baseline can read them.

## Allowed Inputs

For each `user x day` episode, the baseline may use:

- The frozen daily paper pool from clean `candidate_pools.jsonl`.
- Paper title, abstract, authors, venue/source, and metadata available before recommendation.
- The user's initial cold-start evidence or initial profile.
- The user's own historical feedback from previous days only.
- Previous selected papers as positive ratings.
- Deterministic previous-day background candidates as low-weight random negatives.

## Forbidden Inputs

The baseline must not use:

- Current-day selected papers before ranking.
- Future user feedback.
- `oracle_label` or `oracle_score` during ranking.
- PaperFlow-updated dynamic profiles after each day.
- PaperFlow drift state, drift bonus, anchor state, recovered state, or profile-update internals.
- Reading reports, reading-report quality feedback, or PDF-enriched report content.
- Full PaperFlow `system_score` or `system_label`.

These fields may remain in output files only for evaluation compatibility, not for ranking.

## Cold-Start Construction

Day 1 has little or no historical rating data. To mirror Scholar Inbox onboarding while staying within PaperFlow data, the baseline builds an initial user representation from the user's cold-start profile.

Clean cold-start sources:

- Sanitized `users.json`: `description`, `seed_directions`, and `initial_topics` when present.
- Fixed `data/roles.json` bootstrap metadata: `seed_directions`, `bootstrap_summary`, `description`, and initial keyword/author/institution preferences.

The cold-start representation is converted into:

- A profile text query.
- A weighted topic/entity set.
- Soft keyword/author/institution diagnostic signals.

Example profile text:

```text
Research interests: embodied-ai, reinforcement-learning, robotics.
Keywords: vision-language-action, dexterous manipulation, sim-to-real robot learning.
Preferred authors: ...
Preferred institutions: ...
```

Important: these role-level preferences are treated as onboarding evidence only, analogous to Scholar Inbox asking a user to choose papers/authors/topics during registration. They are not PaperFlow's dynamically updated profile, and they are not used as hard must-read rules.

## Historical Feedback Mapping

Scholar Inbox uses explicit upvotes and downvotes. PaperFlow benchmark episodes provide simulated reading choices rather than explicit thumbs-up/down. Therefore, the baseline uses the following mapping:

| PaperFlow signal | Scholar Inbox-style rating | Weight |
|---|---|---:|
| selected/read paper from previous days | positive rating | 1.0 |
| unshown candidate paper | random/background negative candidate | 0.10 |

Rationale:

- A selected paper is strong evidence of interest.
- Full PaperFlow's `shown` field is not used as a skipped/downvote signal because it is a Full Pipeline exposure decision.
- Random background negatives regularize the classifier, following the paper's use of random negatives, but with low weight to avoid over-penalizing unseen scientific areas.

Only feedback from days before the target day can be used.

## Ranking Model

The baseline is implemented as a user-specific content-based daily-digest ranker.

### Preferred Model

If embeddings are available:

```text
paper_text = title + " [SEP] " + abstract
paper_vector = embedding(paper_text)
```

Then train a lightweight user-specific classifier from previous ratings. When the rating history is still too small, fall back to a centroid-style scorer so early days remain runnable:

```text
positive_centroid = weighted mean(selected paper vectors)
negative_centroid = weighted mean(background negative vectors)
feedback_score = cosine(paper_vector, positive_centroid) - 0.5 * cosine(paper_vector, negative_centroid)
```

When enough historical ratings exist, the runnable baseline uses a deterministic weighted logistic-regression classifier over the same TF-IDF paper representation, matching the Scholar Inbox paper more directly.

Minimum training threshold:

```text
use classifier if positives >= 3 and negatives >= 8
otherwise use cold-start similarity + centroid fallback
```

### Fallback Model

If embeddings are unavailable or API calls are unstable, use deterministic TF-IDF or lexical scoring over title and abstract.

This fallback is still valid because the Scholar Inbox paper evaluates TF-IDF as a content-based recommender baseline, although it selects dense GTE embeddings for its final system.

## Score Function

The final score is intentionally content-dominant. This keeps the baseline aligned with Scholar Inbox's paper-content recommendation design rather than turning it into an author, institution, venue, or must-read rule system.

```text
ScholarInboxScore(p, u, t) =
  0.80 * ContentClassifierScore(p, u, <t)
+ 0.15 * ColdStartProfileSimilarity(p, u)
+ 0.05 * KeywordExactMatch(p, u)
```

Where:

- `ContentClassifierScore` is learned only from previous-day feedback.
- `ColdStartProfileSimilarity` uses the fixed initial profile, not PaperFlow's updated profile.
- `KeywordExactMatch` checks initial keywords as a soft title/abstract content signal, not hard must-read.
- `AuthorMatch`, `InstitutionMatch`, and `SourcePrior` may be emitted as diagnostics, but their ranking weights are fixed to `0.00` for this baseline.

The weights should remain fixed across all users and days.

## Daily Episode Procedure

For each user, process episodes chronologically.

For each day:

1. Load the daily candidate pool for the user-day episode.
2. Build the baseline model using only the user's feedback history before this day.
3. Score every paper in the daily pool.
4. Sort by `ScholarInboxScore` descending.
5. Mark the top 20 papers as `shown = true`.
6. Assign `system_rank` from 1 to 20 for shown papers.
7. Set non-shown papers to `shown = false` and empty rank.
8. After evaluation-compatible output is written, update the baseline's feedback memory using this day's selected papers and deterministic background negatives for the next day.

Important: current-day labels are used only after the day has been ranked.

## System Labels

The baseline should output system labels for comparability with PaperFlow tables.

Recommended thresholds:

```text
score >= 0.70 -> high_relevant
0.45 <= score < 0.70 -> maybe_interested
score < 0.45 -> edge_relevant
```

This baseline should not emit `must_read`.

Reason:

Scholar Inbox can prioritize papers through relevance scores and ratings, but it does not represent PaperFlow's explicit hard must-read mechanism. Initial must-read keywords/authors are treated as soft preference signals only.

## Output Format

The baseline output should mirror the existing `episode_papers.jsonl` schema so the same evaluation script can be reused.

Required fields:

```text
date
episode_id
user_id
role_name
paper_id
title
abstract
authors
source
url
shown
selected
pool_rank
system_rank
system_score
system_label
oracle_score
oracle_label
select_probability
```

Additional recommended fields:

```text
baseline_method = "Scholar Inbox Pipeline"
content_score
cold_start_score
author_match_score
keyword_match_score
source_prior
training_positive_count
training_negative_count
uses_feedback_classifier
```

## Evaluation

Use the same metrics as the main experiment:

```text
Oracle P@5
Oracle P@10
Oracle P@20
Oracle R@20
Oracle NDCG@10
Oracle NDCG@20
Oracle MRR@20
```

Evaluation uses oracle fields only after ranking.

## Expected Behavior

Expected strengths:

- Should perform well for stable users with repeated topic interests.
- Should improve after several days because previous selected papers act as positives.
- Should be stronger than static keyword subscription.
- Should be competitive when title/abstract semantics align with user interests.

Expected weaknesses:

- May react slowly to interest drift because it has no explicit drift state.
- May confuse short exploration with stable preference if feedback is sparse.
- May underperform when the user has multiple separate research interests, since the paper reports that separate explicit interest modeling is not fully supported.
- Does not distinguish long-term profile, observing-state drift, and committed shifting state.
- Does not use reading-report feedback or report-preference learning.

## Difference From Full PaperFlow Pipeline

| Capability | Scholar Inbox Pipeline | Full PaperFlow Pipeline |
|---|---:|---:|
| Daily personalized ranking | yes | yes |
| Initial cold-start support | yes | yes |
| Content-based feedback learning | yes | yes |
| Structured research profile | no | yes |
| Multi-source profile fields | partial | yes |
| Hard must-read priority | no | yes |
| Interest drift state | no | yes |
| Stable / observing / shifting modeling | no | yes |
| Reading-report generation | no | yes |
| Reading-report feedback | no | yes |
| Weekly explanation/report | no | yes |

## Paper Wording

Recommended paper description:

```text
Scholar Inbox Pipeline is implemented as a content-based daily digest baseline inspired by Scholar Inbox. It builds a user-specific paper relevance model from the user's initial cold-start evidence and historical paper-level feedback. Previous selected papers are treated as positive ratings, and deterministic previous-day background candidates are treated as low-weight random negatives. The model reranks the same daily candidate pools as PaperFlow using only information available before each recommendation day. Unlike PaperFlow, it does not maintain structured profile updates, explicit must-read priority, interest drift states, or reading-report feedback.
```

## Implementation Notes

Runnable script:

```text
python scripts/export_clean_baseline_benchmark.py --input-dir <benchmark_output>
python scripts/run_scholar_inbox_baseline.py --input-dir <benchmark_output>/baseline_clean_input
```

Recommended method key:

```text
scholar_inbox
```

Recommended output directory:

```text
<benchmark_output>/main_experiment/scholar_inbox/
```

The implementation should process users and dates sequentially to prevent future feedback leakage.

Current implementation:

```text
baselines/scholar_inbox/runner.py
scripts/run_scholar_inbox_baseline.py
```

The current runnable version uses deterministic TF-IDF vectors over `title + abstract`, the same paper-text boundary used by the Scholar Inbox experiments. For early cold-start days it falls back to profile similarity and a centroid-style feedback scorer; once a user has at least 3 historical positives and 8 historical background negatives, it trains a deterministic sparse weighted logistic-regression classifier for that user. To avoid future-text leakage, the TF-IDF space is built separately for each user-day from only the current day's candidate pool, the fixed initial profile text, and that user's previous feedback texts. To avoid Full Pipeline contamination, the runner uses clean candidates for scoring and reads `selected` only from `labels_for_eval.jsonl` after a day has already been ranked. This follows the paper's content-based/rating-driven structure and keeps the baseline runnable without external embedding APIs. If dense embeddings are later required, the vectorizer can be replaced while preserving the same chronological feedback and output contract.
