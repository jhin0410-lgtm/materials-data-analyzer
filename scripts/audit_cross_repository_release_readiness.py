"""Audit public release metadata across both materials analyzer repositories.

This audit is offline and read-only with respect to release actions. It never
creates tags, GitHub Releases, or package-index uploads, and it does not rerun
scientific analyses.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
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
CHAR_CHANGELOG_RELEASE_RE = re.compile(r"^## \[(\d+\.\d+\.\d+)\]", re.MULTILINE)

SUMMARY_FILE = "cross_repository_release_readiness.json"
REPORT_FILE = "cross_repository_release_readiness.md"
MANIFEST_FILE = "cross_repository_release_readiness_manifest.json"


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def version_tuple(value: str) -> tuple[int, int, int]:
    if not SEMVER_RE.fullmatch(value):
        raise ValueError(f"Invalid semantic version: {value}")
    major, minor, patch = value.split(".")
    return int(major), int(minor), int(patch)


def read_text(root: Path, relative: str) -> str:
    path = root / relative
    if not path.is_file():
        raise FileNotFoundError(f"Required tracked file not found: {path}")
    return path.read_text(encoding="utf-8")


def file_presence(root: Path, required: list[str]) -> tuple[list[str], list[str]]:
    present = [item for item in required if (root / item).is_file()]
    missing = [item for item in required if not (root / item).is_file()]
    return present, missing


def extract_unreleased(changelog: str) -> str:
    for marker in ("## Unreleased", "## [Unreleased]"):
        if marker in changelog:
            remainder = changelog.split(marker, maxsplit=1)[1]
            next_heading = re.search(r"^## ", remainder, re.MULTILINE)
            return remainder[: next_heading.start()] if next_heading else remainder
    return ""


def extract_cff_scalar(text: str, key: str) -> str | None:
    match = re.search(
        rf"^{re.escape(key)}:\s*[\"']?([^\n\"']+)", text, re.MULTILINE
    )
    return match.group(1).strip() if match else None


def audit_data_repository(root: Path) -> dict[str, Any]:
    required = [
        "README.md",
        "LICENSE",
        "SECURITY.md",
        "CONTRIBUTING.md",
        "CHANGELOG.md",
        "CITATION.cff",
        "PUBLIC_RELEASE_VERSION",
        "requirements.txt",
        ".github/workflows/ci.yml",
        "src/platform_core/version.py",
        "docs/PUBLIC_RELEASE_STATUS.md",
        "scripts/run_representative_process_characterization_workflow.py",
        "docs/REPRESENTATIVE_PROCESS_CHARACTERIZATION_WORKFLOW.md",
    ]
    present, missing = file_presence(root, required)
    blockers: list[str] = []
    warnings: list[str] = []
    if missing:
        blockers.append(f"Missing required public-release files: {missing}")

    public_version = read_text(root, "PUBLIC_RELEASE_VERSION").strip()
    version_tuple(public_version)

    platform_text = read_text(root, "src/platform_core/version.py")
    platform_match = PLATFORM_VERSION_RE.search(platform_text)
    if not platform_match:
        raise ValueError("Unable to parse PLATFORM_VERSION.")
    platform_version = platform_match.group(1)

    citation = read_text(root, "CITATION.cff")
    citation_version = extract_cff_scalar(citation, "version")
    citation_date = extract_cff_scalar(citation, "date-released")

    changelog = read_text(root, "CHANGELOG.md")
    release_heading = f"## v{public_version}"
    status_document = read_text(root, "docs/PUBLIC_RELEASE_STATUS.md")
    release_notes_relative = f"docs/releases/V{public_version.replace('.', '_')}.md"
    release_notes_exists = (root / release_notes_relative).is_file()

    if platform_version != public_version:
        blockers.append(
            f"PLATFORM_VERSION {platform_version} does not match public release {public_version}."
        )
    if citation_version != public_version:
        blockers.append(
            f"CITATION.cff version {citation_version} does not match public release {public_version}."
        )
    if citation_date is None:
        warnings.append(
            "CITATION.cff has no date-released field; the current repository policy does not "
            "treat this optional field as a release blocker."
        )
    if release_heading not in changelog:
        blockers.append(f"CHANGELOG.md lacks the stable release heading {release_heading}.")
    if not release_notes_exists:
        blockers.append(f"Release notes are missing: {release_notes_relative}")
    if f"stable public release is **v{public_version}**" not in status_document:
        blockers.append("PUBLIC_RELEASE_STATUS.md does not declare the canonical public version.")

    unreleased = extract_unreleased(changelog)
    stage_versions = sorted(
        {match.group(1) for match in VERSION_TOKEN_RE.finditer(unreleased)},
        key=version_tuple,
    )
    higher_stage_versions = [
        value for value in stage_versions if version_tuple(value) > version_tuple(public_version)
    ]
    stage_separation_documented = (
        "development-stage identifiers" in status_document
        and "not automatically promoted" in status_document
        and "exact commit SHA" in status_document
    )
    if higher_stage_versions and not stage_separation_documented:
        blockers.append(
            "Unreleased contains higher version-like labels without an explicit policy "
            "separating development stages from the stable public release."
        )
    elif higher_stage_versions:
        warnings.append(
            "Unreleased contains development-stage labels above the stable public version; "
            "the tracked release policy explicitly prevents automatic promotion."
        )

    ci = read_text(root, ".github/workflows/ci.yml")
    if "permissions:\n  contents: read" not in ci:
        blockers.append("CI does not declare read-only contents permission.")
    if "python -m pytest -q" not in ci:
        blockers.append("CI does not run the complete pytest suite.")
    warnings.append(
        "The data repository is released as a versioned workflow/source repository; "
        "wheel and sdist publication are not part of its current public contract."
    )

    status = (
        "ready_for_existing_release_metadata_pending_external_tag_verification"
        if not blockers
        else "blocked_for_versioned_repository_release"
    )
    return {
        "repository": "materials-data-analyzer",
        "release_mode": "versioned_repository_workflow",
        "status": status,
        "public_release_version": public_version,
        "platform_version": platform_version,
        "citation_version": citation_version,
        "citation_date_released": citation_date,
        "release_notes": release_notes_relative,
        "release_notes_present": release_notes_exists,
        "unreleased_version_like_stage_labels": stage_versions,
        "higher_development_stage_labels": higher_stage_versions,
        "development_stage_separation_documented": stage_separation_documented,
        "required_files_present": present,
        "required_files_missing": missing,
        "blockers": blockers,
        "warnings": warnings,
        "verified_contracts": {
            "stable_release_heading_present": release_heading in changelog,
            "release_status_document_matches": (
                f"stable public release is **v{public_version}**" in status_document
            ),
            "read_only_ci_permissions": "permissions:\n  contents: read" in ci,
            "full_test_command_present": "python -m pytest -q" in ci,
            "representative_workflow_documented": True,
            "package_distribution_required": False,
        },
    }


def audit_characterization_repository(root: Path) -> dict[str, Any]:
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
    present, missing = file_presence(root, required)
    blockers: list[str] = []
    warnings: list[str] = []
    if missing:
        blockers.append(f"Missing required public-release files: {missing}")

    project = tomllib.loads(read_text(root, "pyproject.toml")).get("project")
    if not isinstance(project, dict) or not isinstance(project.get("version"), str):
        raise ValueError("Unable to parse characterization [project].version.")
    package_version = project["version"]
    version_tuple(package_version)

    runtime_match = RUNTIME_VERSION_RE.search(read_text(root, "src/mca/__init__.py"))
    if not runtime_match:
        raise ValueError("Unable to parse characterization runtime __version__.")
    runtime_version = runtime_match.group(1)

    citation = read_text(root, "CITATION.cff")
    citation_version = extract_cff_scalar(citation, "version")
    citation_date = extract_cff_scalar(citation, "date-released")
    releases = CHAR_CHANGELOG_RELEASE_RE.findall(read_text(root, "CHANGELOG.md"))
    latest_changelog_version = releases[0] if releases else None

    version_sources = {
        "pyproject": package_version,
        "runtime": runtime_version,
        "citation": citation_version,
        "changelog_latest_release": latest_changelog_version,
    }
    if None in version_sources.values() or len(set(version_sources.values())) != 1:
        blockers.append(f"Characterization version sources are inconsistent: {version_sources}")
    if citation_version and citation_date is None:
        blockers.append("Versioned characterization citation is missing date-released.")

    ci = read_text(root, ".github/workflows/ci.yml")
    required_ci_tokens = [
        "permissions:\n  contents: read",
        "pytest -q",
        "python -m build",
        "mca --version",
        "dist/*.whl",
    ]
    missing_ci_tokens = [token for token in required_ci_tokens if token not in ci]
    if missing_ci_tokens:
        blockers.append(f"Characterization CI lacks release checks: {missing_ci_tokens}")

    warnings.append(
        "The offline audit does not verify whether a Git tag, GitHub Release, or "
        "package-index upload exists."
    )
    return {
        "repository": "materials-characterization-analyzer",
        "release_mode": "python_source_and_wheel_distribution",
        "status": (
            "ready_for_tag_creation_pending_external_release_action"
            if not blockers
            else "blocked_for_versioned_package_release"
        ),
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
    missing_compatibility = [str(path) for path in compatibility_files if not path.is_file()]
    blockers: list[str] = []
    if missing_compatibility:
        blockers.append(
            f"Missing tracked cross-repository compatibility evidence: {missing_compatibility}"
        )
    if data["blockers"]:
        blockers.append("The data repository release metadata is not internally consistent.")
    if characterization["blockers"]:
        blockers.append("The characterization package metadata is not internally consistent.")

    overall = (
        "ready_for_coordinated_external_release_verification"
        if not blockers
        else "blocked_for_coordinated_release"
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
            "next_required_action": (
                "Verify the intended Git tags and GitHub Releases externally, then create or "
                "publish only through an explicit reviewed release action."
                if not blockers
                else "Resolve the listed metadata or compatibility blockers and rerun the audit."
            ),
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

This is a software-release metadata audit. It does not promote scientific claims.

## materials-data-analyzer

- Status: `{data['status']}`
- Stable public version: `{data['public_release_version']}`
- Platform version: `{data['platform_version']}`
- Citation version: `{data['citation_version']}`
- Higher Unreleased development-stage labels: `{data['higher_development_stage_labels']}`
- Development-stage separation documented: `{data['development_stage_separation_documented']}`

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

## Coordinated Release

### Blocking items

{cross_blockers}

### Required next action

{cross['next_required_action']}

## Boundary

- No tag or GitHub Release was created.
- No wheel or source distribution was published.
- No scientific analysis was rerun.
- Release metadata consistency does not establish scientific validity.
"""


