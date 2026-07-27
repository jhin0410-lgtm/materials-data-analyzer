# Public Release and Citation Status

## Current public release

The current stable public release is **v2.7.0**.

The canonical machine-readable version is stored in the repository-root file:

```text
PUBLIC_RELEASE_VERSION
```

Release notes:

- [`docs/releases/V2_7_0.md`](releases/V2_7_0.md)

Citation metadata:

- [`CITATION.cff`](../CITATION.cff)

## Release scope

v2.7.0 closes the complete development scope accumulated after v2.4.0.
Internal labels `v2.5.1`, `v2.5.2`, and `v2.6.1` through `v2.6.14` describe
implementation and evidence stages; they are not separate public releases.

The release includes:

- version-allowlisted compatibility adapters and retrieval-reproducibility
  audits;
- the leakage-safe Battery warm-start benchmark and deterministic failure
  diagnostics;
- the complete comparability, admission, SNL LFP, Michigan Formation, and
  checksum-bound v2.6 external-evidence line;
- schema `1.0` cross-repository characterization bundle consumption;
- pinned DWCNT, RWGS, four-carbon-material, and NIST producer-consumer workflows;
- a representative NIST process-characterization workflow, design
  identifiability audit, and bounded next-experiment plan;
- public repository hardening, citation metadata, and deterministic release
  audits.

The release does not convert restricted or negative results into positive
scientific claims. Materials compatibility remains restricted, Battery
compatibility remains partial, retrieval reproducibility remains
`insufficient_evidence`, Ridge forecasting remains **Unsupported**, the v2.6
external-evidence closeout remains **Inconclusive**, and public
process-characterization cases remain **Diagnostic**.

## Relationship between `main` and the public release

At the v2.7.0 promotion commit, `Unreleased` contains no additional feature
work. The reviewed promotion commit is eligible for separate external tag or
GitHub Release verification after all required workflows pass.

After any subsequent change is merged to `main`, cite the exact commit SHA in
addition to v2.7.0 and treat `main` as ahead of the stable release until another
release closeout is completed.

A future release must:

1. complete software validation;
2. review scientific claim boundaries and preserve negative results;
3. move the intended `Unreleased` scope into a stable release section;
4. add matching release notes;
5. update `PUBLIC_RELEASE_VERSION`, runtime version, and `CITATION.cff` together;
6. confirm that tracked files contain no raw restricted data, secrets,
   generated outputs, or user-specific paths.

## Reproducible citation

For a stable release, cite:

- repository title;
- public release version;
- repository URL;
- exact Git commit SHA used for the analysis;
- all external datasets, publications, standards, and upstream software used by
  the relevant case study.

The root MIT license covers original repository code and documentation only. It
does not relicense third-party datasets, publications, standards, model files,
or instrument exports.

## Release validation boundary

A passing test suite establishes software behavior for the tested environment.
It does not prove that samples are comparable, preprocessing is scientifically
defensible, a process effect is causal, a model generalizes, or a result is
suitable for engineering release.

Every public release must preserve the repository's scientific evidence labels:

- **Supported**
- **Diagnostic**
- **Inconclusive**
- **Unsupported**
