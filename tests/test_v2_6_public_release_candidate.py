from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "audit_v2_6_public_release_candidate.py"


def _module():
    spec = importlib.util.spec_from_file_location("v2_6_release_candidate", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_tracked_v2_6_release_promotion_preserves_truthful_version() -> None:
    module = _module()
    summary = module.build_summary(PROJECT_ROOT)

    assert summary["status"] == "completed"
    assert summary["decision"] == (
        "v2_6_0_metadata_promoted_pending_external_release_action"
    )
    assert summary["candidate_version"] == "2.6.0"
    assert summary["release_date"] == "2026-07-28"
    assert summary["separate_v2_5_public_release_authorized"] is False
    assert summary["software_validation"]["status"] == "supported"
    assert summary["software_validation"]["v2_6_stage_count"] == 13
    assert all(summary["software_validation"]["checks"].values())
    assert summary["scientific_closeout"]["status"] == "inconclusive"
    assert summary["scientific_closeout"]["ridge_generalization"] == "unsupported"
    assert summary["scientific_closeout"]["predictive_validation_readiness"] == (
        "not_ready"
    )
    assert summary["public_metadata_promotion_performed"] is True
    assert summary["tag_or_release_created"] is False


def test_release_stage_inventory_is_complete_and_ordered() -> None:
    config = json.loads(
        (PROJECT_ROOT / "configs" / "v2_6_public_release_candidate.json").read_text(
            encoding="utf-8"
        )
    )
    expected = ["2.5.1", "2.5.2", *[f"2.6.{index}" for index in range(1, 15)]]

    assert config["included_feature_stage_versions"] == expected
    assert len(config["audited_main_commit"]) == 40
    assert len(config["v2_6_core_closeout_commit"]) == 40
    assert config["public_metadata_promotion_performed"] is True
    assert config["tag_or_release_created"] is False


def test_release_outputs_are_checksummed_and_fail_closed(tmp_path: Path) -> None:
    module = _module()
    output = tmp_path / "promotion"
    paths = module.run(PROJECT_ROOT, output)

    summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    assert summary["candidate_version"] == "2.6.0"
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


def test_release_document_preserves_claim_boundaries() -> None:
    document = (
        PROJECT_ROOT / "docs" / "V2_6_PUBLIC_RELEASE_CANDIDATE.md"
    ).read_text(encoding="utf-8")
    release_notes = (
        PROJECT_ROOT / "docs" / "releases" / "V2_6_0.md"
    ).read_text(encoding="utf-8")

    assert "Ridge generalization: **Unsupported**" in document
    assert "final scientific closeout: **Inconclusive**" in document
    assert "three-condition process design is **Diagnostic**" in document
    assert "A separate v2.5.0 public release is not justified" in document
    assert "does not establish" in document
    assert "2.6.14" in release_notes
    assert "Ridge pooled MAE: `4.1537`" in release_notes
    assert "not_ready_for_predictive_or_causal_modeling" in release_notes
