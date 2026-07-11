"""Tests for Smart Factory v1.4.3 analysis-ready audit helpers."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "build_smart_factory_v1_4_analysis_ready.py"
SPEC_PATH = (
    PROJECT_ROOT
    / "data"
    / "case_studies"
    / "smart_factory"
    / "normalization_spec_v1_4.json"
)
FEATURE_QUALITY_PATH = (
    PROJECT_ROOT / "data" / "processed" / "smart_factory_v1_4_feature_quality_inventory.csv"
)
INTEGRITY_PATH = (
    PROJECT_ROOT / "data" / "processed" / "smart_factory_v1_4_integrity_summary.csv"
)
ANALYSIS_READY_SUMMARY_PATH = (
    PROJECT_ROOT / "data" / "processed" / "smart_factory_v1_4_analysis_ready_summary.csv"
)


def _load_script_module():
    spec = importlib.util.spec_from_file_location("smart_factory_v14_analysis_ready", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _synthetic_aligned_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "sample_index": [0, 1, 2, 3],
            "source_timestamp_raw": [
                "01/01/2020 00:00:00",
                "01/01/2020 01:00:00",
                "01/01/2020 02:00:00",
                "01/01/2020 03:00:00",
            ],
            "observation_timestamp": pd.date_range("2020-01-01", periods=4, freq="h"),
            "source_order_index": [0, 1, 2, 3],
            "chronological_rank": [0, 1, 2, 3],
            "target_raw": [-1, 1, -1, 1],
            "target_pass_fail": [0, 1, 0, 1],
            "target_failure": [0, 1, 0, 1],
            "process_feature_000": [1.0, 2.0, 3.0, 4.0],
            "process_feature_001": [None, None, None, None],
            "process_feature_002": [5.0, 5.0, 5.0, 5.0],
            "process_feature_003": [9.0, 9.0, 9.0, 10.0],
            "process_feature_004": [1.0, 2.0, None, None],
        }
    )


def test_feature_quality_inventory_classifies_missing_constant_and_near_constant() -> None:
    module = _load_script_module()
    spec = module.load_json(SPEC_PATH)

    inventory = module.build_feature_quality_inventory(
        _synthetic_aligned_frame(),
        spec["feature_quality_thresholds"],
    ).set_index("feature_name")

    assert inventory.loc["process_feature_000", "readiness_category"] == "complete"
    assert inventory.loc["process_feature_001", "readiness_category"] == "all_missing"
    assert inventory.loc["process_feature_002", "readiness_category"] == "constant"
    assert inventory.loc["process_feature_004", "readiness_category"] == "high_missing"

    near_constant = module.build_feature_quality_inventory(
        pd.DataFrame({"process_feature_000": [1.0] * 99 + [2.0]}),
        spec["feature_quality_thresholds"],
    ).set_index("feature_name")
    assert near_constant.loc["process_feature_000", "readiness_category"] == "near_constant"


def test_integrity_summary_detects_conflicting_duplicate_targets(tmp_path: Path) -> None:
    module = _load_script_module()
    df = _synthetic_aligned_frame()
    df.loc[1, ["process_feature_000", "process_feature_003", "process_feature_004"]] = [
        1.0,
        9.0,
        1.0,
    ]
    df.loc[1, "process_feature_001"] = None
    df.loc[1, "process_feature_002"] = 5.0

    summary = module.build_integrity_summary(
        df,
        tmp_path / "row_level_duplicate_diagnostics.csv",
    ).set_index("check")

    assert int(summary.loc["duplicate_feature_rows_conflicting_target", "value"]) == 2
    assert summary.loc["duplicate_feature_rows_conflicting_target", "status"] == "not_ready"


def test_normalization_spec_has_local_only_analysis_ready_policy() -> None:
    spec = _load_script_module().load_json(SPEC_PATH)

    assert spec["local_output_paths"]["analysis_ready"].endswith(
        "smart_factory_v1_4_secom_analysis_ready.csv"
    )
    assert "analysis_ready" not in spec["tracked_output_paths"]


def test_analysis_ready_script_does_not_import_network_clients() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "urllib" not in source
    assert "requests" not in source
    assert "httpx" not in source


def test_tracked_analysis_ready_artifacts_exist_and_are_compact() -> None:
    feature_quality = pd.read_csv(FEATURE_QUALITY_PATH)
    integrity = pd.read_csv(INTEGRITY_PATH)
    summary = pd.read_csv(ANALYSIS_READY_SUMMARY_PATH)

    assert len(feature_quality) == 590
    assert not integrity.empty
    assert summary.set_index("metric").loc["source_sha_unchanged", "status"] == "ready"
