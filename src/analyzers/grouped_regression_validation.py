"""Generic grouped regression validation utilities.

The evaluator is intentionally conservative: it performs fixed baseline
comparisons, records overlap diagnostics, preserves negative/poor results, and
does not tune model parameters or select favorable splits.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class SplitConfig:
    """Configuration for one validation split strategy."""

    name: str
    splitter_type: str
    group_column: str | None = None
    n_splits: int = 10
    test_size: float = 0.2
    random_state: int = 42


@dataclass(frozen=True)
class ModelConfig:
    """Configuration for one fixed baseline model variant."""

    name: str
    estimator_type: str
    target_treatment: str = "raw"
    alpha: float = 1.0
    random_state: int = 42


@dataclass(frozen=True)
class ValidationConfig:
    """Configuration for grouped regression validation."""

    identifier_column: str
    target_column: str
    feature_columns: list[str]
    split_configs: list[SplitConfig]
    model_configs: list[ModelConfig]
    theoretical_column: str | None = None
    formula_group_column: str | None = None
    chemical_system_group_column: str | None = None
    ambiguity_group_column: str | None = None


def calculate_file_sha256(path: str | Path) -> str:
    """Calculate SHA-256 without modifying a file."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def default_model_configs(random_state: int = 42) -> list[ModelConfig]:
    """Return fixed baseline model variants."""
    return [
        ModelConfig("dummy_median", "dummy_median", "raw", random_state=random_state),
        ModelConfig("ridge_raw", "ridge", "raw", alpha=1.0, random_state=random_state),
        ModelConfig("ridge_log1p", "ridge", "log1p", alpha=1.0, random_state=random_state),
        ModelConfig(
            "histogram_gradient_boosting_raw",
            "histogram_gradient_boosting",
            "raw",
            random_state=random_state,
        ),
        ModelConfig(
            "histogram_gradient_boosting_log1p",
            "histogram_gradient_boosting",
            "log1p",
            random_state=random_state,
        ),
    ]


def default_split_configs(random_state: int = 42) -> list[SplitConfig]:
    """Return fixed random and group-aware split strategies."""
    return [
        SplitConfig("random", "shuffle", None, 10, 0.2, random_state),
        SplitConfig(
            "reduced_formula_group",
            "group_shuffle",
            "reduced_formula_group",
            10,
            0.2,
            random_state,
        ),
        SplitConfig(
            "chemical_system_group",
            "group_shuffle",
            "chemical_system_group",
            10,
            0.2,
            random_state,
        ),
    ]


def validate_feature_columns(
    df: pd.DataFrame,
    feature_columns: list[str],
    forbidden_features: Iterable[str],
    target_column: str,
) -> None:
    """Validate that feature columns are numeric and leakage-free."""
    missing = [column for column in feature_columns if column not in df.columns]
    if missing:
        raise ValueError("Missing feature column(s): " + ", ".join(missing))
    forbidden = set(forbidden_features) | {target_column}
    leaked = sorted(set(feature_columns).intersection(forbidden))
    if leaked:
        raise ValueError("Forbidden feature(s) included: " + ", ".join(leaked))
    nonnumeric = [
        column for column in feature_columns if not pd.api.types.is_numeric_dtype(df[column])
    ]
    if nonnumeric:
        raise ValueError("Feature column(s) must be numeric: " + ", ".join(nonnumeric))


