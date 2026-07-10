# Battery Archive Raw Data Audit

Audit date: 2026-07-09

Scope: raw file inventory audit only. No raw data files, zip files, Kaggle case study files, simulation code, or existing analyzer behavior were modified.

Raw folder reviewed:

```text
data/raw/battery_archive/
```

## Summary

The current `data/raw/battery_archive/` folder contains Battery Archive-style raw zip archives, not an already extracted raw folder tree.

Top-level inventory:

```text
data/raw/battery_archive/
├─ CALCE.zip
├─ HNEI.zip
├─ Michigan Expansion.zip
├─ Michigan Formation.zip
├─ Oxford.zip
├─ README.md
├─ SNL LFP.zip
├─ SNL NCA.zip
├─ SNL NMC.zip
└─ UL-Purdue.zip
```

No zip was extracted during this audit. The internal zip central directories and representative CSV headers were inspected read-only.

## Raw Folder Structure

Top-level files:

| File | Type | Approx. size |
| --- | --- | ---: |
| `CALCE.zip` | zip archive | 60.8 MB |
| `HNEI.zip` | zip archive | 117.9 MB |
| `Michigan Expansion.zip` | zip archive | 86.7 MB |
| `Michigan Formation.zip` | zip archive | 257.7 MB |
| `Oxford.zip` | zip archive | 32.1 MB |
| `SNL LFP.zip` | zip archive | 251.6 MB |
| `SNL NCA.zip` | zip archive | 86.8 MB |
| `SNL NMC.zip` | zip archive | 173.1 MB |
| `UL-Purdue.zip` | zip archive | 84.3 MB |
| `README.md` | local raw-data note | small |

Top-level count:

- Total files in `data/raw/battery_archive/`: 10
- Zip files: 9
- Markdown files: 1
- Total zip archive size: about 1.15 GB

## File Extensions

Top-level extensions:

| Extension | Count |
| --- | ---: |
| `.zip` | 9 |
| `.md` | 1 |

Internal zip entry extensions:

| Extension | Count |
| --- | ---: |
| `.csv` | 392 |

No internal Excel, MAT, JSON, parquet, or metadata sidecar files were found from zip directory inspection.

## Internal Zip Inventory

Each zip contains paired cycle-level CSV files and time-series CSV files.

| Zip | Entries | Cycle CSV | Time-series CSV | Other CSV |
| --- | ---: | ---: | ---: | ---: |
| `CALCE.zip` | 14 | 7 | 7 | 0 |
| `HNEI.zip` | 30 | 15 | 15 | 0 |
| `Michigan Expansion.zip` | 36 | 18 | 18 | 0 |
| `Michigan Formation.zip` | 80 | 40 | 40 | 0 |
| `Oxford.zip` | 16 | 8 | 8 | 0 |
| `SNL LFP.zip` | 60 | 30 | 30 | 0 |
| `SNL NCA.zip` | 48 | 24 | 24 | 0 |
| `SNL NMC.zip` | 64 | 32 | 32 | 0 |
| `UL-Purdue.zip` | 44 | 22 | 22 | 0 |
| **Total** | **392** | **196** | **196** | **0** |

Observed naming patterns:

```text
{source}/{cell_or_test_id}_{form_factor}_{chemistry}_{temperature}_{soc_window}_{rates}_{replicate}_cycle_data.csv
{source}/{cell_or_test_id}_{form_factor}_{chemistry}_{temperature}_{soc_window}_{rates}_{replicate}_timeseries.csv
{source}/{cell_or_test_id}_{form_factor}_{chemistry}_{temperature}_{soc_window}_{rates}_{replicate}_timeseries_data.csv
```

Examples:

```text
CALCE/CALCE_CX2-16_prism_LCO_25C_0-100_0.5-0.5C_a_cycle_data.csv
CALCE/CALCE_CX2-16_prism_LCO_25C_0-100_0.5-0.5C_a_timeseries.csv
Michigan Expansion/MICH_01R_pouch_NMC_25C_0-100_0.2-0.2C_cycle_data.csv
Michigan Expansion/MICH_01R_pouch_NMC_25C_0-100_0.2-0.2C_timeseries_data.csv
UL-Purdue/UL-PUR_CF10DPA_pouch_NCA_25C_0-100_1-1C_n_cycle_data.csv
UL-Purdue/UL-PUR_CF10DPA_pouch_NCA_25C_0-100_1-1C_n_timeseries_data.csv
```

