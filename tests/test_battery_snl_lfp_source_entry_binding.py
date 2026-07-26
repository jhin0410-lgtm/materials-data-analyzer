from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from src.platform_core import battery_snl_lfp_source_entry_binding as mod


def fake_v265() -> dict:
    payload = {
        "schema_version": "2.6.5",
        "bounded_source_id": "snl_lfp_commercial_18650_study",
        "recovery_decision": {"overall_status": "source_evidence_recovered_gate_not_passed"},
        "preservation_checks": {
            "preserved_metrics": [
                {"mae": 3.425575369058076, "model": "persistence"},
                {"mae": 4.15369918179312, "model": "ridge"},
            ]
        },
    }
    payload["deterministic_result_checksum"] = mod.canonical_checksum(payload)
    return payload


def fake_v266() -> dict:
    payload = {
        "schema_version": "2.6.6",
        "bounded_source_id": "snl_lfp_commercial_18650_study",
        "binding_decision": {"overall_status": "local_artifact_inventory_bound_gate_not_passed"},
        "archive_audit": {
            "archive_sha256": mod.EXPECTED_ARCHIVE_SHA256,
            "entry_manifest_checksum": mod.EXPECTED_ENTRY_MANIFEST_CHECKSUM,
            "inventory": {"inventory_contract_match": True},
        },
    }
    payload["deterministic_result_checksum"] = mod.canonical_checksum(payload)
    return payload


def config_payload(v265_checksum: str, v266_checksum: str) -> dict:
    return {
        "schema_version": mod.VERSION,
        "package_id": mod.PACKAGE_ID,
        "case_study_id": "battery_archive_snl_lfp",
        "bounded_source_id": "snl_lfp_commercial_18650_study",
        "source_entry_binding_manifest_path": mod.DEFAULT_MANIFEST_PATH,
        "v2_6_5_source_evidence_summary_path": mod.V265_SUMMARY,
        "v2_6_6_artifact_binding_summary_path": mod.V266_SUMMARY,
        "expected_v2_6_5_checksum": v265_checksum,
        "expected_v2_6_6_checksum": v266_checksum,
        "required_evidence_fields": list(mod.EVIDENCE_FIELDS),
        "required_binding_dimensions": list(mod.BINDING_DIMENSIONS),
        "read_policy": {
            "allow_tracked_json_reads": True,
            "allow_raw_archive_read": False,
            "allow_entry_payload_read": False,
            "allow_csv_header_read": False,
            "allow_csv_row_read": False,
            "allow_archive_extraction": False,
        },
        "credential_policy": {"store_credentials": False, "network_access_required": False},
        "output_root": mod.DEFAULT_OUTPUT_ROOT,
        "tracked_summary_path": mod.DEFAULT_TRACKED_SUMMARY,
        "output_policy": "tracked_compact_summary_and_local_full_result",
        "dry_run": True,
    }


def repository_manifest() -> dict:
    return json.loads(Path(mod.DEFAULT_MANIFEST_PATH).read_text(encoding="utf-8"))


def setup_repo(tmp_path: Path) -> tuple[mod.ReviewConfig, dict, dict, dict]:
    v265, v266, manifest = fake_v265(), fake_v266(), repository_manifest()
    files = {
        mod.DEFAULT_MANIFEST_PATH: manifest,
        mod.V265_SUMMARY: v265,
        mod.V266_SUMMARY: v266,
        mod.DEFAULT_CONFIG_PATH: config_payload(
            v265["deterministic_result_checksum"],
            v266["deterministic_result_checksum"],
        ),
    }
    for relative, payload in files.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
    return mod.load_config(repo_root=tmp_path), manifest, v265, v266


def test_config_is_strict_and_path_safe(tmp_path: Path):
    config, _, v265, v266 = setup_repo(tmp_path)
    assert config.manifest_path == mod.DEFAULT_MANIFEST_PATH
    payload = config_payload(v265["deterministic_result_checksum"], v266["deterministic_result_checksum"])
    payload["source_entry_binding_manifest_path"] = "../binding.json"
    with pytest.raises(ValueError, match="repository-relative"):
        mod.ReviewConfig.from_dict(payload)


