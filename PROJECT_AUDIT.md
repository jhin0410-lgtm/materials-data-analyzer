# Project Audit

Audit date: 2026-07-06

Scope: inventory and classification only. No source code, README, data, output, or test cleanup was performed as part of this audit.

## Project Identity

`materials_data_analyzer` should be treated as a:

**Tabular Engineering Data Analysis & Virtual Experiment Screening Platform**

The core project is a general-purpose platform for CSV-based engineering, process, quality, reliability, and smart-factory tabular data. Its center of gravity is EDA, validation, target-feature analysis, process/reliability/SPC analysis, and data-driven virtual experiment screening.

The Kaggle NASA battery work is not the core product identity. It is a representative real-data case study showing how the platform can process a public engineering dataset, prepare analysis-ready tables, run validation-aware simulation analysis, and document limitations.

## Current Directory Inventory

### `src/`

Core Python package and CLI entry point. It currently contains:

- Platform IO and preprocessing: `data_io.py`, `io_utils.py`, `preprocessing.py`
- CLI orchestration: `process_data.py`
- Reporting and plotting helpers: `reports.py`, `visualization.py`
- Readiness/result schemas: `dataset_registry.py`, `schema_mapping.py`, `domain_constraints.py`, `data_validation.py`, `results.py`
- Analysis modes under `src/analyzers/`
- Real-data loaders under `src/loaders/`
- Optional external-source connectors under `src/connectors/`

### `src/analyzers/`

Core analyzer modes:

- `eda.py`: basic EDA and dataset profiling
- `process.py`: process/target analysis and multi-objective summaries
- `reliability.py`: reliability-oriented summaries
- `simulation.py`: data-driven surrogate simulation, scenario screening, model diagnostics, and optional group-aware validation
- `smart_factory.py`: smart-factory style log/trend summaries
- `spc.py`: SPC/capability analysis

### `src/loaders/`

Case-study and real-dataset preparation utilities:

- `battery_loader.py`: NASA `.mat` battery loader skeleton and cycle-summary helpers
- `kaggle_battery_metadata_loader.py`: Kaggle NASA metadata discharge summary builder
- `kaggle_battery_discharge_features.py`: raw discharge CSV scalar feature extraction

These are not analyzer modes. They prepare external data into analyzer-compatible tabular CSVs.

### `src/connectors/`

Optional ingestion connectors:

- `base.py`
- `battery_archive_connector.py`
- `htem_connector.py`
- `kaggle_connector.py`
- `materials_project_connector.py`

These should be treated as optional ingestion infrastructure, not required core analyzer behavior.

### `scripts/`

Utility scripts around ingestion, inspection, case-study preprocessing, and comparison:

- `ingest_data.py`
- `inspect_processed_data.py`
- `build_kaggle_battery_summary.py`
- `build_kaggle_battery_discharge_features.py`
- `compare_simulation_runs.py`

### `data/sample/`

Synthetic demo/sample inputs for tests and examples. Current visible files:

- `experiment_process.csv`
- `README.md`

Git status also shows deleted tracked sample files that need cleanup review:

- `data/sample/experiment_reliability.csv`
- `data/sample/factory_log.csv`
- `data/sample/simulation_scenarios.csv`

### `data/raw/`

Raw-data staging area. Current visible folders:

- `battery/`
- `battery_archive/`
- `htem/`
- `kaggle/`
- `materials_project/`
- `README.md`

This area should remain local-first. Large raw datasets should not be committed. The local Kaggle raw folder currently contains thousands of ignored raw files.

### `data/processed/`

Generated or case-study processed tables. Current visible files:

- `kaggle_battery_simulation_comparison.csv`
- `kaggle_nasa_battery_analysis_ready_with_features.csv`
- `kaggle_nasa_battery_cycle_summary.csv`
- `kaggle_nasa_battery_cycle_summary_analysis_ready.csv`
- `kaggle_nasa_battery_discharge_features.csv`
- `kaggle_nasa_battery_quality_summary.csv`
- `materials_project_fe_si.csv`
- `README.md`

These files are useful for portfolio/case-study reproducibility, but they are generated artifacts and should have an explicit versioning policy.

### `data/case_studies/`

