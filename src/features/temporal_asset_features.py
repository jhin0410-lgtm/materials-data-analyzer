"""Cutoff-safe temporal asset feature construction utilities.

The helpers in this module build binary-horizon labels and fixed lookback
features from longitudinal asset observations. They intentionally avoid future
rows, full-lifetime normalization, and target-informed feature selection.
"""

from __future__ import annotations

import csv
import hashlib
import math
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class TemporalAssetFeatureConfig:
    """Configuration for horizon-label and lookback-feature construction."""

    asset_column: str = "serial_number"
    date_column: str = "observation_date"
    model_column: str = "model"
    capacity_column: str = "capacity_bytes"
    failure_column: str = "failure"
    source_order_column: str = "source_order_index"
    observation_number_column: str = "observation_number_within_asset"
    days_since_first_column: str = "days_since_first_observation"
    post_failure_status_column: str = "post_failure_status"
    feature_columns: tuple[str, ...] = ()
    horizon_days: int = 7
    lookback_days: int = 7
    case_study_version: str = "v1.5.4"
    source_sha256: str = ""


def hash_asset_id(asset_id: Any) -> str:
    """Return a deterministic non-reversible asset hash for tracked diagnostics."""
    return hashlib.sha256(str(asset_id).encode("utf-8")).hexdigest()[:16]


def label_failure_within_horizon(
    *,
    origin: date,
    first_failure_date: date | None,
    horizon_days: int,
) -> int:
    """Return 1 only when first observed failure is after origin and within horizon."""
    if first_failure_date is None:
        return 0
    return int(origin < first_failure_date <= origin + timedelta(days=horizon_days))


def origin_eligibility_status(
    *,
    origin: date,
    first_failure_date: date | None,
    archive_last_date: date,
    horizon_days: int,
) -> str:
    """Classify whether an origin can be used for fixed-horizon prediction."""
    if first_failure_date is not None and origin >= first_failure_date:
        return "post_event_excluded"
    if origin + timedelta(days=horizon_days) > archive_last_date:
        return "right_edge_excluded"
    return "eligible"


def lookback_window_start(origin: date, lookback_days: int) -> date:
    """Return inclusive start date for a lookback ending on origin date."""
    if lookback_days < 1:
        raise ValueError("lookback_days must be >= 1")
    return origin - timedelta(days=lookback_days - 1)


def aggregate_lookback_values(
    window: Iterable[tuple[date, dict[str, float]]],
    *,
    origin: date,
    feature_columns: Iterable[str],
    lookback_days: int,
) -> dict[str, float]:
    """Build deterministic aggregate features from rows at or before origin."""
    rows = list(window)
    result: dict[str, float] = {}
    observed_dates = {row_date for row_date, _ in rows}
    for feature in feature_columns:
        values = [values_by_feature.get(feature, np.nan) for _, values_by_feature in rows]
        numeric = pd.to_numeric(pd.Series(values, dtype="float64"), errors="coerce")
        nonmissing = numeric.dropna()
        prefix = f"{feature}__"
        result[prefix + "current"] = _last_value(numeric)
        result[prefix + "mean_7d"] = _series_stat(nonmissing, "mean")
        result[prefix + "median_7d"] = _series_stat(nonmissing, "median")
        result[prefix + "min_7d"] = _series_stat(nonmissing, "min")
        result[prefix + "max_7d"] = _series_stat(nonmissing, "max")
        result[prefix + "std_7d"] = _series_stat(nonmissing, "std")
        result[prefix + "count_7d"] = float(nonmissing.size)
        result[prefix + "missing_count_7d"] = float(len(rows) - nonmissing.size)
        result[prefix + "delta_7d"] = _delta(nonmissing)
        result[prefix + "slope_7d"] = _slope(rows, feature)
    result["lookback_observation_count"] = float(len(rows))
    result["lookback_days_observed"] = float(len(observed_dates))
    result["lookback_observation_density_7d"] = float(len(observed_dates) / lookback_days)
    result["prediction_origin_weekday"] = float(origin.weekday())
    return result


