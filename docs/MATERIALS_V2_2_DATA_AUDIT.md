# Materials v2.2 Data Audit

Status: `implemented_bounded`.

This audit documents the data gate used for v2.2 Materials physics-aware
feature building. No Materials Project API call, new acquisition, or raw scan is
performed in v2.2. The workflow reuses existing local v1.3 artifacts.

## Source Artifacts

Observed local-only inputs:

- `data/processed/materials_project_v1_3_acquired.csv`
- `data/processed/materials_project_v1_3_analysis_ready.csv`

The acquired CSV has 838 rows and contains composition/formula metadata,
`material_id`, `energy_above_hull`, `composition`, `composition_reduced`, and
`formula_pretty`. The analysis-ready CSV has the same 838 material identifiers
plus v1.3 descriptor, group, target, and evaluation columns.

The local input files remain ignored/local-only. They are required to reproduce
the full v2.2 feature matrix and matched comparison, but tests use synthetic
fixtures and do not require local Materials Project data.

## Data Gate

v2.2 proceeds only when:

- the local v1.3 acquired and analysis-ready files exist
- composition values can be parsed from declared sources
- `material_id` can align the v2.2 feature matrix to the v1.3 analysis-ready table
- target and group columns remain unchanged
- no API/network access is required

Current local execution met these conditions:

- source rows: 838
- feature rows: 838
- generated feature rows: 838
- unsupported feature rows: 0
- observed elements: 67
- feature-property coverage min/median/max: 1.0 / 1.0 / 1.0

## Local And Tracked Outputs

Local-only row-level outputs are written under:

```text
outputs/materials_physics_v2_2/
```

Tracked compact outputs are:

```text
data/processed/materials_physics_v2_2_feature_definitions.csv
data/processed/materials_physics_v2_2_property_source_metadata.json
data/processed/materials_physics_v2_2_feature_coverage_summary.csv
data/processed/materials_physics_v2_2_feature_use_evidence.json
data/processed/materials_physics_v2_2_predictive_comparison_summary.csv
data/processed/materials_physics_v2_2_predictive_value_decision.json
data/processed/materials_physics_v2_2_report_summary.md
```

## Boundaries

This audit supports feature construction and matched validation only. It does
not support new Materials Project acquisition, DFT replacement, new-material
discovery, synthesizability claims, SHAP interpretation, or a
physics-constrained model claim.
