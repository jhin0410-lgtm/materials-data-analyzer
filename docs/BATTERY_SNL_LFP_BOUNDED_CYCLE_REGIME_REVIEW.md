# Battery SNL LFP Bounded Cycle-Regime Review

Status: `v2.6.9_feature_stage_complete_local_cycle_reviewed`

## Objective

v2.6.9 tests the narrowest defensible question left by v2.6.8:

> Do the first eight cycle-summary rows in three predeclared SNL LFP
> representatives contain threshold-free regime contrasts consistent with the
> source-declared three-cycle capacity check followed by bulk cycling?

This stage does not create confirmed capacity-check labels. It does not inspect
time-series rows, infer step commands, merge cohorts, or execute a model.

## Source sequence and candidate labels

The official Battery Archive SNL study description states that each cycling
round contains a capacity check, bulk cycling at the assigned condition, and
another capacity check. A capacity check consists of three 0–100% SOC cycles at
0.5C. Filename SOC and rate metadata describe the bulk-cycling condition and do
not necessarily describe capacity-check rows.

The source establishes an experimental sequence, but it does not prove that the
first three rows in the converted CSV are capacity-check rows. Therefore:

- positions 1–3 are recorded as `capacity_check_candidate`;
- positions 4–8 are recorded as `bulk_cycle_candidate`;
- neither label is promoted to a confirmed row identity.

## Upstream identity

The reviewed result preserves:

- archive path: `data/raw/battery_archive/SNL LFP.zip`;
- archive SHA-256:
  `006a335cbcdabc858a85ab0cdbc59a7001150751cf22abe8a7132c85ef63223d`;
- v2.6.8 tracked compact checksum:
  `28c68acecdce55787189ddd981c097d1748504dab43b3777b896638652fb70f2`;
- common cycle-data header checksum:
  `02c4b1f087f1133349cfb60f52443c75099c1d5742a266b4b2889701a344d88c`;
- v2.6.9 tracked compact checksum:
  `dc6c7c4046d81ddf879c2f1538eab75708dd387f7d9d940adc0c6dfc2c3e01dc`.

The archive checksum is verified before any entry payload is opened.

## Representative and read scope

Exactly three 25 °C, replicate-`a` cycle-data entries are opened:

- `SNL_18650_LFP_25C_0-100_0.5-1C_a_cycle_data.csv`;
- `SNL_18650_LFP_25C_20-80_0.5-0.5C_a_cycle_data.csv`;
- `SNL_18650_LFP_25C_40-60_0.5-0.5C_a_cycle_data.csv`.

For each entry the implementation reads one known 12-column header and exactly
the first eight cycle-summary rows. No time-series entry, nonrepresentative
entry, complete CSV file, or extracted archive is read.

## Selected measurements

Only the following fields are retained as exact finite decimal strings:

| Header | Recorded field | Unit handling |
| --- | --- | --- |
| `Cycle_Index` | `cycle_index` | no unit |
| `Min_Current (A)` | `min_current_a` | exact source string, A |
| `Max_Current (A)` | `max_current_a` | exact source string, A |
| `Min_Voltage (V)` | `min_voltage_v` | exact source string, V |
| `Max_Voltage (V)` | `max_voltage_v` | exact source string, V |
| `Charge_Capacity (Ah)` | `charge_capacity_ah` | exact source string, Ah |
| `Discharge_Capacity (Ah)` | `discharge_capacity_ah` | exact source string, Ah |

No rounding, conversion, imputation, smoothing, or row exclusion is performed.
Start/end timestamps, test time, energy columns, and all time-series values are
excluded from the tracked artifact.

## Reviewed result

The bounded local execution recorded:

- archive identity: `verified`;
- representative entries opened: `3 / 3`;
- cycle-summary rows read: `24`;
- contract mismatches: `0`;
- row-width matches: `24 / 24`;
- strictly increasing cycle indices: `3 / 3`;
- within-file candidate contrasts observed: `3 / 3`;
- fitted or inferred thresholds: none;
- candidate-label promotion: none;
- scientific closeout: `diagnostic`.

