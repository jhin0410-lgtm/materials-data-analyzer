"""Strict generic reliability outcome-label tests."""

from __future__ import annotations

import pandas as pd

from analyzers.reliability import calculate_reliability_summary, normalize_failed_series


def _metric(summary: pd.DataFrame, name: str) -> object:
    return summary.loc[summary["metric"] == name, "value"].iloc[0]


def test_nonbinary_numeric_failure_codes_are_not_silently_coerced() -> None:
    normalized = normalize_failed_series(pd.Series([0, 1, -1, 2, 0.5, "pass", "fail"]))

    assert normalized.iloc[0] == 0.0
    assert normalized.iloc[1] == 1.0
    assert normalized.iloc[5] == 0.0
    assert normalized.iloc[6] == 1.0
    assert normalized.iloc[2:5].isna().all()


def test_reliability_summary_reports_invalid_failure_codes() -> None:
    summary = calculate_reliability_summary(pd.DataFrame({"failed": [0, 1, 2, -1]}))

    assert int(_metric(summary, "invalid_failed_code_count")) == 2
    assert int(_metric(summary, "valid_failed_count")) == 2
