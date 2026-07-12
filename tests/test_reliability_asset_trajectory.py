"""Tests for Reliability v1.5.3 asset trajectory audits."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from connectors.reliability import list_zip_members
from loaders.reliability import build_full_archive_inventory, select_valid_daily_members
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


def _aggregates(tmp_path: Path):
    module = _load_script_module()
    zip_path = write_synthetic_backblaze_zip(tmp_path / "sample.zip")
    inventory = build_full_archive_inventory(list_zip_members(zip_path))
    valid_members = select_valid_daily_members(inventory)
    return module, module.first_pass_collect(zip_path, valid_members)


def test_first_pass_collects_asset_counts_and_duplicate_asset_dates(tmp_path: Path) -> None:
    module, aggregates = _aggregates(tmp_path)
    trajectory = module.build_trajectory_summary(aggregates).iloc[0]

    assert trajectory["total_assets"] == 6
    assert trajectory["multi_observation_asset_count"] == 4
    assert trajectory["duplicate_asset_date_count"] == 2
    assert trajectory["inconsistent_model_asset_count"] == 1


def test_source_archive_is_not_modified_by_first_pass(tmp_path: Path) -> None:
    module = _load_script_module()
    zip_path = write_synthetic_backblaze_zip(tmp_path / "sample.zip")
    before = zip_path.stat().st_size
    inventory = build_full_archive_inventory(list_zip_members(zip_path))
    module.first_pass_collect(zip_path, select_valid_daily_members(inventory))

    assert zip_path.stat().st_size == before
