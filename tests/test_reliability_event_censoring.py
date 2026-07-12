"""Tests for Reliability v1.5.3 event and censoring audits."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from connectors.reliability import list_zip_members
from loaders.reliability import (
    build_full_archive_inventory,
    classify_post_failure_status,
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


def _aggregates(tmp_path: Path):
    module = _load_script_module()
    zip_path = write_synthetic_backblaze_zip(tmp_path / "sample.zip")
    inventory = build_full_archive_inventory(list_zip_members(zip_path))
    valid_members = select_valid_daily_members(inventory)
    return module, module.first_pass_collect(zip_path, valid_members)


def test_event_integrity_flags_post_failure_observations(tmp_path: Path) -> None:
    module, aggregates = _aggregates(tmp_path)
    event = module.build_event_integrity_summary(aggregates).iloc[0]

    assert event["failure_row_count"] == 1
    assert event["unique_failed_asset_count"] == 1
    assert event["failure_followed_by_later_observation_asset_count"] == 1
    assert event["repeated_event_asset_count"] == 0


def test_censoring_summary_uses_conservative_statuses(tmp_path: Path) -> None:
    module, aggregates = _aggregates(tmp_path)
    censoring = module.build_censoring_summary(aggregates)

    statuses = set(censoring["censoring_status"])
    assert "post_failure_inconsistent" in statuses
    assert "administrative_end_of_archive" in statuses
    assert "single_observation_unknown" in statuses


def test_post_failure_status_classification_keeps_same_day_failure_separate() -> None:
    assert (
        classify_post_failure_status("2020-01-01", 0, "2020-01-02")
        == "pre_failure_observation"
    )
    assert (
        classify_post_failure_status("2020-01-02", 1, "2020-01-02")
        == "failure_observation"
    )
    assert (
        classify_post_failure_status("2020-01-03", 0, "2020-01-02")
        == "post_failure_observation"
    )
