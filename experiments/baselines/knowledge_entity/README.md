# Knowledge-Entity Enhanced Recommendation

This baseline represents fine-grained knowledge-entity and multifaceted document representation methods in the PaperFlow main experiment.

Use `design.md` as the source-of-truth design. The implementation reranks frozen PaperFlow benchmark episode pools and writes results to:

```text
<benchmark_output>/main_experiment/knowledge_entity/
```

Method row name:

```text
Knowledge-Entity Enhanced Recommendation
```

Recommended no-contamination command after the Full PaperFlow benchmark is complete:

```cmd
run_knowledge_entity_baseline_clean.cmd
```

This first exports `baseline_clean_input/`, then runs the baseline using only that clean input.
