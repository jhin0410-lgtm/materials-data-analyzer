# Processed Data

This folder contains generated or curated case-study summary artifacts.

Processed files are not raw data. They should be derived from documented source data through loader scripts, inspection scripts, or analyzer workflows. Large raw datasets, source archives, API responses, and credentials should not be stored here.

## Kaggle NASA Battery Case Study Summaries

The following files are the main processed artifacts for the Kaggle NASA battery case study:

```text
kaggle_nasa_battery_cycle_summary.csv
kaggle_nasa_battery_cycle_summary_analysis_ready.csv
kaggle_nasa_battery_quality_summary.csv
kaggle_nasa_battery_discharge_features.csv
kaggle_nasa_battery_analysis_ready_with_features.csv
kaggle_battery_simulation_comparison.csv
```

Roles:

- `kaggle_nasa_battery_cycle_summary.csv`: full quality-audited discharge cycle summary from Kaggle metadata.
- `kaggle_nasa_battery_cycle_summary_analysis_ready.csv`: analysis-ready subset filtered to normal retention-quality rows.
- `kaggle_nasa_battery_quality_summary.csv`: battery-level quality summary used to inspect warning rates and retention ranges.
- `kaggle_nasa_battery_discharge_features.csv`: scalar features extracted from raw discharge CSV files, such as voltage/current/temperature/duration summaries.
- `kaggle_nasa_battery_analysis_ready_with_features.csv`: analysis-ready metadata summary joined with discharge-derived scalar features.
- `kaggle_battery_simulation_comparison.csv`: summary table comparing selected simulation runs.

## Policy

- Keep only intentional, documented summary artifacts.
- Do not store raw downloaded datasets here.
- Do not store API keys, Kaggle credentials, or local config files here.
- If a processed file is not referenced by case-study documentation or tests, review whether it should remain local/generated.

