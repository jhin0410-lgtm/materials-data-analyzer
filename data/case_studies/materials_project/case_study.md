# Materials Project Descriptive Property Screening Pilot

## Objective

This case study demonstrates a small, reproducible descriptive property
screening workflow using a local Materials Project-derived tabular dataset.

The goal is to show how `materials_data_analyzer` can preserve provenance,
validate a schema, audit data quality, and rank already available computed
properties in a transparent way.

This is not a machine-learning prediction task, virtual experiment model,
synthesis recommendation, or claim of new material discovery.

## Dataset Scope

The current pilot dataset is a local 50-row CSV with seven columns:

```text
material_id
formula
band_gap_ev
formation_energy_ev_atom
energy_above_hull_ev_atom
density_g_cm3
volume_a3
```

All rows contain both Fe and Si in the formula string. The rows are multinary
Fe/Si-containing materials; the dataset is not a binary-only Fe-Si dataset.

The values are Materials Project calculated properties. They are not direct
experimental measurements, process data, or manufacturing results.

## Provenance Status

The current query provenance is `reconstructed`.

Known provenance facts:

- Local source artifact: `data/processed/materials_project_fe_si.csv`
- Row count: 50
- Column count: 7
- Query contract: `query_spec.json`
- Schema contract: `schema_contract.json`
- Retrieval timestamp: unknown
- Materials Project API/database version: unknown
- API credentials: not stored in the repository

The current local artifact is useful as a pilot, but it should not be treated as
an exact-provenance research dataset.

## Data Quality

The v1.2.2 normalization and quality audit produced:

- Valid / warning / invalid rows: 50 / 0 / 0
- Duplicate material identifiers: 0
- Numeric conversion failures: 0
- Non-finite numeric values: 0
- Missing numeric property values: 0
- Rows containing Fe: 50
- Rows containing Si: 50
- Rows containing both Fe and Si: 50
- Binary Fe-Si rows: 0
- Multinary Fe/Si-containing rows: 50

No rows were silently removed. The normalized table and full screening results
remain local generated artifacts.

## Screening Specification

The screening configuration is stored in:

```text
data/case_studies/materials_project/screening_spec.json
```

Default v1.2.3/v1.2.4 settings:

- Filter: `quality_status in ["valid"]`
- Objective: minimize `energy_above_hull_ev_atom`
- Weight: 1.0
- Tie policy: `min_rank`
- Missing-value policy: `exclude_from_ranking`
- Top-N summary: 10 rows

The objective is intentionally narrow. It ranks already available computed
energy-above-hull values as a descriptive stability-proxy screen.

## Ranking Method

For the minimize objective, lower `energy_above_hull_ev_atom` values receive
higher objective scores. Scores are min-max scaled within the observed 50-row
pilot table.

The full row-level output preserves:

- original property values
- filter pass/fail status
- objective score
- objective rank
- composite score
- overall rank
- screening status and notes

The current pilot has a single objective, so the composite score is the same as
the energy-above-hull objective score.

Rows that fail filters or have missing objective values are retained in the
full results file but are not assigned a valid rank.

## Screening Results

Actual local screening smoke:

- Total rows: 50
- Filter pass/fail: 50 / 0
- Objective count: 1
- Ranked rows: 50
- Missing objective rows: 0
- Tie count: 7
- Compact summary rows: 10

Output files:

```text
data/processed/materials_project_screening_results.csv
data/processed/materials_project_screening_summary.csv
```

The compact summary is the case-study artifact intended for review. The full
50-row results table is treated as local-only by default.

## Tied Top Candidates

Seven rows share the top rank because their observed
`energy_above_hull_ev_atom` is `0.0`.

| Rank | material_id | formula | energy_above_hull_ev_atom | composite_score |
| ---: | --- | --- | ---: | ---: |
| 1 | `mp-aaabrwvs` | `Na3FeSiCO7` | 0.0 | 1.0 |
| 1 | `mp-aaabxcig` | `FeSiTc2` | 0.0 | 1.0 |
| 1 | `mp-aaacfyzt` | `HoFeSi` | 0.0 | 1.0 |
| 1 | `mp-aaacfzgh` | `PrFeSi` | 0.0 | 1.0 |
| 1 | `mp-aaacfzoe` | `SmFeSi` | 0.0 | 1.0 |
| 1 | `mp-aaacgiyk` | `CeFeSi2` | 0.0 | 1.0 |
| 1 | `mp-aaagbkqt` | `TiFeSi` | 0.0 | 1.0 |

The tied candidates are intentionally left tied. No secondary objective or
manual tie-break was added.

## Interpretation

Lower `energy_above_hull_ev_atom` is commonly useful as a computed
thermodynamic stability proxy. A value of `0.0` means the row is on the
calculated convex hull under the source database calculation context.

This does not guarantee:

- synthesis success
- process stability
- experimental stability
- manufacturing feasibility
- favorable kinetics
- defect tolerance
- performance under a specific temperature, pressure, or synthesis route

The ranking does not include kinetics, defects, temperature, pressure,
synthesis route, cost, toxicity, availability, or experimental validation.

## Limitations

- The dataset has only 50 rows.
- Query provenance is reconstructed, not exact.
- Retrieval timestamp and Materials Project API/database version are unknown.
- There are no composition descriptors, elemental fractions, or structural
  feature expansions.
- The screening objective is a single computed property.
- The result is a descriptive ranking, not a predictive model.
- Random/train-test validation and group-aware validation are not applicable
  because no model was trained.

## Reproduction Commands

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

- `data/case_studies/materials_project/query_spec.json`
- `data/case_studies/materials_project/schema_contract.json`
- `data/case_studies/materials_project/screening_spec.json`
- `data/processed/materials_project_query_manifest.json`
- `data/processed/materials_project_property_inventory.csv`
- `data/processed/materials_project_quality_summary.csv`
- `data/processed/materials_project_screening_summary.csv`
- source, methodology, README, and case-study documents

Local-only artifacts:

- `data/processed/materials_project_fe_si.csv`
- `data/processed/materials_project_normalized.csv`
- `data/processed/materials_project_screening_results.csv`
- raw Materials Project API responses

Credentials, API keys, absolute local paths, and raw API responses should not
be committed.

## Decision Gate

### Option A: Close as 50-row descriptive pilot

This option is appropriate when the goal is to demonstrate:

- generic deterministic property screening
- schema and quality-contract workflow
- provenance-aware local artifact handling
- compact portfolio documentation

Limitations:

- weak representativeness
- reconstructed provenance
- single-objective screening
- no ML validation
- no composition-family generalization claim

### Option B: Broader exact-provenance Materials Project query

This option is needed before claiming:

- property prediction
- group-aware validation
- composition-family comparison
- multi-objective screening beyond a pilot
- generalizable materials screening

Minimum requirements for a broader query:

- exact query specification
- retrieval timestamp
- Materials Project API/package/database version notes
- requested fields and units
- deterministic pagination/limit policy
- broader sample size
- explicit chemical-system policy
- duplicate/polymorph policy
- documented target/feature contract

Recommended decision:

> Close v1.2 as a 50-row descriptive screening pilot. Start a broader
> exact-provenance query only if the next goal is predictive modeling,
> multi-objective screening, or stronger generalization claims.

## Conclusion

The current Materials Project pilot successfully demonstrates a reproducible
descriptive property screening workflow over a small local tabular dataset.

It should be presented as a compact engineering-data platform example, not as a
scientific discovery result or production materials recommendation.
