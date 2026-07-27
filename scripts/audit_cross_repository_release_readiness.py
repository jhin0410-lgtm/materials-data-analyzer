"""Audit public-release readiness across the data and characterization repositories.

The audit is intentionally offline. It inspects tracked repository files only and
never creates tags, publishes packages, contacts package indexes, or changes
version metadata.
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

VERSION_RE = re.compile(r"(?<![0-9])v?(\d+\.\d+\.\d+)(?![0-9])")
PLATFORM_VERSION_RE = re.compile(
    r'^PLATFORM_VERSION\s*=\s*["\'](\d+\.\d+\.\d+)["\']', re.MULTILINE
)
RUNTIME_VERSION_RE = re.compile(
    r'^__version__\s*=\s*["\'](\d+\.\d+\.\d+)["\']', re.MULTILINE
)
CHANGELOG_RELEASE_RE = re.compile(r"^## \[(\d+\.\d+\.\d+)\]", re.MULTILINE)

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
    parts = value.split(".")
    if len(parts) != 3 or any(not part.isdigit() for part in parts):
        raise ValueError(f"Invalid semantic version: {value}")
    return tuple(int(part) for part in parts)  # type: ignore[return-value]


def read_text(root: Path, relative: str) -> str:
    path = root / relative
    if not path.is_file():
        raise FileNotFoundError(f"Required tracked file not found: {path}")
    return path.read_text(encoding="utf-8")


def file_presence(root: Path, required: list[str]) -> tuple[list[str], list[str]]:
    present = [relative for relative in required if (root / relative).is_file()]
    missing = [relative for relative in required if not (root / relative).is_file()]
    return present, missing


def extract_unreleased(changelog: str) -> str:
    marker = "## Unreleased"
    bracket_marker = "## [Unreleased]"
    if marker in changelog:
        start = changelog.index(marker) + len(marker)
    elif bracket_marker in changelog:
        start = changelog.index(bracket_marker) + len(bracket_marker)
    else:
        return ""
    remainder = changelog[start:]
    next_heading = re.search(r"^## ", remainder, re.MULTILINE)
    return remainder[: next_heading.start()] if next_heading else remainder


def extract_cff_scalar(text: str, key: str) -> str | None:
    match = re.search(rf"^{re.escape(key)}:\s*[\"']?([^\n\"']+)", text, re.MULTILINE)
    return match.group(1).strip() if match else None


def audit_data_repository(root: Path) -> dict[str, Any]:
    required = [
        "README.md",
        "LICENSE",
        "SECURITY.md",
        "CONTRIBUTING.md",
        "CHANGELOG.md",
        "CITATION.cff",
        "requirements.txt",
        ".github/workflows/ci.yml",
        "src/platform_core/version.py",
        "scripts/run_representative_process_characterization_workflow.py",
        "docs/REPRESENTATIVE_PROCESS_CHARACTERIZATION_WORKFLOW.md",
    ]
    present, missing = file_presence(root, required)
    blockers: list[str] = []
    warnings: list[str] = []
    if missing:
        blockers.append(f"Missing required public-release files: {missing}")

    version_text = read_text(root, "src/platform_core/version.py")
    version_match = PLATFORM_VERSION_RE.search(version_text)
    if not version_match:
        raise ValueError("Unable to parse PLATFORM_VERSION from data repository.")
    runtime_version = version_match.group(1)

    changelog = read_text(root, "CHANGELOG.md")
    unreleased = extract_unreleased(changelog)
    declared_unreleased_versions = sorted(
        {match.group(1) for match in VERSION_RE.finditer(unreleased)},
        key=parse_version,
    )
    highest_unreleased = declared_unreleased_versions[-1] if declared_unreleased_versions else None
    if highest_unreleased and parse_version(highest_unreleased) > parse_version(runtime_version):
        blockers.append(
            "The Unreleased changelog declares work through "
            f"{highest_unreleased}, but PLATFORM_VERSION remains {runtime_version}."
        )

    citation = read_text(root, "CITATION.cff")
    citation_version = extract_cff_scalar(citation, "version")
    citation_date = extract_cff_scalar(citation, "date-released")
    if citation_version is None:
        blockers.append(
            "CITATION.cff is commit-oriented and intentionally has no release version; "
            "a versioned citation must be added only after the next public version is selected."
        )
    elif citation_version != runtime_version:
        blockers.append(
            f"CITATION.cff version {citation_version} does not match PLATFORM_VERSION {runtime_version}."
        )
    if citation_version and citation_date is None:
        blockers.append("A versioned CITATION.cff must include date-released.")

    ci = read_text(root, ".github/workflows/ci.yml")
    if "permissions:\n  contents: read" not in ci:
        blockers.append("CI does not declare read-only contents permission.")
    if "python -m pytest -q" not in ci:
        blockers.append("CI does not run the complete pytest suite.")
    if "python -m build" not in ci:
        warnings.append(
            "The data repository is a workflow repository rather than a Python distribution; "
            "wheel/sdist construction is not currently part of its release contract."
        )

    status = "blocked_for_versioned_public_release" if blockers else "ready_for_versioned_repository_release"
    return {
        "repository": "materials-data-analyzer",
        "release_mode": "versioned_repository_workflow",
        "status": status,
        "runtime_version": runtime_version,
        "citation_version": citation_version,
        "citation_date_released": citation_date,
        "unreleased_declared_versions": declared_unreleased_versions,
        "highest_unreleased_declared_version": highest_unreleased,
        "required_files_present": present,
        "required_files_missing": missing,
        "blockers": blockers,
        "warnings": warnings,
        "verified_contracts": {
            "representative_workflow_documented": True,
            "read_only_ci_permissions": "permissions:\n  contents: read" in ci,
            "full_test_command_present": "python -m pytest -q" in ci,
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

    pyproject = tomllib.loads(read_text(root, "pyproject.toml"))
    project = pyproject.get("project")
    if not isinstance(project, dict) or not isinstance(project.get("version"), str):
        raise ValueError("Unable to parse [project].version from characterization pyproject.toml.")
    package_version = project["version"]

    runtime_text = read_text(root, "src/mca/__init__.py")
    runtime_match = RUNTIME_VERSION_RE.search(runtime_text)
    if not runtime_match:
        raise ValueError("Unable to parse __version__ from characterization package.")
    runtime_version = runtime_match.group(1)

    citation = read_text(root, "CITATION.cff")
    citation_version = extract_cff_scalar(citation, "version")
    citation_date = extract_cff_scalar(citation, "date-released")
    changelog = read_text(root, "CHANGELOG.md")
    releases = CHANGELOG_RELEASE_RE.findall(changelog)
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

    status = (
        "ready_for_tag_creation_pending_external_release_action"
        if not blockers
        else "blocked_for_versioned_package_release"
    )
    warnings.append(
        "The offline audit does not verify whether a Git tag, GitHub Release, or package-index upload exists."
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
    cross_repo_files = [
        data_root / ".github/workflows/cross-repository-nist-ambench-2018-02.yml",
        data_root / "docs/NIST_AMBENCH_CROSS_REPOSITORY_HANDOFF.md",
        characterization_root
        / "scripts/export_nist_ambench_2018_02_optical_metrology_bundle.py",
    ]
    missing_cross_repo = [str(path) for path in cross_repo_files if not path.is_file()]
    cross_repo_blockers = []
    if missing_cross_repo:
        cross_repo_blockers.append(
            f"Missing tracked cross-repository compatibility evidence: {missing_cross_repo}"
        )
    if data["blockers"]:
        cross_repo_blockers.append(
            "The data repository cannot be represented by an unambiguous versioned release."
        )
    if characterization["blockers"]:
        cross_repo_blockers.append(
            "The characterization repository cannot be represented by a consistent package release."
        )

    overall = (
        "partial_release_readiness_data_repository_blocked"
        if data["blockers"] and not characterization["blockers"]
        else "ready_for_coordinated_release_action"
        if not cross_repo_blockers
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
            "tracked_compatibility_evidence_present": not missing_cross_repo,
            "missing_compatibility_evidence": missing_cross_repo,
            "blockers": cross_repo_blockers,
            "next_required_action": (
                "Select and document the next materials-data-analyzer public version, "
                "align PLATFORM_VERSION, CHANGELOG, and CITATION.cff, then rerun this audit."
                if data["blockers"]
                else "Create reviewed tags/releases without changing scientific claim boundaries."
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

This is a software-release audit. It does not promote any scientific result,
model, mechanism, optimization, or engineering decision.

## materials-data-analyzer

- Status: `{data['status']}`
- Runtime platform version: `{data['runtime_version']}`
- Highest version named in Unreleased: `{data['highest_unreleased_declared_version']}`
- Citation version: `{data['citation_version']}`
- Release mode: `{data['release_mode']}`

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
- Passing this audit would establish release-metadata consistency only, not scientific validity.
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
        "--data-repo-root",
        default=str(Path(__file__).resolve().parents[1]),
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
