# Public Release and Citation Status

## Current public release

The current stable public release is **v2.6.0**.

The canonical machine-readable version is stored in the repository-root file:

```text
PUBLIC_RELEASE_VERSION
```

Release notes:

- [`docs/releases/V2_6_0.md`](releases/V2_6_0.md)

Citation metadata:

- [`CITATION.cff`](../CITATION.cff)

## Release scope

v2.6.0 closes the completed internal feature stages `v2.5.1`, `v2.5.2`, and
`v2.6.1` through `v2.6.14`, together with the reviewed public-repository and
cross-repository integration work present at the promotion commit.

A separate v2.5.0 release was not created. The v2.5 compatibility and
retrieval-reproducibility stages are included in v2.6.0 because the complete
v2.6 evidence line was implemented and checksum-closed before a v2.5 public
boundary existed.

The release preserves rather than upgrades the tracked scientific outcomes:

- Materials compatibility: `compatible_with_restrictions`;
- Battery compatibility: `partial`;
- retrieval reproducibility: `insufficient_evidence`;
- Ridge generalization: `unsupported`;
- cross-cohort comparability: `not_established`;
- external-cohort admission: `not_admitted`;
- predictive-validation readiness: `not_ready`;
- Battery v2.6 scientific closeout: `inconclusive`;
- public process-characterization workflows: `Diagnostic`.

## Relationship between `main` and the public release

At the v2.6.0 promotion commit, `Unreleased` contains no additional feature
work. That commit is eligible for reviewed external tag or GitHub Release
creation after all release workflows pass.

After any subsequent change is merged to `main`, cite the exact commit SHA in
addition to v2.6.0 and treat `main` as ahead of the stable release until another
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
