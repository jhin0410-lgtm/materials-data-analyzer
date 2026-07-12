"""Tests for Reliability v1.5.3 horizon/lookback feasibility."""

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


def test_horizon_feasibility_excludes_post_event_rows_and_counts_positive_origin(
    tmp_path: Path,
) -> None:
    module, aggregates = _aggregates(tmp_path)
    horizon = module.build_horizon_feasibility(aggregates).set_index("horizon_days")

    assert horizon.loc[1, "positive_labels"] >= 1
    assert horizon.loc[1, "post_event_excluded_rows"] >= 2
    assert horizon.loc[1, "leakage_safe_constructibility"] in {True, "True"}


def test_lookback_feasibility_is_past_or_current_only(tmp_path: Path) -> None:
    module, aggregates = _aggregates(tmp_path)
    lookback = module.build_lookback_feasibility(aggregates)

    assert set(lookback["leakage_status"]) == {"past_or_current_observations_only"}
    assert "current_day_only" in set(lookback["lookback_window_days"].astype(str))


def test_full_leakage_audit_marks_lifetime_metadata_as_not_features() -> None:
    module = _load_script_module()
    leakage = module.build_full_leakage_audit().set_index("field_or_pattern")

    assert leakage.loc["days_to_last_observation", "status"] == "target_construction_only"
    assert leakage.loc["post_failure_rows", "status"] == "prohibited_feature"
    assert leakage.loc["serial_number", "status"] == "metadata_only"