def generate_splits(
    df: pd.DataFrame,
    split_config: SplitConfig,
) -> list[dict[str, Any]]:
    """Generate fixed split assignments; invalid splits are recorded, not replaced."""
    tools = _load_sklearn_tools()
    index = np.arange(len(df))
    results: list[dict[str, Any]] = []
    if split_config.splitter_type == "shuffle":
        splitter = tools["ShuffleSplit"](
            n_splits=split_config.n_splits,
            test_size=split_config.test_size,
            random_state=split_config.random_state,
        )
        iterator = splitter.split(index)
    elif split_config.splitter_type == "group_shuffle":
        if split_config.group_column is None or split_config.group_column not in df.columns:
            return [
                {
                    "split_strategy": split_config.name,
                    "split_index": idx,
                    "status": "invalid",
                    "invalid_reason": "group column unavailable",
                    "train_index": np.array([], dtype=int),
                    "test_index": np.array([], dtype=int),
                }
                for idx in range(split_config.n_splits)
            ]
        groups = df[split_config.group_column]
        if groups.nunique(dropna=True) < 2:
            return [
                {
                    "split_strategy": split_config.name,
                    "split_index": idx,
                    "status": "invalid",
                    "invalid_reason": "too few groups",
                    "train_index": np.array([], dtype=int),
                    "test_index": np.array([], dtype=int),
                }
                for idx in range(split_config.n_splits)
            ]
        splitter = tools["GroupShuffleSplit"](
            n_splits=split_config.n_splits,
            test_size=split_config.test_size,
            random_state=split_config.random_state,
        )
        iterator = splitter.split(index, groups=groups)
    else:
        raise ValueError(f"Unsupported splitter_type: {split_config.splitter_type}")

    for split_index, (train_index, test_index) in enumerate(iterator):
        status = "valid"
        invalid_reason = ""
        if split_config.splitter_type == "group_shuffle":
            group_values = df[split_config.group_column]
            overlap = set(group_values.iloc[train_index]).intersection(
                set(group_values.iloc[test_index])
            )
            if overlap:
                status = "invalid"
                invalid_reason = f"group overlap detected: {split_config.group_column}"
        results.append(
            {
                "split_strategy": split_config.name,
                "split_index": split_index,
                "status": status,
                "invalid_reason": invalid_reason,
                "train_index": train_index,
                "test_index": test_index,
            }
        )
    return results


def evaluate_validation(
    df: pd.DataFrame,
    config: ValidationConfig,
    *,
    forbidden_features: Iterable[str],
) -> dict[str, pd.DataFrame]:
    """Run fixed baseline models across all configured splits."""
    validate_feature_columns(
        df,
        config.feature_columns,
        forbidden_features,
        config.target_column,
    )
    y = pd.to_numeric(df[config.target_column], errors="coerce")
    if y.isna().any():
        raise ValueError("Target contains missing or nonnumeric values; rows are not dropped.")
    if (y < 0).any():
        raise ValueError("log1p target treatment requires nonnegative target values.")

    all_prediction_rows: list[dict[str, Any]] = []
    all_metric_rows: list[dict[str, Any]] = []
    split_diagnostics: list[dict[str, Any]] = []
    screening_rows: list[dict[str, Any]] = []

    for split_config in config.split_configs:
        splits = generate_splits(df, split_config)
        for split in splits:
            diagnostics = build_split_diagnostics(df, split, config)
            split_diagnostics.append(diagnostics)
            if split["status"] != "valid":
                for model_config in config.model_configs:
                    all_metric_rows.append(
                        _invalid_metric_row(split, model_config, diagnostics)
                    )
                continue
            for model_config in config.model_configs:
                result = evaluate_model_on_split(df, config, split, model_config)
                prediction_rows = result["predictions"]
                all_prediction_rows.extend(prediction_rows)
                metric_row = {
                    **_split_model_keys(split, model_config),
                    **diagnostics,
                    **result["metrics"],
                    "status": "valid",
                    "invalid_reason": "",
                }
                all_metric_rows.append(metric_row)
                screening_rows.append(
                    {
                        **_split_model_keys(split, model_config),
                        **result["screening_metrics"],
                    }
                )

    predictions = pd.DataFrame(all_prediction_rows)
    metrics = pd.DataFrame(all_metric_rows)
    split_df = pd.DataFrame(split_diagnostics)
    screening = pd.DataFrame(screening_rows)
    comparison = summarize_model_comparison(metrics)
    screening_summary = summarize_screening_metrics(screening)
    return {
        "predictions": predictions,
        "metrics": metrics,
        "model_comparison": comparison,
        "split_diagnostics": split_df,
        "screening_metrics": screening_summary,
    }


