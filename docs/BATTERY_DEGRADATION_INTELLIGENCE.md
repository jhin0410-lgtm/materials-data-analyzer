# Battery Degradation Intelligence v1

## Purpose

Battery Degradation Intelligence asks a narrower and more defensible question than generic battery-life prediction:

> Given cycle-level retention history and, when available, admitted voltage/current/temperature signals, what degradation patterns, exact-horizon generalization performance, error structure, uncertainty, and extrapolation limits are supported by the measurements?

The workflow does not convert statistical associations into electrochemical mechanism, lifetime, RUL, optimization, or production-control claims.

## Analysis Flow

```text
cycle summary and optional raw signals
-> schema, unit, identity, duplicate, and time-order validation
-> raw-signal provenance and battery-cycle admission gate
-> cycle-level physical feature extraction
-> degradation-rate and knee-candidate diagnostics
-> exact-horizon origin-only forecast table
-> battery-disjoint GroupKFold validation
-> six transparent origin-only baselines plus Ridge
-> nested grouped conformal uncertainty
-> OOD and plausibility checks
-> battery / lifecycle / knee / regime / interval error diagnostics
-> component-level scientific closeout
```

## Installed Command

```powershell
mda-battery-intelligence `
  --cycle-summary data/processed/kaggle_nasa_battery_cycle_summary_analysis_ready.csv `
  --output outputs/battery_degradation_intelligence
```

A fast deterministic smoke run disables only the knee bootstrap:

```powershell
mda-battery-intelligence `
  --cycle-summary data/processed/kaggle_nasa_battery_cycle_summary_analysis_ready.csv `
  --output outputs/battery_degradation_intelligence_smoke `
  --n-splits 3 `
  --knee-bootstrap-samples 0
```

Existing output directories are not overwritten silently. Pass `--overwrite` only for deliberate full replacement.

## Cycle-Summary Contract

Default required columns:

| Column | Meaning | Requirement |
|---|---|---|
| `battery_id` | Stable battery identity | Non-missing; complete identity groups are held out |
| `cycle_index` | Cycle number | Finite numeric; unique and strictly increasing within a battery after audited sorting |
| `capacity_retention_percent` | Forecast target | Finite numeric; broad diagnostic plausibility range defaults to 0–150% |

Optional numeric quantities such as `discharge_capacity_ah`, `reference_capacity_ah`, `internal_resistance_ohm`, and `ambient_temperature_c` are validated and retained. Implausible values generate flags rather than silent deletion.

Duplicate battery-cycle rows are rejected because aggregation would require an explicit scientific rule. Exact-horizon targets require an observed row at `origin_cycle + horizon`; missing target cycles are counted and excluded rather than interpolated.

## Forecast Definition

The forecast is fixed-horizon and warm-start cross-battery:

- the target is retention at exactly `origin_cycle + horizon`;
- only the origin row and earlier history are predictors;
- battery identity is never a numeric feature;
- complete battery identities are held out with `GroupKFold`;
- preprocessing and Ridge fitting occur within each training fold;
- the held-out battery may contribute its own history before the origin, so this is not zero-shot forecasting;
- full observed life, future knee position, and future regime labels are never forecast features.

## Predeclared Origin-Only Baselines

Ridge is compared on exactly the same rows against:

| Baseline | Definition |
|---|---|
| `persistence` | Current retention |
| `trailing_mean` | Mean of the origin-only trailing window |
| `local_linear` | Full extrapolation of the trailing OLS slope |
| `damped_trend` | Half-strength extrapolation of the trailing slope |
| `robust_trend` | Median pairwise slope across available lags |
| `ewma_trend` | Recency-weighted linear slope across available lags |

No baseline silently clips predictions. The scientific closeout compares Ridge with the globally strongest predeclared origin-only baseline, not only persistence.

A row-level `row_oracle_baseline` is also recorded for error-envelope diagnosis. It selects the lowest-error baseline after the outcome is known and is explicitly **not** a deployable model or fair primary comparator.

