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
- source, methodology, and case-study docs

Local-only artifacts:

- `data/processed/materials_project_fe_si.csv`
- `data/processed/materials_project_normalized.csv`
- `data/processed/materials_project_screening_results.csv`
- `data/processed/materials_project_v1_3_acquired.csv`
- `data/processed/materials_project_v1_3_analysis_ready.csv`
- `data/processed/materials_project_v1_3_validation_predictions.csv`
- `data/processed/materials_project_v1_3_trust_diagnostics.csv`
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
