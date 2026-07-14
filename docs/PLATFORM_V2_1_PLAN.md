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

## Execution Boundary

Still disabled in v2.1.1:

- acquisition execution
- model training
- raw data reads
- scientific result recomputation
- canonical artifact overwrite
- arbitrary imports
- subprocess or shell execution from config
- network calls
- database server dependencies

`reliability_trust_closeout` remains the only controlled verify adapter.
Registry ingestion can record its manifest but cannot broaden its permissions.

## Registry Roadmap

Planned follow-up work:

- v2.1.2: registry-aware report summaries and manifest history views
- v2.1.3: explicit backfill tools for selected manifest directories
- v2.1.4: adapter output comparison policy for isolated runs
- v2.1.5: v2.1 closeout and release readiness audit

## Non-Goals

v2.1 is not a production workflow scheduler, ML tracking server, remote
database, model registry, or dashboard. It is a local reproducibility index for
the CLI-first platform.
