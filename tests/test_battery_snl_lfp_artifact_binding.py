from __future__ import annotations

import json
from pathlib import Path
import zipfile

import pytest

from src.platform_core import battery_snl_lfp_artifact_binding as mod


def source_summary() -> dict:
    payload = {
        "schema_version": "2.6.5",
        "bounded_source_id": "snl_lfp_commercial_18650_study",
        "coverage_summary": {"promotion_requirement_satisfied_count": 0},
        "recovery_decision": {"overall_status": "source_evidence_recovered_gate_not_passed"},
    }
    payload["deterministic_result_checksum"] = mod.canonical_checksum(payload)
    return payload


def config_payload(source_checksum: str) -> dict:
    return {
        "schema_version": "2.6.6",
        "package_id": mod.PACKAGE_ID,
        "case_study_id": "battery_archive_snl_lfp",
        "bounded_source_id": "snl_lfp_commercial_18650_study",
        "archive_path": mod.EXPECTED_ARCHIVE_PATH,
        "source_evidence_summary_path": "data/processed/battery_v2_6_5_snl_lfp_source_evidence_summary.json",
        "expected_source_evidence_checksum": source_checksum,
        "expected_archive_filename": "SNL LFP.zip",
        "expected_root_prefix": mod.EXPECTED_ROOT_PREFIX,
        "expected_inventory": dict(mod.EXPECTED_COUNTS),
        "required_evidence_fields": list(mod.EVIDENCE_FIELDS),
        "read_policy": {
            "allow_archive_sha256": True,
            "allow_zip_central_directory": True,
            "allow_entry_payload_read": False,
            "allow_archive_extraction": False,
            "allow_csv_row_read": False,
        },
        "credential_policy": {"store_credentials": False, "network_access_required": False},
        "output_root": mod.DEFAULT_OUTPUT_ROOT,
        "tracked_summary_path": mod.DEFAULT_TRACKED_SUMMARY,
        "output_policy": "local_details_and_tracked_compact_summary",
        "dry_run": True,
    }


def setup_repo(tmp_path: Path, with_archive: bool = True, entries: int = 30) -> mod.BindingConfig:
    summary = source_summary()
    source_path = tmp_path / "data/processed/battery_v2_6_5_snl_lfp_source_evidence_summary.json"
    source_path.parent.mkdir(parents=True)
    source_path.write_text(json.dumps(summary), encoding="utf-8")
    cfg_path = tmp_path / mod.DEFAULT_CONFIG_PATH
    cfg_path.parent.mkdir(parents=True)
    cfg_path.write_text(json.dumps(config_payload(summary["deterministic_result_checksum"])), encoding="utf-8")
    if with_archive:
        archive_path = tmp_path / mod.EXPECTED_ARCHIVE_PATH
        archive_path.parent.mkdir(parents=True)
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for index in range(entries):
                stem = f"SNL_18650_LFP_15C_0-100_0.5-1C_r{index:02d}"
                archive.writestr(f"SNL LFP/{stem}_cycle_data.csv", "not read\n")
                archive.writestr(f"SNL LFP/{stem}_timeseries.csv", "not read\n")
    return mod.load_config(repo_root=tmp_path)


def test_config_is_strict_and_path_safe(tmp_path: Path):
    config = setup_repo(tmp_path, with_archive=False)
    assert config.archive_path == mod.EXPECTED_ARCHIVE_PATH
    payload = config_payload(source_summary()["deterministic_result_checksum"])
    payload["archive_path"] = "../SNL LFP.zip"
    with pytest.raises(ValueError, match="repository-relative"):
        mod.BindingConfig.from_dict(payload)


def test_missing_local_archive_is_explicit_pending(tmp_path: Path):
    config = setup_repo(tmp_path, with_archive=False)
    result = mod.build_result(config, source_summary(), tmp_path)
    assert result["archive_audit"]["status"] == "pending_local_artifact"
    assert result["binding_decision"]["overall_status"] == "pending_local_artifact"
    assert result["archive_bytes_read_for_checksum"] is False
    assert result["zip_central_directory_read"] is False
    assert result["scientific_closeout"]["status"] == "inconclusive"


def test_valid_archive_uses_central_directory_without_payload_reads(tmp_path: Path, monkeypatch):
    config = setup_repo(tmp_path)

    def forbidden(*args, **kwargs):
        raise AssertionError("entry payload access or extraction is prohibited")

    monkeypatch.setattr(zipfile.ZipFile, "open", forbidden)
    monkeypatch.setattr(zipfile.ZipFile, "read", forbidden)
    monkeypatch.setattr(zipfile.ZipFile, "extract", forbidden)
    monkeypatch.setattr(zipfile.ZipFile, "extractall", forbidden)
    result = mod.build_result(config, source_summary(), tmp_path)
    audit = result["archive_audit"]
    assert audit["status"] == "local_artifact_inventory_bound"
    assert len(audit["archive_sha256"]) == 64
    assert audit["inventory"]["actual_entry_count"] == 60
    assert audit["inventory"]["complete_pair_count"] == 30
    assert audit["label_summary"] == {
        "parsed_count": 60,
        "unparsed_count": 0,
        "labels_are_scientific_evidence": False,
    }
    assert result["entry_payloads_read"] is False
    assert result["csv_rows_read"] is False
    assert result["archives_extracted"] is False


