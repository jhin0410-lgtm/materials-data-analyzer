# Battery Forecast Failure Diagnostics

Status: `v2.6.2_feature_stage_complete_with_diagnostic_closeout`

The v2.6.2 audit explains the negative v2.6.1 Battery forecasting benchmark
without changing its model, features, split, horizon, or official metrics. It
is a diagnostic analysis, not a performance-improvement stage.

## Source Benchmark

The source remains the exact five-cycle `warm_start_cross_battery` benchmark:

- 34 source trajectories and 33 evaluable batteries;
- 2,100 prediction origins;
- persistence pooled MAE `3.425575`;
- fixed Ridge pooled MAE `4.153699`;
- Ridge pooled MAE worsening `21.2555%`;
- 13 of 33 batteries improved by Ridge;
- source scientific assessment `unsupported`.

The tracked source-benchmark checksum is
`9bcc58b0f7df95cc996aee6f509aac6a9293f753186b50d8b1635bb6ad392d42`.
The local detailed-result checksum is
`5e565dfe7f4b183bbca3531f46190071732f395afd0f7fa0f63c4896e502e906`.
The existing benchmark was re-executed with the same config and seed because
its local prediction artifact had been removed. Both checksums matched; the
v2.6.1 tracked summary was not changed.

## Predeclared Diagnostics

The audit uses fixed rules:

| Diagnostic | Rule |
|---|---|
| Sparse evaluation | At most 10 prediction origins |
| Abrupt transition | At least 10 percentage points between adjacent observations |
| High target variation | Trajectory standard deviation at least 15 percentage points |
| Low target variation | Trajectory standard deviation at most 1 percentage point |
| High local volatility | Five-observation standard deviation at least 5 percentage points |
| Flat local window | Five-observation range at most 0.5 percentage points |
| Early regime | Prediction origin cycle at most 50 |
| Middle regime | Prediction origin cycle 51 through 100 |
| Late regime | Prediction origin cycle above 100 |
| Physical range | 0 through 150 percent |

The regime rule uses only the prediction-origin cycle. It does not use the
future target, final trajectory length, EOL threshold, or failure outcome.
Quality flags do not delete or alter rows.

## Influence Analysis

Ridge excess absolute error is concentrated but not attributable to one
battery:

- the top three excess-error contributors account for `68.12%`;
- the top five account for `90.35%`;
- the largest Ridge absolute-error contributor accounts for `15.20%`;
- no leave-one-battery-out analysis reverses persistence superiority;
- leave-one-out Ridge-minus-persistence MAE remains between `0.5794` and
  `0.8229`.

The worst per-battery Ridge MAE belongs to
`battery_ref_14c990fd50cc`: Ridge `45.7799`, persistence `47.8119`, over seven
predictions. Ridge is better for this battery, so the highest per-battery MAE
is not the source of the aggregate Ridge deficit.

Six batteries have at most ten prediction origins, representing `1.43%` of
prediction rows. Their net excess-error share is approximately zero and
slightly negative. Sparse metrics are unstable locally, but they do not
explain the pooled result.

## Regime Results

| Regime | Predictions | Persistence MAE | Ridge MAE | Ridge relative improvement |
|---|---:|---:|---:|---:|
| Early | 1,009 | 3.7367 | 4.1592 | -11.31% |
| Middle | 635 | 3.7232 | 4.9473 | -32.88% |
| Late | 456 | 2.3227 | 3.0363 | -30.72% |

Ridge is worse in every fixed-cycle regime. This supports a diagnostic model
form mismatch and a strong short-horizon persistence baseline, but does not
identify a degradation mechanism.

## Trajectory and Local-Trend Findings

The 34 tracked trajectories contain:

- 28 missing-cycle gaps across 13 batteries;
- 23 abrupt drops across 15 batteries;
- 39 abrupt upward recoveries across 20 batteries;
- 15 suspicious opposite-direction single-point jumps across 8 batteries;
- 8 high-target-volatility batteries;
- 1 low-target-variation battery.

There are no duplicate or source-order-reversed cycles. Prediction origins
near an abrupt transition have higher MAE for both models, but account for
only `6.09%` of Ridge excess error. Abrupt transitions are therefore relevant
diagnostics, not the primary aggregate explanation. Correlations between
local slope, volatility, retention level, monotonicity, and absolute error are
descriptive and non-causal.

## Physical Plausibility

Ridge produces three negative, out-of-bound predictions. They account for
`0.24%` of Ridge absolute error and `1.30%` of Ridge excess error. No clipping
is applied. Physical extrapolation is present but is not the main pooled-MAE
driver.

## Comparability

The immediate Kaggle package, battery identity, ambient temperature, and
global preprocessing lineage are available. Comparability is nevertheless
`comparability_not_established` because:

- the official original NASA snapshot/version is unresolved;
- chemistry and nominal capacity are unavailable in the tracked table;
- protocol evidence is group-level rather than cycle-specific;
- cutoff-voltage policy is unavailable;
- four batteries span multiple recorded ambient temperatures;
- calibration and measurement uncertainty are unavailable.

Missing fields are not filled, inferred, or treated as equal conditions.

## Failure-Mode Taxonomy

The deterministic labels `baseline_dominant`, `sparse_evaluation`,
`high_target_volatility`, `abrupt_transition`, `physical_extrapolation`,
`possible_data_quality_issue`, `metadata_comparability_unresolved`,
`model_form_mismatch`, and `no_clear_failure_mode` are diagnostic
classifications. They are not physical-mechanism diagnoses.

## Scientific Closeout

The closeout is `diagnostic`:

- excess error is concentrated, but no individual battery controls the
  scientific conclusion;
- sparse groups, abrupt-transition proximity, and three nonphysical
  predictions do not explain the aggregate deficit;
- Ridge is worse in all three predeclared cycle regimes;
- short-horizon persistence strength and battery-dependent linear-model
  mismatch are the best-supported descriptive explanation;
- source/test-condition comparability remains unresolved.

A new model experiment is not justified without comparability metadata and a
predeclared external-validation plan. This audit does not support predictive
generalization, SOH/RUL/lifetime, mechanism, causal, engineering, or
production claims.

## Reproduction

The detailed benchmark artifacts are local-only. From a tracked checkout:

```powershell
python -m src.cli --json run-battery-generalization-forecast configs/examples/battery_generalization_forecast.json --local-only
python -m src.cli --json preview-battery-forecast-diagnostics configs/examples/battery_forecast_diagnostics.json
python -m src.cli --json run-battery-forecast-diagnostics configs/examples/battery_forecast_diagnostics.json
python -m src.cli --json validate-battery-forecast-diagnostics outputs/v2_6_battery_diagnostics/diagnostic_summary.json
```

The diagnostics perform no model fitting, network access, credential access,
source mutation, outlier removal, clipping, or post-hoc threshold tuning.
