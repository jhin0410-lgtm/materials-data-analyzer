from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from src.platform_core import battery_source_evidence_recovery as mod


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path
    for directory in ["configs/examples", "data/platform", "data/processed"]:
        (root / directory).mkdir(parents=True, exist_ok=True)
    source_root = Path(__file__).resolve().parents[1]
    config = json.loads((source_root / mod.DEFAULT_CONFIG_PATH).read_text(encoding="utf-8"))
    manifest = json.loads(
        (source_root / "data/platform/battery_snl_lfp_source_document_manifest_v1.json").read_text(encoding="utf-8")
    )
    admission = {
        "candidate_id": "battery_archive_local_bundle_v1",
        "deterministic_result_checksum": "2776bc152c0e4655f0c90ec6513883aea3758cac7fac687e02e5685c72dfdb6f",
        "admission_decision": {"overall_status": "not_admitted_for_cross_cohort_validation"},
        "preservation_checks": {
            "preserved_metrics": [
                {"mae": 3.425575369058076, "model": "persistence"},
                {"mae": 4.15369918179312, "model": "ridge"},
            ]
        },
    }
    (root / mod.DEFAULT_CONFIG_PATH).write_text(json.dumps(config), encoding="utf-8")
    (root / config["source_document_manifest_path"]).write_text(json.dumps(manifest), encoding="utf-8")
    (root / config["source_admission_summary_path"]).write_text(json.dumps(admission), encoding="utf-8")
    return root


def load_fixture(repo: Path):
    config = mod.load_config(repo_root=repo)
    manifest = json.loads((repo / config.source_document_manifest_path).read_text(encoding="utf-8"))
    admission = json.loads((repo / config.source_admission_summary_path).read_text(encoding="utf-8"))
    return config, manifest, admission


def test_actual_config_loads():
    config = mod.load_config(repo_root=Path(__file__).resolve().parents[1])
    assert config.schema_version == "2.6.5"
    assert config.bounded_source_id == "snl_lfp_commercial_18650_study"


def test_unknown_config_field_is_rejected(repo: Path):
    payload = json.loads((repo / mod.DEFAULT_CONFIG_PATH).read_text(encoding="utf-8"))
    payload["surprise"] = True
    with pytest.raises(ValueError, match="unknown config"):
        mod.RecoveryConfig.from_dict(payload)


def test_path_traversal_is_rejected(repo: Path):
    payload = json.loads((repo / mod.DEFAULT_CONFIG_PATH).read_text(encoding="utf-8"))
    payload["output_root"] = "../escape"
    with pytest.raises(ValueError, match="repository-relative"):
        mod.RecoveryConfig.from_dict(payload)


def test_manifest_has_exact_document_and_evidence_order(repo: Path):
    config, manifest, _ = load_fixture(repo)
    mod.validate_manifest(manifest, config)
    assert tuple(item["document_id"] for item in manifest["documents"]) == mod.DOCUMENT_IDS
    assert tuple(item["evidence_field"] for item in manifest["evidence_claims"]) == mod.EVIDENCE_FIELDS


def test_document_recovery_does_not_promote_local_binding(repo: Path):
    config, manifest, admission = load_fixture(repo)
    result = mod.build_result(config, manifest, admission)
    assert result["coverage_summary"]["document_evidence_recovered_count"] == 7
    assert result["coverage_summary"]["promotion_requirement_satisfied_count"] == 0
    assert result["coverage_summary"]["remaining_blocking_field_count"] == 8


def test_recovery_decision_allows_only_bounded_inventory_binding(repo: Path):
    config, manifest, admission = load_fixture(repo)
    result = mod.build_result(config, manifest, admission)
    decision = result["recovery_decision"]
    assert decision["bounded_inventory_binding"]["status"] == "eligible_for_read_only_inventory_binding"
    assert decision["bounded_inventory_binding"]["csv_row_read_allowed"] is False
    assert decision["bounded_inventory_binding"]["archive_extraction_allowed"] is False
    assert decision["cross_cohort_comparability"]["status"] == "not_admitted"
    assert decision["predictive_validation"]["status"] == "blocked"


def test_source_metric_is_not_current_target_alignment(repo: Path):
    config, manifest, admission = load_fixture(repo)
    result = mod.build_result(config, manifest, admission)
    target = result["target_contract_assessment"]
    assert target["source_metric_documented"] is True
    assert target["aligned_to_v2_6_1_five_cycle_target"] is False
    assert target["predictive_target_ready"] is False


def test_admission_checksum_tampering_blocks_execution(repo: Path):
    config, manifest, admission = load_fixture(repo)
    admission["deterministic_result_checksum"] = "0" * 64
    with pytest.raises(ValueError, match="checksum mismatch"):
        mod.build_result(config, manifest, admission)


def test_manifest_binding_claim_is_rejected(repo: Path):
    config, manifest, _ = load_fixture(repo)
    tampered = copy.deepcopy(manifest)
    tampered["evidence_claims"][0]["battery_file_binding_established"] = True
    with pytest.raises(ValueError, match="may not claim local binding"):
        mod.validate_manifest(tampered, config)


def test_result_is_deterministic(repo: Path):
    config, manifest, admission = load_fixture(repo)
    first = mod.build_result(config, manifest, admission)
    second = mod.build_result(config, manifest, admission)
    assert first == second
    assert first["deterministic_result_checksum"] == second["deterministic_result_checksum"]


def test_preview_has_no_writes(repo: Path):
    config = mod.load_config(repo_root=repo)
    payload = mod.preview(config, repo_root=repo)
    assert payload["write_outputs"] is False
    assert payload["promotion_requirement_satisfied_count"] == 0
    assert not (repo / config.output_root).exists()
    assert not (repo / config.tracked_summary_path).exists()


def test_execute_writes_only_declared_outputs(repo: Path):
    config = mod.load_config(repo_root=repo)
    before_manifest = (repo / config.source_document_manifest_path).read_bytes()
    before_admission = (repo / config.source_admission_summary_path).read_bytes()
    result = mod.execute(config, repo_root=repo, write_outputs=True)
    assert (repo / config.output_root / "source_document_register.json").is_file()
    assert (repo / config.output_root / "recovery_matrix.json").is_file()
    assert (repo / config.output_root / "recovery_summary.json").is_file()
    tracked = json.loads((repo / config.tracked_summary_path).read_text(encoding="utf-8"))
    mod.validate_result(tracked)
    assert tracked["artifact_kind"].endswith("compact_summary")
    assert result["raw_data_read"] is False
    assert (repo / config.source_document_manifest_path).read_bytes() == before_manifest
    assert (repo / config.source_admission_summary_path).read_bytes() == before_admission


def test_validate_rejects_result_tampering(repo: Path):
    config, manifest, admission = load_fixture(repo)
    result = mod.build_result(config, manifest, admission)
    result["network_called"] = True
    with pytest.raises(ValueError, match="prohibited execution flag"):
        mod.validate_result(result)


def test_module_has_no_network_archive_or_model_dependencies():
    text = Path(mod.__file__).read_text(encoding="utf-8")
    prohibited = ["requests", "urllib", "httpx", "zipfile", "sklearn", "tensorflow", "torch", "xgboost"]
    for token in prohibited:
        assert token not in text
