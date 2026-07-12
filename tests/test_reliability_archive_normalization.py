"""Tests for Reliability v1.5.3 archive normalization helpers."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd

from connectors.reliability import list_zip_members
from loaders.reliability import (
    build_full_archive_inventory,
    normalize_backblaze_daily_frame,
    select_valid_daily_members,
)
from reliability_full_year_fixtures import write_synthetic_backblaze_zip


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "build_reliability_v1_5_full_year.py"


def _load_script_module():
    spec = importlib.util.spec_from_file_location("reliability_v15_full_year", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_full_archive_inventory_excludes_macos_and_malformed_members(tmp_path: Path) -> None:
    zip_path = write_synthetic_backblaze_zip(tmp_path / "sample.zip")
    inventory = build_full_archive_inventory(list_zip_members(zip_path))

    valid_members = select_valid_daily_members(inventory)
    excluded = inventory[inventory["inclusion_status"] == "excluded"]

    assert valid_members == [
        "2013/2020-01-01.csv",
        "2013/2020-01-02.csv",
        "2013/2020-01-03.csv",
    ]
    assert {"macos_metadata", "hidden_file", "malformed_filename"}.issubset(
        set(excluded["member_type"])
    )
    assert inventory.loc[inventory["valid_daily_csv"], "duplicate_date_status"].eq(
        "unique_date"
    ).all()


def test_schema_drift_summary_detects_single_compatible_signature(tmp_path: Path) -> None:
    module = _load_script_module()
    zip_path = write_synthetic_backblaze_zip(tmp_path / "sample.zip")
    inventory = build_full_archive_inventory(list_zip_members(zip_path))
    valid_members = select_valid_daily_members(inventory)

    schema, extra = module.build_schema_drift_summary(zip_path, inventory, valid_members)

    assert len(schema) == 1
    assert schema.loc[0, "member_count"] == 3
    assert schema.loc[0, "compatibility_status"] == "compatible"
    assert all(status == "compatible" for status in extra["member_schema_status"].values())


def test_normalize_backblaze_daily_frame_preserves_source_provenance() -> None:
    frame = pd.DataFrame(
        {
            "date": ["2020-01-01"],
            "serial_number": ["A"],
            "model": ["M1"],
            "capacity_bytes": [100],
            "failure": [0],
            "smart_5_raw": [1],
        }
    )

    normalized = normalize_backblaze_daily_frame(
        frame,
        source_member="2013/2020-01-01.csv",
        source_order_start=10,
    )

    assert normalized.loc[0, "source_member"] == "2013/2020-01-01.csv"
    assert normalized.loc[0, "source_row_index"] == 0
    assert normalized.loc[0, "source_order_index"] == 10
    assert normalized.loc[0, "event_indicator"] == 0
