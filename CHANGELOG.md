# Changelog

## Unreleased

- No changes yet.

## v2.1

- Added a local-only SQLite run/artifact registry scaffold under
  `outputs/platform_registry/` for run/report manifest ingestion, artifact
  instance records, lineage, reproducibility status, run comparison,
  validation, and export.
- Added registry CLI commands and optional `--register-run` support for
  dry-run, controlled verify execution, and read-only report generation.
- Kept registry operations metadata-only: no acquisition execution, model
  training, raw data reads, scientific recomputation, canonical output
  overwrite, network access, or arbitrary execution.
- Added bounded scientific execution closeout with scientific trust-boundary
  evaluation, constraint-role classification, feature-candidate metadata
  registry, claim-boundary persistence, schema v4 registry tables, and
  deterministic scientific registry snapshots.
- Added CLI commands for scientific trust evaluation, feature-candidate
  inspection, feature eligibility, claim boundaries, trust export, and
  scientific trust validation.
- Documented that scientific execution supports bounded consistency evidence
  and feature-candidate metadata only; it does not perform feature generation,
  model training, phase identification, SHAP, DFT/FEM/CFD, or production
  scientific decisions.

## v2.0

- Added an additive platform core with explicit plugin, adapter, artifact,
  validation-policy, trust-policy, execution-policy, and case-study registries.
- Added lightweight JSON pipeline config validation, dry-run planning, and
  local run-manifest writing without arbitrary imports, shell commands,
  network access, raw-data access, or model training.
- Added safe thin adapter metadata for selected trust stages while keeping
  Materials Project and Smart Factory execution blocked.
- Added controlled `verify` execution for the Reliability trust closeout only,
  with side-effect accounting and protected compact artifact SHA checks.
- Added a generic case-study interface and metadata-only new-domain onboarding
  validation.
- Added read-only JSON/Markdown platform report generation from registries and
  tracked compact artifacts under local-only `outputs/platform_reports/`.
- Preserved all existing v1.x scripts, output schemas, case-study docs, and raw
  / local-only artifact policies.

This release does not add acquisition orchestration, full-pipeline execution,
model training, raw-data reads, scientific result recomputation, dashboard/UI,
PDF reporting, production deployment, or new scientific claims.

## v1.5

- Added a generic reliability/risk contract covering asset identity,
  event/censoring policy, leakage boundaries, validation hierarchy, metrics,
  model-status vocabulary, and prohibited claims.
- Assessed public reliability dataset candidates and selected Backblaze Hard
  Drive Test Data 2013 as the conditional primary case study, with NASA
  C-MAPSS retained as a benchmark backup.
- Added a bounded Backblaze access gate, source SHA policy, archive inventory,
  schema reconnaissance, and readiness summaries while keeping the raw archive
  local-only.
- Added full-year streaming normalization for the Backblaze 2013 archive,
  event/censoring integrity summaries, horizon/lookback feasibility, split
  feasibility, SMART feature inventory, and compact readiness outputs.
- Added fixed 7-day horizon / 7-day lookback asset/time-aware classical
  classification baselines with train-only preprocessing, asset-disjoint,
  time-aware, combined asset/time validation, and random-row optimistic
  reference.
- Added compact classification metrics, split diagnostics, model summaries,
  top-risk diagnostics, threshold diagnostics, error-structure summaries, and
  conservative classification conclusions.
- Added trust-boundary closeout outputs for model eligibility, validation
  stability, weighting dependence, resource boundaries, operational boundaries,
  claim boundaries, release readiness, and case-study documentation.
- Documented that no representative model is selected: v1.5 supports
  retrospective offline diagnostic ranking only, not production alerts.

This release does not add survival modeling, RUL regression, Weibull fitting,
hyperparameter tuning, SHAP, causal root-cause analysis, calibrated failure
probability claims, or maintenance automation.

## v1.4

- Added the Smart Factory process-quality contract and leakage map.
- Recorded Bosch as a conditional primary candidate and activated UCI SECOM as
  the operational fallback when Bosch access, terms, and file inventory could
  not be verified locally.
- Added SECOM acquisition provenance, raw SHA checks, schema inventory, and
  readiness summaries while keeping raw data local-only.
- Added row-position SECOM analysis-ready normalization with explicit
  day-first timestamp parsing, source-order alignment, target mapping, temporal
  integrity checks, feature-quality inventory, and SPC/split feasibility
  summaries.
- Added fixed classical time-aware classification baselines for SECOM with
  train-only preprocessing, chronological primary validation, stratified random
  optimistic reference, PR-AUC primary metrics, threshold diagnostics, Brier
  score diagnostics, random-vs-temporal gap summaries, and conservative model
  status boundaries.
- Added trust-boundary closeout artifacts for model eligibility, temporal
  stability, operational boundary, claim boundary, release readiness, and
  case-study documentation.
- Documented that v1.4.4 outputs are diagnostic-only: no representative
  production model is selected, group-aware evidence is unavailable, and
  capability analysis is not ready because specification limits are absent.

This release does not add deep learning, SHAP, SMOTE, causal root-cause
analysis, calibrated production probability claims, real-time control,
equipment-specific generalization, or production decision automation.

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
