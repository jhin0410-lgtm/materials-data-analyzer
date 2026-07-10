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

## v1.3.2 Acquisition Follow-up

Controlled live acquisition was implemented and executed from
`acquisition_spec_v1_3.json` without modifying the v1.2 Materials Project
dataset or screening artifacts.

Preflight used one Materials Project API request with `chunk_size=5` and
`num_chunks=1`. Full acquisition then used the exact query contract:
`elements=["Fe", "Si"]`, `num_elements=(2, 5)`, `deprecated=False`,
`include_gnome=False`, `all_fields=False`, the requested field list from the
spec, and no `theoretical`, `energy_above_hull`, or `is_stable` filter.

Recorded acquisition result:

- acquisition UTC timestamp: `2026-07-10T15:47:31+00:00`
- Materials Project database version: `2026.04.13`
- Python: `3.13.14`
- `mp-api`: `0.46.4`
- `pymatgen`: `2026.5.4`
- `emmet-core`: `0.87.1`
- returned rows: `838`
- columns: `21`
- unique material IDs: `838`
- duplicate material IDs: `0`
- Fe/Si-containing rows: `838`
- element-count out-of-range rows: `0`
- deprecated rows: `0`
- missing target rows: `0`
- target min/median/max: `0.0` / `0.048901150624092615` / `5.538618802559524`
- target zero count/rate: `141` / `0.16825775656324582`
- theoretical distribution: `False=204`, `True=634`
- reduced-formula groups: `548`
- chemical-system groups: `167`
- acquisition status: `success`
- data sufficiency gate: `ready_for_descriptor_stage`
- raw JSONL SHA-256:
  `1ba5a877b5aeb678fca914b2451b477aaf15844d635130e0843b6f7b596e3e0f`
- sorted table SHA-256:
  `7a47cc968d667dcc0c56712842ea764386b10dcd2a7e61ff89771c6e09ba3941`

Generated local-only artifacts:

- `data/processed/materials_project_v1_3_raw.jsonl`
- `data/processed/materials_project_v1_3_acquired.csv`

Compact tracked-candidate artifacts:

- `data/processed/materials_project_v1_3_acquisition_manifest.json`
- `data/processed/materials_project_v1_3_acquisition_summary.csv`

No composition descriptors, model training, train/test split, group split, or
screening was executed in v1.3.2.

## v1.3.3 Composition Representation and Identifiability Follow-up

Composition-only descriptor generation and readiness auditing were implemented
without API/network calls and without modifying the acquired v1.3 CSV or raw
JSONL artifacts.

Actual composition source:

- primary source used: `composition_reduced`
- parsed rows: `838 / 838`
- descriptor quality: `valid=838`
- source acquired CSV SHA-256 remained unchanged:
  `7a47cc968d667dcc0c56712842ea764386b10dcd2a7e61ff89771c6e09ba3941`

Descriptor families generated:

- stoichiometric composition descriptors: `9`
- elemental property aggregations: `40`
- pairwise mismatch descriptors: `5`
- composition category fractions: `6`
- primary composition-only feature count: `60`

Elemental property coverage from `pymatgen.core.Element` was complete for all
observed elements for:

- atomic number
- atomic mass
- periodic row
- periodic group
- electronegativity
- Mendeleev number
- atomic radius
- first ionization energy

No missing elemental property was zero-filled. No elemental property was
excluded for coverage in this acquired dataset.

Descriptor redundancy and identifiability diagnostics:

- high Spearman-correlation pairs with absolute correlation >= `0.95`: `39`
- rows sharing a duplicate composition-only descriptor vector: `400`
- unique descriptor vectors: `548`
- multi-row reduced-formula groups: `110`
- ambiguous same-formula groups: `109`
- mixed zero/positive same-formula groups: `16`
- maximum target range within the same reduced formula: `5.4784680825`
- composition-only diagnostic MAE to formula median: `0.04956294336856753`
- composition-only diagnostic RMSE to formula mean: `0.3157428762147056`

These ambiguity diagnostics are empirical composition-identifiability checks,
not model performance and not a theoretical lower bound. They show that
composition-only descriptors cannot uniquely identify all polymorph-specific
Materials Project `energy_above_hull` values.

Target suitability diagnostics:

- target count: `838`
- zero rate: `0.16825775656324582`
- variance: `0.15836790966256073`
- skewness: `10.243286412540181`
- median: `0.048901150624092546`
- p95: `0.2802287996303803`
- p99: `1.4547765986777292`
- max: `5.538618802559524`

No target transformation, classification label, two-stage target, screening
score, or rank target was created in v1.3.3.

Split-readiness diagnostics:

- reduced-formula groups: `548`
- chemical-system groups: `167`
- optional crystal-system groups: `7`
- random split readiness: `ready`
- reduced-formula group split readiness: `ready`
- chemical-system group split readiness: `ready`
- overall modeling readiness: `conditional`

The overall readiness is conditional because same-composition polymorph
ambiguity and duplicate descriptor vectors are material for a composition-only
validation task. This does not block v1.3.4, but it must be reflected in
validation interpretation.

Generated local-only artifact:

- `data/processed/materials_project_v1_3_analysis_ready.csv`

Compact tracked-candidate artifacts:

- `data/case_studies/materials_project/descriptor_spec_v1_3.json`
- `data/processed/materials_project_v1_3_descriptor_inventory.csv`
- `data/processed/materials_project_v1_3_descriptor_redundancy_summary.csv`
- `data/processed/materials_project_v1_3_composition_ambiguity_summary.csv`
- `data/processed/materials_project_v1_3_target_suitability_summary.csv`
- `data/processed/materials_project_v1_3_split_readiness_summary.csv`
- `data/processed/materials_project_v1_3_group_inventory.csv`

Descriptor importance is not causal evidence. Same composition may have
multiple polymorph targets. SHAP and other local explanation methods are
deferred until validated models exist. Physical mechanisms require structure,
process, and confounder review beyond this composition-only descriptor audit.

Next step: v1.3.4 may run baseline validation comparisons across deterministic
random, reduced-formula group, and chemical-system group splits using the
analysis-ready descriptor table. It should not treat random split performance as
generalization evidence.
