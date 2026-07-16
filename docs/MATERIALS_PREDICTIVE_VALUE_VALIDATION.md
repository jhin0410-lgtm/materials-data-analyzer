# Materials Predictive-Value Validation

Status: `implemented_bounded`.

v2.2 validates whether the registered Materials physics-informed composition
features add predictive value beyond the existing v1.3 composition-only
baseline. It reuses the v1.3 target, split hierarchy, and fixed baseline model
families. It does not acquire new data, change splits after seeing results,
perform feature selection, tune hyperparameters, run SHAP, or claim a
physics-constrained model.

## Feature Sets

The comparison uses four feature-set roles:

- `original_baseline_full`: v1.3 baseline descriptors over the full v1.3 table,
  reference only
- `matched_baseline`: v1.3 baseline descriptors restricted to rows where v2.2
  physics features are generated
- `physics_only`: v2.2 registered physics/control features only
- `combined_baseline_physics`: matched baseline descriptors plus v2.2 features

The primary comparison is matched baseline versus physics-only versus combined
on the same rows, split policies, random state, and model configuration.

## Validation Hierarchy

Primary evidence:

- `reduced_formula_group`
- `chemical_system_group`

Secondary optimistic reference:

- `random`

Random split is not primary evidence because it can share formula, chemical
system, or descriptor patterns between train and test.

## Current Result

Current local execution:

- matched rows: 838
- generated feature rows: 838
- feature coverage: 1.0
- primary target: `energy_above_hull`
- primary decision: `performance_degraded`
- combined primary median MAE improvement: `-0.0005982293913257795`
- physics-only primary median MAE improvement: `0.0`

The v2.2 features were generated and used in matched comparison, but they did
not improve the group-aware baseline overall. The negative result is retained
as a trust-boundary outcome.

## CLI

```powershell
python -m src.cli run-materials-feature-comparison configs/examples/materials_physics_predictive_comparison.json
python -m src.cli show-materials-feature-comparison latest
python -m src.cli export-materials-feature-summary
```

## Claim Boundary

Allowed with limits:

- composition-derived `physics_informed_feature_available`
- matched-comparison `physics_informed_feature_used`
- `performance_degraded` predictive-value decision

Not allowed:

- physics-constrained model
- hybrid physics ML
- DFT replacement
- robust energy-above-hull prediction
- new-material discovery
- synthesizability claim
- causal mechanism
- SHAP explanation

The result should be read as a bounded negative/limited validation finding, not
as proof that all physics descriptors are useless or that a different dataset
could not support a stronger claim.
