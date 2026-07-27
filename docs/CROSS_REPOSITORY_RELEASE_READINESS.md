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

### Is the stable release metadata internally valid?

For the v2.7.0 closeout, the audit requires agreement among:

- `PUBLIC_RELEASE_VERSION`;
- `src/platform_core/version.py`;
- `CITATION.cff`;
- the `CHANGELOG.md` release heading;
- `docs/releases/V2_7_0.md`;
- `docs/PUBLIC_RELEASE_STATUS.md`.

### Is the audited data-repository HEAD eligible for external release action?

The v2.7.0 closeout keeps the `Unreleased` section empty. The expected data
repository status is therefore:

```text
ready_for_current_head_release_action
```

This status means the tracked version, citation, changelog, release notes, and
runtime metadata are consistent and no post-release feature entry is present.
It does not prove that a Git tag or GitHub Release exists.

After any later feature is added under `Unreleased`, the same audit must return:

```text
stable_release_metadata_valid_main_ahead
```

and current-HEAD tagging as v2.7.0 becomes disallowed.

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

The expected pinned-package status remains:

```text
ready_for_external_tag_or_release_verification
```

The offline audit cannot verify whether a Git tag, GitHub Release, or package
index upload exists. Those remain explicit external release actions.

## Coordinated v2.7.0 closeout status

When the data repository is closed at v2.7.0 and the pinned characterization
package remains consistent at 0.8.6, the expected cross-repository status is:

```text
ready_for_external_release_action
```

This means tracked release metadata and compatibility evidence are ready for
human-reviewed external tag and release verification. The workflow itself does
not create either release.

## Pinned companion commit

The dedicated workflow audits `materials-characterization-analyzer` at:

```text
7242594f775b8dbe651a6131bb1b39b5f60c62cd
```

That commit contains the corrected `0.8.6` public package metadata and the
four-material source-safety fixes. Changing the pin requires review and another
successful audit.

## Preserved release results

Release closeout must preserve, rather than hide, the tracked scientific
outcomes:

- Materials composition physics: `performance_degraded`;
- known-structure predictive value: `structure_predictive_value_limited`;
- Materials compatibility: compatible with restrictions;
- Battery compatibility: partial;
- retrieval reproducibility: `insufficient_evidence`;
- Battery forecast improvement: `unsupported`;
- process-characterization workflows: `Diagnostic`;
- NIST predictive or causal modeling readiness: blocked.

These results are validated as release content, not upgraded by the release.

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
