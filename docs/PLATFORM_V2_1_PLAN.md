# Platform v2.1 Plan

Status: `release_ready`.

v2.1 continues the v2 platform scaffold by improving reproducibility metadata
and controlled local execution bookkeeping. It does not change v1.x case-study
outputs and does not make acquisition or model training executable from the
unified CLI.

## v2.1.1 Scope

v2.1.1 adds a persistent local run registry:

- standard-library `sqlite3` backend
- local-only DB under `outputs/platform_registry/`
- run and report manifest ingestion
- artifact instance records
- input-to-output lineage
- reproducibility status
- run comparison
- registry validation and export
- optional `--register-run` for dry-run, controlled execute, and report
  generation commands

The registry stores metadata only. It does not store raw rows, credentials,
model binaries, host/user identity, or environment secrets.

## v2.1.2 Scope

v2.1.2 adds registry intelligence and policy diagnostics:

- deterministic diagnostic rules over persisted run metadata
- evidence-gap records for missing provenance, validation, trust, or artifact
  evidence
- registered claim evaluation for allowed/prohibited/unsupported claims
- lightweight evidence graph linking run, config, code, artifacts, policies,
  and claim IDs
- local SQLite diagnostic tables under the existing registry
- CLI commands for diagnose/show/list/evaluate/compare/export
- optional read-only report summary of persisted diagnostics

Diagnostics do not execute acquisition, adapters, model training, trust
scripts, raw-data reads, network calls, or scientific recomputation.

## Execution Boundary

Still disabled in v2.1.2:

- acquisition execution
- model training
- raw data reads
- scientific result recomputation
- canonical artifact overwrite
- arbitrary imports
- subprocess or shell execution from config
- network calls
- database server dependencies
- arbitrary diagnostic rules from user config
- free-form AI/LLM claim interpretation

`reliability_trust_closeout` remains the only controlled verify adapter.
Registry ingestion can record its manifest but cannot broaden its permissions.

## v2.1.3 Scope

v2.1.3 adds a scientific constraint and domain-knowledge scaffold:

- unit and dimension registry with simple compatible conversions
- scientific constraint metadata contract
- code-registered evaluator IDs for small range/unit/consistency checks
- domain-knowledge packs for materials, battery, manufacturing, reliability,
  and XRD
- XRD Bragg and Scherrer metadata examples
- applicability checks for small JSON metadata configs
- scientific evidence-graph helper and registered scientific claim IDs
- CLI commands for list, inspect, validate, unit conversion, and local-only
  registry export

It does not execute equations from config, read raw datasets, train models,
perform DFT/FEM/CFD, or claim physical validity without explicit evidence.

## v2.1.4 Scope

v2.1.4 adds bounded scientific execution and persistence:

- request/result models for scalar and small-list scientific checks
- unit normalization and conversion records before evaluator execution
- XRD Bragg d-spacing and Scherrer crystallite-size metadata checks
- synthetic materials composition and battery cycle consistency checks
- scientific execution, finding, claim, and unit-conversion tables in registry
  schema `3`
- CLI preview, execute, show, list, validate, and export commands

It still does not execute arbitrary equations, user callables, raw dataset
scans, DFT/FEM/CFD, model training, phase identification, or production
decision automation.

## v2.1.5 Scope

v2.1.5 closes the scientific execution layer with trust-boundary metadata:

- evidence-level vocabulary from metadata registration through bounded quantity
  estimation
- constraint-role classification for validation, diagnostics, feature
  candidates, model-constraint candidates, and post-prediction checks
- metadata-only scientific feature-candidate registry
- feature eligibility checks against persisted execution variables and units
- claim-boundary evaluation for supported, unsupported, and prohibited
  scientific claims
- SQLite registry schema `4` tables for trust evaluations, constraint
  eligibility, feature eligibility, and claim boundaries
- optional read-only report summary of stored scientific trust rows

It does not generate feature values, connect features to models, apply model
constraints, run SHAP, perform DFT/FEM/CFD, identify phases, or claim production
scientific validity.

## Registry Roadmap

Completed v2.1 work:

- v2.1.2: registry-aware policy diagnostics and evidence-gap analysis
- v2.1.3: scientific constraint and domain-knowledge metadata scaffold
- v2.1.4: bounded scientific execution, XRD consistency checks, and finding
  persistence
- v2.1.5: scientific trust boundary, feature eligibility, and v2.1 closeout

Recommended follow-up work:

- v2.2: selected bounded feature builders with leakage tests and no model
  claim unless model-input evidence exists

## Non-Goals

v2.1 is not a production workflow scheduler, ML tracking server, remote
database, model registry, or dashboard. It is a local reproducibility index for
the CLI-first platform.