Case-study documentation and source notes:

- `battery/source.md`
- `battery_archive/source.md`
- `htem/source.md`
- `kaggle_battery/README.md`
- `kaggle_battery/source.md`
- `kaggle_battery/case_study.md`
- `kaggle_battery/simulation_comparison.md`
- `materials_project/source.md`

### `outputs/`

Generated analyzer run outputs. Current folders include demo runs, smoke runs, test artifacts, Kaggle battery case-study runs, Materials Project runs, and temporary comparison-test outputs.

Representative groups:

- Demo outputs: `demo_eda`, `demo_process`, `demo_reliability`, `demo_simulation`, `demo_smart_factory`, `demo_spc`, `demo_virtual_experiment`
- Kaggle case-study outputs: `kaggle_battery_metadata_only_retention_simulation`, `kaggle_battery_feature_enriched_retention_simulation`, `kaggle_battery_metadata_only_group_retention_simulation`, `kaggle_battery_feature_enriched_group_retention_simulation`, `kaggle_battery_feature_enriched_no_count_group_retention_simulation`
- Smoke/test outputs: `kaggle_battery_group_validation_smoke`, `kaggle_battery_random_validation_smoke`, `_compare_simulation_runs_tests`, `_kaggle_battery_feature_tests`, and similar

`outputs/` is generated and gitignored.

### `tests/`

Pytest suite for core analyzers, IO, preprocessing, readiness layer, simulation diagnostics, loaders, connectors, scripts, and result schemas.

Current test suite size from this audit run: 89 tests.

## Classification

| Path or pattern | Classification | Notes |
| --- | --- | --- |
| `src/process_data.py` | `core_platform` | CLI entry point for analyzer modes. |
| `src/analyzers/` | `core_platform` | Core EDA/process/reliability/smart_factory/SPC/simulation modes. |
| `src/data_io.py`, `src/io_utils.py` | `core_platform` | Data loading and output helpers. |
| `src/preprocessing.py` | `core_platform` | Shared cleaning/preprocessing behavior. |
| `src/reports.py`, `src/visualization.py` | `core_platform` | Shared reporting and plotting helpers. |
| `src/dataset_registry.py` | `core_platform` | Data readiness metadata schema. |
| `src/schema_mapping.py` | `core_platform` | Column standardization helper. |
| `src/domain_constraints.py` | `core_platform` | Domain constraint checks. |
| `src/data_validation.py` | `core_platform` | Dataset readiness report helper. |
| `src/results.py` | `core_platform` | Future API/Streamlit-compatible request/result schema. |
| `src/loaders/battery_loader.py` | `case_study_kaggle_battery` | NASA battery loader groundwork; not a general analyzer mode. |
| `src/loaders/kaggle_battery_metadata_loader.py` | `case_study_kaggle_battery` | Kaggle NASA metadata to cycle summary. |
| `src/loaders/kaggle_battery_discharge_features.py` | `case_study_kaggle_battery` | Raw discharge CSV scalar feature extraction. |
| `scripts/build_kaggle_battery_summary.py` | `case_study_kaggle_battery` | Builds full, analysis-ready, and quality summary CSVs. |
| `scripts/build_kaggle_battery_discharge_features.py` | `case_study_kaggle_battery` | Builds discharge feature table and merged analysis-ready table. |
| `scripts/compare_simulation_runs.py` | `case_study_kaggle_battery` | Compares selected simulation runs for the case study. |
| `data/case_studies/kaggle_battery/` | `case_study_kaggle_battery` | Portfolio case-study documentation. |
| `src/connectors/` | `optional_connector` | External data source ingestion helpers. |
| `scripts/ingest_data.py` | `optional_connector` | Connector-driven ingestion script. |
| `configs/data_sources.example.yaml` | `optional_connector` | Example connector config. |
| `data/processed/*.csv` | `generated_artifact` | Processed outputs; decide whether selected case-study tables should be versioned. |
| `outputs/` | `generated_artifact` | Analyzer run outputs; currently gitignored. |
| `docs/images/*.png` | `generated_artifact` | Static docs images, currently tracked. |
| `data/sample/` | `sample_data` | Synthetic demo/test data area. |
| `tests/` | `test_support` | Pytest coverage for platform, loaders, connectors, and scripts. |
| `README.md`, `TESTING.md`, `docs/` | `documentation` | Project-level documentation. |
| `data/raw/**/README.md` | `documentation` | Raw-data placement notes. |
| `data/case_studies/*/source.md` | `documentation` | Dataset source notes. |
| `data/raw/kaggle/`, `data/raw/battery_archive/`, `data/raw/htem/`, `data/raw/materials_project/` | `cleanup_review_needed` | Local raw-data staging; should stay ignored except README/source docs. |
| Smoke/test output folders under `outputs/` | `cleanup_review_needed` | Useful during development, but not all should remain as portfolio artifacts. |
| Deleted tracked sample/raw files in `git status` | `cleanup_review_needed` | Need intentional restore/remove decision later. |

