# Main Experiment Baselines

This directory keeps each main-experiment baseline in its own folder so the design, implementation notes, configuration, and generated outputs do not get mixed together.

Recommended structure:

```text
baselines/
  scholar_inbox/
    design.md
    README.md              # optional implementation notes
    config.json            # optional fixed scoring weights
  citation_enhanced/
    design.md
  discourse_aware/
    design.md
    README.md
  scinup_strict/
    design.md
    README.md
  knowledge_entity/
    design.md
    README.md
```

Main-experiment baseline outputs should be written under the frozen benchmark output directory rather than committed here:

```text
<benchmark_output>/main_experiment/<baseline_key>/
```

This keeps source design files separate from generated experiment artifacts.