def evaluate_model_on_split(
    df: pd.DataFrame,
    config: ValidationConfig,
    split: dict[str, Any],
    model_config: ModelConfig,
) -> dict[str, Any]:
    """Fit one fixed model on one split and return predictions and metrics."""
    tools = _load_sklearn_tools()
    train_index = split["train_index"]
    test_index = split["test_index"]
    x_train = df.iloc[train_index][config.feature_columns]
    x_test = df.iloc[test_index][config.feature_columns]
    y_train_raw = pd.to_numeric(df.iloc[train_index][config.target_column], errors="raise")
    y_test = pd.to_numeric(df.iloc[test_index][config.target_column], errors="raise")
    if model_config.target_treatment == "log1p":
        y_train = np.log1p(y_train_raw)
    else:
        y_train = y_train_raw

    model = build_model_pipeline(model_config, tools)
    model.fit(x_train, y_train)
    raw_prediction = np.asarray(model.predict(x_test), dtype=float)
    if model_config.target_treatment == "log1p":
        raw_prediction = np.expm1(raw_prediction)
    constrained_prediction = np.maximum(raw_prediction, 0.0)
    negative_prediction = raw_prediction < 0

    predictions = build_prediction_rows(
        df,
        config,
        split,
        model_config,
        y_test.to_numpy(dtype=float),
        raw_prediction,
        constrained_prediction,
        negative_prediction,
    )
    prediction_df = pd.DataFrame(predictions)
    metrics = compute_metric_bundle(
        y_true=y_test.to_numpy(dtype=float),
        raw_prediction=raw_prediction,
        constrained_prediction=constrained_prediction,
        negative_prediction=negative_prediction,
        prediction_df=prediction_df,
    )
    metrics.update(
        compute_subgroup_metrics(
            prediction_df,
            subgroup_columns=[
                "theoretical",
                "ambiguity_group_status",
            ],
        )
    )
    screening_metrics = compute_screening_metrics(prediction_df)
    return {
        "predictions": predictions,
        "metrics": metrics,
        "screening_metrics": screening_metrics,
    }


def build_model_pipeline(model_config: ModelConfig, tools: dict[str, Any]) -> Any:
    """Build a fixed sklearn Pipeline for one model variant."""
    Pipeline = tools["Pipeline"]
    SimpleImputer = tools["SimpleImputer"]
    if model_config.estimator_type == "dummy_median":
        estimator = tools["DummyRegressor"](strategy="median")
        return Pipeline([("imputer", SimpleImputer(strategy="median")), ("model", estimator)])
    if model_config.estimator_type == "ridge":
        estimator = tools["Ridge"](alpha=model_config.alpha)
        return Pipeline(
            [
                ("imputer", SimpleImputer(strategy="median")),
                ("scaler", tools["StandardScaler"]()),
                ("model", estimator),
            ]
        )
    if model_config.estimator_type == "histogram_gradient_boosting":
        estimator = tools["HistGradientBoostingRegressor"](
            random_state=model_config.random_state,
            max_iter=60,
            learning_rate=0.1,
            max_leaf_nodes=31,
        )
        return Pipeline([("imputer", SimpleImputer(strategy="median")), ("model", estimator)])
    raise ValueError(f"Unsupported estimator_type: {model_config.estimator_type}")


def build_prediction_rows(
    df: pd.DataFrame,
    config: ValidationConfig,
    split: dict[str, Any],
    model_config: ModelConfig,
    actual: np.ndarray,
    raw_prediction: np.ndarray,
    constrained_prediction: np.ndarray,
    negative_prediction: np.ndarray,
) -> list[dict[str, Any]]:
    """Build local row-level prediction records."""
    train_df = df.iloc[split["train_index"]]
    test_df = df.iloc[split["test_index"]]
    train_descriptor_keys = set(_descriptor_keys(train_df, config.feature_columns))
    train_formula = _set_if_column(train_df, config.formula_group_column)
    train_chemsys = _set_if_column(train_df, config.chemical_system_group_column)
    rows: list[dict[str, Any]] = []
    for i, (_, row) in enumerate(test_df.iterrows()):
        formula = row.get(config.formula_group_column, "") if config.formula_group_column else ""
        chemsys = (
            row.get(config.chemical_system_group_column, "")
            if config.chemical_system_group_column
            else ""
        )
        descriptor_key = _descriptor_key(row, config.feature_columns)
        absolute_error = abs(actual[i] - constrained_prediction[i])
        rows.append(
            {
                "split_strategy": split["split_strategy"],
                "split_index": split["split_index"],
                "model_variant": model_config.name,
                "material_id": row[config.identifier_column],
                "reduced_formula_group": formula,
                "chemical_system_group": chemsys,
                "theoretical": row.get(config.theoretical_column, pd.NA)
                if config.theoretical_column
                else pd.NA,
                "actual_target": actual[i],
                "raw_prediction": raw_prediction[i],
                "constrained_prediction": constrained_prediction[i],
                "absolute_error": absolute_error,
                "negative_prediction": bool(negative_prediction[i]),
                "descriptor_seen_in_train": descriptor_key in train_descriptor_keys,
                "formula_seen_in_train": formula in train_formula if formula != "" else False,
                "chemical_system_seen_in_train": chemsys in train_chemsys if chemsys != "" else False,
                "ambiguity_group_status": row.get(
                    config.ambiguity_group_column,
                    "unknown",
                )
                if config.ambiguity_group_column
                else "unknown",
            }
        )
    return rows


