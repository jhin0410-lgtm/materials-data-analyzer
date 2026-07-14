# Project Structure

`materials_data_analyzer` is a **Tabular Engineering Data Analysis & Virtual Experiment Screening Platform**.

This document separates core platform code, case-study utilities, optional connectors, generated artifacts, and local raw data.

## v1.1 Structure Freeze

During the v1.1 Battery Archive work, this repository keeps the current Minimal Cleanup Tree rather than continuing structural reshuffles. Connectors own raw discovery and access boundaries, loaders own file-content parsing and schema normalization, and scripts own workflow orchestration. Battery Archive v1.1.3 and later should focus on schema audit and ingestion behavior within these boundaries.

The v1.1 Battery Archive cycle-data case study is complete through reliability
group summaries and documentation. Timeseries processing, forecasting, and
group-aware simulation remain future work, and the repository structure remains
frozen for this phase.

## Core Platform

Core platform files are required for the CLI analyzer workflow:

```text
src/process_data.py
src/analyzers/
src/data_io.py
src/io_utils.py
src/preprocessing.py
src/reports.py
src/visualization.py
src/config.py
src/dataset_registry.py
src/schema_mapping.py
src/domain_constraints.py
src/data_validation.py
src/results.py
```

These files support CSV loading, validation, EDA, process analysis, reliability analysis, SPC, smart-factory log analysis, simulation screening, reporting, plotting, and future API/Streamlit result schemas.

`src/analyzers/property_screening.py` provides generic deterministic property
filtering and ranking for descriptive tabular screening workflows. It is not an
ML model or virtual experiment predictor.

`src/analyzers/grouped_regression_validation.py` and
`src/analyzers/applicability_domain.py` provide generic validation and
trust-boundary diagnostics used by the Materials Project case study. They are
baseline diagnostic utilities, not AutoML, candidate recommendation, or
calibrated uncertainty engines.

`src/analyzers/process_quality_readiness.py` provides generic schema,
timestamp, identifier, target, leakage, SPC, and group/time validation
readiness checks for process-quality and Smart Factory case studies. It does
not train models or call external systems.

`src/analyzers/temporal_classification_validation.py` and
`src/analyzers/classification_trust.py` provide fixed baseline time-aware
classification validation and trust-boundary summaries. They are diagnostic
utilities, not AutoML, SHAP, real-time monitoring, or production decision
engines.

`src/analyzers/reliability_readiness.py` provides generic asset, event,
censoring, temporal-order, validation-feasibility, and leakage-readiness checks
for reliability/risk case studies. `src/connectors/reliability.py` and
`src/loaders/reliability.py` support source discovery, schema reconnaissance,
and streaming full-year normalization audits for v1.5 readiness gates. They do
not train models, fit survival curves, or estimate RUL.

`src/features/temporal_asset_features.py` and
`src/analyzers/asset_temporal_classification.py` provide generic cutoff-safe
lookback feature construction and fixed asset/time-aware binary classification
baseline utilities. `src/analyzers/reliability_trust.py` aggregates compact
classification artifacts into model-eligibility, operational-boundary, and
claim-boundary closeout tables. They are used for the v1.5 Backblaze
diagnostic case study and do not perform survival modeling, RUL regression,
hyperparameter search, SHAP, or production alerting.

`src/platform_core/` contains the additive v2 scaffold: plugin metadata,
adapter metadata, artifact metadata, case-study metadata, validation/trust
policy registries, JSON config validation, onboarding validation,
side-effect-free dry-run planning, local manifest writing, and the controlled
reliability trust verify runtime. v2.0.5 also adds read-only platform report
models, explicit compact-artifact extractors, registry snapshots, and
JSON/Markdown report generation under `outputs/platform_reports/`. v2.1.1 adds
a local-only SQLite run/artifact registry under `outputs/platform_registry/`
for manifest ingestion, lineage, reproducibility status, and run comparison.
v2.1.2 adds registry diagnostics, evidence-gap analysis, registered claim
evaluation, and evidence-graph summaries from persisted metadata only.
`src/cli.py` exposes this scaffold via `python -m src.cli`. It does not replace
existing scripts or execute acquisition/modeling pipelines.

## Case Study Utilities

Case-study utilities prepare public or external datasets for the core analyzer:

```text
src/loaders/
scripts/build_kaggle_battery_summary.py
scripts/build_kaggle_battery_discharge_features.py
scripts/compare_simulation_runs.py
scripts/build_materials_project_query_contract.py
scripts/build_materials_project_normalized.py
scripts/run_materials_project_screening.py
scripts/run_materials_project_v1_3_validation.py
scripts/run_materials_project_v1_3_trust_analysis.py
```

These are not analyzer modes. They convert source-specific data into analyzer-ready tabular CSV files.

Materials Project schema normalization lives in `src/loaders/materials_project_loader.py`.

## Optional Connectors

The connector layer is optional and experimental:

```text
src/connectors/
scripts/ingest_data.py
configs/data_sources.example.yaml
```

Connectors may help ingest from external data sources, but the core analyzer remains a local CSV-first CLI platform.