## Keep List

These files/folders should be kept unless a later cleanup pass has a specific replacement plan:

- `src/process_data.py`
- `src/analyzers/`
- `src/data_io.py`
- `src/io_utils.py`
- `src/preprocessing.py`
- `src/reports.py`
- `src/visualization.py`
- `src/dataset_registry.py`
- `src/schema_mapping.py`
- `src/domain_constraints.py`
- `src/data_validation.py`
- `src/results.py`
- `src/loaders/`
- `src/connectors/` if optional ingestion remains part of the roadmap
- `scripts/inspect_processed_data.py`
- `scripts/ingest_data.py`
- `scripts/build_kaggle_battery_summary.py`
- `scripts/build_kaggle_battery_discharge_features.py`
- `scripts/compare_simulation_runs.py`
- `data/sample/README.md`
- Synthetic sample CSVs required by tests and CLI examples
- `data/raw/README.md`
- `data/raw/**/README.md`
- `data/case_studies/kaggle_battery/`
- `data/case_studies/*/source.md`
- Selected `data/processed/` CSVs that are intentionally part of the portfolio case study
- `tests/`
- `.github/workflows/ci.yml`
- `README.md`
- `TESTING.md`
- `requirements.txt`

## Cleanup Review List

These are cleanup candidates, but no cleanup was performed in this audit:

- Smoke run outputs under `outputs/`, such as `kaggle_battery_group_validation_smoke`, `kaggle_battery_random_validation_smoke`, and other smoke/check folders.
- Temporary test output folders under `outputs/`, such as `_compare_simulation_runs_tests`, `_compare_simulation_runs_report_tests`, `_connector_tests`, `_inspect_processed_data_tests`, and `_kaggle_battery_feature_tests`.
- Older demo/test run outputs that are not needed for portfolio presentation.
- Duplicated or intermediate processed CSVs in `data/processed/`; decide which are canonical case-study deliverables.
- `data/processed/materials_project_fe_si.csv`; review whether this is a portfolio artifact, connector smoke artifact, or local generated file.
- Deleted tracked files shown by Git:
  - `data/raw/experiment_process.csv`
  - `data/raw/experiment_reliability.csv`
  - `data/raw/factory_log.csv`
  - `data/sample/experiment_reliability.csv`
  - `data/sample/factory_log.csv`
  - `data/sample/simulation_scenarios.csv`
- Optional connector skeletons if the near-term project wants to stay focused on local CSV analysis only.
- Local raw data under `data/raw/kaggle/`, `data/raw/battery_archive/`, `data/raw/htem/`, and `data/raw/materials_project/`.
- Python cache folders and pytest cache if any are visible locally. They are already covered by `.gitignore`.

## Git Hygiene Check

### Status Summary

The working tree is dirty. Current status includes:

- Modified tracked files: `.gitignore`, `data/sample/experiment_process.csv`, core simulation/readiness-related source files, and simulation/preprocessing tests.
- Deleted tracked files: 7 files, listed separately below.
- Untracked folders/files: configs, case-study docs, processed data, raw-source README folders, notebooks, scripts, connectors, loaders, readiness modules, result schema, and new tests.

### Deleted Markers Requiring Attention

Git currently reports these tracked files as deleted:

