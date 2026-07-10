# Repository Root & Architecture Audit

Generated on: 2026-07-10  
Branch inspected: `feature/v1.1-battery-archive`  
Scope: audit only. No code, data, README, `.gitignore`, file move, file delete, commit, or push was performed.

Phase A/B cleanup implementation note:

- Root audit records were moved to [docs/audits](audits/): `PROJECT_AUDIT.md`, `COMMIT_BOUNDARY_REVIEW.md`.
- Cleanup planning remains in [docs/plans](plans/): `CLEANUP_PLAN.md`.
- Historical cleanup/staging records were moved to [docs/archive/cleanup](archive/cleanup/): `CLEANUP_EXECUTION_LOG.md`, `STAGING_PLAN.md`.
- The original snapshot below is retained as the pre-cleanup audit record.

## 1. Current Repository Snapshot

The project is currently a CLI-first tabular engineering data analysis platform with case-study and connector work layered around it. The root is usable, but it now mixes stable public documentation with historical planning logs. That is the main cleanup pressure point.

Top-level snapshot:

| path | current purpose | tracked / ignored / local-only status | kind | problem | recommended action |
| --- | --- | --- | --- | --- | --- |
| `.github/` | CI workflow | tracked | configuration | Low risk; small and appropriate. | keep |
| `.gitignore` | Ignore policy for raw data, outputs, credentials, caches | tracked | configuration | Comments display mojibake in this checkout; policy itself is useful. | keep; later repair comments only |
| `README.md` | Main project identity, quickstart, capabilities | tracked | documentation | Appropriate at root. | keep |
| `CHANGELOG.md` | Version history | tracked | documentation | Appropriate at root. | keep |
| `TESTING.md` | Test-running notes | tracked | documentation | Could stay root or move to `docs/guides/`; root is acceptable if short. | keep for now |
| `requirements.txt` | Runtime/test dependencies | tracked | configuration | No `pyproject.toml`; current style is simple but workable. | keep |
| `PROJECT_AUDIT.md` | Historical project inventory | tracked | documentation / audit | Root clutter; useful record but not core landing document. | move candidate to `docs/audits/` |
| `CLEANUP_PLAN.md` | Cleanup planning record | tracked | documentation / plan | Root clutter; useful historical plan. | move candidate to `docs/plans/` |
| `CLEANUP_EXECUTION_LOG.md` | Cleanup execution log | tracked | documentation / log | Root clutter; useful historical record. | move candidate to `docs/archive/cleanup/` |
| `COMMIT_BOUNDARY_REVIEW.md` | Commit boundary review | tracked | documentation / audit | Root clutter; useful historical review. | move candidate to `docs/audits/` |
| `STAGING_PLAN.md` | Commit staging plan | tracked | documentation / plan | Root clutter; historical and less useful after commit. | archive candidate |
| `configs/` | Config examples/local configs | ignored by `.git/info/exclude`; not tracked | local-only / configuration | Local-only policy is not communicated to other clones because it is in `.git/info/exclude`. `data_sources.example.yaml` may be valuable as tracked example. | inspect manually; consider `.gitignore` and example policy later |
| `data/` | sample, raw policy, processed summaries, case-study docs | mixed tracked and ignored | data / docs / generated artifacts | Clear subfolders, but `data/raw` has tracked old sample CSVs despite raw ignore policy. | keep now; review data contract |
| `docs/` | Architecture, specs, audits, output policy, images | tracked | documentation | Good home for most non-root documents; may need subfolders. | keep and organize later |
| `notebooks/` | Battery preprocessing/inspection templates | ignored by `.git/info/exclude`; not tracked | local-only / workflow templates | Policy is local-only and not visible to other clones. Templates may be worth tracking or moving to `scripts/`. | inspect manually |
| `outputs/` | Analyzer run outputs | ignored by `.gitignore` | generated artifacts | Many local smoke/test runs exist; ignored correctly. | keep local or prune later |
| `scripts/` | Workflow scripts and utilities | tracked | source / CLI utilities | Growing dataset-specific script set. | keep; later consider subfolders |
| `src/` | Core platform source, analyzers, connectors, loaders | tracked | source | Responsibilities are mostly clear. | keep |
| `tests/` | Unit and integration-ish tests | tracked | test support | Structure is still manageable. | keep |
| `.pytest_cache/`, `__pycache__/` | Python caches | ignored | temporary | Correctly ignored. | ignore |

