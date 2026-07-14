# Platform Architecture

Status: `development_stage` for v2.1.4.

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
- Manifest first: v2.0.5 plans workflows, maps selected trust adapters, writes
  local manifests, and allows one read-only reliability trust verification
  adapter. It does not run acquisition, model training, raw-data reads, trust
  scripts, or network operations.
- Domain interface first: case studies now expose common lifecycle metadata
  and onboarding readiness without forcing old scripts into one abstraction.
- Report read-only: platform reports summarize registries and tracked compact
  artifacts without recomputing scientific results.
- Persistent local registry: v2.1.1 can ingest run/report manifests into a
  local SQLite metadata index without rerunning scientific workflows.
- Registry intelligence: v2.1.2 evaluates static policy diagnostics, evidence
  gaps, claim decisions, and evidence graphs from persisted metadata only.
- Scientific metadata first: v2.1.4 adds bounded scientific execution on top of
  unit-aware constraints, domain-knowledge packs, applicability checks, and
  XRD Bragg/Scherrer examples without raw-data reads or model training.

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
- `src/platform_core/adapters.py`: thin adapter metadata contract
- `src/platform_core/adapter_registry.py`: explicit adapter registry
- `src/platform_core/artifacts.py`: artifact registry and path policy
- `src/platform_core/validation_registry.py`: validation policy metadata
- `src/platform_core/trust_registry.py`: trust policy metadata
- `src/platform_core/config.py`: lightweight JSON config validation
- `src/platform_core/planner.py`: side-effect-free dry-run planner
- `src/platform_core/manifests.py`: safe local dry-run manifest writer
- `src/platform_core/execution_policy.py`: explicit execution allowlist
- `src/platform_core/execution_runtime.py`: controlled verify runtime
- `src/platform_core/artifact_resolver.py`: safe artifact ID resolution
- `src/platform_core/side_effects.py`: side-effect accounting
- `src/platform_core/case_studies.py`: generic case-study interface contract
- `src/platform_core/case_study_registry.py`: explicit case-study registry
- `src/platform_core/onboarding.py`: metadata-only new-domain onboarding validator
- `src/platform_core/reports.py`: platform report data model
- `src/platform_core/report_extractors.py`: explicit compact-artifact extractors
- `src/platform_core/report_generator.py`: JSON/Markdown report renderer and local-only writer
- `src/platform_core/run_registry.py`: local SQLite run/artifact registry
- `src/platform_core/registry_service.py`: service wrapper for registry CLI operations
- `src/platform_core/diagnostic_rules.py`: static diagnostics rule definitions
- `src/platform_core/diagnostic_service.py`: run-registry diagnostic orchestration
- `src/platform_core/claim_diagnostics.py`: registered machine-readable claim decisions
- `src/platform_core/evidence_graph.py`: in-memory evidence graph summaries
- `src/platform_core/units.py`: small unit/dimension registry
- `src/platform_core/scientific_constraints.py`: scientific constraint data model
- `src/platform_core/scientific_evaluators.py`: code-registered safe evaluator functions
- `src/platform_core/scientific_constraint_registry.py`: explicit scientific constraint registry
- `src/platform_core/domain_knowledge.py`: domain-knowledge pack registry
- `src/platform_core/scientific_applicability.py`: small JSON applicability and validation checks
- `src/platform_core/scientific_execution.py`: bounded scientific execution,
  unit normalization, finding persistence, and local-only result writing
- `src/platform_core/snapshots.py`: deterministic registry snapshot helper
- `src/cli.py`: unified CLI scaffold

## Plugin Registry

The initial registry contains metadata for:

| Plugin | Case study | Status | Notes |
| --- | --- | --- | --- |
| `battery_archive` | Battery Archive | `scaffolded` | Existing cycle-data scripts remain the orchestration layer. |
| `materials_project` | Materials Project | `dry_run_ready` | Trust adapter is mapped for manifest-only dry-runs. |
| `smart_factory` | Smart Factory / SECOM | `dry_run_ready` | Trust adapter is mapped for manifest-only dry-runs. |
| `reliability` | Backblaze reliability | `dry_run_ready` | Trust adapter is mapped for manifest-only dry-runs. |

`scaffolded` means the platform can inspect, validate, and dry-run metadata.
It does not mean v2 can execute the full case-study pipeline yet.
`dry_run_ready` means a safe adapter mapping exists for manifest planning.
Only `reliability_trust_closeout` has an additional verify-mode execution
allowlist entry in v2.0.3.

## Case-Study Interface

v2.0.4 adds a domain-facing case-study registry on top of the plugin and
adapter registries. It maps Battery Archive, Materials Project, Smart Factory,
and Reliability to common lifecycle stages while preserving their existing
scripts and output contracts. No case study is marked `fully_onboarded`.

The interface can be inspected with:

```powershell
python -m src.cli list-case-studies
python -m src.cli inspect-case-study reliability
python -m src.cli list-case-study-stages reliability
```

## Adapter Registry

`src/platform_core/adapter_registry.py` maps selected trust/closeout stages to
existing script metadata through explicit adapter IDs:

- `materials_project_trust_closeout`
- `smart_factory_trust_closeout`
- `reliability_trust_closeout`

Adapters store module paths as metadata only. The unified CLI does not import
or execute those modules in v2.0.2.

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

Example dry-run and manifest dry-run configs live in `configs/examples/`.

## Run Manifest Contract

`data/platform/run_manifest_schema_v2.json` defines the future run manifest.
v2.0.2 can write a single local dry-run manifest under `outputs/platform_runs/`
when requested with `--write-manifest`. Manifests are local-only and ignored by
Git.
v2.0.3 also writes terminal execution manifests for approved verify runs.

