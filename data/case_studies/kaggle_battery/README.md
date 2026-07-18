# Kaggle Battery Case Study

This folder documents the Kaggle NASA battery capacity retention case study.

- `case_study.md`: Portfolio-oriented narrative report covering data preparation, feature engineering, validation design, results, interpretation, limitations, and next steps.
- `source.md`: Data source, raw-data policy, processing notes, generated file descriptions, and analyzer command references.
- `simulation_comparison.md`: Generated comparison report for the simulation runs, including random-split versus group-split results and feature-enriched model comparisons.

The v2.3.5 source-metadata recovery and predeclared evaluator-stability audit
is documented in:

- [`docs/BATTERY_SOURCE_METADATA_RECOVERY.md`](../../../docs/BATTERY_SOURCE_METADATA_RECOVERY.md)
- [`docs/BATTERY_EVALUATOR_STABILITY_AUDIT.md`](../../../docs/BATTERY_EVALUATOR_STABILITY_AUDIT.md)
- [`docs/BATTERY_V2_3_5_SCIENTIFIC_BOUNDARY.md`](../../../docs/BATTERY_V2_3_5_SCIENTIFIC_BOUNDARY.md)

It verifies the immediate local Kaggle lineage for 34 cells and recovers only
source-supported metadata. The official original NASA snapshot/version and
measurement uncertainty remain unavailable; no external data was downloaded.
