# Citation-Enhanced Literature Recommendation

This baseline represents citation-network and external-impact enhanced literature recommendation in the PaperFlow main experiment.

Use `design.md` as the source-of-truth design. The implementation reranks frozen PaperFlow benchmark episode pools and writes results to:

```text
<benchmark_output>/main_experiment/citation_enhanced/
```

Method row name:

```text
Citation-Enhanced Literature Recommendation
```

Recommended no-contamination command after the Full PaperFlow benchmark is complete:

```cmd
run_citation_enhanced_baseline_clean.cmd
```

This first exports `baseline_clean_input/`, then runs the baseline using only that clean input.