def build_temporal_asset_feature_table(
    df: pd.DataFrame,
    config: TemporalAssetFeatureConfig,
) -> pd.DataFrame:
    """Build a cutoff-safe feature table from an in-memory asset history."""
    required = [
        config.asset_column,
        config.date_column,
        config.failure_column,
        config.model_column,
        config.capacity_column,
    ]
    missing = [column for column in required + list(config.feature_columns) if column not in df]
    if missing:
        raise ValueError("Missing required column(s): " + ", ".join(missing))
    frame = df.copy()
    frame[config.date_column] = pd.to_datetime(frame[config.date_column], errors="raise").dt.date
    frame[config.failure_column] = pd.to_numeric(frame[config.failure_column], errors="raise").astype(int)
    if set(frame[config.failure_column].unique()) - {0, 1}:
        raise ValueError("failure column must contain only 0 and 1")
    archive_last = max(frame[config.date_column])
    event_dates = _first_failure_dates(frame, config)
    rows: list[dict[str, Any]] = []
    sort_columns = [config.asset_column, config.date_column]
    if config.source_order_column in frame:
        sort_columns.append(config.source_order_column)
    for asset, group in frame.sort_values(sort_columns, kind="mergesort").groupby(
        config.asset_column, sort=False
    ):
        window: deque[tuple[date, dict[str, float]]] = deque()
        first_failure = event_dates.get(str(asset))
        for _, row in group.iterrows():
            origin = row[config.date_column]
            values = {
                feature: _to_float(row.get(feature, np.nan))
                for feature in config.feature_columns
            }
            window.append((origin, values))
            start = lookback_window_start(origin, config.lookback_days)
            while window and window[0][0] < start:
                window.popleft()
            status = origin_eligibility_status(
                origin=origin,
                first_failure_date=first_failure,
                archive_last_date=archive_last,
                horizon_days=config.horizon_days,
            )
            if status != "eligible":
                continue
            target = label_failure_within_horizon(
                origin=origin,
                first_failure_date=first_failure,
                horizon_days=config.horizon_days,
            )
            rows.append(
                {
                    **_base_feature_row(row, asset, origin, first_failure, target, config),
                    **aggregate_lookback_values(
                        window,
                        origin=origin,
                        feature_columns=config.feature_columns,
                        lookback_days=config.lookback_days,
                    ),
                }
            )
    return pd.DataFrame(rows)


def write_temporal_asset_feature_dataset_from_csv(
    *,
    input_path: str | Path,
    output_path: str | Path,
    config: TemporalAssetFeatureConfig,
    chunksize: int = 100_000,
) -> dict[str, Any]:
    """Build a local horizon/lookback dataset from selected analysis-ready columns."""
    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    usecols = _streaming_usecols(config)
    frame = pd.read_csv(input_path, usecols=usecols)
    if frame.empty:
        raise ValueError("Input analysis-ready CSV is empty.")
    frame[config.date_column] = pd.to_datetime(frame[config.date_column], errors="raise")
    frame[config.failure_column] = pd.to_numeric(
        frame[config.failure_column], errors="raise"
    ).astype(int)
    if set(frame[config.failure_column].unique()) - {0, 1}:
        raise ValueError("failure column must contain only 0 and 1")
    for column in config.feature_columns:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.sort_values(
        [config.asset_column, config.date_column, config.source_order_column],
        kind="mergesort",
    ).reset_index(drop=True)
    archive_last = frame[config.date_column].max()
    failure_dates = (
        frame[frame[config.failure_column].eq(1)]
        .groupby(config.asset_column)[config.date_column]
        .min()
    )
    asset_last_dates = frame.groupby(config.asset_column)[config.date_column].max()
    frame["_first_failure_date"] = frame[config.asset_column].map(failure_dates)
    frame["_asset_last_observation_date"] = frame[config.asset_column].map(asset_last_dates)
    horizon_end = frame[config.date_column] + pd.to_timedelta(config.horizon_days, unit="D")
    has_failure = frame["_first_failure_date"].notna()
    post_event = has_failure & (frame[config.date_column] >= frame["_first_failure_date"])
    target = (
        has_failure
        & (frame[config.date_column] < frame["_first_failure_date"])
        & (frame["_first_failure_date"] <= horizon_end)
    ).astype(int)
    right_edge = target.eq(0) & ~post_event & (frame["_asset_last_observation_date"] < horizon_end)

    output = pd.DataFrame(
        {
            "case_study_version": config.case_study_version,
            "source_sha256": config.source_sha256,
            "serial_number": frame[config.asset_column].astype(str),
            "asset_id_hash": frame[config.asset_column].astype(str).map(hash_asset_id),
            "prediction_origin": frame[config.date_column].dt.strftime("%Y-%m-%d"),
            "horizon_end": horizon_end.dt.strftime("%Y-%m-%d"),
            "target_failure_within_7d": target,
            "event_date": frame["_first_failure_date"].dt.strftime("%Y-%m-%d").fillna(""),
            "eligibility_status": "eligible",
            "right_edge_excluded": right_edge,
            "post_event_excluded": post_event,
            "model": frame[config.model_column].astype(str),
            "capacity_bytes": frame[config.capacity_column],
            "drive_age_days": frame[config.days_since_first_column],
            "observation_number_within_asset": frame[config.observation_number_column],
            "source_order_index": frame[config.source_order_column],
        }
    )

    grouped = frame.groupby(config.asset_column, sort=False)
    row_count = (
        grouped.rolling(
            f"{config.lookback_days}D",
            on=config.date_column,
        )[config.source_order_column]
        .count()
        .to_numpy()
    )
    output["lookback_observation_count"] = row_count
    output["lookback_days_observed"] = row_count
    output["lookback_observation_density_7d"] = row_count / float(config.lookback_days)
    output["prediction_origin_weekday"] = frame[config.date_column].dt.weekday.astype(float)

    for feature in config.feature_columns:
        rolling = grouped.rolling(f"{config.lookback_days}D", on=config.date_column)[feature]
        count = rolling.count().to_numpy()
        first = rolling.apply(_first_raw_value, raw=True).to_numpy()
        current = frame[feature].to_numpy(dtype=float)
        delta = current - first
        slope = np.where(count >= 2, delta / np.maximum(row_count - 1, 1), np.nan)
        prefix = f"{feature}__"
        output[prefix + "current"] = current
        output[prefix + "mean_7d"] = rolling.mean().to_numpy()
        output[prefix + "median_7d"] = rolling.median().to_numpy()
        output[prefix + "min_7d"] = rolling.min().to_numpy()
        output[prefix + "max_7d"] = rolling.max().to_numpy()
        output[prefix + "std_7d"] = rolling.std(ddof=0).fillna(0.0).to_numpy()
        output[prefix + "count_7d"] = count
        output[prefix + "missing_count_7d"] = row_count - count
        output[prefix + "delta_7d"] = delta
        output[prefix + "slope_7d"] = slope

    eligible = target.eq(1) | (~post_event & ~right_edge)
    final = output.loc[eligible, _feature_dataset_columns(config)]
    final.to_csv(output_path, index=False)
    positive_mask = final["target_failure_within_7d"].astype(int).eq(1)
    written = int(len(final))
    positive_rows = int(positive_mask.sum())
    positive_assets = set(final.loc[positive_mask, "serial_number"].astype(str))
    right_edge_excluded = int((right_edge & ~post_event).sum())
    post_event_excluded = int(post_event.sum())
    return {
        "output_path": str(output_path).replace("\\", "/"),
        "row_count": written,
        "positive_rows": positive_rows,
        "positive_assets": len(positive_assets),
        "right_edge_excluded_rows": right_edge_excluded,
        "post_event_excluded_rows": post_event_excluded,
        "horizon_days": config.horizon_days,
        "lookback_days": config.lookback_days,
    }


