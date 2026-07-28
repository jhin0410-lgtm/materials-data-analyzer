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
    spec = importlib.util.spec_from_file_location("v2_7_release_candidate", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_tracked_v2_7_promotion_preserves_the_release_boundary() -> None:
    module = _module()
    summary = module.build_summary(PROJECT_ROOT)

    assert summary["status"] == "completed"
    assert summary["decision"] == (
        "v2_7_0_metadata_promoted_pending_external_release_action"
    )
    assert summary["candidate_version"] == "2.7.0"
    assert summary["superseded_candidate_version"] == "2.6.0"
    assert summary["release_date"] == "2026-07-28"
    assert summary["post_v2_6_feature_scope_commit_count_at_audit"] == 38
    assert summary["post_v2_6_commit_count_at_audit"] == 41
    assert summary["audited_main_commit"] == (
        "2d003aecede89aacc25cdb246bf9cc6adec19bf9"
    )
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
    assert config["superseded_candidate_version"] == "2.6.0"
    assert config["post_v2_6_feature_scope_commit_count_at_audit"] == 38
    assert config["post_v2_6_commit_count_at_audit"] == 41
    assert config["audited_main_commit"] == (
        "2d003aecede89aacc25cdb246bf9cc6adec19bf9"
    )
    assert len(config["feature_scope_audited_commit"]) == 40
    assert len(config["v2_6_core_closeout_commit"]) == 40
    assert config["public_metadata_promotion_performed"] is True
    assert config["tag_or_release_created"] is False


def test_version_inventory_uses_complete_tokens() -> None:
    module = _module()

    assert module.release_notes_contains_version("stage 2.6.1 complete", "2.6.1")
    assert not module.release_notes_contains_version("stage 2.6.10 complete", "2.6.1")
    assert not module.release_notes_contains_version("stage 12.6.1 complete", "2.6.1")


def test_unreleased_heading_is_required() -> None:
    module = _module()

    with pytest.raises(ValueError, match="missing the required"):
        module.unreleased_text("## v2.7.0\n")


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


def test_promotion_documents_preserve_complete_scope_and_claim_boundaries() -> None:
    document = (
        PROJECT_ROOT / "docs" / "V2_7_PUBLIC_RELEASE_CANDIDATE.md"
    ).read_text(encoding="utf-8")
    release_notes = (
        PROJECT_ROOT / "docs" / "releases" / "V2_7_0.md"
    ).read_text(encoding="utf-8")

    for version in ["v2.5.1", "v2.5.2", *[f"v2.6.{i}" for i in range(1, 15)]]:
        assert version in document
    for version in ["2.5.1", "2.5.2", *[f"2.6.{i}" for i in range(1, 15)]]:
        assert version in release_notes
    assert "The stable public version is **v2.7.0**" in document
    assert "v2.6 evidence line" in document
    assert "38 audited commits" in document
    assert "Ridge forecast improvement: **Unsupported**" in document
    assert "final evidence-line scientific status: **Inconclusive**" in document
    assert "remain **Diagnostic**" in document
    assert "Ridge pooled MAE: `4.1537`" in release_notes
    assert "persistence pooled MAE: `3.4256`" in release_notes
    assert "not_ready_for_predictive_or_causal_modeling" in release_notes
    assert "does not establish" in document
