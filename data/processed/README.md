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
