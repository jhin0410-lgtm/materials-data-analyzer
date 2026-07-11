"""Generic time-aware binary classification validation utilities.

This module is intentionally conservative. It runs fixed classical baselines,
fits every preprocessing step only on the training partition, records weak or
undefined metrics explicitly, and treats random validation only as an
optimistic reference.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ClassificationModelConfig:
    """Fixed baseline model configuration."""

    name: str
    estimator_type: str
    random_state: int = 42


@dataclass(frozen=True)
class ClassificationValidationConfig:
    """Configuration for temporal binary classification validation."""

    case_study_version: str
    source_artifact: str
    source_sha256: str
    identifier_column: str
    target_column: str
    timestamp_column: str
    feature_columns: list[str]
    chronological_rank_column: str = "chronological_rank"
    source_order_column: str = "source_order_index"
    random_state: int = 42
    missing_rate_threshold: float = 0.95
    near_constant_top_value_rate: float = 0.99
    random_test_size: float = 0.2
    model_configs: list[ClassificationModelConfig] | None = None


@dataclass(frozen=True)
class TrainOnlyPreprocessor:
    """Train-fitted numeric preprocessing state."""

    retained_features: list[str]
    removed_features: dict[str, list[str]]
    near_constant_features: list[str]
    medians: pd.Series
    means: pd.Series
    stds: pd.Series
    missing_rates: pd.Series


def calculate_file_sha256(path: str | Path) -> str:
    """Calculate a file SHA-256 digest without modifying the file."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def default_classification_model_configs(
    random_state: int = 42,
) -> list[ClassificationModelConfig]:
    """Return fixed classical binary-classification baseline configs."""
    return [
        ClassificationModelConfig("dummy_prior", "dummy_prior", random_state),
        ClassificationModelConfig(
            "logistic_regression_balanced",
            "logistic_regression",
            random_state,
        ),
        ClassificationModelConfig(
            "random_forest_balanced",
            "random_forest",
            random_state,
        ),
        ClassificationModelConfig(
            "hist_gradient_boosting_balanced",
            "hist_gradient_boosting",
            random_state,
        ),
    ]


def validate_binary_target(df: pd.DataFrame, target_column: str) -> None:
    """Validate that a mapped binary target contains only 0 and 1."""
    if target_column not in df.columns:
        raise ValueError(f"Missing target column: {target_column}")
    values = set(pd.to_numeric(df[target_column], errors="raise").dropna().astype(int))
    if values - {0, 1}:
        raise ValueError(f"Target values must be within {{0, 1}}, found {sorted(values)}")


def validate_feature_columns(df: pd.DataFrame, feature_columns: Iterable[str]) -> None:
    """Validate feature presence and numeric compatibility."""
    missing = [column for column in feature_columns if column not in df.columns]
    if missing:
        raise ValueError("Missing feature column(s): " + ", ".join(missing))
    nonnumeric = [
        column
        for column in feature_columns
        if not pd.api.types.is_numeric_dtype(pd.to_numeric(df[column], errors="coerce"))
    ]
    if nonnumeric:
        raise ValueError("Feature column(s) must be numeric: " + ", ".join(nonnumeric))


def generate_validation_splits(
    df: pd.DataFrame,
    split_plan: pd.DataFrame,
    config: ClassificationValidationConfig,
) -> list[dict[str, Any]]:
    """Generate random-reference and feasible chronological split indexes."""
    tools = _load_sklearn_tools()
    ordered = _chronologically_ordered_index(df, config)
    y = pd.to_numeric(df[config.target_column], errors="raise").astype(int)
    splits: list[dict[str, Any]] = []

    if y.nunique() == 2 and len(df) >= 2:
        splitter = tools["StratifiedShuffleSplit"](
            n_splits=1,
            test_size=config.random_test_size,
            random_state=config.random_state,
        )
        train_index, test_index = next(splitter.split(np.arange(len(df)), y))
        splits.append(
            {
                "split_id": "stratified_random_reference_80_20",
                "split_type": "stratified_random_reference",
                "validation_type": "random_reference",
                "train_index": df.index.to_numpy()[train_index],
                "validation_index": np.array([], dtype=int),
                "test_index": df.index.to_numpy()[test_index],
                "feasibility_status": "feasible",
                "leakage_status": "optimistic_reference_not_primary",
            }
        )

    feasible = split_plan[
        split_plan["feasibility_status"].astype(str).str.lower().eq("feasible")
    ].copy()
    for _, row in feasible.iterrows():
        train_rows = int(row["train_rows"])
        test_rows = int(row["test_rows"])
        if train_rows <= 0 or test_rows <= 0 or train_rows + test_rows > len(ordered):
            splits.append(
                {
                    "split_id": str(row["split_name"]),
                    "split_type": str(row["split_type"]),
                    "validation_type": "primary_temporal",
                    "train_index": np.array([], dtype=int),
                    "validation_index": np.array([], dtype=int),
                    "test_index": np.array([], dtype=int),
                    "feasibility_status": "not_feasible",
                    "leakage_status": "invalid_row_counts",
                }
            )
            continue
        splits.append(
            {
                "split_id": str(row["split_name"]),
                "split_type": str(row["split_type"]),
                "validation_type": "primary_temporal",
                "train_index": ordered[:train_rows],
                "validation_index": np.array([], dtype=int),
                "test_index": ordered[train_rows : train_rows + test_rows],
                "feasibility_status": str(row["feasibility_status"]),
                "leakage_status": str(row.get("leakage_status", "not_recorded")),
            }
        )
    return splits


