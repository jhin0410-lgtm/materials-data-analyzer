# Scientific Execution

Status: `development_stage` for v2.1.4.

v2.1.4 adds a bounded scientific execution layer for explicit scalar and
small-list metadata checks. It runs only code-registered evaluators and small
domain-specific derivations after applicability, unit, and assumption checks.

## Execution Pipeline

The execution order is request validation, constraint lookup, knowledge-pack
lookup, applicability evaluation, required variable check, unit validation and
conversion, assumption validation, registered evaluator execution, tolerance
comparison, finding creation, claim evaluation, evidence graph summary, and
optional local registry persistence.

`scientific_recomputation_performed` means a registered scientific evaluator or
bounded derivation ran. It does not mean a case-study dataset was recomputed.

## Supported Checks

- XRD Bragg geometry: derives d-spacing and optionally compares a supplied
  d-spacing within tolerance.
- XRD Scherrer preconditions: derives a crystallite-size estimate with explicit
  correction status and limitations.
- Materials basics: synthetic composition fraction, duplicate element metadata,
  and simple weighted descriptor checks.
- Battery basics: synthetic cycle order, non-negative capacity, efficiency
  bounds, temperature unit conversion, and capacity-retention metadata checks.

Manufacturing and reliability remain limited to semantic or synthetic metadata
checks when requested variables are available.

## Boundaries

The layer does not read raw datasets, scan CSVs, train models, parse arbitrary
equations, call user-supplied functions, run DFT/FEM/CFD, identify XRD phases,
or make production decisions. A violation narrows the claim boundary; it is not
automatically proof of a physical impossibility.

## CLI

```powershell
python -m src.cli preview-scientific-check configs/examples/xrd_bragg_consistent_check.json
python -m src.cli execute-scientific-check configs/examples/xrd_bragg_consistent_check.json --persist --output-dir outputs/platform_science/xrd_bragg_consistent_check
python -m src.cli show-scientific-execution xrd_bragg_consistent_check
python -m src.cli list-scientific-findings --execution-id xrd_bragg_consistent_check
python -m src.cli evaluate-scientific-claim xrd_bragg_consistent_check phase_identification_supported
python -m src.cli scientific-registry-validate
```

`preview-scientific-check` never persists findings or writes result files.
`execute-scientific-check` can persist to the local SQLite registry and can
write local-only JSON/Markdown artifacts under `outputs/platform_science/`.

## Local Outputs

When output writing is enabled, the following files are created locally:

- `scientific_result.json`
- `scientific_report.md`
- `execution_manifest.json`

These files are ignored with `outputs/**` and should not be committed.
