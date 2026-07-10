"""Tests for Battery Archive cycle normalization."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
import zipfile

import pandas as pd
import pytest

from loaders.battery_archive_cycle_loader import (
    NORMALIZED_CYCLE_COLUMNS,
    build_cycle_column_mapping,
    build_cycle_schema_audit_tables,
    load_battery_archive_cycle_data,
)

_METADATA_COLUMNS = [
    "source",
    "cell_id",
    "chemistry",
    "form_factor",
    "temperature_C",
    "soc_min_pct",
    "soc_max_pct",
    "soc_window",
    "charge_c_rate",
    "discharge_c_rate",
    "protocol_label",
    "zip_file",
    "internal_csv_path",
    "file_name",
]


def _write_zip(zip_path: Path, entries: dict[str, str | bytes]) -> None:
    with zipfile.ZipFile(zip_path, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)


def _metadata_inventory(rows: list[dict[str, object]]) -> pd.DataFrame:
    base_metadata = {
        "source": "Synthetic",
        "cell_id": "CELL_A",
        "chemistry": "NMC",
        "form_factor": "pouch",
        "temperature_C": 25.0,
        "soc_min_pct": 0.0,
        "soc_max_pct": 100.0,
        "soc_window": "0-100",
        "charge_c_rate": 0.5,
        "discharge_c_rate": 1.0,
        "protocol_label": "NMC|pouch|25C|0-100|0.5-1C",
    }
    records = [{**base_metadata, **row} for row in rows]
    return pd.DataFrame(records, columns=_METADATA_COLUMNS)


def _build_synthetic_audit(raw_dir: Path, inventory_df: pd.DataFrame):
    return build_cycle_schema_audit_tables(raw_dir, inventory_df, sample_rows=10)


def test_two_synthetic_schemas_normalize_to_same_canonical_columns(tmp_path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    _write_zip(
        raw_dir / "A.zip",
        {
            "with_time_cycle_data.csv": (
                "Cycle_Index,Start_Time,End_Time,Test_Time (s),Min_Current (A),"
                "Max_Current (A),Min_Voltage (V),Max_Voltage (V),"
                "Charge_Capacity (Ah),Discharge_Capacity (Ah),"
                "Charge_Energy (Wh),Discharge_Energy (Wh)\n"
                "1,2020-01-01,2020-01-01,10,-1,2,3.0,4.2,1.1,1.0,4.1,3.9\n"
            ),
            "no_time_cycle_data.csv": (
                "Cycle_Index,Test_Time (s),Min_Current (A),Max_Current (A),"
                "Min_Voltage (V),Max_Voltage (V),Charge_Capacity (Ah),"
                "Discharge_Capacity (Ah),Charge_Energy (Wh),Discharge_Energy (Wh)\n"
                "1,11,-1,2,3.0,4.2,1.2,1.1,4.2,4.0\n"
            ),
        },
    )
    inventory_df = _metadata_inventory(
        [
            {
                "zip_file": "A.zip",
                "internal_csv_path": "with_time_cycle_data.csv",
                "file_name": "with_time_cycle_data.csv",
                "cell_id": "CELL_A",
            },
            {
                "zip_file": "A.zip",
                "internal_csv_path": "no_time_cycle_data.csv",
                "file_name": "no_time_cycle_data.csv",
                "cell_id": "CELL_B",
            },
        ]
    )
    schema_df, column_df = _build_synthetic_audit(raw_dir, inventory_df)

    normalized_df, summary_df, mapping_df = load_battery_archive_cycle_data(
        raw_dir,
        inventory_df,
        schema_df,
        column_df,
    )

    assert list(normalized_df.columns) == NORMALIZED_CYCLE_COLUMNS
    assert len(normalized_df) == 2
    assert summary_df["load_status"].tolist() == ["success", "success"]
    assert normalized_df["source_row_number"].tolist() == [1, 1]
    with_time = normalized_df.loc[
        normalized_df["file_name"] == "with_time_cycle_data.csv"
    ].iloc[0]
    no_time = normalized_df.loc[
        normalized_df["file_name"] == "no_time_cycle_data.csv"
    ].iloc[0]
    assert with_time["date_or_timestamp"] == "2020-01-01"
    assert pd.isna(no_time["date_or_timestamp"])
    assert with_time["charge_capacity"] == 1.1
    assert no_time["discharge_energy"] == 4.0
    assert with_time["charge_capacity_unit"] == "Ah"
    assert with_time["discharge_energy_unit"] == "Wh"
    assert {"start_time", "cycle_index", "charge_capacity"}.issubset(
        set(mapping_df["canonical_column_name"])
    )


def test_normalization_records_invalid_numeric_and_blank_rows(tmp_path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    _write_zip(
        raw_dir / "A.zip",
        {
            "bad_values_cycle_data.csv": (
                "Cycle_Index,Test_Time (s),Min_Current (A),Max_Current (A),"
                "Min_Voltage (V),Max_Voltage (V),Charge_Capacity (Ah),"
                "Discharge_Capacity (Ah),Charge_Energy (Wh),Discharge_Energy (Wh)\n"
                "1,10,-1,2,3,4,bad,1.0,4.1,3.9\n"
                ",,,,,,,,,\n"
                "bad_cycle,11,-1,2,3,4,1.1,also_bad,4.2,nope\n"
            ),
        },
    )
    inventory_df = _metadata_inventory(
        [
            {
                "zip_file": "A.zip",
                "internal_csv_path": "bad_values_cycle_data.csv",
                "file_name": "bad_values_cycle_data.csv",
            }
        ]
    )
    schema_df, column_df = _build_synthetic_audit(raw_dir, inventory_df)

    normalized_df, summary_df, _ = load_battery_archive_cycle_data(
        raw_dir,
        inventory_df,
        schema_df,
        column_df,
    )

    summary = summary_df.iloc[0]
    assert summary["raw_row_count"] == 3
    assert summary["normalized_row_count"] == 2
    assert summary["dropped_blank_row_count"] == 1
    assert summary["invalid_cycle_index_count"] == 1
    assert summary["invalid_charge_capacity_count"] == 1
    assert summary["invalid_discharge_capacity_count"] == 1
    assert summary["invalid_discharge_energy_count"] == 1
    assert summary["load_status"] == "success_with_warnings"
    assert pd.isna(normalized_df.loc[0, "charge_capacity"])
    assert pd.isna(normalized_df.loc[1, "cycle_index"])


def test_normalization_handles_raw_column_order_by_mapping_contract(tmp_path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    _write_zip(
        raw_dir / "A.zip",
        {
            "reordered_cycle_data.csv": (
                "Discharge_Energy (Wh),Charge_Energy (Wh),Discharge_Capacity (Ah),"
                "Charge_Capacity (Ah),Max_Voltage (V),Min_Voltage (V),"
                "Max_Current (A),Min_Current (A),Test_Time (s),Cycle_Index\n"
                "3.9,4.1,1.0,1.1,4.2,3.0,2,-1,10,1\n"
            )
        },
    )
    inventory_df = _metadata_inventory(
        [
            {
                "zip_file": "A.zip",
                "internal_csv_path": "reordered_cycle_data.csv",
                "file_name": "reordered_cycle_data.csv",
            }
        ]
    )
    schema_df, column_df = _build_synthetic_audit(raw_dir, inventory_df)

    normalized_df, summary_df, _ = load_battery_archive_cycle_data(
        raw_dir,
        inventory_df,
        schema_df,
        column_df,
    )

    assert summary_df.loc[0, "load_status"] == "success"
    assert normalized_df.loc[0, "cycle_index"] == 1
    assert normalized_df.loc[0, "charge_capacity"] == 1.1
    assert normalized_df.loc[0, "discharge_energy"] == 3.9


def test_normalization_records_missing_metadata_key(tmp_path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    _write_zip(raw_dir / "A.zip", {"a_cycle_data.csv": "Cycle_Index\n1\n"})
    schema_inventory = pd.DataFrame(
        {
            "zip_file": ["A.zip"],
            "internal_csv_path": ["a_cycle_data.csv"],
            "file_name": ["a_cycle_data.csv"],
            "schema_fingerprint": ["schema_unknown"],
            "column_count": [1],
            "raw_columns": ['["Cycle_Index"]'],
            "normalized_columns": ['["cycle_index"]'],
            "sample_row_count": [1],
            "encoding_used": ["utf-8-sig"],
            "delimiter_used": [","],
            "empty_file": [False],
            "read_status": ["success"],
            "read_message": [""],
        }
    )
    column_inventory = pd.DataFrame(
        {
            "zip_file": ["A.zip"],
            "internal_csv_path": ["a_cycle_data.csv"],
            "file_name": ["a_cycle_data.csv"],
            "schema_fingerprint": ["schema_unknown"],
            "raw_column_name": ["Cycle_Index"],
            "normalized_column_name": ["cycle_index"],
            "column_position": [1],
            "sample_inferred_dtype": ["int64"],
            "sample_non_null_count": [1],
            "sample_null_count": [0],
            "sample_values": ['["1"]'],
            "unit_candidate": ["unknown"],
            "mapping_candidate": ["cycle_index"],
            "mapping_confidence": ["high"],
            "mapping_note": ["explicit cycle index/name"],
        }
    )
    inventory_df = _metadata_inventory([])

    normalized_df, summary_df, _ = load_battery_archive_cycle_data(
        raw_dir,
        inventory_df,
        schema_inventory,
        column_inventory,
    )

    assert normalized_df.empty
    assert summary_df.loc[0, "load_status"] == "load_error"
    assert summary_df.loc[0, "metadata_join_status"] == "missing"


def test_normalization_rejects_duplicate_inventory_keys(tmp_path) -> None:
    inventory_df = _metadata_inventory(
        [
            {
                "zip_file": "A.zip",
                "internal_csv_path": "a_cycle_data.csv",
                "file_name": "a_cycle_data.csv",
            },
            {
                "zip_file": "A.zip",
                "internal_csv_path": "a_cycle_data.csv",
                "file_name": "a_cycle_data.csv",
            },
        ]
    )

    with pytest.raises(ValueError, match="duplicate"):
        load_battery_archive_cycle_data(
            tmp_path,
            inventory_df,
            pd.DataFrame(),
            pd.DataFrame(),
        )


def test_normalization_records_unknown_schema_as_load_error(tmp_path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    _write_zip(raw_dir / "A.zip", {"a_cycle_data.csv": "Cycle_Index\n1\n"})
    inventory_df = _metadata_inventory(
        [
            {
                "zip_file": "A.zip",
                "internal_csv_path": "a_cycle_data.csv",
                "file_name": "a_cycle_data.csv",
            }
        ]
    )
    schema_df, column_df = _build_synthetic_audit(raw_dir, inventory_df)
    schema_df.loc[0, "schema_fingerprint"] = "schema_not_in_mapping"

    normalized_df, summary_df, _ = load_battery_archive_cycle_data(
        raw_dir,
        inventory_df,
        schema_df,
        column_df,
    )

    assert normalized_df.empty
    assert summary_df.loc[0, "load_status"] == "load_error"
    assert "schema mapping" in summary_df.loc[0, "load_message"]


def test_normalization_script_creates_csv_outputs(tmp_path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    _write_zip(
        raw_dir / "A.zip",
        {
            "a_cycle_data.csv": (
                "Cycle_Index,Test_Time (s),Min_Current (A),Max_Current (A),"
                "Min_Voltage (V),Max_Voltage (V),Charge_Capacity (Ah),"
                "Discharge_Capacity (Ah),Charge_Energy (Wh),Discharge_Energy (Wh)\n"
                "1,10,-1,2,3,4,1.1,1.0,4.1,3.9\n"
            )
        },
    )
    inventory_df = _metadata_inventory(
        [
            {
                "zip_file": "A.zip",
                "internal_csv_path": "a_cycle_data.csv",
                "file_name": "a_cycle_data.csv",
            }
        ]
    )
    schema_df, column_df = _build_synthetic_audit(raw_dir, inventory_df)
    inventory_path = tmp_path / "inventory.csv"
    schema_path = tmp_path / "schema.csv"
    column_path = tmp_path / "columns.csv"
    normalized_output = tmp_path / "normalized.csv"
    summary_output = tmp_path / "summary.csv"
    mapping_output = tmp_path / "mapping.csv"
    inventory_df.to_csv(inventory_path, index=False)
    schema_df.to_csv(schema_path, index=False)
    column_df.to_csv(column_path, index=False)

    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_battery_archive_cycle_normalized.py",
            "--raw-dir",
            str(raw_dir),
            "--inventory",
            str(inventory_path),
            "--schema-inventory",
            str(schema_path),
            "--column-inventory",
            str(column_path),
            "--normalized-output",
            str(normalized_output),
            "--summary-output",
            str(summary_output),
            "--mapping-output",
            str(mapping_output),
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=True,
    )

    assert len(pd.read_csv(normalized_output)) == 1
    assert len(pd.read_csv(summary_output)) == 1
    assert not pd.read_csv(mapping_output).empty
    assert "normalized row count: 1" in result.stdout
    assert not (raw_dir / "a_cycle_data.csv").exists()