def compute_metric_bundle(
    *,
    y_true: np.ndarray,
    raw_prediction: np.ndarray,
    constrained_prediction: np.ndarray,
    negative_prediction: np.ndarray,
    prediction_df: pd.DataFrame,
) -> dict[str, Any]:
    """Compute regression and overlap-aware metrics for one fold."""
    tools = _load_sklearn_tools()
    absolute_error = np.abs(y_true - constrained_prediction)
    raw_absolute_error = np.abs(y_true - raw_prediction)
    metrics: dict[str, Any] = {
        "mae": float(tools["mean_absolute_error"](y_true, constrained_prediction)),
        "median_absolute_error": float(np.median(absolute_error)),
        "rmse": float(math.sqrt(tools["mean_squared_error"](y_true, constrained_prediction))),
        "r2": _safe_r2(y_true, constrained_prediction, tools),
        "spearman": _safe_spearman(y_true, constrained_prediction),
        "spearman_status": _spearman_status(y_true, constrained_prediction),
        "prediction_bias_mean": float(np.mean(constrained_prediction - y_true)),
        "negative_prediction_count": int(np.sum(negative_prediction)),
        "negative_prediction_rate": float(np.mean(negative_prediction)) if len(negative_prediction) else np.nan,
        "raw_prediction_mae": float(np.mean(raw_absolute_error)),
        "raw_prediction_rmse": float(math.sqrt(np.mean((y_true - raw_prediction) ** 2))),
        "descriptor_overlap_rows": int(prediction_df["descriptor_seen_in_train"].sum()),
        "descriptor_overlap_rate": float(prediction_df["descriptor_seen_in_train"].mean()),
        "formula_overlap_rows": int(prediction_df["formula_seen_in_train"].sum()),
        "formula_overlap_rate": float(prediction_df["formula_seen_in_train"].mean()),
        "chemical_system_overlap_rows": int(prediction_df["chemical_system_seen_in_train"].sum()),
        "chemical_system_overlap_rate": float(prediction_df["chemical_system_seen_in_train"].mean()),
    }
    for label, mask in [
        ("descriptor_overlap", prediction_df["descriptor_seen_in_train"]),
        ("descriptor_novel", ~prediction_df["descriptor_seen_in_train"]),
    ]:
        subset = prediction_df[mask]
        metrics[f"{label}_row_count"] = int(len(subset))
        metrics[f"{label}_mae"] = (
            float(subset["absolute_error"].mean()) if len(subset) else np.nan
        )
    return metrics


def compute_screening_metrics(prediction_df: pd.DataFrame) -> dict[str, Any]:
    """Compute low-target screening/ranking metrics for one fold."""
    metrics: dict[str, Any] = {}
    for pct in [0.10, 0.20]:
        suffix = "10pct" if pct == 0.10 else "20pct"
        actual_set = _lowest_fraction_ids(prediction_df, "actual_target", pct)
        predicted_set = _lowest_fraction_ids(prediction_df, "constrained_prediction", pct)
        intersection = actual_set.intersection(predicted_set)
        actual_rate = len(actual_set) / len(prediction_df) if len(prediction_df) else np.nan
        precision = len(intersection) / len(predicted_set) if predicted_set else np.nan
        recall = len(intersection) / len(actual_set) if actual_set else np.nan
        metrics[f"precision_at_{suffix}"] = precision
        metrics[f"recall_at_{suffix}"] = recall
        metrics[f"enrichment_factor_at_{suffix}"] = (
            precision / actual_rate if actual_rate and not pd.isna(actual_rate) else np.nan
        )
        zero_ids = set(
            prediction_df.loc[prediction_df["actual_target"].eq(0), "material_id"].astype(str)
        )
        metrics[f"exact_zero_target_recall_at_{suffix}"] = (
            len(zero_ids.intersection(predicted_set)) / len(zero_ids)
            if zero_ids
            else np.nan
        )
    return metrics