def evaluate_temporal_classification(
    df: pd.DataFrame,
    split_plan: pd.DataFrame,
    config: ClassificationValidationConfig,
) -> dict[str, pd.DataFrame]:
    """Run fixed baseline models across random and chronological splits."""
    validate_binary_target(df, config.target_column)
    validate_feature_columns(df, config.feature_columns)
    models = config.model_configs or default_classification_model_configs(config.random_state)
    splits = generate_validation_splits(df, split_plan, config)
    metric_rows: list[dict[str, Any]] = []
    prediction_rows: list[dict[str, Any]] = []
    split_rows: list[dict[str, Any]] = []
    threshold_rows: list[dict[str, Any]] = []

    for split in splits:
        diagnostics = build_split_diagnostics(df, split, config)
        split_rows.append(diagnostics)
        split_valid = _split_has_minimum_support(df, split, config)
        for model_config in models:
            if not split_valid["ready"]:
                metric_rows.append(
                    _invalid_metric_row(
                        split,
                        diagnostics,
                        model_config,
                        config,
                        split_valid["reason"],
                    )
                )
                continue
            result = evaluate_model_on_split(df, split, config, model_config, diagnostics)
            metric_rows.append(result["metrics"])
            prediction_rows.extend(result["predictions"])
            threshold_rows.append(result["threshold"])

    predictions = pd.DataFrame(prediction_rows)
    metrics = pd.DataFrame(metric_rows)
    split_diagnostics = pd.DataFrame(split_rows)
    threshold_summary = pd.DataFrame(threshold_rows)
    model_summary = build_model_summary(metrics)
    random_temporal_gap = build_random_temporal_gap(metrics)
    error_structure = build_error_structure_summary(predictions)
    conclusion = build_classification_conclusion(metrics, model_summary, split_diagnostics)
    return {
        "predictions": predictions,
        "metrics": metrics,
        "split_diagnostics": split_diagnostics,
        "model_summary": model_summary,
        "random_temporal_gap": random_temporal_gap,
        "threshold_summary": threshold_summary,
        "error_structure_summary": error_structure,
        "classification_conclusion": conclusion,
    }


def evaluate_model_on_split(
    df: pd.DataFrame,
    split: dict[str, Any],
    config: ClassificationValidationConfig,
    model_config: ClassificationModelConfig,
    diagnostics: dict[str, Any],
) -> dict[str, Any]:
    """Fit one model on one train split and evaluate its holdout rows."""
    tools = _load_sklearn_tools()
    train_df = df.loc[split["train_index"]]
    test_df = df.loc[split["test_index"]]
    y_train = pd.to_numeric(train_df[config.target_column], errors="raise").astype(int)
    y_test = pd.to_numeric(test_df[config.target_column], errors="raise").astype(int)
    preprocessor = fit_train_only_preprocessor(
        train_df[config.feature_columns],
        missing_rate_threshold=config.missing_rate_threshold,
        near_constant_top_value_rate=config.near_constant_top_value_rate,
    )
    if not preprocessor.retained_features and model_config.estimator_type != "dummy_prior":
        return {
            "metrics": _invalid_metric_row(
                split,
                diagnostics,
                model_config,
                config,
                "no_features_retained_after_train_only_preprocessing",
            ),
            "predictions": [],
            "threshold": _invalid_threshold_row(split, diagnostics, model_config, config),
        }

    scale = model_config.estimator_type == "logistic_regression"
    x_train = transform_with_preprocessor(train_df[config.feature_columns], preprocessor, scale=scale)
    x_test = transform_with_preprocessor(test_df[config.feature_columns], preprocessor, scale=scale)
    model = build_classifier(model_config, tools)
    try:
        if model_config.estimator_type == "hist_gradient_boosting":
            weights = tools["compute_sample_weight"]("balanced", y_train)
            model.fit(x_train, y_train, sample_weight=weights)
        else:
            model.fit(x_train, y_train)
        score = _positive_class_score(model, x_test)
    except Exception as exc:  # pragma: no cover - defensive status path
        return {
            "metrics": _invalid_metric_row(
                split,
                diagnostics,
                model_config,
                config,
                f"model_fit_or_score_failed:{type(exc).__name__}",
            ),
            "predictions": [],
            "threshold": _invalid_threshold_row(split, diagnostics, model_config, config),
        }

    predicted_label = (score >= 0.5).astype(int)
    metric_bundle = compute_classification_metrics(y_test.to_numpy(), score, predicted_label)
    threshold_bundle = compute_threshold_metrics(y_test.to_numpy(), score, 0.5)
    preprocessing_summary = _preprocessing_summary(preprocessor, len(config.feature_columns))
    metrics = {
        **_split_model_keys(split, model_config, config),
        **diagnostics,
        **preprocessing_summary,
        **metric_bundle,
        "status": "valid",
        "invalid_reason": "",
    }
    threshold = {
        **_split_model_keys(split, model_config, config),
        **diagnostics,
        **threshold_bundle,
        "threshold_selection_policy": "fixed_default_0_5",
        "threshold_selected_using_test_labels": False,
        "status": "valid",
    }
    predictions = build_prediction_rows(
        test_df=test_df,
        score=score,
        predicted_label=predicted_label,
        split=split,
        model_config=model_config,
        config=config,
        retained_feature_count=len(preprocessor.retained_features),
    )
    return {"metrics": metrics, "predictions": predictions, "threshold": threshold}


