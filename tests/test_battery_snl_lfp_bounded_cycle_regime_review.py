from __future__ import annotations

import copy
import csv
import io
import json
from pathlib import Path
import shutil
import zipfile

import pytest

from src.platform_core import battery_snl_lfp_bounded_cycle_regime_review as mod


HEADER = [
    "Cycle_Index",
    "Start_Time",
    "End_Time",
    "Test_Time (s)",
    "Min_Current (A)",
    "Max_Current (A)",
    "Min_Voltage (V)",
    "Max_Voltage (V)",
    "Charge_Capacity (Ah)",
    "Discharge_Capacity (Ah)",
    "Charge_Energy (Wh)",
    "Discharge_Energy (Wh)",
]


def _copy_inputs(root: Path) -> mod.CycleRegimeConfig:
    for relative in (
        mod.DEFAULT_CONFIG_PATH,
        mod.DEFAULT_CONTRACT_PATH,
        "data/processed/battery_v2_6_8_snl_lfp_bounded_schema_read_summary.json",
    ):
        source = Path(relative)
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    return mod.load_config(repo_root=root)


def _csv_text(protocol: str, *, rows: int = 9, bad_width: bool = False,
              bad_value: bool = False, nonincreasing: bool = False,
              header: list[str] | None = None) -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(header or HEADER)
    for position in range(1, rows + 1):
        cycle_index = position
        if nonincreasing and position == 5:
            cycle_index = 4
        if position <= 3:
            values = [
                cycle_index, "start", "end", position * 100,
                -0.55, 0.55, 2.0, 3.6, 1.10, 1.08, 4.0, 3.8,
            ]
        elif protocol == "0-100":
            values = [
                cycle_index, "start", "end", position * 100,
                -1.10, 0.55, 2.0, 3.6, 1.08, 1.05, 4.0, 3.7,
            ]
        elif protocol == "20-80":
            values = [
                cycle_index, "start", "end", position * 100,
                -0.55, 0.55, 2.8, 3.4, 0.66, 0.64, 2.2, 2.0,
            ]
        else:
            values = [
                cycle_index, "start", "end", position * 100,
                -0.55, 0.55, 3.1, 3.3, 0.22, 0.21, 0.7, 0.65,
            ]
        if bad_value and position == 2:
            values[4] = "not-a-number"
        if bad_width and position == 4:
            values.pop()
        writer.writerow(values)
    return output.getvalue()


def _write_archive(
    root: Path,
    *,
    omit: str | None = None,
    rows: int = 9,
    bad_width: bool = False,
    bad_value: bool = False,
    nonincreasing: bool = False,
    bad_header: bool = False,
    include_extra: bool = False,
) -> Path:
    path = root / mod.EXPECTED_ARCHIVE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for entry in mod.REPRESENTATIVE_ENTRIES:
            if entry == omit:
                continue
            protocol = (
                "0-100" if "0-100" in entry
                else ("20-80" if "20-80" in entry else "40-60")
            )
            header = list(HEADER)
            if bad_header:
                header[-1] = "Changed_Header"
            archive.writestr(
                entry,
                _csv_text(
                    protocol,
                    rows=rows,
                    bad_width=bad_width,
                    bad_value=bad_value,
                    nonincreasing=nonincreasing,
                    header=header,
                ),
            )
        if include_extra:
            archive.writestr("SNL LFP/unapproved_timeseries.csv", "a,b\n1,2\n")
    return path


