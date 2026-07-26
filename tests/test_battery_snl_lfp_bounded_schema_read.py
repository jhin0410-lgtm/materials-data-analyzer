from __future__ import annotations

import json
from pathlib import Path
import zipfile

import pytest

from src.platform_core import battery_snl_lfp_bounded_schema_read as mod


CYCLE_TEXT = (
    "Cycle_Index,Charge_Capacity (Ah),Discharge_Capacity (Ah),Min_Voltage (V)\n"
    "1,1.10,1.08,2.0\n"
    "2,1.09,1.07,2.0\n"
    "3,1.08,1.06,2.0\n"
    "4,1.07,1.05,2.0\n"
    "5,1.06,1.04,2.0\n"
    "6,1.05,1.03,2.0\n"
)
TIMESERIES_TEXT = (
    "Test_Time (s),Cycle_Index,Step_Index,Current (A),Voltage (V),Cell_Temperature (C)\n"
    "0,1,1,0.55,3.2,25\n"
    "1,1,1,0.55,3.3,25\n"
    "2,1,2,0.00,3.4,25\n"
    "3,1,3,-1.10,3.2,25\n"
    "4,1,3,-1.10,3.1,25\n"
    "5,1,3,-1.10,3.0,25\n"
)


def write_archive(path: Path, overrides: dict[str, str] | None = None, omit: set[str] | None = None):
    overrides = overrides or {}
    omit = omit or set()
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in mod.REPRESENTATIVE_ENTRIES:
            if name in omit:
                continue
            default = CYCLE_TEXT if name.endswith("_cycle_data.csv") else TIMESERIES_TEXT
            archive.writestr(name, overrides.get(name, default))
        archive.writestr("SNL LFP/nonrepresentative_trap.csv", "must,not,be,read\n1,2,3,4\n")


def summary(payload: dict) -> dict:
    payload = dict(payload)
    payload["deterministic_result_checksum"] = mod.canonical_checksum(payload)
    return payload


def config_payload(v267_checksum: str, v266_checksum: str, archive_sha: str) -> dict:
    value = json.loads(Path(mod.DEFAULT_CONFIG_PATH).read_text(encoding="utf-8"))
    value["expected_v2_6_7_checksum"] = v267_checksum
    value["expected_v2_6_6_checksum"] = v266_checksum
    value["expected_archive_sha256"] = archive_sha
    return value


def setup_repo(tmp_path: Path, monkeypatch, with_archive: bool = True, overrides=None, omit=None):
    archive_path = tmp_path / mod.EXPECTED_ARCHIVE_PATH
    if with_archive:
        write_archive(archive_path, overrides=overrides, omit=omit)
        archive_sha = mod.sha256_file(archive_path)
    else:
        archive_sha = "a" * 64

    monkeypatch.setattr(mod, "EXPECTED_ARCHIVE_SHA256", archive_sha)
    contract = json.loads(Path(mod.DEFAULT_CONTRACT_PATH).read_text(encoding="utf-8"))
    contract["archive_identity"]["archive_sha256"] = archive_sha
    contract_path = tmp_path / mod.DEFAULT_CONTRACT_PATH
    contract_path.parent.mkdir(parents=True, exist_ok=True)
    contract_path.write_text(json.dumps(contract), encoding="utf-8")

    v267 = summary({
        "schema_version": "2.6.7",
        "binding_decision": {
            "overall_status": "condition_group_nomenclature_bound_gate_not_passed"
        },
    })
    v266 = summary({
        "schema_version": "2.6.6",
        "archive_audit": {
            "archive_sha256": archive_sha,
            "status": "local_artifact_inventory_bound",
        },
    })
    monkeypatch.setattr(mod, "EXPECTED_V267_CHECKSUM", v267["deterministic_result_checksum"])
    monkeypatch.setattr(mod, "EXPECTED_V266_CHECKSUM", v266["deterministic_result_checksum"])

    v267_path = tmp_path / "data/processed/battery_v2_6_7_snl_lfp_source_entry_binding_summary.json"
    v266_path = tmp_path / "data/processed/battery_v2_6_6_snl_lfp_artifact_binding_summary.json"
    v267_path.parent.mkdir(parents=True, exist_ok=True)
    v267_path.write_text(json.dumps(v267), encoding="utf-8")
    v266_path.write_text(json.dumps(v266), encoding="utf-8")

    cfg = config_payload(
        v267["deterministic_result_checksum"],
        v266["deterministic_result_checksum"],
        archive_sha,
    )
    cfg_path = tmp_path / mod.DEFAULT_CONFIG_PATH
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
    return mod.load_config(repo_root=tmp_path), contract, v267, v266