def compute_subgroup_metrics(
    prediction_df: pd.DataFrame,
    subgroup_columns: list[str],
) -> dict[str, Any]:
    """Compute compact subgroup metrics for available subgroups."""
    metrics: dict[str, Any] = {}
    for column in subgroup_columns:
        if column not in prediction_df.columns:
            continue
        for value, subgroup in prediction_df.groupby(column, dropna=False):
            label = _clean_metric_label(f"{column}_{value}")
            metrics[f"{label}_count"] = int(len(subgroup))
            if len(subgroup) < 2:
                metrics[f"{label}_mae"] = np.nan
                metrics[f"{label}_median_absolute_error"] = np.nan
                metrics[f"{label}_rmse"] = np.nan
                metrics[f"{label}_r2"] = np.nan
                metrics[f"{label}_spearman"] = np.nan
                metrics[f"{label}_note"] = "too few rows"
                continue
            y_true = subgroup["actual_target"].to_numpy(dtype=float)
            y_pred = subgroup["constrained_prediction"].to_numpy(dtype=float)
            ae = np.abs(y_true - y_pred)
            metrics[f"{label}_mae"] = float(ae.mean())
            metrics[f"{label}_median_absolute_error"] = float(np.median(ae))
            metrics[f"{label}_rmse"] = float(math.sqrt(np.mean((y_true - y_pred) ** 2)))
            metrics[f"{label}_r2"] = _safe_r2(y_true, y_pred, _load_sklearn_tools())
            metrics[f"{label}_spearman"] = _safe_spearman(y_true, y_pred)
            metrics[f"{label}_target_min"] = float(np.min(y_true))
            metrics[f"{label}_target_median"] = float(np.median(y_true))
            metrics[f"{label}_target_max"] = float(np.max(y_true))
            metrics[f"{label}_note"] = ""
    return metrics


def build_split_diagnostics(
    df: pd.DataFrame,
    split: dict[str, Any],
    config: ValidationConfig,
) -> dict[str, Any]:
    """Build split size, overlap, and target distribution diagnostics."""
    if split["status"] != "valid":
        return {
            "split_strategy": split["split_strategy"],
            "split_index": split["split_index"],
            "split_status": "invalid",
            "invalid_reason": split["invalid_reason"],
        }
    train = df.iloc[split["train_index"]]
    test = df.iloc[split["test_index"]]
    material_overlap = _set_if_column(train, config.identifier_column).intersection(
        _set_if_column(test, config.identifier_column)
    )
    formula_overlap = _overlap(train, test, config.formula_group_column)
    chemsys_overlap = _overlap(train, test, config.chemical_system_group_column)
    descriptor_overlap_keys = set(_descriptor_keys(train, config.feature_columns)).intersection(
        set(_descriptor_keys(test, config.feature_columns))
    )
    target_train = pd.to_numeric(train[config.target_column], errors="coerce")
    target_test = pd.to_numeric(test[config.target_column], errors="coerce")
    diagnostics = {
        "split_strategy": split["split_strategy"],
        "split_index": split["split_index"],
        "split_status": "valid",
        "invalid_reason": "",
        "train_row_count": int(len(train)),
        "test_row_count": int(len(test)),
        "train_formula_group_count": _nunique(train, config.formula_group_column),
        "test_formula_group_count": _nunique(test, config.formula_group_column),
        "train_chemical_system_group_count": _nunique(train, config.chemical_system_group_column),
        "test_chemical_system_group_count": _nunique(test, config.chemical_system_group_column),
        "material_id_overlap_count": len(material_overlap),
        "reduced_formula_overlap_count": len(formula_overlap),
        "chemical_system_overlap_count": len(chemsys_overlap),
        "descriptor_vector_overlap_count": len(descriptor_overlap_keys),
        "target_train_min": float(target_train.min()),
        "target_train_median": float(target_train.median()),
        "target_train_max": float(target_train.max()),
        "target_train_variance": float(target_train.var(ddof=0)),
        "target_test_min": float(target_test.min()),
        "target_test_median": float(target_test.median()),
        "target_test_max": float(target_test.max()),
        "target_test_variance": float(target_test.var(ddof=0)),
        "train_theoretical_false_count": _bool_count(train, config.theoretical_column, False),
        "train_theoretical_true_count": _bool_count(train, config.theoretical_column, True),
        "test_theoretical_false_count": _bool_count(test, config.theoretical_column, False),
        "test_theoretical_true_count": _bool_count(test, config.theoretical_column, True),
    }
    if split["split_strategy"] == "reduced_formula_group" and formula_overlap:
        diagnostics["split_status"] = "invalid"
        diagnostics["invalid_reason"] = "reduced_formula_group overlap detected"
    if split["split_strategy"] == "chemical_system_group" and chemsys_overlap:
        diagnostics["split_status"] = "invalid"
        diagnostics["invalid_reason"] = "chemical_system_group overlap detected"
    return diagnostics