def test_manifest_has_12_groups_and_30_pairs(tmp_path: Path):
    config, manifest, _, _ = setup_repo(tmp_path)
    mod.validate_manifest(manifest, config)
    groups = manifest["condition_group_bindings"]
    assert len(groups) == 12
    assert sum(row["observed_cell_count"] for row in groups) == 30
    assert sum(row["observed_entry_pair_count"] for row in groups) == 30


def test_condition_groups_preserve_official_nomenclature_scope(tmp_path: Path):
    config, manifest, _, _ = setup_repo(tmp_path)
    mod.validate_manifest(manifest, config)
    assert all(row["institution_code"] == "SNL" for row in manifest["condition_group_bindings"])
    assert all(row["form_factor"] == "18650" for row in manifest["condition_group_bindings"])
    assert all(row["chemistry_label"] == "LFP" for row in manifest["condition_group_bindings"])
    assert all(row["charge_rate_c"] == 0.5 for row in manifest["condition_group_bindings"])


def test_soc_protocol_family_mapping_is_explicit(tmp_path: Path):
    config, manifest, _, _ = setup_repo(tmp_path)
    mod.validate_manifest(manifest, config)
    for row in manifest["condition_group_bindings"]:
        family = row["study_protocol_family"]
        if row["soc_window_percent"] == "0-100":
            assert "CCCV" in family
        elif row["soc_window_percent"] == "20-80":
            assert "voltage limits" in family
        else:
            assert row["soc_window_percent"] == "40-60"
            assert "capacity limits" in family


def test_build_result_establishes_only_group_nomenclature_binding(tmp_path: Path):
    config, manifest, v265, v266 = setup_repo(tmp_path)
    decision = mod.build_result(config, manifest, v265, v266)["binding_decision"]
    assert decision["publication_to_repository"] == "established"
    assert decision["repository_filename_nomenclature"] == "established"
    assert decision["condition_group_to_entry_patterns"] == "established_repository_nomenclature_only"
    assert decision["physical_cell_to_entry"] == "not_established"
    assert decision["cycle_command_to_rows"] == "not_established"
    assert decision["official_distribution_snapshot"] == "not_established"


def test_no_evidence_field_is_promoted(tmp_path: Path):
    config, manifest, v265, v266 = setup_repo(tmp_path)
    result = mod.build_result(config, manifest, v265, v266)
    assert result["coverage_summary"]["promotion_requirement_satisfied_count"] == 0
    assert all(row["promotion_requirement_satisfied"] is False for row in result["evidence_binding_matrix"])


