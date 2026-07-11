"""Generic applicability-domain diagnostics for tabular regression validation.

The helpers in this module are intentionally modest. They compute descriptor
space distances using training-fold preprocessing only, then summarize whether
distance is associated with prediction error. The distance status is a
diagnostic proxy, not calibrated uncertainty and not a physical boundary.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ApplicabilityConfig:
    """Configuration for distance-based applicability diagnostics."""

    feature_columns: list[str]
    identifier_column: str
    k_neighbors: int = 5
    in_domain_percentile: float = 90.0
    out_of_domain_percentile: float = 95.0


@dataclass(frozen=True)
class ApplicabilityReference:
    """Train-fold reference state for descriptor-space distance diagnostics."""

    feature_columns: list[str]
    k_neighbors: int
    train_row_count: int
    train_nn_distance_count: int
    in_domain_percentile: float
    out_of_domain_percentile: float
    in_domain_threshold: float
    out_of_domain_threshold: float
    imputation_values: dict[str, float]
    scaler_mean: dict[str, float]
    scaler_scale: dict[str, float]
    train_matrix: np.ndarray
    train_descriptor_keys: set[str]
    train_nn_distances: np.ndarray


def fit_applicability_reference(
    train_df: pd.DataFrame,
    config: ApplicabilityConfig,
) -> ApplicabilityReference:
    """Fit train-only preprocessing and train-distance reference distribution."""
    _validate_config(train_df, config)
    train_numeric = _coerce_feature_frame(train_df, config.feature_columns)
    imputation = train_numeric.median(axis=0).fillna(0.0)
    train_imputed = train_numeric.fillna(imputation)
    mean = train_imputed.mean(axis=0)
    scale = train_imputed.std(axis=0, ddof=0).replace(0.0, 1.0).fillna(1.0)
    train_matrix = ((train_imputed - mean) / scale).to_numpy(dtype=float)
    train_nn = _train_nearest_neighbor_distances(train_matrix)
    if len(train_nn):
        in_threshold = float(np.percentile(train_nn, config.in_domain_percentile))
        out_threshold = float(np.percentile(train_nn, config.out_of_domain_percentile))
    else:
        in_threshold = np.nan
        out_threshold = np.nan
    return ApplicabilityReference(
        feature_columns=list(config.feature_columns),
        k_neighbors=max(1, int(config.k_neighbors)),
        train_row_count=int(len(train_df)),
        train_nn_distance_count=int(len(train_nn)),
        in_domain_percentile=float(config.in_domain_percentile),
        out_of_domain_percentile=float(config.out_of_domain_percentile),
        in_domain_threshold=in_threshold,
        out_of_domain_threshold=out_threshold,
        imputation_values={col: float(imputation[col]) for col in config.feature_columns},
        scaler_mean={col: float(mean[col]) for col in config.feature_columns},
        scaler_scale={col: float(scale[col]) for col in config.feature_columns},
        train_matrix=train_matrix,
        train_descriptor_keys=set(descriptor_keys(train_df, config.feature_columns)),
        train_nn_distances=train_nn,
    )


def build_applicability_diagnostics(
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    config: ApplicabilityConfig,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Compute nearest-train distance diagnostics for one train/test split."""
    reference = fit_applicability_reference(train_df, config)
    if test_df.empty:
        return pd.DataFrame(columns=_diagnostic_columns(config.identifier_column)), _reference_summary(reference)
    test_numeric = _coerce_feature_frame(test_df, config.feature_columns)
    imputation = pd.Series(reference.imputation_values)
    mean = pd.Series(reference.scaler_mean)
    scale = pd.Series(reference.scaler_scale)
    test_matrix = ((test_numeric.fillna(imputation) - mean) / scale).to_numpy(dtype=float)
    nearest, knn_mean = _test_nearest_distances(
        reference.train_matrix,
        test_matrix,
        reference.k_neighbors,
    )
    test_keys = descriptor_keys(test_df, config.feature_columns)
    rows: list[dict[str, Any]] = []
    for idx, (_, row) in enumerate(test_df.iterrows()):
        percentile = _distance_percentile(nearest[idx], reference.train_nn_distances)
        status = classify_applicability_percentile(
            percentile,
            reference.in_domain_percentile,
            reference.out_of_domain_percentile,
        )
        rows.append(
            {
                config.identifier_column: row[config.identifier_column],
                "nearest_train_distance": float(nearest[idx]),
                "knn_mean_distance": float(knn_mean[idx]),
                "train_distance_percentile": percentile,
                "applicability_status": status,
                "descriptor_seen_in_train": test_keys[idx] in reference.train_descriptor_keys,
                "train_row_count": reference.train_row_count,
                "train_nn_distance_count": reference.train_nn_distance_count,
                "in_domain_percentile": reference.in_domain_percentile,
                "out_of_domain_percentile": reference.out_of_domain_percentile,
                "in_domain_threshold": reference.in_domain_threshold,
                "out_of_domain_threshold": reference.out_of_domain_threshold,
            }
        )
    return pd.DataFrame(rows), _reference_summary(reference)


