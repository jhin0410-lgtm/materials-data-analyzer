# Materials Project Acquisition Scope Audit

Status: `v2.2.3_complete`

This audit reconstructs the current 838-row Materials Project dataset from tracked v1.3 artifacts. It does not call the Materials Project API and does not create row-level structure artifacts.

## Lineage Verdict

- Verdict: `exact_query_reconstructed`
- Source collection: `materials.summary`
- Query method: `MPRester.materials.summary.search`
- Required elements: `Fe`, `Si`
- Element-count filter: `2` through `5`
- Deprecated records: excluded
- GNoMe records: excluded by explicit policy
- Target filter: none
- Requested target: `energy_above_hull`
- Final returned rows: `838`
- Analysis-ready rows: `838`

The 838 rows are both the returned v1.3 query result and the modeling subset after descriptor normalization. They are not the whole Materials Project universe.

## Dataset Scope

- Unique material IDs: `838`
- Missing material IDs: `0`
- Unique reduced formulas: `548`
- Unique chemical systems: `167`
- Unique elements observed: `67`
- Binary rows: `13`
- Ternary rows: `299`
- Quaternary-plus rows: `526`

This is a Fe/Si-containing multinary dataset. It is not a binary Fe-Si-only dataset.

## Target

- Target column: `energy_above_hull`
- Unit: `eV/atom`
- Missing target rows: `0`
- Zero target rows: `141`
- Mean: `0.11485223385742548`
- Median: `0.048901150624092546`
- Max: `5.538618802559524`

## Structure Status

The v1.3 query requested summary-level metadata such as `symmetry`, `density`, `volume`, and `nsites`, but it did not request full `structure` payloads. Current structure-body coverage is therefore `0/838`.

Actual structure enrichment status is `unavailable_no_local_api_data`. Future enrichment must use existing material IDs only, bounded chunks, local-only raw structure artifacts, checksums, and explicit credential-gated execution.

## Preserved v2.2.1 Result

The v2.2.1 predictive decision remains unchanged:

- `predictive_value_status`: `performance_degraded`
- `representative_model_selected`: `false`
- `physics_constrained_model`: `false`
- `hybrid_physics_ml`: `false`

Structure metadata in v2.2.3 does not alter model results or create a structure-aware predictive claim.