def fit_train_only_preprocessor(
    x_train: pd.DataFrame,
    *,
    missing_rate_threshold: float,
    near_constant_top_value_rate: float,
) -> TrainOnlyPreprocessor:
    """Fit feature exclusion, median imputation, and scaling state on train only."""
    numeric = x_train.apply(pd.to_numeric, errors="coerce")
    missing_rates = numeric.isna().mean()
    removed: dict[str, list[str]] = {
        "all_missing": [],
        "high_missing": [],
        "constant": [],
    }
    near_constant: list[str] = []
    retained: list[str] = []
    for column in numeric.columns:
        series = numeric[column]
        nonmissing = series.dropna()
        missing_rate = float(missing_rates[column])
        if nonmissing.empty:
            removed["all_missing"].append(column)
            continue
        if missing_rate >= missing_rate_threshold:
            removed["high_missing"].append(column)
            continue
        if int(nonmissing.nunique()) <= 1:
            removed["constant"].append(column)
            continue
        top_rate = float(nonmissing.value_counts(normalize=True, dropna=True).iloc[0])
        if top_rate >= near_constant_top_value_rate:
            near_constant.append(column)
        retained.append(column)

    retained_df = numeric[retained] if retained else pd.DataFrame(index=numeric.index)
    medians = retained_df.median(axis=0, skipna=True).fillna(0.0)
    imputed = retained_df.fillna(medians)
    means = imputed.mean(axis=0) if retained else pd.Series(dtype=float)
    stds = imputed.std(axis=0, ddof=0).replace(0, 1.0) if retained else pd.Series(dtype=float)
    return TrainOnlyPreprocessor(
        retained_features=retained,
        removed_features=removed,
        near_constant_features=near_constant,
        medians=medians,
        means=means,
        stds=stds,
        missing_rates=missing_rates,
    )


def transform_with_preprocessor(
    x: pd.DataFrame,
    preprocessor: TrainOnlyPreprocessor,
    *,
    scale: bool,
) -> np.ndarray:
    """Apply train-fitted preprocessing to another partition."""
    if not preprocessor.retained_features:
        return np.empty((len(x), 0), dtype=float)
    numeric = x[preprocessor.retained_features].apply(pd.to_numeric, errors="coerce")
    transformed = numeric.fillna(preprocessor.medians)
    if scale:
        transformed = (transformed - preprocessor.means) / preprocessor.stds
    return transformed.to_numpy(dtype=float)


def build_classifier(model_config: ClassificationModelConfig, tools: dict[str, Any]) -> Any:
    """Build one fixed baseline classifier."""
    if model_config.estimator_type == "dummy_prior":
        return tools["DummyClassifier"](strategy="prior")
    if model_config.estimator_type == "logistic_regression":
        return tools["LogisticRegression"](
            class_weight="balanced",
            max_iter=1000,
            solver="liblinear",
            random_state=model_config.random_state,
        )
    if model_config.estimator_type == "random_forest":
        return tools["RandomForestClassifier"](
            n_estimators=60,
            min_samples_leaf=2,
            max_features="sqrt",
            class_weight="balanced_subsample",
            random_state=model_config.random_state,
            n_jobs=1,
        )
    if model_config.estimator_type == "hist_gradient_boosting":
        return tools["HistGradientBoostingClassifier"](
            max_iter=10,
            learning_rate=0.08,
            max_leaf_nodes=15,
            max_bins=32,
            random_state=model_config.random_state,
        )
    raise ValueError(f"Unsupported estimator_type: {model_config.estimator_type}")


def compute_classification_metrics(
    y_true: np.ndarray,
    score: np.ndarray,
    predicted_label: np.ndarray,
) -> dict[str, Any]:
    """Compute threshold-independent and 0.5-threshold metrics."""
    tools = _load_sklearn_tools()
    counts = _confusion_counts(y_true, predicted_label)
    threshold_metrics = _rates_from_counts(counts)
    result: dict[str, Any] = {
        **counts,
        **threshold_metrics,
        "threshold": 0.5,
        "threshold_policy": "fixed_default_0_5",
        "predicted_positive_rate": float(np.mean(predicted_label)) if len(predicted_label) else np.nan,
        "test_prevalence": float(np.mean(y_true)) if len(y_true) else np.nan,
        "average_precision": np.nan,
        "average_precision_status": "unavailable_one_class",
        "roc_auc": np.nan,
        "roc_auc_status": "unavailable_one_class",
        "brier_score": _safe_brier(y_true, score, tools),
        "log_loss": _safe_log_loss(y_true, score, tools),
        "log_loss_status": "valid",
    }
    if len(np.unique(y_true)) == 2:
        result["average_precision"] = float(tools["average_precision_score"](y_true, score))
        result["average_precision_status"] = "valid"
        result["roc_auc"] = float(tools["roc_auc_score"](y_true, score))
        result["roc_auc_status"] = "valid"
    if pd.isna(result["log_loss"]):
        result["log_loss_status"] = "unavailable"
    return result


