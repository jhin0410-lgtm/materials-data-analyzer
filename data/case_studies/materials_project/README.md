# Materials Project Case Study

This folder documents Materials Project descriptive screening and validation
case-study work for `materials_data_analyzer`.

The case study demonstrates a reproducible tabular workflow:

```text
local Materials Project-derived CSV
-> query/provenance contract
-> schema normalization and quality audit
-> deterministic descriptive property screening
-> exact-provenance acquisition and descriptor validation
-> group-aware baseline validation and trust-boundary closeout
-> bounded physics-feature construction and matched predictive-value validation
-> controlled known-structure enrichment and bounded structure-descriptor comparison
-> compact case-study summary
```

It is not a Materials Project API download workflow, ML prediction workflow,
DFT simulation workflow, or claim of new materials discovery.

## Scope

- Dataset: 50-row local pilot artifact.
- v1.3 dataset: 838-row exact-provenance local acquisition artifact.
- Chemistry scope: formulas contain both Fe and Si, but every row is
  multinary; this is not a binary-only Fe-Si dataset.
- Source property type: Materials Project calculated properties.
- Provenance status: `reconstructed`.
- Retrieval timestamp/API version: unknown.
- Default screening objective: minimize `energy_above_hull_ev_atom` as a
  descriptive stability-proxy screen.

## Key Documents

- [Source notes](source.md): source scope, provenance, credential policy, and
  raw/processed artifact policy.
- [Screening methodology](screening_methodology.md): scoring, filtering,
  ranking, missing-value handling, and interpretation limits.
- [Case study report](case_study.md): narrative summary, tied top candidates,
  validation closeout, decision gate, and conclusions.
- [v1.3 plan and follow-up](../../../docs/MATERIALS_PROJECT_V1_3_PLAN.md):
  acquisition, descriptors, validation, trust boundary, and closeout notes.
- [Materials physics features](../../../docs/MATERIALS_PHYSICS_FEATURES.md):
  v2.2 builder definitions, property source, coverage, and CLI.
- [Materials predictive-value validation](../../../docs/MATERIALS_PREDICTIVE_VALUE_VALIDATION.md):
  v2.2 matched baseline/physics comparison and claim boundary.
- [Materials known-structure prediction](../../../docs/MATERIALS_KNOWN_STRUCTURE_PREDICTION.md):
  v2.2.5 snapshot-aligned known-structure comparison and local/tracked outputs.
- [Materials structure predictive value](../../../docs/MATERIALS_STRUCTURE_PREDICTIVE_VALUE.md):
  v2.2.5 paired structure-descriptor decision and representative-model boundary.

## Configuration Files

- [Query spec](query_spec.json): reconstructed credential-free query contract.
- [Schema contract](schema_contract.json): canonical seven-column schema and
  quality rules.
- [Screening spec](screening_spec.json): deterministic descriptive screening
  configuration.
- [Acquisition spec](acquisition_spec_v1_3.json): v1.3 exact acquisition
  contract.
- [Modeling contract](modeling_contract_v1_3.json): v1.3 modeling scope and
  validation boundaries.
- [Descriptor spec](descriptor_spec_v1_3.json): v1.3 composition descriptor
  contract.
- [Validation spec](validation_spec_v1_3.json): v1.3.4 group-aware baseline
  validation contract.
- [Trust spec](trust_spec_v1_3.json): v1.3.5 applicability, claim-boundary,
  and XAI deferral policy.
- v2.2 feature and predictive-comparison schemas:
  [materials_physics_feature_definition_schema_v2.json](../../../data/platform/materials_physics_feature_definition_schema_v2.json)
  and
  [materials_predictive_comparison_schema_v2.json](../../../data/platform/materials_predictive_comparison_schema_v2.json).

## Reproduction Order

Run from the repository root.

```powershell
python scripts/build_materials_project_query_contract.py --input data/processed/materials_project_fe_si.csv --query-spec data/case_studies/materials_project/query_spec.json --manifest-output data/processed/materials_project_query_manifest.json --property-inventory-output data/processed/materials_project_property_inventory.csv
```

```powershell
python scripts/build_materials_project_normalized.py --input data/processed/materials_project_fe_si.csv --schema-contract data/case_studies/materials_project/schema_contract.json --normalized-output data/processed/materials_project_normalized.csv --quality-summary-output data/processed/materials_project_quality_summary.csv
```

```powershell
python scripts/run_materials_project_screening.py --input data/processed/materials_project_normalized.csv --screening-spec data/case_studies/materials_project/screening_spec.json --results-output data/processed/materials_project_screening_results.csv --summary-output data/processed/materials_project_screening_summary.csv
```

v1.3 trust-boundary closeout uses existing local v1.3 analysis-ready and
validation prediction artifacts:

```powershell
python scripts/run_materials_project_v1_3_trust_analysis.py
```

v2.2 physics-feature follow-up uses existing local v1.3 artifacts:

```powershell
python -m src.cli build-materials-physics-features configs/examples/materials_physics_feature_build.json
python -m src.cli run-materials-feature-comparison configs/examples/materials_physics_predictive_comparison.json
```

