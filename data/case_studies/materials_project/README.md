# Materials Project Case Study

This folder documents a small Materials Project descriptive property screening
pilot for `materials_data_analyzer`.

The case study demonstrates a reproducible tabular workflow:

```text
local Materials Project-derived CSV
-> query/provenance contract
-> schema normalization and quality audit
-> deterministic descriptive property screening
-> compact case-study summary
```

It is not a Materials Project API download workflow, ML prediction workflow,
DFT simulation workflow, or claim of new materials discovery.

## Scope

- Dataset: 50-row local pilot artifact.
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
  decision gate, and conclusions.

## Configuration Files

- [Query spec](query_spec.json): reconstructed credential-free query contract.
- [Schema contract](schema_contract.json): canonical seven-column schema and
  quality rules.
- [Screening spec](screening_spec.json): deterministic descriptive screening
  configuration.

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

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_tests.ps1
```

## Artifact Policy

Tracked compact artifacts:

- `query_spec.json`
- `schema_contract.json`
- `screening_spec.json`
- `data/processed/materials_project_query_manifest.json`
- `data/processed/materials_project_property_inventory.csv`
- `data/processed/materials_project_quality_summary.csv`
- `data/processed/materials_project_screening_summary.csv`
- source, methodology, and case-study docs

Local-only artifacts:

- `data/processed/materials_project_fe_si.csv`
- `data/processed/materials_project_normalized.csv`
- `data/processed/materials_project_screening_results.csv`
- raw Materials Project API responses

## Current Pilot Limitations

- Small 50-row local dataset.
- Reconstructed provenance rather than exact historical query metadata.
- No composition descriptors or structural feature expansion.
- No ML model, train/test validation, or virtual experiment prediction.
- Energy-above-hull ranking is descriptive and does not guarantee
  synthesizability, process feasibility, or experimental performance.
