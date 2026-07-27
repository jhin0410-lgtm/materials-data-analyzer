# Cross-Repository Public Release Readiness

## Purpose

This offline audit checks whether the two public repositories expose internally
consistent release metadata and the software validation expected for their
different release modes.

- `materials-data-analyzer` is primarily a versioned workflow repository.
- `materials-characterization-analyzer` is also a Python source and wheel
  distribution.

The audit does not create tags, GitHub Releases, package-index uploads, or
scientific results.

## Run

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

For the v2.7.0 promotion, the audit requires agreement among:

- `PUBLIC_RELEASE_VERSION`;
- `src/platform_core/version.py`;
- `CITATION.cff`;
- the `CHANGELOG.md` release heading;
- `docs/releases/V2_7_0.md`;
- `docs/PUBLIC_RELEASE_STATUS.md`.

At the promotion commit, `Unreleased` is empty. The expected status is:

```text
ready_for_current_head_release_action
```

This means tracked metadata is internally consistent and the audited HEAD has no
post-release feature entry. It does not prove that a Git tag or GitHub Release
exists.

After later work is added under `Unreleased`, the audit must return
`stable_release_metadata_valid_main_ahead`, and tagging that later HEAD as
v2.7.0 becomes disallowed.

## Characterization repository decision model

The characterization repository is audited as a Python package. The audit
requires agreement among `pyproject.toml`, runtime `mca.__version__`,
`CITATION.cff`, and the latest released changelog heading. Its CI must include
read-only permissions, pytest, wheel and source-distribution build, installed-
wheel CLI smoke testing, and distribution-content checks.

The pinned expected status remains:

```text
ready_for_external_tag_or_release_verification
```

## Coordinated v2.7.0 status

When the data repository is promoted at v2.7.0 and the pinned characterization
package remains consistent at 0.8.6, the expected cross-repository status is:

```text
ready_for_external_release_action
```

This indicates tracked metadata and compatibility evidence are ready for human-
reviewed external tag and release verification. The workflow itself does not
create either release.

## Pinned companion commit

The dedicated workflow audits `materials-characterization-analyzer` at:

```text
7242594f775b8dbe651a6131bb1b39b5f60c62cd
```

Changing this pin requires review and another successful audit.

## Preserved release results

The promotion preserves:

- Materials compatibility: `compatible_with_restrictions`;
- Battery compatibility: `partial`;
- retrieval reproducibility: `insufficient_evidence`;
- Ridge generalization: `unsupported`;
- cross-cohort comparability: `not_established`;
- external-cohort admission: `not_admitted`;
- predictive-validation readiness: `not_ready`;
- provider-to-local binding: `not_established`;
- Battery v2.6 scientific closeout: `inconclusive`;
- process-characterization workflows: `Diagnostic`;
- NIST predictive or causal modeling readiness: blocked.

These outcomes are release content, not upgraded by release validation.

## Scientific boundary

Release readiness is software governance, not scientific validation. A
successful audit does not establish source truth, sample comparability,
instrument calibration, causal effects, mechanism validity, predictive
generalization, process optimization, or engineering-release suitability.

No source data are recomputed, no model is trained, and no scientific evidence
level is promoted.