## Representative Files

Representative cycle files:

| Archive | Representative cycle file |
| --- | --- |
| `CALCE.zip` | `CALCE/CALCE_CX2-16_prism_LCO_25C_0-100_0.5-0.5C_a_cycle_data.csv` |
| `HNEI.zip` | `HNEI/HNEI_18650_NMC_LCO_25C_0-100_0.5-1.5C_a_cycle_data.csv` |
| `Michigan Expansion.zip` | `Michigan Expansion/MICH_01R_pouch_NMC_25C_0-100_0.2-0.2C_cycle_data.csv` |
| `Michigan Formation.zip` | `Michigan Formation/MICH_BLForm1_pouch_NMC_45C_0-100_1-1C_a_cycle_data.csv` |
| `Oxford.zip` | `Oxford/OX_1-1_pouch_LCO_40C_0-100_2-1.84C_a_cycle_data.csv` |
| `SNL LFP.zip` | `SNL LFP/SNL_18650_LFP_15C_0-100_0.5-1C_a_cycle_data.csv` |
| `SNL NCA.zip` | `SNL NCA/SNL_18650_NCA_15C_0-100_0.5-1C_a_cycle_data.csv` |
| `SNL NMC.zip` | `SNL NMC/SNL_18650_NMC_15C_0-100_0.5-1C_a_cycle_data.csv` |
| `UL-Purdue.zip` | `UL-Purdue/UL-PUR_CF10DPA_pouch_NCA_25C_0-100_1-1C_n_cycle_data.csv` |

Representative time-series files:

| Archive | Representative time-series file |
| --- | --- |
| `CALCE.zip` | `CALCE/CALCE_CX2-16_prism_LCO_25C_0-100_0.5-0.5C_a_timeseries.csv` |
| `Michigan Expansion.zip` | `Michigan Expansion/MICH_01R_pouch_NMC_25C_0-100_0.2-0.2C_timeseries_data.csv` |
| `UL-Purdue.zip` | `UL-Purdue/UL-PUR_CF10DPA_pouch_NCA_25C_0-100_1-1C_n_timeseries_data.csv` |

Large time-series entries exist. The largest observed internal entry was:

```text
UL-Purdue/UL-PUR_CF10DPA_pouch_NCA_25C_0-100_1-1C_n_timeseries_data.csv
```

with an internal uncompressed length of about 302 MB.

## CSV Structure

### Cycle-Level CSV Headers

Most cycle files share this header:

```text
Cycle_Index,Start_Time,End_Time,Test_Time (s),Min_Current (A),Max_Current (A),Min_Voltage (V),Max_Voltage (V),Charge_Capacity (Ah),Discharge_Capacity (Ah),Charge_Energy (Wh),Discharge_Energy (Wh)
```

Some Michigan and UL-Purdue cycle files omit `Start_Time` and `End_Time`:

```text
Cycle_Index,Test_Time (s),Min_Current (A),Max_Current (A),Min_Voltage (V),Max_Voltage (V),Charge_Capacity (Ah),Discharge_Capacity (Ah),Charge_Energy (Wh),Discharge_Energy (Wh)
```

### Time-Series CSV Headers

Observed time-series files share this header:

```text
Date_Time,Test_Time (s),Cycle_Index,Current (A),Voltage (V),Charge_Capacity (Ah),Discharge_Capacity (Ah),Charge_Energy (Wh),Discharge_Energy (Wh),Environment_Temperature (C),Cell_Temperature (C)
```

## Possible Metadata Files

No dedicated metadata CSV, JSON, Excel, or MAT file was found inside the archives.

Metadata appears to be encoded in file and folder names:

- Source/dataset: `CALCE`, `HNEI`, `Michigan Expansion`, `Michigan Formation`, `Oxford`, `SNL LFP`, `SNL NCA`, `SNL NMC`, `UL-Purdue`
- Cell/test identifier: e.g. `CALCE_CX2-16`, `MICH_01R`, `SNL_18650_LFP_15C...`
- Form factor: e.g. `18650`, `pouch`, `prism`
- Chemistry: e.g. `LCO`, `NMC`, `NMC_LCO`, `LFP`, `NCA`
- Temperature/protocol: e.g. `25C`, `45C`, `-5C`
- SOC window: e.g. `0-100`, `20-80`, `40-60`
- C-rate protocol: e.g. `0.5-0.5C`, `0.5-1.5C`, `1-1C`, `2-1.84C`
- Replicate suffix: e.g. `a`, `b`, `c`, `n`

Implementation implication:

- A loader should include a filename parser, but parsing should be defensive and should preserve the original archive and entry path for traceability.

## Possible Cycle Data Files

The best first-pass data source is `*_cycle_data.csv`.

Reasons:

- It is already cycle-level.
- It is small compared with time-series CSV files.
- It has direct capacity and energy columns.
- It can support existing analyzer modes with minimal transformation.

Likely standardized cycle summary fields:

```text
archive_name
source_dataset
battery_id
source_filename
cycle_index
test_time_s
start_time
end_time
min_current_a
max_current_a
min_voltage_v
max_voltage_v
charge_capacity_ah
discharge_capacity_ah
charge_energy_wh
discharge_energy_wh
ambient_temperature_c
cell_chemistry
form_factor
soc_window
charge_rate_c
discharge_rate_c
replicate_id
capacity_retention_percent
failed
```

The `Start_Time` and `End_Time` columns must be optional because they are absent in some sources.

## Possible Target Columns

Direct target candidates:

- `Discharge_Capacity (Ah)`
- `Discharge_Energy (Wh)`
- `Charge_Capacity (Ah)`
- `Charge_Energy (Wh)`
- `Max_Voltage (V)`
- `Min_Voltage (V)`

Derived target candidates:

- `capacity_retention_percent`
- `discharge_energy_retention_percent`
- `capacity_fade_percent`
- `failed`, if derived from a threshold such as `capacity_retention_percent < 80`
- `cycle_life_to_80_percent`, if aggregated at battery/cell level

Recommended first target for analyzer compatibility:

```text
capacity_retention_percent
```

Recommended direct target for a minimal loader:

```text
discharge_capacity_ah
```

Important interpretation note:

- Any `failed` label would be derived from an analysis rule, not a source-provided label, unless a source-specific metadata file is later found.

## Possible Feature Columns

Cycle-level features from `*_cycle_data.csv`:

- `cycle_index`
- `test_time_s`
- `min_current_a`
- `max_current_a`
- `min_voltage_v`
- `max_voltage_v`
- `charge_capacity_ah`
- `charge_energy_wh`
- `discharge_energy_wh`
- `ambient_temperature_c`, parsed from filename or time-series environment temperature
- `cell_chemistry`, parsed from filename
- `form_factor`, parsed from filename
- `soc_window`, parsed from filename
- `charge_rate_c`, parsed from filename
- `discharge_rate_c`, parsed from filename
- `source_dataset`, parsed from archive/folder name

Time-series-derived features from `*_timeseries*.csv`:

- `cycle_duration_s`
- `voltage_mean_v`
- `voltage_min_v`
- `voltage_max_v`
- `current_mean_a`
- `current_min_a`
- `current_max_a`
- `cell_temperature_mean_c`
- `cell_temperature_min_c`
- `cell_temperature_max_c`
- `cell_temperature_rise_c`
- `environment_temperature_mean_c`
- `raw_sample_count`

Recommended first phase:

- Use only `*_cycle_data.csv`.
- Add filename-derived metadata.
- Defer time-series-derived features until a streaming/limit-safe extractor is designed.

## Processed Output Candidates

Candidate processed outputs:

```text
data/processed/battery_archive_cycle_summary.csv
data/processed/battery_archive_cell_metadata.csv
data/processed/battery_archive_quality_summary.csv
data/processed/battery_archive_analysis_ready.csv
data/processed/battery_archive_timeseries_features.csv
```

Recommended first output:

```text
data/processed/battery_archive_cycle_summary.csv
```

Minimum schema candidate:

```text
archive_name
source_dataset
battery_id
source_filename
cycle_index
ambient_temperature_c
charge_capacity_ah
discharge_capacity_ah
capacity_retention_percent
charge_energy_wh
discharge_energy_wh
min_current_a
max_current_a
min_voltage_v
max_voltage_v
failed
```

Recommended analysis-ready variant:

```text
data/processed/battery_archive_cycle_summary_analysis_ready.csv
```

This should exclude only rows with explicit quality problems from analysis-ready output, while preserving a full audit output.

## Case Study Suitability

Battery Archive appears suitable as a future real-data case study.

Strengths:

- Multiple sources and protocols.
- Already includes cycle-level CSV files.
- File names encode useful protocol metadata.
- Contains enough diversity for EDA, reliability analysis, group-aware validation, and virtual experiment screening.
- Directly supports existing analyzer modes after transformation:
  - `eda`
  - `reliability`
  - `simulation`
  - potentially `process` style grouping by protocol variables

Recommended case study framing:

```text
Battery Archive cycle-level degradation screening case study
```

Recommended first model target:

```text
capacity_retention_percent
```

Recommended validation:

- Use group-aware validation by `battery_id` or `source_dataset`.
- Avoid random train/test split as the only reported validation because cycles from the same cell are repeated measurements.

## Implementation Risks Before Loader Work

P0 risks:

- Raw zip archives are large and must not be committed.
- Time-series files can be very large; reading all time-series CSVs into memory would be unsafe.
- No explicit metadata file was found; filename parsing will be required and may be brittle.
- Schema variation exists: some cycle files include `Start_Time` and `End_Time`, while others do not.
- Derived labels such as `failed` must be documented as analysis labels, not source labels.

P1 risks:

- Battery/cell ID extraction needs careful design to avoid merging distinct cells.
- Capacity retention reference capacity should be robust, e.g. first valid capacity, first-N median, or source-specific rule.
- Cross-source units appear consistent in headers, but unit validation should still be included.
- Cycle-level and time-series files are paired by filename pattern; pairing logic should be tested before feature extraction.
- Some protocols use different SOC windows and C-rates; models should not mix them without metadata features or group-aware validation.

P2 risks:

- Licensing/provenance should be documented before public case-study publication.
- A loader should support `--limit` or per-archive selection for development.
- A quality summary should report invalid capacity, missing cycle index, duplicate cycle rows, and unusual retention values.

## Recommended Implementation Order

No implementation was performed in this audit. If implementation proceeds later:

1. Add a zip inventory helper or script that lists archives, entries, and headers without extraction.
2. Implement a cycle CSV loader that streams `*_cycle_data.csv` from selected zip files.
3. Parse filename metadata defensively and preserve `archive_name` and `source_filename`.
4. Build a full cycle summary CSV.
5. Add data validation and quality flags.
6. Build an analysis-ready CSV from normal rows only.
7. Run existing analyzer modes on the analysis-ready CSV.
8. Defer time-series feature extraction until the cycle summary path is stable.

## Git / Raw Data Policy Check

Current `.gitignore` includes:

```text
data/raw/**
outputs/
```

Git ignore verification:

```text
.gitignore:16:data/raw/** data/raw/battery_archive/CALCE.zip
.gitignore:16:data/raw/** data/raw/battery_archive/HNEI.zip
.gitignore:16:data/raw/** data/raw/battery_archive/README.md
```

Ignored status:

```text
!! data/raw/battery_archive/
```

This confirms the raw Battery Archive zips are ignored and should not be added to Git.

## Command Results

### `python -m pytest`

Result:

```text
99 passed in 14.57s
```

### `git status --short`

Status before creating this audit document:

```text

```

Actual status after creating this audit document:

```text
?? docs/BATTERY_ARCHIVE_DATA_AUDIT.md
```
