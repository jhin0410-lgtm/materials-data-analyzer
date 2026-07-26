# Battery SNL LFP Bounded CSV Schema Read

Status: `v2.6.8_feature_stage_complete_bounded_schema_observed`

## Objective

v2.6.8 implements the smallest payload-read step justified by the v2.6.7
source-to-entry review. It asks one narrow question:

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

Validated local full-result checksum:

```text
b6f4f3bff664e6a6bc3ddfeead891f4fdff2671f539cb40ae0a0d38b252d4494
```

Tracked compact-result checksum:

```text
28c68acecdce55787189ddd981c097d1748504dab43b3777b896638652fb70f2
```

The full result and compact result use separate deterministic checksums because
`compact()` retains the bounded evidence fields and then canonicalizes the
result again.

## Observed bounded result

The checksum-verified local run recorded:

- archive identity: `verified`;
- representative entries opened: `6 / 6`;
- headers read: `6`;
- sampled data rows read: `30`;
- schema-contract matches: `6`;
- schema-contract mismatches: `0`;
- sampled row-width matches: `6 / 6`;
- duplicate headers: none;
- raw sample values retained: `false`;
- complete CSV files read: `false`.

All three cycle-data representatives expose the same 12-column header and header
checksum:

```text
02c4b1f087f1133349cfb60f52443c75099c1d5742a266b4b2889701a344d88c
```

Observed cycle-data columns are:

- `Cycle_Index`;
- `Start_Time` and `End_Time`;
- `Test_Time (s)`;
- minimum and maximum current in `A`;
- minimum and maximum voltage in `V`;
- charge and discharge capacity in `Ah`;
- charge and discharge energy in `Wh`.

All three time-series representatives expose the same 11-column header and
header checksum:

```text
730d272a0c60f8bce285e4659f437253af1da663b6ec69d2153fe39c531ac2b5
```

Observed time-series columns are:

- `Date_Time`, `Test_Time (s)`, and `Cycle_Index`;
- current in `A` and voltage in `V`;
- charge and discharge capacity in `Ah`;
- charge and discharge energy in `Wh`;
- environment and cell temperature in header-labelled `C`.

The observed `C` label is retained exactly as source header text. It is not
silently converted to `°C` and is not calibration evidence.

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

The tracked-result test validates the reviewed local compact artifact directly,
locks its deterministic checksum, and confirms that all six observations remain
bounded and structurally valid. GitHub Actions does not regenerate the real
artifact because the ignored local ZIP is intentionally unavailable in CI.

## Scientific closeout

Current result: **Diagnostic**.

- Result: `bounded_representative_schema_observed`.
- Evidence level: six predeclared headers and at most five rows per file.
- Strongest evidence: the checksum-verified archive yielded six contract-matching
  representative observations with consistent cycle-data and time-series header
  structures and no sampled row-width mismatch.
- Primary limitation: the bounded samples cannot establish full-file or
  all-entry consistency, capacity-check classification, exact cycle commands,
  instrument-channel mapping, calibration, or cohort equivalence.
- Suitable for: observed CSV schema inventory, candidate column-role planning,
  and design of the next bounded read contract.
- Unsuitable for: capacity-check classification, cycle-command binding,
  instrument-channel binding, unit conversion, cohort comparison, model
  evaluation, mechanism claims, or engineering decisions.

The gate therefore remains:

- overall: `bounded_schema_observed_gate_not_passed`;
- cross-cohort comparability: `not_admitted`;
- predictive validation: `blocked`.
