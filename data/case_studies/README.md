# Case Studies

This folder contains real-data demonstrations for `materials_data_analyzer`.

Case studies are not core analyzer modes. They show how the core platform can be applied to public or properly licensed engineering tabular datasets after source-specific loading, quality review, and analysis-ready table preparation.

## Current Case Studies

### `kaggle_battery/`

Representative real-data case study using the Kaggle NASA battery dataset.

This folder documents:

- Data source and raw-data policy
- Metadata-based discharge cycle summary generation
- Full audit versus analysis-ready filtering
- Raw discharge CSV feature extraction
- Random split versus `battery_id` group split validation
- Simulation comparison results
- Portfolio-style case-study interpretation and limitations

Key files:

```text
data/case_studies/kaggle_battery/README.md
data/case_studies/kaggle_battery/source.md
data/case_studies/kaggle_battery/case_study.md
data/case_studies/kaggle_battery/simulation_comparison.md
```

## Other Source Notes

Other folders may contain source notes or early dataset exploration notes:

```text
data/case_studies/battery/
data/case_studies/battery_archive/
data/case_studies/htem/
data/case_studies/materials_project/
```

Treat these as documentation or optional ingestion references unless they are promoted to full case studies.

