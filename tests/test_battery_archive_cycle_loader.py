"""Tests for Battery Archive cycle CSV schema audit loader."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
import zipfile

import pandas as pd
import pytest

from loaders.battery_archive_cycle_loader import (
    COLUMN_INVENTORY_COLUMNS,
    SCHEMA_INVENTORY_COLUMNS,
    build_cycle_schema_audit_tables,
    build_schema_fingerprint,
    infer_mapping_candidate,
    normalize_column_name,
)


def _write_zip(zip_path: Path, entries: dict[str, str | bytes]) -> None:
    with zipfile.ZipFile(zip_path, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)


def _inventory(rows: list[dict[str, object]]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def test_column_name_normalization_preserves_unit_tokens() -> None:
    assert normalize_column_name("Cycle Index") == "cycle_index"
    assert normalize_column_name("Discharge Capacity (Ah)") == "discharge_capacity_ah"
    assert normalize_column_name("Capacity/mAh") == "capacity_mah"


def test_schema_fingerprint_uses_ordered_normalized_columns() -> None:
    columns = ["cycle_index", "charge_capacity_ah", "discharge_capacity_ah"]
    same_order = ["cycle_index", "charge_capacity_ah", "discharge_capacity_ah"]
    different_order = ["cycle_index", "discharge_capacity_ah", "charge_capacity_ah"]

    assert build_schema_fingerprint(columns) == build_schema_fingerprint(same_order)
    assert build_schema_fingerprint(columns) != build_schema_fingerprint(different_order)


def test_mapping_candidates_are_conservative() -> None:
    assert infer_mapping_candidate("Cycle_Index", "cycle_index")[0] == "cycle_index"
    assert (
        infer_mapping_candidate(
            "Discharge_Capacity (Ah)",
            "discharge_capacity_ah",
        )[0]
        == "discharge_capacity"
    )
    assert infer_mapping_candidate("Capacity (mAh)", "capacity_mah") == (
        "unknown",
        "none",
        "capacity column is not explicitly charge/discharge",
    )


def test_cycle_schema_audit_reads_bounded_samples_and_preserves_columns(tmp_path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    _write_zip(
        raw_dir / "A.zip",
        {
            "nested/cell_a_cycle_data.csv": (
                "Cycle_Index,Charge_Capacity (Ah),Discharge_Capacity (Ah),"
                "Charge_Energy (Wh),Discharge_Energy (Wh)\n"
                "1,1.1,1.0,4.0,3.8\n"
                "2,1.0,0.9,3.9,3.6\n"
            ),
            "nested/cell_b_cycle_data.csv": (
                "Cycle_Index,Charge_Capacity (Ah),Discharge_Capacity (Ah),"
                "Charge_Energy (Wh),Discharge_Energy (Wh)\n"
                "1,1.2,1.1,4.1,3.9\n"
            ),
        },
    )
    inventory_df = _inventory(
        [
            {
                "zip_file": "A.zip",
                "internal_csv_path": "nested/cell_b_cycle_data.csv",
                "file_name": "cell_b_cycle_data.csv",
            },
            {
                "zip_file": "A.zip",
                "internal_csv_path": "nested/cell_a_cycle_data.csv",
                "file_name": "cell_a_cycle_data.csv",
            },
        ]
    )

    schema_df, column_df = build_cycle_schema_audit_tables(
        raw_dir,
        inventory_df,
        sample_rows=1,
    )

    assert list(schema_df.columns) == SCHEMA_INVENTORY_COLUMNS
    assert list(column_df.columns) == COLUMN_INVENTORY_COLUMNS
    assert schema_df["internal_csv_path"].tolist() == [
        "nested/cell_a_cycle_data.csv",
        "nested/cell_b_cycle_data.csv",
    ]
    assert schema_df["sample_row_count"].tolist() == [1, 1]
    assert schema_df["read_status"].tolist() == ["success", "success"]
    assert schema_df["schema_fingerprint"].nunique() == 1
    raw_columns = json.loads(schema_df.loc[0, "raw_columns"])
    normalized_columns = json.loads(schema_df.loc[0, "normalized_columns"])
    assert raw_columns[1] == "Charge_Capacity (Ah)"
    assert "discharge_capacity_ah" in normalized_columns
    assert set(column_df["mapping_candidate"]) >= {
        "cycle_index",
        "charge_capacity",
        "discharge_capacity",
        "charge_energy",
        "discharge_energy",
    }
    assert not (raw_dir / "nested").exists()


def test_cycle_schema_audit_distinguishes_column_order(tmp_path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    _write_zip(
        raw_dir / "A.zip",
        {
            "a_cycle_data.csv": "Cycle_Index,Charge_Capacity (Ah),Discharge_Capacity (Ah)\n1,1.1,1.0\n",
            "b_cycle_data.csv": "Cycle_Index,Discharge_Capacity (Ah),Charge_Capacity (Ah)\n1,1.0,1.1\n",
        },
    )
    inventory_df = _inventory(
        [
            {
                "zip_file": "A.zip",
                "internal_csv_path": "a_cycle_data.csv",
                "file_name": "a_cycle_data.csv",
            },
            {
                "zip_file": "A.zip",
                "internal_csv_path": "b_cycle_data.csv",
                "file_name": "b_cycle_data.csv",
            },
        ]
    )

    schema_df, _ = build_cycle_schema_audit_tables(raw_dir, inventory_df)

    assert schema_df["schema_fingerprint"].nunique() == 2


def test_cycle_schema_audit_handles_header_only_empty_and_read_error(tmp_path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    _write_zip(
        raw_dir / "A.zip",
        {
            "header_only_cycle_data.csv": "Cycle_Index,Discharge_Capacity (Ah)\n",
            "empty_cycle_data.csv": "",
            "invalid_cycle_data.csv": b"\xff\xfe\xff",
        },
    )
    inventory_df = _inventory(
        [
            {
                "zip_file": "A.zip",
                "internal_csv_path": "header_only_cycle_data.csv",
                "file_name": "header_only_cycle_data.csv",
            },
            {
                "zip_file": "A.zip",
                "internal_csv_path": "empty_cycle_data.csv",
                "file_name": "empty_cycle_data.csv",
            },
            {
                "zip_file": "A.zip",
                "internal_csv_path": "invalid_cycle_data.csv",
                "file_name": "invalid_cycle_data.csv",
            },
        ]
    )

    schema_df, column_df = build_cycle_schema_audit_tables(raw_dir, inventory_df)

    status_by_file = dict(zip(schema_df["file_name"], schema_df["read_status"]))
    assert status_by_file["header_only_cycle_data.csv"] == "header_only"
    assert status_by_file["empty_cycle_data.csv"] == "empty"
    assert status_by_file["invalid_cycle_data.csv"] == "read_error"
    assert "header_only_cycle_data.csv" in set(column_df["file_name"])
    assert "empty_cycle_data.csv" not in set(column_df["file_name"])


def test_cycle_schema_audit_records_missing_zip_and_member_errors(tmp_path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    _write_zip(raw_dir / "A.zip", {"present_cycle_data.csv": "Cycle_Index\n1\n"})
    inventory_df = _inventory(
        [
            {
                "zip_file": "A.zip",
                "internal_csv_path": "missing_cycle_data.csv",
                "file_name": "missing_cycle_data.csv",
            },
            {
                "zip_file": "missing.zip",
                "internal_csv_path": "present_cycle_data.csv",
                "file_name": "present_cycle_data.csv",
            },
        ]
    )

    schema_df, column_df = build_cycle_schema_audit_tables(raw_dir, inventory_df)

    assert schema_df["read_status"].tolist() == ["read_error", "read_error"]
    assert column_df.empty
    assert schema_df["read_message"].str.contains("not found").all()


def test_cycle_schema_audit_rejects_missing_required_inventory_columns(tmp_path) -> None:
    with pytest.raises(ValueError, match="missing required"):
        build_cycle_schema_audit_tables(tmp_path, pd.DataFrame({"zip_file": ["A.zip"]}))


def test_cycle_schema_audit_script_creates_outputs(tmp_path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    _write_zip(
        raw_dir / "A.zip",
        {
            "nested/cell_a_cycle_data.csv": (
                "Cycle_Index,Test_Time (s),Discharge_Capacity (Ah)\n"
                "1,10,1.0\n"
            )
        },
    )
    inventory_path = tmp_path / "inventory.csv"
    schema_output = tmp_path / "schema.csv"
    column_output = tmp_path / "columns.csv"
    report_output = tmp_path / "report.md"
    _inventory(
        [
            {
                "zip_file": "A.zip",
                "internal_csv_path": "nested/cell_a_cycle_data.csv",
                "file_name": "cell_a_cycle_data.csv",
            }
        ]
    ).to_csv(inventory_path, index=False)

    result = subprocess.run(
        [
            sys.executable,
            "scripts/audit_battery_archive_cycle_schemas.py",
            "--raw-dir",
            str(raw_dir),
            "--inventory",
            str(inventory_path),
            "--schema-output",
            str(schema_output),
            "--column-output",
            str(column_output),
            "--report-output",
            str(report_output),
            "--sample-rows",
            "1",
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=True,
    )

    schema_df = pd.read_csv(schema_output)
    column_df = pd.read_csv(column_output)
    assert len(schema_df) == 1
    assert len(column_df) == 3
    assert report_output.exists()
    assert "schema inventory rows: 1" in result.stdout
    assert "Battery Archive Cycle Schema Audit" in report_output.read_text(
        encoding="utf-8"
    )
