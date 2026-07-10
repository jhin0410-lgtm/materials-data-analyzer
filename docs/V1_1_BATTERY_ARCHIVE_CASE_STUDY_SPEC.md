# v1.1 Battery Archive Case Study Spec

Spec date: 2026-07-10

Scope: design document only. No code, raw zip files, extracted raw files, processed CSVs, Kaggle case study files, simulation logic, or existing analyzer behavior were modified for this spec.

Reference audit:

```text
docs/BATTERY_ARCHIVE_DATA_AUDIT.md
```

## Goal

Build a second real-data case study that connects Battery Archive zip-based raw data to the existing `materials_data_analyzer` workflow.

The first implementation scope should read cycle-level battery aging data from Battery Archive zip files, create analyzer-ready CSV tables, and make the result usable with existing reliability, simulation, and virtual experiment screening workflows.

Target workflow:

```text
Battery Archive raw zip
-> cycle_data file inventory
-> filename metadata parsing
-> cycle_data schema mapping
-> cycle-level summary CSV
-> analysis-ready CSV
-> reliability analysis
-> optional simulation / virtual experiment screening
-> Markdown case study report
```

The first v1.1 implementation should stay limited to `*_cycle_data.csv` files. Time-series feature extraction should remain a later phase.

## Non-goals

Do not implement these in v1.1:

- Raw zip Git commit
- Raw zip extracted copy Git commit
- Time-series feature extraction
- Electrochemical impedance modeling
- Battery-specific deep learning
- Degradation forecasting
- NLR data integration
- Materials Project integration
- New simulation model types
- AutoML, Bayesian optimization, or active learning
- Production battery model claims

The Battery Archive case study should remain a tabular engineering data case study, not a battery-specific forecasting platform.

## Raw Data Assumptions

Based on `docs/BATTERY_ARCHIVE_DATA_AUDIT.md`, the current raw staging area has this shape:

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

Assumptions for v1.1:

- There are 9 zip files.
- Internal zip entries are CSV files.
- There are 196 `*_cycle_data.csv` files.
- There are 196 `*_timeseries*.csv` files.
- No separate metadata CSV, JSON, Excel, or MAT files were found.
- Metadata must be derived from archive names, internal folder names, and file names.
- Raw zip files are under `data/raw/**` and must remain ignored by Git.
- Cycle-level CSV files are the first safe ingestion target because they are already summarized by cycle and are much smaller than time-series files.

## Ingestion Strategy

Use Python's standard `zipfile` module to inspect and read CSV files directly from zip archives without extracting them to disk.

Recommended first-phase behavior:

1. Discover zip files under `data/raw/battery_archive/`.
2. Open each zip with `zipfile.ZipFile`.
3. List internal entries.
4. Select entries matching `*_cycle_data.csv`.
5. Read selected CSV entries through a file-like object.
6. Normalize columns through a schema mapping layer.
7. Add archive/file metadata.
8. Concatenate normalized cycle rows into one full cycle summary table.

Files to process in v1.1:

```text
*_cycle_data.csv
```

Files to defer:

```text
*_timeseries.csv
*_timeseries_data.csv
```

Reason for deferring time-series files:

- Some internal time-series CSV entries are very large.
- Reading all time-series rows into memory would be risky.
- The platform already has a strong cycle-level path from the Kaggle case study.
- A later time-series extractor should be streaming, limit-aware, and separately tested.

Recommended loader behavior:

- Never require raw zip extraction.
- Never write raw extracted CSVs to `data/raw/`.
- Preserve `zip_file` and `internal_csv_path` in all processed outputs.
- Support optional include/exclude filters by zip name for development.
- Support a `limit_files` option for tests and smoke runs.
- Fail with clear messages when no zip files or no cycle CSV files are found.

## Filename Metadata Parser Design

Battery Archive archives do not include a separate metadata file, so v1.1 needs a defensive filename metadata parser.

Recommended metadata columns:

```text
source_file
zip_file
internal_csv_path
cell_id
source
chemistry
form_factor
temperature_C
soc_window
charge_c_rate
discharge_c_rate
protocol_label
```

Additional useful traceability columns:

```text
filename_parse_status
filename_parse_message
replicate_id
```

Observed filename pattern:

```text
{source}/{cell_or_test_id}_{form_factor}_{chemistry}_{temperature}_{soc_window}_{rates}_{replicate}_cycle_data.csv
```

Examples:

```text
CALCE/CALCE_CX2-16_prism_LCO_25C_0-100_0.5-0.5C_a_cycle_data.csv
Michigan Expansion/MICH_01R_pouch_NMC_25C_0-100_0.2-0.2C_cycle_data.csv
SNL LFP/SNL_18650_LFP_15C_0-100_0.5-1C_a_cycle_data.csv
UL-Purdue/UL-PUR_CF10DPA_pouch_NCA_25C_0-100_1-1C_n_cycle_data.csv
```

