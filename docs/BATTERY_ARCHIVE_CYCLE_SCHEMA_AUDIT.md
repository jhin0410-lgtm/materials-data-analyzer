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