def compute_threshold_metrics(
    y_true: np.ndarray,
    score: np.ndarray,
    threshold: float,
) -> dict[str, Any]:
    """Compute threshold-dependent metrics for one fixed threshold."""
    predicted = (score >= threshold).astype(int)
    counts = _confusion_counts(y_true, predicted)
    return {
        "threshold": threshold,
        **counts,
        **_rates_from_counts(counts),
        "predicted_positive_rate": float(np.mean(predicted)) if len(predicted) else np.nan,
    }


def build_prediction_rows(
    *,
    test_df: pd.DataFrame,
    score: np.ndarray,
    predicted_label: np.ndarray,
    split: dict[str, Any],
    model_config: ClassificationModelConfig,
    config: ClassificationValidationConfig,
    retained_feature_count: int,
) -> list[dict[str, Any]]:
    """Build local-only row-level prediction diagnostics."""
    rows: list[dict[str, Any]] = []
    feature_missing_rate = test_df[config.feature_columns].isna().mean(axis=1)
    y_true = pd.to_numeric(test_df[config.target_column], errors="raise").astype(int).to_numpy()
    for idx, (_, row) in enumerate(test_df.iterrows()):
        actual = int(y_true[idx])
        predicted = int(predicted_label[idx])
        rows.append(
            {
                "case_study_version": config.case_study_version,
                "source_artifact": config.source_artifact,
                "source_sha256": config.source_sha256,
                "split_id": split["split_id"],
                "split_type": split["split_type"],
                "validation_type": split["validation_type"],
                "model_name": model_config.name,
                "model_type": model_config.estimator_type,
                config.identifier_column: row[config.identifier_column],
                config.timestamp_column: row[config.timestamp_column],
                config.chronological_rank_column: row[config.chronological_rank_column],
                "actual_target": actual,
                "predicted_score": float(score[idx]),
                "predicted_label_0_5": predicted,
                "threshold": 0.5,
                "is_false_positive": bool(actual == 0 and predicted == 1),
                "is_false_negative": bool(actual == 1 and predicted == 0),
                "is_true_positive": bool(actual == 1 and predicted == 1),
                "is_true_negative": bool(actual == 0 and predicted == 0),
                "row_missing_rate": float(feature_missing_rate.iloc[idx]),
                "retained_feature_count": retained_feature_count,
            }
        )
    return rows


def build_split_diagnostics(
    df: pd.DataFrame,
    split: dict[str, Any],
    config: ClassificationValidationConfig,
) -> dict[str, Any]:
    """Build split-level diagnostics for temporal and random validation."""
    train = df.loc[split["train_index"]] if len(split["train_index"]) else df.iloc[0:0]
    validation = (
        df.loc[split["validation_index"]] if len(split["validation_index"]) else df.iloc[0:0]
    )
    test = df.loc[split["test_index"]] if len(split["test_index"]) else df.iloc[0:0]
    train_time = pd.to_datetime(train[config.timestamp_column], errors="coerce")
    validation_time = pd.to_datetime(validation[config.timestamp_column], errors="coerce")
    test_time = pd.to_datetime(test[config.timestamp_column], errors="coerce")
    sample_overlap = int(set(train.index).intersection(set(test.index)).__len__())
    temporal_overlap = _temporal_overlap_status(split, train_time, test_time)
    leakage_status = (
        "no_future_to_past"
        if split["validation_type"] == "primary_temporal"
        and temporal_overlap == "none"
        and sample_overlap == 0
        else split["leakage_status"]
    )
    return {
        "case_study_version": config.case_study_version,
        "source_artifact": config.source_artifact,
        "source_sha256": config.source_sha256,
        "split_id": split["split_id"],
        "split_type": split["split_type"],
        "validation_type": split["validation_type"],
        "train_rows": int(len(train)),
        "validation_rows": int(len(validation)),
        "test_rows": int(len(test)),
        "train_failures": _failure_count(train, config.target_column),
        "validation_failures": _failure_count(validation, config.target_column),
        "test_failures": _failure_count(test, config.target_column),
        "train_time_start": _time_min(train_time),
        "train_time_end": _time_max(train_time),
        "validation_time_start": _time_min(validation_time),
        "validation_time_end": _time_max(validation_time),
        "test_time_start": _time_min(test_time),
        "test_time_end": _time_max(test_time),
        "temporal_overlap": temporal_overlap,
        "sample_overlap_count": sample_overlap,
        "leakage_status": leakage_status,
        "feasibility_status": split["feasibility_status"],
        "primary_evidence": bool(split["validation_type"] == "primary_temporal"),
    }