def summarize_model_comparison(metrics: pd.DataFrame) -> pd.DataFrame:
    """Summarize fold metrics by split strategy and model variant."""
    metric_columns = [
        "mae",
        "median_absolute_error",
        "rmse",
        "r2",
        "spearman",
        "prediction_bias_mean",
        "negative_prediction_rate",
        "descriptor_overlap_rate",
        "formula_overlap_rate",
        "chemical_system_overlap_rate",
        "descriptor_overlap_mae",
        "descriptor_novel_mae",
    ]
    rows: list[dict[str, Any]] = []
    valid = metrics[metrics["status"].eq("valid")].copy() if "status" in metrics else metrics.copy()
    for (strategy, model_variant), group in valid.groupby(["split_strategy", "model_variant"]):
        for metric in metric_columns:
            if metric not in group.columns:
                continue
            values = pd.to_numeric(group[metric], errors="coerce").dropna()
            if values.empty:
                continue
            rows.append(
                {
                    "strategy": strategy,
                    "model_variant": model_variant,
                    "metric": metric,
                    "mean": float(values.mean()),
                    "median": float(values.median()),
                    "std": float(values.std(ddof=0)),
                    "min": float(values.min()),
                    "max": float(values.max()),
                    "valid_split_count": int(len(values)),
                    "interpretation_flag": _interpretation_flag(strategy, metric, float(values.median())),
                }
            )
    return pd.DataFrame(rows)


def summarize_screening_metrics(screening: pd.DataFrame) -> pd.DataFrame:
    """Summarize screening metrics by split strategy and model variant."""
    rows: list[dict[str, Any]] = []
    if screening.empty:
        return pd.DataFrame(rows)
    metric_columns = [
        column
        for column in screening.columns
        if column not in {"split_strategy", "split_index", "model_variant"}
    ]
    for (strategy, model_variant), group in screening.groupby(["split_strategy", "model_variant"]):
        for metric in metric_columns:
            values = pd.to_numeric(group[metric], errors="coerce").dropna()
            rows.append(
                {
                    "strategy": strategy,
                    "model_variant": model_variant,
                    "metric": metric,
                    "mean": float(values.mean()) if not values.empty else np.nan,
                    "median": float(values.median()) if not values.empty else np.nan,
                    "std": float(values.std(ddof=0)) if not values.empty else np.nan,
                    "min": float(values.min()) if not values.empty else np.nan,
                    "max": float(values.max()) if not values.empty else np.nan,
                    "valid_split_count": int(len(values)),
                    "tie_policy": "sort by metric ascending then material_id for deterministic metric calculation",
                }
            )
    return pd.DataFrame(rows)


def write_outputs(
    outputs: dict[str, pd.DataFrame],
    *,
    predictions_path: str | Path,
    metrics_path: str | Path,
    comparison_path: str | Path,
    split_diagnostics_path: str | Path,
    screening_path: str | Path,
) -> None:
    """Write all validation output CSVs."""
    _write_csv(outputs["predictions"], predictions_path)
    _write_csv(outputs["metrics"], metrics_path)
    _write_csv(outputs["model_comparison"], comparison_path)
    _write_csv(outputs["split_diagnostics"], split_diagnostics_path)
    _write_csv(outputs["screening_metrics"], screening_path)


