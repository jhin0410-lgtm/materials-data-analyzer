# Public Release and Citation Status

## Current public release

The current stable public release is **v2.4.0**.

The canonical machine-readable version is stored in the repository-root file:

```text
PUBLIC_RELEASE_VERSION
```

Release notes:

- [`docs/releases/V2_4_0.md`](releases/V2_4_0.md)

Citation metadata:

- [`CITATION.cff`](../CITATION.cff)

## Relationship between `main` and the public release

The `main` branch contains additional work after v2.4.0. Those changes are
listed under `Unreleased` in [`CHANGELOG.md`](../CHANGELOG.md).

Internal feature-stage labels such as `v2.5.1`, `v2.5.2`, `v2.6.1`, or
`v2.6.2` inside the `Unreleased` section are development-stage identifiers.
They are not automatically promoted to a stable public software release.

Do not describe `main` as v2.5 or v2.6 unless a separate release closeout has:

1. completed software validation;
2. reviewed scientific claim boundaries and preserved negative results;
3. moved the applicable changelog entries into a stable release section;
4. added matching release notes;
5. updated `PUBLIC_RELEASE_VERSION` and `CITATION.cff` together;
6. confirmed that tracked files contain no raw restricted data, secrets,
   generated outputs, or user-specific paths.

## Reproducible citation

For a stable release, cite:

- repository title;
- public release version;
- repository URL;
- exact Git commit SHA used for the analysis;
- all external datasets, publications, standards, and upstream software used by
  the relevant case study.

When using the current `main` branch rather than the stable release, cite the
exact commit SHA. The public release version alone is insufficient because
`main` may include post-release workflows and scientific closeouts.

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