## Local Configs And Notebooks

`configs/examples/` contains sanitized tracked examples. Local, private, or
secret configs remain ignored by narrow `.gitignore` patterns and should not be
committed. Platform report examples live alongside dry-run and onboarding
examples and write only ignored local outputs. `notebooks/` remains local
scratch space unless a public example is created intentionally. Do not commit
credentials, private paths, executed scratch notebooks, or local API settings.

## Case Study Documentation

Real-data demonstrations live under:

```text
data/case_studies/
```

The current representative real-data demonstrations are:

```text
data/case_studies/kaggle_battery/
data/case_studies/battery_archive/
data/case_studies/materials_project/
data/case_studies/smart_factory/
data/case_studies/reliability/
```

They document source data, processing steps, quality review, analysis-ready or
series-level summaries, limitations, and next steps.

The v1.2 Materials Project pilot is complete as a 50-row descriptive
calculated-property screening case study.

The v1.3 Materials Project validation case study is complete through exact
provenance acquisition, 60 composition-only descriptors, identifiability and
ambiguity audit, group-aware baseline validation, applicability-domain
diagnostics, error-structure summaries, and conservative claim-boundary
closeout. It does not claim novel-material recommendation, DFT replacement,
calibrated uncertainty, or production screening readiness. v1.4 and v1.5 extend
the same trust-boundary pattern to Smart Factory process quality and
Reliability Engineering case studies.

The v1.4 Smart Factory case study is complete as a SECOM fallback
process-quality trust-boundary demonstration: dataset candidate assessment,
process-quality contract, leakage map, acquisition provenance, analysis-ready
normalization, temporal integrity checks, feature-quality audit, fixed
time-aware classification baselines, and conservative closeout. It does not
claim production readiness, calibrated probability, causal root cause, or
group-aware generalization.

The v1.5 reliability/risk work is complete as a Backblaze trust-boundary case
study. It defines asset-level reliability fields, event/censoring policy,
leakage risks, validation hierarchy, metrics, candidate dataset assessment,
Backblaze full-year normalization/readiness outputs, fixed 7-day asset/time
classification baselines, and model-eligibility closeout outputs. It does not
claim survival probability, RUL, calibrated operational probability, root-cause
discovery, or production maintenance readiness.

Portfolio and release-facing documentation lives in `docs/`, including
`docs/PORTFOLIO_OVERVIEW.md` and versioned release notes under
`docs/releases/`. These documents summarize tracked artifacts and claim
boundaries; they do not replace source manifests or case-study contracts.

## Generated Artifacts

Generated artifacts include:

```text
data/processed/
outputs/
```

`data/processed/` may contain curated case-study summary tables. `outputs/` contains regenerable analyzer run outputs and should generally stay local. See [`OUTPUTS_POLICY.md`](OUTPUTS_POLICY.md) for the repository-level outputs policy.
Platform report outputs are generated under `outputs/platform_reports/` and are
local-only. Platform registry databases and exports are generated under
`outputs/platform_registry/` and are also local-only. Registry diagnostic
tables and exports are metadata-only local artifacts under the same ignored
path.

For Materials Project, compact tracked candidates include query manifests,
property inventories, quality summaries, screening summaries, descriptor
inventories, model-comparison summaries, applicability summaries,
error-structure summaries, claim-boundary summaries, and trust conclusions.
Local-only artifacts include source/acquired CSVs, normalized CSVs,
analysis-ready descriptor tables, full row-level screening results, row-level
validation predictions, and row-level trust diagnostics.

For Smart Factory v1.4, compact tracked artifacts include acquisition,
readiness, feature-quality, temporal, classification-metric, eligibility,
claim-boundary, and closeout summaries. Local-only artifacts include raw SECOM
files, the SECOM analysis-ready CSV, row-level classification predictions, and
`outputs/` diagnostics.

### v0.9 Virtual Experiment Outputs

Simulation mode writes virtual experiment screening artifacts under:

```text
outputs/{run_name}/processed/
outputs/{run_name}/reports/
```

Key v0.9 candidate-screening outputs include:

- `candidate_conditions.csv`: normalized candidate or generated design table.
- `candidate_predictions.csv`: prediction table with candidate validation status and warning counts.
- `candidate_domain_warnings.csv`: training feature min/max range warning table.
- `candidate_ranking.csv`: goal-based candidate ranking table for screening review.
- `simulation_report.md`: Markdown report explaining validation, candidate predictions, warnings, ranking, limitations, and next experiment checks.

These outputs are regenerable run artifacts. Keep the output policy in docs, and do not commit actual `outputs/` run folders by default.

## Sample Data

Synthetic demo data lives under:

```text
data/sample/
```

These files are for tests, quickstart commands, and pipeline demonstration. They are not real experimental or production records.

## Local Raw Data

Local raw-data staging lives under:

```text
data/raw/
```

Raw downloaded datasets, API responses, Kaggle files, credentials, and large source archives should not be committed.

## Tests

The pytest suite lives under:

```text
tests/
```

It covers the core analyzer, data readiness helpers, loaders, optional connectors, script utilities, and simulation validation behavior.