def test_source_summary_content_tampering_is_detected(tmp_path: Path):
    config, manifest, v265, v266 = setup_repo(tmp_path)
    v266["archive_audit"]["archive_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="source summary checksum"):
        mod.build_result(config, manifest, v265, v266)


def test_archive_and_entry_manifest_identity_are_preserved(tmp_path: Path):
    config, manifest, v265, v266 = setup_repo(tmp_path)
    result = mod.build_result(config, manifest, v265, v266)
    assert result["preservation_checks"]["archive_identity_verified"] is True
    assert result["preservation_checks"]["entry_manifest_identity_verified"] is True
    assert result["archive_identity"]["archive_sha256"] == mod.EXPECTED_ARCHIVE_SHA256
    assert result["archive_identity"]["entry_manifest_checksum"] == mod.EXPECTED_ENTRY_MANIFEST_CHECKSUM


def test_manifest_rejects_physical_cell_promotion(tmp_path: Path):
    config, manifest, _, _ = setup_repo(tmp_path)
    manifest = copy.deepcopy(manifest)
    manifest["condition_group_bindings"][0]["physical_cell_identity_established"] = True
    with pytest.raises(ValueError, match="physical-cell identity"):
        mod.validate_manifest(manifest, config)


def test_manifest_rejects_official_snapshot_promotion(tmp_path: Path):
    config, manifest, _, _ = setup_repo(tmp_path)
    manifest = copy.deepcopy(manifest)
    manifest["archive_identity"]["provider_versioned_distribution_id"] = "invented-release"
    with pytest.raises(ValueError, match="distribution ID"):
        mod.validate_manifest(manifest, config)


def test_manifest_rejects_condition_group_count_drift(tmp_path: Path):
    config, manifest, _, _ = setup_repo(tmp_path)
    manifest = copy.deepcopy(manifest)
    manifest["condition_group_bindings"][0]["observed_cell_count"] += 1
    with pytest.raises(ValueError, match="cell total"):
        mod.validate_manifest(manifest, config)


def test_result_is_deterministic(tmp_path: Path):
    config, manifest, v265, v266 = setup_repo(tmp_path)
    first = mod.build_result(config, manifest, v265, v266)
    second = mod.build_result(config, manifest, v265, v266)
    assert first["deterministic_result_checksum"] == second["deterministic_result_checksum"]
    assert mod.compact(first)["deterministic_result_checksum"] == mod.compact(second)["deterministic_result_checksum"]


def test_compact_omits_full_source_register_and_binding_rows(tmp_path: Path):
    config, manifest, v265, v266 = setup_repo(tmp_path)
    compact = mod.compact(mod.build_result(config, manifest, v265, v266))
    assert "source_register" not in compact
    assert "condition_group_bindings" not in compact
    assert len(compact["condition_group_summary"]) == 12
    assert len(compact["binding_dimension_statuses"]) == 8
    mod.validate_result(compact)


def test_execute_writes_only_declared_outputs(tmp_path: Path):
    config, _, _, _ = setup_repo(tmp_path)
    result = mod.execute(config, tmp_path, write_outputs=True)
    output_root = tmp_path / mod.DEFAULT_OUTPUT_ROOT
    assert sorted(path.name for path in output_root.iterdir()) == ["source_entry_binding_review.json"]
    tracked = tmp_path / mod.DEFAULT_TRACKED_SUMMARY
    assert tracked.is_file()
    mod.validate_result(json.loads(tracked.read_text(encoding="utf-8")))
    assert result["coverage_summary"]["condition_group_count"] == 12


def test_preview_reads_only_tracked_evidence(tmp_path: Path):
    config, _, _, _ = setup_repo(tmp_path)
    value = mod.preview(config, tmp_path)
    assert value["condition_group_count"] == 12
    assert value["represented_cell_count"] == 30
    assert value["allowed_reads"] == ["tracked JSON evidence packages"]
    assert value["write_outputs"] is False


def test_validate_rejects_silent_scientific_promotion(tmp_path: Path):
    config, manifest, v265, v266 = setup_repo(tmp_path)
    result = mod.build_result(config, manifest, v265, v266)
    result["coverage_summary"]["promotion_requirement_satisfied_count"] = 1
    result["deterministic_result_checksum"] = mod.canonical_checksum(result)
    with pytest.raises(ValueError, match="silently promoted"):
        mod.validate_result(result)


def test_schemas_manifest_and_tracked_summary_parse():
    for path in (
        Path("data/platform/battery_snl_lfp_source_entry_binding_manifest_v1.json"),
        Path("data/platform/battery_source_entry_binding_manifest_schema_v1.json"),
        Path("data/platform/battery_source_entry_binding_review_config_schema_v1.json"),
        Path("data/platform/battery_source_entry_binding_review_result_schema_v1.json"),
        Path("data/processed/battery_v2_6_7_snl_lfp_source_entry_binding_summary.json"),
    ):
        json.loads(path.read_text(encoding="utf-8"))


def test_module_has_no_network_dataframe_archive_or_model_dependencies():
    text = Path(mod.__file__).read_text(encoding="utf-8")
    for forbidden in ("requests", "urllib", "pandas", "numpy", "sklearn", "tensorflow", "torch", "zipfile"):
        assert f"import {forbidden}" not in text
        assert f"from {forbidden}" not in text