def classify_applicability_percentile(
    train_distance_percentile: float,
    in_domain_percentile: float = 90.0,
    out_of_domain_percentile: float = 95.0,
) -> str:
    """Classify a row using fixed train NN-distance percentile cutoffs."""
    if pd.isna(train_distance_percentile):
        return "unclassified_small_train"
    if train_distance_percentile <= in_domain_percentile:
        return "in_domain"
    if train_distance_percentile <= out_of_domain_percentile:
        return "boundary"
    return "out_of_domain"


def descriptor_keys(df: pd.DataFrame, feature_columns: list[str]) -> list[str]:
    """Return deterministic exact descriptor-vector keys for numeric features."""
    features = _coerce_feature_frame(df, feature_columns)
    keys: list[str] = []
    for values in features.itertuples(index=False, name=None):
        parts = ["<NA>" if pd.isna(value) else f"{float(value):.12g}" for value in values]
        keys.append("|".join(parts))
    return keys


def summarize_error_by_stratum(
    df: pd.DataFrame,
    *,
    stratum_type: str,
    stratum_column: str,
    group_columns: Iterable[str] = ("split_strategy", "model_variant"),
) -> pd.DataFrame:
    """Summarize prediction error by a named stratum column."""
    required = {
        stratum_column,
        "actual_target",
        "prediction",
        "absolute_error",
        "negative_prediction",
    }
    missing = sorted(required.difference(df.columns))
    if missing:
        raise ValueError("Missing error summary column(s): " + ", ".join(missing))
    group_list = [column for column in group_columns if column in df.columns]
    rows: list[dict[str, Any]] = []
    totals = df.groupby(group_list).size().to_dict() if group_list else {(): len(df)}
    for keys, group in df.groupby(group_list + [stratum_column], dropna=False):
        if not isinstance(keys, tuple):
            keys = (keys,)
        key_values = dict(zip(group_list + [stratum_column], keys))
        group_key = tuple(key_values[column] for column in group_list)
        total = totals.get(group_key, len(df))
        metrics = _regression_error_metrics(group)
        rows.append(
            {
                **{column: key_values[column] for column in group_list},
                "stratum_type": stratum_type,
                "stratum_value": str(key_values[stratum_column]),
                "row_count": int(len(group)),
                "coverage": float(len(group) / total) if total else np.nan,
                **metrics,
            }
        )
    return pd.DataFrame(rows)