def build_model_summary(metrics: pd.DataFrame) -> pd.DataFrame:
    """Summarize model evidence conservatively."""
    rows: list[dict[str, Any]] = []
    valid = metrics[metrics["status"].eq("valid")].copy()
    for model_name in sorted(metrics["model_name"].dropna().unique()):
        model_rows = valid[valid["model_name"].eq(model_name)]
        temporal = model_rows[model_rows["validation_type"].eq("primary_temporal")]
        random = model_rows[model_rows["validation_type"].eq("random_reference")]
        final = temporal[temporal["split_id"].astype(str).str.contains("final_holdout")]
        dummy_temporal = valid[
            valid["validation_type"].eq("primary_temporal")
            & valid["model_name"].eq("dummy_prior")
        ]
        dummy_final = dummy_temporal[
            dummy_temporal["split_id"].astype(str).str.contains("final_holdout")
        ]
        temporal_ap = _median_metric(temporal, "average_precision")
        temporal_ap_std = _std_metric(temporal, "average_precision")
        random_ap = _median_metric(random, "average_precision")
        final_ap = _median_metric(final, "average_precision")
        dummy_temporal_ap = _median_metric(dummy_temporal, "average_precision")
        dummy_final_ap = _median_metric(dummy_final, "average_precision")
        improvement = _subtract_or_nan(temporal_ap, dummy_temporal_ap)
        final_improvement = _subtract_or_nan(final_ap, dummy_final_ap)
        status, basis, selected = _model_status(
            model_name=model_name,
            temporal_split_count=int(len(temporal)),
            temporal_ap=temporal_ap,
            temporal_ap_std=temporal_ap_std,
            final_ap=final_ap,
            improvement=improvement,
            final_improvement=final_improvement,
        )
        rows.append(
            {
                "model_name": model_name,
                "model_status": status,
                "selected_representative_model": selected,
                "temporal_split_count": int(len(temporal)),
                "temporal_median_pr_auc": temporal_ap,
                "temporal_pr_auc_std": temporal_ap_std,
                "final_holdout_pr_auc": final_ap,
                "random_reference_pr_auc": random_ap,
                "dummy_temporal_median_pr_auc": dummy_temporal_ap,
                "temporal_pr_auc_improvement_vs_dummy": improvement,
                "final_holdout_pr_auc_improvement_vs_dummy": final_improvement,
                "random_temporal_pr_auc_gap": _subtract_or_nan(random_ap, temporal_ap),
                "median_brier_score": _median_metric(temporal, "brier_score"),
                "median_mcc": _median_metric(temporal, "mcc"),
                "median_recall": _median_metric(temporal, "recall"),
                "median_precision": _median_metric(temporal, "precision"),
                "decision_basis": basis,
            }
        )
    return pd.DataFrame(rows)


def build_random_temporal_gap(metrics: pd.DataFrame) -> pd.DataFrame:
    """Compare random-reference and primary-temporal median metrics."""
    rows: list[dict[str, Any]] = []
    valid = metrics[metrics["status"].eq("valid")]
    for model_name in sorted(valid["model_name"].dropna().unique()):
        model_rows = valid[valid["model_name"].eq(model_name)]
        random = model_rows[model_rows["validation_type"].eq("random_reference")]
        temporal = model_rows[model_rows["validation_type"].eq("primary_temporal")]
        for metric in [
            "average_precision",
            "roc_auc",
            "recall",
            "mcc",
            "brier_score",
        ]:
            random_value = _median_metric(random, metric)
            temporal_value = _median_metric(temporal, metric)
            rows.append(
                {
                    "model_name": model_name,
                    "metric": metric,
                    "random_reference_median": random_value,
                    "temporal_primary_median": temporal_value,
                    "random_minus_temporal_gap": _subtract_or_nan(random_value, temporal_value),
                    "interpretation": _gap_interpretation(metric, random_value, temporal_value),
                }
            )
    return pd.DataFrame(rows)


def build_error_structure_summary(predictions: pd.DataFrame) -> pd.DataFrame:
    """Build compact row-level error-structure summaries."""
    if predictions.empty:
        return pd.DataFrame(
            [
                {
                    "summary_type": "prediction_rows",
                    "model_name": "",
                    "split_id": "",
                    "stratum": "all",
                    "row_count": 0,
                    "status": "no_predictions",
                }
            ]
        )
    rows: list[dict[str, Any]] = []
    frame = predictions.copy()
    frame["observation_timestamp"] = pd.to_datetime(
        frame["observation_timestamp"],
        errors="coerce",
    )
    frame["temporal_block"] = pd.qcut(
        frame["chronological_rank"],
        q=min(4, max(1, frame["chronological_rank"].nunique())),
        labels=False,
        duplicates="drop",
    )
    frame["missingness_quantile"] = pd.qcut(
        frame["row_missing_rate"],
        q=min(4, max(1, frame["row_missing_rate"].nunique())),
        labels=False,
        duplicates="drop",
    )
    for (model_name, split_id), group in frame.groupby(["model_name", "split_id"], dropna=False):
        rows.extend(_error_rows_for_group(group, model_name, split_id, "all", "all"))
        for block, subgroup in group.groupby("temporal_block", dropna=False):
            rows.extend(
                _error_rows_for_group(
                    subgroup,
                    model_name,
                    split_id,
                    "temporal_block",
                    str(block),
                )
            )
        for quantile, subgroup in group.groupby("missingness_quantile", dropna=False):
            rows.extend(
                _error_rows_for_group(
                    subgroup,
                    model_name,
                    split_id,
                    "missingness_quantile",
                    str(quantile),
                )
            )
        for threshold in [0.2, 0.5, 0.8]:
            predicted = (group["predicted_score"].to_numpy(dtype=float) >= threshold).astype(int)
            metrics = compute_threshold_metrics(
                group["actual_target"].to_numpy(dtype=int),
                group["predicted_score"].to_numpy(dtype=float),
                threshold,
            )
            rows.append(
                {
                    "summary_type": "threshold_sensitivity",
                    "model_name": model_name,
                    "split_id": split_id,
                    "stratum": f"threshold={threshold}",
                    "row_count": int(len(group)),
                    "failure_count": int(group["actual_target"].sum()),
                    "false_negative_count": int(((group["actual_target"] == 1) & (predicted == 0)).sum()),
                    "false_positive_count": int(((group["actual_target"] == 0) & (predicted == 1)).sum()),
                    "precision": metrics["precision"],
                    "recall": metrics["recall"],
                    "predicted_positive_rate": metrics["predicted_positive_rate"],
                    "score_median": float(group["predicted_score"].median()),
                    "status": "descriptive",
                }
            )
    return pd.DataFrame(rows)


