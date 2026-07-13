# Platform v2 Plan

Status: `scaffold_stage` for v2.0.4.

## Why v2

v1.x established a repeatable pattern across Battery Archive, Materials
Project, Smart Factory / SECOM, and Reliability / Backblaze:

- source provenance
- acquisition contracts
- schema and readiness audits
- local/tracked artifact separation
- feature construction
- group/time-aware validation
- train-only preprocessing
- model eligibility
- trust-boundary closeout
- clean snapshot testing

v2 starts turning that repeated pattern into a platform scaffold without
breaking existing case-study workflows.

## v2.0.1 Scope

v2.0.1 adds:

- platform configuration contract
- run manifest contract
- case-study plugin metadata contract
- explicit plugin registry
- artifact registry
- validation policy registry
- trust policy registry
- unified CLI scaffold
- dry-run planner
- example dry-run configs

It does not execute actual acquisition, model training, network access, or
case-study recomputation.

## Architecture Audit Summary

| Area | Classification | v2.0.1 decision |
| --- | --- | --- |
| `src/analyzers/grouped_regression_validation.py` | generic reusable component | register via validation policy |
| `src/analyzers/temporal_classification_validation.py` | generic reusable component | register via validation policy |
| `src/analyzers/asset_temporal_classification.py` | generic reusable component | register via validation policy |
| `src/analyzers/classification_trust.py` | reusable with adapter | register via trust policy |
| `src/analyzers/reliability_trust.py` | reusable with adapter | register via trust policy |
| `src/connectors/` | optional ingestion layer | keep as-is |
| `src/loaders/` | source-specific normalization | keep as-is |
| `scripts/` | case-study orchestration | keep as-is; future adapters |
| `data/case_studies/` | contracts and documentation | keep as-is |
| `data/processed/` | compact tracked artifacts plus local-only generated tables | register selected artifacts |
| `outputs/` | local generated run outputs | keep local-only |

No existing module is deprecated or deleted in v2.0.1.

## v2.0.2 Scope

v2.0.2 adds thin, explicit adapter metadata for selected trust/closeout stages:

- `materials_project_trust_closeout`
- `smart_factory_trust_closeout`
- `reliability_trust_closeout`

The adapters are safe for dry-run and manifest-only planning. They do not
execute acquisition, normalization, validation, trust scripts, subprocesses, or
arbitrary imports.

v2.0.2 also adds local dry-run manifest writing under `outputs/platform_runs/`.
The manifest captures selected plugin, adapter, stage, config hash, expected
artifacts, execution boundary, and trust claim boundary.

## v2.0.3 Scope

v2.0.3 adds a controlled executable runtime for exactly one adapter:
`reliability_trust_closeout` in `verify` mode. The runtime reads only tracked
compact artifacts, writes local run outputs under `outputs/platform_runs/`,
records input/output checksums, and applies side-effect accounting.

Materials Project and Smart Factory adapter execution remain blocked. General
script execution, acquisition, normalization, model training, raw data reads,
and canonical output overwrite remain out of scope.

## v2.0.4 Scope

v2.0.4 adds a generic case-study interface and onboarding contract:

- `CaseStudyMetadata` and lifecycle-stage metadata
- explicit case-study registry for Battery Archive, Materials Project, Smart
  Factory, and Reliability
- adapter bridge from case-study stages to the existing adapter registry
- metadata-only onboarding schema for future domains
- onboarding validator for policy compatibility, artifact contracts, path
  safety, local/tracked conflicts, claim boundaries, and readiness status
- synthetic `environmental_monitoring` onboarding example

This stage does not migrate old scripts, recompute case-study results, execute
acquisition, train models, or grant new runtime permissions.

## Registry Roadmap

The first registry entries are metadata-only/scaffolded or dry-run-ready:

- `battery_archive`
- `materials_project` (`dry_run_ready` for trust manifest planning)
- `smart_factory` (`dry_run_ready` for trust manifest planning)
- `reliability` (`dry_run_ready` for trust manifest planning)

Future work should make adapters executable only after manifest-only behavior
remains stable across more than one case study.

## CLI Roadmap

v2.0.1 supports:

- `list-plugins`
- `inspect-plugin`
- `list-artifacts`
- `validate-config`
- `dry-run`
- `show-policy`
- `show-version`

v2.0.2 adds:

- `list-adapters`
- `inspect-adapter`
- `dry-run --write-manifest`
- `show-manifest`
- `validate-manifest`

v2.0.4 adds:

- `list-case-studies`
- `inspect-case-study`
- `list-case-study-stages`
- `validate-onboarding`
- `inspect-onboarding`
- `onboarding-plan`

Actual `run` execution is intentionally deferred.

## Non-Goals

v2.0.1 does not add:

- model training
- acquisition execution
- network calls
- dashboard/UI
- script deletion or migration
- public API breakage
- dynamic plugin auto-discovery
- YAML config
- shell command execution from config

## Release Roadmap

- v2.0.1: architecture contract, registries, config validation, CLI scaffold
- v2.0.2: thin case-study adapters and safe dry-run manifests
- v2.0.3: controlled reliability trust verify runtime and manifest lifecycle
- v2.0.4: case-study interface, onboarding contract, and domain metadata validation
- v2.0.5: platform-level trust-boundary release

Advanced physics-aware materials descriptors, graph neural networks, or SHAP
remain later v2.x work and should only be added when validation gates justify
interpretation.
