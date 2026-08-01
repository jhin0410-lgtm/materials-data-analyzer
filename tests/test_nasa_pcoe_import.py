from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy.io import savemat

from platform_core.battery_intelligence import (
    BatteryIntelligenceConfig,
    audit_raw_signal_admission,
    import_nasa_pcoe_battery,
    run_battery_intelligence,
)
from platform_core.battery_intelligence.common import file_sha256


OFFICIAL_ARCHIVE_URL = (
    "https://phm-datasets.s3.amazonaws.com/NASA/5.+Battery+Data+Set.zip"
)


def _write_battery_mat(
    path: Path,
    battery_id: str,
    *,
    cycles: int = 15,
    malformed_cycle: int | None = None,
) -> None:
    operations: list[dict[str, object]] = []
    battery_offset = int(battery_id[-2:]) if battery_id[-2:].isdigit() else 0
    for cycle in range(1, cycles + 1):
        elapsed = np.linspace(0.0, 3600.0, 21)
        voltage = np.linspace(4.2, 3.0, 21) - 0.001 * cycle
        current = np.full(21, -(1.0 + 0.01 * battery_offset))
        temperature = np.linspace(
            24.0 + battery_offset,
            27.0 + battery_offset,
            21,
        )
        if malformed_cycle == cycle:
            voltage = voltage[:-1]
        operations.append(
            {
                "type": "discharge",
                "ambient_temperature": 24.0 + battery_offset,
                "time": np.array([2026, 1, cycle, 0, 0, 0], dtype=float),
                "data": {
                    "Voltage_measured": voltage,
                    "Current_measured": current,
                    "Temperature_measured": temperature,
                    "Time": elapsed,
                    "Capacity": 2.0 - 0.005 * cycle - 0.002 * battery_offset,
                },
            }
        )
        operations.append(
            {
                "type": "charge",
                "ambient_temperature": 24.0 + battery_offset,
                "time": np.array([2026, 1, cycle, 1, 0, 0], dtype=float),
                "data": {
                    "Voltage_measured": np.linspace(3.0, 4.2, 21),
                    "Current_measured": np.ones(21),
                    "Temperature_measured": temperature,
                    "Time": elapsed,
                },
            }
        )
    savemat(path, {battery_id: {"cycle": np.array(operations, dtype=object)}})


def _write_cohort(directory: Path, *, batteries: int = 5, cycles: int = 15) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for index in range(batteries):
        battery_id = f"B{index + 5:04d}"
        _write_battery_mat(
            directory / f"{battery_id}.mat",
            battery_id,
            cycles=cycles,
        )


def _write_archive_and_receipt(
    source: Path,
    root: Path,
    *,
    nested: bool = False,
    source_url: str = OFFICIAL_ARCHIVE_URL,
) -> tuple[Path, Path]:
    outer = root / "5_Battery_Data_Set.zip"
    if nested:
        inner = root / "BatteryAgingARC-FY08Q4.zip"
        with zipfile.ZipFile(
            inner, "w", compression=zipfile.ZIP_DEFLATED
        ) as archive:
            for path in sorted(source.glob("*.mat")):
                archive.write(
                    path,
                    arcname=f"BatteryAgingARC-FY08Q4/{path.name}",
                )
        with zipfile.ZipFile(
            outer, "w", compression=zipfile.ZIP_DEFLATED
        ) as archive:
            archive.write(inner, arcname=inner.name)
    else:
        with zipfile.ZipFile(
            outer, "w", compression=zipfile.ZIP_DEFLATED
        ) as archive:
            for path in sorted(source.glob("*.mat")):
                archive.write(path, arcname=path.name)
    receipt = root / "retrieval_receipt.json"
    receipt.write_text(
        json.dumps(
            {
                "source_url": source_url,
                "retrieved_at": "2026-08-01T00:00:00Z",
                "archive_sha256": hashlib.sha256(outer.read_bytes()).hexdigest(),
            }
        ),
        encoding="utf-8",
    )
    return outer, receipt


def _load_imported(output: Path) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    cycle_summary = pd.read_csv(output / "nasa_pcoe_cycle_summary.csv")
    raw_signal = pd.read_csv(output / "nasa_pcoe_raw_signal.csv")
    provenance = json.loads(
        (output / "nasa_pcoe_raw_signal_provenance.json").read_text(
            encoding="utf-8"
        )
    )
    return cycle_summary, raw_signal, provenance


