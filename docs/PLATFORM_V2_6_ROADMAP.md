# Platform v2.6 Roadmap

Status: `v2.6.1_battery_generalization_forecasting_feature_stage_complete`

## Release Boundary

`v2.4.0` remains the current public release. v2.6.1 is a feature-stage
benchmark and does not create a tag, release, or public version change.

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

The v2.5 compatibility and retrieval-reproducibility conclusions are
unchanged. Battery retrieval reproducibility remains `insufficient_evidence`,
and no network, credential, or new-data acquisition is added.

## Next Evidence

Further model complexity is lower priority than independent comparable source
evidence. A later stage should require an external battery cohort with explicit
protocol, chemistry, timestamp, uncertainty, and calibration metadata before
reconsidering predictive generalization.

## Non-Goals

v2.6.1 does not add deep learning, LSTM, Transformer, GNN, PINN, AutoML,
hyperparameter search, automatic acquisition, heterogeneous dataset merging,
mechanism fitting, lifetime prediction, UI, tag, or release work.
