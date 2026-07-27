"""Audit public-release readiness across the data and characterization repositories.

The audit is offline and read-only with respect to both repositories. It never
creates tags, GitHub releases, package-index uploads, or scientific results.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import tomllib
from pathlib import Path
from typing import Any

SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
VERSION_TOKEN_RE = re.compile(r"(?<![0-9])v?(\d+\.\d+\.\d+)(?![0-9])")
PLATFORM_VERSION_RE = re.compile(
    r'^PLATFORM_VERSION\s*=\s*["\'](\d+\.\d+\.\d+)["\']', re.MULTILINE
)
RUNTIME_VERSION_RE = re.compile(
    r'^__version__\s*=\s*["\'](\d+\.\d+\.\d+)["\']', re.MULTILINE
)
CHANGELOG_RELEASE_RE = re.compile(
    r"^##\s+(?:\[)?(\d+\.\d+\.\d+)(?:\])?(?:\s|$)", re.MULTILINE
)

SUMMARY_FILE = "cross_repository_release_readiness.json"
REPORT_FILE = "cross_repository_release_readiness.md"
MANIFEST_FILE = "cross_repository_release_readiness_manifest.json"


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_version(value: str) -> tuple[int, int, int]:
    if not SEMVER_RE.fullmatch(value):
        raise ValueError(f"Invalid semantic version: {value}")
    major, minor, patch = value.split(".")
    return int(major), int(minor), int(patch)


def _read_text(root: Path, relative: str) -> str:
    path = root / relative
    if not path.is_file():
        raise FileNotFoundError(f"Required tracked file not found: {path}")
    return path.read_text(encoding="utf-8")


def _presence(root: Path, required: list[str]) -> tuple[list[str], list[str]]:
    present = [relative for relative in required if (root / relative).is_file()]
    missing = [relative for relative in required if not (root / relative).is_file()]
    return present, missing


def _extract_unreleased(changelog: str) -> str:
    match = re.search(r"^##\s+\[?Unreleased\]?\s*$", changelog, re.MULTILINE)
    if not match:
        return ""
    remainder = changelog[match.end() :]
    next_heading = re.search(r"^##\s+", remainder, re.MULTILINE)
    return remainder[: next_heading.start()] if next_heading else remainder


def _extract_cff_scalar(text: str, key: str) -> str | None:
    match = re.search(
        rf"^{re.escape(key)}:\s*[\"']?([^\n\"']+)", text, re.MULTILINE
    )
    return match.group(1).strip() if match else None


def _highest_named_version(text: str) -> str | None:
    versions = {match.group(1) for match in VERSION_TOKEN_RE.finditer(text)}
    return max(versions, key=parse_version) if versions else None


def audit_data_repository(root: Path) -> dict[str, Any]:
    root = root.resolve()
    baseline_required = [
        "README.md",
        "LICENSE",
        "SECURITY.md",
        "CONTRIBUTING.md",
        "CHANGELOG.md",
        "CITATION.cff",
        "PUBLIC_RELEASE_VERSION",
        "docs/PUBLIC_RELEASE_STATUS.md",
        "requirements.txt",
        ".github/workflows/ci.yml",
        "src/platform_core/version.py",
        "scripts/run_representative_process_characterization_workflow.py",
        "docs/REPRESENTATIVE_PROCESS_CHARACTERIZATION_WORKFLOW.md",
    ]
    present, missing = _presence(root, baseline_required)
    blockers: list[str] = []
    warnings: list[str] = []
    if missing:
        blockers.append(f"Missing required public files: {missing}")

    public_version = _read_text(root, "PUBLIC_RELEASE_VERSION").strip()
    parse_version(public_version)
    release_notes_relative = (
        f"docs/releases/V{public_version.replace('.', '_')}.md"
    )
    if (root / release_notes_relative).is_file():
        present.append(release_notes_relative)
    else:
        missing.append(release_notes_relative)
        blockers.append(
            f"Release notes for public version {public_version} are missing: "
            f"{release_notes_relative}"
        )

    runtime_text = _read_text(root, "src/platform_core/version.py")
    runtime_match = PLATFORM_VERSION_RE.search(runtime_text)
    if not runtime_match:
        raise ValueError("Unable to parse PLATFORM_VERSION from data repository.")
    runtime_version = runtime_match.group(1)
    if runtime_version != public_version:
        blockers.append(
            f"PLATFORM_VERSION {runtime_version} does not match public release "
            f"version {public_version}."
        )

    citation = _read_text(root, "CITATION.cff")
    citation_version = _extract_cff_scalar(citation, "version")
    citation_date = _extract_cff_scalar(citation, "date-released")
    if citation_version != public_version:
        blockers.append(
            f"CITATION.cff version {citation_version!r} does not match public "
            f"release version {public_version}."
        )
    if citation_date is None:
        warnings.append(
            "CITATION.cff has no date-released; this is permitted for the "
            "repository citation but should be added at the next formal release."
        )

    changelog = _read_text(root, "CHANGELOG.md")
    if f"## v{public_version}" not in changelog:
        blockers.append(
            f"CHANGELOG.md does not contain the public release heading v{public_version}."
        )
    unreleased = _extract_unreleased(changelog)
    highest_unreleased = _highest_named_version(unreleased)
    main_ahead = bool(unreleased.strip())
    if highest_unreleased and parse_version(highest_unreleased) > parse_version(
        public_version
    ):
        warnings.append(
            "The main branch contains post-release work named through "
            f"{highest_unreleased}; current HEAD must not be tagged as v{public_version}."
        )

    if (root / release_notes_relative).is_file():
        release_notes = _read_text(root, release_notes_relative)
        if not release_notes.startswith(f"# v{public_version} -"):
            blockers.append(
                f"{release_notes_relative} does not identify v{public_version}."
            )

    status_doc = _read_text(root, "docs/PUBLIC_RELEASE_STATUS.md")
    if f"stable public release is **v{public_version}**" not in status_doc:
        blockers.append(
            "PUBLIC_RELEASE_STATUS.md does not identify the canonical public release."
        )
    if "exact Git commit SHA" not in status_doc:
        blockers.append(
            "PUBLIC_RELEASE_STATUS.md does not require commit-level reproducibility."
        )

    ci = _read_text(root, ".github/workflows/ci.yml")
    if "permissions:\n  contents: read" not in ci:
        blockers.append("CI does not declare read-only contents permission.")
    if "python -m pytest -q" not in ci:
        blockers.append("CI does not run the complete pytest suite.")

    if blockers:
        status = "blocked_release_metadata_inconsistent"
    elif main_ahead:
        status = "stable_release_metadata_valid_main_ahead"
    else:
        status = "ready_for_current_head_release_action"

    return {
        "repository": "materials-data-analyzer",
        "release_mode": "versioned_repository_workflow",
        "status": status,
        "public_release_version": public_version,
        "runtime_platform_version": runtime_version,
        "citation_version": citation_version,
        "citation_date_released": citation_date,
        "highest_unreleased_named_version": highest_unreleased,
        "main_contains_post_release_work": main_ahead,
        "current_main_tagging_allowed": not blockers and not main_ahead,
        "stable_release_metadata_valid": not blockers,
        "required_files_present": sorted(set(present)),
        "required_files_missing": sorted(set(missing)),
        "blockers": blockers,
        "warnings": warnings,
        "verified_contracts": {
            "release_notes_present": (root / release_notes_relative).is_file(),
            "representative_workflow_documented": True,
            "read_only_ci_permissions": "permissions:\n  contents: read" in ci,
            "full_test_command_present": "python -m pytest -q" in ci,
            "package_distribution_required": False,
        },
    }


def audit_characterization_repository(root: Path) -> dict[str, Any]:
    root = root.resolve()
    required = [
        "README.md",
        "LICENSE",
        "SECURITY.md",
        "CONTRIBUTING.md",
        "CHANGELOG.md",
        "CITATION.cff",
        "pyproject.toml",
        ".github/workflows/ci.yml",
        "src/mca/__init__.py",
    ]
    present, missing = _presence(root, required)
    blockers: list[str] = []
    warnings: list[str] = []
    if missing:
        blockers.append(f"Missing required public files: {missing}")

    pyproject = tomllib.loads(_read_text(root, "pyproject.toml"))
    project = pyproject.get("project")
    if not isinstance(project, dict) or not isinstance(project.get("version"), str):
        raise ValueError("Unable to parse [project].version from pyproject.toml.")
    package_version = project["version"]

    runtime_match = RUNTIME_VERSION_RE.search(
        _read_text(root, "src/mca/__init__.py")
    )
    if not runtime_match:
        raise ValueError("Unable to parse __version__ from characterization package.")
    runtime_version = runtime_match.group(1)

    citation = _read_text(root, "CITATION.cff")
    citation_version = _extract_cff_scalar(citation, "version")
    citation_date = _extract_cff_scalar(citation, "date-released")
    releases = CHANGELOG_RELEASE_RE.findall(_read_text(root, "CHANGELOG.md"))
    latest_changelog_version = releases[0] if releases else None

    version_sources = {
        "pyproject": package_version,
        "runtime": runtime_version,
        "citation": citation_version,
        "changelog_latest_release": latest_changelog_version,
    }
    if None in version_sources.values() or len(set(version_sources.values())) != 1:
        blockers.append(
            f"Characterization version sources are inconsistent: {version_sources}"
        )
    if citation_date is None:
        warnings.append("Versioned characterization citation has no date-released.")

    ci = _read_text(root, ".github/workflows/ci.yml")
    required_ci_tokens = [
        "permissions:\n  contents: read",
        "pytest -q",
        "python -m build",
        "mca --version",
        "dist/*.whl",
    ]
    missing_ci_tokens = [token for token in required_ci_tokens if token not in ci]
    if missing_ci_tokens:
        blockers.append(
            f"Characterization CI lacks release checks: {missing_ci_tokens}"
        )

    status = (
        "blocked_package_release_metadata_inconsistent"
        if blockers
        else "ready_for_external_tag_or_release_verification"
    )
    warnings.append(
        "The offline audit cannot verify whether a Git tag, GitHub Release, or "
        "package-index publication exists."
    )
    return {
        "repository": "materials-characterization-analyzer",
        "release_mode": "python_source_and_wheel_distribution",
        "status": status,
        "package_version": package_version,
        "runtime_version": runtime_version,
        "citation_version": citation_version,
        "citation_date_released": citation_date,
        "latest_changelog_version": latest_changelog_version,
        "version_sources": version_sources,
        "required_files_present": present,
        "required_files_missing": missing,
        "blockers": blockers,
        "warnings": warnings,
        "verified_contracts": {
            "read_only_ci_permissions": required_ci_tokens[0] in ci,
            "tests_present": required_ci_tokens[1] in ci,
            "wheel_and_sdist_build_present": required_ci_tokens[2] in ci,
            "installed_wheel_cli_smoke_test_present": required_ci_tokens[3] in ci,
            "distribution_artifact_check_present": required_ci_tokens[4] in ci,
        },
    }


def build_summary(
    data_root: Path,
    characterization_root: Path,
    characterization_commit: str | None,
) -> dict[str, Any]:
    data = audit_data_repository(data_root)
    characterization = audit_characterization_repository(characterization_root)
    compatibility_files = [
        data_root / ".github/workflows/cross-repository-nist-ambench-2018-02.yml",
        data_root / "docs/NIST_AMBENCH_CROSS_REPOSITORY_HANDOFF.md",
        characterization_root
        / "scripts/export_nist_ambench_2018_02_optical_metrology_bundle.py",
    ]
    missing_compatibility = [
        str(path) for path in compatibility_files if not path.is_file()
    ]
    blockers: list[str] = []
    if data["blockers"]:
        blockers.append("Data repository release metadata is inconsistent.")
    if characterization["blockers"]:
        blockers.append("Characterization package release metadata is inconsistent.")
    if missing_compatibility:
        blockers.append(
            "Tracked cross-repository compatibility evidence is incomplete."
        )

    if blockers:
        overall = "blocked_for_coordinated_release"
    elif data["main_contains_post_release_work"]:
        overall = "coordinated_release_requires_data_version_closeout"
    else:
        overall = "ready_for_external_release_action"

    next_action = (
        "Resolve release metadata blockers and rerun the audit."
        if blockers
        else (
            "Select the next materials-data-analyzer public version, move the "
            "applicable Unreleased entries into release notes, update all version "
            "sources together, and rerun this audit."
            if data["main_contains_post_release_work"]
            else "Verify or create reviewed external tags/releases without changing scientific claim boundaries."
        )
    )

    return {
        "schema_version": "1.0",
        "workflow": "cross_repository_public_release_readiness_audit",
        "status": "completed",
        "evidence_level": "Software validation",
        "network_access_performed": False,
        "tags_created": False,
        "releases_created": False,
        "packages_published": False,
        "characterization_commit_audited": characterization_commit,
        "repositories": {
            "materials_data_analyzer": data,
            "materials_characterization_analyzer": characterization,
        },
        "cross_repository": {
            "status": overall,
            "tracked_compatibility_evidence_present": not missing_compatibility,
            "missing_compatibility_evidence": missing_compatibility,
            "blockers": blockers,
            "next_required_action": next_action,
        },
        "scientific_boundary": {
            "scientific_results_recomputed": False,
            "models_trained": False,
            "optimization_performed": False,
            "release_readiness_implies_scientific_validity": False,
        },
    }


def build_report(summary: dict[str, Any]) -> str:
    data = summary["repositories"]["materials_data_analyzer"]
    char = summary["repositories"]["materials_characterization_analyzer"]
    cross = summary["cross_repository"]
    data_blockers = "\n".join(f"- {item}" for item in data["blockers"]) or "- None"
    char_blockers = "\n".join(f"- {item}" for item in char["blockers"]) or "- None"
    cross_blockers = "\n".join(f"- {item}" for item in cross["blockers"]) or "- None"
    return f"""# Cross-Repository Public Release Readiness