def test_nasa_importer_writes_official_receipt_admission_ready_contracts(
    tmp_path: Path,
) -> None:
    source = tmp_path / "mat"
    _write_cohort(source)
    archive, receipt = _write_archive_and_receipt(source, tmp_path)
    output = tmp_path / "imported"

    manifest = import_nasa_pcoe_battery(
        input_path=archive,
        output_dir=output,
        retrieval_receipt_path=receipt,
    )

    assert manifest["battery_count"] == 5
    assert manifest["discharge_cycle_count"] == 75
    assert manifest["raw_point_count"] == 1575
    assert manifest["retrieval_receipt_verified"] is True
    cycle_summary, raw_signal, provenance = _load_imported(output)
    assert cycle_summary.groupby("battery_id")["cycle_index"].min().eq(1).all()
    assert cycle_summary.groupby("battery_id")["cycle_index"].max().eq(15).all()
    assert raw_signal["step_type"].eq("discharge").all()
    assert raw_signal["capacity_ah"].ge(0).all()
    assert raw_signal["global_time_s"].notna().all()
    assert provenance["source_sha256"] == file_sha256(
        output / "nasa_pcoe_raw_signal.csv"
    )
    assert provenance["transformation"]["no_interpolation"] is True
    assert provenance["transformation"]["no_smoothing"] is True

    admission = audit_raw_signal_admission(
        cycle_summary=cycle_summary,
        raw_signal=raw_signal,
        provenance=provenance,
        raw_sha256=file_sha256(output / "nasa_pcoe_raw_signal.csv"),
        group_column="battery_id",
        cycle_column="cycle_index",
    )
    assert admission["admitted_for_predictive_comparison"] is True
    assert admission["source_retrieval_verification_status"] == (
        "nasa_import_official_receipt_verified"
    )
    assert admission["covered_battery_fraction"] == pytest.approx(1.0)
    assert admission["covered_cycle_fraction"] == pytest.approx(1.0)


def test_nasa_importer_verifies_nested_zip_retrieval_receipt(
    tmp_path: Path,
) -> None:
    source = tmp_path / "mat"
    _write_cohort(source)
    outer, receipt = _write_archive_and_receipt(source, tmp_path, nested=True)
    output = tmp_path / "imported"
    manifest = import_nasa_pcoe_battery(
        input_path=outer,
        output_dir=output,
        retrieval_receipt_path=receipt,
    )
    assert manifest["retrieval_receipt_verified"] is True
    _, _, provenance = _load_imported(output)
    assert provenance["source_identifier"] == OFFICIAL_ARCHIVE_URL
    inventory = pd.read_csv(output / "nasa_pcoe_source_inventory.csv")
    assert inventory["source_location"].str.contains("!").all()


def test_nasa_importer_rejects_receipt_checksum_mismatch(tmp_path: Path) -> None:
    source = tmp_path / "mat"
    _write_cohort(source, batteries=1)
    archive_path, receipt = _write_archive_and_receipt(source, tmp_path)
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    payload["archive_sha256"] = "0" * 64
    receipt.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="archive_sha256"):
        import_nasa_pcoe_battery(
            input_path=archive_path,
            output_dir=tmp_path / "output",
            retrieval_receipt_path=receipt,
        )


def test_nasa_importer_rejects_ambiguous_battery_identity(
    tmp_path: Path,
) -> None:
    source = tmp_path / "B0005.mat"
    _write_battery_mat(source, "B0006")
    with pytest.raises(ValueError, match="battery identity is ambiguous"):
        import_nasa_pcoe_battery(
            input_path=source,
            output_dir=tmp_path / "output",
            retrieved_at="2026-08-01T00:00:00Z",
        )


def test_nasa_importer_rejects_mismatched_signal_lengths(
    tmp_path: Path,
) -> None:
    source = tmp_path / "B0005.mat"
    _write_battery_mat(source, "B0005", malformed_cycle=2)
    with pytest.raises(ValueError, match="lengths must match"):
        import_nasa_pcoe_battery(
            input_path=source,
            output_dir=tmp_path / "output",
            retrieved_at="2026-08-01T00:00:00Z",
        )


