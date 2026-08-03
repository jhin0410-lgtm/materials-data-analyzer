# Program-wide Audit Remediation

## Scope

This remediation addresses the August 2026 repository-wide audit across generic tabular workflows, Battery Intelligence, NASA PCoE import and review packaging, connectors, output safety, provenance, packaging, and continuous integration.

## Safety changes

- User-facing output replacement is transactional. The prior recognized run is retained until a complete staged run succeeds.
- Filesystem roots, the current directory, the user home directory, configured project roots, and targets that contain protected input evidence are rejected.
- A foreign non-empty directory cannot be overwritten merely by passing `--overwrite`.
- NASA archive extraction applies member, nesting, cumulative expanded-size, and compression-ratio limits.
- NASA audit bundles redact the local absolute source path from their embedded README.

## Data and scientific changes

- Identifier and provenance columns are protected from heuristic numeric coercion, including leading-zero identifiers.
- Preprocessing writes exact source-row exclusions and reasons.
- A versioned dataset contract can declare identifiers, groups, timestamps, units, features, targets, outcomes, exposure, and censoring.
- `--decision-grade` fails closed when required semantic roles are absent. This gate validates declared semantics only and does not prove comparability or causal validity.
- Multi-objective process ranking requires complete target coverage and records explicit weights plus percentile sensitivity.
- Cp/Cpk is suppressed when sample count or statistical-control readiness is insufficient.
- Generic reliability accepts only explicit binary failure labels and reports invalid codes.
- Simulation candidate ranks are suppressed when no out-of-sample holdout exists.
- Battery feature eligibility and imputation are fitted inside training folds.
- Battery model selection uses battery-macro MAE as the primary decision metric while retaining pooled-row and fold-balanced metrics.

## Reproducibility and packaging

Run manifests record terminal status, runtime platform, dependency versions, source commit when locally resolvable, and SHA-256/byte counts for generated artifacts. Absolute interpreter paths are not recorded.

The source distribution includes repository tests, scripts, compact fixtures, configs, and documentation required by those tests. CI tests the extracted sdist independently.

## Scientific boundary

These changes improve software integrity and the validity of the evaluation procedure. They do not convert the current Battery predictive result into a supported claim. The NASA protocol findings remain diagnostic and the Ridge predictive hypothesis remains unsupported unless new independent, protocol-comparable evidence changes that conclusion.