def feature_columns_for_smart_only(smart_features: Iterable[str]) -> list[str]:
    """Return the primary SMART-only aggregate columns used for modeling."""
    suffixes = ["current", "mean_7d", "std_7d", "delta_7d", "slope_7d"]
    return [f"{feature}__{suffix}" for feature in smart_features for suffix in suffixes]


def feature_columns_for_safe_metadata() -> list[str]:
    """Return numeric safe operational metadata columns for modeling."""
    return [
        "capacity_bytes",
        "drive_age_days",
        "observation_number_within_asset",
        "lookback_observation_count",
        "lookback_days_observed",
        "lookback_observation_density_7d",
        "prediction_origin_weekday",
    ]


def _first_failure_dates(
    frame: pd.DataFrame,
    config: TemporalAssetFeatureConfig,
) -> dict[str, date]:
    failed = frame[frame[config.failure_column].eq(1)]
    if failed.empty:
        return {}
    grouped = (
        failed.groupby(config.asset_column)[config.date_column]
        .min()
        .map(lambda value: value if isinstance(value, date) else pd.to_datetime(value).date())
        .astype(object)
        .to_dict()
    )
    return {str(asset): failure_date for asset, failure_date in grouped.items()}


def _scan_events_and_archive_end(
    input_path: Path,
    config: TemporalAssetFeatureConfig,
    *,
    usecols: list[str],
    chunksize: int,
) -> tuple[dict[str, date], date]:
    event_dates: dict[str, date] = {}
    archive_last: date | None = None
    for chunk in pd.read_csv(input_path, usecols=usecols, chunksize=chunksize):
        dates = pd.to_datetime(chunk[config.date_column], errors="raise").dt.date
        chunk = chunk.assign(_date=dates)
        if not chunk.empty:
            local_max = max(chunk["_date"])
            archive_last = local_max if archive_last is None else max(archive_last, local_max)
        failures = chunk[pd.to_numeric(chunk[config.failure_column], errors="raise").astype(int).eq(1)]
        for row in failures.itertuples(index=False):
            row_map = _tuple_to_dict(row, failures.columns)
            asset = str(row_map[config.asset_column])
            failure_date = row_map["_date"]
            if asset not in event_dates or failure_date < event_dates[asset]:
                event_dates[asset] = failure_date
    if archive_last is None:
        raise ValueError("Input analysis-ready CSV is empty.")
    return event_dates, archive_last


