"""Origin-only battery forecast baselines.

All predictors in this module use only values available at the forecast origin.
They do not use the held-out battery's future observations, full-trajectory knee
location, or cross-battery fitted parameters.
"""
from __future__ import annotations

from typing import Any, Sequence

import numpy as np
import pandas as pd


BASELINE_DEFINITIONS: dict[str, str] = {
    "persistence": "Use the origin retention as the future prediction.",
    "trailing_mean": "Use the origin-only trailing retention mean.",
    "local_linear": "Extrapolate the trailing ordinary-least-squares slope.",
    "damped_trend": "Extrapolate one half of the trailing slope to limit instability.",
    "robust_trend": "Extrapolate the median pairwise slope across available lags.",
    "ewma_trend": "Extrapolate a recency-weighted linear slope across available lags.",
}


def _origin_target(row: pd.Series) -> float:
    if "origin_target_percent" in row and pd.notna(row["origin_target_percent"]):
        return float(row["origin_target_percent"])
    if "current_target" in row and pd.notna(row["current_target"]):
        return float(row["current_target"])
    raise ValueError(
        "forecast row missing origin_target_percent and legacy current_target"
    )


def _history_points(row: pd.Series, lags: Sequence[int]) -> tuple[np.ndarray, np.ndarray]:
    points: list[tuple[float, float]] = []
    for lag in sorted(lags, reverse=True):
        column = f"target_lag_{lag}"
        if column in row and pd.notna(row[column]):
            points.append((-float(lag), float(row[column])))
    points.append((0.0, _origin_target(row)))
    x = np.asarray([item[0] for item in points], dtype=float)
    y = np.asarray([item[1] for item in points], dtype=float)
    return x, y


def _median_pairwise_slope(x: np.ndarray, y: np.ndarray) -> float:
    slopes: list[float] = []
    for left in range(len(x) - 1):
        for right in range(left + 1, len(x)):
            delta_x = x[right] - x[left]
            if delta_x > 0:
                slopes.append(float((y[right] - y[left]) / delta_x))
    return float(np.median(slopes)) if slopes else 0.0


def _weighted_slope(x: np.ndarray, y: np.ndarray) -> float:
    if len(x) < 2:
        return 0.0
    age = x - np.min(x)
    weights = np.power(2.0, age / max(float(np.ptp(x)), 1.0))
    weight_sum = float(np.sum(weights))
    x_mean = float(np.sum(weights * x) / weight_sum)
    y_mean = float(np.sum(weights * y) / weight_sum)
    denominator = float(np.sum(weights * (x - x_mean) ** 2))
    if denominator <= np.finfo(float).eps:
        return 0.0
    return float(np.sum(weights * (x - x_mean) * (y - y_mean)) / denominator)


def build_baseline_predictions(
    forecast_table: pd.DataFrame,
    *,
    horizon: int,
    lags: Sequence[int],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Return deterministic origin-only predictions for transparent baselines."""
    required = {"target_rolling_mean", "target_rolling_slope"}
    missing = sorted(required - set(forecast_table.columns))
    if missing:
        raise ValueError("forecast table missing baseline columns: " + ", ".join(missing))
    if not {
        "origin_target_percent",
        "current_target",
    }.intersection(forecast_table.columns):
        raise ValueError(
            "forecast table missing origin_target_percent and legacy current_target"
        )

    rows: list[dict[str, float]] = []
    for _, row in forecast_table.iterrows():
        current = _origin_target(row)
        trailing_slope = float(row["target_rolling_slope"])
        history_x, history_y = _history_points(row, lags)
        robust_slope = _median_pairwise_slope(history_x, history_y)
        weighted_slope = _weighted_slope(history_x, history_y)
        rows.append(
            {
                "persistence_prediction": current,
                "trailing_mean_prediction": float(row["target_rolling_mean"]),
                "local_linear_prediction": current + horizon * trailing_slope,
                "damped_trend_prediction": current + horizon * 0.5 * trailing_slope,
                "robust_trend_prediction": current + horizon * robust_slope,
                "ewma_trend_prediction": current + horizon * weighted_slope,
            }
        )

    predictions = pd.DataFrame(rows, index=forecast_table.index)
    if not np.isfinite(predictions.to_numpy(dtype=float)).all():
        raise ValueError("baseline construction produced non-finite predictions")
    return predictions, {
        "baseline_names": list(BASELINE_DEFINITIONS),
        "definitions": BASELINE_DEFINITIONS,
        "origin_only": True,
        "origin_target_field": (
            "origin_target_percent"
            if "origin_target_percent" in forecast_table.columns
            else "current_target"
        ),
        "legacy_current_target_alias_is_electrical_current": False,
        "full_trajectory_knee_used": False,
        "silent_clipping": False,
    }
