# Natural-Language User Profile Recommendation

This baseline represents natural-language user-interest profile based scientific literature recommendation in the PaperFlow main experiment.

Use `design.md` as the source-of-truth design. The implementation reranks frozen PaperFlow benchmark episode pools and writes results to:

```text
<benchmark_output>/main_experiment/nl_profile/
```

Method row name:

```text
Natural-Language User Profile Recommendation
```

Recommended no-contamination command after the Full PaperFlow benchmark is complete:

```cmd
run_nl_profile_baseline_clean.cmd
```

This first exports `baseline_clean_input/`, then runs the baseline using only that clean input.
