# Reliability Case Study Planning

Status: `trust_boundary_complete` through v1.5.5.

This folder defines the generic reliability/risk use-case boundary and the
Backblaze 2013 trust-boundary case study. It does not contain downloaded
reliability raw data, survival estimates, RUL predictions, calibrated
operational probabilities, or production maintenance recommendations.

In short, this folder does not contain downloaded raw data.

## Primary Scope

The v1.5 primary question is:

> Can asset history and condition data available up to an observation cutoff be
> used to evaluate future failure risk or time-to-event while preserving
> censoring and temporal order?

This scope is broader than binary classification but narrower than production
maintenance decision automation. It is intended to support future readiness
audits, leakage checks, temporal and asset-disjoint validation design, and
trust-boundary reporting.

## Problem Taxonomy

- Binary failure classification: failure within a fixed horizon.
- Remaining useful life regression: remaining time or cycle target, with final
  event information separated from prediction-time features.
- Time-to-event / survival analysis: event time with right, interval, or
  administrative censoring where available.
- Recurrent event analysis: repeated failures after repair or replacement,
  requiring a clock-reset policy.
- Maintenance decision support: offline prioritization framing only, not causal
  maintenance-effect estimation.
- Degradation trajectory analysis: sensor, capacity, wear, or health-index
  trajectories using only past measurements.

Contract scaffolding was implemented in v1.5.1. v1.5.2 added a bounded
Backblaze access gate and compact readiness audit. v1.5.3 added full-year
streaming normalization and event/censoring readiness reassessment. v1.5.4
added fixed 7-day diagnostic classification baselines. v1.5.5 closes the case
study with model eligibility and trust-boundary reporting.

## Dataset Candidate Decision

Candidate assessment lives in
[`dataset_candidates_v1_5.csv`](dataset_candidates_v1_5.csv).

Current decision:

- `backblaze_drive_stats`: `conditional_primary_candidate`
- `nasa_cmapss`: `operational_backup_candidate`
- `nasa_n_cmapss`: `secondary_fixture`
- `nasa_ims_bearing`: `secondary_fixture`
- `femto_pronostia`: `secondary_fixture`
- `uci_ai4i_2020`: `secondary_fixture`
- `battery_archive_existing`: `rejected`
- `uci_secom_existing`: `rejected_for_primary`

The Backblaze drive data is the preferred reliability candidate because it has
explicit asset identifiers, repeated observations, dates, condition variables,
and observed failures. It was not downloaded in v1.5.1. v1.5.2 verified
bounded access and file structure for the 2013 archive. v1.5.3 then processed
the full archive into a local-only analysis-ready trajectory table and compact
readiness summaries.

NASA C-MAPSS is retained as a benchmark backup for RUL methodology, but it is a
simulation benchmark rather than real-world operational evidence.

## v1.5.2 Access Gate and Readiness Result

Backblaze remains the active candidate after the v1.5.2 bounded access gate.
The script uses the official `data_2013.zip` archive, keeps the raw ZIP
local-only under `data/raw/reliability/backblaze_drive_stats/`, lists archive
members without full extraction, and reads five representative daily CSV
members for schema/readiness reconnaissance.

Compact observed results:

- bounded sample rows: 96,838
- bounded sample columns: 86
- independent assets: 28,767
- observed failure rows: 10
- selected primary task: `binary_horizon_failure`
- readiness verdict: `conditionally_ready`

Survival, RUL regression, and recurrent event analysis remain `not_ready`.
Censoring is interpreted conservatively as administrative last observation in
the bounded sample, not as a completed operational survival audit.

## v1.5.3 Full-Year Normalization Result

The v1.5.3 full-year audit streams the official 2013 Backblaze archive member
by member. It does not extract raw daily CSV files and does not commit the raw
archive or the large row-level analysis-ready table.

Compact observed results:

- valid daily CSV files: 266
- excluded archive members: 269
- date range: 2013-04-10 to 2013-12-31
- normalized rows: 5,091,501
- assets: 29,072
- multi-observation assets: 29,058
- failure rows / failed assets: 724 / 724
- post-failure anomaly assets: 7
- compatible schema signatures: 1
- SMART feature columns: 80
- selected primary task: `binary_horizon_failure`
- recommended horizon / lookback: 7 days / 7 days
- overall readiness verdict: `conditionally_ready`

The 7-day horizon has 4,892,482 eligible prediction rows and 4,797 positive
labels. Asset-disjoint, chronological, and combined asset-disjoint future
splits are `conditionally_ready`; random row split remains an optimistic or
prohibited reference, not primary evidence.

Censoring is still uncertain: non-failure asset exits may reflect administrative
end of archive, removal, retirement, or other unobserved causes. Survival
analysis is therefore only conditionally ready for a future survival-specific
censoring audit. RUL regression and recurrent event analysis remain `not_ready`.

## v1.5.4 7-Day Classification Baseline Result

v1.5.4 uses the v1.5.3 readiness gate to run fixed classical baselines for a
7-day failure-risk task. The task is retrospective and offline:

- horizon: 7 days
- lookback: 7 calendar days including the prediction origin day
- eligible origins: 4,892,482
- positive labels: 4,797
- positive assets: 706
- post-event excluded rows: 904
- right-edge excluded rows: 198,115