def test_config_is_strict_and_read_limits_are_fixed(tmp_path: Path, monkeypatch):
    config, _, _, _ = setup_repo(tmp_path, monkeypatch, with_archive=False)
    assert config.max_data_rows_per_entry == 5
    payload = json.loads((tmp_path / mod.DEFAULT_CONFIG_PATH).read_text())
    payload["csv_policy"]["max_data_rows_per_entry"] = 6
    with pytest.raises(ValueError, match="CSV read limits"):
        mod.SchemaReadConfig.from_dict(payload)


def test_contract_has_exact_six_representative_entries(tmp_path: Path, monkeypatch):
    config, contract, _, _ = setup_repo(tmp_path, monkeypatch, with_archive=False)
    mod.validate_contract(contract, config)
    assert tuple(x["entry_name"] for x in contract["representative_entries"]) == mod.REPRESENTATIVE_ENTRIES


def test_missing_archive_is_explicit_pending(tmp_path: Path, monkeypatch):
    config, contract, v267, v266 = setup_repo(tmp_path, monkeypatch, with_archive=False)
    result = mod.build_result(config, contract, v267, v266, tmp_path)
    assert result["schema_read_decision"]["overall_status"] == "pending_local_artifact"
    assert result["csv_headers_read"] is False
    assert result["csv_data_rows_read"] is False
    mod.validate_result(result)


def test_valid_archive_reads_only_exact_entries_and_five_rows(tmp_path: Path, monkeypatch):
    config, contract, v267, v266 = setup_repo(tmp_path, monkeypatch)
    opened = []
    original = zipfile.ZipFile.open

    def recording_open(self, name, *args, **kwargs):
        opened.append(name.filename if isinstance(name, zipfile.ZipInfo) else name)
        return original(self, name, *args, **kwargs)

    monkeypatch.setattr(zipfile.ZipFile, "open", recording_open)
    result = mod.build_result(config, contract, v267, v266, tmp_path)
    assert opened == list(mod.REPRESENTATIVE_ENTRIES)
    assert result["schema_read_decision"]["overall_status"] == "bounded_schema_observed_gate_not_passed"
    assert result["representative_read_summary"]["opened_entry_count"] == 6
    assert result["representative_read_summary"]["sample_data_row_count"] == 30
    assert all(x["sample_data_rows_read"] == 5 for x in result["file_observations"])
    assert all(x["raw_sample_values_retained"] is False for x in result["file_observations"])
    mod.validate_result(result)


def test_timeseries_required_roles_are_observed(tmp_path: Path, monkeypatch):
    config, contract, v267, v266 = setup_repo(tmp_path, monkeypatch)
    result = mod.build_result(config, contract, v267, v266, tmp_path)
    series = [x for x in result["file_observations"] if x["file_kind"] == "timeseries"]
    assert len(series) == 3
    for item in series:
        roles = item["role_contract"]["observed_candidate_roles"]
        assert {"test_time", "voltage", "current"}.issubset(roles)


def test_missing_representative_entry_is_rejected(tmp_path: Path, monkeypatch):
    missing = {mod.REPRESENTATIVE_ENTRIES[-1]}
    config, contract, v267, v266 = setup_repo(tmp_path, monkeypatch, omit=missing)
    result = mod.build_result(config, contract, v267, v266, tmp_path)
    assert result["schema_read_decision"]["overall_status"] == "representative_entry_contract_mismatch"
    assert result["representative_read_summary"]["opened_entry_count"] == 5


def test_row_width_mismatch_is_diagnostic_not_promoted(tmp_path: Path, monkeypatch):
    name = mod.REPRESENTATIVE_ENTRIES[0]
    bad = CYCLE_TEXT.replace("2,1.09,1.07,2.0", "2,1.09")
    config, contract, v267, v266 = setup_repo(tmp_path, monkeypatch, overrides={name: bad})
    result = mod.build_result(config, contract, v267, v266, tmp_path)
    assert result["schema_read_decision"]["overall_status"] == "bounded_schema_contract_mismatch"
    item = result["file_observations"][0]
    assert item["row_width_contract_match"] is False
    assert result["schema_read_decision"]["cycle_command_to_rows"] == "not_established"


def test_missing_required_role_is_contract_mismatch(tmp_path: Path, monkeypatch):
    name = mod.REPRESENTATIVE_ENTRIES[1]
    bad = TIMESERIES_TEXT.replace("Current (A)", "Signal_X")
    config, contract, v267, v266 = setup_repo(tmp_path, monkeypatch, overrides={name: bad})
    result = mod.build_result(config, contract, v267, v266, tmp_path)
    assert result["schema_read_decision"]["overall_status"] == "bounded_schema_contract_mismatch"


