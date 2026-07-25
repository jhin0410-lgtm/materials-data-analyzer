# Platform v2.6 Roadmap

Status: `v2.6.3_battery_comparability_evidence_feature_stage_complete`

## Release Boundary

`v2.4.0` remains the current public release. v2.6.1, v2.6.2, and v2.6.3 are
feature-stage work and do not create a tag, release, or public version change.

## v2.6.1 Scope

v2.6.1 uses the existing tracked Kaggle NASA-derived Battery analysis-ready
table. It adds:

- exact five-cycle capacity-retention target alignment;
- current and lagged retention plus trailing rolling features;
- battery-disjoint deterministic GroupKFold evaluation;
- persistence and fixed Ridge baselines;
- train-only imputation and scaling;
- per-battery and pooled metrics;
- leakage, plausibility, source-mutation, and deterministic checksum audits;
- preview, run, and validate CLI commands.

The result is `unsupported`: Ridge does not improve pooled MAE over persistence
and improves only 13 of 33 evaluated batteries. This negative result is kept
without tuning or benchmark redesign.

## Boundaries

The scenario is warm-start cross-battery forecasting. It permits only
pre-origin history from each held-out battery and is not zero-shot. It does
not establish lifetime, RUL, SOH, mechanism, causal, calibrated-probability,
external-generalization, or engineering-decision evidence.

## v2.6.2 Failure Diagnostics

v2.6.2 preserves every v2.6.1 metric and adds deterministic, read-only
diagnostics over the existing predictions. The top five batteries account for
`90.35%` of Ridge excess absolute error, but no leave-one-battery-out result
reverses persistence superiority. Ridge is worse in the fixed early, middle,
and late regimes. Sparse batteries, abrupt-transition proximity, and three
nonphysical Ridge predictions are not primary aggregate drivers.

Source/test-condition comparability remains `comparability_not_established`.
The scientific closeout is `diagnostic`, not a mechanism or predictive
generalization finding. See
[Battery Forecast Failure Diagnostics](BATTERY_FORECAST_FAILURE_DIAGNOSTICS.md).

## v2.6.3 Comparability Evidence

v2.6.3 preserves the v2.6.1 model and metrics and the v2.6.2 diagnostic
conclusion. It audits a predeclared evidence matrix for chemistry, nominal
capacity, ambient temperature, charge/discharge protocols, cutoff voltage,
measurement calibration/uncertainty, and source snapshot/version.

The immediate Kaggle distribution and cycle-level ambient-temperature records
are verified, but no required field establishes cross-battery condition
equivalence. Chemistry, nominal capacity, cycle-specific commanded protocols,
cutoff policy, calibration/uncertainty, and the official NASA snapshot remain
unresolved; recorded temperatures are heterogeneous. The result is
`comparability_not_established` with an `inconclusive` scientific closeout.
See [Battery Comparability Evidence Package](BATTERY_COMPARABILITY_EVIDENCE_PACKAGE.md).

The v2.5 compatibility and retrieval-reproducibility conclusions are
unchanged. Battery retrieval reproducibility remains `insufficient_evidence`,
and no network, credential, acquisition, source mutation, model training,
metric recomputation, or public-version change is added.

## Next Evidence

Do not add model complexity from the current cohort. The next useful step is to
obtain source-backed battery-level chemistry and nominal capacity,
cycle-specific commanded protocols and cutoff policy, calibration/uncertainty
records, and an independently verifiable official source snapshot. Any future
cohort and validation plan must be predeclared before model evaluation.

## Non-Goals

v2.6 does not add deep learning, LSTM, Transformer, GNN, PINN, AutoML,
hyperparameter search, automatic acquisition, heterogeneous dataset merging,
mechanism fitting, lifetime prediction, UI, tag, or release work.
