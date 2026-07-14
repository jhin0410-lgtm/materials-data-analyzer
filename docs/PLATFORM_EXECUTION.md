# Platform Execution

Status: `development_stage` for v2.1.1.

v2.0.3 introduces controlled adapter execution for one narrow case:
`reliability_trust_closeout` in `verify` mode. It verifies existing tracked
compact reliability trust artifacts and writes a local run manifest plus
verification reports under `outputs/platform_runs/`.

## Execution Boundary

Allowed now:

- `reliability_trust_closeout` with `execution_mode=verify`
- tracked compact artifact reads through registered artifact IDs
- local output under `outputs/platform_runs/<run_id>/`
- terminal manifest writing
- verification report writing
- side-effect report writing

Still disabled:

- acquisition
- normalization
- feature build
- model training
- raw data reads
- row-level prediction reads
- canonical tracked output overwrite
- process spawning
- shell commands
- arbitrary dynamic imports
- user-provided module or callable paths
- Materials Project and Smart Factory adapter execution

## Allowlist

Executable permission is code-registered in
`src/platform_core/execution_policy.py`.

| Adapter | Mode | Status |
| --- | --- | --- |
| `reliability_trust_closeout` | `verify` | allowed |
| `materials_project_trust_closeout` | none | blocked |
| `smart_factory_trust_closeout` | none | blocked |

Config files cannot elevate network, raw data, model training, process
spawning, or canonical overwrite permissions.

## Verify Mode

Verify mode reads existing tracked compact artifacts and checks trust-boundary
facts such as:

- representative model remains `none_selected`
- SHAP remains `deferred_not_justified`
- survival/RUL remain `deferred_not_ready`
- production and calibrated probability claims remain prohibited
- no raw serial identifiers, credentials, or absolute host paths appear in the
  compact trust artifacts

Verify mode does not recompute scientific results. It does not run the v1.5
trust script because that canonical script can check local raw archive SHA.

## Isolated Run Mode

`isolated_run` is deferred in v2.0.3. It should only be enabled after an
adapter can safely inject an output directory and compare isolated outputs
against canonical compact artifacts without overwriting tracked files.

## Manifest Lifecycle

Executable manifests use these terminal and lifecycle statuses:

- `planned`
- `preflight_validated`
- `execution_started`
- `execution_completed`
- `verification_completed`
- `blocked`
- `failed`
- `side_effect_violation`

Manifests are local-only and include config SHA, adapter policy version,
input/output checksums, produced local files, side-effect status, and claim
boundary. They do not store credentials, usernames, hostnames, or absolute
paths.

v2.1.1 can optionally ingest terminal manifests into the local run registry
with `--register-run`. Registration records metadata only and never changes
the adapter's execution permission or scientific result.

## Side-Effect Guard

The runtime snapshots protected compact artifact hashes and repository file
inventory outside the allowed output directory. After execution it checks:

- protected compact artifact SHA changes
- new files outside the allowed output directory
- output file count and byte limits
- tracked-file metadata changes detected from the Git index

Only files under `outputs/platform_runs/<run_id>/` are allowed.

## CLI

```powershell
python -m src.cli list-executable-adapters
python -m src.cli show-execution-policy reliability_trust_closeout
python -m src.cli execute configs/examples/reliability_trust_verify_run.json --mode verify
python -m src.cli execute configs/examples/reliability_trust_verify_run.json --mode verify --register-run
python -m src.cli verify-run outputs/platform_runs/reliability-trust-verify-run/run_manifest.json
```

Exit codes:

| Code | Meaning |
| --- | --- |
| 0 | success |
| 2 | invalid config |
| 3 | adapter not found |
| 4 | execution disabled |
| 5 | missing artifact |
| 6 | side-effect violation |
| 7 | verification mismatch |
| 8 | runtime failure |
| 9 | overwrite/path policy violation |
| 10 | registry conflict or validation failure |

## Limitations

This is not a production orchestration engine. It is a manifest-first execution
boundary for one read-only verification adapter. Canonical output promotion,
real adapter execution for other stages, and isolated output comparison remain
future work.

v2.0.4 case-study onboarding validation does not change this execution
boundary. Passing onboarding validation never grants runtime permission.

v2.0.5 platform reporting also does not change this execution boundary. Report
generation is a read-only local summary of registries and tracked compact
artifacts, not an adapter execution mode.

v2.1.1 registry ingestion also does not change this execution boundary. It is a
local manifest index, not an execution engine.
