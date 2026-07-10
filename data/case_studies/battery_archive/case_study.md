# Battery Archive Reliability Case Study

## Objective

This case study documents how `materials_data_analyzer` can turn Battery Archive cycle-level CSV data into compact reliability and degradation proxy summaries. It is a tabular engineering data case study, not a degradation forecasting model or remaining useful life prediction workflow.

## Dataset Scope

- Raw source: 9 Battery Archive zip files stored locally under `data/raw/battery_archive/`.
- Raw data is not committed to Git.
- Inventory audit found 196 `*_cycle_data.csv` files and 196 timeseries CSV files.
- This case study uses only cycle-level CSV files.
- Filename-derived metadata is used for source, chemistry, form factor, temperature, SOC window, and C-rate fields.
- Timeseries feature extraction is out of scope for this case study.

## Pipeline

1. Zip inventory without extraction.
2. Filename metadata enrichment.
3. Cycle CSV schema audit.
4. Schema normalization.
5. Cycle quality flags.
6. Initial discharge-capacity baseline.
7. Capacity retention.
8. Capacity-based SOH proxy.
9. 80% and 70% threshold crossing proxies.
10. Series-level and group-level summaries.

## Data Quality

- Cycle rows represented in compact summaries: 343,503.
- Cycle series: 196.
- Series with duplicate cycle index: 25.
- Series with nonmonotonic cycle index: 1.
- Series with invalid rows: 0.
- Series with warning or non-candidate status: 153.

Duplicate cycle-index and nonmonotonic cycle-index cases are retained as quality warnings. Source rows are not deleted. Groups with small sample counts are explicitly flagged so simple averages are not overinterpreted.

## Existing Platform Workflow

The compact `battery_archive_cycle_series_summary.csv` table can be passed to the existing EDA and reliability CLI modes without changing core analyzer logic. These smoke runs summarize the series-level table; they do not create a new forecasting model.

```powershell
python src/process_data.py --mode eda --input data/processed/battery_archive_cycle_series_summary.csv --run-name battery_archive_series_summary_eda_smoke
python src/process_data.py --mode reliability --input data/processed/battery_archive_cycle_series_summary.csv --run-name battery_archive_series_summary_reliability_smoke
```

## Reliability Summary

- Series reaching the 80% threshold proxy: 191.
- Series reaching the 70% threshold proxy: 187.
- Observed-censored at 80%: 5.
- Observed-censored at 70%: 9.

Threshold crossings are observed proxies only. A series that does not cross a threshold is treated as censored within the observed data window; no cycle life or RUL is inferred.

## Group Comparisons

Groups are defined by source, chemistry, form factor, temperature, SOC window, and charge/discharge C-rate. Metadata-missing groups are kept rather than silently dropped.

| source | chemistry | form_factor | temperature_C | soc_window | charge_c_rate | discharge_c_rate | series_count | median_final_retention_pct | reached_80pct_rate | warning_series_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Michigan Formation | NMC | pouch | 25.0 | 0-100 | 1.0 | 1.0 | 21 | 0.0 | 100.0 | 52.381 |
| Michigan Formation | NMC | pouch | 45.0 | 0-100 | 1.0 | 1.0 | 19 | 0.0 | 100.0 | 57.8947 |
| HNEI | NMC_LCO | 18650 | 25.0 | 0-100 | 0.5 | 1.5 | 15 | 74.27664079040225 | 100.0 | 100.0 |
| UL-Purdue | NCA | 18650 | 23.0 | 2.5-96.5 | 0.5 | 0.5 | 11 | 1.347190146266359 | 100.0 | 63.6364 |
| UL-Purdue | NCA | 18650 | 23.0 | 0-100 | 0.5 | 0.5 | 10 | 8.881905391994707 | 100.0 | 50.0 |
| Oxford | LCO | pouch | 40.0 | 0-100 | 2.0 | 1.84 | 8 | 78.28895879987292 | 62.5 | 0.0 |
| CALCE | LCO | prism | 25.0 | 0-100 | 0.5 | 0.5 | 7 | 41.28508124076809 | 100.0 | 100.0 |
| SNL LFP | LFP | 18650 | 25.0 | 0-100 | 0.5 | 1.0 | 4 | 0.0 | 100.0 | 100.0 |
| SNL LFP | LFP | 18650 | 25.0 | 0-100 | 0.5 | 3.0 | 4 | 0.0 | 100.0 | 100.0 |
| SNL LFP | LFP | 18650 | 25.0 | 20-80 | 0.5 | 0.5 | 4 | 0.0 | 100.0 | 100.0 |
| SNL LFP | LFP | 18650 | 35.0 | 0-100 | 0.5 | 1.0 | 4 | 0.0 | 100.0 | 100.0 |
| SNL NCA | NCA | 18650 | 25.0 | 0-100 | 0.5 | 1.0 | 4 | 0.0 | 100.0 | 100.0 |

