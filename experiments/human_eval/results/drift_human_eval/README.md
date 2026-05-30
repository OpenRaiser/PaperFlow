# drift_human_eval

Status: final manual

This folder reports the drift-experiment human evaluation.

## Method Scores

| Rank | Method | AdaptationHumanScore | DriftAutoScore | NewTopicFit | AdaptationAppropriateness | OldNewBalance | DriftDecisionHelpfulness |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | Full PaperFlow | 68.7500 | 68.6812 | 3.3472 | 2.8611 | 4.2361 | 3.3056 |
| 2 | Fixed Profile | 68.1944 | 65.3778 | 3.3056 | 2.9722 | 4.0417 | 3.3195 |
| 3 | w/o Drift | 67.7778 | 65.5264 | 3.2500 | 2.9306 | 4.0417 | 3.3333 |

## Main Correlation

Use this sentence in the paper if you need the concise result:

`DriftAutoScore` correlates strongly with `AdaptationHumanScore` (`r=0.914851`, `rho=0.890438`, `n=72`).

## Files

- `summary.csv`: method-level drift human-evaluation scores.
- `correlations.csv`: automatic drift metric vs. human drift metric correlations.
- `pairwise_summary.csv`: pairwise ranking agreement summary.

Source: `scripts/human_eval/packages/drift_human_eval/data/results/list_level/drift_list_human_eval_method_summary.csv`