def build_classification_conclusion(
    metrics: pd.DataFrame,
    model_summary: pd.DataFrame,
    split_diagnostics: pd.DataFrame,
) -> pd.DataFrame:
    """Build a compact claim-boundary and conclusion table."""
    selected = model_summary[model_summary["selected_representative_model"].eq(True)]
    temporal_splits = split_diagnostics[split_diagnostics["validation_type"].eq("primary_temporal")]
    best_temporal_ap = (
        model_summary["temporal_median_pr_auc"].max()
        if "temporal_median_pr_auc" in model_summary
        else np.nan
    )
    rows = [
        (
            "dataset",
            "uci_secom",
            "SECOM fallback is active; Bosch remains blocked pending user action.",
        ),
        (
            "target_definition",
            "target_failure_fail_1_pass_0",
            "Mapped from raw SECOM labels: -1 pass -> 0, 1 fail -> 1.",
        ),
        (
            "primary_evidence",
            "chronological_time_aware_validation",
            f"Primary temporal split count: {len(temporal_splits)}.",
        ),
        (
            "random_reference",
            "optimistic_reference_only",
            "Random split is secondary and must not be used as primary evidence.",
        ),
        (
            "group_aware_evidence",
            "not_available",
            "SECOM lacks explicit equipment, lot, product, or recipe identifiers.",
        ),
        (
            "capability_analysis",
            "not_ready",
            "Specification limits are absent; Cp/Cpk/Pp/Ppk are not computed.",
        ),
        (
            "representative_model_decision",
            "none_selected" if selected.empty else str(selected.iloc[0]["model_name"]),
            "No model is promoted to production readiness; status is conservative.",
        ),
        (
            "best_temporal_median_pr_auc",
            _fmt(best_temporal_ap),
            "Primary metric is average precision / PR-AUC.",
        ),
        (
            "allowed_claim",
            "offline_time_aware_quality_risk_screening_diagnostic",
            "Classical baselines can be compared under chronological holdout.",
        ),
        (
            "prohibited_claim",
            "production_ready_failure_prevention_or_root_cause",
            "No causal, equipment-specific, calibrated production, or real-time control claim is supported.",
        ),
        (
            "calibration_claim",
            "uncalibrated_score_only",
            "Brier score is recorded as a diagnostic; calibrated probability claims are not made.",
        ),
    ]
    return pd.DataFrame(rows, columns=["field", "value", "evidence"])


def write_classification_outputs(
    outputs: dict[str, pd.DataFrame],
    *,
    predictions_path: str | Path,
    metrics_path: str | Path,
    split_diagnostics_path: str | Path,
    model_summary_path: str | Path,
    random_temporal_gap_path: str | Path,
    threshold_summary_path: str | Path,
    error_structure_path: str | Path,
    conclusion_path: str | Path,
) -> None:
    """Write local prediction and compact tracked CSV outputs."""
    path_map = {
        "predictions": predictions_path,
        "metrics": metrics_path,
        "split_diagnostics": split_diagnostics_path,
        "model_summary": model_summary_path,
        "random_temporal_gap": random_temporal_gap_path,
        "threshold_summary": threshold_summary_path,
        "error_structure_summary": error_structure_path,
        "classification_conclusion": conclusion_path,
    }
    for name, path in path_map.items():
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        outputs[name].to_csv(output, index=False)


def _chronologically_ordered_index(
    df: pd.DataFrame,
    config: ClassificationValidationConfig,
) -> np.ndarray:
    sort_columns = [config.chronological_rank_column]
    if config.source_order_column in df.columns:
        sort_columns.append(config.source_order_column)
    return (
        df.sort_values(sort_columns, ascending=True, kind="mergesort")
        .index.to_numpy()
    )


def _split_has_minimum_support(
    df: pd.DataFrame,
    split: dict[str, Any],
    config: ClassificationValidationConfig,
) -> dict[str, Any]:
    train = df.loc[split["train_index"]] if len(split["train_index"]) else df.iloc[0:0]
    test = df.loc[split["test_index"]] if len(split["test_index"]) else df.iloc[0:0]
    if train.empty or test.empty:
        return {"ready": False, "reason": "empty_train_or_test_partition"}
    train_target = pd.to_numeric(train[config.target_column], errors="raise").astype(int)
    test_target = pd.to_numeric(test[config.target_column], errors="raise").astype(int)
    if train_target.nunique() < 2:
        return {"ready": False, "reason": "train_partition_has_one_class"}
    if test_target.sum() < 1:
        return {"ready": False, "reason": "test_partition_has_no_failures"}
    return {"ready": True, "reason": ""}


def _split_model_keys(
    split: dict[str, Any],
    model_config: ClassificationModelConfig,
    config: ClassificationValidationConfig,
) -> dict[str, Any]:
    return {
        "case_study_version": config.case_study_version,
        "source_artifact": config.source_artifact,
        "source_sha256": config.source_sha256,
        "split_id": split["split_id"],
        "split_type": split["split_type"],
        "validation_type": split["validation_type"],
        "model_name": model_config.name,
        "model_type": model_config.estimator_type,
    }


