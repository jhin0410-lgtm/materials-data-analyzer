# Cross-Repository Public Release Readiness

## Purpose

This audit checks whether `materials-data-analyzer` and
`materials-characterization-analyzer` have internally consistent public release
metadata and tracked compatibility evidence.

It is an offline software-release audit. It does not create tags, publish
packages, rerun scientific analyses, or promote any scientific conclusion.

## Run locally

```powershell
python scripts/audit_cross_repository_release_readiness.py `
  --characterization-repo-root ..\materials-characterization-analyzer `
  --characterization-commit 7242594f775b8dbe651a6131bb1b39b5f60c62cd `
  --output outputs\cross_repository_release_readiness
```

The output directory must be new or empty.

## Outputs

```text
cross_repository_release_readiness.json
cross_repository_release_readiness.md
cross_repository_release_readiness_manifest.json
```

The manifest records SHA-256 checksums for the JSON and Markdown outputs.

## Repository release modes

The repositories intentionally use different release contracts.

### materials-data-analyzer

This is a versioned workflow and source repository. Its stable public version is
read from `PUBLIC_RELEASE_VERSION`. The audit requires agreement among:

- `PUBLIC_RELEASE_VERSION`;
- `src/platform_core/version.py`;
- `CITATION.cff`;
- the matching stable heading in `CHANGELOG.md`;
- `docs/PUBLIC_RELEASE_STATUS.md`;
- the matching file under `docs/releases/`.

The current stable public version is `2.4.0`.

The `main` branch contains post-release work. Labels such as `v2.5.1`, `v2.6.1`,
or `v2.6.2` under `Unreleased` are development-stage identifiers, not automatic
stable releases. The audit accepts these higher labels only because the tracked
release policy explicitly separates them from the stable version and requires
users of `main` to cite the exact commit SHA.

Wheel or source-distribution construction is not currently part of this
repository's public contract.

### materials-characterization-analyzer

This is a Python package repository. The audit requires agreement among:

- `[project].version` in `pyproject.toml`;
- runtime `__version__`;
- `CITATION.cff`;
- the latest stable changelog heading.

It also checks that CI:

- runs tests;
- builds wheel and source distributions;
- installs the wheel;
- executes `mca --version`;
- checks distribution contents for forbidden local-data paths.

At the pinned audited commit, all version sources report `0.8.6`.

## Audited decision

### materials-data-analyzer

```text
ready_for_existing_release_metadata_pending_external_tag_verification
```

Confirmed:

- stable public version: `2.4.0`;
- platform version: `2.4.0`;
- citation version: `2.4.0`;
- stable changelog heading and release notes are present;
- higher Unreleased development-stage labels are explicitly separated from the
  stable release;
- public documentation, security policy, contribution guide, CI, representative
  workflow, and cross-repository handoff evidence are present.

`CITATION.cff` does not currently contain `date-released`. The repository's
tracked policy does not treat that optional CFF field as a blocker, but the audit
records it as a warning.

### materials-characterization-analyzer

```text
ready_for_tag_creation_pending_external_release_action
```

Confirmed:

- package, runtime, citation, and changelog versions all equal `0.8.6`;
- test, build, wheel installation, CLI smoke test, and distribution-content
  checks are present.

### Coordinated status

```text
ready_for_coordinated_external_release_verification
```

This means tracked metadata and compatibility evidence are consistent. It does
not prove that the expected Git tags, GitHub Releases, or package-index uploads
exist.

## Required next action

Verify the intended tags and GitHub Releases through an explicit reviewed
release action. Do not create or move tags automatically from this audit.

For `materials-characterization-analyzer`, package publication should occur only
when the owner explicitly chooses a distribution target and confirms that
`0.8.6` has not already been published there.

For `materials-data-analyzer`, users analyzing the post-`2.4.0` `main` branch
must cite the exact commit SHA in addition to the stable public release context.

## Scientific boundary

Release readiness establishes metadata, documentation, build or workflow, and
citation consistency only. It does not establish:

- sample comparability;
- causal process effects;
- predictive generalization;
- phase, composition, chemical-state, or mechanism confirmation;
- optimization validity;
- production or engineering-release suitability.
