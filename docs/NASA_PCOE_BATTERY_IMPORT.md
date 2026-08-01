# NASA PCoE Battery MATLAB Import

## Purpose

This workflow closes the gap between the NASA Prognostics Center of Excellence
battery-aging MATLAB files and the canonical raw-signal contract consumed by
Battery Degradation Intelligence.

It is intentionally split into two trust boundaries:

1. a transparent PowerShell acquisition script records URL, timestamp, file
   size, and archive SHA-256;
2. an offline Python importer verifies the receipt, recursively reads local ZIP
   and MAT files, and emits auditable CSV and JSON artifacts.

The analysis package itself performs no network access.

## Official source and target definition

Landing page:

```text
https://www.nasa.gov/intelligent-systems-division/discovery-and-systems-health/pcoe/pcoe-data-set-repository/
```

Current archive endpoint referenced by that repository:

```text
https://phm-datasets.s3.amazonaws.com/NASA/5.+Battery+Data+Set.zip
```

Dataset citation recorded by the importer:

```text
B. Saha and K. Goebel (2007), Battery Data Set,
NASA Prognostics Data Repository, NASA Ames Research Center.
```

The NASA Open Data description states that the experiments use an end-of-life
criterion of 30% fade in rated capacity, from 2 Ah to 1.4 Ah. The canonical
`capacity_retention_percent` target is therefore derived as:

```text
100 × source discharge Capacity / 2.0 Ah
```

The source scalar `Capacity` remains unchanged in `discharge_capacity_ah`.
`reference_capacity_ah` is 2.0 for this dataset and
`reference_capacity_method` is `source_rated_capacity_2_ah`.

The first observed discharge is deliberately not used as the 100% reference.
Some experiments begin with a partial or protocol-limited discharge; using that
value as the denominator can inflate later targets by orders of magnitude.

A common 2 Ah denominator corrects target semantics but does not prove
cross-protocol comparability. Discharge Capacity still depends on current,
ambient temperature, and voltage cutoff.

The NASA data-catalog license field is not specified. The PCoE repository asks
users to acknowledge the dataset and donors and states that use is at the
user's own risk. The importer records this statement as source terms; it does
not reinterpret it as a software license.

## One-command local workflow

After the official ZIP and receipt exist under
`data/raw/battery/nasa_pcoe`, run from the repository root:

```powershell
.\scripts\run_nasa_pcoe_battery_pipeline.ps1
```

The script performs, in order:

1. receipt-verified offline import with invalid-Capacity quarantine;
2. source-rated 2 Ah target derivation;
3. signal-enriched, battery-disjoint forecasting;
4. target/reference comparability audit;
5. battery influence and observed-condition triage.

It overwrites only the declared generated import and analysis directories. The
source ZIP and retrieval receipt are never modified.

## 1. Acquire the archive and receipt

From the repository root on Windows PowerShell:

```powershell
.\scripts\download_nasa_pcoe_battery_dataset.ps1
```

Generated local files:

```text
data/raw/battery/nasa_pcoe/
├── 5_Battery_Data_Set.zip
└── retrieval_receipt.json
```

The script records the checksum of the bytes actually retrieved so later import
can verify that the supplied ZIP is the file represented by the receipt. The
JSON receipt is written as UTF-8 without a byte-order mark.

Use `-Force` only when intentionally replacing an existing local archive and
receipt.

## 2. Convert MAT files to canonical artifacts

The explicit importer command remains available:

```powershell
mda-nasa-battery-import `
  --input data/raw/battery/nasa_pcoe/5_Battery_Data_Set.zip `
  --retrieval-receipt data/raw/battery/nasa_pcoe/retrieval_receipt.json `
  --output data/processed/nasa_pcoe_battery_import `
  --overwrite
```

The importer accepts:

- one `.mat` battery file;
- a directory containing `.mat` files;
- a ZIP archive, including bounded nested ZIP archives.

It rejects unsafe archive paths, excessive nesting or member counts, oversized
members, ambiguous battery identities, same-ID files with different checksums,
malformed vectors, non-finite measurements, non-positive voltage, and
non-monotonic source time.

A discharge operation whose source `Capacity` is missing, nonnumeric,
non-scalar, complex, non-finite, zero, or negative is not repaired. It is
excluded from canonical prediction tables and recorded in
`nasa_pcoe_excluded_operations.csv` with its original source identity and
ordinal. Later discharge ordinals are not renumbered.

The official outer archive contains overlapping sub-bundles. A repeated
`battery_id` is deduplicated only when the complete MAT SHA-256 is identical to
the previously imported copy. The duplicate remains visible in the source
inventory. A same-ID file with different bytes remains a fatal ambiguity.