Heuristic parsing proposal:

- `zip_file`: top-level zip filename, e.g. `SNL LFP.zip`.
- `source`: first internal path segment, e.g. `SNL LFP`.
- `source_file`: basename of the internal CSV file.
- `internal_csv_path`: full path inside zip.
- `form_factor`: token matching known values such as `18650`, `pouch`, `prism`.
- `chemistry`: token or token group matching known values such as `LCO`, `NMC`, `NMC_LCO`, `LFP`, `NCA`.
- `temperature_C`: token matching values like `25C`, `45C`, `-5C`; parse to numeric Celsius.
- `soc_window`: token matching a pattern such as `0-100`, `20-80`, `40-60`.
- `charge_c_rate` and `discharge_c_rate`: parse the rate token, e.g. `0.5-1.5C`, into two numeric C-rate values.
- `replicate_id`: trailing replicate token before `_cycle_data.csv` when present.
- `cell_id`: conservative prefix before the protocol metadata tokens.
- `protocol_label`: stable joined string from chemistry, form factor, temperature, SOC window, and rates.

Failure policy:

- Do not drop rows when filename parsing partially fails.
- Set unparsed fields to `unknown` or null.
- Set `filename_parse_status` to `parsed`, `partial`, or `failed`.
- Preserve `zip_file`, `internal_csv_path`, and `source_file` even when parsing fails.
- Keep parser logic defensive; do not assume every source follows one exact regex.

## Cycle Data Schema Audit

Representative cycle CSV headers from the audit:

```text
Cycle_Index,Start_Time,End_Time,Test_Time (s),Min_Current (A),Max_Current (A),Min_Voltage (V),Max_Voltage (V),Charge_Capacity (Ah),Discharge_Capacity (Ah),Charge_Energy (Wh),Discharge_Energy (Wh)
```

Some files omit `Start_Time` and `End_Time`:

```text
Cycle_Index,Test_Time (s),Min_Current (A),Max_Current (A),Min_Voltage (V),Max_Voltage (V),Charge_Capacity (Ah),Discharge_Capacity (Ah),Charge_Energy (Wh),Discharge_Energy (Wh)
```

Expected normalized schema candidates:

| Raw candidate | Normalized column |
| --- | --- |
| `Cycle_Index` | `cycle_index` |
| `Start_Time` | `start_time` |
| `End_Time` | `end_time` |
| `Test_Time (s)` | `test_time_s` |
| `Min_Current (A)` | `min_current_a` |
| `Max_Current (A)` | `max_current_a` |
| `Min_Voltage (V)` | `min_voltage_v` |
| `Max_Voltage (V)` | `max_voltage_v` |
| `Charge_Capacity (Ah)` | `charge_capacity_ah` |
| `Discharge_Capacity (Ah)` | `discharge_capacity_ah` |
| `Charge_Energy (Wh)` | `charge_energy_wh` |
| `Discharge_Energy (Wh)` | `discharge_energy_wh` |

Candidate concepts requested for the case study:

- `cycle_index`
- `discharge_capacity`
- `charge_capacity`
- `coulombic_efficiency`
- `energy`
- `retention`
- `soh`
- `temperature`
- `internal_resistance`

Schema mapping notes:

- `discharge_capacity` should map from `Discharge_Capacity (Ah)`.
- `charge_capacity` should map from `Charge_Capacity (Ah)`.
- `energy` can be represented by `charge_energy_wh` and `discharge_energy_wh`.
- `retention` and `soh` are derived fields, not direct observed columns in the audited cycle CSV headers.
- `temperature` should come from filename metadata in the first phase. Time-series temperature should wait for a later extractor.
- `internal_resistance` was not observed in the representative cycle CSV headers and should remain null or omitted in v1.1 unless source-specific evidence appears.
- `coulombic_efficiency` can be derived as `discharge_capacity_ah / charge_capacity_ah`, with guardrails for missing or zero charge capacity.

## Processed Output Design

Recommended v1.1 processed outputs:

```text
data/processed/battery_archive_cycle_file_inventory.csv
data/processed/battery_archive_cycle_summary.csv
data/processed/battery_archive_analysis_ready.csv
data/case_studies/battery_archive/case_study.md
```

Output roles:

| File | Role |
| --- | --- |
| `battery_archive_cycle_file_inventory.csv` | One row per discovered `*_cycle_data.csv` file, including zip name, internal path, file size, source, parse status, and detected columns. |
| `battery_archive_cycle_summary.csv` | Full quality-audited cycle-level summary preserving all readable cycle rows and source traceability. |
| `battery_archive_analysis_ready.csv` | Filtered analysis-ready table for existing analyzer modes; excludes rows with invalid critical fields but does not delete the full audit table. |
| `data/case_studies/battery_archive/case_study.md` | Case study narrative, source assumptions, processing steps, quality checks, analyzer commands, limitations, and interpretation. |

