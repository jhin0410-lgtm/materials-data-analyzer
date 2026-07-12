# Platform Architecture

Status: `scaffold_stage` for v2.0.1.

`materials_data_analyzer` remains a CLI-first tabular engineering-data
analysis project. The v2 platform layer adds a registry and configuration
scaffold around the existing v1.x case studies without moving scripts,
changing output schemas, or replacing `src/process_data.py`.

## Architecture Principles

- Additive first: keep existing case-study scripts and analyzer modules working.
- Metadata before migration: register existing workflows before adapting them.
- Explicit contracts: pipeline configs, artifacts, validation, and trust policy
  are declared in JSON or typed metadata.
- No hidden execution: configs cannot contain Python expressions, shell
  commands, arbitrary imports, or credentials.
- Dry-run first: v2.0.1 plans workflows and validates config, but does not run
  acquisition, model training, or network operations.

## Component Boundaries

```text
Data Source
-> Connector / access gate
-> Loader / schema normalization
-> Readiness and leakage audit
-> Feature construction
-> Validation
-> Trust boundary
-> Compact artifacts and case-study documentation
```

In code:

- `src/platform_core/plugins.py`: plugin metadata contract
- `src/platform_core/registry.py`: explicit plugin registry
- `src/platform_core/artifacts.py`: artifact registry and path policy
- `src/platform_core/validation_registry.py`: validation policy metadata
- `src/platform_core/trust_registry.py`: trust policy metadata
- `src/platform_core/config.py`: lightweight JSON config validation
- `src/platform_core/planner.py`: side-effect-free dry-run planner
- `src/cli.py`: unified CLI scaffold

## Plugin Registry

The initial registry contains metadata for:

| Plugin | Case study | Status | Notes |
| --- | --- | --- | --- |
| `battery_archive` | Battery Archive | `scaffolded` | Existing cycle-data scripts remain the orchestration layer. |
| `materials_project` | Materials Project | `scaffolded` | Registers exact-provenance validation and trust artifacts. |
| `smart_factory` | Smart Factory / SECOM | `scaffolded` | Registers time-aware classification and trust artifacts. |
| `reliability` | Backblaze reliability | `scaffolded` | Registers asset/time-aware validation and trust artifacts. |

`scaffolded` means the platform can inspect, validate, and dry-run metadata.
It does not mean v2 can execute the full case-study pipeline yet.

## Artifact Registry

Artifacts are described by ID, case study, stage, relative path, type, format,
tracked/local-only policy, producer, consumers, provenance requirement, and
status. The registry rejects:

- duplicate artifact IDs
- absolute paths
- `..` path traversal
- tracked/local-only conflicts
- raw artifacts marked as tracked compact outputs

No files are moved by the registry.

## Validation Registry

The initial validation policies are:

- `random_reference_only`
- `group_aware_regression`
- `time_aware_classification`
- `asset_time_combined_classification`

The registry points to existing analyzers where appropriate. It does not
duplicate model-fitting logic.

## Trust Registry

The initial trust policies are:

- `materials_group_generalization`
- `smart_factory_time_aware`
- `reliability_asset_time_aware`

Default trust policies do not contain `production_ready` and do not allow
production claims.

## Configuration Contract

`data/platform/pipeline_config_schema_v2.json` defines the v2 config contract.
The initial implementation uses lightweight validation in
`src/platform_core/config.py` instead of adding a JSON-schema dependency.

Example dry-run configs live in `configs/examples/`.

## Run Manifest Contract

`data/platform/run_manifest_schema_v2.json` defines the future run manifest.
v2.0.1 does not write run manifests yet; it only defines the contract.

## Unified CLI

The scaffold is available with:

```powershell
python -m src.cli list-plugins
python -m src.cli inspect-plugin reliability
python -m src.cli list-artifacts --plugin reliability
python -m src.cli validate-config configs/examples/reliability_trust_dry_run.json
python -m src.cli dry-run configs/examples/reliability_trust_dry_run.json
python -m src.cli show-policy reliability_asset_time_aware
python -m src.cli show-version
```

Add `--json` before the command for deterministic JSON output.

## Backward Compatibility

v2.0.1 does not remove, rename, or replace:

- `src/process_data.py`
- existing scripts under `scripts/`
- existing case-study contracts
- processed output schemas
- test paths
- documentation links

The platform layer is a scaffold for later adapters.

## Security and Safety

The scaffold avoids:

- `eval`
- `exec`
- arbitrary shell execution
- arbitrary import paths from user config
- filesystem-wide plugin scanning
- network calls on import or dry-run
- credential storage
- absolute host paths in configs or manifests

## Known Technical Debt

- Existing case-study scripts are not yet callable through v2 adapters.
- Registries are explicit Python metadata, not external package discovery.
- Dry-run reports scaffold readiness, not executable pipeline readiness.
- Artifact registry coverage is intentionally selective and should expand as
  adapters are implemented.
