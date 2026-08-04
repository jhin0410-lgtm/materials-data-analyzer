"""Training-fold-only helpers for battery forecast validation."""
from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


def metric_dict(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    absolute = np.abs(actual - predicted)
    return {
        "mae": float(mean_absolute_error(actual, predicted)),
        "median_absolute_error": float(np.median(absolute)),
        "rmse": float(math.sqrt(mean_squared_error(actual, predicted))),
        "r2": float(r2_score(actual, predicted)) if len(actual) >= 2 else math.nan,
        "p90_absolute_error": float(np.quantile(absolute, 0.90)),
        "p95_absolute_error": float(np.quantile(absolute, 0.95)),
    }


def select_fold_features(
    train: pd.DataFrame, candidate_columns: Sequence[str]
) -> tuple[list[str], dict[str, str]]:
    """Remove all-missing, constant, and exact-duplicate columns using train only."""
    selected: list[str] = []
    dropped: dict[str, str] = {}
    for column in candidate_columns:
        series = train[column]
        if not series.notna().any():
            dropped[column] = "all_missing_in_training_fold"
            continue
        if series.nunique(dropna=True) <= 1:
            dropped[column] = "constant_in_training_fold"
            continue
        duplicate_of = next(
            (retained for retained in selected if series.equals(train[retained])), None
        )
        if duplicate_of is not None:
            dropped[column] = f"exact_duplicate_of:{duplicate_of}"
            continue
        selected.append(column)
    return selected, dropped


def make_model(alpha: float) -> Pipeline:
    return Pipeline(
        [
            ("impute", SimpleImputer(strategy="median", add_indicator=True)),
            ("scale", StandardScaler()),
            ("ridge", Ridge(alpha=alpha)),
        ]
    )


def pipeline_metadata(
    model: Pipeline, selected_features: Sequence[str]
) -> dict[str, Any]:
    imputer = model.named_steps["impute"]
    scaler = model.named_steps["scale"]
    ridge = model.named_steps["ridge"]
    transformed = [str(value) for value in imputer.get_feature_names_out(selected_features)]
    indicator = getattr(imputer, "indicator_", None)
    indicator_indexes = getattr(indicator, "features_", [])
    return {
        "selected_input_features": list(selected_features),
        "transformed_feature_names": transformed,
        "imputer_strategy": "median",
        "imputer_statistics": {
            str(column): float(value)
            for column, value in zip(selected_features, imputer.statistics_, strict=True)
        },
        "missing_indicator_features": [
            str(selected_features[index]) for index in indicator_indexes
        ],
        "scaler_mean": {
            name: float(value)
            for name, value in zip(transformed, scaler.mean_, strict=True)
        },
        "scaler_scale": {
            name: float(value)
            for name, value in zip(transformed, scaler.scale_, strict=True)
        },
        "ridge_alpha": float(ridge.alpha),
        "ridge_intercept": float(ridge.intercept_),
        "ridge_coefficients": {
            name: float(value)
            for name, value in zip(transformed, ridge.coef_, strict=True)
        },
    }


def group_oof_residuals(
    x: pd.DataFrame,
    y: np.ndarray,
    groups: np.ndarray,
    *,
    alpha: float,
    max_splits: int,
) -> np.ndarray:
    unique_groups = np.unique(groups)
    if len(unique_groups) < 3:
        return np.array([], dtype=float)
    splitter = GroupKFold(n_splits=min(max_splits, len(unique_groups)))
    residuals: list[float] = []
    for train_index, test_index in splitter.split(x, y, groups):
        train_raw = x.iloc[train_index]
        eligible, _ = select_fold_features(train_raw, list(x.columns))
        if not eligible:
            continue
        model = make_model(alpha)
        model.fit(train_raw[eligible], y[train_index])
        prediction = model.predict(x.iloc[test_index][eligible])
        residuals.extend(np.abs(y[test_index] - prediction).tolist())
    return np.asarray(residuals, dtype=float)


def finite_sample_conformal_quantile(
    residuals: np.ndarray, coverage: float
) -> float:
    if len(residuals) == 0:
        return math.nan
    rank = math.ceil((len(residuals) + 1) * coverage) / len(residuals)
    return float(np.quantile(residuals, min(rank, 1.0), method="higher"))


def ood_diagnostics(
    train: pd.DataFrame, test: pd.DataFrame
) -> tuple[np.ndarray, np.ndarray]:
    train_min = train.min(axis=0).to_numpy(dtype=float)
    train_max = train.max(axis=0).to_numpy(dtype=float)
    train_iqr = (
        train.quantile(0.75, axis=0) - train.quantile(0.25, axis=0)
    ).to_numpy(dtype=float)
    train_std = train.std(axis=0, ddof=0).to_numpy(dtype=float)
    scale = np.where(train_iqr > 0, train_iqr, np.where(train_std > 0, train_std, 1.0))
    values = test.to_numpy(dtype=float)
    outside = (values < train_min) | (values > train_max)
    outside_count = np.sum(outside, axis=1)
    distance = np.maximum(train_min - values, values - train_max)
    distance = np.maximum(distance, 0.0) / scale
    max_distance = np.max(np.where(outside, distance, 0.0), axis=1)
    max_distance[outside_count == 0] = 0.0
    return outside_count.astype(int), max_distance.astype(float)


def improvement_percent(reference_mae: float, candidate_mae: float) -> float:
    return float(
        100.0
        * (reference_mae - candidate_mae)
        / max(reference_mae, np.finfo(float).eps)
    )


def coverage_summary(group: pd.DataFrame) -> tuple[int, float, float]:
    available = group["interval_contains_actual"].notna()
    count = int(available.sum())
    coverage = (
        float(group.loc[available, "interval_contains_actual"].astype(bool).mean())
        if count
        else math.nan
    )
    width = group["prediction_interval_high"] - group["prediction_interval_low"]
    return count, coverage, float(width[available].mean()) if count else math.nan
