# Kaggle Battery Simulation Comparison

## Dataset and analysis-ready filtering summary

- The case study uses Kaggle NASA battery discharge metadata and analysis-ready rows filtered by `retention_quality_flag == normal`.
- Full quality-audited rows remain available in `kaggle_nasa_battery_cycle_summary.csv`; analyzer-facing runs use the analysis-ready summary or feature-joined analysis-ready table.
- Raw discharge CSV files are summarized into scalar features only; raw time-series rows are not merged into the analyzer table.

## Model comparison table

| run_name | validation_type | test_r2 | r2_gap | test_rmse | rmse_ratio | cv_r2_mean | cv_rmse_mean | top_1_feature |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| metadata_random | random_split | 0.2340 | 0.1787 | 20.3328 | 1.1879 | 0.2180 | 19.8883 | cycle_index |
| feature_random | random_split | 0.9813 | 0.0136 | 3.1808 | 1.9857 | 0.9684 | 3.9336 | raw_sample_count |
| metadata_group | group_split_by_battery_id | 0.1660 | 0.1470 | 34.0606 | 2.4417 | 0.0437 | 18.6583 | cycle_index |
| feature_group | group_split_by_battery_id | 0.3415 | 0.6514 | 30.2664 | 21.2358 | 0.1115 | 17.4235 | temperature_mean_c |
| feature_no_count_group | group_split_by_battery_id | 0.3320 | 0.6610 | 30.4833 | 21.6960 | 0.1659 | 17.0770 | temperature_mean_c |

## Random split vs group split interpretation

- Random split runs can place cycles from the same battery in both train and test sets, which may overstate cycle-level predictive performance.
- Group split runs use `battery_id` separation and are the more relevant check for battery-level generalization.
- `metadata_group` test_r2: 0.1660; `metadata_random` test_r2: 0.2340; delta: -0.0680.
- `feature_group` test_r2: 0.3415; `feature_random` test_r2: 0.9813; delta: -0.6398.

## Metadata-only vs feature-enriched interpretation

- Metadata-only runs use cycle index, ambient temperature, and capacity-style metadata features.
- Feature-enriched runs include scalar summaries from raw discharge curves such as duration, voltage, current, and temperature statistics.
- `feature_random` test_r2: 0.9813; `metadata_random` test_r2: 0.2340; delta: 0.7472.
- `feature_group` test_r2: 0.3415; `metadata_group` test_r2: 0.1660; delta: 0.1755.

## raw_sample_count exclusion result

- `feature_no_count_group` excludes `raw_sample_count` to reduce dependence on a feature that may encode measurement length or logging behavior.
- `feature_no_count_group` test_r2: 0.3320; `feature_group` test_r2: 0.3415; delta: -0.0095.
- `feature_no_count_group` test_rmse: 30.4833; `feature_group` test_rmse: 30.2664; delta: 0.2170.

## Limitations

- These comparisons are case-study diagnostics, not proof of a production-ready battery degradation model.
- The current features are cycle-level summaries and do not model sequence history directly.
- Group-aware validation is stricter than random splitting, but it still depends on available battery diversity and metadata quality.
- Feature importance is model-specific and should be interpreted as a screening signal, not a causal explanation.

## Next step: battery-level generalization and lagged forecasting

- Use group-aware validation as the default for battery-level claims.
- Add lagged cycle features and battery-level holdout studies before forecasting future retention.
- Compare simple baseline forecasting approaches before adding more complex time-series ML/DL.
