"""Tests for Battery Archive connector skeleton."""

from __future__ import annotations

import zipfile

import pytest

from connectors.battery_archive_connector import (
    BATTERY_ARCHIVE_INVENTORY_COLUMNS,
    BatteryArchiveConnector,
    build_cycle_file_inventory,
    discover_cycle_files,
)


def test_battery_archive_missing_endpoint_returns_warning(monkeypatch) -> None:
    monkeypatch.delenv("BATTERY_ARCHIVE_ENDPOINT", raising=False)
    monkeypatch.delenv("BATTERY_ARCHIVE_BASE_URL", raising=False)

    result = BatteryArchiveConnector().probe(limit=5)

    assert result.source_name == "battery_archive"
    assert result.raw_paths == []
    assert result.processed_paths == []
    assert "endpoint is not configured" in result.warnings[0]


def _write_zip(zip_path, entries: dict[str, str]) -> None:
    with zipfile.ZipFile(zip_path, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)


def test_battery_archive_cycle_discovery_filters_cycle_data_entries(tmp_path) -> None:
    _write_zip(
        tmp_path / "B_source.zip",
        {
            "folder/": "",
            "folder/cell_b_timeseries.csv": "time,current\n0,1\n",
            "folder/cell_b_cycle_data.csv": "Cycle_Index,Discharge_Capacity (Ah)\n1,1.0\n",
            "folder/nested/cell_c_CYCLE_DATA.CSV": "Cycle_Index,Discharge_Capacity (Ah)\n1,1.1\n",
            "__MACOSX/folder/hidden_cycle_data.csv": "ignored\n",
            "folder/.hidden_cycle_data.csv": "ignored\n",
            "folder/._resource_cycle_data.csv": "ignored\n",
        },
    )
    _write_zip(
        tmp_path / "A_source.zip",
        {
            "alpha/cell_a_cycle_data.csv": "Cycle_Index,Discharge_Capacity (Ah)\n1,0.9\n",
            "alpha/cell_a_timeseries_data.csv": "time,current\n0,1\n",
        },
    )

    records = discover_cycle_files(tmp_path)
    inventory_df = build_cycle_file_inventory(tmp_path)

    assert [record["zip_file"] for record in records] == [
        "A_source.zip",
        "B_source.zip",
        "B_source.zip",
    ]
    assert inventory_df["internal_csv_path"].tolist() == [
        "alpha/cell_a_cycle_data.csv",
        "folder/cell_b_cycle_data.csv",
        "folder/nested/cell_c_CYCLE_DATA.CSV",
    ]
    assert list(inventory_df.columns) == BATTERY_ARCHIVE_INVENTORY_COLUMNS
    assert inventory_df["file_type"].unique().tolist() == ["cycle_data"]
    assert not inventory_df["internal_csv_path"].str.contains("timeseries").any()
    assert inventory_df.duplicated(["zip_file", "internal_csv_path"]).sum() == 0
    assert not (tmp_path / "folder").exists()
    assert not (tmp_path / "__MACOSX").exists()


def test_battery_archive_cycle_inventory_raises_when_no_zip_files(tmp_path) -> None:
    with pytest.raises(FileNotFoundError, match="No Battery Archive zip files"):
        build_cycle_file_inventory(tmp_path)


def test_battery_archive_cycle_inventory_raises_for_corrupt_zip(tmp_path) -> None:
    corrupt_zip = tmp_path / "corrupt.zip"
    corrupt_zip.write_text("not a zip file", encoding="utf-8")

    with pytest.raises(ValueError, match="corrupt.zip"):
        build_cycle_file_inventory(tmp_path)
