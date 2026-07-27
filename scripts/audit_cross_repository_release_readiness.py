"""Audit release metadata for the two public materials repositories.

The audit is offline and does not create tags, releases, package uploads, or
scientific results.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import tomllib
from pathlib import Path
from typing import Any

SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
VERSION_TOKEN = re.compile(r"(?<![0-9])v?(\d+\.\d+\.\d+)(?![0-9])")
PLATFORM_VERSION = re.compile(
    r'^PLATFORM_VERSION\s*=\s*["\'](\d+\.\d+\.\d+)["\']', re.MULTILINE
)
RUNTIME_VERSION = re.compile(
    r'^__version__\s*=\s*["\'](\d+\.\d+\.\d+)["\']', re.MULTILINE
)
CHANGELOG_RELEASE = re.compile(
    r"^##\s+(?:\[)?(\d+\.\d+\.\d+)(?:\])?(?:\s|$)", re.MULTILINE
)
NO_UNRELEASED_WORK = re.compile(
    r"^No unreleased changes(?: at the v\d+\.\d+\.\d+ promotion boundary)?\.$"
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
    if not SEMVER.fullmatch(value):
        raise ValueError(f"Invalid semantic version: {value}")
    return tuple(int(part) for part in value.split("."))  # type: ignore[return-value]


def read_text(root: Path, relative: str) -> str:
    path = root / relative
    if not path.is_file():
        raise FileNotFoundError(f"Required tracked file not found: {path}")
    return path.read_text(encoding="utf-8")


def missing_files(root: Path, required: tuple[str, ...]) -> list[str]:
    return [relative for relative in required if not (root / relative).is_file()]


def cff_value(text: str, key: str) -> str | None:
    match = re.search(
        rf"^{re.escape(key)}:\s*[\"']?([^\n\"']+)", text, re.MULTILINE
    )
    return match.group(1).strip() if match else None


def unreleased_text(changelog: str) -> str:
    match = re.search(r"^##\s+\[?Unreleased\]?\s*$", changelog, re.MULTILINE)
    if not match:
        return ""
    remainder = changelog[match.end() :]
    next_heading = re.search(r"^##\s+", remainder, re.MULTILINE)
    return remainder[: next_heading.start()] if next_heading else remainder


def unreleased_contains_work(changelog: str) -> bool:
    body = unreleased_text(changelog).strip()
    return bool(body and not NO_UNRELEASED_WORK.fullmatch(body))


def highest_version(text: str) -> str | None:
    body = text.strip()
    if not body or NO_UNRELEASED_WORK.fullmatch(body):
        return None
    versions = {match.group(1) for match in VERSION_TOKEN.finditer(body)}
    return max(versions, key=parse_version) if versions else None


def audit_data_repository(root: Path) -> dict[str, Any]:
    root = root.resolve()
    required = (
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
    )
    missing = missing_files(root, required)
    blockers = [f"Missing required public files: {missing}"] if missing else []
    warnings: list[str] = []

    public_version = read_text(root, "PUBLIC_RELEASE_VERSION").strip()
    parse_version(public_version)
    runtime_match = PLATFORM_VERSION.search(
        read_text(root, "src/platform_core/version.py")
    )
    if not runtime_match:
        raise ValueError("Unable to parse PLATFORM_VERSION.")
    runtime_version = runtime_match.group(1)

    citation = read_text(root, "CITATION.cff")
    citation_version = cff_value(citation, "version")
    citation_date = cff_value(citation, "date-released")
    changelog = read_text(root, "CHANGELOG.md")
    unreleased = unreleased_text(changelog)
    highest_unreleased = highest_version(unreleased)
    main_ahead = unreleased_contains_work(changelog)
    release_notes = f"docs/releases/V{public_version.replace('.', '_')}.md"

    if runtime_version != public_version:
        blockers.append(
            f"PLATFORM_VERSION {runtime_version} != public version {public_version}."
        )
    if citation_version != public_version:
        blockers.append(
            f"CITATION.cff version {citation_version!r} != public version {public_version}."
        )
    if f"## v{public_version}" not in changelog:
        blockers.append(f"CHANGELOG.md lacks release heading v{public_version}.")
    if not (root / release_notes).is_file():
        blockers.append(f"Missing release notes: {release_notes}")
    elif not read_text(root, release_notes).startswith(f"# v{public_version} -"):
        blockers.append(f"Release notes do not identify v{public_version}.")

    status_doc = read_text(root, "docs/PUBLIC_RELEASE_STATUS.md")
    if f"stable public release is **v{public_version}**" not in status_doc:
        blockers.append("Public release status does not match the version source.")
    if "exact commit SHA" not in status_doc and "exact Git commit SHA" not in status_doc:
        blockers.append("Public release status lacks commit-level citation guidance.")

    ci = read_text(root, ".github/workflows/ci.yml")
    if "permissions:\n  contents: read" not in ci:
        blockers.append("CI lacks read-only contents permission.")
    if "python -m pytest -q" not in ci:
        blockers.append("CI does not run the complete pytest suite.")

    if citation_date is None:
        warnings.append(
            "CITATION.cff has no date-released; add one at the next formal release."
        )
    if highest_unreleased and parse_version(highest_unreleased) > parse_version(
        public_version
    ):
        warnings.append(
            f"main contains work through {highest_unreleased}; do not tag current "
            f"HEAD as v{public_version}."
        )

    status = (
        "blocked_release_metadata_inconsistent"
        if blockers
        else "stable_release_metadata_valid_main_ahead"
        if main_ahead
        else "ready_for_current_head_release_action"
    )
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
        "missing_required_files": missing,
        "blockers": blockers,
        "warnings": warnings,
    }


def audit_characterization_repository(root: Path) -> dict[str, Any]:
    root = root.resolve()
    required = (
        "README.md",
        "LICENSE",
        "SECURITY.md",
        "CONTRIBUTING.md",
        "CHANGELOG.md",
        "CITATION.cff",
        "pyproject.toml",
        ".github/workflows/ci.yml",
        "src/mca/__init__.py",
    )
    missing = missing_files(root, required)
    blockers = [f"Missing required public files: {missing}"] if missing else []
    warnings: list[str] = []

    project = tomllib.loads(read_text(root, "pyproject.toml")).get("project")
    if not isinstance(project, dict) or not isinstance(project.get("version"), str):
        raise ValueError("Unable to parse [project].version.")
    package_version = project["version"]
    runtime_match = RUNTIME_VERSION.search(read_text(root, "src/mca/__init__.py"))
    if not runtime_match:
        raise ValueError("Unable to parse mca.__version__.")
    runtime_version = runtime_match.group(1)
    citation = read_text(root, "CITATION.cff")
    citation_version = cff_value(citation, "version")
    citation_date = cff_value(citation, "date-released")
    releases = CHANGELOG_RELEASE.findall(read_text(root, "CHANGELOG.md"))
    latest_release = releases[0] if releases else None
    sources = {
        "pyproject": package_version,
        "runtime": runtime_version,
        "citation": citation_version,
        "changelog_latest_release": latest_release,
    }
    if None in sources.values() or len(set(sources.values())) != 1:
        blockers.append(f"Characterization versions are inconsistent: {sources}")
    if citation_date is None:
        warnings.append("Characterization citation has no date-released.")

    ci = read_text(root, ".github/workflows/ci.yml")
    tokens = (
        "permissions:\n  contents: read",
        "pytest -q",
        "python -m build",
        "mca --version",
        "dist/*.whl",
    )
    absent = [token for token in tokens if token not in ci]
    if absent:
        blockers.append(f"Characterization CI lacks release checks: {absent}")
    warnings.append(
        "Offline audit cannot verify tags, GitHub Releases, or package-index uploads."
    )
    return {
        "repository": "materials-characterization-analyzer",
        "release_mode": "python_source_and_wheel_distribution",
        "status": (
            "blocked_package_release_metadata_inconsistent"
            if blockers
            else "ready_for_external_tag_or_release_verification"
        ),
        "package_version": package_version,
        "runtime_version": runtime_version,
        "citation_version": citation_version,
        "citation_date_released": citation_date,
        "latest_changelog_version": latest_release,
        "version_sources": sources,
        "missing_required_files": missing,
        "blockers": blockers,
        "warnings": warnings,
    }


def build_summary(
    data_root: Path,
    characterization_root: Path,
    characterization_commit: str | None,
) -> dict[str, Any]:
    data = audit_data_repository(data_root)
    characterization = audit_characterization_repository(characterization_root)
    compatibility = (
        data_root / ".github/workflows/cross-repository-nist-ambench-2018-02.yml",
        data_root / "docs/NIST_AMBENCH_CROSS_REPOSITORY_HANDOFF.md",
        characterization_root
        / "scripts/export_nist_ambench_2018_02_optical_metrology_bundle.py",
    )
    missing_compatibility = [str(path) for path in compatibility if not path.is_file()]
    blockers = []
    if data["blockers"]:
        blockers.append("Data repository release metadata is inconsistent.")
    if characterization["blockers"]:
        blockers.append("Characterization release metadata is inconsistent.")
    if missing_compatibility:
        blockers.append("Cross-repository compatibility evidence is incomplete.")

    if blockers:
        overall = "blocked_for_coordinated_release"
        next_action = "Resolve release metadata blockers and rerun the audit."
    elif data["main_contains_post_release_work"]:
        overall = "coordinated_release_requires_data_version_closeout"
        next_action = (
            "Select the next data-repository public version, close the intended "
            "Unreleased scope, update all version sources, and rerun the audit."
        )
    else:
        overall = "ready_for_external_release_action"
        next_action = "Verify or create reviewed external tags and releases."

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
    return f"""# Cross-Repository Public Release Readiness

