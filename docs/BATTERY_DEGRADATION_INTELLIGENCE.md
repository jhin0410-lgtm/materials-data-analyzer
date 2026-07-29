# Battery Degradation Intelligence v1

## Purpose

Battery Degradation Intelligence v1 is an additive analysis workflow for asking a narrower and more defensible question than generic battery-life prediction:

> Given cycle-level retention history and, when available, standardized voltage/current/temperature signals, what degradation patterns, exact-horizon generalization performance, uncertainty, and extrapolation limits are supported by the available measurements?

The workflow strengthens analysis depth without converting statistical associations into electrochemical mechanism, lifetime, RUL, optimization, or production-control claims.

## Analysis Flow

```text
cycle summary and optional raw signals
-> schema, unit, identity, duplicate, and time-order validation
-> cycle-level physical feature extraction
-> degradation-rate and knee-candidate diagnostics
-> exact-horizon origin-only forecast table
-> battery-disjoint GroupKFold validation
-> persistence comparison
-> nested group conformal uncertainty
-> feature-range extrapolation audit
-> physical-plausibility flags
-> scientific evidence closeout
```

## Installed Command

```powershell
mda-battery-intelligence `
  --cycle-summary data/processed/kaggle_nasa_battery_cycle_summary_analysis_ready.csv `
  --output outputs/battery_degradation_intelligence
```

Use `--raw-signal` only for a table that satisfies the contract below. The tracked analysis-ready table does not itself contain raw voltage/current trajectories, so a run without `--raw-signal` records that signal-derived diagnostics were not evaluated.

For a faster deterministic smoke run:

```powershell
mda-battery-intelligence `
  --cycle-summary data/processed/kaggle_nasa_battery_cycle_summary_analysis_ready.csv `
  --output outputs/battery_degradation_intelligence_smoke `
  --n-splits 3 `
  --knee-bootstrap-samples 0
```

Existing output directories are not overwritten silently. Pass `--overwrite` only when deliberate full replacement is intended.

## Cycle-Summary Contract

Required columns are configurable but default to:

| Column | Meaning | Requirement |
|---|---|---|
| `battery_id` | Stable battery identity | Non-missing; used as the validation group |
| `cycle_index` | Cycle number | Finite numeric; unique and strictly increasing within a battery after audited stable sorting |
| `capacity_retention_percent` | Forecast target | Finite numeric; diagnostic plausibility range defaults to 0–150% |

Optional numeric quantities such as `discharge_capacity_ah`, `reference_capacity_ah`, `internal_resistance_ohm`, and `ambient_temperature_c` are validated and retained. Implausible optional values generate flags rather than silent deletion.

Duplicate battery-cycle rows are rejected because aggregation would require an explicit scientific rule. Exact-horizon targets require an observed row at `origin_cycle + horizon`; missing target cycles are counted and excluded rather than interpolated.

## Optional Raw-Signal Contract

Required columns:

| Column | Unit / meaning |
|---|---|
| `battery_id` | Stable battery identity matching the cycle summary |
| `cycle_index` | Cycle number |
| `step_type` | Allowlisted charge, charge-CC, charge-CV, discharge, rest, or impedance label |
| `elapsed_time_s` | Seconds from the start of the step; strictly increasing within each step |
| `voltage_v` | Cell voltage in volts |
| `current_a` | Current in amperes; sign is not used for integration magnitude because step labels define direction |

Optional columns:

| Column | Unit / meaning |
|---|---|
| `step_id` | Explicit step-segment identity; required when a step type repeats within a cycle or elapsed time resets between segments |
| `temperature_c` | Temperature in degrees Celsius |
| `capacity_ah` | Instrument-reported cumulative capacity in ampere-hours |
| `global_time_s` | Monotonic experiment time used for start-to-peak temperature rise and adjacent-sample current-transition analysis |

The workflow rejects duplicate battery-cycle-step-time rows, non-finite required measurements, nonpositive voltage, negative elapsed time, and unknown step labels. It does not infer units from value magnitudes. When `step_id` is absent, the workflow uses `step_type` as the segment identity and records that each step type must occur as one continuous elapsed-time segment within a battery-cycle.

## Signal-Derived Features

When sufficient raw data are present, the workflow calculates:

- charge and discharge duration;
- charge-CC and charge-CV duration and CV fraction;
- integrated charge/discharge throughput in Ah;
- integrated charge/discharge energy in Wh;
- coulombic and energy efficiency;
- voltage and current extrema;
- temperature minimum, maximum, span, and start-to-peak rise when global time is supplied;
- a current-transition resistance proxy only when globally ordered adjacent samples contain a measurable current step;
- `dQ/dV` peak height and voltage for one continuous, mostly monotonic discharge segment;
- median absolute `dV/dQ`;
- `dQ/dV` peak sensitivity across smoothing windows 5, 9, and 15.