## 3. Run the signal-enriched analysis

The explicit analysis command remains available:

```powershell
mda-battery-intelligence `
  --cycle-summary data/processed/nasa_pcoe_battery_import/nasa_pcoe_cycle_summary.csv `
  --raw-signal data/processed/nasa_pcoe_battery_import/nasa_pcoe_raw_signal.csv `
  --raw-signal-provenance data/processed/nasa_pcoe_battery_import/nasa_pcoe_raw_signal_provenance.json `
  --output outputs/nasa_pcoe_signal_enriched_battery_intelligence `
  --n-splits 5 `
  --knee-bootstrap-samples 200 `
  --overwrite
```

The cycle summary and raw signal should come from the same authoritative MAT
files. Filename similarity or row order is never used as a join.

## Import outputs

```text
nasa_pcoe_battery_import/
├── nasa_pcoe_cycle_summary.csv
├── nasa_pcoe_raw_signal.csv
├── nasa_pcoe_raw_signal_provenance.json
├── nasa_pcoe_source_inventory.csv
├── nasa_pcoe_protocol_summary.csv
├── nasa_pcoe_import_warnings.csv
├── nasa_pcoe_excluded_operations.csv
└── nasa_pcoe_import_manifest.json
```

### Cycle identity

`cycle_index` is the one-based sequential ordinal of `discharge` operations in
source order within each unique battery MAT file.

Charge and impedance operations are counted in inventory but are not assigned
to a discharge cycle by inference. This avoids silently creating a
charge-discharge pairing that the source structure does not explicitly state.

### Battery identity

A MAT file is imported only when:

- it contains exactly one non-private top-level variable with a `cycle`
  structure; and
- that variable agrees case-insensitively with the original MAT filename stem.

The source variable text becomes `battery_id`. Repeated normalized identities
are accepted only when their complete MAT SHA-256 values are identical.

### Raw-signal mapping

For each discharge operation:

| NASA field | Canonical field |
|---|---|
| `Voltage_measured` | `voltage_v` |
| `Current_measured` | `current_a` |
| `Temperature_measured` | `temperature_c` when complete |
| `Time` | `elapsed_time_s` |
| derived current integral | `capacity_ah` |
| relative source operation time plus elapsed time | `global_time_s` when complete |

`capacity_ah` is the cumulative trapezoidal integral of the absolute measured
current over source elapsed time. It is explicitly recorded as derived and is
not represented as the source scalar discharge capacity.

The MATLAB date vector is preserved as
`operation_started_at_source_time`. The source documentation does not declare a
timezone, so the importer does not label it UTC. `global_time_s` uses only
within-battery timestamp differences and is omitted unless all imported source
timestamps are valid.

### Forecast target semantics

The forecast table now exposes `origin_target_percent` as the explicit target
value available at the forecast origin. The legacy `current_target` column is
retained only as a backward-compatible artifact alias and is not an electrical
current field. It is excluded from fitted feature columns to avoid duplicate
predictors.

Physical current conditions are represented by raw-signal features such as
`current_abs_max_a`. Comparability reports no longer emit the misleading
`median_observed_current_target` field.

### No silent preprocessing

The importer performs no:

- interpolation;
- smoothing;
- outlier removal;
- Capacity replacement or clipping;
- inferred unit conversion;
- inferred charge-discharge pairing;
- timezone inference.

Optional temperature and global-time columns are emitted only when complete.
They are omitted with an explicit warning rather than partially imputed.

## Protocol summary and external validation

`nasa_pcoe_protocol_summary.csv` records per-battery descriptive support for
later comparability review:

- discharge-cycle and raw-point counts;
- ambient-temperature range;
- voltage range;
- median and maximum absolute discharge current;
- median sample interval and discharge duration;
- initial, final, minimum, and maximum source discharge Capacity;
- minimum, median, and maximum retention against the 2 Ah rating;
- the first observed discharge fraction of rated capacity.

This table prepares protocol comparison. It does not prove compatible chemistry,
cell format, formation history, cycling limits, temperature control,
instrumentation, calibration, or failure definition.

## Validation status

Synthetic MAT files test parser behavior, nested-archive handling, checksum
verification, checksum-safe duplicate handling, invalid-Capacity quarantine,
rated-capacity target derivation, target/current semantic separation,
PowerShell syntax, installed packaging, and end-to-end software execution.

Passing those tests is software validation. Scientific validation still requires
reviewing real import warnings, protocol conditions, held-out-battery errors,
and an external comparable cohort. A lower error after this correction would be
diagnostic evidence, not proof of deployment readiness.