```text
D data/raw/experiment_process.csv
D data/raw/experiment_reliability.csv
D data/raw/factory_log.csv
D data/sample/experiment_reliability.csv
D data/sample/factory_log.csv
D data/sample/simulation_scenarios.csv
```

These should not be resolved casually. In a cleanup pass, decide whether to restore them, replace them with newer synthetic sample files, or intentionally remove them in a dedicated commit.

### Ignore Coverage

Current `.gitignore` covers:

- Python caches and build artifacts
- `.pytest_cache/`
- `.venv/`
- `outputs/`
- `data/raw/battery/*` with README exception
- `data/raw/materials_project/*`
- `data/raw/kaggle/*`
- `data/raw/htem/*`
- `data/raw/battery_archive/*`
- `data/raw/**/README.md` exceptions
- `configs/data_sources.local.yaml`
- `.env`

Manual `git check-ignore` checks confirmed:

```text
outputs/... is ignored by outputs/
data/raw/kaggle/... is ignored by data/raw/kaggle/*
data/raw/battery/B0005.mat is ignored by data/raw/battery/*
.env is ignored
configs/data_sources.local.yaml is ignored
```

`data/processed/` is not currently ignored. That may be intentional if selected processed case-study CSVs are portfolio artifacts. If processed outputs should remain local/generated, add a clear ignore policy later.

The local Kaggle raw folder currently contains 7,577 raw files under `data/raw/kaggle/`; these are ignored and should not be committed.

## Recommended Next Cleanup Steps

Do not execute these steps as part of this audit. Recommended order for a later cleanup pass:

1. Decide the versioning policy for `data/processed/`: keep selected portfolio CSVs, ignore all generated CSVs, or keep only small summaries.
2. Resolve deleted tracked sample/raw files intentionally: restore, replace, or remove in a dedicated cleanup commit.
3. Separate the Kaggle battery case study into canonical deliverables:
   - source documentation
   - full audit CSV if versioned
   - analysis-ready CSV if versioned
   - feature-enriched CSV if versioned
   - comparison CSV/report
   - final `case_study.md`
4. Prune or archive non-canonical `outputs/` smoke/test/demo runs after preserving any report tables needed for the portfolio.
5. Review optional connectors and decide whether they belong in the main branch now or should remain behind a documented optional ingestion layer.
6. Ensure raw data folders contain only README/source instructions in version control.
7. Update README after cleanup decisions are made, not before.
8. Run `python -m pytest` and any CLI smoke commands after cleanup.
9. Commit in logical batches: core platform, ingestion/readiness, Kaggle case study, docs, cleanup.

## Command Results

### `python -m pytest`

Result:

```text
89 passed in 10.20s
```

### `git status --short`

Result:

```text
 M .gitignore
 D data/raw/experiment_process.csv
 D data/raw/experiment_reliability.csv
 D data/raw/factory_log.csv
 M data/sample/experiment_process.csv
 D data/sample/experiment_reliability.csv
 D data/sample/factory_log.csv
 D data/sample/simulation_scenarios.csv
 M src/analyzers/simulation.py
 M src/preprocessing.py
 M src/process_data.py
 M src/reports.py
 M src/visualization.py
 M tests/test_preprocessing.py
 M tests/test_simulation.py
?? PROJECT_AUDIT.md
?? configs/
?? data/case_studies/
?? data/processed/
?? data/raw/battery/
?? data/raw/battery_archive/
?? data/raw/htem/
?? data/raw/kaggle/
?? data/raw/materials_project/
?? data/sample/README.md
?? notebooks/
?? scripts/
?? src/connectors/
?? src/data_validation.py
?? src/dataset_registry.py
?? src/domain_constraints.py
?? src/loaders/
?? src/results.py
?? src/schema_mapping.py
?? tests/test_battery_archive_connector.py
?? tests/test_battery_loader.py
?? tests/test_compare_simulation_runs.py
?? tests/test_connectors_base.py
?? tests/test_data_readiness.py
?? tests/test_htem_connector.py
?? tests/test_inspect_processed_data.py
?? tests/test_kaggle_battery_discharge_features.py
?? tests/test_kaggle_battery_metadata_loader.py
?? tests/test_kaggle_connector.py
?? tests/test_materials_project_connector.py
?? tests/test_results.py
```
