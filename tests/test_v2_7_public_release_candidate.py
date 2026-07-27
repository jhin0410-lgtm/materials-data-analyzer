from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "audit_v2_7_public_release_candidate.py"
OLD_V2_6_PATHS = (
    "configs/v2_6_public_release_candidate.json",
    "scripts/audit_v2_6_public_release_candidate.py",
    "docs/V2_6_PUBLIC_RELEASE_CANDIDATE.md",
    "tests/test_v2_6_public_release_candidate.py",
    ".github/workflows/v2-6-public-release-candidate.yml",
)


def _module():
    spec = importlib.util.spec_from_file_location("v2_7_release_promotion", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_tracked_v2_7_metadata_promotion_is_complete() -> None:
    module = _module()
    summary = module.build_summary(PROJECT_ROOT)

    assert summary["status"] == "completed"
    assert summary["decision"] == (
        "v2_7_0_metadata_promoted_external_release_pending"
    )
    assert summary["candidate_version"] == "2.7.0"
    assert summary["superseded_candidate_version"] == "2.6.0"
    assert summary["post_v2_6_commit_count_at_audit"] == 38
    assert summary["separate_v2_5_or_v2_6_public_release_authorized"] is False
    assert summary["software_validation"]["status"] == "supported"
    assert summary["software_validation"]["v2_6_stage_count"] == 13
    assert all(summary["software_validation"]["checks"].values())
    assert summary["scientific_closeout"]["status"] == "inconclusive"
    assert summary["scientific_closeout"]["ridge_generalization"] == "unsupported"
    assert summary["scientific_closeout"]["predictive_validation_readiness"] == (
        "not_ready"
    )
    assert summary["scientific_closeout"][
        "post_v2_6_process_characterization_status"
    ] == "diagnostic"
    assert summary["public_metadata_promotion_performed"] is True
    assert summary["tag_or_release_created"] is False


def test_promotion_inventory_includes_every_v2_5_and_v2_6_stage() -> None:
    config = json.loads(
        (PROJECT_ROOT / "configs" / "v2_7_public_release_candidate.json").read_text(
            encoding="utf-8"
        )
    )
    expected = ["2.5.1", "2.5.2", *[f"2.6.{index}" for index in range(1, 15)]]

    assert config["included_internal_stage_versions"] == expected
    assert config["candidate_version"] == "2.7.0"
    assert config["promoted_public_version"] == "2.7.0"
    assert config["release_date"] == "2026-07-28"
    assert config["superseded_candidate_version"] == "2.6.0"
    assert config["post_v2_6_commit_count_at_audit"] == 38
    assert config["public_metadata_promotion_performed"] is True
    assert config["tag_or_release_created"] is False


def test_superseded_v2_6_candidate_files_are_removed() -> None:
    for relative in OLD_V2_6_PATHS:
        assert not (PROJECT_ROOT / relative).exists(), relative


def test_promotion_outputs_are_checksummed_and_fail_closed(tmp_path: Path) -> None:
    module = _module()
    output = tmp_path / "promotion"
    paths = module.run(PROJECT_ROOT, output)

    summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    assert summary["candidate_version"] == "2.7.0"
    assert manifest["public_metadata_promotion_performed"] is True
    assert manifest["tag_or_release_created"] is False
    for name, filename in manifest["outputs"].items():
        assert manifest["output_sha256"][name] == module.sha256_file(
            output / filename
        )

    sentinel = output / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")
    with pytest.raises(FileExistsError, match="existing files preserved"):
        module.run(PROJECT_ROOT, output)
    assert sentinel.read_text(encoding="utf-8") == "keep"


def test_release_documents_preserve_complete_scope_and_claim_boundaries() -> None:
    candidate = (
        PROJECT_ROOT / "docs" / "V2_7_PUBLIC_RELEASE_CANDIDATE.md"
    ).read_text(encoding="utf-8")
    notes = (
        PROJECT_ROOT / "docs" / "releases" / "V2_7_0.md"
    ).read_text(encoding="utf-8")
    changelog = (PROJECT_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    for version in ["v2.5.1", "v2.5.2", *[f"v2.6.{i}" for i in range(1, 15)]]:
        assert version in candidate
        assert version in notes
    assert "The selected stable public version is **v2.7.0**" in candidate
    assert "metadata has been promoted" in candidate
    assert "Ridge forecast improvement: **Unsupported**" in candidate
    assert "final evidence-line scientific status: **Inconclusive**" in candidate
    assert "remain **Diagnostic**" in candidate
    assert "## v2.7.0" in changelog
    unreleased = changelog.split("## Unreleased", 1)[1].split("## v2.7.0", 1)[0]
    assert "No unreleased changes" in unreleased
    assert "does not establish" in candidate
