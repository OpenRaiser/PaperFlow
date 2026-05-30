# Discourse-Aware Content Recommendation

This baseline represents discourse-aware and paper-structure enhanced content recommendation in the PaperFlow main experiment.

Use `design.md` as the source-of-truth design. The implementation reranks frozen PaperFlow benchmark episode pools and writes results to:

```text
<benchmark_output>/main_experiment/discourse_aware/
```

Method row name:

```text
Discourse-Aware Content Recommendation
```

Recommended no-contamination command after the Full PaperFlow benchmark is complete:

```cmd
run_discourse_aware_baseline_clean.cmd
```

This first exports `baseline_clean_input/`, then runs the baseline using only that clean input.
