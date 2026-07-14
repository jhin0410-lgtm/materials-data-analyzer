# Platform Adapters

Status: `scaffold_stage` for v2.0.4.

Adapters are a thin metadata layer between the v2 platform registry and the
existing case-study scripts. The scripts in `scripts/` remain canonical.
v2.0.3 approves only one read-only verification callable; general script
execution remains disabled.

## Execution Boundary

Allowed in the current scaffold:

- list adapter metadata
- validate configs that reference registered adapter IDs
- build dry-run plans
- write one local dry-run manifest when requested
- execute `reliability_trust_closeout` in verify mode
- inspect and validate that manifest

Not allowed in the current scaffold:

- acquisition
- raw data reads
- normalization
- model training
- trust script execution
- subprocess or shell execution
- arbitrary import paths from user config
- filesystem-wide plugin discovery

## Current Adapter Matrix

| Adapter | Plugin | Stage | Status | Script metadata |
| --- | --- | --- | --- | --- |
| `materials_project_trust_closeout` | `materials_project` | `trust` | `executable_disabled` | `scripts/run_materials_project_v1_3_trust_analysis.py` |
| `smart_factory_trust_closeout` | `smart_factory` | `trust` | `executable_disabled` | `scripts/run_smart_factory_v1_4_trust_analysis.py` |
| `reliability_trust_closeout` | `reliability` | `trust` | `verify_allowed` | `scripts/run_reliability_v1_5_trust_analysis.py` metadata; approved callable is `src/platform_core/case_adapters/reliability.py` |

Battery Archive remains `scaffolded` because its closeout workflow is not yet
mapped to the same trust-policy adapter contract.

v2.0.4 adds a separate case-study interface registry. That registry describes
domain and lifecycle coverage; it does not make these adapters executable.

## Script Inventory

| Stage | Existing script examples | v2.0.2 decision |
| --- | --- | --- |
| acquisition | `acquire_materials_project_v1_3.py`, `build_smart_factory_v1_4_acquisition.py`, `build_reliability_v1_5_acquisition.py` | metadata only; not executable |
| normalization | `build_materials_project_normalized.py`, `build_smart_factory_v1_4_analysis_ready.py`, `build_reliability_v1_5_full_year.py` | metadata only; not executable |
| readiness | `inspect_materials_project_v1_3_readiness.py` and case-study readiness scripts | metadata only |
| feature_build | `build_materials_project_v1_3_descriptors.py`, `run_reliability_v1_5_classification.py` feature cache step | future adapter work |
| validation | `run_materials_project_v1_3_validation.py`, `run_smart_factory_v1_4_classification.py` | metadata only; model execution disabled |
| trust | v1.3/v1.4/v1.5 trust scripts | mapped as manifest-only adapters |
| closeout | case-study documentation builders | future adapter work |
| utility | `compare_simulation_runs.py`, `inspect_processed_data.py`, `run_tests.ps1` | not platform adapters |

## Manifest-Only Flow

```powershell
python -m src.cli validate-config configs/examples/reliability_trust_manifest_dry_run.json
python -m src.cli dry-run configs/examples/reliability_trust_manifest_dry_run.json --write-manifest
python -m src.cli validate-manifest outputs/platform_runs/reliability-trust-manifest-dry-run/run_manifest.json
python -m src.cli show-manifest outputs/platform_runs/reliability-trust-manifest-dry-run/run_manifest.json
```

The manifest is written under `outputs/`, which is local-only. It records
adapter ID, config hash, required artifacts, expected outputs, execution
boundary, and trust claim boundary. It does not store credentials, host paths,
usernames, raw rows, or API responses.

## Adding A Future Adapter

Future adapters should:

- register an explicit adapter ID
- reference existing artifact IDs instead of raw paths
- keep module path and callable name as metadata until execution is approved
- declare network, raw-data, model-training, and output-write requirements
- remain dry-run-safe before any executable mode is introduced
- add tests for config validation, dry-run planning, manifest writing, and
  security boundaries
