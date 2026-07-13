# Platform v2 Closeout

Status: `feature_complete_pending_release_audit`.

v2 turns repeated v1.x case-study patterns into an additive platform scaffold:
explicit registries, manifest-first planning, controlled execution boundaries,
case-study lifecycle metadata, new-domain onboarding checks, and read-only
platform reporting.

## Completed Scope

- v2.0.1: platform registry scaffold, config contract, run-manifest schema, and
  unified CLI scaffold
- v2.0.2: thin trust-stage adapter metadata and dry-run manifest writer
- v2.0.3: controlled verify execution for the reliability trust adapter only
- v2.0.4: generic case-study interface and metadata-only onboarding contract
- v2.0.5: read-only JSON/Markdown platform report engine

## Current Execution Boundary

Only `reliability_trust_closeout` has controlled verify-mode execution.
Materials Project and Smart Factory trust adapters remain dry-run/manifest
only. Battery Archive remains partially onboarded. Acquisition, normalization,
feature engineering, model training, raw-data reads, trust reruns, and
canonical output overwrites remain disabled in the unified CLI.

## Reporting Boundary

The v2.0.5 report engine summarizes registry metadata and tracked compact
artifacts. It does not recompute scientific results or select representative
models. Report outputs stay local-only under `outputs/platform_reports/`.

## Security Model

- JSON configs contain metadata only.
- User configs cannot provide module paths or callables.
- No `eval`, `exec`, arbitrary shell, arbitrary import, network access, or
  raw-data read is used by the report engine.
- Absolute paths, path traversal, credentials, and symlink escapes are rejected
  for report output.

## Backward Compatibility

Existing case-study scripts, analyzer modules, output schemas, tracked compact
artifacts, and v1.x documentation remain canonical. The v2 scaffold does not
delete or move existing workflow files.

## Release Readiness Checklist

- Existing v1.x tests remain in the full suite.
- v2 CLI commands work without local raw data.
- Clean tracked snapshot tests do not require Backblaze archives, row-level
  predictions, or generated outputs.
- Report engine marks `scientific_recomputation_performed = false`.
- Generated reports remain local-only and ignored by Git.

## v2.1 Roadmap

- Add executable adapters only after dry-run and verify boundaries remain
  stable.
- Expand artifact registry coverage incrementally.
- Add a configuration-driven pipeline runner for safe stages.
- Add richer report templates without changing scientific results.
- Keep dashboard/UI, PDF, and advanced model interpretation out of scope until
  validation gates justify them.