def test_official_receipt_signals_enter_predictive_comparison(
    tmp_path: Path,
) -> None:
    source = tmp_path / "mat"
    _write_cohort(source, batteries=5, cycles=15)
    archive, receipt = _write_archive_and_receipt(source, tmp_path)
    imported = tmp_path / "imported"
    import_nasa_pcoe_battery(
        input_path=archive,
        output_dir=imported,
        retrieval_receipt_path=receipt,
    )

    analysis = tmp_path / "analysis"
    manifest = run_battery_intelligence(
        cycle_summary_path=imported / "nasa_pcoe_cycle_summary.csv",
        raw_signal_path=imported / "nasa_pcoe_raw_signal.csv",
        raw_signal_provenance_path=(
            imported / "nasa_pcoe_raw_signal_provenance.json"
        ),
        output_dir=analysis,
        config=BatteryIntelligenceConfig(
            n_splits=5,
            knee_bootstrap_samples=0,
        ),
    )

    assert manifest["raw_signal_admission"][
        "admitted_for_predictive_comparison"
    ] is True
    assert manifest["signal_feature_comparison"] is not None
    assert (analysis / "reports" / "signal_feature_comparison.json").is_file()
    assert (
        analysis / "tables" / "forecast_feature_table_capacity_only.csv"
    ).is_file()


def test_user_declared_local_import_is_diagnostic_only(tmp_path: Path) -> None:
    source = tmp_path / "mat"
    _write_cohort(source, batteries=5, cycles=15)
    imported = tmp_path / "imported"
    import_nasa_pcoe_battery(
        input_path=source,
        output_dir=imported,
        retrieved_at="2026-08-01T00:00:00Z",
    )
    cycle_summary, raw_signal, provenance = _load_imported(imported)
    admission = audit_raw_signal_admission(
        cycle_summary=cycle_summary,
        raw_signal=raw_signal,
        provenance=provenance,
        raw_sha256=file_sha256(imported / "nasa_pcoe_raw_signal.csv"),
        group_column="battery_id",
        cycle_column="cycle_index",
    )
    assert admission["admitted_for_predictive_comparison"] is False
    assert admission["status"] == "not_admitted_unverified_source_retrieval"
    assert admission["source_retrieval_verification_status"] == (
        "nasa_import_receipt_missing"
    )


def test_nonofficial_receipt_is_not_predictively_admitted(tmp_path: Path) -> None:
    source = tmp_path / "mat"
    _write_cohort(source, batteries=5, cycles=15)
    archive, receipt = _write_archive_and_receipt(
        source,
        tmp_path,
        source_url="https://example.invalid/nasa-battery.zip",
    )
    imported = tmp_path / "imported"
    import_nasa_pcoe_battery(
        input_path=archive,
        output_dir=imported,
        retrieval_receipt_path=receipt,
    )
    cycle_summary, raw_signal, provenance = _load_imported(imported)
    admission = audit_raw_signal_admission(
        cycle_summary=cycle_summary,
        raw_signal=raw_signal,
        provenance=provenance,
        raw_sha256=file_sha256(imported / "nasa_pcoe_raw_signal.csv"),
        group_column="battery_id",
        cycle_column="cycle_index",
    )
    assert admission["admitted_for_predictive_comparison"] is False
    assert admission["source_retrieval_verification_status"] == (
        "nasa_import_receipt_not_official_archive"
    )


def test_source_provenance_columns_are_not_forecast_features(
    tmp_path: Path,
) -> None:
    source = tmp_path / "mat"
    _write_cohort(source)
    imported = tmp_path / "imported"
    import_nasa_pcoe_battery(
        input_path=source,
        output_dir=imported,
        retrieved_at="2026-08-01T00:00:00Z",
    )
    analysis = tmp_path / "analysis"
    manifest = run_battery_intelligence(
        cycle_summary_path=imported / "nasa_pcoe_cycle_summary.csv",
        output_dir=analysis,
        config=BatteryIntelligenceConfig(
            n_splits=5,
            knee_bootstrap_samples=0,
        ),
    )
    feature_columns = manifest["validation_summary"]["feature_columns"]
    assert not any(column.startswith("source_") for column in feature_columns)


def test_nasa_importer_preserves_nonempty_output_by_default(
    tmp_path: Path,
) -> None:
    source = tmp_path / "mat"
    _write_cohort(source, batteries=1)
    output = tmp_path / "output"
    import_nasa_pcoe_battery(
        input_path=source,
        output_dir=output,
        retrieved_at="2026-08-01T00:00:00Z",
    )
    with pytest.raises(FileExistsError, match="non-empty"):
        import_nasa_pcoe_battery(
            input_path=source,
            output_dir=output,
            retrieved_at="2026-08-01T00:00:00Z",
        )