def _streaming_usecols(config: TemporalAssetFeatureConfig) -> list[str]:
    columns = [
        config.asset_column,
        config.date_column,
        config.model_column,
        config.capacity_column,
        config.failure_column,
        config.source_order_column,
        config.observation_number_column,
        config.days_since_first_column,
        config.post_failure_status_column,
    ]
    return list(dict.fromkeys(columns + list(config.feature_columns)))


def _feature_dataset_columns(config: TemporalAssetFeatureConfig) -> list[str]:
    base = [
        "case_study_version",
        "source_sha256",
        "serial_number",
        "asset_id_hash",
        "prediction_origin",
        "horizon_end",
        "target_failure_within_7d",
        "event_date",
        "eligibility_status",
        "right_edge_excluded",
        "post_event_excluded",
        "model",
        "capacity_bytes",
        "drive_age_days",
        "observation_number_within_asset",
        "source_order_index",
    ]
    aggregates: list[str] = []
    suffixes = [
        "current",
        "mean_7d",
        "median_7d",
        "min_7d",
        "max_7d",
        "std_7d",
        "count_7d",
        "missing_count_7d",
        "delta_7d",
        "slope_7d",
    ]
    for feature in config.feature_columns:
        aggregates.extend([f"{feature}__{suffix}" for suffix in suffixes])
    common = [
        "lookback_observation_count",
        "lookback_days_observed",
        "lookback_observation_density_7d",
        "prediction_origin_weekday",
    ]
    return base + aggregates + common


def _base_feature_row(
    row: Any,
    asset: Any,
    origin: date,
    first_failure: date | None,
    target: int,
    config: TemporalAssetFeatureConfig,
) -> dict[str, Any]:
    row_get = row.get if isinstance(row, dict) else row.__getitem__
    return {
        "case_study_version": config.case_study_version,
        "source_sha256": config.source_sha256,
        "serial_number": asset,
        "asset_id_hash": hash_asset_id(asset),
        "prediction_origin": origin.isoformat(),
        "horizon_end": (origin + timedelta(days=config.horizon_days)).isoformat(),
        "target_failure_within_7d": int(target),
        "event_date": first_failure.isoformat() if first_failure else "",
        "eligibility_status": "eligible",
        "right_edge_excluded": False,
        "post_event_excluded": False,
        "model": row_get(config.model_column),
        "capacity_bytes": row_get(config.capacity_column),
        "drive_age_days": row_get(config.days_since_first_column)
        if config.days_since_first_column in row
        else np.nan,
        "observation_number_within_asset": row_get(config.observation_number_column)
        if config.observation_number_column in row
        else np.nan,
        "source_order_index": row_get(config.source_order_column)
        if config.source_order_column in row
        else np.nan,
    }


def _ordered_row(row: dict[str, Any], fieldnames: list[str]) -> dict[str, Any]:
    return {key: row.get(key, "") for key in fieldnames}


def _tuple_to_dict(record: Any, columns: Iterable[str]) -> dict[str, Any]:
    return dict(zip(columns, record))


def _last_value(series: pd.Series) -> float:
    if series.empty:
        return np.nan
    return _to_float(series.iloc[-1])


def _series_stat(series: pd.Series, stat: str) -> float:
    if series.empty:
        return np.nan
    if stat == "mean":
        return float(series.mean())
    if stat == "median":
        return float(series.median())
    if stat == "min":
        return float(series.min())
    if stat == "max":
        return float(series.max())
    if stat == "std":
        return float(series.std(ddof=0)) if len(series) > 1 else 0.0
    raise ValueError(f"Unsupported stat: {stat}")


def _delta(series: pd.Series) -> float:
    if len(series) < 2:
        return np.nan
    return float(series.iloc[-1] - series.iloc[0])


def _slope(rows: list[tuple[date, dict[str, float]]], feature: str) -> float:
    pairs = [
        (row_date, values.get(feature, np.nan))
        for row_date, values in rows
        if not pd.isna(values.get(feature, np.nan))
    ]
    if len(pairs) < 2:
        return np.nan
    first_date = pairs[0][0]
    x = np.array([(row_date - first_date).days for row_date, _ in pairs], dtype=float)
    y = np.array([value for _, value in pairs], dtype=float)
    if np.all(x == x[0]):
        return np.nan
    return float(np.polyfit(x, y, 1)[0])


def _to_float(value: Any) -> float:
    try:
        if value is None or pd.isna(value):
            return np.nan
        return float(value)
    except (TypeError, ValueError):
        return np.nan


def _first_raw_value(values: np.ndarray) -> float:
    nonmissing = values[~pd.isna(values)]
    if len(nonmissing) == 0:
        return np.nan
    return float(nonmissing[0])
