# Platform v2 Plan

Status: `scaffold_stage` for v2.0.1.

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

## Registry Roadmap

The first registry entries are metadata-only/scaffolded:

- `battery_archive`
- `materials_project`
- `smart_factory`
- `reliability`

Future work should add thin adapters only after the metadata contract remains
stable across more than one case study.

## CLI Roadmap

v2.0.1 supports:

- `list-plugins`
- `inspect-plugin`
- `list-artifacts`
- `validate-config`
- `dry-run`
- `show-policy`
- `show-version`

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
- v2.0.2: thin case-study adapters for selected trust/closeout stages
- v2.0.3: executable configuration pipeline with manifest writing
- v2.0.4: unified report generation from registered artifacts
- v2.0.5: platform-level trust-boundary release

Advanced physics-aware materials descriptors, graph neural networks, or SHAP
remain later v2.x work and should only be added when validation gates justify
interpretation.
