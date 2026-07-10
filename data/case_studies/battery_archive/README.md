# Battery Archive Case Study

This folder documents the Battery Archive reliability/degradation proxy case
study for `materials_data_analyzer`.

Battery Archive is the second representative real-data case study in this
project. It differs from the Kaggle NASA battery case study by focusing on raw
zip inventory, filename metadata parsing, cycle CSV schema normalization,
quality flags, threshold/censoring summaries, and compact group-level
reliability summaries.

## Files

- `source.md`: source scope, raw-data policy, and metadata assumptions.
- `methodology.md`: reproducible processing steps and commands.
- `case_study.md`: narrative case-study report generated from compact summaries.

## Key Processed Outputs

- `data/processed/battery_archive_cycle_series_summary.csv`
- `data/processed/battery_archive_data_quality_summary.csv`
- `data/processed/battery_archive_reliability_group_summary.csv`

The large `data/processed/battery_archive_cycle_analysis_ready.csv` file is a
generated local artifact and is not recommended for Git tracking.
