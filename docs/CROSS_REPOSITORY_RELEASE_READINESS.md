# Cross-Repository Public Release Readiness

## Purpose

This audit checks whether the two public repositories expose internally
consistent release metadata and the software validation expected for their
different release modes.

- `materials-data-analyzer` is primarily a versioned workflow repository.
- `materials-characterization-analyzer` is also a Python source and wheel
  distribution.

The audit is offline. It does not create tags, GitHub Releases, package-index
uploads, or scientific results.

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

## Outputs

- `cross_repository_release_readiness.json`
- `cross_repository_release_readiness.md`
- `cross_repository_release_readiness_manifest.json`

The manifest records SHA-256 for the JSON summary and Markdown report.

## Data repository decision model

The audit separates two questions that must not be conflated.

### Is the existing stable release metadata valid?

For the current repository state, the stable public release is `v2.4.0`. The
audit requires agreement among:

- `PUBLIC_RELEASE_VERSION`;
- `src/platform_core/version.py`;
- `CITATION.cff`;
- the `CHANGELOG.md` release heading;
- `docs/releases/V2_4_0.md`;
- `docs/PUBLIC_RELEASE_STATUS.md`.

### Can the current `main` commit be tagged as that release?

No. `main` contains additional work under `Unreleased`, including feature-stage
labels through `v2.6.2`. Therefore valid v2.4.0 citation metadata does not make
the current HEAD a clean v2.4.0 release commit.

The expected status is:

```text
stable_release_metadata_valid_main_ahead
```

The next public version is not selected automatically. A future release must
move the intended `Unreleased` scope into explicit release notes and update all
version sources together.

## Characterization repository decision model

The characterization repository is audited as a Python package. The audit
requires agreement among:

- `pyproject.toml` project version;
- runtime `mca.__version__`;
- `CITATION.cff`;
- latest released changelog heading.

Its CI must include:

- read-only contents permission;
- pytest;
- wheel and source-distribution build;
- installed-wheel `mca --version` smoke testing;
- distribution artifact checks.

The offline audit cannot verify whether a Git tag, GitHub Release, or package
index upload exists. Those remain external release actions.

## Pinned companion commit

The dedicated workflow audits `materials-characterization-analyzer` at:

```text
7242594f775b8dbe651a6131bb1b39b5f60c62cd
```

That commit contains the corrected `0.8.6` public package metadata and the
four-material source-safety fixes. Changing the pin requires review and another
successful audit.

## Scientific boundary

Release readiness is software governance, not scientific validation.

A successful audit does not establish:

- sample comparability;
- instrument calibration or measurement uncertainty;
- causal process effects;
- mechanism validity;
- predictive generalization;
- process optimization;
- engineering-release suitability.

No source data are recomputed, no model is trained, and no scientific evidence
level is promoted.
