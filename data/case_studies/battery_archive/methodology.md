# Battery Archive Case Study Methodology

This methodology is intentionally conservative and reproducible.

## Steps

1. Zip inventory
2. Filename metadata enrichment
3. Schema audit
4. Schema normalization
5. Quality flags
6. Baseline capacity
7. Capacity retention
8. Capacity-based SOH proxy
9. 80%/70% threshold crossing proxy
10. Series-level summary
11. Group-level reliability summary

## Commands

```powershell
python scripts/build_battery_archive_cycle_inventory.py --raw-dir data/raw/battery_archive --output data/processed/battery_archive_cycle_file_inventory.csv
python scripts/enrich_battery_archive_cycle_inventory.py --input data/processed/battery_archive_cycle_file_inventory.csv --output data/processed/battery_archive_cycle_file_inventory_enriched.csv
python scripts/audit_battery_archive_cycle_schemas.py --raw-dir data/raw/battery_archive --inventory data/processed/battery_archive_cycle_file_inventory_enriched.csv --schema-output data/processed/battery_archive_cycle_schema_inventory.csv --column-output data/processed/battery_archive_cycle_column_inventory.csv --report-output docs/BATTERY_ARCHIVE_CYCLE_SCHEMA_AUDIT.md
python scripts/build_battery_archive_cycle_normalized.py --raw-dir data/raw/battery_archive --inventory data/processed/battery_archive_cycle_file_inventory_enriched.csv --schema-inventory data/processed/battery_archive_cycle_schema_inventory.csv --column-inventory data/processed/battery_archive_cycle_column_inventory.csv --normalized-output data/processed/battery_archive_cycle_normalized.csv --summary-output data/processed/battery_archive_cycle_load_summary.csv --mapping-output data/processed/battery_archive_cycle_column_mapping.csv
python scripts/build_battery_archive_analysis_ready.py --input data/processed/battery_archive_cycle_normalized.csv --analysis-ready-output data/processed/battery_archive_cycle_analysis_ready.csv --series-summary-output data/processed/battery_archive_cycle_series_summary.csv --quality-summary-output data/processed/battery_archive_data_quality_summary.csv
python scripts/build_battery_archive_case_study.py --series-summary data/processed/battery_archive_cycle_series_summary.csv --group-summary-output data/processed/battery_archive_reliability_group_summary.csv --report-output data/case_studies/battery_archive/case_study.md
```

No raw zip is extracted by these scripts. Large generated cycle-level tables should remain local-only by default.
