"""Raw voltage/current/temperature feature extraction."""
from __future__ import annotations
import math
from typing import Any, Sequence
import numpy as np
import pandas as pd
from .common import _quality_flag, validate_raw_signal


def _integrate_abs(values: np.ndarray, times_s: np.ndarray, divisor: float) -> float:
    if len(values) < 2:
        return math.nan
    increments = np.diff(times_s)
    trapezoids = 0.5 * (np.abs(values[:-1]) + np.abs(values[1:])) * increments
    return float(np.sum(trapezoids) / divisor)


def _moving_average(values: np.ndarray, window: int) -> np.ndarray:
    if window <= 1:
        return values.astype(float, copy=True)
    if len(values) < window:
        return np.full_like(values, np.nan, dtype=float)
    series = pd.Series(values, dtype=float)
    return series.rolling(window=window, center=True, min_periods=window).mean().to_numpy()


def _incremental_capacity_features(
    cycle: pd.DataFrame,
    windows: Sequence[int] = (5, 9, 15),
) -> tuple[dict[str, float], list[str]]:
    features: dict[str, float] = {
        "dqdv_peak_height_ah_per_v": math.nan,
        "dqdv_peak_voltage_v": math.nan,
        "dvdq_median_v_per_ah": math.nan,
        "dqdv_peak_voltage_sensitivity_v": math.nan,
        "dqdv_peak_height_relative_sensitivity": math.nan,
    }
    warnings: list[str] = []
    if "capacity_ah" not in cycle.columns:
        return features, ["capacity_signal_unavailable"]

    discharge = cycle[cycle["step_type"] == "discharge"].copy()
    if len(discharge) < max(windows) + 2:
        return features, ["insufficient_discharge_points_for_incremental_capacity"]

    voltage = discharge["voltage_v"].to_numpy(dtype=float)
    capacity = discharge["capacity_ah"].to_numpy(dtype=float)
    order = np.argsort(voltage, kind="mergesort")
    voltage = voltage[order]
    capacity = capacity[order]

    aggregated = (
        pd.DataFrame({"voltage": voltage, "capacity": capacity})
        .groupby("voltage", as_index=False, sort=True)["capacity"]
        .mean()
    )
    voltage = aggregated["voltage"].to_numpy(dtype=float)
    capacity = aggregated["capacity"].to_numpy(dtype=float)
    if len(voltage) < max(windows) + 2 or np.ptp(voltage) <= 0:
        return features, ["insufficient_unique_voltage_support"]

    peak_voltages: list[float] = []
    peak_heights: list[float] = []
    median_dvdq: list[float] = []
    for window in windows:
        smoothed_capacity = _moving_average(capacity, window)
        valid = np.isfinite(smoothed_capacity)
        if valid.sum() < 5:
            continue
        v = voltage[valid]
        q = smoothed_capacity[valid]
        with np.errstate(divide="ignore", invalid="ignore"):
            dqdv = np.gradient(q, v)
            dvdq = np.gradient(v, q)
        finite_dqdv = np.isfinite(dqdv)
        finite_dvdq = np.isfinite(dvdq)
        if finite_dqdv.sum() < 3:
            continue
        absolute = np.abs(dqdv[finite_dqdv])
        peak_position = int(np.argmax(absolute))
        finite_v = v[finite_dqdv]
        peak_voltages.append(float(finite_v[peak_position]))
        peak_heights.append(float(absolute[peak_position]))
        if finite_dvdq.any():
            median_dvdq.append(float(np.nanmedian(np.abs(dvdq[finite_dvdq]))))

    if not peak_voltages:
        return features, ["incremental_capacity_derivative_unstable"]

    features["dqdv_peak_voltage_v"] = float(np.median(peak_voltages))
    features["dqdv_peak_height_ah_per_v"] = float(np.median(peak_heights))
    if median_dvdq:
        features["dvdq_median_v_per_ah"] = float(np.median(median_dvdq))
    features["dqdv_peak_voltage_sensitivity_v"] = float(np.ptp(peak_voltages))
    median_height = float(np.median(peak_heights))
    features["dqdv_peak_height_relative_sensitivity"] = (
        float(np.ptp(peak_heights) / median_height) if median_height > 0 else math.nan
    )
    if features["dqdv_peak_voltage_sensitivity_v"] > 0.05:
        warnings.append("incremental_capacity_peak_location_sensitive_to_smoothing")
    if (
        math.isfinite(features["dqdv_peak_height_relative_sensitivity"])
        and features["dqdv_peak_height_relative_sensitivity"] > 0.5
    ):
        warnings.append("incremental_capacity_peak_height_sensitive_to_smoothing")
    return features, warnings


