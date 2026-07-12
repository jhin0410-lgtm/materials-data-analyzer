# Reliability v1.5 Plan

Status: `contract_stage`; v1.5.2 access gate is `access_gate_complete`
and v1.5.3 full-year normalization/readiness reassessment is
`conditionally_ready` for a future binary horizon failure-risk workflow.

v1.5 starts a generic reliability/risk workflow for asset-level engineering
data. The tracked repository does not contain raw downloads, trained models,
survival curves, RUL estimates, or production maintenance readiness claims.

## Motivation

The project already includes Battery Archive degradation analysis and Smart
Factory time-aware classification. v1.5 adds a reliability-specific contract
for assets, events, censoring, maintenance history, degradation trajectories,
and trust-boundary reporting.

The guiding question is:

> Can asset history and condition data available up to an observation cutoff be
> used to evaluate future failure risk or time-to-event while preserving
> censoring and temporal order?

## Problem Taxonomy

1. Binary failure classification: failure within a fixed horizon, such as 7 or
   30 days.
2. Remaining useful life regression: remaining cycle or time, with final event
   data used only for target construction.
3. Time-to-event / survival analysis: event time with right, interval, or
   administrative censoring where available.
4. Recurrent event analysis: repeated events for the same asset, requiring a
   repair/replacement and clock-reset policy.
5. Maintenance decision support: offline prioritization framing, not causal
   maintenance-effect estimation.
6. Degradation trajectory analysis: condition or health trajectories with
   future-window leakage prevention.

The primary v1.5 scope is reliability readiness for future failure risk or
time-to-event analysis. The other tasks remain future extensions.

## Scope Boundary

Included:

- asset-level longitudinal data
- event and censoring definitions
- prediction origin and horizon policy
- temporal validation
- asset/group-aware validation
- train-only preprocessing
- failure incidence and censoring distribution
- maintenance history audit
- degradation trajectory availability
- offline reliability decision-support framing
- model eligibility and trust-boundary vocabulary

Excluded:

- causal maintenance-effect estimation
- automatic maintenance scheduling
- safety-critical control
- guaranteed RUL
- digital twin claims
- physical crack-growth or finite-element simulation
- assuming a Weibull law always fits
- production deployment
- regulatory certification
- calibrated operational probability claims without validation

## Dataset Candidate Assessment

Candidate details are tracked in
[`../data/case_studies/reliability/dataset_candidates_v1_5.csv`](../data/case_studies/reliability/dataset_candidates_v1_5.csv).

| Dataset | Status | Rationale |
| --- | --- | --- |
| Backblaze Hard Drive Test Data | `conditional_primary_candidate` | Real longitudinal asset data with serial numbers, daily dates, SMART attributes, and failure flags. Access terms, file inventory, and censoring definitions require v1.5.2 verification. |
| NASA C-MAPSS | `operational_backup_candidate` | Strong RUL benchmark with unit/cycle structure, but it is a simulation benchmark and not real operational evidence. |
| NASA N-CMAPSS | `secondary_fixture` | Useful larger benchmark for later work, but too model-oriented and large for the initial contract stage. |
| NASA IMS Bearing | `secondary_fixture` | Real accelerated bearing trajectories, but limited independent asset support and no realistic fleet censoring. |
| FEMTO-ST PRONOSTIA | `secondary_fixture` | Known bearing PHM benchmark; source stability and redistribution terms require verification. |
| UCI AI4I 2020 | `secondary_fixture` | Small synthetic predictive-maintenance fixture; useful for tests, not longitudinal reliability evidence. |
| Battery Archive | `rejected` | Already covered in the v1.1 battery degradation case study. |
| UCI SECOM | `rejected_for_primary` | Already covered in v1.4 and lacks asset-level reliability structure. |

Official or primary source pages used for candidate assessment include:

- Backblaze Hard Drive Test Data:
  <https://www.backblaze.com/cloud-storage/resources/hard-drive-test-data>
- NASA Prognostics Center of Excellence data repository:
  <https://www.nasa.gov/intelligent-systems-division/discovery-and-systems-health/pcoe/pcoe-data-set-repository/>
