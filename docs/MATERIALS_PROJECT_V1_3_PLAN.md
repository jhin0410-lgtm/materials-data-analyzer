# Materials Project v1.3 Plan

## Objective

v1.3 prepares an exact-provenance Materials Project validation dataset contract
before any live API acquisition, feature generation, or modeling.

The goal is to move beyond the v1.2 50-row descriptive pilot only when the
query scope, provenance capture, target/feature boundary, leakage controls, and
validation strategy are explicit.

No Materials Project API or network call was made in v1.3.1.

## Why A New Dataset Is Required

The v1.2 dataset is useful as a compact descriptive screening pilot, but it is
not enough for predictive validation:

- It has only 50 rows.
- Query provenance is reconstructed.
- Retrieval timestamp and API/database version are unknown.
- It has no composition-derived numeric descriptor table.
- It cannot support strong group-aware generalization claims.

v1.3 therefore starts with contracts rather than acquisition.

## Installed Contract Inspection

Local introspection, without network access, found:

- Python: 3.13.14
- `mp-api`: 0.46.4
- `pymatgen`: 2026.5.4
- `emmet-core`: 0.87.1
- `MPRester` import: available
- `SummaryRester.search` import: available
- `SummaryDoc` import: available

The installed `summary.search` signature supports:

- `elements`
- `exclude_elements`
- `num_elements`
- `deprecated`
- `theoretical`
- `include_gnome`
- `fields`
- `all_fields`
- `chunk_size`
- `num_chunks`
- `_sort_fields`
- `energy_above_hull`
- `is_stable`

The callable signature does not expose `nelements` as a parameter in this
installed version; use `num_elements=(2, 5)` for acquisition and request the
returned `nelements` field.

`MPRester` exposes database/emmet version helper names, but live acquisition
must record the database version during an authenticated run. This was not
called in v1.3.1.

## Acquisition Scope

Contract file:

```text
data/case_studies/materials_project/acquisition_spec_v1_3.json
```

Planned scope:

- Materials whose returned composition/formula contains both Fe and Si.
- Binary through quinary Fe/Si-containing systems.
- Not restricted to binary Fe-Si.
- Exclude deprecated records with `deprecated=false`.
- Do not filter on `energy_above_hull`.
- Do not filter on `is_stable`.
- Use `include_gnome=false` explicitly rather than relying on the client
  default.
- Do not filter theoretical/non-theoretical status initially; capture and audit
  the `theoretical` field after acquisition.

The installed client accepts `elements=["Fe", "Si"]`, but v1.3.2 must still
verify after acquisition that every returned row contains both Fe and Si. API
ordering is not assumed deterministic; saved tabular output should be sorted by
`material_id`.

## Requested Field Tiers

Mandatory identity/provenance fields:

- `material_id`
- `formula_pretty`
- `chemsys`
- `elements`
- `nelements`
- `theoretical`
- `deprecated`

Target:

- `energy_above_hull`

Composition source fields:

- `composition`
- `composition_reduced`
- `formula_pretty`

Analysis-only or optional comparison fields:

- `formation_energy_per_atom`
- `density`
- `volume`
- `nsites`
- `band_gap`
- `is_metal`
- `symmetry`

Provenance candidates:

- `origins`
- `last_updated`
- `database_IDs`

Leakage candidates:

- `is_stable`
- `formation_energy_per_atom`
- `energy_above_hull`

The full `structure` object is excluded from the first v1.3 acquisition
contract to keep the initial tabular dataset smaller and focused on
composition-derived baseline validation.

## Provenance Contract

v1.3.2 acquisition must capture:

- acquisition UTC timestamp
- Python version
- `mp-api` version
- `pymatgen` version
- `emmet-core` version
- API endpoint
- Materials Project database version
- exact query parameters
- exact requested fields
- returned row and column counts
- chunk size and chunk/result count
- raw output SHA-256
- sorted output SHA-256
- duplicate `material_id` count
- null target count
- `credential_included=false`
- `absolute_path_included=false`
- execution status
- partial download/error status

Credentials must be injected only through the `MP_API_KEY` environment variable
and must not be stored in configs, manifests, logs, exceptions, or reports.

## Modeling Target

Modeling contract file:

```text
data/case_studies/materials_project/modeling_contract_v1_3.json
```

Planned target:

- `energy_above_hull`
- continuous regression target
- unit: eV/atom
- source: Materials Project calculated property

This target is a computed Materials Project output. Modeling it is not a new
DFT calculation, not experimental stability validation, and not a
synthesizability proof.

## Feature Tiers

Primary feature tier:

- composition-only descriptors derived from `composition`,
  `composition_reduced`, `formula_pretty`, `elements`, `nelements`, and
  `chemsys`

Optional comparison tier:

- property-assisted computed fields such as `formation_energy_per_atom`,
  `density`, `volume`, `nsites`, `band_gap`, `is_metal`, and `symmetry`

Property-assisted features must be labeled separately because they are Materials
Project computed outputs, not early composition-only screening descriptors.

## Leakage Policy

Forbidden features include:

- `material_id`
- raw formula one-hot or hash encodings
- `energy_above_hull`
- `is_stable`
- target-derived ranks, labels, or screening scores
- post-split global target statistics

`formation_energy_per_atom` is a leakage candidate for stability-like tasks and
belongs only in separately labeled comparison experiments.

## Split Strategy

Minimum comparison set:

1. Deterministic random split: naive baseline only.
2. Reduced-formula group split: controls same-composition and polymorph
   leakage.
3. Chemical-system group split: checks unseen element-family generalization.

No split is executed in v1.3.1. v1.3.2 must first confirm that the acquired
dataset has enough groups for each strategy.

## Data Sufficiency Gates

Stop before modeling if:

- valid target rows are too few
- distinct reduced-formula groups are too few
- distinct chemical-system groups are too few
- target null ratio is excessive
- target is nearly constant or dominated by zero values
- composition parsing failure rate is high
- duplicate `material_id` values are unresolved
- acquisition is partial or failed
- database/package versions are not recorded
- requested mandatory fields are missing

Thresholds must be justified after the real acquisition audit rather than
claimed in advance.

## v1.3 Phases

- v1.3.1: exact acquisition and modeling contract, readiness inspection, and
  non-network validation.
- v1.3.2: authenticated acquisition and provenance manifest, if the user chooses
  to proceed.
- v1.3.3: composition descriptor table and data sufficiency audit.
- v1.3.4: baseline validation comparison across random, reduced-formula group,
  and chemical-system group splits.
- v1.3.5: final Materials Project validation report and closeout.

## Smart Factory And Reliability Roadmap Boundary

v1.3 is limited to broader Materials Project acquisition and group-aware
validation planning. It does not include dashboards, MES integration, smart
factory process-quality analysis, survival analysis, or reliability engineering
expansion.

v1.4 is reserved for a Smart Factory Process Quality Case Study. v1.5 is
reserved for Generic Reliability Engineering.

## Non-goals

v1.3.1 does not:

- call the Materials Project API
- read or print API keys
- download data
- overwrite the v1.2 local dataset
- generate composition descriptors
- train a model
- execute train/test splits
- modify screening results
- build a dashboard
- implement smart factory analysis
- implement survival analysis
- update README/CHANGELOG closeout text
- restructure the repository

## Immediate Next Step

If v1.3 proceeds, the next step is v1.3.2: run an authenticated live acquisition
using the acquisition contract, record exact provenance, save local-only raw and
processed artifacts, and stop before modeling until the data sufficiency gates
are checked.
