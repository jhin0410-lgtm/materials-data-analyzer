# NASA PCoE Full-Audit Remediation

## Scope

This remediation closes the software and provenance gaps found in the 2026-08-04 full-bundle audit. It does **not** convert the NASA result into external scientific validation.

## Implemented controls

- Audit packaging copies the complete analysis directory and, when locally available, the NASA import output, original `5_Battery_Data_Set.zip`, and `retrieval_receipt.json`.
- Text artifacts are path-redacted in staging. Packaging fails closed if a Windows or common POSIX absolute path remains.
- The audit manifest inventories every staged artifact except the self-referential manifest and package inventory/readme, with byte counts and SHA-256 values.
- Discharge-only raw signals retain unavailable charge, CC, and CV quantities as missing values with explicit availability fields. They are never encoded as physical zeros.
- Forecast feature eligibility is fitted within each training fold. All-missing, constant, and exact-duplicate columns are removed using training data only.
- Every fold records selected and dropped features, imputation statistics, missing indicators, scaler parameters, Ridge coefficients, intercept, and calibration evidence.
- `source_cohort_id` is derived from the innermost nested ZIP in `source_mat_file` lineage.
- The workflow reports both battery-disjoint GroupKFold and leave-one-source-archive-out validation when at least two source cohorts are available.
- Conformal coverage is reported pooled, by battery, by fold, and by source cohort.
- The audit package includes rated-2-Ah versus first-valid-discharge target-normalization sensitivity.
- A completed 34-battery disposition can be supplied explicitly to the packager. It is validated and included without authorizing repair, filtering, causal attribution, or stronger predictive claims.
- An explicit external-validation gate remains blocked until a chemically and procedurally compatible independent cohort is supplied.

## Recommended execution

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force

.\scripts\run_nasa_pcoe_battery_pipeline.ps1

.\scripts\package_nasa_pcoe_full_audit.ps1 `
  -DispositionInput ".\outputs\nasa_protocol_review_disposition_completed.csv"
```

The pipeline must be rerun before final packaging so charge-feature semantics and all prediction artifacts are recomputed under the remediated code. Package-time correction of an older `signal_features.csv` is retained only as diagnostic evidence and does not retroactively change old model results.

## Scientific boundary

- Battery-disjoint and source-cohort-disjoint tests are internal NASA stress tests.
- The NASA cohorts share repository origin and do not constitute independent external validation.
- Target-normalization sensitivity does not identify an authoritative protocol-specific reference capacity.
- Passing tests and reproducible packaging establish software behavior, not degradation mechanism, causality, transferability, or engineering readiness.