def run_audit(
    data_repo_root: str | Path,
    characterization_repo_root: str | Path,
    output_dir: str | Path,
    characterization_commit: str | None = None,
) -> dict[str, Path]:
    data_root = Path(data_repo_root).resolve()
    characterization_root = Path(characterization_repo_root).resolve()
    output = Path(output_dir)
    if not data_root.is_dir():
        raise FileNotFoundError(f"Data repository root not found: {data_root}")
    if not characterization_root.is_dir():
        raise FileNotFoundError(
            f"Characterization repository root not found: {characterization_root}"
        )
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(
            f"Output directory is not empty; existing files were preserved: {output}"
        )
    output.mkdir(parents=True, exist_ok=True)

    summary = build_summary(data_root, characterization_root, characterization_commit)
    summary_path = output / SUMMARY_FILE
    report_path = output / REPORT_FILE
    manifest_path = output / MANIFEST_FILE
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    report_path.write_text(build_report(summary), encoding="utf-8")
    outputs = {"summary": summary_path, "report": report_path}
    manifest = {
        "schema_version": "1.0",
        "workflow": summary["workflow"],
        "outputs": {name: path.name for name, path in outputs.items()},
        "output_sha256": {name: sha256_file(path) for name, path in outputs.items()},
        "network_access_performed": False,
        "tags_created": False,
        "releases_created": False,
        "packages_published": False,
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    outputs["manifest"] = manifest_path
    return outputs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-repo-root", default=str(Path(__file__).resolve().parents[1])
    )
    parser.add_argument("--characterization-repo-root", required=True)
    parser.add_argument("--characterization-commit")
    parser.add_argument("--output", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        outputs = run_audit(
            args.data_repo_root,
            args.characterization_repo_root,
            args.output,
            args.characterization_commit,
        )
    except (OSError, ValueError, TypeError, KeyError, tomllib.TOMLDecodeError) as exc:
        print(f"Cross-repository release-readiness audit failed: {exc}", file=sys.stderr)
        return 1
    print("Cross-repository release-readiness audit completed.")
    for name, path in outputs.items():
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