def _invalid_metric_row(
    split: dict[str, Any],
    diagnostics: dict[str, Any],
    model_config: ClassificationModelConfig,
    config: ClassificationValidationConfig,
    reason: str,
) -> dict[str, Any]:
    return {
        **_split_model_keys(split, model_config, config),
        **diagnostics,
        "original_feature_count": len(config.feature_columns),
        "retained_feature_count": 0,
        "removed_all_missing_count": 0,
        "removed_high_missing_count": 0,
        "removed_constant_count": 0,
        "near_constant_retained_count": 0,
        "status": "invalid",
        "invalid_reason": reason,
        "average_precision": np.nan,
        "average_precision_status": "unavailable",
        "roc_auc": np.nan,
        "roc_auc_status": "unavailable",
        "balanced_accuracy": np.nan,
        "mcc": np.nan,
        "f1": np.nan,
        "precision": np.nan,
        "recall": np.nan,
        "specificity": np.nan,
        "negative_predictive_value": np.nan,
        "brier_score": np.nan,
        "log_loss": np.nan,
        "log_loss_status": "unavailable",
    }


def _invalid_threshold_row(
    split: dict[str, Any],
    diagnostics: dict[str, Any],
    model_config: ClassificationModelConfig,
    config: ClassificationValidationConfig,
) -> dict[str, Any]:
    return {
        **_split_model_keys(split, model_config, config),
        **diagnostics,
        "threshold": 0.5,
        "threshold_selection_policy": "fixed_default_0_5",
        "threshold_selected_using_test_labels": False,
        "status": "invalid",
    }


def _preprocessing_summary(
    preprocessor: TrainOnlyPreprocessor,
    original_feature_count: int,
) -> dict[str, Any]:
    return {
        "original_feature_count": original_feature_count,
        "retained_feature_count": len(preprocessor.retained_features),
        "removed_all_missing_count": len(preprocessor.removed_features["all_missing"]),
        "removed_high_missing_count": len(preprocessor.removed_features["high_missing"]),
        "removed_constant_count": len(preprocessor.removed_features["constant"]),
        "near_constant_retained_count": len(preprocessor.near_constant_features),
    }


def _positive_class_score(model: Any, x_test: np.ndarray) -> np.ndarray:
    if hasattr(model, "predict_proba"):
        probabilities = model.predict_proba(x_test)
        classes = list(model.classes_)
        if 1 not in classes:
            return np.zeros(len(x_test), dtype=float)
        return np.asarray(probabilities[:, classes.index(1)], dtype=float)
    if hasattr(model, "decision_function"):
        raw = np.asarray(model.decision_function(x_test), dtype=float)
        return 1.0 / (1.0 + np.exp(-raw))
    return np.asarray(model.predict(x_test), dtype=float)


def _confusion_counts(y_true: np.ndarray, predicted: np.ndarray) -> dict[str, int]:
    tools = _load_sklearn_tools()
    tn, fp, fn, tp = tools["confusion_matrix"](y_true, predicted, labels=[0, 1]).ravel()
    return {
        "true_negative": int(tn),
        "false_positive": int(fp),
        "false_negative": int(fn),
        "true_positive": int(tp),
    }


def _rates_from_counts(counts: dict[str, int]) -> dict[str, float]:
    tp = counts["true_positive"]
    tn = counts["true_negative"]
    fp = counts["false_positive"]
    fn = counts["false_negative"]
    total = tp + tn + fp + fn
    precision = _safe_divide(tp, tp + fp)
    recall = _safe_divide(tp, tp + fn)
    specificity = _safe_divide(tn, tn + fp)
    npv = _safe_divide(tn, tn + fn)
    return {
        "balanced_accuracy": np.nanmean([recall, specificity]),
        "mcc": _mcc(tp, tn, fp, fn),
        "f1": _safe_divide(2 * precision * recall, precision + recall),
        "precision": precision,
        "recall": recall,
        "specificity": specificity,
        "negative_predictive_value": npv,
        "accuracy": _safe_divide(tp + tn, total),
    }


def _mcc(tp: int, tn: int, fp: int, fn: int) -> float:
    denominator = math.sqrt((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn))
    return _safe_divide(tp * tn - fp * fn, denominator)


def _safe_brier(y_true: np.ndarray, score: np.ndarray, tools: dict[str, Any]) -> float:
    try:
        return float(tools["brier_score_loss"](y_true, score))
    except Exception:
        return np.nan


def _safe_log_loss(y_true: np.ndarray, score: np.ndarray, tools: dict[str, Any]) -> float:
    try:
        clipped = np.clip(score, 1e-15, 1 - 1e-15)
        return float(tools["log_loss"](y_true, np.column_stack([1 - clipped, clipped]), labels=[0, 1]))
    except Exception:
        return np.nan


def _safe_divide(numerator: float, denominator: float) -> float:
    if denominator == 0 or pd.isna(denominator):
        return np.nan
    return float(numerator / denominator)


def _failure_count(df: pd.DataFrame, target_column: str) -> int:
    if df.empty or target_column not in df.columns:
        return 0
    return int(pd.to_numeric(df[target_column], errors="coerce").fillna(0).sum())


def _time_min(times: pd.Series) -> str:
    valid = times.dropna()
    return "" if valid.empty else str(valid.min())


def _time_max(times: pd.Series) -> str:
    valid = times.dropna()
    return "" if valid.empty else str(valid.max())


