# Materials Structure Prediction Readiness

Status: `v2.2.5_complete`

v2.2.4 evaluates whether the existing Materials Project validation cohort is
ready for a future structure-aware comparison. It does not run that comparison.

## Readiness Inputs

- existing Materials Project rows: 838
- unique requested material IDs: 838
- current API structures returned: 838
- valid `CrystalStructureEntity` records: 838
- composition-consistent structures: 838
- snapshot-aligned target/structure candidates: 838
- descriptor rows: 838
- periodic graph artifacts: 838

## Decision

Current decision:

```text
structure_prediction_ready_with_restrictions
```

The restrictions are important:

- the original v1.3 target is preserved and current target values are audit-only.
- source version metadata is unavailable.
- relaxed MP structures belong to the `known_structure_post_relaxation`
  context, not pre-structure composition screening.
- descriptors and graph artifacts have not been tested for predictive value.
- no GNN, structure-aware regression, SHAP, or DFT replacement claim has been
  made.

## v2.2.5 Outcome

v2.2.5 used only the snapshot-aligned cohort, explicitly declared the
known-structure prediction context, preserved the original v1.3 target, and
compared structure descriptors against the v2.2.1 composition-feature result.

The resulting decision is:

```text
structure_predictive_value_limited
```

Structure descriptors improved one primary group split only. No representative
known-structure model was selected, and graph artifacts remain non-model
artifacts.