These are measurement-derived diagnostics. The resistance value is a current-transition proxy, not a validated electrochemical impedance or internal-resistance estimate; it is withheld when global time or a measurable transition is unavailable. Incremental-capacity features are withheld for multiple discharge segments or non-monotonic voltage/capacity traces, and otherwise remain smoothing-sensitive. Warnings record every unavailable or sensitive result.

No smoothing, interpolation, outlier removal, or record exclusion is performed silently.

## Degradation-Rate and Knee Diagnostics

For each battery, the workflow produces:

- overall retention slope;
- rolling degradation-rate estimates;
- best two-segment linear candidate;
- pre- and post-candidate slopes;
- fit improvement versus a single line;
- candidate-cycle sensitivity to minimum-segment choices;
- residual-bootstrap 5–95% candidate interval.

A result is called a `candidate` only when the post-split slope is more negative and the piecewise fit improves sum of squared error by at least 10%. Otherwise it is a `weak_candidate` or an insufficient-data result.

A knee candidate is not a ground-truth physical transition and does not identify a degradation mechanism.

## Leakage-Safe Forecast Definition

The workflow performs fixed-horizon warm-start cross-battery forecasting:

- the target is retention at exactly `origin_cycle + horizon`;
- only the origin row and earlier retention history are used;
- current retention, lagged retention, trailing mean, trailing standard deviation, trailing slope, origin cycle, and available current-cycle numeric features may be used;
- battery identity is never used as a numeric predictor;
- entire battery identities are held out with `GroupKFold`;
- persistence, defined as the current retention value, is the mandatory baseline;
- scaling and Ridge fitting occur inside each training fold.

This is not zero-shot forecasting because the held-out battery contributes its own history before each prediction origin. It is not full-life or RUL prediction.

## Uncertainty and Extrapolation

For each outer validation fold, prediction-interval width is estimated from absolute residuals generated by an inner battery-grouped out-of-fold procedure using only the outer training batteries. The finite-sample conformal quantile is then applied symmetrically to held-out predictions.

The workflow reports:

- requested and observed interval coverage;
- number of interval-evaluable predictions;
- features outside outer-training minimum and maximum values;
- maximum extrapolation distance normalized by training IQR or standard deviation;
- predictions outside the configured broad retention plausibility range.

The intervals are empirical validation intervals, not calibrated lifetime confidence bounds. Coverage on the same source family does not replace an independent external cohort.

## Outputs

```text
<output>/
├── config_snapshot.json
├── run_manifest.json
├── tables/
│   ├── validated_cycle_summary.csv
│   ├── quality_flags.csv
│   ├── signal_features.csv                 # only when raw signals are supplied
│   ├── trajectory_diagnostics.csv
│   ├── trajectory_points.csv
│   ├── forecast_feature_table.csv
│   ├── validation_predictions.csv
│   └── validation_by_battery.csv
├── figures/
│   ├── capacity_trajectories.png
│   └── forecast_predictions.png
└── reports/
    ├── validation_summary.json
    ├── scientific_closeout.json
    └── scientific_closeout.md
```

The manifest records source SHA-256 values, configuration, readiness, forecast-table exclusions, validation summary, evidence level, limitations, artifact paths, and artifact checksums.

## Scientific Closeout Rules

The workflow distinguishes software execution from scientific evidence:

- leakage makes the result `Unsupported`;
- fewer than five evaluated batteries makes generalization `Inconclusive`;
- failure to improve persistence consistently makes the model result `Unsupported`;
- point-prediction improvement without adequate uncertainty coverage remains `Diagnostic`;
- even with leakage-safe improvement and approximate coverage, the result remains `Diagnostic` until a protocol-comparable external cohort is evaluated.

The workflow does not issue `Supported` for predictive generalization by itself.

## Current Limitation of the Tracked Battery Table

The tracked cycle-summary table supports trajectory, knee-candidate, exact-horizon validation, uncertainty, and OOD analysis. It does not contain the full raw voltage/current/temperature trajectories required to test whether IC, CC/CV, energy, thermal, or transition-resistance features improve cross-battery performance.

Therefore:

- the software capability can be validated with controlled test signals;
- a cycle-summary run can produce a real diagnostic result;
- raw-signal scientific value remains unverified until authoritative signal files with stable battery/cycle identities and documented units are supplied;
- no mechanism, RUL, process-optimization, or engineering-decision claim should be made from the current tracked table alone.
