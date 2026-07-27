# Cross-Repository Public Release Readiness

## Purpose

This offline audit checks whether `materials-data-analyzer` and
`materials-characterization-analyzer` expose internally consistent release
metadata and the software validation expected for their different release modes.
It does not create tags, GitHub Releases, package-index uploads, or scientific
results.

## Run

Check out both repositories independently, then run:

```powershell
python scripts/audit_cross_repository_release_readiness.py `
  --data-repo-root . `
  --characterization-repo-root ../materials-characterization-analyzer `
  --characterization-commit <audited-commit-sha> `
  --output outputs/cross_repository_release_readiness
```

The output directory must be absent or empty. Existing files are preserved and
cause a fail-closed error.

Outputs:

- `cross_repository_release_readiness.json`;
- `cross_repository_release_readiness.md`;
- `cross_repository_release_readiness_manifest.json`.

The manifest records SHA-256 for the JSON summary and Markdown report.

## Data repository decision model

The stable public release is **v2.7.0**. The audit requires agreement among:

- `PUBLIC_RELEASE_VERSION`;
- runtime `PLATFORM_VERSION`;
- `CITATION.cff`, including `date-released: 2026-07-28`;
- the `CHANGELOG.md` v2.7.0 release heading;
- `docs/releases/V2_7_0.md`;
- `docs/PUBLIC_RELEASE_STATUS.md`.

At the reviewed promotion boundary, the `Unreleased` section contains no feature
work. The expected data-repository status is:

```text
ready_for_current_head_release_action
```

This means tracked metadata is internally consistent and the reviewed commit may
proceed to separate external tag or GitHub Release verification. It does not
mean a tag or release already exists.

After any subsequent commit adds new `Unreleased` work, the expected status
returns to `stable_release_metadata_valid_main_ahead`, and the exact commit SHA
must be cited with v2.7.0.

## Characterization repository decision model

The characterization repository is audited as a Python source and wheel
distribution. The audit requires agreement among:

- `pyproject.toml` project version;
- runtime `mca.__version__`;
- `CITATION.cff`;
- latest released changelog heading.

Its CI must include read-only repository permissions, pytest, wheel and source-
distribution build, installed-wheel `mca --version` smoke testing, and
distribution artifact checks.

The pinned companion commit is:

```text
7242594f775b8dbe651a6131bb1b39b5f60c62cd
```

That commit reports `0.8.6` consistently. The offline audit cannot verify whether
a Git tag, GitHub Release, or package-index upload exists.

## Coordinated decision

When the data repository is `ready_for_current_head_release_action`, the
characterization package metadata is consistent, and tracked NIST compatibility
evidence is present, the expected cross-repository status is:

```text
ready_for_external_release_action
```

External action remains separate. No tag, release, or package publication is
created by this workflow.

## Scientific boundary

This is software-release governance. Passing it does not establish source truth,
sample comparability, calibration, measurement uncertainty, causal
identification, mechanism validity, predictive generalization, optimization
readiness, or engineering-release suitability. The v2.7.0 release preserves
**Supported**, **Diagnostic**, **Inconclusive**, and **Unsupported** evidence
labels without promotion.
