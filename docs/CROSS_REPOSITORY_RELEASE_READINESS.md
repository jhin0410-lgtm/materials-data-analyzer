# Cross-Repository Public Release Readiness

## Purpose

This audit checks whether `materials-data-analyzer` and
`materials-characterization-analyzer` can be represented by clear, internally
consistent public release metadata.

It is a software-release check. It does not rerun scientific analyses, train a
model, approve a mechanism, or convert a Diagnostic result into a Supported
result.

## Run locally

Check out both repositories as sibling or otherwise accessible directories, then
run from `materials-data-analyzer`:

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

The manifest binds the JSON and Markdown results with SHA-256 checksums.

## Release modes

The repositories do not have to use the same distribution mechanism.

### materials-data-analyzer

This repository is currently a versioned workflow repository. Its public
contract is the tracked source tree, CLI scripts, requirements, documentation,
case-study contracts, and GitHub Actions validation. A wheel or source
distribution is not currently part of that contract.

A versioned release requires agreement among:

- `src/platform_core/version.py`;
- the `Unreleased` section of `CHANGELOG.md`;
- version and date fields in `CITATION.cff`;
- the intended Git tag and release notes.

### materials-characterization-analyzer

This repository is a Python package. A package release requires agreement among:

- `[project].version` in `pyproject.toml`;
- `src/mca/__init__.py`;
- `CITATION.cff`;
- the latest released heading in `CHANGELOG.md`;
- wheel and source-distribution construction;
- an installed-wheel `mca --version` smoke test.

## Audited result

At the audited commits:

### materials-data-analyzer

**Blocked for a versioned public release.**

Confirmed strengths:

- public README, MIT license, security policy, contribution guide, and
  changelog are present;
- CI uses read-only repository permission and runs the full pytest suite;
- the representative process-characterization workflow is documented and
  tested;
- commit-oriented citation metadata is available.

Blocking version evidence:

- `PLATFORM_VERSION` is `2.4.0`;
- the `Unreleased` changelog contains work named through `v2.6.2`;
- `CITATION.cff` deliberately contains no version or release date because a
  defensible next public version has not been selected.

The audit does not choose a version automatically. The next release must first
select a public version that includes all intended changes, then align runtime
metadata, changelog, citation metadata, and the tag.

### materials-characterization-analyzer

**Ready for tag creation, pending an external release action.**

The following all report `0.8.6`:

- `pyproject.toml`;
- runtime `__version__`;
- `CITATION.cff`;
- latest changelog release.

CI also runs tests, builds wheel and source distributions, installs the wheel,
executes `mca --version`, and checks that forbidden local-data paths are not
packaged.

The offline audit cannot verify whether a Git tag, GitHub Release, or package
index upload already exists. Those remain explicit external release actions.

## Required next action

1. Keep `materials-characterization-analyzer` at `0.8.6` unless new user-facing
   changes require another version.
2. Select the next `materials-data-analyzer` public version after reviewing all
   changes currently accumulated under `Unreleased`.
3. Update `PLATFORM_VERSION`, convert the intended changelog content into a
   dated release entry, and add the same version and date to `CITATION.cff`.
4. Rerun this audit.
5. Only after the audit reports coordinated readiness should reviewed tags or
   GitHub Releases be created.

## Scientific boundary

Release readiness means that software metadata, public documentation, build or
workflow contracts, and citations are internally consistent. It does not mean:

- a model is scientifically valid;
- a dataset is comparable for a new purpose;
- a process variable has a causal effect;
- a characterization feature confirms phase, mechanism, or composition;
- a result is ready for production or engineering release.
