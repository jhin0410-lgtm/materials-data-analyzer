"""Tests for Smart Factory v1.4 readiness summary semantics."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
READINESS_SUMMARY_PATH = (
    PROJECT_ROOT / "data" / "processed" / "smart_factory_v1_4_readiness_summary.csv"
)


def test_readiness_summary_has_required_checks() -> None:
    readiness = pd.read_csv(READINESS_SUMMARY_PATH)

    required_checks = {
        "row_count",
        "feature_count",
        "target_availability",
        "target_imbalance",
        "missingness",
        "timestamp_parseability",
        "timestamp_duplicate_count",
        "source_order_timestamp_monotonicity",
        "chronological_ordering",
        "explicit_group_ids",
        "derived_group_proxies",
        "duplicate_risk",
        "group_split_feasibility",
        "time_split_feasibility",
        "combined_validation_feasibility",
        "spc_readiness",
        "capability_readiness",
        "drift_readiness",
        "anomaly_readiness",
    }

    assert required_checks.issubset(set(readiness["check"]))


def test_readiness_summary_does_not_overclaim_secom() -> None:
    readiness = pd.read_csv(READINESS_SUMMARY_PATH).set_index("check")

    assert readiness.loc["overall_readiness", "status"] == "conditionally_ready"
    assert readiness.loc["explicit_group_ids", "status"] == "not_ready"
    assert readiness.loc["combined_validation_feasibility", "status"] == "not_ready"
    assert readiness.loc["timestamp_duplicate_count", "status"] in {
        "ready",
        "conditionally_ready",
    }
    assert readiness.loc["source_order_timestamp_monotonicity", "value"] in {
        "True",
        "False",
    }
    assert "must not be calculated" in readiness.loc["capability_readiness", "note"]


def test_readiness_summary_contains_no_absolute_paths_or_credentials() -> None:
    text = READINESS_SUMMARY_PATH.read_text(encoding="utf-8")

    assert "KAGGLE_KEY" not in text
    assert "KAGGLE_USERNAME" not in text
    assert "C:\\" not in text
    assert "/Users/" not in text
    assert "/home/" not in text