## Decision

**{cross['status']}**

This is a software-release audit. It does not promote any scientific result,
model, mechanism, optimization, or engineering decision.

## materials-data-analyzer

- Status: `{data['status']}`
- Stable public release: `{data['public_release_version']}`
- Runtime platform version: `{data['runtime_platform_version']}`
- Citation version: `{data['citation_version']}`
- Highest version named in Unreleased: `{data['highest_unreleased_named_version']}`
- Current `main` tagging allowed: `{data['current_main_tagging_allowed']}`

### Blocking items

{data_blockers}

## materials-characterization-analyzer

- Status: `{char['status']}`
- Package version: `{char['package_version']}`
- Runtime version: `{char['runtime_version']}`
- Citation version: `{char['citation_version']}`
- Latest changelog release: `{char['latest_changelog_version']}`
- Audited commit: `{summary['characterization_commit_audited']}`

### Blocking items

{char_blockers}

## Cross-repository

- Compatibility evidence present: `{cross['tracked_compatibility_evidence_present']}`
- Tags created: `{summary['tags_created']}`
- Releases created: `{summary['releases_created']}`
- Packages published: `{summary['packages_published']}`

### Blocking items

{cross_blockers}

### Next required action

{cross['next_required_action']}

## Scientific boundary

Release metadata consistency and successful software tests do not establish
sample comparability, mechanism validity, causal identification, predictive
generalization, optimization readiness, or engineering-release suitability.
"""


def _prepare_output_dir(output_dir: Path) -> None:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(
            "Release-readiness output directory must be new or empty; existing "
            f"files were preserved: {output_dir}"
        )
    output_dir.mkdir(parents=True, exist_ok=True)


def run_audit(
    data_root: Path,
    characterization_root: Path,
    output_dir: Path,
    characterization_commit: str | None,
) -> dict[str, Path]:
    _prepare_output_dir(output_dir)
    summary = build_summary(data_root, characterization_root, characterization_commit)
    summary_path = output_dir / SUMMARY_FILE
    report_path = output_dir / REPORT_FILE
    manifest_path = output_dir / MANIFEST_FILE

    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    report_path.write_text(build_report(summary), encoding="utf-8")
    outputs = {"summary": summary_path, "report": report_path}
    manifest = {
        "schema_version": "1.0",
        "generation_status": "completed",
        "outputs": {name: path.name for name, path in outputs.items()},
        "output_sha256": {name: sha256_file(path) for name, path in outputs.items()},
        "network_access_performed": False,
        "tags_created": False,
        "releases_created": False,
        "packages_published": False,
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {**outputs, "manifest": manifest_path}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit cross-repository public-release readiness offline."
    )
    parser.add_argument("--data-repo-root", required=True, type=Path)
    parser.add_argument("--characterization-repo-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--characterization-commit")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    outputs = run_audit(
        args.data_repo_root,
        args.characterization_repo_root,
        args.output,
        args.characterization_commit,
    )
    print(f"Release-readiness summary: {outputs['summary']}")
    print(f"Release-readiness report: {outputs['report']}")
    print(f"Release-readiness manifest: {outputs['manifest']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
