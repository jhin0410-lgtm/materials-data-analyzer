# Platform Direction Reset

Status: `active_direction_after_v2_7_representative_workflow`

## Mission

The project is a Virtual Research Partner for materials and manufacturing work.
It connects tabular process, quality, reliability, Battery, and characterization
results while preserving sample identity, units, provenance, validation scope,
and scientific limitations.

Battery remains one trajectory-oriented case study. It is not the identity of
the platform.

## Repository Roles

### `materials-data-analyzer`

Owns tabular engineering workflows:

- process conditions and experiment tables;
- quality, SPC, and Smart Factory logs;
- reliability and time-dependent asset records;
- Battery cycle and trajectory tables;
- readiness, leakage, validation, candidate screening, and reporting;
- cross-domain sample-level tables used for downstream statistics or models.

### `materials-characterization-analyzer`

Owns instrument-specific interpretation boundaries and feature extraction:

- XRD;
- SEM and EDS;
- Raman;
- TEM and SAED;
- future XPS, FTIR, TGA, and DSC only when their individual contracts and
  representative evidence are ready.

The repositories remain separately installable. They exchange data through
explicit identifiers and versioned result contracts, never through row order,
inferred filenames, or direct internal imports.

## Completed Foundation

The following work is complete and should not be repeatedly reopened without new
evidence:

- CSV-first EDA, process, reliability, SPC, Smart Factory, and simulation modes;
- group-aware, time-aware, and asset-aware validation utilities;
- Materials Project, Smart Factory, Reliability, and Battery case-study evidence;
- stable long-format characterization feature records;
- strict characterization-bundle consumption and sample-ID handoff;
- pinned public producer-consumer workflows;
- one representative real NIST process-characterization workflow;
- process-design identifiability audit and bounded next-experiment plan;
- v2.7.0 public release and citation boundary.

The NIST workflow now provides the previously missing real consumer path:

```text
processing history
-> characterization features
-> sample-ID integration
-> source and artifact verification
-> design-readiness audit
-> bounded next-experiment plan
-> Diagnostic scientific closeout
```

The current three coupled NIST process conditions remain unsuitable for
predictive, causal, or optimization claims.

## Corrected Product Boundary

The stable user-facing interface is the installable `mda` command. Case-study
scripts remain explicit workflow entry points. Registry, PGIR, evidence, and
release-governance commands remain internal repository interfaces.

```text
mda                     user-facing tabular analysis
python scripts/...      representative case-study workflows
python -m src.cli       internal platform and governance operations
```

New user workflows must not be added to the internal governance CLI by default.

## Current Hardening Priorities

### 1. Provenance-aware preprocessing

User-facing runs must:

- reject column names that collide after normalization;
- record original and final headers and dtypes;
- record blank normalization and numeric coercion;
- record introduced missing values and removed empty rows;
- preserve duplicate measurement rows;
- write a preprocessing audit and run manifest.

### 2. Immutable run outputs

A non-empty output directory must never be reused silently. A caller must choose
a new run name or explicitly request complete replacement. Original input
identity, platform version, options, row counts, and generated artifact paths
must remain inspectable.

### 3. Real package installation

The repository must build a wheel and source distribution. CI must install the
wheel and smoke-test the `mda` command on both Windows and Linux. A checkout that
only installs dependencies is not sufficient evidence of installability.

### 4. Candidate eligibility before ranking

Surrogate candidate predictions require a final eligibility layer:

- observed training-range violations are retained but not ranked;
- optional equipment, material, and safety constraints use an allowlisted JSON
  contract;
- arbitrary expressions are prohibited;
- constraint failures remain auditable;
- unconstrained prediction artifacts are preserved separately;
- predictions remain screening aids rather than process approval.

## Priority Rules

Work is prioritized in this order:

1. one complete user-facing workflow;
2. scientific validity and explicit claim boundaries;
3. provenance and reproducibility required by that workflow;
4. maintainability and proportional tests;
5. extension only after the current workflow is complete.

A new gate, schema, dataset, model, source, or instrument is not added unless it
removes a defined blocker in a current workflow.

## Source-Screening Stop Rule

A candidate external source receives one bounded screening stage covering:

- official identity and license;
- actual file or supported API accessibility;
- minimum metadata required for the intended analysis;
- file size and practical processing cost.

The source is placed on hold when access is denied, licensing is unclear, or the
required metadata cannot be recovered without disproportionate effort. The work
then moves to the next ranked source. One failed source must not create a series
of access-failure feature versions.

The Deep Blue route remains closed until materially new provider evidence is
available.

## Now

Complete the usability and provenance hardening layer:

1. preprocessing audit and fail-closed header identity;
2. immutable run directories and SHA-256 run manifests;
3. installable `mda` package and Windows/Linux wheel smoke tests;
4. constraint-aware final candidate ranking;
5. exact release-boundary regression checks;
6. current documentation and interface separation.

No new model or external dataset is needed for this phase.

## Next

Build one end-to-end case study from user-controlled or directly traceable
experimental data with the same identifiers across as many of these layers as
are genuinely available:

```text
sample identity
-> composition
-> processing history
-> characterization feature
-> property, quality, or reliability outcome
-> readiness and leakage audit
-> descriptive or baseline analysis
-> scientific closeout
```

A small compatible dataset is better than a large heterogeneous bundle. When the
existing design is insufficient, the output should identify the narrowest useful
next experiment rather than forcing model training.

## Later

- local UI only after the stable CLI workflows are clear;
- integrated HTML reporting after real users exercise the artifact contract;
- calibrated uncertainty only with defensible validation data;
- external Battery validation only after an independently admissible cohort and
  provider-to-local binding exist;
- new characterization instruments only after existing baselines receive
  representative-data validation;
- physics-informed models only when metadata, boundary conditions, and
  identifiability support the intended claim.

## Definition of Complete

A feature is complete only when it includes:

- implementation;
- proportional tests;
- a user-facing invocation;
- a representative example;
- documented assumptions and limitations;
- preserved valid existing behavior;
- generated-artifact and overwrite policy;
- a clear next action that does not reopen completed work without new evidence.