Optional later outputs:

```text
data/processed/battery_archive_quality_summary.csv
data/processed/battery_archive_cell_metadata.csv
data/processed/battery_archive_timeseries_features.csv
```

Commit policy:

- Small processed summaries may be considered for Git only after file size review.
- Raw zip archives and extracted raw CSVs must not be committed.

## Analysis-ready Table Design

Recommended `battery_archive_analysis_ready.csv` columns:

```text
cell_id
cycle_index
source_file
zip_file
internal_csv_path
source
chemistry
form_factor
temperature_C
soc_window
charge_c_rate
discharge_c_rate
protocol_label
test_time_s
charge_capacity
discharge_capacity
charge_energy_wh
discharge_energy_wh
min_current_a
max_current_a
min_voltage_v
max_voltage_v
coulombic_efficiency
capacity_retention
soh
cycle_life_proxy
data_quality_status
data_quality_message
filename_parse_status
```

Recommended derived field definitions:

- `capacity_retention`: discharge capacity divided by the cell-level reference capacity.
- `soh`: initially equivalent to `capacity_retention`; document as an approximate analysis field unless a source-defined SOH exists.
- `cycle_life_proxy`: optional derived indicator such as whether retention remains above 80 percent, or the cycle index relative to first crossing. Keep it clearly labeled as a proxy.
- `data_quality_status`: e.g. `normal`, `invalid_capacity`, `missing_cycle_index`, `duplicate_cycle`, `invalid_reference_capacity`, `impossible_retention`, `too_few_cycles`, `metadata_parse_warning`.

Reference capacity policy:

- Prefer a robust method such as first-N valid discharge capacity median by `cell_id`.
- Preserve `reference_capacity_ah` and `reference_capacity_method` if capacity retention is computed.
- Do not cap retention values; flag unexpected values instead.

## Data Quality Checks

Required checks:

- Missing cycle index.
- Duplicate cycle rows within a cell.
- Non-numeric discharge or charge capacity.
- Negative capacity.
- Zero capacity where retention or efficiency calculations require positive values.
- Impossible retention, such as negative retention or very high retention above a documented threshold.
- Too few cycles for a cell-level analysis.
- Missing filename metadata.
- Filename parse failures or partial parses.
- Inconsistent schema across files.
- Missing critical columns such as `Cycle_Index` or `Discharge_Capacity (Ah)`.
- Duplicate internal file paths.
- Empty or unreadable CSV entries.

Recommended quality summary dimensions:

- Per file.
- Per cell.
- Per source archive.
- Overall.

Recommended quality output fields:

```text
source
zip_file
internal_csv_path
cell_id
row_count
normal_count
invalid_count
warning_count
missing_cycle_index_count
duplicate_cycle_count
invalid_capacity_count
impossible_retention_count
metadata_parse_warning_count
data_quality_flag
```

## Case Study Workflow

Recommended Battery Archive case study workflow:

```text
raw zip
-> cycle_data inventory
-> schema mapping
-> cycle summary
-> quality checks
-> analysis-ready table
-> reliability analysis
-> optional simulation screening
-> case study Markdown report
```

Detailed steps:

1. Confirm raw zip files are present under `data/raw/battery_archive/`.
2. Build a zip inventory without extraction.
3. Discover `*_cycle_data.csv` entries.
4. Parse filename metadata.
5. Normalize cycle CSV schema.
6. Compute derived fields such as capacity retention, approximate SOH, and quality flags.
7. Save full cycle summary.
8. Save analysis-ready table.
9. Run existing `eda` and `reliability` modes.
10. Optionally run `simulation` mode with cautious group-aware validation.
11. Write `data/case_studies/battery_archive/case_study.md`.

Recommended case study framing:

```text
Battery Archive cycle-level degradation screening case study
```

Do not frame the case study as production battery lifetime forecasting.

## Simulation Use Case

Battery Archive can support a tabular screening example using existing simulation mode.

Possible targets:

- `capacity_retention`
- `soh`
- `discharge_capacity`
- `cycle_life_proxy`

Possible features:

- `cycle_index`
- `temperature_C`
- `charge_c_rate`
- `discharge_c_rate`
- `chemistry`
- `form_factor`
- `soc_window`
- `source`
- `protocol_label`

Important implementation note:

- Existing simulation mode expects numeric feature columns. Categorical metadata such as `chemistry`, `form_factor`, `soc_window`, and `source` would need encoding before use as simulation features.
- For the first simulation smoke, use numeric features only:

```text
cycle_index
temperature_C
charge_c_rate
discharge_c_rate
```

Recommended validation:

- Use `--group-column cell_id` when evaluating generalization across cells.
- Avoid reporting random split alone, because cycles from the same cell are repeated measurements and can inflate apparent performance.

Recommended language:

- Data-driven tabular screening.
- Candidate condition screening aid.
- Reliability and degradation trend analysis.

Avoid:

- Battery-specific forecasting claims.
- Production model claims.
- Automatic lifetime prediction claims.
- Physics-based electrochemical simulation claims.

## Testing Plan

Use synthetic zip files created inside temporary test directories. Do not require real Battery Archive raw zip files in tests.

Recommended tests:

- Zip inventory test:
  - Create a temporary zip with known entries.
  - Assert zip name, entry count, and extension counts are detected.
- Cycle data file discovery test:
  - Include `*_cycle_data.csv`, `*_timeseries.csv`, and unrelated files.
  - Assert only cycle data files are selected for v1.1.
- Filename parser test:
  - Test representative names from CALCE, Michigan, SNL, Oxford, and UL-Purdue patterns.
  - Assert missing or unknown tokens produce `partial` or `failed` status without crashing.
- Schema mapping test:
  - Map `Cycle_Index`, `Test_Time (s)`, and capacity/energy columns to normalized names.
  - Handle optional `Start_Time` and `End_Time`.
- Processed summary creation test:
  - Build a small in-memory cycle summary from synthetic CSV contents inside zip.
  - Assert derived retention and quality columns are present.
- Invalid CSV handling test:
  - Empty CSV.
  - Missing required column.
  - Non-numeric capacity.
  - Negative capacity.
- No raw file committed policy test:
  - Verify test fixtures use temporary zip files.
  - Verify no real `data/raw/battery_archive/*.zip` is required by pytest.

Potential test files:

```text
tests/test_battery_archive_raw_inventory.py
tests/test_battery_archive_cycle_loader.py
```

## Implementation Phases

### v1.1.1 Zip Inventory + Cycle Data Discovery

Goals:

- Add a read-only zip inventory utility.
- Discover `*_cycle_data.csv`.
- Save or return inventory rows with zip file, internal path, size, and detected file type.
- Do not extract zip files.

Candidate output:

```text
data/processed/battery_archive_cycle_file_inventory.csv
```

### v1.1.2 Filename Metadata Parser

Goals:

- Parse source, cell ID, chemistry, form factor, temperature, SOC window, C-rate, and replicate ID from filenames.
- Preserve raw filename and internal CSV path.
- Add parse status and parse message.
- Use defensive heuristics instead of one brittle regex.

### v1.1.3 Cycle Data Loader and Schema Normalization

Goals:

- Read selected cycle CSV entries directly from zip.
- Normalize cycle columns.
- Handle optional `Start_Time` and `End_Time`.
- Add filename metadata to each row.
- Keep unreadable files in inventory/quality output rather than failing silently.

### v1.1.4 Processed Summary and Quality Report

Goals:

- Create full cycle summary.
- Compute capacity retention and approximate SOH.
- Add data quality flags.
- Create analysis-ready table from normal rows.
- Create optional source/cell quality summary.

Candidate outputs:

```text
data/processed/battery_archive_cycle_summary.csv
data/processed/battery_archive_analysis_ready.csv
data/processed/battery_archive_quality_summary.csv
```

### v1.1.5 Case Study Doc and Simulation Smoke

Goals:

- Add `data/case_studies/battery_archive/case_study.md`.
- Document source assumptions, quality flags, analysis-ready filtering, and limitations.
- Run existing analyzer modes on analysis-ready data:

```powershell
python src/process_data.py --mode eda --input data/processed/battery_archive_analysis_ready.csv --run-name battery_archive_eda
python src/process_data.py --mode reliability --input data/processed/battery_archive_analysis_ready.csv --run-name battery_archive_reliability
python src/process_data.py --mode simulation --input data/processed/battery_archive_analysis_ready.csv --target capacity_retention --features cycle_index temperature_C charge_c_rate discharge_c_rate --group-column cell_id --goal maximize --run-name battery_archive_cycle_screening
```

The simulation run should be described as tabular screening only, not degradation forecasting.

## Command Results

### `python -m pytest`

Result:

```text
99 passed in 29.87s
```

### `git status --short`

Status before creating this spec:

```text
?? docs/BATTERY_ARCHIVE_DATA_AUDIT.md
```

Actual status after creating this spec:

```text
?? docs/BATTERY_ARCHIVE_DATA_AUDIT.md
?? docs/V1_1_BATTERY_ARCHIVE_CASE_STUDY_SPEC.md
```
