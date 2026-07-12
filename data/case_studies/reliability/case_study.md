# Backblaze Reliability Case Study

## 1. Executive Summary

This case study uses Backblaze Hard Drive Test Data 2013 to demonstrate an
asset-level reliability validation and trust-boundary workflow. It is a
retrospective offline diagnostic study, not a production drive-failure alert
system.

The workflow covers source access, full-year streaming normalization,
event/censoring integrity, 7-day horizon and 7-day lookback feasibility,
asset/time-aware fixed classical baselines, and conservative model-eligibility
closeout.

Final closeout:

- representative model: `none_selected`
- v1.5 release readiness: `release_ready` as a bounded trust-boundary case
  study
- allowed use: retrospective offline failure-risk ranking diagnostic
- prohibited use: calibrated failure probability, maintenance automation,
  survival/RUL claim, root-cause claim, or production deployment claim

## 2. Reliability Question

Primary question:

> Can drive history and SMART condition data available up to an observation
> cutoff be used to rank observed 7-day failure risk while preserving asset
> identity and chronological order?

This can support offline validation of a diagnostic ranking workflow. It cannot
prove causal root cause, survival probability, RUL, or maintenance intervention
effect.

## 3. Dataset Candidate Decision

Backblaze was selected as the v1.5 active reliability candidate because it has
explicit asset identifiers, repeated daily observations, observed failures, and
SMART condition variables. NASA C-MAPSS remains a benchmark backup but is a
simulation benchmark rather than real operational fleet evidence.

Battery Archive and UCI SECOM were rejected as primary v1.5 datasets because
they are already covered by earlier case studies and do not add the same
asset-level reliability structure.

## 4. Backblaze Provenance

The source archive is the official Backblaze 2013 hard-drive data archive.

- raw archive: `data/raw/reliability/backblaze_drive_stats/data_2013.zip`
- raw archive SHA-256:
  `7f5a53e79b16e695b4b034955806bb3bb194534b169f6eca460dfd3dc48096fe`
- raw archive policy: local-only, not committed
- row-level normalized and prediction files: local-only

Tracked artifacts are compact inventories, manifests, summaries, and trust
tables.

## 5. Archive and Schema Structure

The full-year audit observed:

- valid daily CSV files: 266
- date range: 2013-04-10 to 2013-12-31
- normalized rows: 5,091,501
- schema signatures: 1
- SMART feature columns: 80
- conservative usable SMART candidates: 5

The full analysis-ready table is generated locally and is not tracked.

## 6. Asset Trajectories

The normalized dataset contains:

- assets: 29,072
- multi-observation assets: 29,058
- median observations per asset: 210
- duplicate asset/date rows: 0

Daily prediction origins are not independent samples. Adjacent origins from the
same drive can be highly correlated, so row counts overstate effective sample
size. v1.5.4 therefore reports both asset-balanced and raw-row weighting.

## 7. Event and Censoring Interpretation

The observed `failure=1` row is treated as a terminal-event candidate.

Observed event/censoring audit:

- failure rows: 724
- failed assets: 724
- post-failure anomaly assets: 7
- failure assets with no prior history: 6
- repeated event assets: 0

Non-failure exits are not interpreted as healthy retirements. They may reflect
administrative end of archive, removal, retirement, replacement, or unknown
causes. This prevents operational survival probability claims.

## 8. Horizon and Lookback Selection

v1.5.4 fixed the primary task before modeling:

- horizon: 7 days
- lookback: 7 calendar days including the prediction origin day
- eligible origins: 4,892,482
- positive labels: 4,797
- positive assets: 706
- post-event excluded rows: 904
- right-edge excluded rows: 198,115

The label is positive when the first observed failure occurs after the
prediction origin and within the next 7 days. Same-day failure rows,
post-failure rows, and origins without complete 7-day future visibility are
excluded.

## 9. Feature Policy

The primary feature set uses only target-independent conservative SMART feature
candidates identified during v1.5.3.

Predeclared feature sets:

- `smart_only_conservative`
- `smart_plus_safe_operational_metadata`

Safe metadata includes drive age, observation density, capacity, and train-only
model category encoding. Raw `serial_number`, future observations,
full-lifetime metadata, event date, censoring date, and target-derived fields
are prohibited prediction features.

## 10. Validation Hierarchy

Primary evidence:

- asset-disjoint validation
- time-aware final-month validation
- combined asset-disjoint future validation

Secondary reference:

- stratified random row split

The random split is optimistic reference only because it can mix the same drive
and adjacent daily origins across train/test partitions.

## 11. Repeated-Origin Weighting

v1.5.4 reports both:

- asset-balanced weighting
- raw-row weighting

Raw-row gains are interpreted cautiously because long-lived assets and repeated
daily origins can dominate the objective. v1.5.5 records
`raw_row_dependency_detected` in the trust summary.

## 12. Resource-Aware Training

The local feature dataset has roughly 4.9M eligible origins, so non-dummy
models use deterministic training-only subsampling under the predeclared
resource policy. Test sets are never subsampled.

This is explicitly recorded as `resource_limited_subsampled_training` and is a
reason not to promote any model as representative.

## 13. Models

Fixed classical baselines:

- DummyClassifier prior
- LogisticRegression
- RandomForestClassifier
- HistGradientBoostingClassifier

No hyperparameter search, SMOTE, SHAP, survival model, RUL model, Weibull fit,
or deep learning is used.

## 14. Classification Results

Compact v1.5.4 results:

