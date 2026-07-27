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


def _data_repo(root: Path, *, document_stage_separation: bool = True) -> None:
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
    _write(root, "PUBLIC_RELEASE_VERSION", "2.4.0\n")
    _write(root, "src/platform_core/version.py", 'PLATFORM_VERSION = "2.4.0"\n')
    _write(
        root,
        "CITATION.cff",
        "cff-version: 1.2.0\ntype: software\ntitle: Materials Data Analyzer\n"
        "version: 2.4.0\nlicense: MIT\n",
    )
    _write(
        root,
        "CHANGELOG.md",
        "# Changelog\n\n## Unreleased\n\n- Added v2.6.2 development work.\n\n"
        "## v2.4.0\n\n- Stable release.\n",
    )
    status = "The stable public release is **v2.4.0**.\n"
    if document_stage_separation:
        status += (
            "Higher labels are development-stage identifiers and are not automatically "
            "promoted. Cite the exact commit SHA for main.\n"
        )
    _write(root, "docs/PUBLIC_RELEASE_STATUS.md", status)
    _write(root, "docs/releases/V2_4_0.md", "# v2.4.0 - Stable Release\n")
    _write(
        root,
        ".github/workflows/ci.yml",
        "permissions:\n  contents: read\nsteps:\n  - run: python -m pytest -q\n",
    )


def _characterization_repo(root: Path, *, runtime_version: str = "0.8.6") -> None:
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
        "[project]\nname = \"materials-characterization-analyzer\"\n"
        "version = \"0.8.6\"\n",
    )
    _write(root, "src/mca/__init__.py", f'__version__ = "{runtime_version}"\n')
    _write(
        root,
        "CITATION.cff",
        "cff-version: 1.2.0\ntype: software\ntitle: Characterization\n"
        "version: 0.8.6\ndate-released: 2026-07-27\n",
    )
    _write(
        root,
        "CHANGELOG.md",
        "# Changelog\n\n## [Unreleased]\n\nNone.\n\n"
        "## [0.8.6] - 2026-07-27\n",
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


def test_release_policy_allows_higher_unreleased_stage_labels(tmp_path: Path) -> None:
    module = _module()
    data = tmp_path / "data"
    char = tmp_path / "char"
    _data_repo(data)
    _characterization_repo(char)

    summary = module.build_summary(data, char, "7242594")

    data_result = summary["repositories"]["materials_data_analyzer"]
    char_result = summary["repositories"]["materials_characterization_analyzer"]
    assert data_result["status"] == (
        "ready_for_existing_release_metadata_pending_external_tag_verification"
    )
    assert data_result["public_release_version"] == "2.4.0"
    assert data_result["platform_version"] == "2.4.0"
    assert data_result["citation_version"] == "2.4.0"
    assert data_result["higher_development_stage_labels"] == ["2.6.2"]
    assert data_result["development_stage_separation_documented"] is True
    assert data_result["blockers"] == []
    assert char_result["status"] == "ready_for_tag_creation_pending_external_release_action"
    assert set(char_result["version_sources"].values()) == {"0.8.6"}
    assert summary["cross_repository"]["status"] == (
        "ready_for_coordinated_external_release_verification"
    )


def test_higher_stage_labels_without_release_policy_block(tmp_path: Path) -> None:
    module = _module()
    data = tmp_path / "data"
    _data_repo(data, document_stage_separation=False)

    result = module.audit_data_repository(data)

    assert result["status"] == "blocked_for_versioned_repository_release"
    assert any("higher version-like labels" in item for item in result["blockers"])


def test_characterization_version_mismatch_blocks(tmp_path: Path) -> None:
    module = _module()
    char = tmp_path / "char"
    _characterization_repo(char, runtime_version="0.8.5")

    result = module.audit_characterization_repository(char)

    assert result["status"] == "blocked_for_versioned_package_release"
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
    assert summary["tags_created"] is False
    assert summary["scientific_boundary"]["models_trained"] is False
    for name, filename in manifest["outputs"].items():
        assert manifest["output_sha256"][name] == module.sha256_file(output / filename)

    sentinel = output / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")
    with pytest.raises(FileExistsError, match="existing files were preserved"):
        module.run_audit(data, char, output, "7242594")
    assert sentinel.read_text(encoding="utf-8") == "keep"
