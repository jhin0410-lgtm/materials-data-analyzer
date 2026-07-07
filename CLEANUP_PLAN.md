# Cleanup Plan

Plan date: 2026-07-06

Scope: planning only. No cleanup, deletion, move, code change, README change, analyzer feature change, or `.gitignore` change was performed in this step.

## Cleanup Goal

Project identity:

**Tabular Engineering Data Analysis & Virtual Experiment Screening Platform**

The cleanup goal is to clearly separate:

- Core analyzer platform code
- Kaggle NASA battery case study code and documents
- Optional connectors
- Generated artifacts
- Raw/local data
- Cleanup candidates that need review before any deletion or restore action

This step does not execute cleanup. It only creates a safe plan based on `PROJECT_AUDIT.md`, current directory state, `python -m pytest`, and `git status --short`.

## Current State Summary

Based on `PROJECT_AUDIT.md` and the current workspace:

- Pytest result: `89 passed in 10.76s`
- Git state: dirty working tree
- Deleted tracked files currently shown by Git: 6
- Untracked folders/files include new readiness modules, loaders, connectors, scripts, case-study docs, processed CSVs, notebooks, and new tests
- Raw data folders exist under `data/raw/`
- Large local Kaggle raw data exists under `data/raw/kaggle/`
- `outputs/` exists and contains many generated analyzer runs
- Kaggle battery case-study artifacts exist under `data/case_studies/kaggle_battery/` and `data/processed/`

Current deleted tracked files:

```text
D data/raw/experiment_process.csv
D data/raw/experiment_reliability.csv
D data/raw/factory_log.csv
D data/sample/experiment_reliability.csv
D data/sample/factory_log.csv
D data/sample/simulation_scenarios.csv
```

Important note: sample data deletion markers require special care because quickstart commands, tests, and demo workflows may rely on them.

Current processed files:

```text
data/processed/kaggle_battery_simulation_comparison.csv
data/processed/kaggle_nasa_battery_analysis_ready_with_features.csv
data/processed/kaggle_nasa_battery_cycle_summary.csv
data/processed/kaggle_nasa_battery_cycle_summary_analysis_ready.csv
data/processed/kaggle_nasa_battery_discharge_features.csv
data/processed/kaggle_nasa_battery_quality_summary.csv
data/processed/materials_project_fe_si.csv
data/processed/README.md
```

## Keep List

### 1. `core_platform`

Keep as core platform code:

- `src/process_data.py`
- `src/analyzers/`
- `src/analyzers/eda.py`
- `src/analyzers/process.py`
- `src/analyzers/reliability.py`
- `src/analyzers/simulation.py`
- `src/analyzers/smart_factory.py`
- `src/analyzers/spc.py`
- `src/data_io.py`
- `src/io_utils.py`
- `src/preprocessing.py`
- `src/reports.py`
- `src/visualization.py`
- `src/config.py`
- `src/dataset_registry.py`
- `src/schema_mapping.py`
- `src/domain_constraints.py`
- `src/data_validation.py`
- `src/results.py`

### 2. `tests`

Keep the pytest suite:

- `tests/conftest.py`
- Existing core tests: `test_data_io.py`, `test_eda_io.py`, `test_preprocessing.py`, `test_process.py`, `test_simulation.py`, `test_spc.py`
- Readiness/result tests: `test_data_readiness.py`, `test_results.py`
- Loader/case-study tests: `test_battery_loader.py`, `test_kaggle_battery_metadata_loader.py`, `test_kaggle_battery_discharge_features.py`
- Connector/script tests: `test_connectors_base.py`, `test_battery_archive_connector.py`, `test_htem_connector.py`, `test_kaggle_connector.py`, `test_materials_project_connector.py`, `test_inspect_processed_data.py`, `test_compare_simulation_runs.py`

### 3. `sample_data`

Keep synthetic sample data and sample documentation:

- `data/sample/README.md`
- `data/sample/experiment_process.csv`
- `data/sample/experiment_reliability.csv`
- `data/sample/factory_log.csv`
- `data/sample/simulation_scenarios.csv`

The last three are currently deleted in Git status and should be restored or intentionally replaced before cleanup is finalized.

### 4. Kaggle Battery Case Study Code

Keep as case-study preparation code:

- `src/loaders/battery_loader.py`
- `src/loaders/kaggle_battery_metadata_loader.py`
- `src/loaders/kaggle_battery_discharge_features.py`
- `scripts/build_kaggle_battery_summary.py`
- `scripts/build_kaggle_battery_discharge_features.py`
- `scripts/compare_simulation_runs.py`

These should remain separate from analyzer modes. They are data preparation utilities for real-data case studies.

### 5. Kaggle Battery Case Study Documentation

Keep:

- `data/case_studies/kaggle_battery/README.md`
- `data/case_studies/kaggle_battery/source.md`
- `data/case_studies/kaggle_battery/case_study.md`
- `data/case_studies/kaggle_battery/simulation_comparison.md`

### 6. Essential Processed Case Study Summaries

Keep candidates:

- `data/processed/kaggle_nasa_battery_cycle_summary.csv`
- `data/processed/kaggle_nasa_battery_cycle_summary_analysis_ready.csv`
- `data/processed/kaggle_nasa_battery_quality_summary.csv`
- `data/processed/kaggle_nasa_battery_discharge_features.csv`
- `data/processed/kaggle_nasa_battery_analysis_ready_with_features.csv`
- `data/processed/kaggle_battery_simulation_comparison.csv`

These are useful for portfolio reproducibility. Final commit policy should be decided during cleanup execution.

### 7. Optional Connectors

Keep as optional/experimental ingestion infrastructure unless a later decision removes them:

- `src/connectors/base.py`
- `src/connectors/battery_archive_connector.py`
- `src/connectors/htem_connector.py`
- `src/connectors/kaggle_connector.py`
- `src/connectors/materials_project_connector.py`
- `scripts/ingest_data.py`
- `configs/data_sources.example.yaml`

### 8. `documentation`

Keep:

- `README.md`
- `TESTING.md`
- `PROJECT_AUDIT.md`
- `CLEANUP_PLAN.md`
- `docs/`
- `docs/case_studies/`
- `docs/images/`
- `data/raw/README.md`
- `data/raw/**/README.md`
- `data/case_studies/*/source.md`

## Do Not Commit List

Do not commit these unless there is a very specific, documented exception:

- `data/raw/`
- `outputs/`
- `.env`
- Local config files, especially `configs/data_sources.local.yaml`
- API credentials
- Kaggle credentials
- `__pycache__/`
- `.pytest_cache/`
- Large downloaded datasets
- Raw API responses
- Raw Kaggle downloaded files
- Raw `.mat` files such as local NASA battery files
- Temporary run folders and pytest-generated output folders

## Cleanup Candidates

### 1. `restore_needed`

Files currently deleted in Git status but likely needed or requiring an explicit replacement/removal decision:

- `data/sample/experiment_reliability.csv`
- `data/sample/factory_log.csv`
- `data/sample/simulation_scenarios.csv`
- `data/raw/experiment_process.csv`
- `data/raw/experiment_reliability.csv`
- `data/raw/factory_log.csv`

Recommendation:

- Restore the sample files unless newer synthetic sample equivalents fully replace them.
- Review the old tracked `data/raw/*.csv` files. If they were synthetic demo inputs, either restore or remove them in a dedicated cleanup commit with README updates.

### 2. `archive_or_delete_generated_outputs`

Review these categories later:

- Smoke run outputs, for example:
  - `outputs/kaggle_battery_group_validation_smoke`
  - `outputs/kaggle_battery_random_validation_smoke`
  - `outputs/kaggle_battery_analysis_ready_eda_smoke`
  - `outputs/kaggle_battery_features_eda_smoke`
  - `outputs/kaggle_battery_metadata_eda_smoke`
- Duplicate or older simulation outputs:
  - `outputs/kaggle_battery_capacity_simulation`
  - `outputs/kaggle_battery_retention_simulation`
  - `outputs/kaggle_battery_analysis_ready_retention_simulation`
- Regenerable demo outputs:
  - `outputs/demo_eda`
  - `outputs/demo_process`
  - `outputs/demo_reliability`
  - `outputs/demo_simulation`
  - `outputs/demo_smart_factory`
  - `outputs/demo_spc`
  - `outputs/demo_virtual_experiment`
- Temporary test outputs:
  - `outputs/_compare_simulation_runs_tests`
  - `outputs/_compare_simulation_runs_report_tests`
  - `outputs/_connector_tests`
  - `outputs/_inspect_processed_data_tests`
  - `outputs/_kaggle_battery_feature_tests`

No deletion should happen until the canonical portfolio outputs are identified.

