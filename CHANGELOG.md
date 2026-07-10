# Changelog

## v1.1

- Added the Battery Archive real-data case study as the second representative demonstration of the platform.
- Added Battery Archive zip inventory without extracting raw archives.
- Added filename metadata enrichment for source, chemistry, form factor, temperature, SOC window, and C-rate fields.
- Added cycle CSV schema audit and normalization for the two observed Battery Archive cycle-data schemas.
- Added row-level quality flags and conservative derived capacity metrics, including capacity retention and capacity-based SOH proxy.
- Added 80% and 70% threshold crossing proxy summaries with observed-censoring interpretation.
- Added compact series summary, data-quality summary, reliability group summary, and Battery Archive case-study documentation.
- Added a Windows pytest runner that uses a repository-local temporary directory.
- Stabilized repository documentation and navigation around core platform, case-study utilities, generated artifacts, and local raw-data policy.

This release does not add RUL prediction, degradation forecasting, physical degradation modeling, or production decision automation.

## v0.8

- Added the Kaggle NASA battery real-data case study as a representative demonstration of the platform.
- Built a full audit CSV and analysis-ready CSV split for Kaggle battery metadata-derived discharge summaries.
- Added quality flags for capacity-retention reference issues and retained the full audit table for review.
- Added raw discharge CSV scalar feature extraction for voltage, current, temperature, duration, and sample-count summaries.
- Added group-aware validation for simulation mode so `battery_id` can be used for train/test separation and group cross-validation.
- Added simulation comparison reporting for metadata-only, feature-enriched, random-split, and group-split runs.
- Added project audit, cleanup planning, and cleanup execution documentation.

## v0.7

- Added the real data readiness layer for dataset metadata, schema mapping, domain constraints, and validation summaries.
- Updated preprocessing behavior to preserve duplicate rows by default so repeated experiments or repeated measurements are not removed silently.
- Added simulation model validation diagnostics, including train/test metrics, overfitting diagnostics, cross-validation metrics, and residual plots.
- Added request/result schema groundwork for future Streamlit or API use without changing the existing CLI behavior.

## Next: v0.9

- Polish virtual experiment screening outputs and reports.
- Improve candidate condition ranking language and limitations.
- Add clearer constraints and out-of-distribution warning summaries.
- Improve comparison-friendly report generation.
- Prepare for a later Streamlit demo after the CLI workflow remains stable.
