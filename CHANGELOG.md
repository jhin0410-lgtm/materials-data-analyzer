# Changelog

## v1.3

- Added exact-provenance Materials Project acquisition contracts and local artifact policy.
- Added an 838-row Materials Project validation dataset workflow with source/provenance checks.
- Added 60 composition-only descriptor generation, descriptor inventory, redundancy diagnostics, and composition ambiguity audit.
- Added group-aware baseline validation across random, reduced-formula, and chemical-system split strategies.
- Added local row-level validation predictions plus compact validation, split, model-comparison, and screening-metric summaries.
- Added applicability-domain diagnostics based on train-fold descriptor-space nearest-neighbor distance.
- Added error-structure summaries by domain distance, novelty, formula ambiguity, target stratum, and theoretical status.
- Added claim-boundary and trust-conclusion summaries documenting that no model is eligible for predictive interpretation.
- Deferred SHAP and physical feature-importance interpretation because model validity was not established.
- Documented v1.3 as a rigorous validation case study with weak/limited predictive results preserved.

This release does not claim accurate energy-above-hull prediction, novel stable
material discovery, DFT replacement, experimental synthesizability prediction,
calibrated uncertainty, production screening readiness, or robust unseen
chemical-system recommendation.

## v1.2

- Added the Materials Project pilot case study as a compact calculated-property screening demonstration.
- Added a Materials Project data audit for the local 50-row Fe/Si-containing multinary pilot artifact.
- Added a reconstructed query specification and provenance manifest without storing API credentials.
- Added a seven-column schema contract, conservative normalization workflow, and compact data-quality summary.
- Added a generic deterministic property-screening analyzer for transparent filtering and ranking of existing tabular properties.
- Added a Materials Project screening specification using energy-above-hull minimization as a descriptive ranking objective.
- Added Materials Project screening methodology, compact screening summary, pilot case-study documentation, and decision gate.
- Documented local/generated artifact policy for source, normalized, and full screening result CSVs.

This release does not add ML property prediction, novel materials discovery,
direct DFT calculation execution, synthesis feasibility validation,
experimentally verified recommendations, or generalizable model-performance
claims.

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
