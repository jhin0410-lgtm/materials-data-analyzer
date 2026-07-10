# Commit Boundary Review

Review date: 2026-07-06

Scope: review document only. No analyzer code, loader, connector, processed CSV, output run, raw data, or `.gitignore` change was made as part of this review.

## Goal

Define a safe commit boundary for:

- Core platform
- Kaggle battery case study
- Generated artifacts
- Local raw data

The goal is to separate source code and durable documentation from local/generated artifacts so the repository remains useful, reproducible, and safe to publish.

## Current Git Status

### Summary

- Modified tracked files: 10
- Deleted tracked files: 0
- Untracked top-level or grouped paths: many, including documentation, configs, scripts, loaders, connectors, case-study data/docs, processed data, raw-data README/source folders, and new tests
- `outputs/README.md` exists locally, but is ignored by `outputs/`
- `data/raw/` folders appear as untracked groups because README/source documentation files are intentionally allowed by ignore exceptions; raw downloaded files should remain ignored

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

### Deleted

```text
None
```

## Should Commit

### Core Source Code

Commit candidates:

```text
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
```

Reason:

- These represent the core platform evolution: data readiness, simulation validation diagnostics, group-aware validation, and future API/Streamlit result schemas.

### Scripts

Commit candidates:

```text
scripts/inspect_processed_data.py
scripts/build_kaggle_battery_summary.py
scripts/build_kaggle_battery_discharge_features.py
scripts/compare_simulation_runs.py
scripts/ingest_data.py
```

Reason:

- These are reusable utilities for processed data inspection, Kaggle case-study preparation, simulation comparison, and optional ingestion.

### Tests

Commit candidates:

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

Reason:

- They validate the platform changes, loaders, connectors, script utilities, and result schemas.

### Documentation

Commit candidates:

```text
README.md
CHANGELOG.md
PROJECT_AUDIT.md
CLEANUP_PLAN.md
CLEANUP_EXECUTION_LOG.md
docs/PROJECT_STRUCTURE.md
data/sample/README.md
data/processed/README.md
data/case_studies/README.md
```

Reason:

- These clarify project identity, cleanup history, commit policy, and directory responsibilities.

### `data/sample`

Commit candidates:

```text
data/sample/experiment_process.csv
data/sample/experiment_reliability.csv
data/sample/factory_log.csv
data/sample/simulation_scenarios.csv
data/sample/README.md
```

Reason:

- Sample CSVs support quickstart commands, CLI examples, and tests.
- They must remain synthetic/demo data.

### `data/case_studies`

Commit candidates:

```text
data/case_studies/README.md
data/case_studies/kaggle_battery/README.md
data/case_studies/kaggle_battery/source.md
data/case_studies/kaggle_battery/case_study.md
data/case_studies/kaggle_battery/simulation_comparison.md
data/case_studies/battery/source.md
data/case_studies/battery_archive/source.md
data/case_studies/htem/source.md
data/case_studies/materials_project/source.md
```

Reason:

- These are documentation and source notes, not raw datasets.
- The Kaggle battery case-study docs are the main portfolio narrative.

### Small Processed Case Study Summaries

Commit candidates after size and policy review:

```text
data/processed/kaggle_nasa_battery_cycle_summary.csv
data/processed/kaggle_nasa_battery_cycle_summary_analysis_ready.csv
data/processed/kaggle_nasa_battery_quality_summary.csv
data/processed/kaggle_nasa_battery_discharge_features.csv
data/processed/kaggle_nasa_battery_analysis_ready_with_features.csv
data/processed/kaggle_battery_simulation_comparison.csv
data/processed/README.md
```

Reason:

- These are curated summary artifacts, not raw data.
- They make the case-study report easier to inspect without committing raw Kaggle files.

## Should Not Commit

Do not commit:

```text
data/raw/
outputs/ actual run folders
.env
configs/*.local.yaml
configs/data_sources.local.yaml
API credentials
Kaggle credentials
kaggle.json
__pycache__/
.pytest_cache/
*.pyc
large downloaded datasets
raw API responses
raw Kaggle CSV dumps
raw NASA .mat files
```

Reason:

- These are local, sensitive, large, or regenerable artifacts.
- Raw data and credentials should stay outside Git.

## Processed Data Decision

Current `data/processed/` file-size summary:

| File | Size bytes | Size approx | Decision |
| --- | ---: | ---: | --- |
| `kaggle_battery_simulation_comparison.csv` | 3,364 | 3.3 KB | `commit_candidate` |
| `kaggle_nasa_battery_analysis_ready_with_features.csv` | 783,050 | 764.7 KB | `commit_candidate` |
| `kaggle_nasa_battery_cycle_summary.csv` | 314,336 | 307.0 KB | `commit_candidate` |
| `kaggle_nasa_battery_cycle_summary_analysis_ready.csv` | 277,597 | 271.1 KB | `commit_candidate` |
| `kaggle_nasa_battery_discharge_features.csv` | 587,988 | 574.2 KB | `commit_candidate` |
| `kaggle_nasa_battery_quality_summary.csv` | 3,426 | 3.3 KB | `commit_candidate` |
| `materials_project_fe_si.csv` | 5,414 | 5.3 KB | `review_needed` |
| `README.md` | 1,833 | 1.8 KB | `commit_candidate` |

### Commit Candidates