### 3. `review_processed_data`

Keep candidates:

- `data/processed/kaggle_nasa_battery_cycle_summary.csv`
- `data/processed/kaggle_nasa_battery_cycle_summary_analysis_ready.csv`
- `data/processed/kaggle_nasa_battery_quality_summary.csv`
- `data/processed/kaggle_nasa_battery_discharge_features.csv`
- `data/processed/kaggle_nasa_battery_analysis_ready_with_features.csv`
- `data/processed/kaggle_battery_simulation_comparison.csv`

Review candidates:

- `data/processed/materials_project_fe_si.csv`
- Any future processed files not directly referenced by `case_study.md`, `source.md`, or `simulation_comparison.md`

Decision needed:

- Either commit only selected case-study summaries, or keep `data/processed/` generated/local and rely on scripts to reproduce the files.

### 4. `optional_or_experimental`

Document these as optional/experimental first, rather than deleting:

- `src/connectors/`
- `scripts/ingest_data.py`
- `configs/data_sources.example.yaml`
- `notebooks/battery_preprocessing.py`
- `notebooks/inspect_battery_mat.py`
- `src/loaders/battery_loader.py` if only the Kaggle metadata path remains active
- Non-Kaggle `data/case_studies/*/source.md` files if those case studies are not yet portfolio-ready

### 5. `local_raw_data`

Keep local only:

- `data/raw/kaggle/`
- `data/raw/battery/`
- `data/raw/battery_archive/`
- `data/raw/htem/`
- `data/raw/materials_project/`

Only README/source instruction files should be committed from these areas.

## Processed Data Policy

`data/processed/` contains generated tables. For this project, the safest policy is:

- Commit only small, intentional, documented case-study summary files.
- Do not commit raw or high-volume intermediate data.
- Keep enough processed summaries to make the portfolio report reproducible without committing raw datasets.

Recommended keep candidates:

- `kaggle_nasa_battery_cycle_summary.csv`
- `kaggle_nasa_battery_cycle_summary_analysis_ready.csv`
- `kaggle_nasa_battery_quality_summary.csv`
- `kaggle_nasa_battery_discharge_features.csv`
- `kaggle_nasa_battery_analysis_ready_with_features.csv`
- `kaggle_battery_simulation_comparison.csv`

Review candidates:

- `materials_project_fe_si.csv`: decide whether this belongs to a separate Materials Project case study, connector smoke test, or local generated artifact.
- `data/processed/README.md`: keep if it explains generated-file policy.
- Any future unreferenced processed CSVs: default to review before commit.

## Outputs Policy

`outputs/` should be treated as regenerable analyzer output and should remain gitignored by default.

Representative Kaggle battery case-study runs that should be recorded for traceability:

- `kaggle_battery_metadata_only_retention_simulation`
- `kaggle_battery_feature_enriched_retention_simulation`
- `kaggle_battery_metadata_only_group_retention_simulation`
- `kaggle_battery_feature_enriched_group_retention_simulation`
- `kaggle_battery_feature_enriched_no_count_group_retention_simulation`

Whether to commit any selected output files should be decided during cleanup execution.

Default recommendation:

- Do not commit `outputs/`.
- Commit the curated case-study report and comparison CSV instead:
  - `data/case_studies/kaggle_battery/case_study.md`
  - `data/case_studies/kaggle_battery/simulation_comparison.md`
  - `data/processed/kaggle_battery_simulation_comparison.csv`

## Git Hygiene Plan

### Deleted Tracked Files

Suggested handling:

- `data/sample/experiment_reliability.csv`: restore unless replaced by a documented synthetic sample.
- `data/sample/factory_log.csv`: restore unless replaced by a documented synthetic sample.
- `data/sample/simulation_scenarios.csv`: restore unless simulation examples no longer require it.
- `data/raw/experiment_process.csv`: review whether this was legacy demo data; restore or remove intentionally.
- `data/raw/experiment_reliability.csv`: review whether this was legacy demo data; restore or remove intentionally.
- `data/raw/factory_log.csv`: review whether this was legacy demo data; restore or remove intentionally.

Sample data deletion markers should be resolved before any cleanup commit.

### Untracked Files/Folders

Suggested handling:

- `PROJECT_AUDIT.md`: commit as documentation if accepted.
- `CLEANUP_PLAN.md`: commit as documentation if accepted.
- `configs/`: commit only non-secret examples; keep local configs ignored.
- `data/case_studies/`: commit curated source notes and Kaggle battery case-study docs.
- `data/processed/`: commit only selected case-study summary CSVs after policy decision.
- `data/raw/*`: commit README/source notes only; raw datasets stay local.
- `data/sample/README.md`: commit.
- `notebooks/`: review as templates/helpers; commit only if lightweight and documented.
- `scripts/`: commit reusable utilities.
- `src/connectors/`: commit if optional ingestion layer remains part of roadmap.
- `src/loaders/`: commit case-study loaders if Kaggle/NASA battery case study remains in repo.
- `src/data_validation.py`, `src/dataset_registry.py`, `src/domain_constraints.py`, `src/results.py`, `src/schema_mapping.py`: commit as core readiness/API-prep platform modules.
- New tests: commit with the corresponding modules/scripts they validate.

### Raw Data

Raw data is untracked and should remain ignored/local. Verify `.gitignore` still covers:

- `data/raw/kaggle/*`
- `data/raw/battery/*`
- `data/raw/battery_archive/*`
- `data/raw/htem/*`
- `data/raw/materials_project/*`

### Outputs

`outputs/` is ignored and should remain ignored. If any output table is needed for portfolio documentation, prefer copying the curated summary into `data/processed/` or documenting the run in Markdown rather than committing full output folders.

## Safe Cleanup Command Plan

Do not run these commands in this planning step. These are candidate PowerShell commands for the next cleanup stage.

Check status first:

```powershell
git status --short
```

Restore deleted sample files if the decision is to keep them:

```powershell
git restore -- data/sample/experiment_reliability.csv
git restore -- data/sample/factory_log.csv
git restore -- data/sample/simulation_scenarios.csv
```

Restore old tracked raw demo files only if the decision is to keep them:

```powershell
git restore -- data/raw/experiment_process.csv
git restore -- data/raw/experiment_reliability.csv
git restore -- data/raw/factory_log.csv
```

Preview ignored files before any cleanup:

```powershell
git status --ignored --short
```

List generated output folders before deciding what to archive or delete:

```powershell
Get-ChildItem -Path outputs -Directory | Select-Object -ExpandProperty Name
```

Archive selected outputs before deletion, if needed:

```powershell
Compress-Archive -Path outputs/kaggle_battery_metadata_only_retention_simulation -DestinationPath outputs_archive/kaggle_battery_metadata_only_retention_simulation.zip
```

Delete a specific generated output only after review:

```powershell
Remove-Item -LiteralPath outputs/name_of_reviewed_generated_run -Recurse
```

Avoid broad cleanup commands at first. In particular, do not run this casually:

```powershell
git clean -fdx
```

After any cleanup:

```powershell
python -m pytest
git status --short
```

## Risks

- Deleting `data/sample/` files can break quickstart examples, CLI smoke commands, and tests.
- Deleting Kaggle case-study processed summaries can reduce report reproducibility.
- Deleting all `outputs/` can make it harder to re-check the exact comparison runs unless scripts are rerun.
- Deleting raw data may require re-download, credentials, or manual dataset setup.
- Deleting connector modules can break tests or the optional ingestion layer.
- Committing raw data, API responses, credentials, or local config can expose sensitive or oversized files.
- Removing processed files without updating documentation can leave `case_study.md` and `source.md` pointing to missing artifacts.

## Recommended Cleanup Execution Order

1. Decide whether deleted tracked sample/raw files should be restored, replaced, or removed.
2. Check `.gitignore` policy without changing it until the keep/review decision is final.
3. Confirm raw data is not staged and remains ignored/local.
4. Decide whether any `outputs/` folders should be archived; default to not committing outputs.
5. Decide which `data/processed/` CSVs are canonical portfolio artifacts.
6. Document optional connectors as optional/experimental rather than deleting them immediately.
7. Update README/CHANGELOG only after cleanup decisions are made.
8. Run `python -m pytest`.
9. Run `git status --short` and review staged/untracked files before committing.

## Command Results

### `python -m pytest`

```text
89 passed in 10.76s
```

### `git status --short`

Status before creating `CLEANUP_PLAN.md`:

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

Status after creating `CLEANUP_PLAN.md`:

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

## Final Notes

No cleanup was executed in this step. No files were deleted, moved, or restored. No code, README, analyzer behavior, or `.gitignore` changes were made. The only intended output of this step is `CLEANUP_PLAN.md`.
