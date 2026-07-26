# Battery SNL LFP Bounded Cycle-Regime Review

Status: `v2.6.9_feature_stage_complete_local_cycle_review_pending`

## Objective

v2.6.9 tests the narrowest defensible question left by v2.6.8:

> Do the first eight cycle-summary rows in three predeclared SNL LFP
> representatives contain threshold-free regime contrasts consistent with the
> source-declared three-cycle capacity check followed by bulk cycling?

This stage does not create confirmed capacity-check labels. It does not inspect
time-series rows, infer step commands, merge cohorts, or execute a model.

## Source sequence

The official Battery Archive SNL study description states that each cycling
round contains:

1. a capacity check;
2. a number of cycles at the designated bulk condition;
3. another capacity check.

The capacity check consists of three 0–100% SOC charge/discharge cycles at
0.5C. The source also warns that filename SOC and rate metadata describe the
bulk-cycling condition, not necessarily the capacity-check condition.

The source establishes the experimental sequence. It does not establish that
the first three rows in the converted cycle-data CSV are capacity-check rows.
Accordingly, v2.6.9 records source-sequence candidates only.

## Upstream identity

The implementation preserves:

- archive path: `data/raw/battery_archive/SNL LFP.zip`;
- archive SHA-256:
  `006a335cbcdabc858a85ab0cdbc59a7001150751cf22abe8a7132c85ef63223d`;
- v2.6.8 tracked compact checksum:
  `28c68acecdce55787189ddd981c097d1748504dab43b3777b896638652fb70f2`;
- common cycle-data header checksum:
  `02c4b1f087f1133349cfb60f52443c75099c1d5742a266b4b2889701a344d88c`.

The archive checksum is verified before any entry payload is opened.

## Representative scope

Exactly three cycle-data entries are permitted:

- `SNL_18650_LFP_25C_0-100_0.5-1C_a_cycle_data.csv`;
- `SNL_18650_LFP_25C_20-80_0.5-0.5C_a_cycle_data.csv`;
- `SNL_18650_LFP_25C_40-60_0.5-0.5C_a_cycle_data.csv`.

Temperature and replicate are held at 25 °C and `a`, while all three documented
SOC protocol families are represented.

No time-series entry may be opened in this stage. v2.6.8 found no step index or
command-state column, so a step-level read is not yet justified.

## Read boundary

For each exact representative, the implementation may read:

1. one cycle-data header;
2. exactly the first eight cycle-summary rows;
3. no physical line longer than 65,536 bytes.

The eight row positions are recorded as:

- positions 1–3: `capacity_check_candidate`;
- positions 4–8: `bulk_cycle_candidate`.

The assignment is based on the official round sequence. It is not a confirmed
row classification.

## Selected measurements

Only these fields are retained:

| Header | Recorded field | Unit handling |
| --- | --- | --- |
| `Cycle_Index` | `cycle_index` | no unit |
| `Min_Current (A)` | `min_current_a` | exact source string, A |
| `Max_Current (A)` | `max_current_a` | exact source string, A |
| `Min_Voltage (V)` | `min_voltage_v` | exact source string, V |
| `Max_Voltage (V)` | `max_voltage_v` | exact source string, V |
| `Charge_Capacity (Ah)` | `charge_capacity_ah` | exact source string, Ah |
| `Discharge_Capacity (Ah)` | `discharge_capacity_ah` | exact source string, Ah |

Values are validated as finite decimals and preserved as the exact CSV strings.
No rounding, unit conversion, imputation, smoothing, or row exclusion is
performed. Start/end timestamps, test time, and energy columns are not retained.

## Contrast method

For each selected current, voltage, and capacity field, v2.6.9 records:

- the exact range over positions 1–3;
- the exact range over positions 4–8;
- whether the two ranges are non-overlapping;
- the direction of non-overlap, when present.

No numerical threshold is fitted or inferred. A non-overlapping range is a
bounded diagnostic contrast, not proof of a commanded protocol or capacity-check
identity.

The overall candidate evidence may be reported as
`candidate_supported_not_established` only when:

- all three representative entries satisfy the read contract;
- cycle indices are strictly increasing;
- each representative has at least one non-overlapping current or voltage range.

This status is deliberately weaker than `established`.

## Stop conditions

The review stops or records a mismatch when:

- archive SHA-256 differs;
- an exact representative entry is missing, duplicated, encrypted, or unsafe;
- the cycle-data header checksum differs from v2.6.8;
- fewer than eight rows are available;
- row width differs from the 12-column header;
- a selected column is absent;
- a selected value is empty, non-decimal, or non-finite;
- cycle indices are non-integer or non-increasing.

The implementation does not fall back to another file, encoding, delimiter,
row count, or field.

## Prohibited operations

v2.6.9 does not:

- open time-series files;
- open nonrepresentative entries;
- read a complete CSV file;
- extract the archive;
- retain unselected raw fields;
- infer or fit classification thresholds;
- promote candidate rows to confirmed capacity checks;
- infer cycle commands or step identities;
- bind instrument channels;
- establish calibration or uncertainty;
- merge cohorts;
- train or evaluate a model;
- recompute v2.6.1 metrics;
- access the network or credentials.

## CLI

```bash
python -m src.platform_core.battery_snl_lfp_bounded_cycle_regime_review --json preview
python -m src.platform_core.battery_snl_lfp_bounded_cycle_regime_review --json run
python -m src.platform_core.battery_snl_lfp_bounded_cycle_regime_review --json validate \
  outputs/v2_6_battery_snl_lfp_bounded_cycle_regime/bounded_cycle_regime_result.json
```

`preview` validates the contract and reports archive presence without hashing or
opening the archive.

## Outputs

Local full result:

```text
outputs/v2_6_battery_snl_lfp_bounded_cycle_regime/
└─ bounded_cycle_regime_result.json
```

Tracked compact result:

```text
data/processed/battery_v2_6_9_snl_lfp_bounded_cycle_regime_summary.json
```

The initial tracked result is `pending_local_artifact`. The real local result
must be reviewed before merge.

## Software validation

Synthetic ZIP tests verify:

- exact three-entry access;
- eight-row and physical-line limits;
- checksum rejection before ZIP access;
- missing, malformed, short, width-mismatched, and non-monotonic inputs;
- exact selected-field retention;
- exclusion of unapproved and time-series entries;
- threshold-free range contrasts;
- deterministic full and compact outputs;
- rejection of scientific claim promotion.

Synthetic success proves software behavior only.

## Scientific closeout before local execution

Current result: **Inconclusive**.

- Evidence level: contract defined without local cycle-summary observations.
- Strongest evidence: official round sequence plus checksum-bound v2.6.8 schema.
- Primary limitation: no real first-eight-row values have been reviewed.
- Suitable for: bounded local cycle-regime review.
- Unsuitable for: confirmed capacity-check labels, step classification,
  cycle-command binding, instrument-channel binding, cohort comparison,
  predictive validation, mechanism claims, or engineering decisions.
