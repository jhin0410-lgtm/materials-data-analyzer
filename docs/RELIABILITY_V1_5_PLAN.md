# Reliability v1.5 Plan

Status: `contract_stage`.

v1.5 starts a generic reliability/risk workflow for asset-level engineering
data. It does not download data, train models, fit survival curves, or claim
production maintenance readiness.

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

v1.5.1 does not do data download, API access, model training, survival model
fitting, Weibull fitting, RUL regression, actual feature engineering,
hyperparameter tuning, SHAP, causal maintenance analysis, dashboards, main
merge, tag, or release.

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
- v1.5.2: access gate for the selected primary candidate; no modeling.
- v1.5.3: normalization and event/censoring audit if the access gate passes.
- v1.5.4: fixed baseline validation if readiness gates pass.
- v1.5.5: model eligibility, trust-boundary report, and negative-result
  closeout if needed.
