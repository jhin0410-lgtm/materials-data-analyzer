# Smart Factory v1.4 Plan

Status: active case-study track through v1.4.4.

This document defines the v1.4 Smart Factory Process Quality Case Study
contract for `materials_data_analyzer`. v1.4.1 defined the contract, v1.4.2
activated the UCI SECOM fallback after the Bosch access gate was blocked,
v1.4.3 created the analysis-ready normalization and temporal/feature-quality
audit, and v1.4.4 adds fixed classical time-aware classification baselines.

The v1.4.4 modeling step is limited to offline diagnostic classification
baselines. It does not add deep learning, SHAP, causal interpretation,
calibrated production probability claims, dashboards, real-time control, or
production decision automation.

## Motivation

The core platform already supports CSV validation, EDA, process analysis,
reliability analysis, SPC, smart-factory log summaries, and virtual experiment
screening. v1.4 focuses on a manufacturing process-quality case study where
time, equipment, lot, product, recipe, and downstream quality timing matter.

The first step is not modeling. The first step is to define the analysis
question, dataset contract, leakage boundaries, validation hierarchy, and data
readiness checks.

## Business Question

Can process anomalies, yield shifts, and defect risk be detected using process
logs while preserving time, lot, equipment, and recipe structure for offline
manufacturing decision support?

Included scope:

- Process state monitoring
- SPC and process capability readiness
- Equipment, line, lot, batch, product, recipe, and time-unit analysis
- Drift and anomaly screening
- Process-to-quality relationship analysis
- Offline defect or yield risk estimation
- Human review prioritization
- Limited what-if or virtual screening as a screening aid

Excluded scope:

- Real-time PLC control
- Automatic process control
- Causal root-cause proof
- Digital twin claims
- Physics simulation claims
- Production deployment claims
- Safety-critical control
- Automatic decisions without human review

## Dataset Candidate Comparison

No data was downloaded for this contract stage. The table below is based on
public dataset pages, competition descriptions, and cited repository metadata.
Uncertain fields are marked as uncertain rather than inferred.

| Dataset | Status | Public/legal usability | Scale | Time/order info | Equipment/line | Lot/batch/product | Process variables | Quality target | Missingness / imbalance | Validation value | SPC/capability value | Reproducibility risk |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Bosch Production Line Performance | conditional_primary_candidate | Publicly listed Kaggle competition; actual access, competition terms, license/redistribution scope, and file inventory are not yet verified | About 1.18M training rows; many numeric, categorical, and date features reported in public descriptions | Date-style station measurements | Strong line/station encoded feature names | Product identity partly implicit; lot/batch unclear | Strong manufacturing measurements | Binary internal failure response | Very large and highly imbalanced; missingness likely meaningful | Strong group/time design potential if date/station structure is handled carefully | Good anomaly/drift potential; capability requires spec limits not present | Large files, Kaggle account/terms, file inventory, and feature semantics are risks |
| UCI SECOM | operational_backup_candidate | CC BY 4.0 on UCI | 1,567 rows, 591 features | Timestamp column present | Equipment/line not explicit | Lot/product not explicit | Semiconductor process measurements | Pass/fail label | Missing values; likely class imbalance | Good backup for process-to-quality validation, weak group structure | SPC possible for process variables; capability needs external spec limits | Stable UCI source, compact |
| UCI AI4I 2020 Predictive Maintenance | secondary_synthetic_fixture | CC BY 4.0 on UCI | 10,000 rows, 14 columns | Sequential UDI/order but synthetic | Machine state implied, not real line | Product ID and type present | Temperatures, speed, torque, tool wear | Failure labels and failure modes | No missing values; synthetic imbalance | Good synthetic fixture for tests and examples, not real-world evidence | Useful for readiness/SPC examples with synthetic assumptions | Synthetic by design |
| Tennessee Eastman process dataset | secondary_synthetic_fixture | MIT-licensed GitHub dataset | Multiple simulated process runs and faults | Time-series observations | Process variables and manipulated variables | Batch/fault run structure | Rich multivariate process control variables | Fault indicators, operating modes | Designed simulation; no real product quality target | Strong drift/anomaly/process-monitoring fixture | Strong SPC/control-chart demonstration value; capability needs declared specs | Simulated process, Excel/CSV handling details |
| UCI Steel Plates Faults | rejected_for_primary | CC BY 4.0 on UCI | 1,941 rows, 27 features | No explicit time/order | No equipment/line | No lot/batch/product | Image/geometry-derived defect features, not process logs | Seven steel fault classes | No missing values; class distribution should be audited | Useful quality classification dataset but weak process validation structure | Weak SPC/capability fit because process-time context is absent | Stable UCI source but not aligned with v1.4 goal |

### Source References

- Bosch Production Line Performance: Kaggle competition page and public
  competition write-ups describing production-line measurements, numeric,
  categorical, and date files.