Current tracked tree highlights:

```text
.
|-- README.md
|-- CHANGELOG.md
|-- TESTING.md
|-- PROJECT_AUDIT.md
|-- CLEANUP_PLAN.md
|-- CLEANUP_EXECUTION_LOG.md
|-- COMMIT_BOUNDARY_REVIEW.md
|-- STAGING_PLAN.md
|-- requirements.txt
|-- .github/workflows/ci.yml
|-- docs/
|-- scripts/
|-- src/
|   |-- analyzers/
|   |-- connectors/
|   `-- loaders/
|-- tests/
`-- data/
    |-- sample/
    |-- raw/
    |-- processed/
    `-- case_studies/
```

`git status --short` before creating this audit was clean. `git status --ignored --short` showed ignored local/generated paths including `.pytest_cache/`, `configs/`, `notebooks/`, `outputs/`, `data/raw/battery_archive/`, `data/raw/kaggle/`, `data/raw/materials_project/`, and `data/processed/materials_project_fe_si.csv`.

## 2. Root-level File Audit

Root files inspected:

| file | classification | recommendation | target path if moved | reason |
| --- | --- | --- | --- | --- |
| `.gitignore` | must stay root | keep | root | Git ignore rules must stay root-level. |
| `README.md` | must stay root | keep | root | Primary public entry point. |
| `CHANGELOG.md` | should stay root | keep | root | Conventional release-history location. |
| `requirements.txt` | must stay root for current workflow | keep | root | Current install/test instructions depend on it. |
| `TESTING.md` | root acceptable | keep or move | `docs/guides/TESTING.md` | It is short and useful; move only if docs are reorganized. |
| `PROJECT_AUDIT.md` | audit record | move | `docs/audits/PROJECT_AUDIT.md` | Useful but clutters root. |
| `COMMIT_BOUNDARY_REVIEW.md` | audit record | move | `docs/audits/COMMIT_BOUNDARY_REVIEW.md` | Useful commit policy record. |
| `CLEANUP_PLAN.md` | plan record | move | `docs/plans/CLEANUP_PLAN.md` | Planning record belongs under docs. |
| `CLEANUP_EXECUTION_LOG.md` | execution log | archive | `docs/archive/cleanup/CLEANUP_EXECUTION_LOG.md` | Historical cleanup log, not a root landing doc. |
| `STAGING_PLAN.md` | historical plan | archive or move | `docs/archive/cleanup/STAGING_PLAN.md` | Useful for history, not for everyday users. |

Recommended root policy:

- Keep root focused on `README.md`, `CHANGELOG.md`, `TESTING.md` or a docs link, `requirements.txt`, `.gitignore`, `.github/`, `src/`, `scripts/`, `tests/`, `data/`, and `docs/`.
- Move audit/cleanup/staging records under `docs/audits/`, `docs/plans/`, or `docs/archive/cleanup/`.
- Do not delete root documents in the first cleanup pass; move and repair links first.

## 3. Documentation Structure Audit

Current documentation types:

| path | type | recommendation | target path |
| --- | --- | --- | --- |
| `README.md` | project overview / quickstart | keep | root |
| `CHANGELOG.md` | release notes | keep | root |
| `TESTING.md` | testing guide | keep or move | root or `docs/guides/TESTING.md` |
| `docs/PROJECT_STRUCTURE.md` | architecture documentation | keep | `docs/architecture/PROJECT_STRUCTURE.md` optional later |
| `docs/OUTPUTS_POLICY.md` | generated artifact policy | keep | `docs/guides/OUTPUTS_POLICY.md` optional later |
| `docs/V0_9_VIRTUAL_EXPERIMENT_SCREENING_SPEC.md` | version specification | keep | `docs/specifications/` |
| `docs/V1_1_BATTERY_ARCHIVE_CASE_STUDY_SPEC.md` | version specification | keep | `docs/specifications/` |
| `docs/V1_0_RELEASE_READINESS_AUDIT.md` | audit | keep | `docs/audits/` |
| `docs/BATTERY_ARCHIVE_DATA_AUDIT.md` | audit | keep | `docs/audits/` |
| `PROJECT_AUDIT.md` | audit | move | `docs/audits/` |
| `COMMIT_BOUNDARY_REVIEW.md` | audit | move | `docs/audits/` |
| `CLEANUP_PLAN.md` | plan | move | `docs/plans/` |
| `STAGING_PLAN.md` | plan/history | archive | `docs/archive/cleanup/` |
| `CLEANUP_EXECUTION_LOG.md` | execution log | archive | `docs/archive/cleanup/` |
| `data/case_studies/*` | case-study documentation | keep | current location |
| `docs/case_studies/*` | case-study template docs | keep | current or `docs/guides/case_studies/` |
| `docs/images/*` | README/example images | keep | current location |

Suggested docs structure for a later cleanup:

```text
docs/
  architecture/
    PROJECT_STRUCTURE.md
  audits/
    BATTERY_ARCHIVE_DATA_AUDIT.md
    V1_0_RELEASE_READINESS_AUDIT.md
    PROJECT_AUDIT.md
    COMMIT_BOUNDARY_REVIEW.md
    REPOSITORY_ROOT_AND_ARCHITECTURE_AUDIT.md
  specifications/
    V0_9_VIRTUAL_EXPERIMENT_SCREENING_SPEC.md
    V1_1_BATTERY_ARCHIVE_CASE_STUDY_SPEC.md
  guides/
    OUTPUTS_POLICY.md
    TESTING.md
  case_studies/
  images/
  archive/
    cleanup/
      CLEANUP_EXECUTION_LOG.md
      CLEANUP_PLAN.md
      STAGING_PLAN.md
```

Do not over-split immediately. The practical first move is root cleanup: relocate root audit/planning documents and repair links.

## 4. Source Architecture Audit

The source architecture mostly follows the intended responsibility boundaries.

### connectors

Responsibility: external source discovery, API or zip access, raw-file inventory, and credentials-safe ingestion boundaries.

Current files:

- `src/connectors/base.py`: `BaseConnector`, `IngestionResult`.
- `src/connectors/kaggle_connector.py`: Kaggle dataset access wrapper.
- `src/connectors/materials_project_connector.py`: Materials Project access and simple tabular conversion.
- `src/connectors/htem_connector.py`: HTEM connector skeleton/local handling.
- `src/connectors/battery_archive_connector.py`: Battery Archive connector, zip inventory discovery, cycle file inventory, filename metadata enrichment.

Assessment:

- The connector boundary is sound for API/raw discovery.
- Battery Archive v1.1.1 belongs in connector because zip inventory is raw-source discovery.
- Battery Archive v1.1.2 filename metadata enrichment is still acceptable in connector because it uses inventory path metadata only and does not parse cycle CSV contents.
- If Battery Archive grows into schema normalization, capacity calculations, or cycle summary generation, those parts should move to a loader module such as `src/loaders/battery_archive_cycle_loader.py`.

### loaders

Responsibility: actual data parsing, schema normalization, processed table creation, and analysis-ready summaries.

Current files:

- `src/loaders/battery_loader.py`: NASA `.mat` battery discharge cycle extraction.
- `src/loaders/kaggle_battery_metadata_loader.py`: Kaggle metadata discharge summary, quality flags, analysis-ready filtering.
- `src/loaders/kaggle_battery_discharge_features.py`: raw discharge CSV feature extraction and merge.

Assessment:

- Loaders are currently dataset-specific and appropriate.
- Battery Archive v1.1.3 cycle CSV schema audit/loading should be loader-owned, not connector-owned.
- Loader code should keep raw row-level time-series data out of processed summaries unless explicitly producing features.

### analyzers

Responsibility: domain-independent tabular analysis.

Current modules:

- `src/analyzers/eda.py`
- `src/analyzers/process.py`
- `src/analyzers/reliability.py`
- `src/analyzers/smart_factory.py`
- `src/analyzers/spc.py`
- `src/analyzers/simulation.py`

Assessment:

- Analyzer modules represent the core platform.
- `simulation.py` is large, but it is the central virtual experiment screening engine. Split only when adding real pressure, for example `candidate_validation.py`, `domain_warnings.py`, or `ranking.py`.
- Battery-specific logic should not enter analyzers.

### reports

Responsibility: Markdown formatting and report generation.

Current files:

- `src/reports.py`: report builders for EDA/process/reliability/SPC/smart_factory/simulation.
- `src/visualization.py`: plot generation.
- `src/results.py`: request/result dataclasses for future service/API use.

Assessment:

- `reports.py` is long but coherent.
- If report logic grows further, split by mode later; no need before v1.1.3.

### scripts

Responsibility: CLI orchestration and one-off workflow utilities.

Assessment:

- Scripts are useful, but the folder is becoming mixed: Battery Archive, Kaggle, ingestion, inspection, comparison utilities all sit together.
- Do not move now. Consider subfolders once there are more than two scripts per data source.

## 5. Scripts Audit

| script | purpose | dataset-specific? | reusable? | recommended position |
| --- | --- | --- | --- | --- |
| `scripts/inspect_processed_data.py` | Lightweight processed CSV inspection | no | yes | keep in `scripts/` or later `scripts/maintenance/` |
| `scripts/compare_simulation_runs.py` | Compare multiple simulation run outputs | no, but used by Kaggle case study | yes | keep in `scripts/` |
| `scripts/ingest_data.py` | Connector ingestion entry script | no | yes | keep in `scripts/` |
| `scripts/build_kaggle_battery_summary.py` | Build Kaggle NASA battery metadata summary | yes | case-study workflow | later `scripts/kaggle/` |
| `scripts/build_kaggle_battery_discharge_features.py` | Extract Kaggle discharge raw CSV features | yes | case-study workflow | later `scripts/kaggle/` |
| `scripts/build_battery_archive_cycle_inventory.py` | Build Battery Archive cycle file inventory | yes | case-study workflow | later `scripts/battery_archive/` |
| `scripts/enrich_battery_archive_cycle_inventory.py` | Enrich Battery Archive inventory with filename metadata | yes | case-study workflow | later `scripts/battery_archive/` |

Potential future script structure:

```text
scripts/
  maintenance/
    inspect_processed_data.py
    compare_simulation_runs.py
  ingestion/
    ingest_data.py
  kaggle/
    build_kaggle_battery_summary.py
    build_kaggle_battery_discharge_features.py
  battery_archive/
    build_battery_archive_cycle_inventory.py
    enrich_battery_archive_cycle_inventory.py
```

Do not move scripts until import paths, README examples, and tests are updated in the same cleanup phase.

## 6. Data Directory Contract Audit

### `data/raw/`

Current state:

- `.gitignore` ignores `data/raw/**` but explicitly allows `data/raw/README.md`.
- Tracked: `data/raw/README.md`.
- Tracked legacy/sample-like CSVs: `data/raw/experiment_process.csv`, `data/raw/experiment_reliability.csv`, `data/raw/factory_log.csv`.
- Ignored local raw folders: `data/raw/battery/`, `data/raw/battery_archive/`, `data/raw/htem/`, `data/raw/kaggle/`, `data/raw/materials_project/`.

Policy recommendation:

- Raw downloaded datasets should stay ignored and local-only.
- Keep `data/raw/README.md`.
- Review the three tracked `data/raw/*.csv` files. They look like old sample/demo data and may belong only in `data/sample/`; do not delete without checking historical references.

### `data/sample/`

Current state:

- Tracked synthetic samples: `candidate_conditions.csv`, `experiment_process.csv`, `experiment_reliability.csv`, `factory_log.csv`, `simulation_scenarios.csv`, `README.md`.

Policy recommendation:

- Keep tracked.
- This is the correct home for quickstart/test/demo CSVs.
- Ensure README continues to state that samples are synthetic demonstration datasets, not real experimental results.

### `data/processed/`

Current state:

| file | size | status observed | classification | recommendation |
| --- | ---: | --- | --- | --- |
| `README.md` | 1.8 KB | tracked | documentation | keep |
| `battery_archive_cycle_file_inventory.csv` | 32.5 KB | tracked | reproducibility artifact | keep |
| `battery_archive_cycle_file_inventory_enriched.csv` | 62.5 KB | tracked | reproducibility artifact | keep |
| `kaggle_battery_simulation_comparison.csv` | 3.4 KB | tracked | durable curated artifact | keep |
| `kaggle_nasa_battery_quality_summary.csv` | 3.4 KB | tracked | durable curated artifact | keep |
| `kaggle_nasa_battery_cycle_summary.csv` | 314.3 KB | tracked | full audit artifact | keep if case study reproducibility matters |
| `kaggle_nasa_battery_cycle_summary_analysis_ready.csv` | 277.6 KB | tracked | analysis-ready artifact | keep |
| `kaggle_nasa_battery_discharge_features.csv` | 588.0 KB | tracked | feature artifact | keep if case study should be reproducible without raw CSVs |
| `kaggle_nasa_battery_analysis_ready_with_features.csv` | 783.1 KB | tracked | analysis-ready feature artifact | keep, but monitor repository size |
| `materials_project_fe_si.csv` | 5.4 KB | ignored via `.git/info/exclude` | local-only result | review; either document as local-only or make curated sample intentionally |

Policy recommendation:

- Treat small, curated, case-study summaries as commit-eligible reproducibility artifacts.
- Treat connector API results and ad hoc generated files as local-only unless documented as a case-study output.
- Avoid committing large raw or full time-series data.

### `data/case_studies/`

Current state:

- Tracked case-study documentation for battery, Battery Archive, HTEM, Kaggle battery, and Materials Project.
- Kaggle battery has the most complete report set.
- Battery Archive currently has `source.md` only; richer case-study docs should wait until v1.1.3+.

Policy recommendation:

- Keep.
- Case-study docs are public-facing demonstration material, not core platform code.

## 7. Configs and Notebooks Policy

Observed state:

- `configs/data_sources.example.yaml` exists locally but is ignored by `.git/info/exclude`.
- `notebooks/battery_preprocessing.py` and `notebooks/inspect_battery_mat.py` exist locally but are ignored by `.git/info/exclude`.
- `git check-ignore -v` confirmed:
  - `configs/data_sources.example.yaml` ignored by `.git/info/exclude:9:configs/`
  - `notebooks/battery_preprocessing.py` ignored by `.git/info/exclude:8:notebooks/`

Risk:

- `.git/info/exclude` is local-only. Other clones will not know that `configs/` and `notebooks/` are intended to be ignored.
- If `configs/data_sources.example.yaml` is meant as a non-sensitive example, ignoring the entire directory hides useful onboarding material.
- If notebooks are local-only experiments, the policy should be visible in `.gitignore` or docs.

Recommendation:

- Later decide between:
  - track `configs/data_sources.example.yaml` and ignore only `configs/*.local.yaml`, or
  - keep all configs local-only but document that policy.
- For notebooks:
  - keep ignored if notebooks are scratch work, or
  - track only `.py` templates / README while ignoring executed `.ipynb` notebooks.
- Do not copy sensitive values from local configs into documentation.

## 8. Tests Structure Audit

Current test structure:

| test file | coverage area |
| --- | --- |
| `tests/test_data_io.py` | CSV loading/output helpers |
| `tests/test_preprocessing.py` | cleaning behavior |
| `tests/test_data_readiness.py` | schema mapping, constraints, validation |
| `tests/test_eda_io.py` | EDA outputs |
| `tests/test_process.py` | process analysis |
| `tests/test_spc.py` | SPC behavior |
| `tests/test_simulation.py` | simulation, candidate validation, warnings, ranking, reports |
| `tests/test_results.py` | AnalysisRequest/AnalysisResult |
| `tests/test_connectors_base.py` | connector base structures |
| `tests/test_kaggle_connector.py` | Kaggle connector |
| `tests/test_materials_project_connector.py` | Materials Project connector |
| `tests/test_htem_connector.py` | HTEM connector |
| `tests/test_battery_archive_connector.py` | Battery Archive zip inventory and metadata parser |
| `tests/test_battery_loader.py` | NASA `.mat` battery loader |
| `tests/test_kaggle_battery_metadata_loader.py` | Kaggle battery metadata loader |
| `tests/test_kaggle_battery_discharge_features.py` | Kaggle discharge feature extraction |
| `tests/test_compare_simulation_runs.py` | comparison utility |
| `tests/test_inspect_processed_data.py` | processed data inspection script |

Assessment:

- Test files map reasonably to source modules and scripts.
- `tests/test_simulation.py` is large because simulation mode is feature-rich; this is acceptable for now but may later split into candidate validation, OOD/domain warnings, ranking, and report tests.
- Script tests are mixed into root tests but still manageable.
- No immediate test folder reorganization is required.

## 9. Windows Test Environment Audit

Observed issue:

- Recent runs used a repository-local temporary directory for `TEMP`/`TMP` because the default Windows temp path can hit `PermissionError` for pytest temp fixtures in this environment.
- The audit run used `.pytest_tmp_audit`, removed it after pytest, and did not leave a Git-visible temporary directory.

Options:

| option | recommendation | notes |
| --- | --- | --- |
| Document the command only | acceptable short-term | Lowest change. Add to `TESTING.md` later. |
| Add `scripts/run_tests.ps1` | recommended later | Makes local/CI parity clearer without changing Python code. |
| Configure pytest `--basetemp` in `pyproject.toml`/`pytest.ini` | defer | Fixed basetemp can cause stale-folder/parallel-run issues. |
| Hide issue inside tests | avoid | Environment-specific behavior should not be embedded in test logic. |

Suggested future PowerShell pattern:

```powershell
$tmp = Join-Path (Get-Location).Path ".pytest_tmp"
if (Test-Path -LiteralPath $tmp) { Remove-Item -LiteralPath $tmp -Recurse -Force }
New-Item -ItemType Directory -Path $tmp | Out-Null
$env:TEMP = $tmp
$env:TMP = $tmp
try {
  python -m pytest
} finally {
  if (Test-Path -LiteralPath $tmp) { Remove-Item -LiteralPath $tmp -Recurse -Force }
}
```

If this becomes standard, add `.pytest_tmp*/` to `.gitignore` in a future cleanup phase.

## 10. Packaging and Entry-point Audit

Current state:

- Main CLI entry point is `python src/process_data.py ...`.
- No `pyproject.toml`.
- No `setup.py`.
- Dependencies are in `requirements.txt`.
- CI exists at `.github/workflows/ci.yml`.

Assessment:

- Keeping direct script execution is fine for v1.1.
- A package migration is not required before Battery Archive v1.1.3.
- Moving to `pyproject.toml` and console scripts would be cleaner long-term, but it would change install/run assumptions and should not be mixed with repository cleanup.

Recommendation:

- Do not start packaging migration in the same phase as docs/root cleanup.
- Consider `pyproject.toml` only when public installation or CLI distribution becomes a concrete goal.

## 11. Proposed Target Repository Tree

### Minimal Cleanup Tree

This is the recommended next cleanup target because it minimizes import changes.

```text
materials_data_analyzer/
  README.md
  CHANGELOG.md
  TESTING.md
  requirements.txt
  .gitignore
  .github/
  src/
  tests/
  scripts/
  data/
    sample/
    raw/
    processed/
    case_studies/
  docs/
    PROJECT_STRUCTURE.md
    OUTPUTS_POLICY.md
    audits/
    plans/
    archive/
    specifications/
    case_studies/
    images/
