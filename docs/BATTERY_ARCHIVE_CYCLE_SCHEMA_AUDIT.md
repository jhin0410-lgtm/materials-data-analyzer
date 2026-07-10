# Battery Archive Cycle Schema Audit

Scope: cycle CSV schema audit only. Raw zip files were read in place with Python `zipfile`; no zip archive was extracted and no final normalized cycle table was created.

## Inputs

- Raw directory: `data/raw/battery_archive`
- Inventory: `data/processed/battery_archive_cycle_file_inventory_enriched.csv`
- Maximum sample rows per file: `50`

## Summary

- Zip files represented: 9
- Inventory rows: 196
- Audited cycle files with readable headers: 196
- Unique schema fingerprints: 2
- Unique raw columns: 12

## Read Status Counts

| read_status | count |
| --- | --- |
| success | 196 |

## Top Schema Fingerprints

| schema_fingerprint | file_count | column_count | example_files |
| --- | --- | --- | --- |
| schema_d2669a99bc63 | 116 | 12 | CALCE_CX2-16_prism_LCO_25C_0-100_0.5-0.5C_a_cycle_data.csv; CALCE_CX2-25_prism_LCO_25C_0-100_0.5-0.5C_b_cycle_data.csv; CALCE_CX2-33_prism_LCO_25C_0-100_0.5-0.5C_d_cycle_data.csv |
| schema_63d0cb98b657 | 80 | 10 | MICH_01R_pouch_NMC_25C_0-100_0.2-0.2C_cycle_data.csv; MICH_02C_pouch_NMC_-5C_0-100_0.2-0.2C_cycle_data.csv; MICH_03H_pouch_NMC_45C_0-100_0.2-0.2C_cycle_data.csv |

## Source Archive Schema Variation

| zip_file | file_count | unique_schema_count | read_error_count |
| --- | --- | --- | --- |
| CALCE.zip | 7 | 1 | 0 |
| HNEI.zip | 15 | 1 | 0 |
| Michigan Expansion.zip | 18 | 1 | 0 |
| Michigan Formation.zip | 40 | 1 | 0 |
| Oxford.zip | 8 | 1 | 0 |
| SNL LFP.zip | 30 | 1 | 0 |
| SNL NCA.zip | 24 | 1 | 0 |
| SNL NMC.zip | 32 | 1 | 0 |
| UL-Purdue.zip | 22 | 1 | 0 |

## Frequent Raw Columns

| raw_column | files |
| --- | --- |
| Charge_Capacity (Ah) | 196 |
| Charge_Energy (Wh) | 196 |
| Cycle_Index | 196 |
| Discharge_Capacity (Ah) | 196 |
| Discharge_Energy (Wh) | 196 |
| Max_Current (A) | 196 |
| Max_Voltage (V) | 196 |
| Min_Current (A) | 196 |
| Min_Voltage (V) | 196 |
| Test_Time (s) | 196 |
| End_Time | 116 |
| Start_Time | 116 |

## Frequent Normalized Columns

| normalized_column | files |
| --- | --- |
| charge_capacity_ah | 196 |
| charge_energy_wh | 196 |
| cycle_index | 196 |
| discharge_capacity_ah | 196 |
| discharge_energy_wh | 196 |
| max_current_a | 196 |
| max_voltage_v | 196 |
| min_current_a | 196 |
| min_voltage_v | 196 |
| test_time_s | 196 |
| end_time | 116 |
| start_time | 116 |

## Mapping Candidate Coverage

| mapping_candidate | file_count | coverage_percent |
| --- | --- | --- |
| cycle_index | 196 | 100.0 |
| charge_capacity | 196 | 100.0 |
| discharge_capacity | 196 | 100.0 |
| charge_energy | 196 | 100.0 |
| discharge_energy | 196 | 100.0 |
| coulombic_efficiency | 0 | 0.0 |
| capacity_retention | 0 | 0.0 |
| soh | 0 | 0.0 |
| internal_resistance | 0 | 0.0 |
| temperature | 0 | 0.0 |
| elapsed_time | 196 | 100.0 |
| date_or_timestamp | 116 | 59.2 |

## Unit Variation

| normalized_column_name | unit_candidate | count |
| --- | --- | --- |
| charge_capacity_ah | Ah | 196 |
| charge_energy_wh | Wh | 196 |
| cycle_index | unknown | 196 |
| discharge_capacity_ah | Ah | 196 |
| discharge_energy_wh | Wh | 196 |
| max_current_a | A | 196 |
| max_voltage_v | V | 196 |
| min_current_a | A | 196 |
| min_voltage_v | V | 196 |
| test_time_s | s | 196 |
| end_time | unknown | 116 |
| start_time | unknown | 116 |

## Clearly Mappable Areas

| mapping_candidate | file_count | coverage_percent |
| --- | --- | --- |
| cycle_index | 196 | 100.0 |
| charge_capacity | 196 | 100.0 |
| discharge_capacity | 196 | 100.0 |
| charge_energy | 196 | 100.0 |
| discharge_energy | 196 | 100.0 |
| elapsed_time | 196 | 100.0 |
| date_or_timestamp | 116 | 59.2 |

## Uncertain Or Non-target Mapping Areas

