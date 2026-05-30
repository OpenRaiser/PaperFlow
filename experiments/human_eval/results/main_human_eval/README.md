# main_human_eval

Status: final manual

This folder reports the main-experiment human evaluation.

## Method Scores

| Rank | Method | ListwiseHumanScore | WithBalance | RecommendationScore | gNDCG@20 | Useful@5 | Useful@20 | MRR@20 | Lift@20 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | Full PaperFlow Pipeline | 65.555556 | 63.333333 | 52.813691 | 0.711039 | 0.433333 | 0.233333 | 0.750000 | 13.695473 |
| 2 | Scholar Inbox Pipeline | 55.555555 | 55.833333 | 46.059680 | 0.554738 | 0.333333 | 0.191667 | 0.652778 | 14.800720 |
| 3 | Natural-Language User Profile Recommendation | 53.333333 | 55.000000 | 48.191893 | 0.575250 | 0.400000 | 0.200000 | 0.638889 | 17.546502 |
| 4 | Citation-Enhanced Literature Recommendation | 44.444445 | 45.000000 | 36.431241 | 0.446864 | 0.233333 | 0.175000 | 0.509804 | 8.793879 |
| 5 | Knowledge-Entity Enhanced Recommendation | 35.555555 | 35.833333 | 35.859659 | 0.373449 | 0.266667 | 0.150000 | 0.545238 | 8.779784 |
| 6 | Discourse-Aware Content Recommendation | 30.000000 | 30.833333 | 24.248884 | 0.223899 | 0.200000 | 0.133333 | 0.277778 | 5.152109 |

## Main Correlation

Use this sentence in the paper if you need the concise result:

`RecommendationScore` correlates strongly with `ListwiseHumanScore` (`r=0.862586`, `rho=0.863089`, `n=36`).

## Files

- `summary.csv`: method-level main human-evaluation scores.
- `correlations.csv`: automatic metric vs. human metric correlations.
- `listwise_annotator_agreement.csv`: annotator agreement summary.

Source: `scripts/human_eval/packages/main_human_eval/data/listwise_behavior_human_filled_1.csv + _2.csv + _3.csv`

