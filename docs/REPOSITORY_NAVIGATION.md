# Repository Navigation

This guide identifies the current user entry points, implementation ownership,
case-study workflows, scientific evidence, and historical records without moving
or deleting compatibility-sensitive files.

The repository contains two related but distinct software surfaces:

1. a stable tabular engineering-data analyzer used through installed commands;
2. an additive research-platform and governance layer used mainly through
   source-checkout commands and case-study workflows.

They share scientific trust-boundary policies but should not be treated as one
interchangeable CLI.

## Start Here

| Goal | Entry point | Primary documentation |
|---|---|---|
| Analyze a local engineering CSV | `mda` | root `README.md` and `OUTPUTS_POLICY.md` |
| Run Battery Degradation Intelligence | `mda-battery-intelligence` | `BATTERY_DEGRADATION_INTELLIGENCE.md` |
| Import official NASA PCoE raw signals | `mda-nasa-battery-import` | `NASA_PCOE_BATTERY_IMPORT.md` |
| Close an already-reviewed NASA audit | `scripts/close_nasa_pcoe_audit.ps1` | `NASA_PCOE_AUDIT_CLOSEOUT.md` |
| Build the representative NIST process-characterization case | `scripts/run_representative_process_characterization_workflow.py` | NIST case-study documentation |
| Inspect platform/governance metadata | `python -m src.cli` | platform and PGIR documentation |
| Clean local caches and classify outputs | explicit PowerShell paths | `WORKSPACE_HYGIENE.md` |

## Code Ownership Map

### Stable installed analyzer

```text
src/materials_data_analyzer/
src/process_data.py
src/analyzers/
src/config.py
src/data_io.py
src/dataset_contract.py
src/io_utils.py
src/preprocessing.py
src/reports.py
src/results.py
src/visualization.py
```

`materials_data_analyzer.cli` preserves the installed `mda` command while the
historical `python src/process_data.py` command remains supported. Root-level
modules are compatibility-sensitive and must not be moved or deleted without an
import-reference audit, wheel/sdist tests, and explicit migration support.

### Platform and scientific-governance layer

```text
src/platform_core/
src/cli.py
configs/examples/
data/platform/
```

`src/cli.py` is the source-checkout platform CLI. It is not the implementation
behind the installed `mda` command. It owns registry, manifest, governance,
scientific-constraint, PGIR, external-source, Materials, Battery, and bounded
physics workflow commands.

The file is a known maintainability hotspot. Future decomposition must preserve
all subcommands, exit codes, JSON contracts, and `python -m src.cli` behavior.
It should be split behind a thin compatibility entry point rather than rewritten
as an unrelated new CLI.

### Source-specific ingestion

```text
src/connectors/
src/loaders/
scripts/build_*.py
scripts/acquire_*.py
scripts/ingest_data.py
```

Connectors own source discovery and acquisition boundaries. Loaders own
file-content parsing and canonical schema normalization. Scripts own workflow
orchestration. A connector success does not establish data comparability or
scientific readiness.

### Characterization integration

```text
src/loaders/characterization_bundle.py
scripts/build_characterization_handoff.py
scripts/consume_characterization_handoff_bundle.py
```

Instrument-specific XRD, SEM, EDS, Raman, TEM, and SAED extraction remains owned
by `materials-characterization-analyzer`. This repository consumes versioned,
checksum-bound files joined through explicit sample identities.

## Script Navigation

See [`scripts/README.md`](../scripts/README.md) for workflow categories and
selection rules.

The preferred rule is:

- use an installed CLI for reusable analysis behavior;
- use a `run_*` script for a documented end-to-end local workflow;
- use a `build_*` script for deterministic artifact construction;
- use an `audit_*` or `verify_*` script for read-only validation;
- use release-specific scripts only when reproducing that release contract.

Do not run every script as a generic pipeline. Many scripts are bounded
case-study or historical release workflows.

## Data Navigation

### Tracked sample data

```text
data/sample/
```

Small synthetic or sanitized files used by quickstarts and tests.

### Tracked compact scientific evidence

```text
data/processed/
data/platform/
data/case_studies/
```

These areas preserve compact summaries, decisions, claim boundaries, source
notes, and reproducibility evidence. They are not a dumping ground for local
row-level outputs.

Use:

- [`data/processed/README.md`](../data/processed/README.md) for the detailed
  processed-data policy;
- [`data/processed/ARTIFACT_INDEX.md`](../data/processed/ARTIFACT_INDEX.md) for
  evidence-family navigation;
- `data/processed/artifact_catalog.csv` for machine-readable family-prefix rules.

### Local raw and generated data

```text
data/raw/
data/processed/nasa_pcoe_battery_import/
outputs/
```

These are intentionally ignored. Ignored does not mean disposable. Preserve
source archives, retrieval receipts, import manifests, canonical analysis
outputs, and completed audit bundles according to `WORKSPACE_HYGIENE.md`.

## Documentation Navigation

### Current user and repository operation

- `README.md`
- `docs/OUTPUTS_POLICY.md`
- `docs/WORKSPACE_HYGIENE.md`
- `docs/REPOSITORY_NAVIGATION.md`
- `TESTING.md`
- `CONTRIBUTING.md`
- `SECURITY.md`

### Current scientific methods and trust boundaries

Method-specific documents at the top level of `docs/` describe data contracts,
validation design, applicability boundaries, scientific constraints, PGIR,
Battery, Materials, Smart Factory, Reliability, and bounded physics work.

A method document may report `Supported`, `Diagnostic`, `Inconclusive`, or
`Unsupported` evidence. Its existence does not imply a positive scientific
result.

### Case studies

```text
docs/case_studies/
data/case_studies/
```

`data/case_studies/` owns source notes and compact case-specific evidence.
`docs/case_studies/` owns broader narrative and cross-repository workflow
explanation.

### Releases, RFCs, audits, plans, and archive

```text
docs/releases/
docs/rfcs/
docs/audits/
docs/plans/
docs/archive/
release/
```

These are governance and history records. Historical plans are not current
implementation specifications. Release-specific files may be checksum- or
path-sensitive and should not be deleted merely because a newer release exists.

## Test Navigation

The current flat `tests/` directory preserves established CI collection paths.
Use filename intent rather than assuming every test has the same role:

- analyzer and loader behavior: `test_<component>.py`;
- safety and contract regression: names containing `contract`, `safety`,
  `provenance`, `binding`, or `hygiene`;
- case-study integration: names containing the source or case identifier;
- release and publication verification: names containing `release`, `promotion`,
  or the version label;
- PowerShell workflow tests: names containing `script` or the workflow name.

A future test-directory reorganization must preserve pytest discovery, CI file
references, source-distribution self-tests, and release contracts. It is not a
safe cosmetic move.

## Cleanup Decision Rule

Before moving or deleting a tracked file, determine:

1. whether a public CLI, import, test, workflow, manifest, release attestation, or
   documentation link references its exact path;
2. whether it contains source measurements, row-level outputs, compact evidence,
   or only historical narrative;
3. whether regeneration is deterministic and documented;
4. whether deletion would erase a negative or inconclusive result;
5. whether compatibility can be preserved with a thin wrapper or redirect.

Use the smallest change that improves navigation or ownership. Do not combine
workspace cleanup with public API redesign, data deletion, and scientific-method
changes in one pull request.