- UCI SECOM: <https://archive.ics.uci.edu/dataset/179/secom>
- UCI AI4I 2020 Predictive Maintenance:
  <https://archive.ics.uci.edu/dataset/601/ai4i+2020+predictive+maintenance+dataset>
- Tennessee Eastman process dataset:
  <https://github.com/mv-per/tennessee-eastman-dataset>
- UCI Steel Plates Faults:
  <https://archive.ics.uci.edu/dataset/198/steel+plates+faults>

## Conditional Candidate and Fallback

Conditional primary candidate: Bosch Production Line Performance.

Rationale: Bosch appears closest to the intended process-quality setting based
on public descriptions of manufacturing production-line structure, date-like
measurements, process features, and downstream failure labels. It also appears
large enough for time-aware and group-aware validation. However, Bosch is not
yet an active primary dataset because actual access, competition terms,
license/redistribution scope, file inventory, and schema details have not been
verified.

Operational backup candidate: UCI SECOM.

Rationale: SECOM is compact, public, clearly licensed, semiconductor-related,
and includes many process measurements with a timestamp and pass/fail label.
Its weaknesses are limited explicit equipment, lot, batch, product, and recipe
structure.

Synthetic secondary fixtures: UCI AI4I and Tennessee Eastman.

Rationale: Synthetic fixtures are useful for unit tests, SPC readiness checks,
and drift/anomaly examples. They should not be presented as substitutes for
real-world manufacturing validation.

Rejected for v1.4 primary: UCI Steel Plates Faults.

Rationale: It is a useful public quality-classification dataset, but it lacks
the time, equipment, lot, and process-log structure required for the v1.4
process-quality contract.

### Dataset Status Transition

Bosch can be promoted only through the following access gate:

```text
conditional_primary_candidate
-> access_verified
-> terms_verified
-> schema_verified
-> readiness_verified
-> active_primary
```

If access, terms, or schema verification fails, the Bosch candidate should move
to `blocked` or `rejected`, and the SECOM fallback path should be activated.

## Unit of Analysis

The preferred unit of analysis is one produced part, wafer, process
observation, batch observation, or inspected unit that can be linked to:

- Process observations available before a prediction horizon
- Equipment, line, lot, batch, product, or recipe context where available
- Downstream quality outcome and quality measurement timing

If the unit of analysis cannot be identified, the case study should stop or be
re-scoped as a descriptive dataset audit.

## Process-Quality Schema

The machine-readable contract lives at:

```text
data/case_studies/smart_factory/process_quality_contract_v1_4.json
```

Required or preferred schema concepts include:

- Unit of analysis
- Prediction horizon
- Observation timestamp or stable process order
- Quality measurement timestamp
- Equipment, line, lot, batch, product, and recipe identifiers
- Process feature families
- Quality target families
- Censoring and delayed-quality policy
- Missingness, duplicate, outlier, and temporal-ordering policies
- Group-aware and time-aware validation policy
- Leakage policy and prohibited features
- SPC, capability, drift, anomaly, provenance, and privacy requirements

Every real dataset is expected to satisfy only a subset of the preferred
fields. The contract therefore records each field as required, preferred,
optional, or unavailable rather than assuming all fields exist.

## Leakage Map

The machine-readable leakage map lives at:

```text
data/case_studies/smart_factory/leakage_map_v1_4.csv
```

It explicitly lists high-risk fields and patterns such as final disposition,
post-inspection defect codes, future sensor windows, target encodings across
groups, random splits that mix the same lot, and product or recipe identity
acting as a hidden target proxy.

## Validation Protocol

Random validation is allowed only as a baseline descriptive reference. It is
not primary evidence for manufacturing process-quality generalization.

### Baseline Descriptive Validation

- Random train/test split
- Useful only as an optimistic reference
- Must be labeled as optimistic when group or time structure exists

Failure conditions:

- Random split is reported as primary evidence
- Same lot, product, or time-adjacent records leak across train/test without
  disclosure

### Group-Aware Validation

Candidate groups:

- `lot_id`
- `batch_id`
- `equipment_id`
- `product_id`
- `recipe_id`

Failure conditions:

- Too few groups for holdout validation
- Held-out groups overlap training groups
- Target encoding or scaling is fitted across groups

### Time-Aware Validation

Candidate protocols:

- Forward chronological split
- Rolling or blocked time split
- Train-only scaler, imputer, encoder, threshold, and aggregate fitting

Failure conditions:

- Future records influence past predictions
- Quality measurement occurs before the supposed observation horizon
- Timestamp parseability or ordering is not sufficient

### Combined Validation

Preferred evidence combines group and time logic when possible:

- Future lots
- Future equipment periods
- Unseen recipe or product if enough groups exist

Failure conditions:

