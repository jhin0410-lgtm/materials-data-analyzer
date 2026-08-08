# Generic external-evidence screening contract

## Purpose

The Virtual Research Partner must not respond to a weak or exhausted benchmark by
searching for arbitrary new rows until something looks favorable. This layer converts
an exact evidence gap into a source-screening contract and evaluates candidate sources
before target acquisition, model fitting, or policy evaluation.

The first consumer is the Materials Project benchmark-v1 closeout. The frozen Fe/Si,
2-5 element identity inventory currently exposes no material IDs outside the original
838-row Materials Project universe under the canonical v1.3 query scope. A new
same-source confirmatory cohort is therefore unavailable under that frozen scope.

This does **not** justify widening the query after benchmark results are known. It
creates a requirement for a scientifically compatible, source-disjoint candidate.

## Generic screening states

`external_evidence_contract.py` reports one of six dispositions:

- `eligible` — all declared metadata and semantic checks match and source independence
  is confirmed;
- `diagnostic_only` — the candidate is semantically usable but is not source-disjoint;
- `semantics_audit_required` — one or more required scientific meanings remain
  unresolved;
- `metadata_incomplete` — provenance, reuse, independence, or required metadata are
  unresolved;
- `scientifically_ineligible` — a required check is a confirmed mismatch or reuse is
  restricted;
- `unavailable` — the candidate source is not currently available.

These are source-screening dispositions, not scientific evidence levels.

Even an `eligible` result keeps all of the following false:

- automatic data acquisition authorization;
- model-fit authorization;
- external-validation claim authorization.

The next step after an eligible screen is to predeclare and freeze the exact
acquisition/evaluation protocol before candidate target values are retrieved.

## Materials Project requirement

The versioned declaration is:

`configs/research/materials_project_external_evidence_requirement.v1.json`

It is generated only from a completed target-blind same-source readiness artifact
whose outcome is exactly `no_new_same_source_identity_cohort`.

The requirement preserves the frozen chemistry scope:

- Fe and Si required;
- 2 to 5 elements;
- phase-stability target corresponding to `energy_above_hull`;
- target unit `eV/atom`.

A matching field name and unit are **not** sufficient for cross-source comparability.
Candidate evidence must explicitly resolve calculation and thermodynamic semantics,
including at least:

- dataset identity and version;
- structure/composition identifiers;
- calculation code/version;
- exchange-correlation functional;
- pseudopotential or equivalent basis/method metadata;
- energy-correction scheme;
- elemental reference energies;
- competing-phase inventory;
- convex-hull construction method;
- target definition and unit;
- thermodynamic reference state;
- correction and hull semantics;
- composition-scope comparability;
- cross-source structure identity mapping.

A Materials Project mirror or other source that inherits Materials Project provenance
cannot satisfy source-disjoint validation merely because its record identifiers differ.

## Run

After the same-source readiness command has completed with zero new IDs:

```powershell
$python = (Resolve-Path ".\.venv313\Scripts\python.exe").Path

& $python `
  .\scripts\build_materials_project_external_evidence_requirement.py `
  --readiness .\outputs\materials_project_independent_source_readiness_v1\independent_source_readiness.json `
  --output .\outputs\materials_project_external_evidence_requirement_v1
```

Expected output:

```text
outputs/materials_project_external_evidence_requirement_v1/
  external_evidence_requirement.json
```

The output binds the exact readiness bytes by SHA-256, the readiness ID, Materials
Project database version, original benchmark identity, row counts, and observed zero
new same-source material IDs.

## Relationship to NASA

NASA already has a domain-specific external-requirement and candidate-source audit.
This generic contract does not rewrite those public APIs in its first version. NASA's
exact-horizon, target/reference, and protocol-temperature rules remain authoritative
for that workflow.

The shared abstraction is intentionally smaller: explicit evidence requirement,
source/provenance independence, required metadata checks, required semantic checks,
and a fail-closed disposition before acquisition.

A future migration may adapt NASA to this common representation only if it can be done
without changing its existing scientific behavior or public outputs.

## Relationship to characterization evidence

This source-screening contract does not replace the characterization handoff policy.
`materials-characterization-analyzer` remains the instrument-specific evidence
producer. `materials-data-analyzer` independently enforces the producer-declared
`downstream_use_policy` before descriptive, association, predictive, causal, or
engineering use.

If an external candidate eventually contributes characterization evidence, **both**
gates apply:

1. external-source/provenance and semantic compatibility must be established for the
   research requirement;
2. the characterization bundle's `downstream_use_policy` must authorize the requested
   downstream use.

Passing either gate cannot override a failure in the other. In particular, a
source-disjoint characterization dataset can still be descriptive-only when calibration,
review, independence grouping, timing, causal design, or operational validation do not
support stronger use.

The existing cross-repository policy workflow remains pinned to the verified MCA
producer contract. Later SAED source-readiness work is additive and does not weaken that
consumer boundary.

## Scientific boundary

This stage is **DevelopmentDiagnostic infrastructure**. It can establish that a source
candidate is worth a separately frozen acquisition/evaluation protocol. It does not by
itself establish source-level independence of downloaded records, predictive validity,
causal validity, experimental synthesizability, DFT replacement, production screening,
or engineering readiness.
