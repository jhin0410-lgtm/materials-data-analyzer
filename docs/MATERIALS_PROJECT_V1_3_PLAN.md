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

## v1.3.4 Group-Aware Baseline Validation Follow-up

Group-aware baseline validation was implemented and executed using the
v1.3.3 analysis-ready descriptor table. No API/network call, descriptor
regeneration, feature selection, hyperparameter search, SHAP/LIME, deep
learning, candidate recommendation, or screening workflow was performed.

Fixed validation policy:

- feature count: `60` primary composition-only descriptors from
  `materials_project_v1_3_descriptor_inventory.csv`
- target: `energy_above_hull`
- splits: `10` fixed splits each for random, reduced-formula group, and
  chemical-system group validation
- test size: `0.20`
- random state: `42`
- models: `dummy_median`, `ridge_raw`, `ridge_log1p`,
  `histogram_gradient_boosting_raw`, and
  `histogram_gradient_boosting_log1p`
- nonnegative prediction policy: raw predictions preserved, negative
  predictions flagged, metrics calculated with `max(raw_prediction, 0)`

Validation execution:

- row-level prediction rows: `24795`
- fold/model metric rows: `150`
- valid split diagnostics: `30 / 30`
- source analysis-ready SHA-256 remained unchanged:
  `d06c78f3580b6380d5a1307d76e35310dd51b85fdbaaa1e3d28a8b7b50112320`

Overlap diagnostics:

- random split median descriptor/formula overlap rate: `0.4464`
- random split median chemical-system overlap rate: `0.9048`
- reduced-formula group split formula overlap: `0`
- reduced-formula group split descriptor-vector overlap: `0`
- chemical-system group split chemical-system overlap: `0`
- chemical-system group split descriptor-vector overlap: `0`

These overlap diagnostics should be interpreted as interpolation advantage and
overlap-driven optimism, not as proof of data leakage.

Median regression metrics by split, best model for each metric:

- random split best median R2: `0.0533`
  (`histogram_gradient_boosting_log1p`)
- reduced-formula group split best median R2: `0.0220`
  (`ridge_log1p`)
- chemical-system group split best median R2: `0.0405`
  (`ridge_log1p`)
- random split best median MAE: `0.0994` (`dummy_median`)
- reduced-formula group split best median MAE: `0.0856`
  (`histogram_gradient_boosting_log1p`)
- chemical-system group split best median MAE: `0.0728`
  (`histogram_gradient_boosting_log1p`)

Negative R2 values and dummy-baseline-like results were preserved in the
metrics. The group-aware scores indicate only limited generalization evidence
for composition-only descriptors.

Target treatment comparison:

- log1p treatment generally reduced RMSE for Ridge and histogram gradient
  boosting compared with their raw-target counterparts.
- log1p treatment generally reduced negative prediction rates.
- No single target treatment was selected automatically; trade-offs are
  recorded by metric and split strategy.

Screening-aligned metrics:

- best median precision at lowest 10 percent by deterministic fold metric:
  - random: `0.5882` (`dummy_median`)
  - reduced-formula group: `0.5625` (`dummy_median`)
  - chemical-system group: `0.6923` (`dummy_median`)

Because the dummy model produces tied predictions, deterministic `material_id`
tie-break ordering can strongly affect top-percent screening metrics. These
values are retained for audit but should not be interpreted as a physically
meaningful ranking model.

Ambiguity and subgroup findings:

- ambiguous formula groups had higher median MAE than singleton formula groups
  across all split/model families.
- composition-only diagnostic MAE from v1.3.3 was `0.04956`; model subgroup
  errors should be read relative to this empirical ambiguity diagnostic, not as
  a theoretical lower bound.
- theoretical=False rows generally had lower MAE than theoretical=True rows in
  the evaluated folds.

Validation conclusion by domain:

- interpolation/random: `validated_for_interpolation_only`
- unseen formula generalization: `limited`
- unseen chemical-system generalization: `limited`
- descriptive screening utility: `limited`

These conclusions are methodological validation summaries for Materials
Project computed properties. They are not causal evidence, not DFT, not
experimental stability validation, and not synthesizability claims. Random
split remains an optimistic interpolation baseline; formula split evaluates
unseen compositions; chemical-system split evaluates unseen additional-element
families. SHAP remains deferred until a defensible model and interpretation
scope are selected.

Generated local-only artifact:

- `data/processed/materials_project_v1_3_validation_predictions.csv`

Compact tracked-candidate artifacts:

