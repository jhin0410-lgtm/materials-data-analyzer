# Battery SNL LFP Bounded CSV Schema Read

Status: `v2.6.8_feature_stage_complete_local_schema_read_pending`

## Objective

v2.6.8 defines and implements the smallest payload-read step justified by the
v2.6.7 source-to-entry review. It asks one narrow question:

> Do six predeclared representative SNL LFP files expose structurally consistent
> headers and minimally sufficient candidate columns for a later, separately
> authorized cycle/step discrimination audit?

This stage is not a loader, cohort import, trajectory analysis, or model run.

## Upstream identity

The implementation preserves:

- local archive path: `data/raw/battery_archive/SNL LFP.zip`;
- archive SHA-256:
  `006a335cbcdabc858a85ab0cdbc59a7001150751cf22abe8a7132c85ef63223d`;
- v2.6.6 compact-result checksum:
  `f4c02c38652848ddba6a69ffe47010e0cb7ada3ad411fd028afdd5ff552b89e5`;
- v2.6.7 compact-result checksum:
  `38fb66269706938513bb000d14427b33147ee13f04d917696e47dff7f2699248`.

The archive checksum is verified before any representative entry payload is
opened. A mismatch stops the audit before CSV access.

## Representative scope

Exactly one cycle-data/time-series pair is selected from each documented SOC
protocol family at 25 °C, replicate `a`:

| Protocol family | Cycle-data entry | Time-series entry |
| --- | --- | --- |
| 0–100% SOC | `SNL_18650_LFP_25C_0-100_0.5-1C_a_cycle_data.csv` | `SNL_18650_LFP_25C_0-100_0.5-1C_a_timeseries.csv` |
| 20–80% SOC | `SNL_18650_LFP_25C_20-80_0.5-0.5C_a_cycle_data.csv` | `SNL_18650_LFP_25C_20-80_0.5-0.5C_a_timeseries.csv` |
| 40–60% SOC | `SNL_18650_LFP_25C_40-60_0.5-0.5C_a_cycle_data.csv` | `SNL_18650_LFP_25C_40-60_0.5-0.5C_a_timeseries.csv` |

The selection is a schema probe. It is not claimed to represent every replicate,
temperature, rate, file, row, cycle, or measurement channel.

## Read contract

For each of the six exact entries, the implementation may read:

1. one CSV header;
2. at most five subsequent data rows;
3. no physical line longer than 65,536 bytes.

The implementation records:

- header text and deterministic header checksum;
- normalized header names;
- units only when explicitly encoded in the header;
- conservative candidate semantic roles;
- sampled non-empty and numeric counts;
- sampled row widths and header-width consistency.

Raw sample values are not retained in either local or tracked results.

## Candidate-role requirements

The structural contract requires candidate roles, not scientifically verified
channel bindings.

Cycle-data files must expose:

- a cycle-index candidate; and
- at least one charge-capacity, discharge-capacity, or general-capacity candidate.

Time-series files must expose:

- a test-time candidate;
- a voltage candidate; and
- a current candidate.

A matching header name does not prove commanded versus measured status, physical
channel identity, calibration, accuracy, or semantic consistency throughout the
file.

## Stop conditions

The audit stops or records a contract mismatch when:

- archive SHA-256 differs from the v2.6.6 identity;
- a representative entry is absent, duplicated, encrypted, or unsafe;
- UTF-8 or strict CSV parsing fails;
- a physical line exceeds the byte limit;
- sampled row widths differ from the header width;
- required candidate roles are absent.

The implementation never falls back to another file, encoding, delimiter, row
limit, or inferred unit.

## Prohibited operations

v2.6.8 does not:

- open any nonrepresentative entry;
- read a complete CSV file;
- extract the ZIP archive;
- retain raw sampled values;
- infer physical cell identities;
- infer exact charge/discharge commands;
- bind instrument channels to columns;
- distinguish capacity-check and bulk-cycling rows conclusively;
- convert or impute units;
- merge cohorts;
- train or evaluate a model;
- recompute v2.6.1 metrics;
- access the network or credentials.

## CLI

```bash
python -m src.platform_core.battery_snl_lfp_bounded_schema_read --json preview
python -m src.platform_core.battery_snl_lfp_bounded_schema_read --json run
python -m src.platform_core.battery_snl_lfp_bounded_schema_read --json validate \
  outputs/v2_6_battery_snl_lfp_bounded_schema_read/bounded_schema_read_result.json
```

`preview` validates the contract and reports archive presence without hashing or
opening the ZIP.

## Outputs

Local full result:

```text
outputs/v2_6_battery_snl_lfp_bounded_schema_read/
└─ bounded_schema_read_result.json
```

Tracked compact result:

```text
data/processed/battery_v2_6_8_snl_lfp_bounded_schema_read_summary.json
```

The initial tracked result is `pending_local_artifact` because GitHub cannot
access the ignored local ZIP. The real local result must be reviewed before this
feature is merged.

## Software validation

Synthetic ZIP fixtures verify:

- exact representative-entry access;
- five-row and 65,536-byte limits;
- checksum rejection before payload access;
- missing, duplicate, malformed, overlong, and width-mismatched inputs;
- required candidate-role detection;
- raw-value non-retention;
- deterministic full and compact results;
- output isolation;
- scientific-boundary rejection.

Synthetic success validates software behavior only. It does not validate the
real archive schema or any scientific interpretation.

## Scientific closeout before local execution

Current result: **Inconclusive**.

- Evidence level: contract defined without local payload observation.
- Strongest evidence: exact archive identity, representative entries, and read
  limits are predeclared.
- Primary limitation: no real header or sampled row has yet been observed by the
  tracked implementation.
- Suitable for: bounded local schema-audit execution.
- Unsuitable for: capacity-check classification, cycle-command binding,
  instrument-channel binding, cohort comparison, predictive validation, model
  selection, or engineering decisions.