```

### Long-term Architecture Tree

This is a later v1.x direction, not an immediate task.

```text
materials_data_analyzer/
  pyproject.toml
  src/
    materials_data_analyzer/
      analyzers/
      connectors/
      loaders/
      reporting/
      cli/
  scripts/
    maintenance/
    battery_archive/
    kaggle/
    ingestion/
  tests/
    analyzers/
    connectors/
    loaders/
    scripts/
    integration/
  docs/
    architecture/
    audits/
    guides/
    specifications/
    archive/
  data/
    sample/
    processed/
    case_studies/
```

Do not apply the long-term tree immediately. It requires import updates, CLI documentation changes, and a dedicated migration test pass.

## 12. Exact Cleanup Action Table

| priority | current path | action | target path | reason | import impact | documentation link impact | test impact | risk | verification command |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| P0 | `README.md` | keep | root | Main landing page | none | none | none | low | `python -m pytest` |
| P0 | `CHANGELOG.md` | keep | root | Release history | none | none | none | low | `git status --short` |
| P0 | `requirements.txt` | keep | root | Current dependency contract | none | none | none | low | `python -m pytest` |
| P0 | `.gitignore` | inspect manually | root | Comments mojibake; policy useful | none | none | none | low if comment-only | `git check-ignore -v data/raw/battery_archive/CALCE.zip outputs/sample_virtual_experiment_v094_smoke` |
| P0 | `data/raw/` | ignore | same | Local/raw downloaded data | none | docs only | none | high if accidentally committed | `git check-ignore -v data/raw/battery_archive/CALCE.zip` |
| P0 | `outputs/` | ignore | same | Regenerable analyzer outputs | none | docs only | none | medium if representative outputs deleted locally | `git check-ignore -v outputs/sample_virtual_experiment_v094_smoke` |
| P1 | `PROJECT_AUDIT.md` | move | `docs/audits/PROJECT_AUDIT.md` | Root cleanup | none | update links if any | none | low | `rg "PROJECT_AUDIT" .` |
| P1 | `COMMIT_BOUNDARY_REVIEW.md` | move | `docs/audits/COMMIT_BOUNDARY_REVIEW.md` | Root cleanup | none | update links if any | none | low | `rg "COMMIT_BOUNDARY_REVIEW" .` |
| P1 | `CLEANUP_PLAN.md` | move | `docs/plans/CLEANUP_PLAN.md` | Root cleanup | none | update links if any | none | low | `rg "CLEANUP_PLAN" .` |
| P1 | `CLEANUP_EXECUTION_LOG.md` | archive | `docs/archive/cleanup/CLEANUP_EXECUTION_LOG.md` | Historical log | none | update links if any | none | low | `rg "CLEANUP_EXECUTION_LOG" .` |
| P1 | `STAGING_PLAN.md` | archive | `docs/archive/cleanup/STAGING_PLAN.md` | Historical staging plan | none | update links if any | none | low | `rg "STAGING_PLAN" .` |
| P1 | `TESTING.md` | keep or move | root or `docs/guides/TESTING.md` | Useful user guide | none | update README if moved | none | low | `rg "TESTING.md|Testing" README.md docs` |
| P1 | `configs/data_sources.example.yaml` | inspect manually | maybe root-tracked under `configs/` | Example config may help users | none | README/docs if tracked | none | medium if secrets copied | `git status --ignored --short configs` |
| P1 | `notebooks/` | inspect manually | maybe keep ignored or move templates to scripts/docs | Current policy local-only | none | docs if policy changes | none | medium if notebooks have local paths | `git status --ignored --short notebooks` |
| P2 | `scripts/build_kaggle_battery_summary.py` | move candidate | `scripts/kaggle/` | Script folder clarity | CLI docs/tests need update | README/case docs update | script tests may need cwd updates | medium | `python -m pytest` |
| P2 | `scripts/build_kaggle_battery_discharge_features.py` | move candidate | `scripts/kaggle/` | Script folder clarity | CLI docs/tests need update | case docs update | tests update | medium | `python -m pytest` |
| P2 | `scripts/build_battery_archive_cycle_inventory.py` | move candidate | `scripts/battery_archive/` | Script folder clarity | CLI docs/tests need update | docs/spec update | tests update | medium | `python -m pytest tests/test_battery_archive_connector.py` |
| P2 | `scripts/enrich_battery_archive_cycle_inventory.py` | move candidate | `scripts/battery_archive/` | Script folder clarity | CLI docs/tests need update | docs/spec update | tests update | medium | `python -m pytest tests/test_battery_archive_connector.py` |
| P2 | `src/connectors/battery_archive_connector.py` | keep now | same | Correct for zip inventory and filename metadata | none | none | none | low | `python -m pytest tests/test_battery_archive_connector.py` |
| P2 | future Battery Archive cycle CSV loader | add later | `src/loaders/battery_archive_cycle_loader.py` | Cycle CSV parsing belongs in loaders | new imports | docs/spec update | new tests | medium | future v1.1.3 tests |
| P2 | `data/raw/experiment_process.csv`, `data/raw/experiment_reliability.csv`, `data/raw/factory_log.csv` | inspect manually | maybe remove or move if duplicated in `data/sample/` | Raw policy conflict | none if unused | docs update | unknown | medium | `rg "data/raw/(experiment_process|experiment_reliability|factory_log)" .` |
| P2 | `data/processed/materials_project_fe_si.csv` | inspect manually | maybe commit as curated artifact or leave ignored | Ignored local processed file | none | case docs update if kept | none | low | `git check-ignore -v data/processed/materials_project_fe_si.csv` |

## 13. Cleanup Phases

### Phase A: policy and root documentation cleanup

Files: root audit/plan/log documents, `.gitignore` comments, `TESTING.md`.

Actions:

- Move root audit/planning docs into `docs/audits/`, `docs/plans/`, and `docs/archive/cleanup/`.
- Repair README/docs links if any.
- Keep README content stable unless link updates are needed.

Risk: broken links, user confusion if documents disappear from root.  
Verification: `rg "PROJECT_AUDIT|CLEANUP_PLAN|COMMIT_BOUNDARY_REVIEW|STAGING_PLAN|CLEANUP_EXECUTION_LOG" .`, `python -m pytest`, `git status --short`.

### Phase B: docs relocation and link repair

Files: `docs/PROJECT_STRUCTURE.md`, `docs/OUTPUTS_POLICY.md`, version specs, audits.

Actions:

- Optionally introduce `docs/audits/`, `docs/specifications/`, `docs/guides/`, `docs/archive/`.
- Move docs in small groups.
- Repair links immediately.

Risk: link rot.  
Verification: `rg "docs/" README.md docs data/case_studies`, `python -m pytest`.

### Phase C: data/processed policy cleanup

Files: `data/processed/*.csv`, `data/processed/README.md`.

Actions:

- Keep curated Kaggle and Battery Archive processed artifacts if public case-study reproducibility is a goal.
- Decide whether `materials_project_fe_si.csv` is local-only or curated.
- Do not delete processed case-study artifacts before confirming reproducibility story.

Risk: losing case-study reproducibility or accidentally committing local API outputs.  
Verification: `git ls-files data/processed`, `git status --ignored --short data/processed`.

### Phase D: scripts/source responsibility cleanup

Files: `scripts/*.py`, `src/connectors/*`, `src/loaders/*`.

Actions:

- Do not move scripts until root/docs cleanup is stable.
- If script subfolders are created, update tests, docs, and command examples in the same commit.
- For Battery Archive v1.1.3, put cycle CSV content parsing in loaders.

Risk: broken commands and script tests.  
Verification: `python -m pytest`, plus smoke commands documented in relevant specs.

### Phase E: Windows test runner standardization

Files: `TESTING.md`, optional future `scripts/run_tests.ps1`, optional `.gitignore`.

Actions:

- Document the repo-local TEMP/TMP workaround.
- Consider adding a small PowerShell runner.
- Add `.pytest_tmp*/` ignore only if a runner is introduced.

Risk: stale temp folders, hiding local permission issues too deeply.  
Verification: `python -m pytest` via the documented command, `git status --ignored --short`.

### Phase F: final verification

Run:

```powershell
python -m pytest
git diff --check
git status --short
git status --ignored --short
```

Also run any README quickstart or case-study smoke commands affected by path changes.

## 14. Stop Conditions

Stop cleanup and ask for confirmation if any of the following are required:

- deleting tracked data files;
- changing public import paths;
- changing CLI commands;
- changing existing output schemas;
- deleting root documents rather than moving them;
- deleting local configs or notebooks;
- rewriting Git history;
- moving scripts without updating tests/docs in the same phase;
- changing `.gitignore` in a way that could accidentally expose raw data or credentials.

## 15. Recommended Next Step

Recommended next step: perform a small root documentation cleanup before starting v1.1.3a schema audit.

Reasoning:

- The core platform and Battery Archive v1.1.1/v1.1.2 are stable.
- The root now contains too many historical audit/plan files, which makes the project look less polished than the code actually is.
- v1.1.3a will add more Battery Archive planning/output, so root/docs boundaries should be clarified first.
- Do not run root cleanup and schema audit in the same step. Keep cleanup mechanical and easy to review.

Suggested immediate task:

1. Move root audit/planning files into `docs/audits/`, `docs/plans/`, and `docs/archive/cleanup/`.
2. Repair links.
3. Add or update a docs index if needed.
4. Run `python -m pytest`, `git diff --check`, and `git status --short`.

## 16. Non-goals

This audit did not perform or recommend doing these within the audit step:

- code refactor;
- file move;
- file delete;
- import update;
- README rewrite;
- `.gitignore` modification;
- Battery Archive schema audit;
- cycle CSV loading;
- Materials Project integration;
- new feature development;
- commit or push.

## 17. Validation

Commands run for this audit:

```powershell
git ls-files
git status --short
git status --ignored --short
git check-ignore -v data/raw/battery_archive/CALCE.zip data/raw/kaggle data/raw/materials_project/mp_fe_si_raw.json outputs/sample_virtual_experiment_v094_smoke configs/data_sources.example.yaml configs/local.yaml notebooks/battery_preprocessing.py data/processed/materials_project_fe_si.csv .pytest_cache/foo
python -m pytest
git diff --check
```

Pytest result:

```text
112 passed in 13.17s
```

Pytest TEMP/TMP method used:

```powershell
$tmp = Join-Path (Get-Location).Path ".pytest_tmp_audit"
$env:TEMP = $tmp
$env:TMP = $tmp
python -m pytest
```

The temporary directory was removed after the run.

`git diff --check` result:

```text
passed with no output
```

`git status --short` before this audit document was created:

```text
(clean)
```

Final `git status --short` after this audit document was created:

```text
?? docs/REPOSITORY_ROOT_AND_ARCHITECTURE_AUDIT.md
```

Generated file:

```text
docs/REPOSITORY_ROOT_AND_ARCHITECTURE_AUDIT.md
```
