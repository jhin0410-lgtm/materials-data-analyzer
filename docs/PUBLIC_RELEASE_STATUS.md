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

## Release boundary

v2.7.0 includes the internal v2.5.1-v2.5.2 compatibility and retrieval stages,
the complete v2.6.1-v2.6.14 Battery evidence line, and the audited 38-commit
post-v2.6 integration and public-repository scope.

The v2.6.14 closeout remains a real internal boundary: it closes the Battery v2.6
evidence line and authorizes no automatic v2.6.15 stage. The later generic
characterization handoff, public producer-consumer workflows, representative
NIST workflow, repository hardening, citation governance, and release-readiness
audits are included in v2.7.0 rather than retroactively relabeled as v2.6.0.

No separate v2.5.0 or v2.6.0 public release is created.

## Preserved results

The release preserves rather than upgrades:

- Materials adapter: `compatible_with_restrictions`;
- Battery adapter: `partial`;
- retrieval reproducibility: `insufficient_evidence`;
- Ridge forecast improvement: `unsupported`;
- cross-cohort comparability: `not_established`;
- external-cohort admission: `not_admitted`;
- predictive-validation readiness: `not_ready`;
- provider-to-local binding: `not_established`;
- Battery evidence-line scientific status: `inconclusive`;
- public process-characterization cases: `Diagnostic`;
- NIST predictive or causal modeling readiness: blocked.

## Relationship between `main` and the public release

At the v2.7.0 promotion commit, `Unreleased` contains no additional feature work.
That commit is eligible for reviewed external tag or GitHub Release creation
after all release workflows pass.

After any subsequent change is merged to `main`, cite the exact commit SHA in
addition to v2.7.0 and treat `main` as ahead of the stable release until another
release closeout is completed.

A future release must complete software validation, review scientific claim
boundaries, move intended `Unreleased` scope into release notes, update all
version sources together, and confirm that tracked files contain no restricted
raw data, secrets, generated outputs, or user-specific paths.

## Reproducible citation

For a stable release, cite the repository title, public release version,
repository URL, exact Git commit SHA, and all external datasets, publications,
standards, and upstream software used by the relevant case study.

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