## Threshold/Censoring Interpretation

The case study reports first crossing and persistent three-cycle crossing for 80% and 70% capacity-retention thresholds. Persistent crossing is a more conservative proxy than a single noisy crossing, but it is still an observed-data summary rather than a life prediction.

## Optional Simulation Validation

Simulation was not run automatically in v1.1.5. A future smoke run may use `capacity_retention_pct` as the target with group-aware validation by `cycle_series_id`. The `cycle_series_id`, baseline capacity, and `discharge_capacity` should not be used as predictive features because they either identify the group or are directly tied to target calculation.

## Limitations

- Battery Archive source/protocol differences mean group comparisons are descriptive.
- Filename metadata may be incomplete or heuristic.
- SOH is represented only as a capacity-based proxy.
- Threshold crossing proxies are not remaining useful life estimates.
- Timeseries behavior and impedance are not included.

## Reproduction Commands

```powershell
python scripts/build_battery_archive_cycle_inventory.py --raw-dir data/raw/battery_archive --output data/processed/battery_archive_cycle_file_inventory.csv
python scripts/enrich_battery_archive_cycle_inventory.py --input data/processed/battery_archive_cycle_file_inventory.csv --output data/processed/battery_archive_cycle_file_inventory_enriched.csv
python scripts/audit_battery_archive_cycle_schemas.py --raw-dir data/raw/battery_archive --inventory data/processed/battery_archive_cycle_file_inventory_enriched.csv --schema-output data/processed/battery_archive_cycle_schema_inventory.csv --column-output data/processed/battery_archive_cycle_column_inventory.csv --report-output docs/BATTERY_ARCHIVE_CYCLE_SCHEMA_AUDIT.md
python scripts/build_battery_archive_cycle_normalized.py --raw-dir data/raw/battery_archive --inventory data/processed/battery_archive_cycle_file_inventory_enriched.csv --schema-inventory data/processed/battery_archive_cycle_schema_inventory.csv --column-inventory data/processed/battery_archive_cycle_column_inventory.csv --normalized-output data/processed/battery_archive_cycle_normalized.csv --summary-output data/processed/battery_archive_cycle_load_summary.csv --mapping-output data/processed/battery_archive_cycle_column_mapping.csv
python scripts/build_battery_archive_analysis_ready.py --input data/processed/battery_archive_cycle_normalized.csv --analysis-ready-output data/processed/battery_archive_cycle_analysis_ready.csv --series-summary-output data/processed/battery_archive_cycle_series_summary.csv --quality-summary-output data/processed/battery_archive_data_quality_summary.csv
python scripts/build_battery_archive_case_study.py --series-summary data/processed/battery_archive_cycle_series_summary.csv --group-summary-output data/processed/battery_archive_reliability_group_summary.csv --report-output data/case_studies/battery_archive/case_study.md
```

## Output Files

- `data/processed/battery_archive_cycle_series_summary.csv`: compact per-series quality and threshold summary.
- `data/processed/battery_archive_data_quality_summary.csv`: compact global/source data-quality metrics.
- `data/processed/battery_archive_reliability_group_summary.csv`: compact group-level reliability proxy summary.
- `data/case_studies/battery_archive/case_study.md`: narrative case-study report.
- `data/processed/battery_archive_cycle_analysis_ready.csv`: large generated local artifact, not recommended for Git tracking.

## Conclusion

This Battery Archive case study complements the Kaggle NASA battery case study by demonstrating a larger, multi-source cycle-data workflow. It emphasizes raw zip inventory, schema normalization, quality flags, censored threshold interpretation, and compact reproducibility outputs rather than predictive degradation modeling.