- `data/case_studies/materials_project/validation_spec_v1_3.json`
- `data/processed/materials_project_v1_3_validation_metrics.csv`
- `data/processed/materials_project_v1_3_model_comparison_summary.csv`
- `data/processed/materials_project_v1_3_split_diagnostics.csv`
- `data/processed/materials_project_v1_3_screening_metrics_summary.csv`

Next step: v1.3.5 should turn the acquisition, descriptor, identifiability, and
validation artifacts into a final Materials Project validation report and
closeout without adding new models or tuning.

## v1.3.5 Trust Boundary and Closeout Follow-up

Model trust-boundary diagnostics were implemented over the existing v1.3.4
validation artifacts. No API/network call, data reacquisition, descriptor
expansion, split regeneration, hyperparameter tuning, SHAP, feature-importance
claim, deep learning, phase-diagram feature, active learning, or candidate
recommendation was performed.

Trust-boundary method:

- source validation prediction rows: `24,795`
- analysis-ready rows: `838`
- primary composition-only descriptors: `60`
- train/test membership reconstructed from existing prediction rows
- preprocessing fit on each reconstructed train fold only
- median imputation and StandardScaler-equivalent scaling used on train folds
- descriptor-space metric: Euclidean distance after train-fold preprocessing
- train reference: train-to-train nearest-neighbor distance with self-neighbor
  excluded
- fixed thresholds: in-domain at `<= p90`, boundary at `p90-p95`, and
  out-of-domain at `> p95` of the train NN-distance distribution
- target and prediction error were not used to set applicability thresholds

Applicability-domain row counts across unique split/test rows:

- in-domain: `3,868`
- boundary: `555`
- out-of-domain: `536`

The distance diagnostic is a proxy only. It is not calibrated uncertainty and
does not prove physical similarity. Across model variants, nearest-train
distance and absolute error were weakly or inconsistently related. The median
nearest-distance/absolute-error Spearman summary was `0.0905`, so the
applicability diagnostic is retained as a screening flag rather than a reliable
uncertainty measure.

Model eligibility gate:

- `ridge_raw`: `diagnostic_only`
- `ridge_log1p`: `diagnostic_only`
- `histogram_gradient_boosting_raw`: `diagnostic_only`
- `histogram_gradient_boosting_log1p`: `diagnostic_only`

No non-dummy model passed the conservative predictive interpretation gate. No
representative model was selected. Model validity therefore precedes XAI:
SHAP and physical feature-importance interpretation were deferred.

Distance, novelty, and subgroup findings:

- exact descriptor/formula novelty generally increased median error for the
  tree baseline and dummy baseline, but not consistently for every model family
- chemical-system-unseen rows generally had higher median error for tree
  baselines, while Ridge behavior remained inconsistent
- target extreme-tail rows had much larger median errors than near-zero or
  middle target strata across all model variants
- ambiguous formula behavior remained model-dependent and should be interpreted
  alongside the v1.3.3 composition identifiability audit
- theoretical=False and theoretical=True subgroup differences were not stable
  enough to support a causal or physical claim

Allowed claims:

- exact provenance dataset was acquired and validated
- composition-only descriptors were generated reproducibly
- random split contains substantial descriptor/formula overlap
- group-aware generalization is limited
- structure-free composition representation has identifiable limitations
- deterministic descriptive screening of observed Materials Project properties
  remains valid

Prohibited claims:

- accurate prediction of `energy_above_hull`
- reliable discovery of novel stable materials
- DFT replacement
- experimental synthesizability prediction
- causal physical mechanism
- robust unseen-chemical-system recommendation
- calibrated uncertainty
- production-ready screening model

Generated local-only artifact:

- `data/processed/materials_project_v1_3_trust_diagnostics.csv`

Compact tracked-candidate artifacts:

- `data/case_studies/materials_project/trust_spec_v1_3.json`
- `data/processed/materials_project_v1_3_applicability_summary.csv`
- `data/processed/materials_project_v1_3_error_structure_summary.csv`
- `data/processed/materials_project_v1_3_claim_boundary.csv`
- `data/processed/materials_project_v1_3_trust_conclusion.csv`

Final v1.3 conclusion:

v1.3 succeeded as a rigorous validation and trust-boundary case study.
Composition-only prediction remained weak, group-aware generalization was
limited, and no predictive novel-material recommendation is claimed. Observed
property descriptive screening remains reproducible. Stronger prediction would
require broader training coverage, structure information, calculation-context
features, or a different modeling scope.

Next phase: v1.4 should move to a Smart Factory Process Quality Case Study with
manufacturing process data, equipment/lot/time structure, SPC/process
capability, drift/anomaly diagnostics, defect/yield relationships, and offline
smart-factory decision support.
