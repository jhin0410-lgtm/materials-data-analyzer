"""Trajectory-rate and knee-candidate diagnostics."""
from __future__ import annotations
import math
from typing import Any, Iterable
import numpy as np
import pandas as pd
from .common import BatteryIntelligenceConfig


def _linear_fit(x: np.ndarray, y: np.ndarray) -> tuple[float, float, np.ndarray, float]:
    design = np.column_stack([x, np.ones_like(x)])
    coefficients, *_ = np.linalg.lstsq(design, y, rcond=None)
    slope, intercept = coefficients
    fitted = design @ coefficients
    sse = float(np.sum((y - fitted) ** 2))
    return float(slope), float(intercept), fitted, sse


def _best_piecewise_fit(
    x: np.ndarray,
    y: np.ndarray,
    min_segment: int,
) -> dict[str, Any] | None:
    if len(x) < 2 * min_segment:
        return None
    _, _, single_fitted, single_sse = _linear_fit(x, y)
    best: dict[str, Any] | None = None
    for split in range(min_segment, len(x) - min_segment + 1):
        before = _linear_fit(x[:split], y[:split])
        after = _linear_fit(x[split:], y[split:])
        combined_sse = before[3] + after[3]
        if best is None or combined_sse < best["piecewise_sse"]:
            fitted = np.concatenate([before[2], after[2]])
            best = {
                "split_index": split,
                "knee_cycle": float(x[split]),
                "slope_before": before[0],
                "slope_after": after[0],
                "piecewise_sse": float(combined_sse),
                "single_sse": float(single_sse),
                "single_fitted": single_fitted,
                "piecewise_fitted": fitted,
            }
    if best is None:
        return None
    denominator = max(best["single_sse"], np.finfo(float).eps)
    best["sse_improvement_percent"] = float(
        100.0 * (best["single_sse"] - best["piecewise_sse"]) / denominator
    )
    return best


def detect_knee_point(
    cycle: Iterable[float],
    target: Iterable[float],
    *,
    min_segment: int = 5,
    bootstrap_samples: int = 200,
    random_seed: int = 42,
) -> dict[str, Any]:
    x = np.asarray(list(cycle), dtype=float)
    y = np.asarray(list(target), dtype=float)
    valid = np.isfinite(x) & np.isfinite(y)
    x = x[valid]
    y = y[valid]
    order = np.argsort(x, kind="mergesort")
    x = x[order]
    y = y[order]
    if len(x) < 2 * min_segment:
        return {
            "status": "insufficient_points",
            "point_count": int(len(x)),
            "knee_cycle": None,
            "knee_ci_low": None,
            "knee_ci_high": None,
        }

    best = _best_piecewise_fit(x, y, min_segment)
    if best is None:
        return {
            "status": "not_detected",
            "point_count": int(len(x)),
            "knee_cycle": None,
            "knee_ci_low": None,
            "knee_ci_high": None,
        }

    sensitivity_candidates: list[float] = []
    for candidate_min in sorted(
        {max(3, min_segment - 2), min_segment, min_segment + 2}
    ):
        candidate = _best_piecewise_fit(x, y, candidate_min)
        if candidate is not None:
            sensitivity_candidates.append(float(candidate["knee_cycle"]))

    rng = np.random.default_rng(random_seed)
    residuals = y - best["piecewise_fitted"]
    bootstrap_knees: list[float] = []
    for _ in range(bootstrap_samples):
        synthetic = best["piecewise_fitted"] + rng.choice(
            residuals, size=len(residuals), replace=True
        )
        estimate = _best_piecewise_fit(x, synthetic, min_segment)
        if estimate is not None:
            bootstrap_knees.append(float(estimate["knee_cycle"]))

    if bootstrap_knees:
        ci_low, ci_high = np.quantile(bootstrap_knees, [0.05, 0.95])
    else:
        ci_low = ci_high = math.nan

    acceleration = best["slope_after"] < best["slope_before"]
    meaningful_fit = best["sse_improvement_percent"] >= 10.0
    status = "candidate" if acceleration and meaningful_fit else "weak_candidate"
    return {
        "status": status,
        "point_count": int(len(x)),
        "knee_cycle": float(best["knee_cycle"]),
        "knee_ci_low": float(ci_low) if math.isfinite(ci_low) else None,
        "knee_ci_high": float(ci_high) if math.isfinite(ci_high) else None,
        "slope_before_percent_per_cycle": float(best["slope_before"]),
        "slope_after_percent_per_cycle": float(best["slope_after"]),
        "sse_improvement_percent": float(best["sse_improvement_percent"]),
        "sensitivity_cycle_span": (
            float(np.ptp(sensitivity_candidates)) if sensitivity_candidates else None
        ),
        "bootstrap_success_count": int(len(bootstrap_knees)),
    }


def analyze_trajectories(
    cycle_summary: pd.DataFrame,
    config: BatteryIntelligenceConfig,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    diagnostics: list[dict[str, Any]] = []
    points: list[pd.DataFrame] = []
    for battery_id, group in cycle_summary.groupby(config.group_column, sort=True):
        ordered = group.sort_values(config.cycle_column, kind="mergesort").copy()
        cycles = ordered[config.cycle_column].to_numpy(dtype=float)
        target = ordered[config.target_column].to_numpy(dtype=float)
        rolling = pd.Series(target).rolling(
            window=config.rolling_window,
            min_periods=config.rolling_window,
        )
        rolling_slope = rolling.apply(
            lambda values: _linear_fit(
                np.arange(len(values), dtype=float), np.asarray(values, dtype=float)
            )[0],
            raw=False,
        )
        ordered["rolling_degradation_rate_percent_per_cycle"] = rolling_slope.to_numpy()
        points.append(
            ordered[
                [
                    config.group_column,
                    config.cycle_column,
                    config.target_column,
                    "rolling_degradation_rate_percent_per_cycle",
                ]
            ]
        )

        if len(ordered) < config.minimum_trajectory_points:
            knee = {
                "status": "insufficient_points",
                "point_count": int(len(ordered)),
                "knee_cycle": None,
                "knee_ci_low": None,
                "knee_ci_high": None,
            }
        else:
            knee = detect_knee_point(
                cycles,
                target,
                min_segment=config.knee_min_segment,
                bootstrap_samples=config.knee_bootstrap_samples,
                random_seed=config.random_seed,
            )
        overall_slope = _linear_fit(cycles, target)[0] if len(cycles) >= 2 else math.nan
        diagnostics.append(
            {
                config.group_column: battery_id,
                "trajectory_point_count": int(len(ordered)),
                "first_cycle": float(cycles[0]),
                "last_cycle": float(cycles[-1]),
                "first_target": float(target[0]),
                "last_target": float(target[-1]),
                "overall_slope_percent_per_cycle": float(overall_slope),
                "minimum_target": float(np.min(target)),
                "maximum_target": float(np.max(target)),
                **knee,
            }
        )
    return pd.DataFrame(diagnostics), pd.concat(points, ignore_index=True)


def _rolling_slope(values: np.ndarray) -> float:
    if len(values) < 2 or not np.isfinite(values).all():
        return math.nan
    x = np.arange(len(values), dtype=float)
    return _linear_fit(x, values.astype(float))[0]
