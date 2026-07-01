"""Tests for SPC calculation helpers."""

from __future__ import annotations

import pandas as pd
import pytest

from analyzers.spc import calculate_process_capability, calculate_spc_summary


def value_for_metric(df: pd.DataFrame, metric: str) -> float:
    """Read one metric value from a long-format metric table."""
    return float(df.loc[df["metric"] == metric, "value"].iloc[0])


def test_calculate_spc_summary_control_limits() -> None:
    spc_df = pd.DataFrame(
        {
            "temperature_c": [10.0, 12.0, 13.0, 15.0],
            "moving_range": [None, 2.0, 1.0, 2.0],
        }
    )

    summary = calculate_spc_summary(spc_df, "temperature_c")

    expected_mr_bar = 5.0 / 3.0
    expected_sigma = expected_mr_bar / 1.128
    expected_center = 12.5

    assert summary["center_line"] == pytest.approx(expected_center)
    assert summary["mr_bar"] == pytest.approx(expected_mr_bar)
    assert summary["sigma_estimate"] == pytest.approx(expected_sigma)
    assert summary["i_ucl"] == pytest.approx(expected_center + 3 * expected_sigma)
    assert summary["i_lcl"] == pytest.approx(expected_center - 3 * expected_sigma)


def test_calculate_process_capability_cp_cpk() -> None:
    capability = calculate_process_capability(
        lsl=5.0,
        usl=15.0,
        mean_value=10.0,
        sigma_estimate=1.0,
    )

    assert value_for_metric(capability, "cp") == pytest.approx(10.0 / 6.0)
    assert value_for_metric(capability, "cpk") == pytest.approx(5.0 / 3.0)


def test_calculate_process_capability_rejects_invalid_spec_limits() -> None:
    with pytest.raises(ValueError):
        calculate_process_capability(
            lsl=10.0,
            usl=10.0,
            mean_value=10.0,
            sigma_estimate=1.0,
        )
