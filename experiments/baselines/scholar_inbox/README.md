# Scholar Inbox Pipeline

This baseline is inspired by `Scholar Inbox: Personalized Paper Recommendations for Scientists`.

Use `design.md` as the source-of-truth design for the main experiment. The implementation reranks the frozen PaperFlow benchmark episode pools and writes results to:

```text
<benchmark_output>/main_experiment/scholar_inbox/
```

Method row name:

```text
Scholar Inbox Pipeline
```

Recommended no-contamination command after the Full PaperFlow benchmark is complete:

```cmd
run_scholar_inbox_baseline_clean.cmd
```

This first exports `baseline_clean_input/`, then runs Scholar Inbox using only that clean input.