def summarize_distance_error_relationship(
    df: pd.DataFrame,
    *,
    group_columns: Iterable[str] = ("split_strategy", "model_variant"),
) -> pd.DataFrame:
    """Summarize whether descriptor distance and absolute error co-vary."""
    required = {"nearest_train_distance", "absolute_error", "applicability_status"}
    missing = sorted(required.difference(df.columns))
    if missing:
        raise ValueError("Missing distance/error column(s): " + ", ".join(missing))
    group_list = [column for column in group_columns if column in df.columns]
    rows: list[dict[str, Any]] = []
    for keys, group in df.groupby(group_list, dropna=False):
        if not isinstance(keys, tuple):
            keys = (keys,)
        key_values = dict(zip(group_list, keys))
        corr = safe_spearman(group["nearest_train_distance"], group["absolute_error"])
        medians = group.groupby("applicability_status")["absolute_error"].median().to_dict()
        in_domain = medians.get("in_domain", np.nan)
        out_domain = medians.get("out_of_domain", np.nan)
        ratio = (
            float(out_domain / in_domain)
            if pd.notna(in_domain) and in_domain != 0 and pd.notna(out_domain)
            else np.nan
        )
        rows.append(
            {
                **key_values,
                "summary_type": "distance_error_relationship",
                "row_count": int(len(group)),
                "nearest_distance_absolute_error_spearman": corr,
                "in_domain_median_absolute_error": in_domain,
                "boundary_median_absolute_error": medians.get("boundary", np.nan),
                "out_of_domain_median_absolute_error": out_domain,
                "out_vs_in_median_error_ratio": ratio,
                "interpretation": interpret_distance_error_relationship(corr, ratio),
            }
        )
        binned = _distance_bins(group)
        for bin_label, bin_group in binned.groupby("distance_bin", dropna=False):
            rows.append(
                {
                    **key_values,
                    "summary_type": "distance_bin",
                    "row_count": int(len(bin_group)),
                    "distance_bin": str(bin_label),
                    "median_absolute_error": float(bin_group["absolute_error"].median()),
                    "nearest_distance_absolute_error_spearman": corr,
                    "interpretation": "descriptive distance bin; not calibrated uncertainty",
                }
            )
    return pd.DataFrame(rows)


def interpret_distance_error_relationship(correlation: float, error_ratio: float) -> str:
    """Return conservative wording for a distance/error relationship."""
    if pd.isna(correlation):
        return "insufficient variation for distance-error diagnostic"
    if correlation >= 0.3 and (pd.isna(error_ratio) or error_ratio >= 1.2):
        return "distance increases with error in this diagnostic proxy"
    if correlation >= 0.15:
        return "weak positive distance-error relationship"
    if correlation <= -0.15:
        return "distance-error relationship is inconsistent or inverse"
    return "weak distance-error relationship"


def safe_spearman(left: pd.Series | np.ndarray, right: pd.Series | np.ndarray) -> float:
    """Compute Spearman correlation without requiring scipy."""
    left_series = pd.Series(left, dtype="float64")
    right_series = pd.Series(right, dtype="float64")
    valid = left_series.notna() & right_series.notna()
    if valid.sum() < 2:
        return np.nan
    left_valid = left_series[valid]
    right_valid = right_series[valid]
    if left_valid.nunique(dropna=True) < 2 or right_valid.nunique(dropna=True) < 2:
        return np.nan
    return float(left_valid.rank(method="average").corr(right_valid.rank(method="average")))


def _validate_config(train_df: pd.DataFrame, config: ApplicabilityConfig) -> None:
    if not config.feature_columns:
        raise ValueError("At least one feature column is required.")
    if config.identifier_column not in train_df.columns:
        raise ValueError(f"Identifier column is missing: {config.identifier_column}")
    missing = [column for column in config.feature_columns if column not in train_df.columns]
    if missing:
        raise ValueError("Missing feature column(s): " + ", ".join(missing))
    if train_df.empty:
        raise ValueError("Train DataFrame must contain at least one row.")
    if not 0 <= config.in_domain_percentile <= config.out_of_domain_percentile <= 100:
        raise ValueError("Percentiles must satisfy 0 <= in_domain <= out_of_domain <= 100.")


def _coerce_feature_frame(df: pd.DataFrame, feature_columns: list[str]) -> pd.DataFrame:
    missing = [column for column in feature_columns if column not in df.columns]
    if missing:
        raise ValueError("Missing feature column(s): " + ", ".join(missing))
    return df[feature_columns].apply(pd.to_numeric, errors="coerce")