## Persistent Run Registry

v2.1.1 adds a local-only SQLite registry under `outputs/platform_registry/`.
It can ingest run manifests and platform report manifests, store artifact
instances and lineage, compute metadata-only reproducibility status, compare
runs, validate registry integrity, and export local JSON/CSV summaries.

The registry is not a workflow scheduler and does not execute acquisition,
model training, raw-data reads, trust analyzers, or scientific recomputation.
See [`PLATFORM_RUN_REGISTRY.md`](PLATFORM_RUN_REGISTRY.md).

## Registry Diagnostics

v2.1.2 adds deterministic diagnostics over persisted registry metadata. The
diagnostic layer connects runs to validation policies, trust policies,
artifact policy, reproducibility status, and registered claim IDs. It records
findings, evidence gaps, claim evaluations, and evidence graphs in local
SQLite tables without rerunning the underlying science.

See [`PLATFORM_DIAGNOSTICS.md`](PLATFORM_DIAGNOSTICS.md).

## Scientific Constraint Registry

v2.1.4 adds bounded execution for registered evaluator IDs and explicit
scalar/small-list inputs. The first explicit examples are XRD Bragg/Scherrer
metadata checks. Equations are display-only and are never parsed from config.

See [`SCIENTIFIC_CONSTRAINTS.md`](SCIENTIFIC_CONSTRAINTS.md),
[`SCIENTIFIC_EXECUTION.md`](SCIENTIFIC_EXECUTION.md),
[`XRD_PHYSICS_VALIDATION.md`](XRD_PHYSICS_VALIDATION.md),
[`DOMAIN_KNOWLEDGE_PACKS.md`](DOMAIN_KNOWLEDGE_PACKS.md), and
[`PHYSICS_AWARE_ROADMAP.md`](PHYSICS_AWARE_ROADMAP.md).

## Unified CLI

The scaffold is available with:

```powershell
python -m src.cli list-plugins
python -m src.cli inspect-plugin reliability
python -m src.cli list-artifacts --plugin reliability
python -m src.cli list-adapters
python -m src.cli inspect-adapter reliability_trust_closeout
python -m src.cli list-case-studies
python -m src.cli inspect-case-study reliability
python -m src.cli list-case-study-stages reliability
python -m src.cli validate-config configs/examples/reliability_trust_dry_run.json
python -m src.cli validate-onboarding configs/examples/environmental_monitoring_onboarding.json
python -m src.cli onboarding-plan configs/examples/environmental_monitoring_onboarding.json
python -m src.cli dry-run configs/examples/reliability_trust_dry_run.json
python -m src.cli dry-run configs/examples/reliability_trust_manifest_dry_run.json --write-manifest
python -m src.cli list-executable-adapters
python -m src.cli show-execution-policy reliability_trust_closeout
python -m src.cli execute configs/examples/reliability_trust_verify_run.json --mode verify
python -m src.cli verify-run outputs/platform_runs/reliability-trust-verify-run/run_manifest.json
python -m src.cli validate-manifest outputs/platform_runs/reliability-trust-manifest-dry-run/run_manifest.json
python -m src.cli show-manifest outputs/platform_runs/reliability-trust-manifest-dry-run/run_manifest.json
python -m src.cli preview-report --config configs/examples/platform_report_all_case_studies.json
python -m src.cli generate-report --config configs/examples/platform_report_all_case_studies.json
python -m src.cli validate-report outputs/platform_reports/platform_v2_all_case_studies
python -m src.cli inspect-report outputs/platform_reports/platform_v2_all_case_studies
python -m src.cli list-report-sources
python -m src.cli registry-init
python -m src.cli registry-ingest outputs/platform_runs/reliability-trust-verify-run/run_manifest.json
python -m src.cli registry-list-runs
python -m src.cli registry-reproducibility reliability-trust-verify-run
python -m src.cli registry-export --overwrite
python -m src.cli diagnose-run reliability-trust-verify-run
python -m src.cli show-diagnostics reliability-trust-verify-run
python -m src.cli evaluate-claim reliability-trust-verify-run production_deployment
python -m src.cli show-policy reliability_asset_time_aware
python -m src.cli list-scientific-constraints
python -m src.cli inspect-scientific-constraint xrd.scherrer.preconditions
python -m src.cli list-knowledge-packs
python -m src.cli validate-scientific-input configs/examples/scientific_constraints_xrd_bragg_scherrer.json
python -m src.cli convert-unit --value 25 --from degC --to K
python -m src.cli export-scientific-registry --output outputs/platform_science/scientific_registry.json --overwrite
python -m src.cli preview-scientific-check configs/examples/xrd_bragg_consistent_check.json
python -m src.cli execute-scientific-check configs/examples/xrd_scherrer_uncorrected_check.json --persist
python -m src.cli show-version
```

Add `--json` before the command for deterministic JSON output.

## Backward Compatibility

v2.0.2 does not remove, rename, or replace:

- `src/process_data.py`
- existing scripts under `scripts/`
- existing case-study contracts
- processed output schemas
- test paths
- documentation links

The platform layer is a scaffold for later executable adapters.

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

- Existing case-study scripts are not yet executable through v2 adapters.
- Registries are explicit Python metadata, not external package discovery.
- Dry-run reports manifest readiness, not executable pipeline readiness.
- Artifact registry coverage is intentionally selective and should expand as
  adapters are implemented.
- The report engine is JSON/Markdown only and does not generate HTML, PDF, or a
  dashboard.
