# Human Eval Results

This folder now keeps the final manual human-evaluation results in separate experiment folders.

## Folders

| Experiment | Folder | Best method | Human score | Auto metric | Human metric | Pearson r | Spearman r | n |
| --- | --- | --- | ---: | --- | --- | ---: | ---: | ---: |
| Main experiment | `main_human_eval` | Full PaperFlow Pipeline | 65.555556 | RecommendationScore | ListwiseHumanScore | 0.862586 | 0.863089 | 36 |
| Drift experiment | `drift_human_eval` | Full PaperFlow | 68.7500 | DriftAutoScore | AdaptationHumanScore | 0.914851 | 0.890438 | 72 |
| Model comparison | `model_human_eval` | grok-4.3 | 94.0741 | ModelAutoScore | ModelHumanScore | 0.963243 | 0.964835 | 14 |

Use `main_human_eval/README.md` for the main-experiment human-evaluation table, `drift_human_eval/README.md` for the drift-experiment human-evaluation table, and `model_human_eval/README.md` for the model-comparison human-evaluation table.