def _run(root: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    config = _copy_inputs(root)
    _write_archive(root)
    monkeypatch.setattr(mod, "sha256_file", lambda _path: mod.EXPECTED_ARCHIVE_SHA256)
    contract = json.loads((root / config.contract_path).read_text(encoding="utf-8"))
    upstream = json.loads((root / config.v2_6_8_summary_path).read_text(encoding="utf-8"))
    return mod.build_result(config, contract, upstream, root)


def test_header_checksum_matches_v2_6_8_contract():
    assert mod.canonical_checksum(HEADER) == mod.EXPECTED_CYCLE_HEADER_CHECKSUM


def test_preview_is_read_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    config = _copy_inputs(tmp_path)
    called = {"hash": False}

    def fail_hash(_path):
        called["hash"] = True
        raise AssertionError("preview must not hash the archive")

    monkeypatch.setattr(mod, "sha256_file", fail_hash)
    value = mod.preview(config, tmp_path)
    assert value["max_data_rows_per_entry"] == 8
    assert value["write_outputs"] is False
    assert called["hash"] is False


def test_success_reads_only_first_eight_rows_and_records_contrasts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    result = _run(tmp_path, monkeypatch)
    mod.validate_result(result)
    assert result["representative_read_summary"]["sample_cycle_row_count"] == 24
    assert result["representative_read_summary"]["evidence_recorded_count"] == 3
    assert result["cycle_regime_decision"]["capacity_check_vs_bulk_cycle_discrimination"] == (
        "candidate_supported_not_established"
    )
    assert all(item["sample_data_rows_read"] == 8 for item in result["file_observations"])
    assert all(len(item["selected_cycle_rows"]) == 8 for item in result["file_observations"])
    assert all(
        item["cycle_regime_contrast"]["threshold_fitted_or_inferred"] is False
        for item in result["file_observations"]
    )


def test_unapproved_entry_is_not_observed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    config = _copy_inputs(tmp_path)
    _write_archive(tmp_path, include_extra=True)
    monkeypatch.setattr(mod, "sha256_file", lambda _path: mod.EXPECTED_ARCHIVE_SHA256)
    contract = json.loads((tmp_path / config.contract_path).read_text(encoding="utf-8"))
    upstream = json.loads((tmp_path / config.v2_6_8_summary_path).read_text(encoding="utf-8"))
    result = mod.build_result(config, contract, upstream, tmp_path)
    assert {item["entry_name"] for item in result["file_observations"]} == set(
        mod.REPRESENTATIVE_ENTRIES
    )
    assert result["nonrepresentative_entry_read"] is False
    assert result["time_series_entry_read"] is False


def test_archive_checksum_mismatch_stops_before_zip_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    config = _copy_inputs(tmp_path)
    _write_archive(tmp_path)
    monkeypatch.setattr(mod, "sha256_file", lambda _path: "0" * 64)

    def fail_zip(*_args, **_kwargs):
        raise AssertionError("ZIP must not open after checksum mismatch")

    monkeypatch.setattr(mod.zipfile, "ZipFile", fail_zip)
    contract = json.loads((tmp_path / config.contract_path).read_text(encoding="utf-8"))
    upstream = json.loads((tmp_path / config.v2_6_8_summary_path).read_text(encoding="utf-8"))
    with pytest.raises(ValueError, match="archive checksum mismatch"):
        mod.build_result(config, contract, upstream, tmp_path)


@pytest.mark.parametrize(
    ("kwargs", "status"),
    [
        ({"rows": 7}, "insufficient_bounded_cycle_rows"),
        ({"bad_width": True}, "bounded_row_width_mismatch"),
        ({"bad_value": True}, "selected_value_contract_mismatch"),
        ({"nonincreasing": True}, "bounded_cycle_index_contract_mismatch"),
        ({"bad_header": True}, "cycle_header_checksum_mismatch"),
    ],
)
def test_contract_mismatches_are_recorded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    kwargs: dict,
    status: str,
):
    config = _copy_inputs(tmp_path)
    _write_archive(tmp_path, **kwargs)
    monkeypatch.setattr(mod, "sha256_file", lambda _path: mod.EXPECTED_ARCHIVE_SHA256)
    contract = json.loads((tmp_path / config.contract_path).read_text(encoding="utf-8"))
    upstream = json.loads((tmp_path / config.v2_6_8_summary_path).read_text(encoding="utf-8"))
    result = mod.build_result(config, contract, upstream, tmp_path)
    assert all(item["read_status"] == status for item in result["file_observations"])
    assert result["cycle_regime_decision"]["overall_status"] == (
        "bounded_cycle_regime_contract_not_fully_satisfied"
    )


def test_missing_entry_is_not_replaced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    config = _copy_inputs(tmp_path)
    missing = mod.REPRESENTATIVE_ENTRIES[1]
    _write_archive(tmp_path, omit=missing)
    monkeypatch.setattr(mod, "sha256_file", lambda _path: mod.EXPECTED_ARCHIVE_SHA256)
    contract = json.loads((tmp_path / config.contract_path).read_text(encoding="utf-8"))
    upstream = json.loads((tmp_path / config.v2_6_8_summary_path).read_text(encoding="utf-8"))
    result = mod.build_result(config, contract, upstream, tmp_path)
    item = next(value for value in result["file_observations"] if value["entry_name"] == missing)
    assert item["read_status"] == "representative_entry_missing"
    assert result["representative_read_summary"]["opened_entry_count"] == 2


def test_compact_result_is_deterministic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    first = mod.compact(_run(tmp_path / "a", monkeypatch))
    second = mod.compact(_run(tmp_path / "b", monkeypatch))
    assert first == second
    mod.validate_result(first)


def test_validate_rejects_scientific_promotion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    payload = mod.compact(_run(tmp_path, monkeypatch))
    promoted = copy.deepcopy(payload)
    promoted["cycle_regime_decision"]["capacity_check_vs_bulk_cycle_discrimination"] = (
        "established"
    )
    promoted["deterministic_result_checksum"] = mod.canonical_checksum(promoted)
    with pytest.raises(ValueError, match="capacity-check discrimination was promoted"):
        mod.validate_result(promoted)


def test_validate_rejects_threshold_inference(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    payload = mod.compact(_run(tmp_path, monkeypatch))
    payload["file_observations"][0]["cycle_regime_contrast"][
        "threshold_fitted_or_inferred"
    ] = True
    payload["deterministic_result_checksum"] = mod.canonical_checksum(payload)
    with pytest.raises(ValueError, match="threshold was fitted or inferred"):
        mod.validate_result(payload)


def test_execute_writes_only_declared_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    config = _copy_inputs(tmp_path)
    _write_archive(tmp_path)
    monkeypatch.setattr(mod, "sha256_file", lambda _path: mod.EXPECTED_ARCHIVE_SHA256)
    result = mod.execute(config, tmp_path, True)
    mod.validate_result(result)
    assert (tmp_path / config.output_root / "bounded_cycle_regime_result.json").is_file()
    assert (tmp_path / config.tracked_summary_path).is_file()
    assert not list(tmp_path.rglob("*.csv"))
