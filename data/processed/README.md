# Processed Data

This folder contains generated or curated case-study summary artifacts.

Processed files are not raw data. They should be derived from documented source data through loader scripts, inspection scripts, or analyzer workflows. Large raw datasets, source archives, API responses, and credentials should not be stored here.

## Kaggle NASA Battery Case Study Summaries

The following files are the main processed artifacts for the Kaggle NASA battery case study:

```text
kaggle_nasa_battery_cycle_summary.csv
kaggle_nasa_battery_cycle_summary_analysis_ready.csv
kaggle_nasa_battery_quality_summary.csv
kaggle_nasa_battery_discharge_features.csv
kaggle_nasa_battery_analysis_ready_with_features.csv
kaggle_battery_simulation_comparison.csv
```

Roles:

- `kaggle_nasa_battery_cycle_summary.csv`: full quality-audited discharge cycle summary from Kaggle metadata.
- `kaggle_nasa_battery_cycle_summary_analysis_ready.csv`: analysis-ready subset filtered to normal retention-quality rows.
- `kaggle_nasa_battery_quality_summary.csv`: battery-level quality summary used to inspect warning rates and retention ranges.
- `kaggle_nasa_battery_discharge_features.csv`: scalar features extracted from raw discharge CSV files, such as voltage/current/temperature/duration summaries.
- `kaggle_nasa_battery_analysis_ready_with_features.csv`: analysis-ready metadata summary joined with discharge-derived scalar features.
- `kaggle_battery_simulation_comparison.csv`: summary table comparing selected simulation runs.

## Battery Archive Case Study Summaries

Compact reproducibility artifacts for the Battery Archive case study include:

```text
battery_archive_cycle_file_inventory.csv
battery_archive_cycle_file_inventory_enriched.csv
battery_archive_cycle_schema_inventory.csv
battery_archive_cycle_column_inventory.csv
battery_archive_cycle_column_mapping.csv
battery_archive_cycle_load_summary.csv
battery_archive_cycle_series_summary.csv
battery_archive_data_quality_summary.csv
battery_archive_reliability_group_summary.csv
```

The large generated cycle-level tables are local artifacts by default:

```text
battery_archive_cycle_normalized.csv
battery_archive_cycle_analysis_ready.csv
```

## Battery PGIR v2.3 Representation Summaries

Compact reproducibility artifacts for the v2.3.2 Battery PGIR representation
pilot include:

```text
battery_v2_3_data_audit_summary.json
battery_v2_3_representation_coverage.csv
battery_v2_3_maturity_summary.csv
battery_v2_3_transition_summary.csv
battery_v2_3_mechanism_readiness.csv
battery_v2_3_pgir_readiness_decision.json
battery_v2_3_report_summary.md
```

The row-level Observation, operational State, and Trajectory JSONL artifacts
are local-only:

```text
outputs/battery_pgir_v2_3/
```

These files document representation readiness only. They do not contain a
battery mechanism fit, SOH/RUL model, diffusion result, Arrhenius estimate, or
production prediction output.

## Materials Project Case Study Summaries

Compact reproducibility artifacts for the Materials Project v1.2 pilot and
v1.3 validation closeout include:

```text
materials_project_query_manifest.json
materials_project_property_inventory.csv
materials_project_quality_summary.csv
materials_project_screening_summary.csv
materials_project_v1_3_acquisition_manifest.json
materials_project_v1_3_acquisition_summary.csv
materials_project_v1_3_descriptor_inventory.csv
materials_project_v1_3_descriptor_redundancy_summary.csv
materials_project_v1_3_composition_ambiguity_summary.csv
materials_project_v1_3_target_suitability_summary.csv
materials_project_v1_3_split_readiness_summary.csv
materials_project_v1_3_group_inventory.csv
materials_project_v1_3_validation_metrics.csv
materials_project_v1_3_model_comparison_summary.csv
materials_project_v1_3_split_diagnostics.csv
materials_project_v1_3_screening_metrics_summary.csv
materials_project_v1_3_applicability_summary.csv
materials_project_v1_3_error_structure_summary.csv
materials_project_v1_3_claim_boundary.csv
materials_project_v1_3_trust_conclusion.csv
materials_physics_v2_2_feature_definitions.csv
materials_physics_v2_2_property_source_metadata.json
materials_physics_v2_2_feature_coverage_summary.csv
materials_physics_v2_2_feature_use_evidence.json
materials_physics_v2_2_predictive_comparison_summary.csv
materials_physics_v2_2_predictive_value_decision.json
materials_physics_v2_2_report_summary.md
materials_project_v2_2_acquisition_scope_summary.json
materials_project_v2_2_structure_coverage_summary.csv
materials_project_v2_2_structure_adapter_summary.json
materials_project_v2_2_operator_snapshot.json
materials_project_v2_2_4_structure_enrichment_summary.json
materials_project_v2_2_4_snapshot_alignment_summary.csv
materials_project_v2_2_4_structure_coverage_summary.csv
materials_project_v2_2_4_descriptor_definition_snapshot.csv
materials_project_v2_2_4_descriptor_coverage_summary.csv
materials_project_v2_2_4_graph_eligibility_summary.csv
materials_project_v2_2_4_operator_snapshot.json
materials_v2_2_5_known_structure_cohort_summary.json
materials_v2_2_5_feature_set_snapshot.csv
materials_v2_2_5_predictive_comparison_summary.csv
materials_v2_2_5_paired_metric_summary.csv
materials_v2_2_5_prediction_uncertainty_summary.csv
materials_v2_2_5_predictive_value_decision.json
materials_v2_2_5_feature_use_evidence.json
materials_v2_2_5_report_summary.md
materials_v2_2_capability_matrix.json
materials_v2_2_evidence_summary.json
materials_v2_2_claim_matrix.json
materials_v2_2_uncertainty_boundary.json
materials_v2_2_prediction_contexts.json
materials_v2_2_closeout_decision.json
materials_v2_2_closeout_summary.md
```

The local source, normalized table, analysis-ready descriptor table, full
row-level screening results, validation predictions, and trust diagnostics are
local artifacts by default:

```text
materials_project_fe_si.csv
materials_project_normalized.csv
materials_project_screening_results.csv
materials_project_v1_3_acquired.csv
materials_project_v1_3_analysis_ready.csv
materials_project_v1_3_validation_predictions.csv
materials_project_v1_3_trust_diagnostics.csv
outputs/materials_physics_v2_2/materials_physics_v2_2_feature_matrix.csv
outputs/materials_physics_v2_2/materials_physics_v2_2_predictions.csv
outputs/materials_project_structure_v2_2/
outputs/materials_structure_prediction_v2_2/
```

Row-level Materials Project structure payloads, converted structure entities,
cache chunks, descriptor tables, graph JSONL, and snapshot-alignment row tables
remain local-only. The v2.2.4 compact tracked files above summarize the
executed bounded existing-ID enrichment without storing row-level material IDs,
targets, structures, or API responses. The v2.2.5 compact tracked files
summarize the known-structure comparison without storing row-level
predictions, material IDs, feature matrices, split assignments, or plots.
The v2.2.6 compact tracked files summarize capability, evidence, claim,
prediction-context, uncertainty, artifact-lineage, and release-readiness
boundaries without rerunning models or storing row-level payloads.

## Smart Factory v1.4 Case Study Summaries

Compact reproducibility artifacts for the Smart Factory v1.4 SECOM fallback
case study include:

```text
smart_factory_v1_4_schema_inventory.csv
smart_factory_v1_4_readiness_summary.csv
smart_factory_v1_4_feature_quality_inventory.csv
smart_factory_v1_4_integrity_summary.csv
smart_factory_v1_4_missingness_summary.csv
smart_factory_v1_4_temporal_summary.csv
smart_factory_v1_4_split_feasibility.csv
smart_factory_v1_4_spc_feasibility.csv
smart_factory_v1_4_analysis_ready_summary.csv
smart_factory_v1_4_classification_metrics.csv
smart_factory_v1_4_classification_split_diagnostics.csv
smart_factory_v1_4_classification_model_summary.csv
smart_factory_v1_4_random_temporal_gap.csv
smart_factory_v1_4_threshold_summary.csv
smart_factory_v1_4_error_structure_summary.csv
smart_factory_v1_4_classification_conclusion.csv
smart_factory_v1_4_model_eligibility.csv
smart_factory_v1_4_temporal_stability_summary.csv
smart_factory_v1_4_operational_boundary.csv
smart_factory_v1_4_claim_boundary.csv
smart_factory_v1_4_trust_summary.csv
smart_factory_v1_4_closeout_conclusion.csv
```

