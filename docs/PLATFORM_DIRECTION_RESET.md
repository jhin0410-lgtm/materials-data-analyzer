# Platform Direction Reset

Status: `active_direction_after_battery_v2_6_closeout`

## Mission

The project is a Virtual Research Partner for materials and manufacturing work.
It connects tabular process, quality, reliability, Battery, and characterization
results while preserving sample identity, units, provenance, validation scope,
and scientific limitations.

It is not a Battery-only program. Battery is one trajectory-oriented case study
inside a broader engineering-data platform.

## Repository Roles

### `materials-data-analyzer`

Owns tabular engineering workflows:

- process conditions and experiment tables;
- quality, SPC, and Smart Factory logs;
- reliability and time-dependent asset records;
- Battery cycle and trajectory tables;
- readiness, leakage, validation, simulation screening, and reporting;
- cross-domain sample-level tables used for downstream statistics or models.

### `materials-characterization-analyzer`

Owns instrument-specific interpretation boundaries and feature extraction:

- XRD;
- SEM and EDS;
- Raman;
- TEM and SAED;
- future XPS, FTIR, TGA, and DSC only when their individual contracts are ready.

The repositories remain independently installable. They exchange data through
explicit identifiers and versioned result contracts, never through row order,
inferred filenames, or direct imports from one repository's internal modules.

## Current State

### Completed or usable foundations

- CSV-first EDA, process, reliability, SPC, Smart Factory, and simulation modes;
- group-aware, time-aware, and asset-aware validation utilities;
- Materials Project, Smart Factory, Reliability, and Battery case-study evidence;
- characterization baselines for XRD, SEM, EDS, Raman, TEM, and SAED;
- long-format characterization feature records containing `sample_id`,
  `measurement_id`, instrument, feature semantics, unit, method, source identity,
  preprocessing identity, and quality flags.

### Overdeveloped area

Battery v2.6 accumulated too many source-access and evidence-closeout stages
relative to the amount of new user-facing analysis. The safeguards remain useful,
but that pattern must not become the normal development loop.

The Deep Blue route is closed. It must not be reopened through repeated requests,
browser impersonation, credential workarounds, or additional gate-only versions.

### Main missing capability

The two repositories describe a stable handoff but previously lacked an actual
consumer workflow. Characterization features could be exported, but process and
characterization rows were not yet validated, pivoted, and joined through an
explicit sample contract.

## Priority Rules

Work is prioritized in this order:

1. a complete user-facing workflow;
2. scientific validity and explicit claim boundaries;
3. provenance and reproducibility needed by that workflow;
4. maintainability and tests;
5. extension only after the current workflow is complete.

A new gate, schema, dataset, model, or instrument is not added unless it removes
a defined blocker in a current workflow.

## Source-Screening Stop Rule

A candidate external source receives one bounded screening stage covering:

- official identity and license;
- actual file or supported API accessibility;
- minimum metadata needed for the intended analysis;
- file size and practical processing cost.

The source is placed on hold when access is denied, licensing is unclear, or the
required metadata cannot be recovered without disproportionate effort. The work
then moves to the next ranked candidate. One failed source must not create a
sequence of access-failure feature versions.

## Now

Implement and validate the characterization-feature handoff:

1. accept one or more existing long-format feature CSVs;
2. validate the stable 12-column contract;
3. reject missing IDs, non-finite values, invalid hashes, ambiguous measurement
   mappings, mixed methods, and mixed preprocessing;
4. reject duplicate semantic features rather than silently averaging them;
5. create a stable feature dictionary and one-row-per-sample wide table;
6. optionally outer-join a process table through explicit, unique `sample_id`;
7. emit a join audit and provenance-aware manifest;
8. provide a synthetic command that runs in a clean checkout.

This is software integration. It does not prove that two rows refer to the same
physical specimen or that extracted features are scientifically comparable.

## Next

Build one representative real end-to-end case study with the same sample IDs
across at least two of these layers:

```text
processing history
-> characterization feature
-> property, quality, or reliability outcome
-> readiness and leakage audit
-> descriptive or baseline validation
-> scientific claim closeout
```

The dataset should be selected for complete identifiers and metadata, not merely
because it is large or popular. A small compatible dataset is better than a large
heterogeneous bundle.

## Later

- add manifest-to-feature binding checks when a representative real handoff needs
  them;
- extend integrated reporting after the handoff is used by a real case study;
- add new characterization instruments only after existing baselines receive
  representative-data validation;
- revisit external Battery validation only when an independently admissible
  cohort and provider-to-local binding are available.

## Definition of Complete

A feature is complete only when it includes:

- implementation;
- proportional tests;
- a user-facing invocation;
- a representative example;
- documented assumptions and limitations;
- preserved existing behavior;
- a clear next action that does not reopen completed work without new evidence.