Primary evidence uses asset-disjoint, final-month time-aware, and combined
asset-disjoint future validation. Stratified random row split is reported only
as an optimistic reference because same-asset and adjacent-origin dependence can
inflate results.

Fixed baselines include dummy prior, logistic regression, random forest, and
histogram gradient boosting. Two predeclared feature sets are evaluated:
conservative SMART-only aggregates and SMART plus safe operational metadata.
All non-dummy predictive models use deterministic training-only subsampling
under the resource policy; test partitions are not subsampled.

Compact observed results:

- valid metric rows: 64
- best primary median PR-AUC: 0.0998
- best combined asset/time PR-AUC: 0.1119
- reference combined top 1% precision / lift / failed-asset capture:
  0.0703 / 62.9x / 0.846
- representative model: `none_selected`

The result is a diagnostic screening signal only. It is not a calibrated
failure probability, maintenance recommendation, root-cause explanation,
survival model, RUL model, or production alert system.

## v1.5.5 Trust-Boundary Closeout

v1.5.5 reads existing compact v1.5.4 artifacts only. It does not retrain
models, change thresholds, run SHAP, fit survival models, estimate RUL, or
regenerate row-level predictions.

Closeout result:

- row prevalence baseline: 0.000980
- positive asset prevalence: 0.0243
- v1.5.4 input model statuses: `candidate_for_further_validation=12`,
  `diagnostic_only=4`
- v1.5.5 trust eligibility statuses: `descriptive_only=4`,
  `diagnostic_only=12`
- representative model: `none_selected`
- release readiness: `release_ready` as a bounded offline trust-boundary
  demonstration

The top-risk result is interpreted as retrospective ranking concentration. It
is not a 7% calibrated failure probability, not 84.6% prediction accuracy, and
not a production alert threshold. Resource-limited training, repeated daily
origins, uncertain censoring, and missing external validation prevent
representative-model selection.

## Contract and Leakage Map

- [`reliability_contract_v1_5.json`](reliability_contract_v1_5.json) defines
  required and preferred reliability fields, censoring/event policy, validation
  hierarchy, metrics, trust vocabulary, allowed claims, prohibited claims, and
  stop conditions.
- [`leakage_map_v1_5.csv`](leakage_map_v1_5.csv) lists common reliability
  leakage patterns such as final cycle count, future degradation windows,
  full-lifetime normalization, random row splits mixing assets, and post-event
  maintenance actions.
- [`acquisition_spec_v1_5.json`](acquisition_spec_v1_5.json) and
  [`acquisition_manifest_v1_5.json`](acquisition_manifest_v1_5.json) record
  the v1.5.2 Backblaze access gate, source metadata, SHA policy, local-only raw
  archive policy, and compact readiness result.
- [`normalization_spec_v1_5.json`](normalization_spec_v1_5.json) and
  [`full_year_manifest_v1_5.json`](full_year_manifest_v1_5.json) record the
  v1.5.3 full-year member inclusion, schema harmonization, local analysis-ready
  output policy, event/censoring treatment, and readiness conclusion.
- [`classification_spec_v1_5.json`](classification_spec_v1_5.json) records the
  v1.5.4 fixed 7-day horizon/lookback, feature sets, validation hierarchy,
  repeated-origin weighting, resource policy, metrics, thresholds, local
  outputs, allowed claims, and prohibited claims.
- [`trust_spec_v1_5.json`](trust_spec_v1_5.json) records the v1.5.5 model
  eligibility, representative-model, top-risk, threshold, calibration,
  survival/RUL, explainability, and applicability boundaries.
- [`case_study.md`](case_study.md) is the narrative Backblaze reliability
  closeout report.

## Relationship to Existing Case Studies

Battery Archive v1.1 already covers battery degradation trajectories and
capacity-derived threshold proxies. v1.5 should avoid simply repeating that
case study.

Smart Factory v1.4 covers process-quality classification with time-aware
validation and trust-boundary closeout, but SECOM lacks explicit asset,
maintenance, and recurrent-event structure. v1.5 should focus on asset-level
reliability data rather than another process-quality table.

## Non-Goals

v1.5.1 does not perform:

- data download or API access
- model training
- survival modeling
- Weibull fitting
- RUL regression
- hyperparameter tuning
- feature engineering from actual raw data
- SHAP or causal maintenance analysis
- dashboarding
- main merge, tag, or release

v1.5.4 performs fixed classical binary classification baselines only. v1.5.5
performs trust-boundary closeout only. v1.5 still does not perform survival
modeling, RUL regression, Weibull fitting, hyperparameter tuning, SHAP, causal
maintenance analysis, calibrated production probability estimation, or
production maintenance decision automation.

## Roadmap

- v1.5.1: generic reliability contract, candidate assessment, leakage map, and
  readiness scaffold.
- v1.5.2: dataset access gate for Backblaze, bounded schema reconnaissance,
  leakage-schema audit, and compact readiness outputs.
- v1.5.3: full-year analysis-ready normalization, event/censoring integrity,
  horizon/lookback feasibility, split feasibility, and task readiness
  reassessment.
- v1.5.4: fixed 7-day asset/time-aware classification baselines and diagnostic
  claim-boundary outputs.
- v1.5.5: trust-boundary closeout and conservative documentation.
