"""Tests for Reliability v1.5.3 full-year audit summaries."""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

from connectors.reliability import list_zip_members
from loaders.reliability import build_full_archive_inventory, select_valid_daily_members
from reliability_full_year_fixtures import write_synthetic_backblaze_zip


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "build_reliability_v1_5_full_year.py"
CASE_DIR = PROJECT_ROOT / "data" / "case_studies" / "reliability"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"


def _load_script_module():
    spec = importlib.util.spec_from_file_location("reliability_v15_full_year", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _summary_parts(tmp_path: Path):
    module = _load_script_module()
    zip_path = write_synthetic_backblaze_zip(tmp_path / "sample.zip")
    inventory = build_full_archive_inventory(list_zip_members(zip_path))
    valid_members = select_valid_daily_members(inventory)
    schema, _ = module.build_schema_drift_summary(zip_path, inventory, valid_members)
    aggregates = module.first_pass_collect(zip_path, valid_members)
    trajectory = module.build_trajectory_summary(aggregates)
    event = module.build_event_integrity_summary(aggregates)
    censoring = module.build_censoring_summary(aggregates)
    temporal = module.build_temporal_coverage_summary(aggregates)
    smart = module.build_smart_feature_inventory(
        aggregates,
        total_rows=aggregates["total_rows"],
        valid_member_count=len(valid_members),
    )
    horizon = module.build_horizon_feasibility(aggregates)
    lookback = module.build_lookback_feasibility(aggregates)
    split = module.build_split_feasibility(aggregates)
    task, selected, recommended_horizon, recommended_lookback = module.build_task_readiness(
        horizon, lookback, split, event
    )
    readiness = module.build_full_readiness_summary(
        inventory=inventory,
        trajectory=trajectory,
        event=event,
        censoring=censoring,
        temporal=temporal,
        smart=smart,
        horizon=horizon,
        lookback=lookback,
        split=split,
        selected_primary_task=selected,
        recommended_horizon=recommended_horizon,
        recommended_lookback=recommended_lookback,
    )
    return module, zip_path, inventory, schema, readiness, task


def test_full_readiness_summary_is_machine_readable(tmp_path: Path) -> None:
    _, _, _, _, readiness, task = _summary_parts(tmp_path)

    assert readiness.loc[0, "total_valid_daily_files"] == 3
    assert readiness.loc[0, "total_rows"] == 12
    assert readiness.loc[0, "total_assets"] == 6
    assert "binary_horizon_failure" in set(task["task"])


def test_normalization_spec_and_manifest_have_no_absolute_paths(tmp_path: Path) -> None:
    module, zip_path, inventory, schema, readiness, _ = _summary_parts(tmp_path)
    spec = module.build_normalization_spec(
        timestamp="2026-01-01T00:00:00+00:00",
        archive_sha="abc",
        analysis_ready_output="data/processed/reliability_v1_5_backblaze_analysis_ready.csv",
    )
    manifest = module.build_full_year_manifest(
        timestamp="2026-01-01T00:00:00+00:00",
        archive_sha_before="abc",
        archive_sha_after="abc",
        inventory=inventory,
        schema=schema,
        readiness=readiness,
        analysis_ready_info={"analysis_ready_size_bytes": 123},
        processing_seconds=1.0,
    )
    text = json.dumps({"spec": spec, "manifest": manifest})

    assert manifest["source_unchanged"] is True
    assert spec["member_inclusion_policy"].startswith("Include only")
    assert not re.search(r"[A-Za-z]:\\\\", text)
    assert "/Users/" not in text
    assert "/home/" not in text
    assert "password=" not in text.lower()


def test_write_analysis_ready_creates_local_only_schema(tmp_path: Path) -> None:
    module = _load_script_module()
    zip_path = write_synthetic_backblaze_zip(tmp_path / "sample.zip")
    inventory = build_full_archive_inventory(list_zip_members(zip_path))
    valid_members = select_valid_daily_members(inventory)
    aggregates = module.first_pass_collect(zip_path, valid_members)
    output_path = tmp_path / "analysis_ready.csv"
    diagnostics_dir = tmp_path / "diagnostics"

    info = module.write_analysis_ready(zip_path, valid_members, aggregates, output_path, diagnostics_dir)

    assert info["rows_written"] == 12
    assert output_path.exists()
    assert (diagnostics_dir / "reliability_v1_5_event_anomalies.csv").exists()


def test_tracked_full_year_artifacts_parse_without_raw_archive() -> None:
    paths = [
        CASE_DIR / "normalization_spec_v1_5.json",
        CASE_DIR / "full_year_manifest_v1_5.json",
        PROCESSED_DIR / "reliability_v1_5_full_archive_inventory.csv",
        PROCESSED_DIR / "reliability_v1_5_schema_drift_summary.csv",
        PROCESSED_DIR / "reliability_v1_5_trajectory_summary.csv",
        PROCESSED_DIR / "reliability_v1_5_event_integrity_summary.csv",
        PROCESSED_DIR / "reliability_v1_5_censoring_summary.csv",
        PROCESSED_DIR / "reliability_v1_5_temporal_coverage_summary.csv",
        PROCESSED_DIR / "reliability_v1_5_smart_feature_inventory.csv",
        PROCESSED_DIR / "reliability_v1_5_full_leakage_audit.csv",
        PROCESSED_DIR / "reliability_v1_5_horizon_feasibility.csv",
        PROCESSED_DIR / "reliability_v1_5_lookback_feasibility.csv",
        PROCESSED_DIR / "reliability_v1_5_split_feasibility.csv",
        PROCESSED_DIR / "reliability_v1_5_full_readiness_summary.csv",
        PROCESSED_DIR / "reliability_v1_5_full_task_readiness.csv",
    ]
    if not all(path.exists() for path in paths):
        return

    json.loads((CASE_DIR / "normalization_spec_v1_5.json").read_text(encoding="utf-8"))
    manifest = json.loads((CASE_DIR / "full_year_manifest_v1_5.json").read_text(encoding="utf-8"))
    text = "\n".join(path.read_text(encoding="utf-8") for path in paths)

    assert manifest["source_unchanged"] is True
    assert manifest["readiness_conclusion"]["selected_primary_task"] == "binary_horizon_failure"
    assert not re.search(r"[A-Za-z]:\\\\", text)
    assert "/Users/" not in text
    assert "/home/" not in text
    assert "password=" not in text.lower()
    assert "secret=" not in text.lower()
    assert "token=" not in text.lower()