- FEMTO-ST PRONOSTIA / IEEE PHM 2012 data challenge:
  <https://www.femto-st.fr/en/Research-departments/AS2M/Research-groups/PHM/IEEE-PHM-2012-Data-challenge.php>
- UCI AI4I 2020 Predictive Maintenance Dataset:
  <https://archive.ics.uci.edu/dataset/601/ai4i+2020+predictive+maintenance+dataset>
- UCI SECOM:
  <https://archive.ics.uci.edu/dataset/179/secom>

Uncertain facts are explicitly retained: exact redistribution terms, current
file inventory, and dataset-specific censoring definitions must be checked in
an access gate before any primary dataset is promoted.

## v1.5.2 Access Gate Result

The v1.5.2 access gate used Backblaze Hard Drive Test Data as the active
candidate and kept NASA C-MAPSS as the operational backup. The bounded source
artifact is the official Backblaze `data_2013.zip` archive from the Backblaze
Hard Drive Test Data page. The raw archive remains local-only under
`data/raw/reliability/backblaze_drive_stats/` and is not tracked.

Observed bounded audit results:

- archive size: 80,983,520 bytes
- ZIP member count: 535, including macOS metadata artifacts
- selected CSV members for bounded readiness: 5
- bounded sample rows: 96,838
- bounded sample columns: 86
- independent assets in bounded sample: 28,767
- observed failure rows: 10
- selected primary task for the next phase: `binary_horizon_failure`
- overall readiness verdict: `conditionally_ready`

Task boundaries:

- `binary_horizon_failure`: `conditionally_ready`
- `terminal_event_prediction`: `conditionally_ready`
- `degradation_trajectory`: `conditionally_ready`
- `survival_time_to_event`: `not_ready` until full follow-up and censoring are audited
- `rul_regression`: `not_ready`
- `recurrent_event_analysis`: `not_ready`

This is still a readiness-stage result. It does not train a reliability model,
fit survival curves, estimate RUL, or make production maintenance claims.

## v1.5.3 Full-Year Normalization and Readiness Reassessment

v1.5.3 extends the bounded access-gate audit to the full 2013 Backblaze archive
without extracting the raw ZIP or loading the full year into memory at once. The
raw archive remains local-only, while compact inventories and summaries are
tracked for reproducibility.

Full-year observed results:

- ZIP members: 535
- valid daily CSV files: 266
- excluded members: 269 macOS metadata, hidden, malformed, or unsupported
  members
- date range: 2013-04-10 to 2013-12-31
- total normalized rows: 5,091,501
- total assets: 29,072
- multi-observation assets: 29,058
- failure rows: 724
- failed assets: 724
- schema signatures: 1 compatible source schema with 85 source columns
- SMART feature columns: 80
- usable SMART feature candidates under conservative availability checks: 5

Event and censoring findings:

- first observed `failure=1` is treated as the terminal event candidate
- 717 failed assets fail on their last observation
- 7 assets have post-failure observations and are retained only as diagnosed
  anomalies, not prediction features
- 6 failed assets have no previous history before the failure row
- non-failed exits are right-censoring candidates, but drive retirement,
  removal, and replacement reasons remain unknown
- censoring categories include `observed_failure`,
  `administrative_end_of_archive`, `lost_to_observation`,
  `single_observation_unknown`, and `post_failure_inconsistent`

Task readiness after the full-year audit:

- `binary_horizon_failure`: `conditionally_ready`
- `terminal_event_prediction`: `conditionally_ready`
- `degradation_trajectory`: `conditionally_ready`
- `survival_time_to_event`: `conditionally_ready`, but only with an explicit
  survival-specific censoring audit
- `rul_regression`: `not_ready`
- `recurrent_event_analysis`: `not_ready`