v2.2.5 known-structure follow-up uses the v2.2.4 local-only structure cache and
descriptor artifacts:

```powershell
python -m src.cli preview-materials-known-structure-comparison configs/examples/materials_known_structure_prediction_preview.json
python -m src.cli run-materials-known-structure-comparison configs/examples/materials_known_structure_predictive_comparison.json
python -m src.cli validate-materials-known-structure-result data/processed/materials_v2_2_5_predictive_value_decision.json
```

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_tests.ps1
```

## Artifact Policy

Tracked compact artifacts:

- `query_spec.json`
- `schema_contract.json`
- `screening_spec.json`
- `acquisition_spec_v1_3.json`
- `modeling_contract_v1_3.json`
- `descriptor_spec_v1_3.json`
- `validation_spec_v1_3.json`
- `trust_spec_v1_3.json`
- `data/processed/materials_project_query_manifest.json`
- `data/processed/materials_project_property_inventory.csv`
- `data/processed/materials_project_quality_summary.csv`
- `data/processed/materials_project_screening_summary.csv`
- `data/processed/materials_project_v1_3_applicability_summary.csv`
- `data/processed/materials_project_v1_3_error_structure_summary.csv`
- `data/processed/materials_project_v1_3_claim_boundary.csv`
- `data/processed/materials_project_v1_3_trust_conclusion.csv`
- `data/processed/materials_physics_v2_2_feature_definitions.csv`
- `data/processed/materials_physics_v2_2_property_source_metadata.json`
- `data/processed/materials_physics_v2_2_feature_coverage_summary.csv`
- `data/processed/materials_physics_v2_2_feature_use_evidence.json`
- `data/processed/materials_physics_v2_2_predictive_comparison_summary.csv`
- `data/processed/materials_physics_v2_2_predictive_value_decision.json`
- `data/processed/materials_physics_v2_2_report_summary.md`
- `data/processed/materials_v2_2_5_known_structure_cohort_summary.json`
- `data/processed/materials_v2_2_5_feature_set_snapshot.csv`
- `data/processed/materials_v2_2_5_predictive_comparison_summary.csv`
- `data/processed/materials_v2_2_5_paired_metric_summary.csv`
- `data/processed/materials_v2_2_5_prediction_uncertainty_summary.csv`
- `data/processed/materials_v2_2_5_predictive_value_decision.json`
- `data/processed/materials_v2_2_5_feature_use_evidence.json`
- `data/processed/materials_v2_2_5_report_summary.md`
- source, methodology, and case-study docs

Local-only artifacts:

- `data/processed/materials_project_fe_si.csv`
- `data/processed/materials_project_normalized.csv`
- `data/processed/materials_project_screening_results.csv`
- `data/processed/materials_project_v1_3_acquired.csv`
- `data/processed/materials_project_v1_3_analysis_ready.csv`
- `data/processed/materials_project_v1_3_validation_predictions.csv`
- `data/processed/materials_project_v1_3_trust_diagnostics.csv`
- `outputs/materials_physics_v2_2/materials_physics_v2_2_feature_matrix.csv`
- `outputs/materials_physics_v2_2/materials_physics_v2_2_predictions.csv`
- `outputs/materials_project_structure_v2_2/`
- `outputs/materials_structure_prediction_v2_2/`
- raw Materials Project API responses

## Current Pilot Limitations

- Small 50-row local dataset.
- Reconstructed provenance rather than exact historical query metadata.
- No composition descriptors or structural feature expansion.
- No ML model, train/test validation, or virtual experiment prediction.
- Energy-above-hull ranking is descriptive and does not guarantee
  synthesizability, process feasibility, or experimental performance.

## v1.2 Closeout

v1.2 is complete as a descriptive screening pilot. Broader exact-provenance
querying is required before prediction, group-aware validation, composition
descriptors, or ML property modeling claims.

## v1.3 Closeout

v1.3 is complete as a rigorous validation and trust-boundary case study.
Composition-only prediction remained weak, group-aware generalization was
limited, no predictive novel-material recommendation is claimed, and SHAP was
deferred because no model passed the interpretation eligibility gate. Observed
property descriptive screening remains reproducible.

## v2.2.1 Follow-Up

v2.2.1 implements selected composition physics-informed feature builders and a
matched predictive-value comparison. All 838 local v1.3 rows generated features
with complete property coverage, but the matched group-aware comparison
concluded `performance_degraded`. This records actual feature use without
claiming a physics-constrained model, hybrid physics/ML, DFT replacement,
SHAP explanation, or new-material discovery.

## v2.2.5 Follow-Up

v2.2.5 runs a known-structure post-relaxation comparison on the 838
snapshot-aligned rows from v2.2.4. The original v1.3 `energy_above_hull`
target remains the source of truth; current API target values are audit-only.

The decision is `structure_predictive_value_limited`: structure descriptors
improved one primary group split only, so no representative known-structure
model is selected. Graph artifacts remain deterministic local artifacts and
are not GNN evidence or model inputs.
