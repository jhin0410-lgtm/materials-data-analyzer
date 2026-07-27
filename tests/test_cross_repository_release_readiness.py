from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "audit_cross_repository_release_readiness.py"


def _module():
    spec = importlib.util.spec_from_file_location("release_readiness", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write(root: Path, relative: str, content: str = "tracked\n") -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _data_repo(
    root: Path,
    *,
    public_version: str = "2.7.0",
    runtime_version: str = "2.7.0",
    citation_version: str = "2.7.0",
    unreleased_line: str = "",
) -> None:
    for relative in (
        "README.md",
        "LICENSE",
        "SECURITY.md",
        "CONTRIBUTING.md",
        "requirements.txt",
        "scripts/run_representative_process_characterization_workflow.py",
        "docs/REPRESENTATIVE_PROCESS_CHARACTERIZATION_WORKFLOW.md",
        ".github/workflows/cross-repository-nist-ambench-2018-02.yml",
        "docs/NIST_AMBENCH_CROSS_REPOSITORY_HANDOFF.md",
    ):
        _write(root, relative)
    _write(root, "PUBLIC_RELEASE_VERSION", f"{public_version}\n")
    _write(
        root,
        "src/platform_core/version.py",
        f'PLATFORM_VERSION = "{runtime_version}"\n',
    )
    _write(
        root,
        "CHANGELOG.md",
        "# Changelog\n\n"
        f"## Unreleased\n\n{unreleased_line}\n\n"
        f"## v{public_version}\n",
    )
    _write(
        root,
        "CITATION.cff",
        "cff-version: 1.2.0\n"
        "type: software\n"
        "title: Materials Data Analyzer\n"
        f"version: {citation_version}\n"
        "date-released: 2026-07-28\n"
        "license: MIT\n",
    )
    _write(
        root,
        "docs/PUBLIC_RELEASE_STATUS.md",
        f"The current stable public release is **v{public_version}**.\n"
        "Record the exact Git commit SHA used.\n",
    )
    _write(
        root,
        f"docs/releases/V{public_version.replace('.', '_')}.md",
        f"# v{public_version} - Test Release\n",
    )
    _write(
        root,
        ".github/workflows/ci.yml",
        "permissions:\n  contents: read\nsteps:\n  - run: python -m pytest -q\n",
    )


def _characterization_repo(root: Path, *, version: str = "0.8.6") -> None:
    for relative in (
        "README.md",
        "LICENSE",
        "SECURITY.md",
        "CONTRIBUTING.md",
        "scripts/export_nist_ambench_2018_02_optical_metrology_bundle.py",
    ):
        _write(root, relative)
    _write(
        root,
        "pyproject.toml",
        "[project]\n"
        'name = "materials-characterization-analyzer"\n'
        f'version = "{version}"\n',
    )
    _write(root, "src/mca/__init__.py", f'__version__ = "{version}"\n')
    _write(
        root,
        "CITATION.cff",
        "cff-version: 1.2.0\n"
        "type: software\n"
        "title: Materials Characterization Analyzer\n"
        f"version: {version}\n"
        "date-released: 2026-07-27\n",
    )
    _write(
        root,
        "CHANGELOG.md",
        f"# Changelog\n\n## [Unreleased]\n\nNone.\n\n"
        f"## [{version}] - 2026-07-27\n",
    )
    _write(
        root,
        ".github/workflows/ci.yml",
        "permissions:\n  contents: read\n"
        "steps:\n"
        "  - run: pytest -q\n"
        "  - run: python -m build\n"
        "  - run: mca --version\n"
        "  - run: python check.py dist/*.whl\n",
    )


def test_audit_marks_closed_data_release_ready_for_external_action(
    tmp_path: Path,
) -> None:
    module = _module()
    data = tmp_path / "data"
    char = tmp_path / "char"
    _data_repo(data)
    _characterization_repo(char)

    summary = module.build_summary(data, char, "7242594")
    data_result = summary["repositories"]["materials_data_analyzer"]
    char_result = summary["repositories"]["materials_characterization_analyzer"]

    assert data_result["status"] == "ready_for_current_head_release_action"
    assert data_result["public_release_version"] == "2.7.0"
    assert data_result["runtime_platform_version"] == "2.7.0"
    assert data_result["citation_version"] == "2.7.0"
    assert data_result["highest_unreleased_named_version"] is None
    assert data_result["main_contains_post_release_work"] is False
    assert data_result["stable_release_metadata_valid"] is True
    assert data_result["current_main_tagging_allowed"] is True
    assert data_result["blockers"] == []
    assert char_result["status"] == (
        "ready_for_external_tag_or_release_verification"
    )
    assert set(char_result["version_sources"].values()) == {"0.8.6"}
    assert summary["cross_repository"]["status"] == "ready_for_external_release_action"
    assert summary["tags_created"] is False
    assert summary["packages_published"] is False


def test_audit_separates_stable_release_from_later_main_work(tmp_path: Path) -> None:
    module = _module()
    data = tmp_path / "data"
    char = tmp_path / "char"
    _data_repo(data, unreleased_line="- Added v2.7.1 post-release work.")
    _characterization_repo(char)

    summary = module.build_summary(data, char, "7242594")
    data_result = summary["repositories"]["materials_data_analyzer"]

    assert data_result["status"] == "stable_release_metadata_valid_main_ahead"
    assert data_result["highest_unreleased_named_version"] == "2.7.1"
    assert data_result["current_main_tagging_allowed"] is False
    assert summary["cross_repository"]["status"] == (
        "coordinated_release_requires_data_version_closeout"
    )


def test_data_release_metadata_mismatch_blocks(tmp_path: Path) -> None:
    module = _module()
    data = tmp_path / "data"
    _data_repo(data, citation_version="2.6.0")

    result = module.audit_data_repository(data)

    assert result["status"] == "blocked_release_metadata_inconsistent"
    assert result["stable_release_metadata_valid"] is False
    assert any("CITATION.cff version" in item for item in result["blockers"])


def test_characterization_version_mismatch_blocks(tmp_path: Path) -> None:
    module = _module()
    char = tmp_path / "char"
    _characterization_repo(char)
    _write(char, "src/mca/__init__.py", '__version__ = "0.8.5"\n')

    result = module.audit_characterization_repository(char)

    assert result["status"] == "blocked_package_release_metadata_inconsistent"
    assert any("inconsistent" in item for item in result["blockers"])


def test_run_audit_writes_checksummed_outputs_and_preserves_existing_files(
    tmp_path: Path,
) -> None:
    module = _module()
    data = tmp_path / "data"
    char = tmp_path / "char"
    output = tmp_path / "audit"
    _data_repo(data)
    _characterization_repo(char)

    outputs = module.run_audit(data, char, output, "7242594")
    summary = json.loads(outputs["summary"].read_text(encoding="utf-8"))
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))

    assert summary["network_access_performed"] is False
    assert summary["scientific_boundary"]["models_trained"] is False
    for name, filename in manifest["outputs"].items():
        assert manifest["output_sha256"][name] == module.sha256_file(
            output / filename
        )

    sentinel = output / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")
    with pytest.raises(FileExistsError, match="existing files were preserved"):
        module.run_audit(data, char, output, "7242594")
    assert sentinel.read_text(encoding="utf-8") == "keep"