def test_overlong_physical_line_stops_entry(tmp_path: Path, monkeypatch):
    name = mod.REPRESENTATIVE_ENTRIES[1]
    bad = "X" * (mod.MAX_LINE_BYTES + 1) + "\n1\n"
    config, contract, v267, v266 = setup_repo(tmp_path, monkeypatch, overrides={name: bad})
    result = mod.build_result(config, contract, v267, v266, tmp_path)
    item = next(x for x in result["file_observations"] if x["entry_name"] == name)
    assert item["read_status"] == "bounded_parse_error"
    assert "byte limit" in item["error"]


def test_archive_identity_mismatch_prevents_payload_open(tmp_path: Path, monkeypatch):
    config, contract, v267, v266 = setup_repo(tmp_path, monkeypatch)
    archive_path = tmp_path / mod.EXPECTED_ARCHIVE_PATH
    with archive_path.open("ab") as handle:
        handle.write(b"identity-mismatch")

    def forbidden(*args, **kwargs):
        raise AssertionError("entry payload must not be opened after checksum mismatch")

    monkeypatch.setattr(zipfile.ZipFile, "open", forbidden)
    result = mod.build_result(config, contract, v267, v266, tmp_path)
    assert result["schema_read_decision"]["overall_status"] == "rejected_archive_identity_mismatch"
    assert result["representative_entry_payloads_read"] is False


def test_preview_does_not_hash_or_open_archive(tmp_path: Path, monkeypatch):
    config, _, _, _ = setup_repo(tmp_path, monkeypatch)

    def forbidden(*args, **kwargs):
        raise AssertionError("preview may not read archive")

    monkeypatch.setattr(mod, "sha256_file", forbidden)
    monkeypatch.setattr(zipfile, "ZipFile", forbidden)
    value = mod.preview(config, tmp_path)
    assert value["archive_present"] is True
    assert value["max_data_rows_per_entry"] == 5


def test_compact_retains_schema_not_raw_values(tmp_path: Path, monkeypatch):
    config, contract, v267, v266 = setup_repo(tmp_path, monkeypatch)
    result = mod.build_result(config, contract, v267, v266, tmp_path)
    compact = mod.compact(result)
    text = json.dumps(compact)
    assert "1.10" not in text
    assert compact["file_observations"][0]["header_observations"]
    mod.validate_result(compact)


def test_validate_rejects_scientific_promotion(tmp_path: Path, monkeypatch):
    config, contract, v267, v266 = setup_repo(tmp_path, monkeypatch)
    result = mod.build_result(config, contract, v267, v266, tmp_path)
    result["schema_read_decision"]["cycle_command_to_rows"] = "established"
    result["deterministic_result_checksum"] = mod.canonical_checksum(result)
    with pytest.raises(ValueError, match="cycle-command"):
        mod.validate_result(result)


def test_result_is_deterministic(tmp_path: Path, monkeypatch):
    config, contract, v267, v266 = setup_repo(tmp_path, monkeypatch)
    first = mod.build_result(config, contract, v267, v266, tmp_path)
    second = mod.build_result(config, contract, v267, v266, tmp_path)
    assert first["deterministic_result_checksum"] == second["deterministic_result_checksum"]


def test_execute_writes_only_declared_outputs(tmp_path: Path, monkeypatch):
    config, _, _, _ = setup_repo(tmp_path, monkeypatch)
    mod.execute(config, tmp_path, write_outputs=True)
    output_root = tmp_path / mod.DEFAULT_OUTPUT_ROOT
    assert sorted(x.name for x in output_root.iterdir()) == ["bounded_schema_read_result.json"]
    assert (tmp_path / mod.DEFAULT_TRACKED_SUMMARY).is_file()
    saved = json.loads((tmp_path / mod.DEFAULT_TRACKED_SUMMARY).read_text())
    mod.validate_result(saved)


def test_module_has_no_dataframe_network_or_model_dependency():
    text = Path(mod.__file__).read_text(encoding="utf-8")
    for forbidden in ("pandas", "numpy", "requests", "urllib", "sklearn", "tensorflow", "torch"):
        assert f"import {forbidden}" not in text
        assert f"from {forbidden}" not in text


def test_raw_archive_and_nonrepresentative_reads_remain_bounded():
    assert mod.EXPECTED_ARCHIVE_PATH.startswith("data/raw/")
    assert len(mod.REPRESENTATIVE_ENTRIES) == 6
    assert mod.MAX_ROWS == 5