| raw_column_name | normalized_column_name | mapping_candidate | mapping_confidence | mapping_note |
| --- | --- | --- | --- | --- |
| Min_Current (A) | min_current_a | unknown | none | observed electrical measurement, not a requested mapping target |
| Max_Current (A) | max_current_a | unknown | none | observed electrical measurement, not a requested mapping target |
| Min_Voltage (V) | min_voltage_v | unknown | none | observed electrical measurement, not a requested mapping target |
| Max_Voltage (V) | max_voltage_v | unknown | none | observed electrical measurement, not a requested mapping target |

## Read Errors

_No rows._

## v1.1.3b Normalization Recommendations

- Use `Cycle_Index` as the initial `cycle_index` candidate when present.
- Preserve `Start_Time` and `End_Time` as optional timestamp-like columns.
- Keep `Charge_Capacity` and `Discharge_Capacity` separate; do not infer direction from generic `Capacity` columns.
- Preserve observed units such as `Ah`, `Wh`, `A`, `V`, and `s`; unit conversion is a later explicit step.
- Treat missing direct retention, SOH, temperature, and internal resistance columns as schema facts, not failures.

## Risks Before Normalization

- A schema audit does not validate battery science conclusions.
- Sample-row dtype inference may miss rare values outside the first rows.
- Semantic mappings are candidates only; final normalization should remain reviewable and source-traceable.
- Derived capacity retention, SOH, cycle-life proxy, and quality flags are out of scope for this audit.

## Raw Zip Extraction Check

This audit reads zip members directly and does not write extracted raw CSV files to `data/raw/` or any temporary extraction folder.

## Generated Outputs

- `data/processed/battery_archive_cycle_schema_inventory.csv`
- `data/processed/battery_archive_cycle_column_inventory.csv`
- `docs/BATTERY_ARCHIVE_CYCLE_SCHEMA_AUDIT.md`

## Implementation Follow-up: v1.1.3b Cycle Normalization

The v1.1.3b loader reads the 196 audited `*_cycle_data.csv` members directly
from the raw zip files and writes a source-traceable normalized cycle table.
No raw zip archive is extracted, and no raw file content is modified.

Generated v1.1.3b outputs:

- `data/processed/battery_archive_cycle_normalized.csv`
- `data/processed/battery_archive_cycle_load_summary.csv`
- `data/processed/battery_archive_cycle_column_mapping.csv`

### Mapping Result

The normalized mapping contract is based only on the two schemas observed in
this audit.

| Raw column | Canonical column | Unit | Required | Notes |
| --- | --- | --- | --- | --- |
| `Cycle_Index` | `cycle_index` | unknown | yes | Present in both schemas. |
| `Test_Time (s)` | `elapsed_time` | `s` | yes | Values are preserved without conversion. |
| `Min_Current (A)` | `min_current` | `A` | yes | Common observed electrical summary column. |
| `Max_Current (A)` | `max_current` | `A` | yes | Common observed electrical summary column. |
| `Min_Voltage (V)` | `min_voltage` | `V` | yes | Common observed electrical summary column. |
| `Max_Voltage (V)` | `max_voltage` | `V` | yes | Common observed electrical summary column. |
| `Charge_Capacity (Ah)` | `charge_capacity` | `Ah` | yes | Values are preserved without conversion. |
| `Discharge_Capacity (Ah)` | `discharge_capacity` | `Ah` | yes | Values are preserved without conversion. |
| `Charge_Energy (Wh)` | `charge_energy` | `Wh` | yes | Values are preserved without conversion. |
| `Discharge_Energy (Wh)` | `discharge_energy` | `Wh` | yes | Values are preserved without conversion. |
| `Start_Time` | `start_time` | unknown | no | Present only in `schema_d2669a99bc63`; also copied to `date_or_timestamp`. |
| `End_Time` | `end_time` | unknown | no | Present only in `schema_d2669a99bc63`. |

### Actual Raw Smoke Result

| Metric | Value |
| --- | ---: |
| Cycle files processed | 196 |
| Total raw rows | 343,503 |
| Total normalized rows | 343,503 |
| Load status `success` | 196 |
| Load status `success_with_warnings` | 0 |
| Load status `load_error` | 0 |
| Dropped blank rows | 0 |
| Invalid numeric values in tracked critical fields | 0 |
| Duplicate `(zip_file, internal_csv_path, source_row_number)` keys | 0 |
| Absolute local path cells in normalized output | 0 |
| Timeseries paths in normalized output | 0 |

Schema-level normalized row counts:

| Schema fingerprint | Normalized rows |
| --- | ---: |
| `schema_d2669a99bc63` | 306,248 |
| `schema_63d0cb98b657` | 37,255 |

Source-level normalized row counts:

| Source | Normalized rows |
| --- | ---: |
| SNL LFP | 168,678 |
| SNL NMC | 76,738 |
| SNL NCA | 31,305 |
| Michigan Formation | 21,239 |
| HNEI | 16,528 |
| CALCE | 12,480 |
| UL-Purdue | 9,471 |
| Michigan Expansion | 6,545 |
| Oxford | 519 |

### Not Yet Computed

The v1.1.3b normalized table intentionally does not compute derived battery
metrics. The following remain out of scope for this step:

- capacity retention
- SOH
- cycle-life proxy
- quality filtering
- reliability analysis
- simulation or virtual experiment screening
- timeseries feature extraction

### Carryover To v1.1.4

- Define explicit quality rules for missing or invalid critical cycle fields.
- Decide how to compute capacity retention without hiding source-level
  assumptions.
- Create an analysis-ready table separately from the full normalized table.
- Keep full provenance columns available for traceability.
- Treat the large normalized CSV as a generated artifact whose tracking policy
  should be reviewed before commit.