def test_filename_labels_keep_entry_name_provenance():
    labels = mod.parse_filename_labels("SNL LFP/SNL_18650_LFP_15C_0-100_0.5-1C_a_cycle_data.csv")
    assert labels["parse_status"] == "parsed_filename_labels"
    assert labels["chemistry_label"] == "LFP"
    assert labels["temperature_label"] == "15C"
    assert labels["charge_rate_label_c"] == "0.5"
    assert labels["discharge_rate_label_c"] == "1"
    assert labels["provenance"] == "entry_name"
    assert labels["scientific_evidence"] is False


def test_inventory_mismatch_does_not_bind(tmp_path: Path):
    config = setup_repo(tmp_path, entries=29)
    result = mod.build_result(config, source_summary(), tmp_path)
    assert result["archive_audit"]["status"] == "inventory_contract_mismatch"
    assert result["binding_decision"]["document_to_archive_binding"] == "not_established"
    assert result["evidence_promotion"]["promotion_requirement_satisfied_count"] == 0


def test_unsafe_entry_is_rejected(tmp_path: Path):
    config = setup_repo(tmp_path, with_archive=False)
    archive_path = tmp_path / mod.EXPECTED_ARCHIVE_PATH
    archive_path.parent.mkdir(parents=True)
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("../escape.csv", "x")
    result = mod.build_result(config, source_summary(), tmp_path)
    assert result["archive_audit"]["status"] == "rejected_unsafe_archive_inventory"
    assert result["archive_audit"]["safety"]["unsafe_entry_count"] == 1


def test_result_is_deterministic_for_same_archive(tmp_path: Path):
    config = setup_repo(tmp_path)
    first = mod.build_result(config, source_summary(), tmp_path)
    second = mod.build_result(config, source_summary(), tmp_path)
    assert first["deterministic_result_checksum"] == second["deterministic_result_checksum"]
    assert first["archive_audit"]["entry_manifest_checksum"] == second["archive_audit"]["entry_manifest_checksum"]


def test_source_summary_content_tampering_is_detected():
    summary = source_summary()
    config = mod.BindingConfig.from_dict(config_payload(summary["deterministic_result_checksum"]))
    summary["bounded_source_id"] = "changed"
    with pytest.raises(ValueError, match="content checksum"):
        mod.verify_source_evidence(summary, config)


def test_validate_rejects_scientific_promotion(tmp_path: Path):
    config = setup_repo(tmp_path, with_archive=False)
    result = mod.build_result(config, source_summary(), tmp_path)
    result["evidence_promotion"]["promotion_requirement_satisfied_count"] = 1
    result["deterministic_result_checksum"] = mod.canonical_checksum(result)
    with pytest.raises(ValueError, match="silently promoted"):
        mod.validate_result(result)


def test_execute_writes_only_declared_outputs(tmp_path: Path):
    config = setup_repo(tmp_path)
    result = mod.execute(config, tmp_path, write_outputs=True)
    output_root = tmp_path / mod.DEFAULT_OUTPUT_ROOT
    assert sorted(path.name for path in output_root.iterdir()) == [
        "artifact_binding_summary.json",
        "central_directory_manifest.json",
    ]
    assert (tmp_path / mod.DEFAULT_TRACKED_SUMMARY).is_file()
    assert len(result["archive_audit"]["entry_manifest"]) == 60


def test_preview_does_not_read_archive_bytes(tmp_path: Path, monkeypatch):
    config = setup_repo(tmp_path)

    def forbidden(*args, **kwargs):
        raise AssertionError("preview may not hash or open the ZIP")

    monkeypatch.setattr(mod, "sha256_file", forbidden)
    monkeypatch.setattr(zipfile, "ZipFile", forbidden)
    value = mod.preview(config, tmp_path)
    assert value["archive_present"] is True
    assert value["write_outputs"] is False


def test_compact_omits_row_level_entry_manifest(tmp_path: Path):
    config = setup_repo(tmp_path)
    result = mod.build_result(config, source_summary(), tmp_path)
    compact = mod.compact(result)
    assert "entry_manifest" not in compact["archive_audit"]
    assert compact["archive_audit"]["entry_manifest_checksum"] == result["archive_audit"]["entry_manifest_checksum"]
    mod.validate_result(compact)


def test_schemas_and_tracked_summary_parse():
    for path in (
        Path("data/platform/battery_artifact_binding_audit_config_schema_v1.json"),
        Path("data/platform/battery_artifact_binding_audit_result_schema_v1.json"),
        Path("data/processed/battery_v2_6_6_snl_lfp_artifact_binding_summary.json"),
    ):
        json.loads(path.read_text(encoding="utf-8"))


def test_module_has_no_network_dataframe_or_model_dependencies():
    text = Path(mod.__file__).read_text(encoding="utf-8")
    for forbidden in ("requests", "urllib", "pandas", "numpy", "sklearn", "tensorflow", "torch"):
        assert f"import {forbidden}" not in text
        assert f"from {forbidden}" not in text


def test_expected_archive_path_is_gitignored_by_policy():
    assert mod.EXPECTED_ARCHIVE_PATH.startswith("data/raw/")