## Error-Structure Diagnostics

The workflow reports global MAE, median absolute error, RMSE, 90th- and 95th-percentile absolute error, maximum error, and row-win fraction for every model.

Errors are then stratified by:

- battery identity;
- early, middle, and late observed lifecycle segment;
- pre-knee, near-knee, post-knee, or unavailable knee label;
- in-domain versus feature-range OOD status;
- recovery/flat, mild, moderate, and severe observed degradation rate;
- trajectory candidate regime;
- prediction-interval width;
- Ridge-improved versus Ridge-not-improved battery groups.

Lifecycle fraction and knee phase may use the complete observed trajectory. They are post-hoc diagnostic labels only and are never used as model inputs. Success/failure profiles are descriptive associations, not causal explanations.

## Optional Raw-Signal Contract

Required columns:

| Column | Unit / meaning |
|---|---|
| `battery_id` | Stable battery identity matching the cycle summary |
| `cycle_index` | Cycle number |
| `step_type` | Allowlisted charge, charge-CC, charge-CV, discharge, rest, or impedance label |
| `elapsed_time_s` | Seconds from the start of the step; strictly increasing within each segment |
| `voltage_v` | Cell voltage in volts |
| `current_a` | Current in amperes; step labels define integration direction |

Optional columns:

| Column | Unit / meaning |
|---|---|
| `step_id` | Explicit segment identity; required when a step type repeats or time resets |
| `temperature_c` | Temperature in degrees Celsius |
| `capacity_ah` | Instrument-reported cumulative capacity in ampere-hours |
| `global_time_s` | Monotonic experiment time for chronological temperature and transition analysis |

The workflow rejects duplicate battery-cycle-step-time rows, non-finite required values, nonpositive voltage, negative elapsed time, and unknown step labels. Units are never inferred from magnitudes.

## Raw-Signal Admission Gate

Raw signals may be extracted for software diagnostics without a provenance sidecar, but they do **not** enter predictive comparison unless all admission checks pass.

Example sidecar:

```json
{
  "source_name": "authoritative source name",
  "source_identifier": "stable URL, DOI, archive ID, or package identifier",
  "retrieved_at": "2026-08-01T00:00:00Z",
  "source_sha256": "exact sha256 of the raw-signal CSV",
  "license_or_terms": "source license or access terms",
  "battery_id_mapping_method": "exact mapping rule",
  "cycle_mapping_method": "exact mapping rule",
  "unit_declarations": {
    "elapsed_time_s": "s",
    "voltage_v": "V",
    "current_a": "A",
    "temperature_c": "degC",
    "capacity_ah": "Ah",
    "global_time_s": "s"
  }
}
```

Invocation:

```powershell
mda-battery-intelligence `
  --cycle-summary path/to/cycle_summary.csv `
  --raw-signal path/to/raw_signal.csv `
  --raw-signal-provenance path/to/raw_signal.provenance.json `
  --output outputs/battery_signal_comparison
```

Admission requires:

- complete provenance fields;
- exact source-file checksum match;
- valid declared units for every supplied physical signal;
- no raw battery-cycle pair absent from the cycle summary;
- at least five covered batteries;
- at least 50% battery and cycle-pair coverage.

If admitted, the workflow runs both capacity-only and signal-enriched grouped validation and records their Ridge MAE difference. Extraction alone does not establish signal-feature scientific value.

## Signal-Derived Features

When sufficient raw data are available, the workflow calculates:

- charge and discharge duration;
- CC and CV duration and CV fraction;
- charge/discharge throughput in Ah;
- charge/discharge energy in Wh;
- coulombic and energy efficiency;
- voltage and current extrema;
- temperature minimum, maximum, span, and start-to-peak rise;
- a globally ordered current-transition resistance proxy;
- `dQ/dV` peak height and voltage;
- median absolute `dV/dQ`;
- `dQ/dV` sensitivity across smoothing windows 5, 9, and 15.

