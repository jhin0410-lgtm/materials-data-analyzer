# Kaggle NASA Battery Capacity Retention Case Study

## 1. Overview

This case study demonstrates a capacity retention analysis workflow using the Kaggle NASA battery dataset. The goal is to show how the Materials & Manufacturing Data Analyzer can turn tabular engineering data and cycle-level discharge summaries into a validated diagnostic analysis.

The workflow uses two data sources from the Kaggle cleaned dataset:

- `metadata.csv`, which provides cycle metadata such as battery ID, test type, temperature, capacity, filename, UID, and test ID.
- Raw discharge CSV files, which provide cycle-level voltage, current, temperature, and time-series measurements.

This is a data-driven diagnostic case study. It is not a physics simulation, not an automatic optimization workflow, and not a replacement for real battery experiments.

## 2. Data Preparation

The metadata loader filtered `metadata.csv` to discharge rows only and produced a cycle-level summary table.

- Discharge rows extracted: 2,794
- Normal rows: 2,495
- `high_retention_warning` rows: 255
- `invalid_capacity` rows: 44
- Rows excluded from the analysis-ready table: 299

The workflow separates the processed outputs into two main tables:

- Full audit CSV: `data/processed/kaggle_nasa_battery_cycle_summary.csv`
- Analysis-ready CSV: `data/processed/kaggle_nasa_battery_cycle_summary_analysis_ready.csv`

The full audit CSV preserves all discharge rows for data quality review. The analysis-ready CSV keeps rows where `retention_quality_flag == normal`, so downstream EDA and simulation runs are not dominated by known quality warnings.

The `failed` column is not an original dataset label. It is a derived analysis label defined as:

```text
failed = 1 when capacity_retention_percent < 80
failed = 0 otherwise
```

## 3. Feature Engineering

Two feature sets were compared.

Metadata-only features:

- `cycle_index`
- `ambient_temperature_c`

Raw discharge curve-derived features:

- Discharge duration features
- Voltage summary features
- Current summary features
- Temperature summary features
- Raw sample count, used in one feature-enriched run and removed in a follow-up group-split check

The `discharge_capacity_ah` column was excluded from retention prediction features because `capacity_retention_percent` is directly calculated from discharge capacity. Including it would make the model evaluation less meaningful for this retention prediction case study.

## 4. Model Validation Design

The case study compares both random split and `battery_id` group split validation.

Random split:

- Cycles from the same battery may appear in both train and test sets.
- This is closer to within-battery diagnostic interpolation.
- It can overstate performance if the goal is to generalize to unseen batteries.

Battery group split:

- `battery_id` is used as the validation group.
- Train and test batteries do not overlap.
- This is closer to unseen-battery generalization.

Both validation views are useful, but they answer different questions.

## 5. Results

| Run | Validation design | Test R2 | Test RMSE |
| --- | --- | ---: | ---: |
| Metadata random | Random split | 0.234 | 20.33 |
| Feature random | Random split | 0.981 | 3.18 |
| Metadata group | `battery_id` group split | 0.166 | 34.06 |
| Feature group | `battery_id` group split | 0.341 | 30.27 |
| Feature no-count group | `battery_id` group split | 0.332 | 30.48 |

## 6. Interpretation

Raw discharge-derived features greatly improved random-split performance. This suggests that voltage, current, temperature, and duration summaries contain strong same-cycle diagnostic information related to capacity retention.

However, the group split results were much weaker. This indicates that the current feature set has limited generalization to unseen batteries, even though it performs well when train and test cycles can come from the same batteries.

Removing `raw_sample_count` had little effect under group split:

- Feature group test R2: 0.341
- Feature no-count group test R2: 0.332

The main conclusion is that the current model is strong for within-battery diagnostic interpolation, but weak for unseen-battery generalization.

## 7. Feature Importance

In the group-split feature-enriched runs, important features included:

- `temperature_mean_c`
- `temperature_max_c`
- `cycle_index`
- `current_mean_a`
- Voltage summary features

These importance values should be interpreted as model-specific screening signals only. They are not causal explanations of battery degradation.

## 8. Limitations

- Capacity retention is derived from the Kaggle cleaned metadata, not provided as a direct original target column.
- Some batteries showed reference-capacity issues, so quality flags and analysis-ready filtering were applied before analyzer runs.
- The current model is closer to same-cycle diagnostic prediction than lagged forecasting.
- Group split performance remains low, so the current model has clear limitations for unseen battery prediction.
- The raw discharge CSV files were reduced to scalar cycle-level features; the full time-series curves were not modeled directly.

## 9. Next Steps

- Require independent, protocol-comparable battery evidence before adding
  model complexity.
- Audit whether external calibration and uncertainty metadata can support a
  scientifically stronger forecasting comparison.
- Keep impedance alignment separate until cycle-level comparability is
  established.

## 10. v2.6.1 Lagged Forecasting Closeout

v2.6.1 evaluates 2,100 exact five-cycle origins across 33 batteries using only
current and earlier retention history. Deterministic GroupKFold partitions
have zero train/test battery overlap. The scenario is
`warm_start_cross_battery`, not zero-shot, because each held-out battery
contributes its own pre-origin history.

Persistence achieved pooled MAE 3.4256; the fixed train-only Ridge pipeline
achieved 4.1537 and improved 13 of 33 batteries. The scientific assessment is
therefore `unsupported`. Three Ridge predictions were negative and were
reported without clipping. See
[Battery-Level Generalization Forecasting](../../../docs/BATTERY_GENERALIZATION_FORECASTING.md)
for the complete feature, split, leakage, plausibility, and claim boundary.
