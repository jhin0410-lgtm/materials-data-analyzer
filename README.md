# materials_data_analyzer

[![CI](https://github.com/jhin0410-lgtm/materials-data-analyzer/actions/workflows/ci.yml/badge.svg)](https://github.com/jhin0410-lgtm/materials-data-analyzer/actions/workflows/ci.yml)

`materials_data_analyzer` is a reproducible engineering-data analysis framework
for provenance, readiness checks, leakage-aware validation, and bounded
scientific claims.

## What This Project Is

`materials_data_analyzer` is a **Tabular Engineering Data Analysis & Virtual Experiment Screening Platform**.

It is a CLI-based analysis platform for CSV-style engineering datasets, including materials experiments, process-condition tables, quality data, reliability records, SPC datasets, and smart-factory-like logs.

The project focuses on this workflow:

```text
CSV engineering data
-> data validation
-> EDA / correlation / groupby analysis
-> target-feature relationship analysis
-> process / reliability / SPC / smart-factory analysis
-> data-driven virtual experiment screening
-> Markdown report generation
```

The simulation workflow is a data-driven screening aid. It uses observed target-feature relationships to compare candidate/scenario conditions. It is not physics simulation and does not replace engineering interpretation or validation experiments.

## Core Workflow

1. Load CSV engineering data.
2. Validate file shape, columns, missingness, duplicate rows, and optional domain constraints.
3. Run EDA, correlation analysis, groupby summaries, and target-feature relationship checks.
4. Run domain-oriented analysis modes such as process, reliability, SPC, or smart-factory log analysis.
5. Run simulation mode for data-driven virtual experiment screening with baseline surrogate modeling and validation diagnostics.
6. Generate processed tables, figures, and Markdown reports under `outputs/{run_name}/`.

## Core Capabilities

- Data validation and readiness reporting
- EDA
- Missing-value and duplicate-row summaries
- Correlation analysis
- Groupby summaries
- Target distribution and target-feature relationship analysis
- Process-condition analysis
- Reliability analysis
- SPC and capability analysis
- Smart-factory log analysis
- Data-driven simulation / virtual experiment screening
- Scenario and candidate condition screening
- Baseline model validation diagnostics
- Markdown report generation

## Core Principles

- Prefer explicit data contracts over implicit assumptions.
- Separate raw/local artifacts from compact tracked summaries.
- Fit preprocessing only on training partitions when validation is involved.
- Treat random splits as optimistic references when asset, battery, material,
  or time dependence can inflate results.
- Preserve weak, negative, or limited results instead of tuning them away.
- State what each result can and cannot support before making claims.

## What This Project Is Not

This project is:

- Not a fully automatic engineering decision system
- Not a production battery degradation model
- Not a general-purpose AutoML platform
- Not a raw data repository
- Not a replacement for engineering interpretation
- Not a physics simulator
- Not a tool for deciding final process conditions without domain review

## Project Structure

```text
src/
  Core platform modules, CLI entry point, analyzers, loaders, connectors,
  data-readiness helpers, reports, and visualization utilities.

src/analyzers/
  Core analyzer modes: eda, process, reliability, smart_factory, spc,
  and simulation.

src/loaders/
  Case-study and dataset preparation utilities. These convert external
  source data into analyzer-ready tabular CSVs.

src/connectors/
  Optional/experimental ingestion layer for external data sources.

scripts/
  Utility scripts for ingestion, inspection, case-study preprocessing,
  and simulation-run comparison.

data/sample/
  Synthetic demonstration CSV files for quickstart and tests.

data/raw/
  Local raw-data staging area. Raw downloaded data should generally not
  be committed.

data/processed/
  Generated or curated case-study summary tables.

data/case_studies/
  Real-data demonstration notes and reports. These are not core analyzer
  modules.

outputs/
  Regenerable analyzer run outputs. These are generally local artifacts
  and are not committed.

tests/
  Pytest suite for the platform, loaders, connectors, scripts, and
  validation helpers.
```

For more detail, see [`docs/PROJECT_STRUCTURE.md`](docs/PROJECT_STRUCTURE.md).

## Quickstart

Install dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Run EDA on the synthetic process dataset:

```powershell
python src/process_data.py --mode eda --input data/sample/experiment_process.csv --run-name demo_eda
```

Run process-condition analysis:

```powershell
python src/process_data.py --mode process --input data/sample/experiment_process.csv --target yield_percent --goal maximize --run-name demo_process
```

Run multi-objective process screening:

```powershell
python src/process_data.py --mode process --input data/sample/experiment_process.csv --targets yield_percent hardness_hv resistivity_ohm_cm --goals maximize maximize minimize --run-name demo_multi_objective
```

Run reliability analysis:

```powershell
python src/process_data.py --mode reliability --input data/sample/experiment_reliability.csv --run-name demo_reliability
```

Run smart-factory log analysis:

```powershell
python src/process_data.py --mode smart_factory --input data/sample/factory_log.csv --run-name demo_smart_factory
```

Run SPC analysis:

```powershell
python src/process_data.py --mode spc --input data/sample/factory_log.csv --target temperature_c --lsl 690 --usl 710 --run-name demo_spc
```

Run simulation mode with a scenario CSV:

```powershell
python src/process_data.py --mode simulation --input data/sample/experiment_process.csv --target yield_percent --features process_temp_c process_time_min pressure_mpa thickness_um --scenario-input data/sample/simulation_scenarios.csv --run-name demo_simulation
```

Run candidate condition screening with the sample candidate table:

```powershell
python src/process_data.py --mode simulation --input data/sample/experiment_process.csv --target yield_percent --features process_temp_C process_time_min pressure_mpa thickness_um --scenario-input data/sample/candidate_conditions.csv --goal maximize --run-name sample_virtual_experiment
```

### Virtual Experiment Screening Quickstart

Use `data/sample/experiment_process.csv` as the training dataset and
`data/sample/candidate_conditions.csv` as the candidate condition table.
The sample candidate table includes `candidate_id`, the required feature
columns, and an extra `note` column that is preserved in the outputs.

The main v0.9 screening outputs are:

- `candidate_predictions.csv`: candidate-level predictions, validation status, and warning counts.
- `candidate_domain_warnings.csv`: feature min/max range warnings based on the training data.
- `candidate_ranking.csv`: goal-based candidate ranking for screening review.
- `simulation_report.md`: Markdown summary of validation, predictions, warnings, ranking, limitations, and suggested next checks.

Run virtual experiment screening without a scenario CSV:

```powershell
python src/process_data.py --mode simulation --input data/sample/experiment_process.csv --target yield_percent --features process_temp_c process_time_min pressure_mpa thickness_um --design-method random --design-samples 100 --run-name demo_virtual_experiment
```

Run tests:

```powershell
python -m pytest
```

On Windows, the repository-local test runner avoids user temp-directory
permission issues:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_tests.ps1
```

The tracked test suite is designed to run without local raw datasets, Backblaze
archives, row-level predictions, or generated `outputs/` folders.

## Real-Data Case Studies

The repository currently includes five representative real-data case studies:

- Kaggle NASA Li-ion Battery
- Battery Archive
- Materials Project
- Smart Factory / UCI SECOM
- Reliability / Backblaze Hard Drive Test Data

The Reliability / Backblaze work is complete as an offline trust-boundary case
study: access gate, full-year normalization audit, event/censoring readiness,
fixed 7-day diagnostic classification baselines, and model-eligibility
closeout.

These case studies demonstrate source-specific preparation and validation
workflows. They are not the core product identity; the core project remains a
Tabular Engineering Data Analysis & Virtual Experiment Screening Platform.

| Case study | Task | Validation emphasis | Trust result | Release |
| --- | --- | --- | --- | --- |
| Kaggle NASA Li-ion Battery | Capacity-retention analysis | Random split vs `battery_id` group split | Stronger within-battery interpolation than unseen-battery generalization | v0.8 |
| Battery Archive | Cycle-level capacity retention and threshold proxies | Data quality, observed censoring, reliability group summaries | Descriptive cycle-data case study; no forecasting/RUL claim | v1.1 |
| Materials Project | Computed-property screening and composition-only validation | Group-aware chemical-system validation and applicability domain | Descriptive screening reproducible; predictive validation weak | v1.2 / v1.3 |
| Smart Factory / UCI SECOM | Process-quality failure classification | Time-aware validation and random-split gap | Diagnostic-only; no production model selected | v1.4.0 |
| Reliability / Backblaze | 7-day drive failure-risk ranking | Asset-disjoint, time-aware, combined asset/time validation | Diagnostic-only; no representative model selected | v1.5.0 |

### Kaggle NASA Li-ion Battery

The Kaggle NASA battery work is a representative real-data case study, not the core product identity.

The case study demonstrates:

- Data quality audit from Kaggle cleaned metadata
- Full audit CSV and analysis-ready CSV separation
- Analysis-ready filtering using `retention_quality_flag`
- Raw discharge CSV feature extraction into scalar cycle-level features
- Random split versus `battery_id` group split validation
- Simulation-run comparison and Markdown reporting

Case-study documents:

- [`data/case_studies/kaggle_battery/case_study.md`](data/case_studies/kaggle_battery/case_study.md)
- [`data/case_studies/kaggle_battery/source.md`](data/case_studies/kaggle_battery/source.md)
- [`data/case_studies/kaggle_battery/simulation_comparison.md`](data/case_studies/kaggle_battery/simulation_comparison.md)

Key conclusion:

Raw discharge-derived features produced high random-split performance, but `battery_id` group split validation showed limited generalization to unseen batteries. This means the current battery case-study model is better viewed as within-battery diagnostic interpolation than production battery-level forecasting.

### Battery Archive

The Battery Archive work is a second representative real-data case study based
on locally staged raw zip files. It demonstrates:

- Raw zip inventory without extraction: 9 zip files
- 196 cycle-data CSV files and 343,503 normalized cycle rows
- Filename metadata enrichment
- Cycle CSV schema audit and normalization
- Quality flags, capacity-retention metrics, and capacity-based SOH proxy
- 80% / 70% threshold crossing proxies with observed-censoring notes
- Compact reliability group summary and Markdown case-study reporting

Raw Battery Archive zip files and large generated cycle-level CSVs are not
included in the repository. Reproduction commands and source notes live in:

- [`data/case_studies/battery_archive/README.md`](data/case_studies/battery_archive/README.md)
- [`data/case_studies/battery_archive/source.md`](data/case_studies/battery_archive/source.md)
- [`data/case_studies/battery_archive/methodology.md`](data/case_studies/battery_archive/methodology.md)
- [`data/case_studies/battery_archive/case_study.md`](data/case_studies/battery_archive/case_study.md)

### Materials Project

The Materials Project work includes a compact 50-row descriptive screening
pilot and a v1.3 exact-provenance validation case study over an 838-row
Fe/Si-containing multinary calculated-property table. It demonstrates:

- Reconstructed query, provenance, schema, and data-quality contracts
- Conservative normalization and compact quality summaries
- Deterministic calculated-property screening
- Descriptive energy-above-hull ranking without ML prediction
- 60 composition-only physical descriptors
- Group-aware baseline validation by reduced formula and chemical system
- Applicability-domain, error-structure, and claim-boundary diagnostics
- Conservative release closeout with weak/limited predictive results preserved

This case study does not claim novel materials discovery, direct DFT execution,
synthesis feasibility, experimental validation, or generalizable model
performance. The v1.3 conclusion is that composition-only prediction remained
weak, group-aware generalization was limited, and observed-property descriptive
screening remains reproducible. Reproduction commands and interpretation notes
live in:

- [`data/case_studies/materials_project/README.md`](data/case_studies/materials_project/README.md)
- [`data/case_studies/materials_project/source.md`](data/case_studies/materials_project/source.md)
- [`data/case_studies/materials_project/screening_methodology.md`](data/case_studies/materials_project/screening_methodology.md)
- [`data/case_studies/materials_project/case_study.md`](data/case_studies/materials_project/case_study.md)

### Smart Factory / UCI SECOM

The Smart Factory work uses UCI SECOM as an operational fallback after the
Bosch access gate was not cleared. It demonstrates process-quality source
provenance, row-order alignment, temporal integrity checks, feature-quality
audit, time-aware validation, train-only preprocessing, fixed classical
classification baselines, and trust-boundary closeout.

The v1.4 conclusion is conservative: all non-dummy models remain
`diagnostic_only`, no representative production model is selected, random split
performance is an optimistic reference only, calibrated probability claims are
prohibited, and group-aware generalization is unavailable because explicit
equipment, lot, product, and recipe IDs are absent.

Case-study documents:

- [`data/case_studies/smart_factory/README.md`](data/case_studies/smart_factory/README.md)
- [`data/case_studies/smart_factory/case_study.md`](data/case_studies/smart_factory/case_study.md)
- [`docs/SMART_FACTORY_V1_4_PLAN.md`](docs/SMART_FACTORY_V1_4_PLAN.md)

### Reliability / Backblaze Hard Drive Test Data

The v1.5 reliability track uses Backblaze Hard Drive Test Data 2013 as an
asset-level reliability case study. It defines event/censoring policy, leakage
boundaries, asset/time-aware validation, fixed 7-day diagnostic classification
baselines, and a conservative trust-boundary closeout.

Observed closeout highlights:

- 5,091,501 normalized daily rows and 29,072 drive assets
- 724 failed assets and 4,797 positive 7-day labels
- best primary median PR-AUC: 0.0998
- best combined asset/time PR-AUC: 0.1119
- combined top 1% reference precision/lift/capture: 0.0703 / 62.9x / 0.846
- representative model: none selected

This case study supports retrospective offline ranking diagnostics only. It
does not fit survival models, estimate RUL, claim calibrated operational
probabilities, run SHAP, identify root cause, or make production maintenance
claims.

Planning documents:

- [`docs/RELIABILITY_V1_5_PLAN.md`](docs/RELIABILITY_V1_5_PLAN.md)
- [`data/case_studies/reliability/README.md`](data/case_studies/reliability/README.md)
- [`data/case_studies/reliability/case_study.md`](data/case_studies/reliability/case_study.md)

## Validation and Trust Boundary

Validation design is part of the result, not an afterthought. Where the data
has repeated batteries, assets, materials, timestamps, or process periods, the
project reports group-aware or time-aware evidence separately from optimistic
random-split references.

Trust-boundary closeouts record whether a model is descriptive-only,
diagnostic-only, limited evidence for further validation, or not run. A case
study can be complete even when no representative model is selected. The
Backblaze v1.5 release is an example: top-risk concentration exists, but
repeated daily origins, resource-limited training, uncertain censoring, and
missing external validation keep the result inside a diagnostic boundary.

## Optional Connectors

The connector layer is optional and experimental. It is not required to use the core CSV analyzer.

Current connector directions include:

- Kaggle
- Materials Project
- HTEM
- Battery Archive

Connectors should not store API keys, Kaggle credentials, raw API responses, or large downloaded datasets in the repository.

## Data and Artifact Policy

- `data/sample/` contains synthetic demonstration data.
- `data/raw/` is local raw-data staging and should generally not be committed.
- `data/processed/` contains generated or curated case-study summary artifacts.
- `outputs/` contains regenerable analyzer run outputs and should generally not be committed.
- For the detailed outputs policy, see [`docs/OUTPUTS_POLICY.md`](docs/OUTPUTS_POLICY.md).
- Public real-data case studies should document source, processing steps, quality limitations, and analysis commands.

## Example Outputs

Representative static images are stored in `docs/images/`.

### Correlation Heatmap

![Demo correlation heatmap](docs/images/correlation_heatmap.png)

### Process Group Summary Chart

![Demo material target mean chart](docs/images/material_target_mean.png)

### SPC Control Chart

![Demo SPC I chart](docs/images/spc_i_chart.png)

### Smart-Factory Trend Chart

![Demo smart-factory temperature trend](docs/images/smart_factory_temperature_trend.png)

Typical run output:

```text
outputs/{run_name}/processed/
outputs/{run_name}/figures/
outputs/{run_name}/reports/
```

## Releases

- v1.5.0: Reliability / Backblaze asset- and time-aware validation with
  trust-boundary closeout. See [`docs/releases/V1_5_0.md`](docs/releases/V1_5_0.md).
- v1.4.0: Smart Factory / UCI SECOM time-aware validation and trust boundary.
- v1.3.1: Materials Project group-aware validation and trust boundary.

For a portfolio-oriented overview of the architecture and case-study arc, see
[`docs/PORTFOLIO_OVERVIEW.md`](docs/PORTFOLIO_OVERVIEW.md).

## Platform v2 Scaffold

v2.0.5 continues the configuration-driven platform layer without replacing the
existing CLI or case-study scripts. It adds explicit plugin, adapter, artifact,
validation-policy, trust-policy, case-study, and onboarding registries plus
dry-run, controlled verify-run manifest support, and local-only read-only
platform reports.

```powershell
python -m src.cli list-plugins
python -m src.cli list-adapters
python -m src.cli list-case-studies
python -m src.cli inspect-case-study reliability
python -m src.cli validate-config configs/examples/reliability_trust_dry_run.json
python -m src.cli validate-onboarding configs/examples/environmental_monitoring_onboarding.json
python -m src.cli onboarding-plan configs/examples/environmental_monitoring_onboarding.json
python -m src.cli dry-run configs/examples/reliability_trust_dry_run.json
python -m src.cli dry-run configs/examples/reliability_trust_manifest_dry_run.json --write-manifest
python -m src.cli execute configs/examples/reliability_trust_verify_run.json --mode verify
python -m src.cli preview-report --config configs/examples/platform_report_all_case_studies.json
python -m src.cli generate-report --config configs/examples/platform_report_all_case_studies.json
```

This layer is currently `scaffold_stage`: it can inspect metadata, validate
configs, validate new-domain onboarding metadata, plan dry-runs, write local
manifest-only dry-run records, and verify Reliability trust compact artifacts.
It can also summarize registry metadata and tracked compact artifacts into
JSON/Markdown reports under ignored `outputs/platform_reports/`. It does not
execute acquisition, model training, trust scripts, raw-data reads,
row-level prediction reads, scientific result recomputation, or network
operations. See
[`docs/PLATFORM_ARCHITECTURE.md`](docs/PLATFORM_ARCHITECTURE.md) and
[`docs/PLATFORM_EXECUTION.md`](docs/PLATFORM_EXECUTION.md). For reporting,
domain interface, and onboarding, see
[`docs/PLATFORM_REPORTING.md`](docs/PLATFORM_REPORTING.md),
[`docs/CASE_STUDY_INTERFACE.md`](docs/CASE_STUDY_INTERFACE.md) and
[`docs/NEW_DOMAIN_ONBOARDING.md`](docs/NEW_DOMAIN_ONBOARDING.md).

## Roadmap

### v0.9: Virtual Experiment Screening Polish

- Improve candidate condition ranking documentation
- Add clearer constraints and out-of-distribution warning summaries
- Improve simulation report readability
- Make virtual experiment outputs easier to compare across runs

### v1.1 Complete: Battery Archive Cycle-Data Case Study

- Raw zip inventory, filename metadata, schema audit, normalization, quality flags, derived capacity metrics, and reliability group summary are complete.
- Timeseries processing, forecasting, and group-aware simulation remain future work.

### v1.2 Complete: Materials Project Descriptive Screening Pilot

- Query/provenance contract, schema normalization, quality audit, deterministic property screening, and pilot documentation are complete.
- Broader exact-provenance querying, composition descriptors, ML property prediction, and group-aware validation remain future work.

### v1.3 Complete: Materials Project Validation and Trust Boundary

- Exact provenance acquisition, 838-row dataset validation, 60 composition-only descriptors, identifiability and ambiguity audit, group-aware baseline validation, applicability-domain diagnostics, claim-boundary summary, and conservative closeout are complete.
- Composition-only prediction remained weak; no predictive novel-material recommendation, DFT replacement, calibrated uncertainty, or production-ready screening claim is made.
- v1.4 is complete as a Smart Factory Process Quality trust-boundary case
  study.

### v1.4 Complete: Smart Factory Process Quality Trust Boundary

- UCI SECOM is used as a fallback process-quality case study after the Bosch
  access gate remained blocked.
- The workflow covers source provenance, analysis-ready normalization,
  temporal integrity, feature-quality audit, time-aware classification
  baselines, and trust-boundary closeout.
- The final result is diagnostic-only: no representative production model,
  calibrated probability claim, causal root-cause claim, or real-time control
  claim is made.
- See [`docs/SMART_FACTORY_V1_4_PLAN.md`](docs/SMART_FACTORY_V1_4_PLAN.md) and
  [`data/case_studies/smart_factory/`](data/case_studies/smart_factory/).

### v1.5 Complete: Reliability Trust Boundary

- Backblaze Hard Drive Test Data 2013 is used as an asset-level reliability
  case study.
- The workflow covers source access, full-year streaming normalization,
  event/censoring integrity, fixed 7-day asset/time-aware classification
  baselines, and model-eligibility closeout.
- The final result is diagnostic-only: no representative model, calibrated
  failure probability, survival/RUL claim, SHAP/root-cause claim, or production
  maintenance claim is made.
- See [`docs/RELIABILITY_V1_5_PLAN.md`](docs/RELIABILITY_V1_5_PLAN.md) and
  [`data/case_studies/reliability/`](data/case_studies/reliability/).

### Later

- Streamlit demo after CLI outputs and report structure are stable
- More case studies using public engineering tabular datasets
- Additional optional connectors where licensing and credentials are handled safely
- More advanced ML/DL only after baseline validation and data-quality workflows are mature

## Related Project

[`materials-characterization-analyzer`](https://github.com/jhin0410-lgtm/materials-characterization-analyzer) is a separate project for XRD, SEM, and EDS characterization data.

This repository focuses on CSV-based engineering tabular data rather than characterization spectra, microscopy images, or elemental maps.