The resistance feature is a transition proxy, not a validated impedance or internal-resistance measurement. Incremental-capacity features are withheld for multiple discharge segments, insufficient support, or non-monotonic trajectories. No smoothing, interpolation, outlier removal, or record exclusion occurs silently.

## Degradation and Knee Diagnostics

For each battery, the workflow produces:

- overall retention slope;
- rolling degradation rate;
- best two-segment linear candidate;
- pre- and post-candidate slopes;
- fit improvement over a single line;
- sensitivity to minimum-segment settings;
- residual-bootstrap 5–95% candidate interval.

`candidate` requires a more negative post-split slope and at least 10% SSE improvement. Otherwise the result is `weak_candidate` or insufficient. A knee candidate is not a physical transition or mechanism identification.

## Uncertainty and OOD

For each outer fold, interval width is estimated from inner battery-grouped out-of-fold absolute residuals using only outer-training batteries. The workflow reports:

- requested and observed interval coverage;
- interval-evaluable prediction count;
- features outside outer-training ranges;
- maximum normalized extrapolation distance;
- predictions outside the broad retention plausibility range.

These are same-source empirical prediction intervals, not lifetime confidence bounds or external calibration evidence.

## Outputs

```text
<output>/
├── config_snapshot.json
├── run_manifest.json
├── tables/
│   ├── validated_cycle_summary.csv
│   ├── quality_flags.csv
│   ├── signal_features.csv                       # when raw signals are supplied
│   ├── trajectory_diagnostics.csv
│   ├── trajectory_points.csv
│   ├── forecast_feature_table.csv
│   ├── validation_predictions.csv
│   ├── validation_by_battery.csv
│   ├── model_comparison.csv
│   ├── forecast_error_diagnostics.csv
│   ├── error_by_battery.csv
│   ├── error_by_lifecycle_segment.csv
│   ├── error_by_knee_phase.csv
│   ├── error_by_domain_status.csv
│   ├── error_by_degradation_rate.csv
│   ├── error_by_trajectory_regime.csv
│   ├── error_by_interval_width.csv
│   ├── battery_error_profiles.csv
│   ├── ridge_success_failure_profiles.csv
│   └── high_error_predictions.csv
├── figures/
│   ├── capacity_trajectories.png
│   ├── forecast_predictions.png
│   ├── model_mae_comparison.png
│   └── ridge_vs_best_baseline_error_delta.png
└── reports/
    ├── validation_summary.json
    ├── error_diagnostics_summary.json
    ├── raw_signal_admission.json                # when raw signals are supplied
    ├── signal_feature_comparison.json           # when admitted
    ├── scientific_closeout.json
    └── scientific_closeout.md
```

Capacity-only comparison artifacts are additionally retained when an admitted signal-enriched run is performed. The manifest records source and sidecar SHA-256 values, configuration, admission decision, model comparison, readiness, limitations, artifact paths, and artifact checksums.

## Component-Level Closeout

The report separates:

- runtime execution;
- input-contract validation;
- battery-disjoint leakage control;
- trajectory and knee diagnostics;
- uncertainty estimation;
- Ridge predictive hypothesis;
- raw-signal provenance admission;
- raw-signal predictive value;
- external generalization;
- engineering-decision readiness.

A primary Ridge result may be `Unsupported` while runtime, contract, and leakage controls are `Supported`. Conversely, passing software tests does not make a predictive or scientific claim valid.

## Current Tracked-Data Limitation

The tracked Kaggle NASA-derived cycle-summary table supports trajectory, baseline, grouped forecast, uncertainty, OOD, and error-structure analysis. It does not include the authoritative full voltage/current/temperature trajectories required to evaluate CC/CV, IC, thermal, energy, or transition-resistance features.

Therefore raw-signal predictive value remains `Inconclusive` until a checksum-bound source file, explicit battery/cycle mapping, declared units, sufficient coverage, and protocol-comparable validation are available. No mechanism, RUL, process optimization, engineering decision, or production-control claim is supported from the tracked summary alone.