### 0–100% SOC representative

The candidate groups have a non-overlapping minimum-current range:

- positions 1–3: `-0.55 A`;
- positions 4–8: `-1.1 A`.

This is consistent with a lower-magnitude 0.5C candidate group followed by the
filename-labelled 1C-discharge bulk condition. It is not a command-log binding.
Voltage and capacity ranges overlap across the two candidate groups.

### 20–80% SOC representative

The candidate groups have a non-overlapping minimum-voltage range:

- positions 1–3: `1.998–1.999 V`;
- positions 4–8: `2.700–3.159 V`.

Current ranges overlap. The voltage contrast is consistent with a full-depth
candidate group followed by a restricted-voltage bulk condition, but it does not
prove the row labels or commanded cutoff settings.

### 40–60% SOC representative

The candidate groups show non-overlap in minimum current, minimum voltage, charge
capacity, and discharge capacity. The strongest capacity contrast is:

- positions 1–3 discharge capacity: `1.070–1.073 Ah`;
- positions 4–8 discharge capacity: `0.220–0.660 Ah`.

This is consistent with a full-capacity candidate group followed by a restricted
capacity-window bulk condition. It is not a confirmed capacity-check label.

## Transition-row limitation

In every representative, row position 4 differs materially from positions 5–8
in at least one capacity or voltage field. Examples include approximately double
capacity in the 0–100% representative and substantially larger capacity in the
20–80% and 40–60% representatives.

Position 4 remains a `bulk_cycle_candidate` because the contract predeclared
positions 4–8 from the documented sequence. The observed internal heterogeneity
means position 4 may be a first-bulk-cycle, transition, initialization, or
conversion-boundary record. v2.6.9 does not determine which explanation is
correct and does not treat positions 4–8 as a homogeneous bulk regime.

## Decision

The recorded decision is:

- capacity-check versus bulk-cycle discrimination:
  `candidate_supported_not_established`;
- source-sequence candidate assignment: `recorded_not_promoted`;
- within-file cycle-regime contrast: `observed_all_representatives`;
- step-level discrimination: `not_available_no_step_identifier`;
- cycle command to rows: `not_established`;
- instrument channel to columns: `not_established`;
- physical cell to entry: `not_established`;
- official distribution snapshot: `not_established`;
- cross-cohort comparability: `not_admitted`;
- predictive validation: `blocked`;
- overall: `bounded_cycle_regime_evidence_recorded_gate_not_passed`.

The condition-specific separating fields are not interchangeable. v2.6.9 does
not support a single universal threshold or classifier across protocol families.

## Software validation

Synthetic ZIP tests cover exact three-entry access, eight-row and physical-line
limits, checksum rejection before ZIP access, missing/malformed/short/width-
mismatched/non-monotonic inputs, exact selected-value retention, time-series
exclusion, threshold-free contrasts, deterministic output, and rejection of
scientific claim promotion.

The tracked-result test validates the reviewed compact artifact directly, locks
its checksum, verifies all 24 selected rows, and checks that all prohibited
execution and inference flags remain false. GitHub Actions does not regenerate
the real result because the ignored local ZIP is intentionally unavailable in CI.

## Scientific closeout

Result: **Diagnostic**.

- Evidence level: official round sequence plus the first eight cycle-summary rows
  in three predeclared representatives.
- Strongest evidence: each representative has at least one threshold-free current
  or voltage contrast between the two source-sequence candidate groups.
- Primary limitation: row identities are not confirmed; position 4 is internally
  transitional; no step identifier, command log, complete-file review,
  instrument mapping, or calibration evidence is available.
- Suitable for: bounded diagnostics, feasibility assessment, and design of the
  next evidence contract.
- Unsuitable for: confirmed capacity-check labels, universal classification,
  step classification, cycle-command binding, instrument-channel binding,
  cohort comparison, model evaluation, mechanism claims, or engineering
  decisions.
