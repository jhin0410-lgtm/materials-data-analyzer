# Battery External Cohort Admission Gate

Status: `v2.6.4_battery_external_cohort_admission_feature_stage_complete`

## Purpose

v2.6.4 prevents a candidate Battery dataset from being merged, harmonized, or
used for predictive validation merely because files are locally available. It
adds a deterministic, read-only admission gate that must be passed before any
cross-cohort model evaluation.

The gate separates three decisions:

1. raw inventory review;
2. cross-cohort scientific comparability;
3. predictive-validation eligibility.

Passing an inventory check does not imply that the cohort is scientifically
comparable or eligible for modeling.

## Candidate

The first candidate is the existing local Battery Archive-style bundle described
by `docs/BATTERY_ARCHIVE_DATA_AUDIT.md`:

- 9 zip archives;
- 196 cycle-level CSV files;
- 196 time-series CSV files;
- no dedicated metadata sidecar identified;
- no independently verifiable official snapshot identifier recorded.

The audit does not read or extract the raw archives. It evaluates the tracked
candidate manifest and source references only.

## Fixed Admission Requirements

The same eight fields from v2.6.3 are required, but v2.6.4 adds the granularity
needed for an external validation cohort:

| Field | Required evidence granularity |
| --- | --- |
| Chemistry | Battery-level source record |
| Nominal capacity | Battery-level source record |
| Ambient temperature | Cycle-level commanded or controlled condition |
| Charge protocol | Cycle-level commanded protocol |
| Discharge protocol | Cycle-level commanded protocol |
| Cutoff voltage | Cycle-level commanded policy |
| Measurement calibration | Instrument- or channel-level calibration/uncertainty |
| Source snapshot | Independently verifiable official distribution snapshot |

A field passes only when it is source-backed, does not require inference, is not
filename-derived, and has the required granularity. For temperature, protocol,
and cutoff fields, observed signals do not substitute for commanded conditions.

## Candidate Result

The current Battery Archive candidate does not satisfy any of the eight
requirements.

- Chemistry and C-rate information are encoded in filenames and remain parsing
  labels, not source-backed scientific metadata.
- Nominal capacity is absent.
- Environment temperature may be observed in time-series files, but no
  cycle-specific controlled-condition record is established.
- Measured current is not a commanded charge or discharge protocol.
- Minimum and maximum observed voltage do not establish cutoff policy.
- Calibration, accuracy, and measurement uncertainty are absent.
- The local archive bundle does not establish official snapshot identities for
  the constituent datasets.
- A source-defined external-validation target is unresolved.

The recorded decision is:

```text
inventory_review: admitted_with_restrictions
cross_cohort_comparability: not_admitted
predictive_validation: blocked
overall_status: not_admitted_for_cross_cohort_validation
```

The scientific closeout is `inconclusive`.

## Allowed Work

The candidate may be used for:

- archive and file inventory review;
- source-document recovery planning;
- loader software-contract tests using synthetic fixtures;
- preservation of filename-derived values as explicitly labeled parsed metadata.

Filename-derived labels must retain provenance and may not be promoted to
verified chemistry, temperature, SOC-window, C-rate, or protocol evidence.

## Prohibited Work

v2.6.4 does not authorize:

- raw-data analysis through this gate;
- archive extraction;
- filename metadata parsing during the audit;
- inferred metadata completion;
- heterogeneous cohort merging;
- target harmonization;
- Ridge or persistence evaluation on the candidate;
- new model training or tuning;
- metric recomputation;
- mechanism, causal, SOH/RUL, lifetime, or engineering claims.

The historical v1.1 Battery Archive case-study specification remains a design
reference only. Its filename parser recommendations are not scientific evidence
and do not override this admission decision.

## Preservation Boundary

The gate verifies and preserves:

- v2.6.3 comparability checksum:
  `c8a91f9b561f68a474401f6f2cb051d115875f8df78f1ba92c4a20dec57d17a8`;
- v2.6.3 decision: `comparability_not_established`;
- persistence pooled MAE: `3.425575369058076`;
- Ridge pooled MAE: `4.15369918179312`;
- `PLATFORM_VERSION`: `2.4.0`.

No model or existing metric is changed.

## Run

Preview without writes:

```powershell
python -m src.platform_core.battery_external_cohort_admission --json preview
```

Run the gate:

```powershell
python -m src.platform_core.battery_external_cohort_admission --json run
```

Validate a generated result:

```powershell
python -m src.platform_core.battery_external_cohort_admission --json validate outputs/v2_6_battery_external_cohort_admission/admission_summary.json
```

Generated local details:

- `outputs/v2_6_battery_external_cohort_admission/admission_matrix.csv`;
- `outputs/v2_6_battery_external_cohort_admission/admission_summary.json`.

Tracked compact evidence:

- `data/processed/battery_v2_6_4_external_cohort_admission_summary.json`.

## What Would Change the Decision

A future candidate can be reconsidered only after the following are obtained and
bound to stable source identifiers before model evaluation:

- battery-level chemistry and nominal capacity;
- cycle-specific commanded charge/discharge protocols;
- cycle-specific cutoff-voltage policy;
- calibration and measurement-uncertainty records;
- independently verifiable official snapshot identities;
- a source-defined or prospectively verified target contract.