The selected primary task remains `binary_horizon_failure`. The recommended
initial horizon and lookback are both 7 days: the 7-day horizon has 4,892,482
eligible prediction rows, 4,797 positive labels, and 706 positive assets; the
7-day lookback has a 93.6% complete-window proportion. Asset-disjoint,
chronological, and combined asset-disjoint future splits are all
`conditionally_ready`; random row split remains prohibited as primary evidence.

The full analysis-ready table
`data/processed/reliability_v1_5_backblaze_analysis_ready.csv` is a generated
local-only artifact of about 1.42 GB. Compact summaries, manifests, and
inventory tables are the tracked reproducibility artifacts.

## v1.5.4 Fixed 7-Day Classification Baselines

v1.5.4 fixes the primary task to a 7-day horizon and 7-day lookback before
modeling. Prediction origins are drive observation dates. A positive label
means the first observed failure occurs after the origin and within the next 7
days. Same-day failure rows, post-failure rows, and origins without complete
7-day future visibility are excluded from prediction origins.

The local-only 7d/7d feature dataset contains:

- eligible origins: 4,892,482
- positive labels: 4,797
- positive assets: 706
- post-event excluded rows: 904
- right-edge excluded rows: 198,115
- local file: `data/processed/reliability_v1_5_horizon_7d_lookback_7d_dataset.csv`
  at about 2.56 GB

Feature sets were fixed before running models:

- `smart_only_conservative`: 7-day aggregates from the five target-independent
  conservative SMART candidates.
- `smart_plus_safe_operational_metadata`: the same SMART aggregates plus drive
  age, observation density/count metadata, `capacity_bytes`, and train-only
  model-category encoding.

Validation hierarchy:

- primary: asset-disjoint, final-month time-aware, and combined asset-disjoint
  future holdout
- secondary: stratified random row split as optimistic reference only
- repeated-origin policy: asset-balanced weighting is primary; raw row weighting
  is reported as a diagnostic comparison

Actual fixed-baseline results:

- valid metric rows: 64
- best primary median PR-AUC: 0.0998
- best combined asset/time PR-AUC: 0.1119
- best combined 1% top-risk failed-asset capture: 84.6% for the
  resource-limited random forest with SMART plus safe metadata
- random row reference is higher for some random-forest runs, consistent with
  possible same-asset dependence, adjacent-origin correlation, or temporal
  optimism
- all non-dummy predictive models used deterministic training-only subsampling
  under the v1.5.4 resource policy; full test partitions were not subsampled

No representative model is selected automatically. These results support a
retrospective offline diagnostic screening signal, not calibrated operational
probabilities, survival probabilities, root-cause claims, or production
maintenance decisions.

## Data Contract

The contract is
[`../data/case_studies/reliability/reliability_contract_v1_5.json`](../data/case_studies/reliability/reliability_contract_v1_5.json).

It separates:

- generic field requirements
- actual dataset availability, which will be assessed later
- event and censoring policy
- validation hierarchy
- metrics by task type
- trust and eligibility vocabulary
- allowed and prohibited claims
- stop conditions

The contract intentionally does not assume a survival-ready dataset unless
event and censoring definitions are available.

## Censoring and Event Policy

Reliability datasets must distinguish:

- right censoring
- left truncation
- interval censoring
- administrative censoring
- informative censoring risk
- competing failure modes
- recurrent events

Run-to-failure benchmarks can provide terminal events, but they may not
represent operational censoring distributions. If RUL labels are generated from
final failure cycle, that information is allowed only for target construction
and never as a prediction-time feature.

## Leakage Map

The leakage map is
[`../data/case_studies/reliability/leakage_map_v1_5.csv`](../data/case_studies/reliability/leakage_map_v1_5.csv).

High-risk examples include:

- post-failure measurements
- maintenance action after diagnosis
- replacement indicator
- final cycle count
- future degradation windows
- full-lifetime normalization
- asset maximum cycle
- target-derived health index
- test asset statistics in preprocessing
- random row splits mixing the same asset
- future observation in rolling features
- failure code assigned after teardown
- RUL derived using final event

## Validation Hierarchy

Primary evidence:

- asset-disjoint validation
- chronological validation
- combined asset-disjoint future validation

Secondary reference:

- random row split only as a prohibited or optimistic illustration

Claim scopes must be kept separate:

- interpolation within known assets
- future prediction for known assets
- generalization to unseen assets
- generalization to unseen fleet/site/regime

## Metrics Plan

Metrics are task-specific:

- Binary horizon risk: PR-AUC, ROC-AUC, Brier score, sensitivity,
  specificity, MCC, and calibration diagnostics.
- RUL regression: MAE, RMSE, domain-justified asymmetric early/late penalty,
  error by life fraction, and asset-level aggregation.
- Survival: concordance index, integrated Brier score, time-dependent AUC, and
  fixed-horizon calibration.

Ordinary regression metrics must not be used to silently ignore censoring.

## Readiness Scaffold

The generic scaffold lives in
[`../src/analyzers/reliability_readiness.py`](../src/analyzers/reliability_readiness.py).

It audits:

- required columns
- asset ID availability
- observations per asset
- timestamp/cycle parseability
- per-asset temporal order
- event indicator validity
- event/censoring timestamp consistency
- recurrent events
- trajectory length distribution
- asset/time/combined split feasibility
- degradation feature availability
- leakage-risk feature patterns

It does not fit models, import survival packages, or call external systems.

## Framework Reuse Audit

| Existing module or pattern | Decision | Notes |
| --- | --- | --- |
| `process_quality_readiness.py` | `reuse_with_generic_adapter` | Useful table-oriented readiness pattern, but reliability needs event/censoring semantics. |
| `grouped_regression_validation.py` | `reuse_with_generic_adapter` | Group-disjoint validation concepts are reusable later. |
| `temporal_classification_validation.py` | `reuse_with_generic_adapter` | Time-aware split and train-only preprocessing rules inform reliability validation. |
| `classification_trust.py` | `reuse_with_generic_adapter` | Trust-boundary vocabulary is reusable, but metrics and censoring rules differ. |
| provenance/artifact patterns | `reuse_as_is` | Local/tracked artifact split and source SHA policies should continue. |
| clean snapshot validation | `reuse_as_is` | Tests must pass without raw/local-only datasets. |
| generic base-class refactor | `defer_refactor` | Do not abstract until two or more reliability case studies confirm shared behavior. |

## Relationship to Existing Case Studies

Battery Archive v1.1 is a battery degradation case study with capacity-derived
threshold proxies. v1.5 should not repeat it as a primary dataset.

Smart Factory v1.4 is process-quality classification with time-aware
validation. SECOM has no explicit asset, maintenance, or recurrent-event
structure, so it is not a reliability primary dataset.

## Non-Goals

v1.5.1 did not do data download or API access. v1.5.2 performed a bounded
official-source access gate and schema/readiness audit. v1.5.3 performs
full-year normalization and readiness reassessment only. v1.5.4 performs fixed
classical binary classification baselines only. v1.5 still does not do survival
model fitting, Weibull fitting, RUL regression, hyperparameter tuning, SHAP,
causal maintenance analysis, calibrated production probability, automatic
maintenance decisions, dashboards, main merge, tag, or release.

## Stop Conditions

Future stages must stop or report `not_ready` when:

- no explicit asset identity exists
- no repeated observations exist
- no event or usable proxy exists
- no timestamp or cycle order exists
- label construction has unresolved leakage
- independent asset count is too small
- all trajectories are terminal but survival readiness is claimed
- license or redistribution terms are ambiguous
- source access fails
- the task duplicates an existing battery case study without added
  methodological value

## Roadmap

- v1.5.1: contract, candidate assessment, leakage map, and readiness scaffold.
- v1.5.2: Backblaze access gate, bounded schema reconnaissance, and readiness
  outputs; no modeling.
- v1.5.3: full-year normalization, event/censoring integrity audit, horizon and
  split feasibility reassessment; no modeling.
- v1.5.4: fixed 7-day asset/time-aware classification baselines and diagnostic
  claim-boundary outputs.
- v1.5.5: model eligibility, trust-boundary report, and negative-result
  closeout if needed.
