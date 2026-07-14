# Platform Diagnostics

Status: `development_stage` for v2.1.2.

Platform diagnostics add a deterministic policy-intelligence layer on top of
the local run registry. They inspect persisted run metadata, artifact records,
validation policies, trust policies, reproducibility status, and claim
boundaries. They do not rerun scripts, read raw data, train models, call
network APIs, recompute metrics, or parse free-form scientific claims.

## Scope

Diagnostics answer metadata questions such as:

- Does the run have config, code, input checksum, and output checksum evidence?
- Is the run reproducibility status verified, partial, or blocked?
- Are artifact tracked/local-only policies internally consistent?
- Is the validation policy registered and train-only?
- Is optimistic random evidence separated from primary validation evidence?
- Is a trust policy registered, and are production/calibration claims blocked?
- Which evidence gaps would narrow or block a claim?

Diagnostics are a registry-governance layer, not a scientific scoring layer.

## Data Model

`src/platform_core/diagnostics.py` defines:

- `DiagnosticFinding`
- `EvidenceGap`
- `ClaimEvaluation`
- `RunDiagnosticReport`

Findings are generated from static rules in
`src/platform_core/diagnostic_rules.py`. Claim evaluations use registered
claim IDs in `src/platform_core/claim_diagnostics.py`; arbitrary free-text
claim parsing is intentionally unsupported.

## Registry Tables

v2.1.2 updates the local SQLite registry to schema version `2` and adds:

- `diagnostic_evaluations`
- `diagnostic_findings`
- `evidence_gaps`
- `claim_evaluations`

The tables store metadata only. They do not store raw rows, row-level
predictions, serial numbers, credentials, host paths, usernames, or model
binaries.

## Evidence Graph

`src/platform_core/evidence_graph.py` builds a small in-memory graph linking:

- run
- code commit
- config SHA
- input/output artifacts
- validation policy
- trust policy
- registered claim IDs

The graph is serialized into diagnostic reports for inspection. It is not a
database graph engine and has no external dependency.

## CLI

Evaluate and persist diagnostics for one run:

```powershell
python -m src.cli diagnose-run reliability-trust-verify-run
```

Inspect stored diagnostics:

```powershell
python -m src.cli show-diagnostics reliability-trust-verify-run
python -m src.cli list-findings --run-id reliability-trust-verify-run
python -m src.cli list-evidence-gaps reliability-trust-verify-run
python -m src.cli evaluate-claim reliability-trust-verify-run production_deployment
```

Compare, validate, and export:

```powershell
python -m src.cli compare-diagnostics run-a run-b
python -m src.cli diagnostics-validate
python -m src.cli diagnostics-export --overwrite
```

Add `--json` before the command for machine-readable output.

Diagnostic command exit codes:

- `0`: evaluation completed with no blockers
- `10`: evaluation completed with warnings or unsupported/prohibited claim
- `11`: blocker found
- `12`: run not found
- `13`: policy/reference missing
- `14`: diagnostic schema error
- `15`: unsupported rule set

## Report Integration

Platform reports can opt into a stored diagnostics summary with
`include_registry_diagnostics: true` in the report config. This reads existing
diagnostic records only; it does not run `diagnose-run` automatically.

If no registry or diagnostic table exists, the report records an explicit
unavailable status.

## Security Boundary

Diagnostics prohibit:

- `eval` / `exec`
- arbitrary import paths from config
- subprocess or shell execution
- network access
- raw-data reads
- model fitting
- test-label threshold tuning
- production-ready claim promotion
- calibrated probability claims without explicit independent evidence

The rule set is code-registered and versioned as `diagnostic_rules_v1`.

## Limitations

- Diagnostics use metadata and registered policy contracts only.
- They do not inspect row-level prediction tables or recompute scientific
  metrics.
- They cannot prove a model is valid; they can only identify policy alignment,
  missing evidence, and claim boundaries.
- Legacy case studies without a standardized trust policy can produce
  `unavailable` findings rather than inferred conclusions.
