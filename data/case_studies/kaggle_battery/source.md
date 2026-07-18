# Kaggle Battery Dataset Source

## Source

- Immediate upstream dataset slug: `patrickfleith/nasa-battery-dataset`
- Dataset URL: `https://www.kaggle.com/datasets/patrickfleith/nasa-battery-dataset`
- Local archive size: 239,496,734 bytes
- Local archive SHA256: `787ba917fc381c0bd354f515966b1831191ceb5b26985ee8b0000bb6bf96efee`
- Local `metadata.csv` SHA256: `182fcf36be0899db30ec0f7b04ed32e11fdf1cbd308241b22ea2a2722f5bc4f8`
- License or terms: not recorded in the local package metadata; unresolved
- Retrieval timestamp: not recorded in the local package metadata
- Redistribution allowed in this repository: unresolved; raw data remains local-only

The immediate Kaggle package is verified by local checksums. The exact
authoritative NASA PCoE snapshot/version from which that package was derived
cannot be verified from the local files and is not asserted. See the
[v2.3.5 source-metadata audit](../../../docs/BATTERY_SOURCE_METADATA_RECOVERY.md).

## Raw Data Policy

Kaggle raw data should not be committed to this repository by default. Keep raw
downloads under `data/raw/kaggle/...` locally and commit only small processed
CSV summaries when redistribution is clearly allowed.

Do not commit Kaggle API keys, tokens, or credentials.

## Ingestion

```bash
python scripts/ingest_data.py --source kaggle --dataset patrickfleith/nasa-battery-dataset --limit 50
```

## Processing Notes

For the `patrickfleith/nasa-battery-dataset` cleaned dataset, the first
analyzer-ready table is built from:

```text
data/raw/kaggle/patrickfleith_nasa-battery-dataset/cleaned_dataset/metadata.csv
```

The processed CSV is a discharge-only cycle-level summary extracted from
`metadata.csv`. It does not merge the thousands of per-cycle raw CSV files under
`cleaned_dataset/data/`.

```bash
python scripts/build_kaggle_battery_summary.py --metadata data/raw/kaggle/patrickfleith_nasa-battery-dataset/cleaned_dataset/metadata.csv --output data/processed/kaggle_nasa_battery_cycle_summary.csv
```

This command writes three processed files:

- `data/processed/kaggle_nasa_battery_cycle_summary.csv`: full quality-audited
  cycle summary. It preserves every discharge metadata row, including
  `high_retention_warning` and `invalid_capacity` rows.
- `data/processed/kaggle_nasa_battery_cycle_summary_analysis_ready.csv`:
  analyzer-ready cycle summary containing only rows with
  `retention_quality_flag == normal`.
- `data/processed/kaggle_nasa_battery_quality_summary.csv`: battery-level
  quality summary with warning counts and battery-level quality flags.

`capacity_retention_percent` is not an original metadata column. It is derived
from `discharge_capacity_ah` and a per-battery reference capacity:

```text
capacity_retention_percent = discharge_capacity_ah / reference_capacity_ah * 100
```

Supported reference capacity methods:

- `first_valid`: use the first positive valid discharge capacity per battery.
- `first_n_median`: use the median of the first N positive valid discharge
  capacities per battery. This is the default with `--reference-window 5`.
- `max_observed`: use the maximum observed positive discharge capacity per
  battery. This can be useful for screening, but it requires interpretation
  caution because the maximum may occur after early metadata artifacts or
  unusual test conditions.

`retention_quality_flag` keeps suspicious derived values without deleting or
capping rows. `high_retention_warning` means the derived retention exceeded
120%, which can happen when the early reference capacity is unusually low or
when metadata-only cycle ordering/capacity values need review.

The full CSV can therefore have a very large maximum
`capacity_retention_percent`. This is intentional for quality review. Those
rows are not deleted from the full file and the retention values are not capped.
They are excluded only from the analysis-ready CSV used by analyzer modes.

`failed` is not an original dataset label. It is a derived screening label:

```text
failed = 1 when capacity_retention_percent < 80
failed = 0 otherwise
```

`internal_resistance_ohm` is intentionally left empty in this metadata-only
version. v2.3.5 found 1,956 impedance rows across the 34 cells, with complete
numeric `Re`/`Rct` pairs in 1,947 rows. They were not temporally aligned to
discharge cycles, so joining them into cycle-level resistance remains future
work.

Raw discharge CSV files can be summarized into scalar physical features after
the analysis-ready summary is created. This step reads only the
`source_filename` rows referenced by the analysis-ready summary. It does not
combine all raw time-series CSV files into one processed table.

```bash
python scripts/build_kaggle_battery_discharge_features.py --summary data/processed/kaggle_nasa_battery_cycle_summary_analysis_ready.csv --raw-root data/raw/kaggle/patrickfleith_nasa-battery-dataset/cleaned_dataset/data --output data/processed/kaggle_nasa_battery_discharge_features.csv --merged-output data/processed/kaggle_nasa_battery_analysis_ready_with_features.csv --limit 100
```

Use `--full` or `--limit none` only when you explicitly want to process every
analysis-ready discharge row.

## Analyzer Commands

After creating a battery cycle summary CSV:

```bash
python src/process_data.py --mode eda --input data/processed/kaggle_nasa_battery_analysis_ready_with_features.csv --run-name kaggle_battery_eda
```

```bash
python src/process_data.py --mode reliability --input data/processed/kaggle_nasa_battery_analysis_ready_with_features.csv --run-name kaggle_battery_reliability
```