```text
data/processed/kaggle_nasa_battery_cycle_summary.csv
data/processed/kaggle_nasa_battery_cycle_summary_analysis_ready.csv
data/processed/kaggle_nasa_battery_quality_summary.csv
data/processed/kaggle_nasa_battery_discharge_features.csv
data/processed/kaggle_nasa_battery_analysis_ready_with_features.csv
data/processed/kaggle_battery_simulation_comparison.csv
data/processed/README.md
```

Rationale:

- All Kaggle battery processed files are under 1 MB each.
- They are documented in the case study.
- They are summary artifacts, not raw time-series dumps.

### Regenerate Only

```text
None identified in current data/processed listing.
```

### Review Needed

```text
data/processed/materials_project_fe_si.csv
```

Rationale:

- Small enough to commit, but not part of the Kaggle battery case-study deliverable.
- Decide whether it belongs to a Materials Project case study, connector smoke result, or local generated artifact.

## Outputs README Issue

`outputs/README.md` exists locally, but `git check-ignore` confirms it is ignored by:

```text
.gitignore:11:outputs/ outputs/README.md
```

This means `outputs/README.md` will not appear in ordinary `git status --short`.

Options:

1. Move or copy the policy to `docs/OUTPUTS_POLICY.md`.
2. Add `.gitignore` exceptions later:

```gitignore
outputs/*
!outputs/README.md
```

Recommendation:

- Prefer option 1: create `docs/OUTPUTS_POLICY.md` in a later documentation cleanup.
- Reason: `outputs/` should remain a fully ignored generated-artifact directory. Keeping policy documentation under `docs/` avoids special-case tracking inside a generated folder.

No `.gitignore` change was made during this review.

## Recommended Commit Groups

If commits are split later, use this order:

1. Core analyzer + tests
   - Core source changes
   - Data readiness modules
   - Simulation validation/group-aware validation changes
   - Matching tests

2. Kaggle battery case study code
   - Battery loaders
   - Kaggle metadata summary builder
   - Raw discharge feature extraction
   - Simulation comparison script

3. Case study documentation and reports
   - `data/case_studies/`
   - selected `data/processed/` Kaggle summary artifacts

4. Cleanup/audit documentation
   - `PROJECT_AUDIT.md`
   - `CLEANUP_PLAN.md`
   - `CLEANUP_EXECUTION_LOG.md`
   - `COMMIT_BOUNDARY_REVIEW.md`

5. Docs reframing
   - `README.md`
   - `CHANGELOG.md`
   - `docs/PROJECT_STRUCTURE.md`
   - `data/processed/README.md`
   - `data/sample/README.md`

## Risks

- Committing `data/raw/` may publish raw downloaded datasets, credentials, or large files.
- Committing `outputs/` run folders can bloat the repository with regenerable artifacts.
- Committing credentials such as `.env`, `kaggle.json`, or local config files can leak secrets.
- Excluding sample data can break quickstart commands and tests.
- Excluding Kaggle processed summary files may make the case-study report less reproducible.
- Committing processed data without source notes can blur the difference between raw data and derived summaries.
- Removing optional connectors from the commit boundary could break connector tests or the optional ingestion layer.

## Commands for Next Step

Do not run these commands as part of this review. They are candidate PowerShell commands for the next step.

Check status:

```powershell
git status --short
```

Add core platform and tests:

```powershell
git add src/analyzers/simulation.py src/preprocessing.py src/process_data.py src/reports.py src/visualization.py
git add src/data_validation.py src/dataset_registry.py src/domain_constraints.py src/results.py src/schema_mapping.py
git add tests/test_preprocessing.py tests/test_simulation.py tests/test_data_readiness.py tests/test_results.py
```

Add loaders, scripts, connectors, and related tests:

```powershell
git add src/loaders scripts src/connectors configs/data_sources.example.yaml
git add tests/test_battery_loader.py tests/test_kaggle_battery_metadata_loader.py tests/test_kaggle_battery_discharge_features.py
git add tests/test_compare_simulation_runs.py tests/test_inspect_processed_data.py
git add tests/test_connectors_base.py tests/test_battery_archive_connector.py tests/test_htem_connector.py tests/test_kaggle_connector.py tests/test_materials_project_connector.py
```

Add documentation:

```powershell
git add README.md CHANGELOG.md PROJECT_AUDIT.md CLEANUP_PLAN.md CLEANUP_EXECUTION_LOG.md COMMIT_BOUNDARY_REVIEW.md
git add docs/PROJECT_STRUCTURE.md data/sample/README.md data/case_studies data/processed/README.md
```

Add selected processed case-study summaries:

```powershell
git add data/processed/kaggle_nasa_battery_cycle_summary.csv
git add data/processed/kaggle_nasa_battery_cycle_summary_analysis_ready.csv
git add data/processed/kaggle_nasa_battery_quality_summary.csv
git add data/processed/kaggle_nasa_battery_discharge_features.csv
git add data/processed/kaggle_nasa_battery_analysis_ready_with_features.csv
git add data/processed/kaggle_battery_simulation_comparison.csv
```

Restore candidates if an unintended change appears:

```powershell
git restore -- path/to/file
```

Remove accidental staged raw/generated files:

```powershell
git restore --staged data/raw
git restore --staged outputs
git rm --cached path/to/accidentally_tracked_generated_file
```

Run tests:

```powershell
python -m pytest
```

Review staged diff:

```powershell
git diff --cached --stat
git diff --cached --name-status
```

## Command Results

### `python -m pytest`

```text
89 passed in 21.76s
```

### `git status --short`

Status captured before creating `COMMIT_BOUNDARY_REVIEW.md`:

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

Status after creating `COMMIT_BOUNDARY_REVIEW.md`:

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
