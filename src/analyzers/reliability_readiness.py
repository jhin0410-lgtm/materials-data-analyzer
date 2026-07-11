"""Generic readiness checks for reliability and risk datasets.

This module audits whether a tabular dataset has enough asset, temporal,
event, censoring, and leakage-control structure for future reliability
analysis. It does not fit models, estimate survival curves, download data, or
call external systems.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pandas as pd


@dataclass(frozen=True)
class ReliabilityReadinessConfig:
    """Column contract for generic reliability readiness checks."""

    required_columns: list[str]
    asset_id_column: str
    observation_timestamp_column: str | None = None
    observation_cycle_column: str | None = None
    event_indicator_column: str | None = None
    event_timestamp_column: str | None = None
    censoring_timestamp_column: str | None = None
    prediction_origin_column: str | None = None
    maintenance_timestamp_column: str | None = None
    maintenance_type_column: str | None = None
    component_id_column: str | None = None
    fleet_id_column: str | None = None
    degradation_feature_columns: list[str] | None = None
    prohibited_feature_patterns: list[str] | None = None
    min_assets_for_asset_split: int = 5
    min_assets_per_split: int = 2
    min_observations_per_asset: int = 2
    min_events_for_event_model: int = 5
    min_rows_for_temporal_split: int = 20


def build_reliability_readiness_report(
    df: pd.DataFrame,
    config: ReliabilityReadinessConfig,
) -> dict[str, pd.DataFrame]:
    """Build CSV-friendly reliability readiness tables."""
    return {
        "required_columns": check_required_columns(df, config.required_columns),
        "asset_summary": summarize_asset_structure(df, config),
        "temporal_order": summarize_temporal_order(df, config),
        "event_indicator": summarize_event_indicator(df, config.event_indicator_column),
        "event_censoring": summarize_event_censoring(df, config),
        "recurrent_events": detect_recurrent_events(df, config),
        "trajectory_length": summarize_trajectory_lengths(df, config),
        "validation_readiness": evaluate_validation_readiness(df, config),
        "leakage_risks": check_reliability_leakage_risks(df, config),
        "feature_availability": summarize_degradation_features(df, config),
    }


def check_required_columns(
    df: pd.DataFrame,
    required_columns: Iterable[str],
) -> pd.DataFrame:
    """Check whether required columns are present."""
    rows = []
    for column in required_columns:
        rows.append(
            {
                "column": column,
                "present": column in df.columns,
                "status": "present" if column in df.columns else "missing",
            }
        )
    return pd.DataFrame(rows)


def summarize_asset_structure(
    df: pd.DataFrame,
    config: ReliabilityReadinessConfig,
) -> pd.DataFrame:
    """Summarize asset identity, cardinality, and repeated observations."""
    column = config.asset_id_column
    if column not in df.columns:
        return pd.DataFrame(
            [
                {
                    "check": "asset_identity",
                    "asset_column": column,
                    "present": False,
                    "asset_count": 0,
                    "rows": len(df),
                    "min_observations_per_asset": 0,
                    "median_observations_per_asset": 0.0,
                    "max_observations_per_asset": 0,
                    "status": "missing_asset_id",
                }
            ]
        )
    counts = df[column].value_counts(dropna=True)
    repeated_assets = int(counts.ge(config.min_observations_per_asset).sum())
    if counts.empty:
        status = "empty_asset_id"
    elif repeated_assets == counts.size:
        status = "asset_longitudinal_ready"
    elif repeated_assets:
        status = "partially_repeated_assets"
    else:
        status = "no_repeated_observations"
    return pd.DataFrame(
        [
            {
                "check": "asset_identity",
                "asset_column": column,
                "present": True,
                "asset_count": int(counts.size),
                "rows": len(df),
                "min_observations_per_asset": int(counts.min()) if not counts.empty else 0,
                "median_observations_per_asset": float(counts.median()) if not counts.empty else 0.0,
                "max_observations_per_asset": int(counts.max()) if not counts.empty else 0,
                "status": status,
            }
        ]
    )


def summarize_temporal_order(
    df: pd.DataFrame,
    config: ReliabilityReadinessConfig,
) -> pd.DataFrame:
    """Check parseability and per-asset chronological order."""
    rows = []
    if config.observation_timestamp_column:
        rows.append(
            _temporal_order_row(
                df,
                asset_column=config.asset_id_column,
                value_column=config.observation_timestamp_column,
                order_type="timestamp",
            )
        )
    if config.observation_cycle_column:
        rows.append(
            _temporal_order_row(
                df,
                asset_column=config.asset_id_column,
                value_column=config.observation_cycle_column,
                order_type="cycle",
            )
        )
    if not rows:
        rows.append(
            {
                "order_type": "none",
                "column": "",
                "present": False,
                "parseable_count": 0,
                "parseable_percent": 0.0,
                "nonmonotonic_asset_count": 0,
                "status": "no_order_column_configured",
            }
        )
    return pd.DataFrame(rows)


def summarize_event_indicator(
    df: pd.DataFrame,
    event_indicator_column: str | None,
) -> pd.DataFrame:
    """Validate event indicator values and event support."""
    if not event_indicator_column:
        return pd.DataFrame(
            [
                {
                    "column": "",
                    "present": False,
                    "valid_values": False,
                    "event_count": 0,
                    "non_event_count": 0,
                    "invalid_value_count": 0,
                    "status": "not_configured",
                }
            ]
        )
    if event_indicator_column not in df.columns:
        return pd.DataFrame(
            [
                {
                    "column": event_indicator_column,
                    "present": False,
                    "valid_values": False,
                    "event_count": 0,
                    "non_event_count": 0,
                    "invalid_value_count": 0,
                    "status": "missing",
                }
            ]
        )
    values = pd.to_numeric(df[event_indicator_column], errors="coerce")
    invalid = values.notna() & ~values.isin([0, 1])
    event_count = int(values.eq(1).sum())
    non_event_count = int(values.eq(0).sum())
    return pd.DataFrame(
        [
            {
                "column": event_indicator_column,
                "present": True,
                "valid_values": bool(not invalid.any() and values.notna().any()),
                "event_count": event_count,
                "non_event_count": non_event_count,
                "invalid_value_count": int(invalid.sum()),
                "status": "valid_binary" if not invalid.any() else "invalid_event_values",
            }
        ]
    )


def summarize_event_censoring(
    df: pd.DataFrame,
    config: ReliabilityReadinessConfig,
) -> pd.DataFrame:
    """Check event/censoring timestamp consistency without modeling censoring."""
    rows = []
    observation = _ordered_series(df, config.observation_timestamp_column, "timestamp")
    prediction_origin = _ordered_series(df, config.prediction_origin_column, "timestamp")
    event_time = _ordered_series(df, config.event_timestamp_column, "timestamp")
    censor_time = _ordered_series(df, config.censoring_timestamp_column, "timestamp")
    event_indicator = (
        pd.to_numeric(df[config.event_indicator_column], errors="coerce")
        if config.event_indicator_column in df.columns
        else pd.Series([pd.NA] * len(df), index=df.index)
    )

    if config.event_timestamp_column:
        comparable = event_time.notna() & observation.notna() & event_indicator.eq(1)
        violations = comparable & (event_time < observation)
        origin_comparable = event_time.notna() & prediction_origin.notna() & event_indicator.eq(1)
        origin_violations = origin_comparable & (event_time < prediction_origin)
        rows.append(
            {
                "check": "event_timestamp_after_observation",
                "column": config.event_timestamp_column,
                "configured": True,
                "comparable_count": int(comparable.sum()),
                "violation_count": int(violations.sum()),
                "status": "valid" if not violations.any() else "event_precedes_observation",
            }
        )
        rows.append(
            {
                "check": "event_timestamp_after_prediction_origin",
                "column": config.event_timestamp_column,
                "configured": bool(config.prediction_origin_column),
                "comparable_count": int(origin_comparable.sum()),
                "violation_count": int(origin_violations.sum()),
                "status": "valid" if not origin_violations.any() else "event_precedes_prediction_origin",
            }
        )
    else:
        rows.append(_not_configured_row("event_timestamp_after_observation", "event_timestamp"))

    if config.censoring_timestamp_column:
        censored = event_indicator.eq(0)
        comparable = censor_time.notna() & observation.notna() & censored
        violations = comparable & (censor_time < observation)
        rows.append(
            {
                "check": "censoring_timestamp_after_observation",
                "column": config.censoring_timestamp_column,
                "configured": True,
                "comparable_count": int(comparable.sum()),
                "violation_count": int(violations.sum()),
                "status": "valid" if not violations.any() else "censoring_precedes_observation",
            }
        )
    else:
        rows.append(_not_configured_row("censoring_timestamp_after_observation", "censoring_timestamp"))
    return pd.DataFrame(rows)


def detect_recurrent_events(
    df: pd.DataFrame,
    config: ReliabilityReadinessConfig,
) -> pd.DataFrame:
    """Detect repeated events per asset."""
    if config.asset_id_column not in df.columns or config.event_indicator_column not in df.columns:
        return pd.DataFrame(
            [
                {
                    "check": "recurrent_events",
                    "asset_count": 0,
                    "recurrent_asset_count": 0,
                    "max_events_per_asset": 0,
                    "status": "missing_asset_or_event_column",
                }
            ]
        )
    event = pd.to_numeric(df[config.event_indicator_column], errors="coerce").fillna(0)
    counts = event.eq(1).groupby(df[config.asset_id_column]).sum()
    recurrent_count = int(counts.gt(1).sum())
    return pd.DataFrame(
        [
            {
                "check": "recurrent_events",
                "asset_count": int(counts.size),
                "recurrent_asset_count": recurrent_count,
                "max_events_per_asset": int(counts.max()) if not counts.empty else 0,
                "status": "recurrent_events_present" if recurrent_count else "single_or_no_event_per_asset",
            }
        ]
    )


def summarize_trajectory_lengths(
    df: pd.DataFrame,
    config: ReliabilityReadinessConfig,
) -> pd.DataFrame:
    """Summarize row counts per asset trajectory."""
    if config.asset_id_column not in df.columns:
        return pd.DataFrame(
            [
                {
                    "asset_count": 0,
                    "min_length": 0,
                    "median_length": 0.0,
                    "max_length": 0,
                    "status": "missing_asset_id",
                }
            ]
        )
    counts = df[config.asset_id_column].value_counts(dropna=True)
    return pd.DataFrame(
        [
            {
                "asset_count": int(counts.size),
                "min_length": int(counts.min()) if not counts.empty else 0,
                "median_length": float(counts.median()) if not counts.empty else 0.0,
                "max_length": int(counts.max()) if not counts.empty else 0,
                "status": "longitudinal" if counts.ge(config.min_observations_per_asset).all() else "short_trajectories_present",
            }
        ]
    )


def evaluate_validation_readiness(
    df: pd.DataFrame,
    config: ReliabilityReadinessConfig,
) -> pd.DataFrame:
    """Evaluate asset, time, and combined validation feasibility."""
    asset_count = (
        int(df[config.asset_id_column].nunique(dropna=True))
        if config.asset_id_column in df.columns
        else 0
    )
    event_count = (
        int(pd.to_numeric(df[config.event_indicator_column], errors="coerce").eq(1).sum())
        if config.event_indicator_column in df.columns
        else 0
    )
    time_ready = _time_or_cycle_ready(df, config)
    asset_ready = asset_count >= config.min_assets_for_asset_split
    event_ready = event_count >= config.min_events_for_event_model
    rows = [
        {
            "validation_type": "asset_disjoint_split",
            "ready": bool(asset_ready and event_ready),
            "basis": (
                f"assets={asset_count}; min_assets={config.min_assets_for_asset_split}; "
                f"events={event_count}; min_events={config.min_events_for_event_model}"
            ),
        },
        {
            "validation_type": "forward_time_split",
            "ready": bool(time_ready and len(df) >= config.min_rows_for_temporal_split and event_ready),
            "basis": (
                f"time_or_cycle_ready={time_ready}; rows={len(df)}; "
                f"min_rows={config.min_rows_for_temporal_split}; events={event_count}"
            ),
        },
        {
            "validation_type": "combined_asset_time_split",
            "ready": bool(asset_ready and time_ready and event_ready),
            "basis": (
                f"asset_ready={asset_ready}; time_or_cycle_ready={time_ready}; "
                f"event_ready={event_ready}"
            ),
        },
    ]
    return pd.DataFrame(rows)


def check_reliability_leakage_risks(
    df: pd.DataFrame,
    config: ReliabilityReadinessConfig,
) -> pd.DataFrame:
    """Flag prohibited feature names or patterns that imply future outcome leakage."""
    patterns = config.prohibited_feature_patterns or default_prohibited_feature_patterns()
    rows = []
    for pattern in patterns:
        matches = [
            column
            for column in df.columns
            if pattern.casefold() in column.casefold()
        ]
        rows.append(
            {
                "field_or_pattern": pattern,
                "matched_columns": ",".join(matches),
                "match_count": len(matches),
                "risk_level": "high" if matches else "not_observed",
                "allowed_as_feature": False if matches else True,
                "status": "prohibited_feature_present" if matches else "not_present",
            }
        )
    return pd.DataFrame(rows)


def summarize_degradation_features(
    df: pd.DataFrame,
    config: ReliabilityReadinessConfig,
) -> pd.DataFrame:
    """Summarize configured degradation/condition feature availability."""
    rows = []
    for column in config.degradation_feature_columns or []:
        if column not in df.columns:
            rows.append(
                {
                    "feature": column,
                    "present": False,
                    "non_null_count": 0,
                    "missing_percent": 100.0,
                    "numeric": False,
                    "status": "missing",
                }
            )
            continue
        non_null = df[column].notna()
        rows.append(
            {
                "feature": column,
                "present": True,
                "non_null_count": int(non_null.sum()),
                "missing_percent": _percent(len(df) - non_null.sum(), len(df)),
                "numeric": bool(pd.api.types.is_numeric_dtype(df[column])),
                "status": "available" if non_null.any() else "empty",
            }
        )
    if not rows:
        rows.append(
            {
                "feature": "",
                "present": False,
                "non_null_count": 0,
                "missing_percent": 0.0,
                "numeric": False,
                "status": "not_configured",
            }
        )
    return pd.DataFrame(rows)


def default_prohibited_feature_patterns() -> list[str]:
    """Return conservative feature-name patterns that often leak reliability targets."""
    return [
        "post_failure",
        "after_failure",
        "future_window",
        "future_degradation",
        "final_cycle",
        "max_cycle",
        "remaining_useful_life",
        "rul",
        "target_health_index",
        "full_lifetime",
        "replacement_after",
        "teardown",
    ]


def _temporal_order_row(
    df: pd.DataFrame,
    *,
    asset_column: str,
    value_column: str,
    order_type: str,
) -> dict[str, object]:
    if value_column not in df.columns:
        return {
            "order_type": order_type,
            "column": value_column,
            "present": False,
            "parseable_count": 0,
            "parseable_percent": 0.0,
            "nonmonotonic_asset_count": 0,
            "status": "missing",
        }
    values = _ordered_series(df, value_column, order_type)
    parseable = values.notna()
    nonmonotonic = 0
    if asset_column in df.columns:
        working = pd.DataFrame({"asset": df[asset_column], "value": values})
        for _, group in working.dropna(subset=["value"]).groupby("asset", sort=False):
            if not group["value"].is_monotonic_increasing:
                nonmonotonic += 1
    status = "ordered" if parseable.any() and nonmonotonic == 0 else "nonmonotonic_assets"
    if not parseable.any():
        status = "unparseable"
    return {
        "order_type": order_type,
        "column": value_column,
        "present": True,
        "parseable_count": int(parseable.sum()),
        "parseable_percent": _percent(parseable.sum(), len(df)),
        "nonmonotonic_asset_count": int(nonmonotonic),
        "status": status,
    }


def _ordered_series(
    df: pd.DataFrame,
    column: str | None,
    order_type: str,
) -> pd.Series:
    if not column or column not in df.columns:
        return pd.Series([pd.NA] * len(df), index=df.index)
    if order_type == "timestamp":
        return pd.to_datetime(df[column], errors="coerce")
    return pd.to_numeric(df[column], errors="coerce")


def _time_or_cycle_ready(df: pd.DataFrame, config: ReliabilityReadinessConfig) -> bool:
    if config.observation_timestamp_column and config.observation_timestamp_column in df.columns:
        values = pd.to_datetime(df[config.observation_timestamp_column], errors="coerce")
        if values.notna().any():
            return True
    if config.observation_cycle_column and config.observation_cycle_column in df.columns:
        values = pd.to_numeric(df[config.observation_cycle_column], errors="coerce")
        if values.notna().any():
            return True
    return False


def _not_configured_row(check: str, column: str) -> dict[str, object]:
    return {
        "check": check,
        "column": column,
        "configured": False,
        "comparable_count": 0,
        "violation_count": 0,
        "status": "not_configured",
    }


def _percent(count: int | float, total: int | float) -> float:
    return float(count / total * 100.0) if total else 0.0
