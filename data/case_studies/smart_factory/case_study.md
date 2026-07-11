# Smart Factory Process-Quality Case Study

## 1. Executive Summary

This case study uses the UCI SECOM semiconductor manufacturing dataset as the
v1.4 operational fallback for a Smart Factory process-quality workflow.

The final v1.4 result is a trust-boundary demonstration, not a production
failure model. The workflow shows how `materials_data_analyzer` handles source
provenance, row-order alignment, temporal validation, train-only
preprocessing, classical baseline classification, and conservative claim
boundaries for high-dimensional process-quality data.

Key result: all non-dummy classification baselines remain `diagnostic_only`.
No representative model is selected.

## 2. Manufacturing Question

The case-study question is:

Can future time-block failure risk in SECOM process data be discriminated using
only past observations?

The result can discuss chronological holdout discrimination, random-versus-time
validation gaps, classical baseline behavior, and limited offline risk-ranking
diagnostics. It cannot establish causal root cause, real-time control,
equipment-specific generalization, calibrated production probability, or
production deployment readiness.

## 3. Dataset Access Decision

Bosch Production Line Performance was treated as the conditional primary
candidate, but it was not promoted because local access, terms, and file
inventory were not verified.

UCI SECOM was activated as the operational fallback. SECOM is public, compact,
and process-quality aligned, but it lacks explicit equipment, lot, product,
and recipe identifiers.

## 4. SECOM Provenance

The acquisition manifest records the SECOM source, DOI, license, raw-file
hashes, row count, feature count, and target mapping. Raw files remain
local-only under `data/raw/`.

Observed source structure:

- Rows: 1,567
- Raw process features: 590
- Pass rows: 1,463
- Fail rows: 104
- Failure prevalence: 0.0664
- Raw target mapping: `-1 -> pass -> 0`, `1 -> fail -> 1`
- Timestamp format: `%d/%m/%Y %H:%M:%S`

## 5. Dataset Structure

SECOM has a high-dimensional numeric process matrix and a separate
label/timestamp file. v1.4 aligns them only by original row position after
verifying equal row counts. No independent sorting is performed before the
join.

The analysis-ready table preserves:

- `sample_index`
- raw timestamp string
- parsed `observation_timestamp`
- `source_order_index`
- `chronological_rank`
- raw and mapped target columns
- 590 process feature columns

## 6. Readiness Findings

Readiness status:

- Time-aware validation: conditionally ready
- Group-aware validation: not ready
- Capability analysis: not ready
- SPC: partially conditional, depending on chart type

Feature-quality audit:

- Complete: 52
- Low missing: 364
- Moderate missing: 20
- High missing: 4
- Very high missing: 28
- Constant: 116
- Near constant: 6

## 7. Temporal Integrity

Temporal audit results:

- Timestamp parse failures: 0
- Duplicate timestamps: 65
- Source-order monotonicity: true
- Chronological inversions: 0

Duplicate timestamps are retained, with source order used as the deterministic
tie-breaker.

## 8. Feature-Quality Findings

The feature matrix is high-dimensional and sparse in places. v1.4.4
preprocessing is fit within each training partition only:

- Remove all-missing training columns
- Remove constant training columns
- Remove columns with train-fold missing rate at or above 0.95
- Retain near-constant columns but record diagnostics
- Median-impute from training data only
- Scale linear-model features from training data only

No target-informed feature selection is used.

## 9. Validation Hierarchy

Primary evidence:

- Chronological blocked splits
- Expanding-window future holdout
- Final chronological holdout

Secondary reference:

- Stratified random split

Random split is treated as an optimistic reference only.

## 10. Models and Preprocessing

Fixed classical baseline models:

- `dummy_prior`
- `logistic_regression_balanced`
- `random_forest_balanced`
- `hist_gradient_boosting_balanced`

No hyperparameter search, SMOTE, deep learning, SHAP, or test-set threshold
tuning is performed.

## 11. Classification Results

Primary metric: average precision / PR-AUC.

Summary:

- Best temporal median PR-AUC: 0.0725
- Best final holdout PR-AUC: 0.1570
- Best random-reference PR-AUC: 0.1599
- Global failure prevalence: 0.0664
- Non-dummy model statuses: `diagnostic_only`
- Representative model: none

The best temporal median PR-AUC is only slightly above prevalence and does not
support a strong predictive claim.

