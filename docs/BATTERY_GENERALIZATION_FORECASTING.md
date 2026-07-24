# Battery-Level Generalization Forecasting

Status: `v2.6.1_feature_stage_complete_with_unsupported_hypothesis`

The current public platform release remains `v2.4.0`. This v2.6.1 feature
stage adds one bounded forecasting benchmark; it is not a release, lifetime
model, SOH/RUL model, or engineering decision system.

## Scientific Question

Can a model trained on other batteries predict capacity retention exactly five
cycles after an origin, using only the held-out battery's observations at or
before that origin?

The registered scenario is `warm_start_cross_battery`:

- battery identity is disjoint between model training and testing;
- a held-out battery's observed pre-origin history may be used;
- no observation after the origin is used as a feature;
- the scenario is not zero-shot because test-battery history is required.

## Data Readiness

The tracked source is
`data/processed/kaggle_nasa_battery_cycle_summary_analysis_ready.csv`.
It contains 2,495 rows and 34 battery trajectories. The exact source SHA-256
is `cf67c7210036e11032e140385864ce68bb8445e2f282e57259aa5b314ed1f7ce`.

The source has no missing target, duplicate battery/cycle pair, or source-order
inversion. Its retention range is 2.0982% to 119.8760%. One trajectory has
only four rows and cannot provide an eligible origin. The benchmark therefore
evaluates 2,100 origins across 33 batteries.

The exact immediate upstream is the locally verified Kaggle package
`patrickfleith/nasa-battery-dataset`. The official NASA snapshot/version,
retrieval timestamp, measurement uncertainty, and calibration metadata remain
unresolved. Retrieval reproducibility remains `insufficient_evidence`.

## Target And Features

The target is `capacity_retention_percent` at exact cycle `t + 5`, in percent.
Rows without an exact future-cycle target are excluded rather than shifted to
the next available observation.

Features available at cycle `t` are:

- retention at `t`;
- exact lags 1, 2, and 3;
- trailing five-observation mean and population standard deviation;
- trailing five-observation linear slope;
- current cycle index.

The rolling window includes the origin and only earlier observations. It is
never centered. Full-trajectory extrema, final capacity, EOL, future labels,
post-target processing, and test-target normalization are prohibited.

Exclusion accounting:

| Reason | Rows |
| --- | ---: |
| Exact `t + 5` target unavailable | 204 |
| Required exact lag unavailable | 159 |
| Minimum history unavailable | 32 |
| Current target missing | 0 |

## Validation And Preprocessing

Five deterministic GroupKFold partitions use `battery_id` as the group.
Every one of the 33 evaluable batteries is held out once. Fold test sets
contain six or seven batteries, and train/test battery overlap is zero.
Random row splitting is not used.

The Ridge pipeline fits `SimpleImputer(strategy="median")`,
`StandardScaler`, and `Ridge(alpha=1.0)` on each training partition only.
No target-informed feature selection, threshold tuning, hyperparameter search,
clipping, or oversampling is performed.

## Baselines And Metrics

The persistence baseline predicts the origin retention at `t + 5`. Ridge is
the only fitted model. Metrics are pooled MAE, RMSE, and R2 plus battery-level
MAE, RMSE, and prediction count. R2 is diagnostic and is not used alone for
the conclusion.

| Model | Pooled MAE | Pooled RMSE | R2 | Median battery MAE | Worst battery MAE |
| --- | ---: | ---: | ---: | ---: | ---: |
| Persistence | 3.4256 | 11.5729 | 0.7430 | 2.7030 | 47.8119 |
| Ridge | 4.1537 | 11.2223 | 0.7584 | 2.6231 | 45.7799 |

Ridge worsened pooled MAE by 0.7281 percentage points, a -21.26% improvement
relative to persistence. It improved 13 of 33 batteries and did not improve
20. Under the predeclared rules, the scientific assessment is `unsupported`.
The higher Ridge R2 and slightly lower RMSE do not override the primary MAE
and cross-battery stability criteria.

## Physical Plausibility

Persistence produced no negative or out-of-bound prediction. Ridge produced
three negative predictions, all outside the predeclared 0% to 150% diagnostic
range. No prediction was silently clipped. These are model limitations, not
mechanism findings.

## Running The Benchmark

Preview without writes or model execution:

```powershell
python -m src.cli --json preview-battery-generalization-forecast configs/examples/battery_generalization_forecast.json
```

Run the fixed local benchmark:

```powershell
python -m src.cli --json run-battery-generalization-forecast configs/examples/battery_generalization_forecast.json
```

Validate the deterministic detailed result:

```powershell
python -m src.cli --json validate-battery-generalization-forecast outputs/v2_6_battery_generalization/forecast_summary.json
```

Detailed predictions and per-battery metrics remain under the ignored
`outputs/v2_6_battery_generalization/` path. The compact tracked summary is
checkout-reproducible because its row-level input is tracked.

## Claim Closeout

- **Result:** the fixed Ridge benchmark does not beat persistence on pooled
  MAE and improves only 13 of 33 batteries.
- **Evidence level:** software-validated, scientifically unsupported.
- **Strongest evidence:** exact-horizon features, zero battery overlap,
  deterministic repeated checksums, and explicit persistence comparison.
- **Primary limitation:** restricted source provenance and unstable
  battery-level improvement.
- **Evidence that would change the conclusion:** independent comparable
  battery data with protocol/calibration metadata and stable improvement over
  persistence under the same leakage-safe design.
- **Suitable for exploration:** yes, as a negative baseline and validation
  example.
- **Suitable for engineering decisions:** no.
- **Suitable for scientific claims:** no predictive-generalization,
  mechanism, lifetime, SOH, RUL, or causal claim.