def _temporal_overlap_status(
    split: dict[str, Any],
    train_time: pd.Series,
    test_time: pd.Series,
) -> str:
    if split["validation_type"] == "random_reference":
        return "not_applicable_random_reference"
    if train_time.dropna().empty or test_time.dropna().empty:
        return "unknown_missing_time"
    return "overlap" if train_time.max() > test_time.min() else "none"


def _median_metric(df: pd.DataFrame, metric: str) -> float:
    if df.empty or metric not in df.columns:
        return np.nan
    values = pd.to_numeric(df[metric], errors="coerce").dropna()
    return float(values.median()) if len(values) else np.nan


def _std_metric(df: pd.DataFrame, metric: str) -> float:
    if df.empty or metric not in df.columns:
        return np.nan
    values = pd.to_numeric(df[metric], errors="coerce").dropna()
    return float(values.std(ddof=0)) if len(values) else np.nan


def _subtract_or_nan(left: float, right: float) -> float:
    if pd.isna(left) or pd.isna(right):
        return np.nan
    return float(left - right)


def _model_status(
    *,
    model_name: str,
    temporal_split_count: int,
    temporal_ap: float,
    temporal_ap_std: float,
    final_ap: float,
    improvement: float,
    final_improvement: float,
) -> tuple[str, str, bool]:
    if model_name == "dummy_prior":
        return "descriptive_only", "prior baseline used for reference only", False
    if temporal_split_count < 2 or pd.isna(temporal_ap):
        return "descriptive_only", "insufficient temporal validation support", False
    if pd.isna(improvement) or improvement <= 0.02:
        return "diagnostic_only", "temporal PR-AUC improvement over dummy is small", False
    if pd.isna(final_ap) or pd.isna(final_improvement) or final_improvement <= 0:
        return "diagnostic_only", "final chronological holdout does not improve over dummy", False
    if pd.notna(temporal_ap_std) and temporal_ap_std > 0.20:
        return "limited_predictive_evidence", "temporal performance varies materially across folds", False
    return "limited_predictive_evidence", "limited time-aware signal; further validation required", False


def _gap_interpretation(metric: str, random_value: float, temporal_value: float) -> str:
    if pd.isna(random_value) or pd.isna(temporal_value):
        return "insufficient_metric_support"
    gap = random_value - temporal_value
    if metric == "brier_score":
        gap = temporal_value - random_value
    if gap > 0.10:
        return "large_random_temporal_gap_possible_nonstationarity"
    if gap > 0.03:
        return "moderate_random_temporal_gap"
    return "no_large_gap_signal"


def _error_rows_for_group(
    group: pd.DataFrame,
    model_name: str,
    split_id: str,
    summary_type: str,
    stratum: str,
) -> list[dict[str, Any]]:
    score = group["predicted_score"].to_numpy(dtype=float)
    actual = group["actual_target"].to_numpy(dtype=int)
    predicted = group["predicted_label_0_5"].to_numpy(dtype=int)
    metrics = compute_classification_metrics(actual, score, predicted)
    return [
        {
            "summary_type": summary_type,
            "model_name": model_name,
            "split_id": split_id,
            "stratum": stratum,
            "row_count": int(len(group)),
            "failure_count": int(group["actual_target"].sum()),
            "failure_rate": float(group["actual_target"].mean()) if len(group) else np.nan,
            "false_negative_count": int(group["is_false_negative"].sum()),
            "false_positive_count": int(group["is_false_positive"].sum()),
            "precision": metrics["precision"],
            "recall": metrics["recall"],
            "average_precision": metrics["average_precision"],
            "mcc": metrics["mcc"],
            "score_min": float(np.min(score)) if len(score) else np.nan,
            "score_median": float(np.median(score)) if len(score) else np.nan,
            "score_max": float(np.max(score)) if len(score) else np.nan,
            "row_missing_rate_median": float(group["row_missing_rate"].median()) if len(group) else np.nan,
            "retained_feature_count_median": float(group["retained_feature_count"].median()) if len(group) else np.nan,
            "timestamp_start": _time_min(group["observation_timestamp"]),
            "timestamp_end": _time_max(group["observation_timestamp"]),
            "status": "descriptive",
        }
    ]


def _fmt(value: float) -> str:
    return "nan" if pd.isna(value) else f"{float(value):.6g}"


def _load_sklearn_tools() -> dict[str, Any]:
    try:
        from sklearn.dummy import DummyClassifier
        from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
        from sklearn.linear_model import LogisticRegression
        from sklearn.metrics import (
            average_precision_score,
            brier_score_loss,
            confusion_matrix,
            log_loss,
            roc_auc_score,
        )
        from sklearn.model_selection import StratifiedShuffleSplit
        from sklearn.utils.class_weight import compute_sample_weight
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise ImportError("scikit-learn is required for temporal classification validation.") from exc
    return {
        "DummyClassifier": DummyClassifier,
        "HistGradientBoostingClassifier": HistGradientBoostingClassifier,
        "LogisticRegression": LogisticRegression,
        "RandomForestClassifier": RandomForestClassifier,
        "StratifiedShuffleSplit": StratifiedShuffleSplit,
        "average_precision_score": average_precision_score,
        "brier_score_loss": brier_score_loss,
        "confusion_matrix": confusion_matrix,
        "compute_sample_weight": compute_sample_weight,
        "log_loss": log_loss,
        "roc_auc_score": roc_auc_score,
    }
