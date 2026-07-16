# Materials Physics Feature Predictive-Value Summary

- Status: `performance_degraded`
- Matched rows: `838`
- Generated feature rows: `838`
- Feature coverage: `1.000000`
- Combined primary median MAE improvement: `-0.0005982293913257795`
- Physics-only primary median MAE improvement: `0.0`

## Claim Boundary

- These are `physics_informed_feature_available` and `physics_informed_feature_used` features only.
- They are not a physics-constrained model, hybrid physics ML model, DFT replacement, or discovery claim.
- SHAP and feature-importance interpretation remain deferred.

## Combined Feature-Set Delta Snapshot

| Split | Model | Median MAE Improvement | Valid Splits |
| --- | --- | ---: | ---: |
| chemical_system_group | dummy_median | 0.0 | 10 |
| chemical_system_group | histogram_gradient_boosting_log1p | -0.0008359957503128387 | 10 |
| chemical_system_group | histogram_gradient_boosting_raw | -0.0008844068763725621 | 10 |
| chemical_system_group | ridge_log1p | -0.0006130313340233298 | 10 |
| chemical_system_group | ridge_raw | -0.0018149256069258934 | 10 |
| random | dummy_median | 0.0 | 10 |
| random | histogram_gradient_boosting_log1p | 0.000336500463205075 | 10 |
| random | histogram_gradient_boosting_raw | 0.0005658646704279069 | 10 |
| random | ridge_log1p | -6.402495230359295e-06 | 10 |
| random | ridge_raw | -0.0005490046037126134 | 10 |
| reduced_formula_group | dummy_median | 0.0 | 10 |
| reduced_formula_group | histogram_gradient_boosting_log1p | -0.0013999754929291536 | 10 |
| reduced_formula_group | histogram_gradient_boosting_raw | 0.0006866282497923898 | 10 |
| reduced_formula_group | ridge_log1p | -0.0005726423994462937 | 10 |
| reduced_formula_group | ridge_raw | -0.0005834274486282293 | 10 |
