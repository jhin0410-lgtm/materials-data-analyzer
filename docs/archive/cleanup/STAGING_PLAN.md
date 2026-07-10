# Staging Plan

> Historical planning record. Retained for project history; not the current implementation specification.

Plan date: 2026-07-06

Scope: staging plan only. No `git add`, `git commit`, file deletion, file move, code edit, README edit, documentation edit outside this file, or `.gitignore` edit was performed in this phase.

## Goal

Create a safe staging plan for committing the current work.

The commit boundary should include core platform code, tests, scripts, documentation, sample data, case-study documentation, and selected small processed summaries.

The commit boundary should exclude raw data, actual `outputs/` run folders, credentials, local configs, caches, and large downloaded datasets.

## Current Git Status Summary

### Modified

```text
 M .gitignore
 M README.md
 M data/sample/experiment_process.csv
 M src/analyzers/simulation.py
 M src/preprocessing.py
 M src/process_data.py
 M src/reports.py
 M src/visualization.py
 M tests/test_preprocessing.py
 M tests/test_simulation.py
```

### Added / Untracked

```text
?? CHANGELOG.md
?? CLEANUP_EXECUTION_LOG.md
?? CLEANUP_PLAN.md
?? COMMIT_BOUNDARY_REVIEW.md
?? PROJECT_AUDIT.md
?? configs/data_sources.example.yaml
?? data/case_studies/README.md
?? data/case_studies/battery/source.md
?? data/case_studies/battery_archive/source.md
?? data/case_studies/htem/source.md
?? data/case_studies/kaggle_battery/README.md
?? data/case_studies/kaggle_battery/case_study.md
?? data/case_studies/kaggle_battery/simulation_comparison.md
?? data/case_studies/kaggle_battery/source.md
?? data/case_studies/materials_project/source.md
?? data/processed/README.md
?? data/processed/kaggle_battery_simulation_comparison.csv
?? data/processed/kaggle_nasa_battery_analysis_ready_with_features.csv
?? data/processed/kaggle_nasa_battery_cycle_summary.csv
?? data/processed/kaggle_nasa_battery_cycle_summary_analysis_ready.csv
?? data/processed/kaggle_nasa_battery_discharge_features.csv
?? data/processed/kaggle_nasa_battery_quality_summary.csv
?? data/processed/materials_project_fe_si.csv
?? data/raw/battery/README.md
?? data/raw/battery_archive/README.md
?? data/raw/htem/README.md
?? data/raw/kaggle/README.md
?? data/raw/materials_project/README.md
?? data/sample/README.md
?? docs/OUTPUTS_POLICY.md
?? docs/PROJECT_STRUCTURE.md
?? notebooks/battery_preprocessing.py
?? notebooks/inspect_battery_mat.py
?? scripts/build_kaggle_battery_discharge_features.py
?? scripts/build_kaggle_battery_summary.py
?? scripts/compare_simulation_runs.py
?? scripts/ingest_data.py
?? scripts/inspect_processed_data.py
?? src/connectors/__init__.py
?? src/connectors/base.py
?? src/connectors/battery_archive_connector.py
?? src/connectors/htem_connector.py
?? src/connectors/kaggle_connector.py
?? src/connectors/materials_project_connector.py
?? src/data_validation.py
?? src/dataset_registry.py
?? src/domain_constraints.py
?? src/loaders/__init__.py
?? src/loaders/battery_loader.py
?? src/loaders/kaggle_battery_discharge_features.py
?? src/loaders/kaggle_battery_metadata_loader.py
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

### Deleted

```text
None
```

### Ignored / Generated Artifact Candidates

Do not stage:

```text
outputs/
data/raw/ downloaded dataset contents
.env
configs/*.local.yaml
kaggle.json
API credential files
__pycache__/
.pytest_cache/
*.pyc
```

`git ls-files data/raw outputs` currently reports tracked legacy raw/demo files only:

```text
data/raw/README.md
data/raw/experiment_process.csv
data/raw/experiment_reliability.csv
data/raw/factory_log.csv
```

No tracked `outputs/` files were reported.

## Must Stage

These are staging candidates for the main commit set. This plan intentionally lists explicit paths instead of recommending `git add .`.

### Core Source

```text
.gitignore
src/analyzers/simulation.py
src/preprocessing.py
src/process_data.py
src/reports.py
src/visualization.py
src/data_validation.py
src/dataset_registry.py
src/domain_constraints.py
src/results.py
src/schema_mapping.py
src/connectors/
src/loaders/
```

Reason:

- These represent the core platform, readiness layer, optional ingestion layer, case-study loaders, and simulation validation improvements.
- `.gitignore` should be staged with this work because it protects raw data, outputs, credentials, and local configs.

### Scripts

```text
scripts/inspect_processed_data.py
scripts/ingest_data.py
scripts/build_kaggle_battery_summary.py
scripts/build_kaggle_battery_discharge_features.py
scripts/compare_simulation_runs.py
```

### Tests

```text
tests/test_preprocessing.py
tests/test_simulation.py
tests/test_battery_archive_connector.py
tests/test_battery_loader.py
tests/test_compare_simulation_runs.py
tests/test_connectors_base.py
tests/test_data_readiness.py
tests/test_htem_connector.py
tests/test_inspect_processed_data.py
tests/test_kaggle_battery_discharge_features.py
tests/test_kaggle_battery_metadata_loader.py
tests/test_kaggle_connector.py
tests/test_materials_project_connector.py
tests/test_results.py
```

### Documentation

```text
README.md
CHANGELOG.md
docs/OUTPUTS_POLICY.md
docs/PROJECT_STRUCTURE.md
PROJECT_AUDIT.md
CLEANUP_PLAN.md
CLEANUP_EXECUTION_LOG.md
COMMIT_BOUNDARY_REVIEW.md
STAGING_PLAN.md
```

### `data/sample`

```text
data/sample/experiment_process.csv
data/sample/experiment_reliability.csv
data/sample/factory_log.csv
data/sample/simulation_scenarios.csv
data/sample/README.md
```

### `data/case_studies`

```text
data/case_studies/README.md
data/case_studies/battery/source.md
data/case_studies/battery_archive/source.md
data/case_studies/htem/source.md
data/case_studies/kaggle_battery/README.md
data/case_studies/kaggle_battery/source.md
data/case_studies/kaggle_battery/case_study.md
data/case_studies/kaggle_battery/simulation_comparison.md
data/case_studies/materials_project/source.md
```

### `data/processed/README.md`

```text
data/processed/README.md
```

## Optional Stage

These processed summaries are small enough to commit and are useful for the Kaggle battery case-study narrative. They are not raw data, but they are generated artifacts, so they should be staged intentionally.

| File | Size | Purpose | Commit recommendation | Reason |
| --- | ---: | --- | --- | --- |
| `data/processed/kaggle_nasa_battery_cycle_summary.csv` | 314,336 bytes | Full audit discharge cycle summary from Kaggle metadata | Yes | Small derived summary; supports audit trail and quality review. |
| `data/processed/kaggle_nasa_battery_cycle_summary_analysis_ready.csv` | 277,597 bytes | Analysis-ready subset filtered to normal retention-quality rows | Yes | Direct analyzer input for case-study runs. |
| `data/processed/kaggle_nasa_battery_quality_summary.csv` | 3,426 bytes | Battery-level quality summary | Yes | Tiny summary explaining quality filtering decisions. |
| `data/processed/kaggle_nasa_battery_discharge_features.csv` | 587,988 bytes | Scalar discharge features from raw discharge CSVs | Yes | Derived feature table; avoids committing raw time-series files. |
| `data/processed/kaggle_nasa_battery_analysis_ready_with_features.csv` | 783,050 bytes | Analysis-ready summary joined with discharge-derived features | Yes | Main feature-enriched analyzer input; under 1 MB. |
| `data/processed/kaggle_battery_simulation_comparison.csv` | 3,364 bytes | Simulation comparison summary | Yes | Directly supports the case-study report. |

Review separately:

| File | Size | Purpose | Commit recommendation | Reason |
| --- | ---: | --- | --- | --- |
| `data/processed/materials_project_fe_si.csv` | 5,414 bytes | Materials Project connector/generated sample | Review needed | Small, but not part of the Kaggle battery case-study boundary. |

## Must Not Stage

Never stage these in the main commit:

```text
data/raw/
outputs/ actual run folders
.env
Kaggle credentials
API credentials
local config files
configs/*.local.yaml
__pycache__/
.pytest_cache/
*.pyc
large downloaded datasets
raw API responses
raw Kaggle CSV dumps
raw NASA .mat files
```

Important:

- Do not run `git add data/raw`.
- Do not run `git add outputs`.
- Do not run `git add .`.

## Outputs Policy Check

`outputs/README.md` may exist locally, but it is ignored by the `outputs/` ignore rule and should not be treated as a commit target.

The durable outputs policy is:

```text
docs/OUTPUTS_POLICY.md
```

`docs/OUTPUTS_POLICY.md` should be staged with documentation.

## Recommended Git Add Commands

Do not execute these commands during this planning phase. These are explicit-path PowerShell commands for the next step.

### 1. Core Platform and Git Hygiene

```powershell
git add .gitignore
git add src/analyzers/simulation.py src/preprocessing.py src/process_data.py src/reports.py src/visualization.py
git add src/data_validation.py src/dataset_registry.py src/domain_constraints.py src/results.py src/schema_mapping.py
```

### 2. Loaders, Connectors, Scripts, Config Example

```powershell
git add src/loaders/__init__.py src/loaders/battery_loader.py src/loaders/kaggle_battery_metadata_loader.py src/loaders/kaggle_battery_discharge_features.py
git add src/connectors/__init__.py src/connectors/base.py src/connectors/battery_archive_connector.py src/connectors/htem_connector.py src/connectors/kaggle_connector.py src/connectors/materials_project_connector.py
git add scripts/inspect_processed_data.py scripts/ingest_data.py scripts/build_kaggle_battery_summary.py scripts/build_kaggle_battery_discharge_features.py scripts/compare_simulation_runs.py
git add configs/data_sources.example.yaml
```

### 3. Tests

```powershell
git add tests/test_preprocessing.py tests/test_simulation.py
git add tests/test_battery_archive_connector.py tests/test_battery_loader.py tests/test_compare_simulation_runs.py tests/test_connectors_base.py tests/test_data_readiness.py tests/test_htem_connector.py tests/test_inspect_processed_data.py tests/test_kaggle_battery_discharge_features.py tests/test_kaggle_battery_metadata_loader.py tests/test_kaggle_connector.py tests/test_materials_project_connector.py tests/test_results.py
```

### 4. Documentation

```powershell
git add README.md CHANGELOG.md
git add docs/OUTPUTS_POLICY.md docs/PROJECT_STRUCTURE.md
git add PROJECT_AUDIT.md CLEANUP_PLAN.md CLEANUP_EXECUTION_LOG.md COMMIT_BOUNDARY_REVIEW.md STAGING_PLAN.md
```

### 5. Sample Data

```powershell
git add data/sample/experiment_process.csv data/sample/experiment_reliability.csv data/sample/factory_log.csv data/sample/simulation_scenarios.csv data/sample/README.md
```

### 6. Case Study Documentation

```powershell
git add data/case_studies/README.md
git add data/case_studies/battery/source.md data/case_studies/battery_archive/source.md data/case_studies/htem/source.md data/case_studies/materials_project/source.md
git add data/case_studies/kaggle_battery/README.md data/case_studies/kaggle_battery/source.md data/case_studies/kaggle_battery/case_study.md data/case_studies/kaggle_battery/simulation_comparison.md
```

### 7. Processed Data README and Optional Kaggle Summaries

```powershell
git add data/processed/README.md
git add data/processed/kaggle_nasa_battery_cycle_summary.csv
git add data/processed/kaggle_nasa_battery_cycle_summary_analysis_ready.csv
git add data/processed/kaggle_nasa_battery_quality_summary.csv
git add data/processed/kaggle_nasa_battery_discharge_features.csv
git add data/processed/kaggle_nasa_battery_analysis_ready_with_features.csv
git add data/processed/kaggle_battery_simulation_comparison.csv
```

### 8. Explicitly Avoid These

```powershell
# Do not run:
# git add .
# git add data/raw
# git add outputs
```

## Pre-Commit Checklist

Before committing, run:

```powershell
git diff --cached --stat
git diff --cached --name-only
python -m pytest
git status --short
```

Also check for accidental raw or output files:

```powershell
git diff --cached --name-only | Select-String -Pattern '^data/raw/|^outputs/|\\.env$|kaggle\\.json|credentials'
```

Expected result:

- No staged raw downloaded data.
- No staged `outputs/` run folders.
- No credentials or local config files.
- No cache files.

## Recommended Commit Messages

Candidate commit messages:

```text
Add data readiness and simulation validation foundation
```

```text
Add Kaggle battery case study and documentation
```

```text
Document project cleanup and commit boundary policy
```

## Command Results

### `python -m pytest`

```text
89 passed in 22.14s
```

### `git status --short`

Status captured before creating `STAGING_PLAN.md`:

```text
 M .gitignore
 M README.md
 M data/sample/experiment_process.csv
 M src/analyzers/simulation.py
 M src/preprocessing.py
 M src/process_data.py
 M src/reports.py
 M src/visualization.py
 M tests/test_preprocessing.py
 M tests/test_simulation.py
?? CHANGELOG.md
?? CLEANUP_EXECUTION_LOG.md
?? CLEANUP_PLAN.md
?? COMMIT_BOUNDARY_REVIEW.md
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
?? docs/OUTPUTS_POLICY.md
?? docs/PROJECT_STRUCTURE.md
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

### `git diff --stat`

```text
 .gitignore                         |  24 ++-
 README.md                          | 261 +++++++++++++++++----------
 data/sample/experiment_process.csv |  17 +-
 src/analyzers/simulation.py        | 359 +++++++++++++++++++++++++++++++++++--
 src/preprocessing.py               |   5 +-
 src/process_data.py                |  10 ++
 src/reports.py                     |  85 +++++++++
 src/visualization.py               |  70 ++++++++
 tests/test_preprocessing.py        |  14 ++
 tests/test_simulation.py           | 195 ++++++++++++++++++++
 10 files changed, 926 insertions(+), 114 deletions(-)
```

### `data/processed` File Size Summary

```text
kaggle_battery_simulation_comparison.csv               3,364 bytes
kaggle_nasa_battery_analysis_ready_with_features.csv 783,050 bytes
kaggle_nasa_battery_cycle_summary.csv                314,336 bytes
kaggle_nasa_battery_cycle_summary_analysis_ready.csv 277,597 bytes
kaggle_nasa_battery_discharge_features.csv           587,988 bytes
kaggle_nasa_battery_quality_summary.csv                3,426 bytes
materials_project_fe_si.csv                            5,414 bytes
README.md                                              1,833 bytes
```

### Final `git status --short`

Status after creating `STAGING_PLAN.md`:

```text
 M .gitignore
 M README.md
 M data/sample/experiment_process.csv
 M src/analyzers/simulation.py
 M src/preprocessing.py
 M src/process_data.py
 M src/reports.py
 M src/visualization.py
 M tests/test_preprocessing.py
 M tests/test_simulation.py
?? CHANGELOG.md
?? CLEANUP_EXECUTION_LOG.md
?? CLEANUP_PLAN.md
?? COMMIT_BOUNDARY_REVIEW.md
?? PROJECT_AUDIT.md
?? STAGING_PLAN.md
?? configs/
?? data/case_studies/
?? data/processed/
?? data/raw/battery/
?? data/raw/battery_archive/
?? data/raw/htem/
?? data/raw/kaggle/
?? data/raw/materials_project/
?? data/sample/README.md
?? docs/OUTPUTS_POLICY.md
?? docs/PROJECT_STRUCTURE.md
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