def extract_signal_features(
    raw_signal: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    validated, validation_flags, _ = validate_raw_signal(raw_signal)
    feature_rows: list[dict[str, Any]] = []
    feature_flags: list[dict[str, Any]] = []

    for (battery_id, cycle_index), cycle in validated.groupby(
        ["battery_id", "cycle_index"], sort=True
    ):
        row: dict[str, Any] = {
            "battery_id": battery_id,
            "cycle_index": cycle_index,
            "signal_point_count": int(len(cycle)),
            "signal_step_count": int(cycle["step_type"].nunique()),
            "voltage_min_v": float(cycle["voltage_v"].min()),
            "voltage_max_v": float(cycle["voltage_v"].max()),
            "current_abs_max_a": float(cycle["current_a"].abs().max()),
        }
        total_duration = 0.0
        charge_ah = 0.0
        discharge_ah = 0.0
        charge_wh = 0.0
        discharge_wh = 0.0
        charge_duration = 0.0
        discharge_duration = 0.0
        cc_duration = 0.0
        cv_duration = 0.0

        for step_type, step in cycle.groupby("step_type", sort=True):
            times = step["elapsed_time_s"].to_numpy(dtype=float)
            currents = step["current_a"].to_numpy(dtype=float)
            voltage = step["voltage_v"].to_numpy(dtype=float)
            duration = float(times[-1] - times[0]) if len(times) >= 2 else 0.0
            total_duration += duration
            throughput_ah = _integrate_abs(currents, times, 3600.0)
            energy_wh = _integrate_abs(currents * voltage, times, 3600.0)
            if step_type in {"charge", "charge_cc", "charge_cv"}:
                charge_duration += duration
                if math.isfinite(throughput_ah):
                    charge_ah += throughput_ah
                if math.isfinite(energy_wh):
                    charge_wh += energy_wh
            if step_type == "discharge":
                discharge_duration += duration
                if math.isfinite(throughput_ah):
                    discharge_ah += throughput_ah
                if math.isfinite(energy_wh):
                    discharge_wh += energy_wh
            if step_type == "charge_cc":
                cc_duration += duration
            if step_type == "charge_cv":
                cv_duration += duration

        row.update(
            {
                "signal_duration_s": total_duration,
                "charge_duration_s": charge_duration,
                "discharge_duration_s": discharge_duration,
                "charge_cc_duration_s": cc_duration,
                "charge_cv_duration_s": cv_duration,
                "charge_throughput_ah": charge_ah if charge_duration > 0 else math.nan,
                "discharge_throughput_ah": (
                    discharge_ah if discharge_duration > 0 else math.nan
                ),
                "charge_energy_wh": charge_wh if charge_duration > 0 else math.nan,
                "discharge_energy_wh": (
                    discharge_wh if discharge_duration > 0 else math.nan
                ),
                "coulombic_efficiency": (
                    discharge_ah / charge_ah if charge_ah > 0 else math.nan
                ),
                "energy_efficiency": (
                    discharge_wh / charge_wh if charge_wh > 0 else math.nan
                ),
                "cv_fraction_of_charge_time": (
                    cv_duration / charge_duration if charge_duration > 0 else math.nan
                ),
            }
        )

        if "temperature_c" in cycle.columns:
            temperature = cycle["temperature_c"].to_numpy(dtype=float)
            row["temperature_min_c"] = float(np.min(temperature))
            row["temperature_max_c"] = float(np.max(temperature))
            row["temperature_span_c"] = float(np.ptp(temperature))
            if "global_time_s" in cycle.columns:
                chronological = cycle.sort_values("global_time_s", kind="mergesort")
                chronological_temperature = chronological["temperature_c"].to_numpy(dtype=float)
                row["temperature_rise_c"] = float(
                    np.max(chronological_temperature) - chronological_temperature[0]
                )
            else:
                row["temperature_rise_c"] = math.nan
                _quality_flag(
                    feature_flags,
                    severity="info",
                    code="temperature_rise_requires_global_time",
                    message="Temperature span was computed, but rise from cycle start requires optional global_time_s.",
                    battery_id=battery_id,
                    cycle_index=cycle_index,
                )
        else:
            row["temperature_min_c"] = math.nan
            row["temperature_max_c"] = math.nan
            row["temperature_span_c"] = math.nan
            row["temperature_rise_c"] = math.nan

        resistance_candidates: list[float] = []
        for _, step in cycle.groupby("step_type", sort=True):
            current = step["current_a"].to_numpy(dtype=float)
            voltage = step["voltage_v"].to_numpy(dtype=float)
            if len(step) < 2:
                continue
            delta_current = np.diff(current)
            delta_voltage = np.diff(voltage)
            threshold = max(0.05, 0.05 * np.max(np.abs(current)))
            transition = np.abs(delta_current) >= threshold
            values = np.abs(delta_voltage[transition] / delta_current[transition])
            values = values[np.isfinite(values) & (values > 0)]
            resistance_candidates.extend(values.tolist())
        resistance_values = np.asarray(resistance_candidates, dtype=float)
        row["resistance_transition_proxy_ohm"] = (
            float(np.median(resistance_values)) if len(resistance_values) else math.nan
        )

        ic_features, warnings = _incremental_capacity_features(cycle)
        row.update(ic_features)
        for warning in warnings:
            _quality_flag(
                feature_flags,
                severity="warning",
                code=warning,
                message="Incremental-capacity result is sensitive or unavailable; no mechanism claim is supported.",
                battery_id=battery_id,
                cycle_index=cycle_index,
            )

        if math.isfinite(row["coulombic_efficiency"]) and not (
            0.0 <= row["coulombic_efficiency"] <= 1.2
        ):
            _quality_flag(
                feature_flags,
                severity="warning",
                code="coulombic_efficiency_outside_diagnostic_range",
                message="Integrated charge/discharge throughput gives an implausible efficiency; verify sign convention, step labels, and time units.",
                battery_id=battery_id,
                cycle_index=cycle_index,
                field="coulombic_efficiency",
                value=row["coulombic_efficiency"],
            )
        if math.isfinite(row["energy_efficiency"]) and not (
            0.0 <= row["energy_efficiency"] <= 1.2
        ):
            _quality_flag(
                feature_flags,
                severity="warning",
                code="energy_efficiency_outside_diagnostic_range",
                message="Integrated energy gives an implausible efficiency; verify step labels and units.",
                battery_id=battery_id,
                cycle_index=cycle_index,
                field="energy_efficiency",
                value=row["energy_efficiency"],
            )
        feature_rows.append(row)

    flags = pd.concat(
        [validation_flags, pd.DataFrame(feature_flags)], ignore_index=True, sort=False
    )
    return pd.DataFrame(feature_rows), flags
