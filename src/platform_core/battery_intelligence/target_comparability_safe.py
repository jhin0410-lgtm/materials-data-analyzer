"""Semantic guard for battery target-comparability diagnostics.

``current_target`` in the forecast table means the configured target value
observed at the forecast origin. It is not electrical current. The original
audit accidentally listed it beside ambient temperature, voltage, and discharge
duration, producing a misleading ``median_observed_current_target`` field.

This wrapper keeps the existing audit implementation and artifact contract while
restricting observed-condition profiles to physical measurement fields. Actual
current is represented by ``current_abs_max_a`` when admitted raw-signal features
are available.
"""
from __future__ import annotations

from pathlib import Path
from threading import RLock
from typing import Any

import pandas as pd

from . import target_comparability as _base
from .common import BatteryIntelligenceConfig

_LOCK = RLock()
_PHYSICAL_CONDITION_COLUMNS = (
    "ambient_temperature_c",
    "current_abs_max_a",
    "discharge_duration_s",
    "voltage_min_v",
    "voltage_max_v",
    "temperature_min_c",
    "temperature_max_c",
    "temperature_span_c",
)


def _run_with_physical_conditions(function: Any, *args: Any, **kwargs: Any) -> Any:
    with _LOCK:
        original = _base._CONDITION_COLUMNS
        _base._CONDITION_COLUMNS = _PHYSICAL_CONDITION_COLUMNS
        try:
            return function(*args, **kwargs)
        finally:
            _base._CONDITION_COLUMNS = original


def build_target_comparability_audit(
    *,
    cycle_summary: pd.DataFrame,
    forecast_table: pd.DataFrame,
    predictions: pd.DataFrame,
    config: BatteryIntelligenceConfig,
) -> dict[str, Any]:
    """Build the audit without misclassifying the origin target as current."""
    result = _run_with_physical_conditions(
        _base.build_target_comparability_audit,
        cycle_summary=cycle_summary,
        forecast_table=forecast_table,
        predictions=predictions,
        config=config,
    )
    result["summary"]["condition_semantics"] = {
        "origin_target_field": "origin_target_value/current_target",
        "origin_target_source_column": config.target_column,
        "origin_target_is_electrical_current": False,
        "electrical_current_condition_field": "current_abs_max_a",
        "legacy_median_observed_current_target_emitted": False,
    }
    return result


def audit_battery_intelligence_run(output_dir: str | Path) -> dict[str, Any]:
    """Audit an existing run using only physical observed-condition fields."""
    return _run_with_physical_conditions(
        _base.audit_battery_intelligence_run,
        output_dir,
    )