def _load_sklearn_tools() -> dict[str, Any]:
    try:
        from sklearn.dummy import DummyRegressor
        from sklearn.ensemble import HistGradientBoostingRegressor
        from sklearn.impute import SimpleImputer
        from sklearn.linear_model import Ridge
        from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
        from sklearn.model_selection import GroupShuffleSplit, ShuffleSplit
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import StandardScaler
    except ModuleNotFoundError as exc:  # pragma: no cover
        raise RuntimeError("scikit-learn is required for grouped validation.") from exc
    return {
        "DummyRegressor": DummyRegressor,
        "GroupShuffleSplit": GroupShuffleSplit,
        "HistGradientBoostingRegressor": HistGradientBoostingRegressor,
        "Pipeline": Pipeline,
        "Ridge": Ridge,
        "ShuffleSplit": ShuffleSplit,
        "SimpleImputer": SimpleImputer,
        "StandardScaler": StandardScaler,
        "mean_absolute_error": mean_absolute_error,
        "mean_squared_error": mean_squared_error,
        "r2_score": r2_score,
    }


def _safe_r2(y_true: np.ndarray, y_pred: np.ndarray, tools: dict[str, Any]) -> float:
    if len(y_true) < 2 or np.var(y_true) == 0:
        return np.nan
    return float(tools["r2_score"](y_true, y_pred))


def _safe_spearman(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    if len(y_true) < 2 or len(np.unique(y_true)) < 2 or len(np.unique(y_pred)) < 2:
        return np.nan
    return float(pd.Series(y_true).corr(pd.Series(y_pred), method="spearman"))


def _spearman_status(y_true: np.ndarray, y_pred: np.ndarray) -> str:
    if len(y_true) < 2:
        return "too_few_rows"
    if len(np.unique(y_true)) < 2:
        return "constant_actual"
    if len(np.unique(y_pred)) < 2:
        return "constant_prediction"
    return "computed"


def _lowest_fraction_ids(prediction_df: pd.DataFrame, column: str, fraction: float) -> set[str]:
    n = len(prediction_df)
    if n == 0:
        return set()
    k = max(1, int(math.ceil(n * fraction)))
    ordered = prediction_df.sort_values(
        by=[column, "material_id"],
        ascending=[True, True],
        kind="mergesort",
    )
    return set(ordered.head(k)["material_id"].astype(str))


def _descriptor_key(row: pd.Series, feature_columns: list[str]) -> str:
    values = [f"{float(row[column]):.12g}" for column in feature_columns]
    return "|".join(values)


def _descriptor_keys(df: pd.DataFrame, feature_columns: list[str]) -> list[str]:
    return [_descriptor_key(row, feature_columns) for _, row in df.iterrows()]


def _set_if_column(df: pd.DataFrame, column: str | None) -> set[Any]:
    if column is None or column not in df.columns:
        return set()
    return set(df[column].dropna().astype(str))


def _overlap(train: pd.DataFrame, test: pd.DataFrame, column: str | None) -> set[Any]:
    return _set_if_column(train, column).intersection(_set_if_column(test, column))


def _nunique(df: pd.DataFrame, column: str | None) -> int:
    if column is None or column not in df.columns:
        return 0
    return int(df[column].nunique(dropna=True))


def _bool_count(df: pd.DataFrame, column: str | None, value: bool) -> int:
    if column is None or column not in df.columns:
        return 0
    return int(df[column].eq(value).sum())


def _split_model_keys(split: dict[str, Any], model_config: ModelConfig) -> dict[str, Any]:
    return {
        "split_strategy": split["split_strategy"],
        "split_index": split["split_index"],
        "model_variant": model_config.name,
        "target_treatment": model_config.target_treatment,
    }


def _invalid_metric_row(
    split: dict[str, Any],
    model_config: ModelConfig,
    diagnostics: dict[str, Any],
) -> dict[str, Any]:
    return {
        **_split_model_keys(split, model_config),
        **diagnostics,
        "status": "invalid",
        "invalid_reason": split.get("invalid_reason", "invalid split"),
    }


def _clean_metric_label(label: str) -> str:
    return (
        str(label)
        .lower()
        .replace("=", "_")
        .replace(" ", "_")
        .replace("-", "_")
        .replace("/", "_")
    )


def _interpretation_flag(strategy: str, metric: str, value: float) -> str:
    if metric == "r2" and value < 0:
        return "below_dummy_like_or_unstable"
    if strategy == "random":
        return "interpolation_baseline"
    if strategy == "reduced_formula_group":
        return "unseen_formula_generalization"
    if strategy == "chemical_system_group":
        return "unseen_chemical_system_generalization"
    return "descriptive"


def _write_csv(df: pd.DataFrame, path: str | Path) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output, index=False)

