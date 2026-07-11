"""Tests for Smart Factory v1.4.3 temporal and split feasibility audits."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "build_smart_factory_v1_4_analysis_ready.py"
TEMPORAL_SUMMARY_PATH = (
    PROJECT_ROOT / "data" / "processed" / "smart_factory_v1_4_temporal_summary.csv"
)
SPLIT_FEASIBILITY_PATH = (
    PROJECT_ROOT / "data" / "processed" / "smart_factory_v1_4_split_feasibility.csv"
)


def _load_script_module():
    spec = importlib.util.spec_from_file_location("smart_factory_v14_temporal", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _small_temporal_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "sample_index": range(8),
            "source_order_index": range(8),
            "chronological_rank": range(8),
            "observation_timestamp": pd.to_datetime(
                [
                    "2020-01-01 00:00:00",
                    "2020-01-01 00:00:00",
                    "2020-01-01 01:00:00",
                    "2020-01-01 02:00:00",
                    "2020-01-02 00:00:00",
                    "2020-01-02 01:00:00",
                    "2020-01-03 00:00:00",
                    "2020-01-03 01:00:00",
                ]
            ),
            "target_failure": [0, 0, 0, 0, 0, 1, 0, 0],
            "process_feature_000": range(8),
        }
    )


def test_temporal_summary_counts_duplicate_timestamps() -> None:
    module = _load_script_module()

    summary = module.build_temporal_summary(_small_temporal_df()).set_index("metric")

    assert int(summary.loc["duplicate_timestamp_count", "value"]) == 2
    assert summary.loc["source_order_monotonicity", "value"] in {True, "True"}


def test_split_feasibility_marks_too_few_failures_not_feasible() -> None:
    module = _load_script_module()
    thresholds = {
        "min_train_rows": 2,
        "min_test_rows": 2,
        "min_train_failures": 1,
        "min_test_failures": 2,
    }

    splits = module.build_split_feasibility(_small_temporal_df(), thresholds)

    assert "not_feasible" in set(splits["feasibility_status"])
    assert splits["infeasibility_reason"].str.contains("too_few_test_failures").any()


def test_generated_temporal_summary_records_no_parse_failures_and_duplicate_count() -> None:
    summary = pd.read_csv(TEMPORAL_SUMMARY_PATH).set_index("metric")

    assert int(summary.loc["timestamp_parse_failure_count", "value"]) == 0
    assert int(summary.loc["duplicate_timestamp_count", "value"]) == 65


def test_generated_split_feasibility_has_no_future_to_past_leakage() -> None:
    splits = pd.read_csv(SPLIT_FEASIBILITY_PATH)

    assert set(splits["leakage_status"]) == {"no_future_to_past"}
    assert {"feasible", "not_feasible"}.issuperset(set(splits["feasibility_status"]))