- Group count too small
- Time horizon cannot be reconstructed
- Target is only available through post-outcome leakage

## SPC Plan

SPC readiness should be assessed before any claim of control-chart utility.

Candidate analyses:

- Individuals / moving range charts for ordered numeric measurements
- X-bar / R or X-bar / S charts when rational subgroups exist
- p / np / c / u charts where inspected counts or defect counts exist
- Rule violations and drift summaries

Control limits must be learned from a baseline period only. Control limits are
not specification limits, and they should not be inferred from the full dataset
when the goal is future monitoring.

## Capability Plan

Process capability requires externally supplied engineering specification
limits. Cp, Cpk, Pp, and Ppk should not be computed for a real dataset unless
LSL/USL or equivalent limits are documented.

Required caveats:

- Control limits and specification limits are distinct.
- Stable-process assumptions must be reviewed.
- Non-normality can make standard capability summaries misleading.
- Subgroup definition must be documented.
- Synthetic fixtures may include known spec limits, but real datasets should
  not invent them.

## Drift and Anomaly Plan

Drift and anomaly checks should remain transparent and descriptive in v1.4:

- Baseline-window distribution summaries
- Time-block shifts in process variables
- Simple rule-based anomaly flags
- Control-chart rule violations where appropriate

No complex uncertainty model, automatic process action, or online control loop
is in scope.

## Quality Prediction Plan

Prediction is a later phase and must be gated by readiness. If performed, it
should start with baseline tabular models only, use train-only preprocessing,
and report random, group-aware, time-aware, and combined validation separately.

Allowed wording:

- Offline screening
- Defect or yield risk estimation
- Human-review prioritization

Prohibited wording:

- Automatic process control
- Root-cause proof
- Production-ready decision system
- Digital twin or physical simulation

## Expected Limitations

- Public datasets may not expose full line, lot, product, recipe, and quality
  timing structure.
- Some datasets are synthetic and cannot replace real-world validation.
- Specification limits are often absent and must not be invented.
- Quality labels may be delayed or generated after inspection.
- Product or recipe identity can behave as a hidden target proxy.
- Class imbalance may dominate defect/failure outcomes.
- Dataset licenses or platform terms may limit redistribution.

## Release Roadmap

### v1.4.1 Dataset and Process-Quality Contract

- Compare candidate datasets without downloading raw data.
- Define process-quality contract and leakage map.
- Add generic readiness scaffold and synthetic tests.

### v1.4.2 Dataset Acquisition Decision

- Confirm legal access, license, attribution, size, and source stability.
- Verify whether Bosch can move through `access_verified`, `terms_verified`,
  `schema_verified`, and `readiness_verified` toward `active_primary`.
- If Bosch fails access, terms, or schema verification, mark it `blocked` or
  `rejected` and activate the SECOM fallback path.

### v1.4.3 Source-Specific Loader

- Implement a loader only after the dataset decision is made.
- Preserve raw/local artifact policy.

### v1.4.4 Time-Aware Quality Classification Baseline

- Run fixed classical baseline classifiers only.
- Treat chronological blocked, expanding-window, and final holdout splits as
  primary evidence.
- Treat stratified random split as an optimistic reference only.
- Fit feature filtering, imputation, and scaling on each training partition
  only.
- Record PR-AUC as the primary metric, threshold diagnostics at 0.5, Brier
  score as a calibration diagnostic, random-vs-temporal gaps, error-structure
  summaries, and conservative model-status boundaries.
- Preserve row-level predictions as local-only.

v1.4.4 result: non-dummy models remain `diagnostic_only`; no representative
production model is selected.

### v1.4.5 SPC, Capability, Drift, and Anomaly Readiness

- Add descriptive SPC/capability readiness outputs where requirements are met.
- Do not invent spec limits.

### v1.4.6 Baseline Process-Quality Validation

- Run baseline models only after data readiness gates pass.
- Compare random, group-aware, time-aware, and combined validation.

## Non-Goals

- Model training in v1.4.1
- Hyperparameter tuning
- Deep learning
- Real-time control
- API ingestion
- Dashboard or UI
- Digital twin
- Causal root-cause claim
- Automatic process adjustment
- Claiming Smart Factory completion
- Commit, push, tag, or merge automation

## Stop Conditions

Stop or re-scope the v1.4 case study if:

- No legally usable data source is available.
- No process variables are available.
- No quality outcome exists.
- No time or order field exists.
- No meaningful group structure exists.
- Target is only available through leakage.
- Dataset is too small for any group-aware or time-aware validation.
- License terms are ambiguous.
- Unit of analysis cannot be identified.

If no single public dataset satisfies all goals, use a primary real-world case
for limited validation and a secondary synthetic process-control fixture for
SPC and drift examples. The synthetic fixture must be labeled as a test/demo
fixture, not as real-world validation evidence.