## Decision

**{cross['status']}**

## materials-data-analyzer

- Status: `{data['status']}`
- Stable public release: `{data['public_release_version']}`
- Runtime platform version: `{data['runtime_platform_version']}`
- Citation version: `{data['citation_version']}`
- Highest version named in Unreleased: `{data['highest_unreleased_named_version']}`
- Current `main` tagging allowed: `{data['current_main_tagging_allowed']}`
- Blockers: `{data['blockers']}`

## materials-characterization-analyzer

- Status: `{char['status']}`
- Version sources: `{char['version_sources']}`
- Audited commit: `{summary['characterization_commit_audited']}`
- Blockers: `{char['blockers']}`

## Next required action

{cross['next_required_action']}

## Scientific boundary

This is a software-release audit. It does not establish sample comparability,
causal identification, mechanism validity, predictive generalization,
optimization readiness, or engineering-release suitability.
"""


def prepare_output(output_dir: Path) -> None:
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
    prepare_output(output_dir)
    summary = build_summary(data_root, characterization_root, characterization_commit)
    summary_path = output_dir / SUMMARY_FILE
    report_path = output_dir / REPORT_FILE
    manifest_path = output_dir / MANIFEST_FILE
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    report_path.write_text(build_report(summary), encoding="utf-8")
    outputs = {"summary": summary_path, "report": report_path}
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "generation_status": "completed",
                "outputs": {name: path.name for name, path in outputs.items()},
                "output_sha256": {
                    name: sha256_file(path) for name, path in outputs.items()
                },
                "network_access_performed": False,
                "tags_created": False,
                "releases_created": False,
                "packages_published": False,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
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
    for name, path in outputs.items():
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
