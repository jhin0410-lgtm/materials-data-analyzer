# Battery Target-Reference Sensitivity

## Purpose

This workflow tests whether the already computed exact-horizon validation
conclusion depends on the target/reference representation. It is a post-hoc
sensitivity audit of fixed predictions, not a second model-development attempt.

The predeclared views are:

1. `rated_capacity_retention_percent` — the declared primary cross-battery target;
2. `absolute_discharge_capacity_ah` — an observable alternative view whose pooled
   error remains diagnostic when batteries have different rated capacities.

The action answers a narrow question:

> Does the direction of the fixed Ridge-versus-persistence comparison change when
> the same validation errors are expressed in retention percentage or absolute Ah?

It does not select whichever target gives the best Ridge result.

## Required existing-run evidence

The Battery Intelligence run must contain:

- `tables/validated_cycle_summary.csv`;
- `tables/validation_predictions.csv`;
- `config_snapshot.json` with the configured group column.

For every evaluated prediction row, the cycle summary must provide the exact
battery/target-cycle record with:

- `capacity_retention_percent`;
- `reference_capacity_ah`;
- `discharge_capacity_ah`.

The action fails when target-cycle binding is ambiguous or when the stored
prediction `actual` does not match the bound target. Missing or invalid reference
metadata on an evaluated target row produces the explicit
`required_reference_metadata_missing` outcome. Missing reference values on cycles
that were not evaluated do not block the action.

## Execution

```powershell
mda-battery-target-sensitivity `
  --run outputs/nasa_analysis_sandbox_<timestamp> `
  --output outputs/nasa_target_reference_sensitivity_<timestamp>
```

Use `--overwrite` only to replace a previously recognized output from this same
workflow. The existing Battery run is protected input and is never modified.

## Outputs

- `summary.json` — bounded action outcome and Ridge/persistence comparisons;
- `model_comparison_by_target.csv` — row-weighted and battery-macro MAE for every
  existing model and both target views;
- `per_battery_comparison.csv` — battery-level MAE for every model/target pair;
- `bound_validation_predictions.csv` — the exact target-cycle binding and both
  transformed prediction views;
- `report.md` — concise human-readable interpretation boundary.

## Outcomes

### `conclusion_stable_across_defensible_targets`

The direction of both row-weighted and battery-macro Ridge-versus-persistence
comparisons remains unchanged across the two views.

### `conclusion_sensitive_to_target_reference`

At least one of the predeclared pooled comparison directions changes. This does
not promote the more favorable target. It shows that target scale/reference choice
materially affects the pooled conclusion and requires explicit scope separation.

### `required_reference_metadata_missing`

One or more evaluated target rows lack a finite positive reference capacity or a
finite non-negative discharge capacity. No alternative target result is produced.

## Scientific boundary

The same rows, battery identities, predictions, and validation split are reused.
The workflow does not:

- refit or retune a model;
- alter features;
- introduce first-observed capacity as a reference;
- clip, repair, smooth, or renormalize source targets;
- remove batteries or favorable error contributors;
- treat absolute-Ah pooling as interchangeable across capacity scales;
- establish a degradation mechanism, external validity, or engineering readiness.

A stable negative result means only that the existing Ridge-versus-persistence
ordering is not explained by this particular predeclared target representation.
It does not show that every possible scientifically defensible target definition
would produce the same conclusion.
