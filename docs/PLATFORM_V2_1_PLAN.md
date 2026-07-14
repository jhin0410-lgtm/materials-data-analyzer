# Platform v2.1 Plan

Status: `development_stage`.

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

## Registry Roadmap

Planned follow-up work:

- v2.1.2: registry-aware policy diagnostics and evidence-gap analysis
- v2.1.3: explicit backfill tools for selected manifest directories
- v2.1.4: adapter output comparison policy for isolated runs
- v2.1.5: v2.1 closeout and release readiness audit

## Non-Goals

v2.1 is not a production workflow scheduler, ML tracking server, remote
database, model registry, or dashboard. It is a local reproducibility index for
the CLI-first platform.