The local row-level analysis-ready and classification prediction tables are
regenerated from documented scripts and remain local-only by default:

```text
smart_factory_v1_4_secom_analysis_ready.csv
smart_factory_v1_4_classification_predictions.csv
```

## Reliability v1.5 Access-Gate and Full-Year Summaries

Compact reproducibility artifacts for the Reliability v1.5 Backblaze bounded
access gate include:

```text
reliability_v1_5_schema_inventory.csv
reliability_v1_5_leakage_schema_audit.csv
reliability_v1_5_readiness_summary.csv
reliability_v1_5_task_feasibility.csv
reliability_v1_5_asset_summary.csv
reliability_v1_5_event_censoring_summary.csv
reliability_v1_5_validation_feasibility.csv
reliability_v1_5_acquisition_conclusion.csv
```

Compact reproducibility artifacts for the v1.5.3 Backblaze full-year
normalization and readiness reassessment include:

```text
reliability_v1_5_full_archive_inventory.csv
reliability_v1_5_schema_drift_summary.csv
reliability_v1_5_trajectory_summary.csv
reliability_v1_5_event_integrity_summary.csv
reliability_v1_5_censoring_summary.csv
reliability_v1_5_temporal_coverage_summary.csv
reliability_v1_5_smart_feature_inventory.csv
reliability_v1_5_full_leakage_audit.csv
reliability_v1_5_horizon_feasibility.csv
reliability_v1_5_lookback_feasibility.csv
reliability_v1_5_split_feasibility.csv
reliability_v1_5_full_readiness_summary.csv
reliability_v1_5_full_task_readiness.csv
```

Compact reproducibility artifacts for the v1.5.4 fixed 7-day classification
baseline include:

```text
reliability_v1_5_classification_metrics.csv
reliability_v1_5_classification_split_diagnostics.csv
reliability_v1_5_classification_model_summary.csv
reliability_v1_5_asset_time_gap_summary.csv
reliability_v1_5_top_risk_summary.csv
reliability_v1_5_threshold_summary.csv
reliability_v1_5_error_structure_summary.csv
reliability_v1_5_classification_conclusion.csv
```

Compact reproducibility artifacts for the v1.5.5 trust-boundary closeout
include:

```text
reliability_v1_5_model_eligibility.csv
reliability_v1_5_validation_stability_summary.csv
reliability_v1_5_weighting_dependency_summary.csv
reliability_v1_5_resource_boundary.csv
reliability_v1_5_operational_boundary.csv
reliability_v1_5_claim_boundary.csv
reliability_v1_5_trust_summary.csv
reliability_v1_5_closeout_conclusion.csv
```

The raw Backblaze archive, large row-level normalized trajectory tables, local
7-day feature dataset, and row-level prediction diagnostics remain local-only
by default:

```text
data/raw/reliability/backblaze_drive_stats/data_2013.zip
reliability_v1_5_backblaze_analysis_ready.csv
reliability_v1_5_horizon_7d_lookback_7d_dataset.csv
reliability_v1_5_classification_predictions.csv
reliability_v1_5_*_row_level.csv
```

## Policy

- Raw downloaded datasets, source archives, full API responses, and credentials do not belong in `data/processed/`.
- Reproducible, compact inventory or summary artifacts may be tracked when they are intentionally part of a documented case study.
- Large generated tables should usually remain local-only unless they are needed for case-study reproducibility and are small enough to review.
- Temporary run outputs and caches belong under `outputs/` or local ignored paths, not in `data/processed/`.
- When updating a tracked processed CSV, include the generating script or command and basic row/count validation in the related case-study notes or change summary.
- Keep only intentional, documented summary artifacts.
- Do not store raw downloaded datasets here.
- Do not store API keys, Kaggle credentials, or local config files here.
- If a processed file is not referenced by case-study documentation or tests, review whether it should remain local/generated.