def _train_nearest_neighbor_distances(train_matrix: np.ndarray) -> np.ndarray:
    if len(train_matrix) < 2:
        return np.array([], dtype=float)
    distances = _pairwise_euclidean(train_matrix, train_matrix)
    np.fill_diagonal(distances, np.inf)
    return np.min(distances, axis=1)


def _test_nearest_distances(
    train_matrix: np.ndarray,
    test_matrix: np.ndarray,
    k_neighbors: int,
) -> tuple[np.ndarray, np.ndarray]:
    if len(train_matrix) == 0:
        raise ValueError("Train matrix must contain at least one row.")
    distances = _pairwise_euclidean(test_matrix, train_matrix)
    nearest = np.min(distances, axis=1)
    k = min(max(1, int(k_neighbors)), len(train_matrix))
    sorted_distances = np.sort(distances, axis=1)
    knn_mean = np.mean(sorted_distances[:, :k], axis=1)
    return nearest, knn_mean


def _pairwise_euclidean(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    diff = left[:, None, :] - right[None, :, :]
    return np.sqrt(np.sum(diff * diff, axis=2))


def _distance_percentile(distance: float, reference_distances: np.ndarray) -> float:
    if len(reference_distances) == 0 or pd.isna(distance):
        return np.nan
    return float(100.0 * np.mean(reference_distances <= distance))


def _reference_summary(reference: ApplicabilityReference) -> dict[str, Any]:
    return {
        "train_row_count": reference.train_row_count,
        "train_nn_distance_count": reference.train_nn_distance_count,
        "k_neighbors": reference.k_neighbors,
        "in_domain_percentile": reference.in_domain_percentile,
        "out_of_domain_percentile": reference.out_of_domain_percentile,
        "in_domain_threshold": reference.in_domain_threshold,
        "out_of_domain_threshold": reference.out_of_domain_threshold,
    }


def _diagnostic_columns(identifier_column: str) -> list[str]:
    return [
        identifier_column,
        "nearest_train_distance",
        "knn_mean_distance",
        "train_distance_percentile",
        "applicability_status",
        "descriptor_seen_in_train",
        "train_row_count",
        "train_nn_distance_count",
        "in_domain_percentile",
        "out_of_domain_percentile",
        "in_domain_threshold",
        "out_of_domain_threshold",
    ]


def _regression_error_metrics(group: pd.DataFrame) -> dict[str, Any]:
    actual = pd.to_numeric(group["actual_target"], errors="coerce")
    prediction = pd.to_numeric(group["prediction"], errors="coerce")
    error = pd.to_numeric(group["absolute_error"], errors="coerce")
    bias = prediction - actual
    return {
        "mae": float(error.mean()) if len(error.dropna()) else np.nan,
        "median_absolute_error": float(error.median()) if len(error.dropna()) else np.nan,
        "rmse": float(math.sqrt(np.mean(np.square(error.dropna()))))
        if len(error.dropna())
        else np.nan,
        "bias": float(bias.mean()) if len(bias.dropna()) else np.nan,
        "spearman": safe_spearman(actual, prediction),
        "negative_prediction_rate": float(
            pd.Series(group["negative_prediction"]).astype(str).str.lower().eq("true").mean()
        )
        if "negative_prediction" in group.columns and len(group)
        else np.nan,
    }


def _distance_bins(group: pd.DataFrame) -> pd.DataFrame:
    output = group.copy()
    distances = pd.to_numeric(output["nearest_train_distance"], errors="coerce")
    if distances.nunique(dropna=True) < 2:
        output["distance_bin"] = "single_distance_bin"
        return output
    try:
        output["distance_bin"] = pd.qcut(
            distances,
            q=min(4, distances.nunique(dropna=True)),
            labels=False,
            duplicates="drop",
        ).astype("Int64")
    except ValueError:
        output["distance_bin"] = "single_distance_bin"
        return output
    output["distance_bin"] = "q" + output["distance_bin"].astype(str)
    return output
