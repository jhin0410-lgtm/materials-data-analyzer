"""Tests for Battery Archive connector skeleton."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
import zipfile

import pandas as pd
import pytest

from connectors.battery_archive_connector import (
    BATTERY_ARCHIVE_INVENTORY_COLUMNS,
    BatteryArchiveConnector,
    build_cycle_file_inventory,
    discover_cycle_files,
    enrich_cycle_file_inventory,
    parse_battery_archive_filename,
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


def test_battery_archive_filename_parser_handles_clear_observed_pattern() -> None:
    metadata = parse_battery_archive_filename(
        zip_file="CALCE.zip",
        internal_csv_path=(
            "CALCE/CALCE_CX2-16_prism_LCO_25C_0-100_0.5-0.5C_a_cycle_data.csv"
        ),
    )

    assert metadata["filename_stem"] == "CALCE_CX2-16_prism_LCO_25C_0-100_0.5-0.5C_a"
    assert metadata["source"] == "CALCE"
    assert metadata["cell_id"] == "CALCE_CX2-16"
    assert metadata["chemistry"] == "LCO"
    assert metadata["form_factor"] == "prism"
    assert metadata["temperature_C"] == 25.0
    assert metadata["soc_min_pct"] == 0.0
    assert metadata["soc_max_pct"] == 100.0
    assert metadata["soc_window"] == "0-100"
    assert metadata["charge_c_rate"] == 0.5
    assert metadata["discharge_c_rate"] == 0.5
    assert metadata["metadata_parse_status"] == "parsed"


def test_battery_archive_filename_parser_keeps_ambiguous_cell_unknown() -> None:
    metadata = parse_battery_archive_filename(
        zip_file="SNL LFP.zip",
        internal_csv_path="SNL LFP/SNL_18650_LFP_15C_0-100_0.5-1C_a_cycle_data.csv",
    )

    assert metadata["source"] == "SNL LFP"
    assert metadata["cell_id"] == "unknown"
    assert metadata["chemistry"] == "LFP"
    assert metadata["form_factor"] == "18650"
    assert metadata["temperature_C"] == 15.0
    assert metadata["charge_c_rate"] == 0.5
    assert metadata["discharge_c_rate"] == 1.0
    assert metadata["metadata_parse_status"] == "partially_parsed"
    assert "cell_id" in metadata["metadata_parse_message"]


def test_battery_archive_filename_parser_handles_negative_temperature() -> None:
    metadata = parse_battery_archive_filename(
        zip_file="Michigan Expansion.zip",
        internal_csv_path=(
            "Michigan Expansion/"
            "MICH_02C_pouch_NMC_-5C_0-100_0.2-0.2C_cycle_data.csv"
        ),
    )

    assert metadata["cell_id"] == "MICH_02C"
    assert metadata["temperature_C"] == -5.0
    assert metadata["chemistry"] == "NMC"


def test_battery_archive_filename_parser_handles_soc_variants_and_c_over_rate() -> None:
    metadata = parse_battery_archive_filename(
        zip_file="synthetic.zip",
        internal_csv_path="NestedSource/placeholder.csv",
        file_name="CELL_A_pouch_NMC_T25_SOC20-80_C/2-1C_cycle_data.csv",
    )

    assert metadata["source"] == "NestedSource"
    assert metadata["cell_id"] == "CELL_A"
    assert metadata["temperature_C"] == 25.0
    assert metadata["soc_min_pct"] == 20.0
    assert metadata["soc_max_pct"] == 80.0
    assert metadata["soc_window"] == "20-80"
    assert metadata["charge_c_rate"] == 0.5
    assert metadata["discharge_c_rate"] == 1.0
    assert metadata["metadata_parse_status"] == "parsed"


def test_battery_archive_filename_parser_does_not_confuse_temperature_and_c_rate() -> None:
    metadata = parse_battery_archive_filename(
        zip_file="synthetic.zip",
        internal_csv_path="Src/CELL_B_pouch_NCA_25C_0-100_1C_cycle_data.csv",
    )

    assert metadata["temperature_C"] == 25.0
    assert pd.isna(metadata["charge_c_rate"])
    assert pd.isna(metadata["discharge_c_rate"])
    assert "single C-rate token" in metadata["metadata_parse_message"]


def test_battery_archive_filename_parser_uses_unknown_for_ambiguous_chemistry() -> None:
    metadata = parse_battery_archive_filename(
        zip_file="synthetic.zip",
        internal_csv_path="Src/CELL_C_pouch_XYZ_25C_20_80SOC_0.5-1C_cycle_data.csv",
    )

    assert metadata["chemistry"] == "unknown"
    assert metadata["soc_min_pct"] == 20.0
    assert metadata["soc_max_pct"] == 80.0
    assert metadata["metadata_parse_status"] == "partially_parsed"
    assert "chemistry" in metadata["metadata_parse_message"]


def test_battery_archive_filename_parser_marks_unknown_filename_unparsed() -> None:
    metadata = parse_battery_archive_filename(
        zip_file="unknown.zip",
        internal_csv_path="Src/unknown_cycle_data.csv",
    )

    assert metadata["metadata_parse_status"] == "unparsed"
    assert metadata["chemistry"] == "unknown"
    assert pd.isna(metadata["temperature_C"])


def test_battery_archive_enrichment_preserves_columns_ordering_and_rows() -> None:
    inventory_df = pd.DataFrame(
        {
            "zip_file": ["B.zip", "A.zip"],
            "internal_csv_path": [
                "SrcB/CELL_B_pouch_NMC_25C_0-100_0.5-1C_cycle_data.csv",
                "SrcA/CELL_A_pouch_LFP_25C_0-100_0.5-0.5C_cycle_data.csv",
            ],
            "file_name": [
                "CELL_B_pouch_NMC_25C_0-100_0.5-1C_cycle_data.csv",
                "CELL_A_pouch_LFP_25C_0-100_0.5-0.5C_cycle_data.csv",
            ],
            "file_type": ["cycle_data", "cycle_data"],
            "uncompressed_size_bytes": [10, 20],
            "compressed_size_bytes": [8, 16],
            "crc32": ["00000001", "00000002"],
            "extra_column": ["keep_b", "keep_a"],
        }
    )

    enriched_df = enrich_cycle_file_inventory(inventory_df)

    assert len(enriched_df) == len(inventory_df)
    assert enriched_df["zip_file"].tolist() == ["A.zip", "B.zip"]
    assert "extra_column" in enriched_df.columns
    assert enriched_df["extra_column"].tolist() == ["keep_a", "keep_b"]
    assert {"filename_stem", "metadata_parse_status", "protocol_label"}.issubset(
        enriched_df.columns
    )


def test_battery_archive_enrichment_requires_inventory_columns() -> None:
    inventory_df = pd.DataFrame({"zip_file": ["A.zip"]})

    with pytest.raises(ValueError, match="missing required column"):
        enrich_cycle_file_inventory(inventory_df)


def test_battery_archive_enrichment_script_creates_output_csv(tmp_path) -> None:
    input_path = tmp_path / "inventory.csv"
    output_path = tmp_path / "enriched.csv"
    pd.DataFrame(
        {
            "zip_file": ["A.zip"],
            "internal_csv_path": [
                "SrcA/CELL_A_pouch_LFP_25C_0-100_0.5-0.5C_cycle_data.csv"
            ],
            "file_name": ["CELL_A_pouch_LFP_25C_0-100_0.5-0.5C_cycle_data.csv"],
            "file_type": ["cycle_data"],
            "uncompressed_size_bytes": [10],
            "compressed_size_bytes": [8],
            "crc32": ["00000001"],
        }
    ).to_csv(input_path, index=False)

    result = subprocess.run(
        [
            sys.executable,
            "scripts/enrich_battery_archive_cycle_inventory.py",
            "--input",
            str(input_path),
            "--output",
            str(output_path),
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=True,
    )
    output_df = pd.read_csv(output_path)

    assert output_path.exists()
    assert len(output_df) == 1
    assert output_df.loc[0, "metadata_parse_status"] == "parsed"
    assert "total rows: 1" in result.stdout
