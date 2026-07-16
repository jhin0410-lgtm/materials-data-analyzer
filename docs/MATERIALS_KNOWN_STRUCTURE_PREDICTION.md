# Materials Known-Structure Prediction

Status: `v2.2.5_complete`

v2.2.5 runs a bounded known-structure predictive comparison on the existing
838-row Materials Project cohort. It uses only snapshot-aligned rows from the
v2.2.4 structure enrichment step.

## Inputs

- cohort: 838 Materials Project rows
- prediction context: `known_structure_post_relaxation`
- target: original v1.3 `energy_above_hull` in eV/atom
- snapshot alignment: 257 exact target matches and 581 within numeric tolerance
- structure descriptors: Tier-1 v2.2.4 descriptors
- graph artifacts: generated in v2.2.4 but not used as model inputs

## Feature Sets

The comparison uses the same rows, split definitions, and fixed model families
for all feature sets:

- A: `known_structure_composition_baseline_v1`
- B: `known_structure_composition_physics_v1`
- C: `known_structure_structure_only_v1`
- D: `known_structure_baseline_plus_structure_v1`
- E: `known_structure_full_combined_v1`

Primary evidence comes from reduced-formula and chemical-system group splits.
The random split is retained only as an optimistic reference.

## Result

The compact decision is:

```text
structure_predictive_value_limited
```

Structure descriptors improved one primary group split only. The
chemical-system split showed some positive paired median MAE deltas for
selected fixed models, while reduced-formula group evidence did not show stable
improvement. A representative model is therefore not selected.

## Local Outputs

Row-level cohorts, predictions, split assignments, plots, and feature-set CSVs
are generated under:

```text
outputs/materials_structure_prediction_v2_2/
```

These files are local-only. Tracked outputs are compact summaries in
`data/processed/`.

## Non-Goals

v2.2.5 does not run MP acquisition, model tuning, SHAP, GNN training, DFT
calculation, graph embeddings, or target migration.
