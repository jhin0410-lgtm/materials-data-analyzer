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

## Official source

Landing page:

```text
https://www.nasa.gov/content/prognostics-center-of-excellence-data-set-repository
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

The NASA data-catalog license field is not specified. The PCoE repository asks
users to acknowledge the dataset and donors and states that use is at the
user's own risk. The importer records this statement as source terms; it does
not reinterpret it as a software license.

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

The script does not embed an expected archive checksum. It records the checksum
of the bytes actually retrieved so later import can verify that the supplied
ZIP is the same file represented by the receipt.

Use `-Force` only when intentionally replacing an existing local archive and
receipt.

## 2. Convert MAT files to canonical artifacts

```powershell
mda-nasa-battery-import `
  --input data/raw/battery/nasa_pcoe/5_Battery_Data_Set.zip `
  --retrieval-receipt data/raw/battery/nasa_pcoe/retrieval_receipt.json `
  --output data/processed/nasa_pcoe_battery_import
```

The importer accepts:

- one `.mat` battery file;
- a directory containing `.mat` files;
- a ZIP archive, including bounded nested ZIP archives.

It rejects unsafe archive paths, excessive nesting or member counts, oversized
members, ambiguous battery identities, duplicate battery files, malformed
vectors, non-finite measurements, non-positive voltage, and non-monotonic
source time.

## 3. Run the signal-enriched analysis

The most internally consistent analysis uses the cycle summary and raw signal
created from the same authoritative MAT files:

```powershell
mda-battery-intelligence `
  --cycle-summary data/processed/nasa_pcoe_battery_import/nasa_pcoe_cycle_summary.csv `
  --raw-signal data/processed/nasa_pcoe_battery_import/nasa_pcoe_raw_signal.csv `
  --raw-signal-provenance data/processed/nasa_pcoe_battery_import/nasa_pcoe_raw_signal_provenance.json `
  --output outputs/nasa_pcoe_signal_enriched_battery_intelligence `
  --n-splits 5 `
  --knee-bootstrap-samples 200
```

The existing Kaggle-derived cycle summary may be paired with the imported raw
signal only when the admission report confirms exact battery and discharge-cycle
identity coverage. Filename similarity or row order is never used as a join.

## Import outputs

```text
nasa_pcoe_battery_import/
├── nasa_pcoe_cycle_summary.csv
├── nasa_pcoe_raw_signal.csv
├── nasa_pcoe_raw_signal_provenance.json
├── nasa_pcoe_source_inventory.csv
├── nasa_pcoe_protocol_summary.csv
├── nasa_pcoe_import_warnings.csv
└── nasa_pcoe_import_manifest.json
```

### Cycle identity

`cycle_index` is the one-based sequential ordinal of `discharge` operations in
source order within each battery MAT file.

Charge and impedance operations are counted in inventory but are not assigned
to a discharge cycle by inference. This avoids silently creating a
charge-discharge pairing that the source structure does not explicitly state.

### Battery identity

A MAT file is imported only when:

- it contains exactly one non-private top-level variable with a `cycle`
  structure; and
- that variable agrees case-insensitively with the original MAT filename stem.

The source variable text becomes `battery_id`. Duplicate normalized identities
fail the entire import.

### Raw-signal mapping

For each discharge operation:

| NASA field | Canonical field |
|---|---|
| `Voltage_measured` | `voltage_v` |
| `Current_measured` | `current_a` |
| `Temperature_measured` | `temperature_c` when complete |
| `Time` | `elapsed_time_s` |
| derived current integral | `capacity_ah` |
| operation timestamp plus elapsed time | `global_time_s` when complete |

`capacity_ah` is the cumulative trapezoidal integral of the absolute measured
current over source elapsed time. It is explicitly recorded as derived and is
not represented as the source scalar discharge capacity.

The source scalar `Capacity` becomes `discharge_capacity_ah` in the cycle
summary. Retention is normalized to the first observed discharge capacity in
each battery, avoiding use of future cycles for the normalization reference.

### No silent preprocessing

The importer performs no:

- interpolation;
- smoothing;
- outlier removal;
- cycle deletion after a malformed discharge operation;
- inferred unit conversion;
- inferred charge-discharge pairing.

Optional temperature and global-time columns are emitted only when complete for
the imported table. They are omitted with an explicit warning rather than
partially imputed.

## Protocol summary and external validation

`nasa_pcoe_protocol_summary.csv` records per-battery descriptive support for
later comparability review:

- discharge-cycle and raw-point counts;
- ambient-temperature range;
- voltage range;
- median and maximum absolute discharge current;
- median sample interval and discharge duration;
- initial, final, minimum, and maximum discharge capacity.

This table prepares protocol comparison. It does not prove that another cohort
has compatible chemistry, cell format, formation history, cycling limits,
temperature control, instrumentation, calibration, or failure definition.
External generalization remains `Inconclusive` until a separate cohort passes
those checks and is evaluated battery-disjoint from development data.

## Validation status

Synthetic MAT files are used only to test parser behavior, nested-archive
handling, checksum verification, fail-closed identity rules, canonical schema,
raw-signal admission, installed packaging, and end-to-end software execution.

Passing those tests is software validation. Scientific validation begins only
after the official archive is acquired, its receipt and per-file checksums are
recorded, import warnings are reviewed, and the real signal-enriched result is
compared against the capacity-only workflow on held-out batteries.
