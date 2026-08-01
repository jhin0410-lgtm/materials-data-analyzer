# Battery Target and Cross-Battery Comparability Audit

## Purpose

A low median absolute error can coexist with a very large mean absolute error and RMSE when a small number of batteries dominate the pooled result. Likewise, a mathematically valid retention target may still be unsuitable for a pooled cross-battery claim when reference-capacity conventions, cycle gaps, or observed test conditions differ materially.

This audit answers a bounded question:

> Are the normalized targets, reference-capacity fields, cycle continuity, observed-condition ranges, and battery-level error contributions sufficiently stable to interpret one pooled cross-battery metric without hiding concentration or source-quality problems?

It does not infer protocol identity, electrochemical mechanism, causality, or a correct exclusion rule.

## Automatic execution

The installed `mda-battery-intelligence` command runs this audit after the normal workflow completes. Existing results can be audited without rerunning feature extraction, knee detection, or grouped validation:

```powershell
mda-battery-result-audit `
  --run-output outputs/nasa_pcoe_signal_enriched_battery_intelligence
```

## Inputs

The audit reads only declared Battery Intelligence artifacts:

- `config_snapshot.json`;
- `tables/validated_cycle_summary.csv`;
- `tables/forecast_feature_table.csv`;
- `tables/validation_predictions.csv`;
- the existing scientific closeout and run manifest when present.

No source row, target, prediction, or battery is modified.

## Target and reference diagnostics

For each battery the audit records:

- observed cycle count, first and last cycle, cycle-gap count, and maximum cycle step;
- first, last, minimum, median, and maximum retention target;
- count and fraction outside the configured plausibility range;
- first-target deviation from 100%;
- maximum and median absolute adjacent target change;
- reference-capacity uniqueness and invalid-reference count when available;
- maximum reconstruction error for `100 * discharge_capacity_ah / reference_capacity_ah`;
- medians of available observed-condition features such as ambient temperature, current target, discharge duration, voltage, and temperature range.

Thresholds are diagnostic flags only. They do not trigger automatic deletion, clipping, renormalization, interpolation, or cohort reassignment.

## Error-concentration diagnostics

For every predicted battery and model the audit records:

- prediction count;
- actual target range;
- absolute-error sum, MAE, median absolute error, and maximum absolute error;
- fraction of the model's total pooled absolute error contributed by that battery.

The summary reports top-one and top-three battery error shares and the ratio of pooled mean absolute error to median absolute error. A pooled result is marked `diagnostic_only` when target/reference concerns or heavy-tail error concentration are detected.

## Outputs

```text
<run-output>/
├── tables/
│   ├── target_integrity_by_battery.csv
│   └── error_concentration_by_battery.csv
└── reports/
    ├── target_comparability_audit.json
    └── target_comparability_audit.md
```

The audit also adds a component status and limitation to the scientific closeout and records the new artifacts and checksums in `run_manifest.json`.

## Scientific boundary

A diagnostic flag does not prove that a battery is erroneous or incomparable. It identifies the exact battery, target behavior, reference convention, condition range, or error contribution that requires source- and protocol-aware review.

The pooled result remains visible. No flagged observation is silently removed, and the audit does not create a more favorable model metric.
