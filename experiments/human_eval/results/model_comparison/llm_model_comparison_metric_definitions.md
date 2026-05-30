# LLM Model-Comparison Metrics

This table compares model backbones inside the same PaperFlow pipeline.
It does not include main-experiment baselines or ablation variants.

`RecommendationScore = 100 * (0.25*gNDCG@20 + 0.15*Useful@5 + 0.15*Useful@20 + 0.20*StrictR@20+ + 0.15*MRR@20 + 0.10*min(Lift@20/15, 1))`.

`ReportAutoScore = 100 * (0.70*SectionCompleteness + 0.30*EvidenceCoverage)`.
In the current logs, `SectionCompleteness` is implemented with `ReportStructureScore`,
and `EvidenceCoverage` is implemented with `ReportEvidenceRate`.

`ModelAutoScore = 0.80*RecommendationScore + 0.20*ReportAutoScore`.

`ParsingSuccess` is omitted from the main model-comparison table because all
completed runs currently achieve 100% non-empty report generation success. It
can be reported in diagnostic appendix tables alongside `SectionCompleteness`,
`EvidenceCoverage`, PDF-source rate, and abstract-fallback rate.

`ModelHumanScore` is filled after blind human evaluation.

`TokenCost` is reported separately as total LLM tokens, excluding the fixed embedding model. It is not included in
`ModelAutoScore` or `ModelHumanScore`.