- valid metric rows: 64
- best primary median PR-AUC: 0.0998
- best combined asset/time PR-AUC: 0.1119
- v1.5.4 model statuses: `candidate_for_further_validation=12`,
  `diagnostic_only=4`
- representative model: `none_selected`

v1.5.5 applies a stricter trust-boundary review:

- v1.5.5 eligibility statuses: `descriptive_only=4`, `diagnostic_only=12`
- representative model: `none_selected`

## 15. Random vs Primary Validation

Random row split is not primary evidence. Some random-reference results are
higher than asset/time-aware primary results, which is consistent with possible
same-drive dependence, adjacent-origin correlation, drive-model proxy behavior,
or temporal distribution shift.

The analysis does not assert a single causal reason for this gap.

## 16. Top-Risk Concentration

The reference combined top 1% row is:

- model: `random_forest`
- feature set: `smart_plus_safe_operational_metadata`
- weighting: `asset_balanced`
- precision: 0.0703
- lift over prevalence: 62.9x
- failed-asset capture: 0.846

This indicates retrospective ranking concentration. It is not 84.6% prediction
accuracy, not a 7% calibrated failure probability, and not a production alert
threshold. The top 1% still contains many false-positive rows and repeated
alerts can occur for the same asset.

## 17. Threshold Limitations

The 0.5 threshold is recorded because it was predeclared. It is not tuned using
test labels and is not an operational threshold.

The threshold outputs are diagnostic only. Rare-event class imbalance makes
accuracy and a default 0.5 cutoff unsuitable as the main evidence.

## 18. Calibration Limitations

Brier score and log loss are diagnostics only.

No calibration model, independent calibration period, or prospective validation
is used. Scores must be described as uncalibrated relative ranking scores, not
failure probabilities.

## 19. Model Eligibility

v1.5.5 eligibility applies these boundaries:

- dummy rows: `descriptive_only`
- non-dummy rows: `diagnostic_only`
- representative model: none

The non-dummy models show diagnostic ranking signal, but they are not promoted
because the evidence is resource-limited, repeated-origin dependent, not
externally validated, not calibrated, and not threshold-ready.

## 20. Why No Representative Model Was Selected

No representative model is selected because:

- all non-dummy results are resource-limited/subsampled training results
- random row split can be optimistic and is not primary evidence
- repeated daily origins reduce effective sample independence
- raw-row weighting may reflect long-lived asset dominance
- 0.5 threshold results are not operationally viable
- scores are not calibrated probabilities
- censoring and non-failure exit reasons are uncertain
- no external year, fleet, or company holdout is validated

## 21. Survival and RUL Limitations

Survival and RUL are deferred/not ready.

Reasons:

- non-failure exit reasons are not directly observed
- informative censoring risk remains
- operational survival distribution is not established
- RUL target construction would require a separate leakage-controlled design
- recurrent-event semantics are not supported by the observed failure rows

## 22. Trust Boundary

Allowed:

- retrospective offline failure-risk ranking diagnostic
- asset/time-aware validation framework demonstration
- top-risk concentration as a candidate screening signal with false-positive
  burden disclosed

Not allowed:

- production-ready failure prediction
- calibrated 7-day failure probability
- maintenance automation or replacement recommendation
- survival probability or RUL estimate
- SHAP/root-cause explanation
- generalization beyond Backblaze 2013

## 23. Allowed Claims

This case study may claim:

- Backblaze 2013 can be normalized into an asset-level reliability table.
- A leakage-controlled 7-day horizon / 7-day lookback task can be constructed.
- Classical baselines show retrospective top-risk concentration under
  asset/time-aware validation.
- The project preserves negative and limited evidence through a trust-boundary
  closeout.

## 24. Prohibited Claims

This case study must not claim:

- accurate hard-drive failure prediction
- calibrated operational failure probability
- guaranteed early warning
- maintenance-effect estimation
- automatic replacement decision support
- root-cause discovery
- survival/RUL modeling
- robust cross-fleet or cross-year generalization

## 25. Reproducibility

Compact tracked artifacts include:

- acquisition and normalization specs/manifests
- schema, event, censoring, horizon, lookback, and split summaries
- classification metrics, threshold, top-risk, and error-structure summaries
- trust summary, model eligibility, operational boundary, claim boundary, and
  closeout conclusion

The local raw archive and large row-level CSVs are intentionally not tracked.

## 26. Local-Only Artifact Policy

Local-only artifacts:

- `data/raw/reliability/backblaze_drive_stats/data_2013.zip`
- `data/processed/reliability_v1_5_backblaze_analysis_ready.csv`
- `data/processed/reliability_v1_5_horizon_7d_lookback_7d_dataset.csv`
- `data/processed/reliability_v1_5_classification_predictions.csv`

Tracked artifacts are compact CSV/JSON/Markdown reproducibility outputs.

## 27. Future Data Requirements

Further evidence would require:

- multiple years
- external data-center holdout
- drive retirement/removal reason
- maintenance and replacement logs
- confirmed failure mode
- consistent SMART semantics
- firmware/environment/load variables
- independent calibration period
- inspection and false-alert cost model
- prospective deployment study

Without these data, additional tuning is lower priority than improving the
validation and provenance evidence.

## 28. Final Conclusion

The Backblaze v1.5 case study is release-ready as a trust-boundary
demonstration. It shows that the platform can perform asset-level reliability
data readiness, leakage-aware label construction, asset/time-aware baseline
validation, compact result reporting, and conservative model eligibility.

It does not select a representative predictive model and does not justify
production maintenance decisions.