## 12. Random vs Temporal Comparison

Random-reference performance is higher than temporal performance for several
models. The trust summary classifies the overall random-temporal interpretation
as `random_optimistic`.

This may indicate temporal distribution variation, small failure support,
high-dimensional missing data, or optimistic split structure. It is not a
causal diagnosis.

## 13. Threshold and Calibration Limitations

The fixed threshold is 0.5. It is always recorded, but it is not tuned with
test labels.

Threshold results do not support binary production failure decisions or
production alerts. Brier score and log loss are diagnostics only. Model scores
must be described as uncalibrated risk scores, not calibrated probabilities.

## 14. Model Eligibility

No non-dummy model passes the predeclared candidate gate. Rejection reasons
include small temporal lift over prevalence, random-temporal gaps, weak
threshold recall or precision, and insufficient consistency above the dummy
baseline.

Allowed model status values are:

- `descriptive_only`
- `diagnostic_only`
- `limited_predictive_evidence`
- `candidate_for_further_validation`

There is no `production_ready` status.

## 15. Why No Representative Model Was Selected

No representative model is selected because the evidence chain is too weak:

- Temporal median PR-AUC is close to prevalence.
- Final holdout improvement is not enough by itself.
- Random-reference performance is optimistic relative to temporal evidence.
- Threshold-level failure detection is weak.
- No external holdout or group-aware validation exists.
- Feature semantics are anonymized.

## 16. SPC and Capability Limitations

Final SPC/capability status:

- I-MR: conditional exploratory use only after stable baseline selection
- X-bar/R: not ready, no rational subgroup
- X-bar/S: not ready, no rational subgroup
- p/np: conditional only with justified chronological aggregation
- Cp/Cpk/Pp/Ppk: not ready, no specification limits

No control charts or capability indices are computed in v1.4.5.

## 17. Trust Boundary

Allowed:

- Retrospective offline diagnostic comparison
- Time-aware validation framework demonstration
- Random split as optimistic reference
- Documentation of why no representative production model is selected

Not allowed:

- Accurate failure prediction claim
- Production-ready model claim
- Real-time monitoring solution claim
- Causal root-cause claim
- Fab-wide generalization claim
- Calibrated probability claim
- Process optimization achieved claim

## 18. Allowed Claims

The v1.4 Smart Factory case study may be described as a conservative
process-quality validation and trust-boundary workflow for tabular
manufacturing data.

It demonstrates source checks, leakage-aware temporal validation, train-only
preprocessing, baseline diagnostics, and honest closeout when the model is
weak.

## 19. Prohibited Claims

Do not describe v1.4 as:

- Accurate failure prediction
- Robust defect detection
- Production-ready Smart Factory model
- Real-time monitoring solution
- Root-cause identification
- Fab-wide generalization
- Calibrated probability estimation
- Process optimization

## 20. Reproducibility

Key commands:

```powershell
python scripts/build_smart_factory_v1_4_acquisition.py
python scripts/build_smart_factory_v1_4_analysis_ready.py
python scripts/run_smart_factory_v1_4_classification.py
python scripts/run_smart_factory_v1_4_trust_analysis.py
```

The actual acquisition and analysis-ready steps require local SECOM raw files.
Unit and full test suites are designed to pass without raw/local-only files.

## 21. Local-Only Artifact Policy

Local-only artifacts:

- `data/raw/smart_factory/`
- `data/processed/smart_factory_v1_4_secom_analysis_ready.csv`
- `data/processed/smart_factory_v1_4_classification_predictions.csv`
- `outputs/`

Compact tracked artifacts are limited to machine-readable summaries,
specifications, and closeout tables.

## 22. Future Data Requirements

Stronger manufacturing modeling would require:

- Equipment IDs
- Lot IDs
- Product IDs
- Recipe IDs
- Maintenance event timestamps
- Inspection or quality measurement timestamps
- Specification limits
- Rational subgroup definitions
- Longer chronological coverage
- More failures
- External fab or line holdout
- Known feature semantics
- Intervention/outcome records

Without these, additional tuning is less important than better data structure.

## 23. Final Conclusion

v1.4 is release-ready as a Smart Factory process-quality trust-boundary case
study. It does not produce a production-ready predictive model. Its value is
that it preserves weak model evidence, documents why stronger claims are not
allowed, and demonstrates how the platform handles time-aware validation and
engineering claim boundaries.
