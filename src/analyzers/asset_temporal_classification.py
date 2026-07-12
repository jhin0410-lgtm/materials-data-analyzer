"""Asset/time-aware fixed baseline classification utilities.

This module evaluates binary horizon-risk baselines under asset-disjoint,
time-aware, combined asset/time, and random-reference validation. It is generic
and does not hard-code Backblaze paths or SMART feature names.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from .temporal_classification_validation import (
    compute_classification_metrics,
    compute_threshold_metrics,
)


@dataclass(frozen=True)
class FeatureSetConfig:
    """A fixed feature set for baseline evaluation."""

    name: str
    numeric_features: tuple[str, ...]
    categorical_features: tuple[str, ...] = ()


@dataclass(frozen=True)
class AssetTemporalModelConfig:
    """A fixed classical model configuration."""

    name: str
    estimator_type: str
    random_state: int = 42
    max_training_rows: int | None = None


@dataclass(frozen=True)
class ResourceBudget:
    """Resource controls for deterministic training subsampling."""

    max_training_rows: int = 200_000
    random_state: int = 42
    prediction_sample_max_rows: int = 20_000


@dataclass(frozen=True)
class AssetTemporalClassificationConfig:
    """Configuration for asset/time-aware binary horizon-risk validation."""

    case_study_version: str
    source_artifact: str
    source_sha256: str
    asset_column: str
    timestamp_column: str
    target_column: str
    feature_sets: tuple[FeatureSetConfig, ...]
    model_configs: tuple[AssetTemporalModelConfig, ...]
    final_holdout_start: str
    random_state: int = 42
    missing_rate_threshold: float = 0.95
    near_constant_top_value_rate: float = 0.99
    asset_test_size: float = 0.2
    random_test_size: float = 0.2
    primary_weighting_policy: str = "asset_balanced"
    weighting_policies: tuple[str, ...] = ("asset_balanced", "raw_row")
    resource_budget: ResourceBudget = ResourceBudget()


@dataclass(frozen=True)
class TabularPreprocessor:
    """Train-fitted preprocessing state for numeric and categorical features."""

    retained_numeric_features: list[str]
    categorical_features: list[str]
    category_vocabularies: dict[str, list[str]]
    removed_features: dict[str, list[str]]
    near_constant_features: list[str]
    medians: pd.Series
    means: pd.Series
    stds: pd.Series


def default_asset_temporal_model_configs(
    random_state: int = 42,
) -> tuple[AssetTemporalModelConfig, ...]:
    """Return fixed baseline model configs for v1.5 reliability classification."""
    return (
        AssetTemporalModelConfig("dummy_prior", "dummy_prior", random_state, None),
        AssetTemporalModelConfig(
            "logistic_regression",
            "logistic_regression",
            random_state,
            250_000,
        ),
        AssetTemporalModelConfig(
            "random_forest",
            "random_forest",
            random_state,
            120_000,
        ),
        AssetTemporalModelConfig(
            "hist_gradient_boosting",
            "hist_gradient_boosting",
            random_state,
            200_000,
        ),
    )


def evaluate_asset_temporal_classification(
    df: pd.DataFrame,
    config: AssetTemporalClassificationConfig,
) -> dict[str, pd.DataFrame]:
    """Evaluate fixed baselines under asset/time-aware validation."""
    validate_input_frame(df, config)
    splits = build_asset_time_splits(df, config)
    metric_rows: list[dict[str, Any]] = []
    split_rows: list[dict[str, Any]] = []
    threshold_rows: list[dict[str, Any]] = []
    top_risk_rows: list[dict[str, Any]] = []
    prediction_rows: list[dict[str, Any]] = []
    error_rows: list[dict[str, Any]] = []

    for split in splits:
        diagnostics = build_split_diagnostics(df, split, config)
        split_rows.append(diagnostics)
        split_ready = split_support_status(df, split, config)
        for feature_set in config.feature_sets:
            for weighting_policy in config.weighting_policies:
                for model_config in config.model_configs:
                    keys = _keys(split, feature_set, weighting_policy, model_config, config)
                    if not split_ready["ready"]:
                        metric_rows.append(
                            _status_metric_row(
                                keys,
                                diagnostics,
                                "invalid",
                                split_ready["reason"],
                            )
                        )
                        continue
                    result = evaluate_one_run(
                        df=df,
                        split=split,
                        diagnostics=diagnostics,
                        feature_set=feature_set,
                        weighting_policy=weighting_policy,
                        model_config=model_config,
                        config=config,
                    )
                    metric_rows.append(result["metrics"])
                    threshold_rows.append(result["threshold"])
                    top_risk_rows.extend(result["top_risk"])
                    prediction_rows.extend(result["prediction_sample"])
                    error_rows.extend(result["error_structure"])

    outputs = {
        "metrics": pd.DataFrame(metric_rows),
        "split_diagnostics": pd.DataFrame(split_rows),
        "threshold_summary": pd.DataFrame(threshold_rows),
        "top_risk_summary": pd.DataFrame(top_risk_rows),
        "prediction_sample": pd.DataFrame(prediction_rows),
        "error_structure_summary": pd.DataFrame(error_rows),
    }
    outputs["model_summary"] = build_model_summary(outputs["metrics"])
    outputs["asset_time_gap_summary"] = build_asset_time_gap_summary(outputs["metrics"])
    outputs["classification_conclusion"] = build_classification_conclusion(
        outputs["metrics"],
        outputs["model_summary"],
        outputs["split_diagnostics"],
    )
    return outputs


def validate_input_frame(df: pd.DataFrame, config: AssetTemporalClassificationConfig) -> None:
    """Validate target, timestamp, asset, and feature-set columns."""
    required = [config.asset_column, config.timestamp_column, config.target_column]
    for feature_set in config.feature_sets:
        required.extend(feature_set.numeric_features)
        required.extend(feature_set.categorical_features)
    missing = [column for column in sorted(set(required)) if column not in df.columns]
    if missing:
        raise ValueError("Missing required column(s): " + ", ".join(missing))
    values = set(pd.to_numeric(df[config.target_column], errors="raise").astype(int).unique())
    if values - {0, 1}:
        raise ValueError(f"{config.target_column} must contain only 0 and 1")
    parsed = pd.to_datetime(df[config.timestamp_column], errors="raise")
    if parsed.isna().any():
        raise ValueError(f"{config.timestamp_column} contains unparsable values")


def build_asset_time_splits(
    df: pd.DataFrame,
    config: AssetTemporalClassificationConfig,
) -> list[dict[str, Any]]:
    """Build deterministic asset-disjoint, time-aware, combined, and random splits."""
    tools = _load_sklearn_tools()
    frame = df.copy()
    frame["_timestamp"] = pd.to_datetime(frame[config.timestamp_column], errors="raise")
    target = pd.to_numeric(frame[config.target_column], errors="raise").astype(int)
    assets = frame[config.asset_column].astype(str)
    asset_target = target.groupby(assets).max().sort_index()
    splits: list[dict[str, Any]] = []

    asset_train, asset_test = _asset_train_test_split(asset_target, config, tools)
    splits.append(
        _split_from_masks(
            frame,
            train_mask=assets.isin(asset_train),
            test_mask=assets.isin(asset_test),
            split_id="asset_disjoint_stratified_80_20",
            split_type="asset_disjoint",
            validation_type="primary_asset_disjoint",
            claim_scope="unseen_asset_generalization",
            leakage_status="asset_overlap_0",
        )
    )

    cutoff = pd.Timestamp(config.final_holdout_start)
    splits.append(
        _split_from_masks(
            frame,
            train_mask=frame["_timestamp"] < cutoff,
            test_mask=frame["_timestamp"] >= cutoff,
            split_id="final_month_holdout",
            split_type="time_aware",
            validation_type="primary_time_aware",
            claim_scope="future_known_population_prediction",
            leakage_status="future_dates_test_only",
        )
    )

    future_assets = assets[frame["_timestamp"] >= cutoff]
    future_asset_target = target[frame["_timestamp"] >= cutoff].groupby(future_assets).max()
    combined_test_assets = _safe_asset_sample(
        future_asset_target,
        test_size=config.asset_test_size,
        random_state=config.random_state + 17,
        tools=tools,
    )
    splits.append(
        _split_from_masks(
            frame,
            train_mask=(frame["_timestamp"] < cutoff) & ~assets.isin(combined_test_assets),
            test_mask=(frame["_timestamp"] >= cutoff) & assets.isin(combined_test_assets),
            split_id="combined_asset_disjoint_future_holdout",
            split_type="combined_asset_time",
            validation_type="primary_combined_asset_time",
            claim_scope="future_unseen_asset_generalization",
            leakage_status="asset_overlap_0_and_future_dates_test_only",
        )
    )

    if len(df) >= 2 and target.nunique() == 2:
        splitter = tools["StratifiedShuffleSplit"](
            n_splits=1,
            test_size=config.random_test_size,
            random_state=config.random_state,
        )
        train_pos, test_pos = next(splitter.split(np.arange(len(df)), target))
        splits.append(
            {
                "split_id": "stratified_random_row_reference_80_20",
                "split_type": "random_row_reference",
                "validation_type": "optimistic_random_reference",
                "claim_scope": "optimistic_reference_only",
                "leakage_status": "same_asset_and_temporal_mixing_possible",
                "train_index": frame.index.to_numpy()[train_pos],
                "test_index": frame.index.to_numpy()[test_pos],
            }
        )
    return splits


def evaluate_one_run(
    *,
    df: pd.DataFrame,
    split: dict[str, Any],
    diagnostics: dict[str, Any],
    feature_set: FeatureSetConfig,
    weighting_policy: str,
    model_config: AssetTemporalModelConfig,
    config: AssetTemporalClassificationConfig,
) -> dict[str, Any]:
    """Fit one fixed model/feature/weighting configuration and evaluate full test."""
    tools = _load_sklearn_tools()
    train_df = df.loc[split["train_index"]]
    test_df = df.loc[split["test_index"]]
    keys = _keys(split, feature_set, weighting_policy, model_config, config)
    preprocessor = fit_train_only_preprocessor(
        train_df,
        numeric_features=list(feature_set.numeric_features),
        categorical_features=list(feature_set.categorical_features),
        missing_rate_threshold=config.missing_rate_threshold,
        near_constant_top_value_rate=config.near_constant_top_value_rate,
    )
    if (
        not preprocessor.retained_numeric_features
        and not preprocessor.categorical_features
        and model_config.estimator_type != "dummy_prior"
    ):
        return {
            "metrics": _status_metric_row(
                keys,
                diagnostics,
                "invalid",
                "no_features_retained_after_train_only_preprocessing",
            ),
            "threshold": _invalid_threshold_row(keys, diagnostics),
            "top_risk": [],
            "prediction_sample": [],
            "error_structure": [],
        }
    fit_train_df, subsample = deterministic_training_subsample(
        train_df,
        target_column=config.target_column,
        asset_column=config.asset_column,
        model_config=model_config,
        budget=config.resource_budget,
    )
    y_fit = pd.to_numeric(fit_train_df[config.target_column], errors="raise").astype(int)
    y_test = pd.to_numeric(test_df[config.target_column], errors="raise").astype(int)
    sample_weight = build_training_sample_weight(
        fit_train_df,
        target_column=config.target_column,
        asset_column=config.asset_column,
        weighting_policy=weighting_policy,
    )
    scale = model_config.estimator_type == "logistic_regression"
    x_fit = transform_with_preprocessor(fit_train_df, preprocessor, scale=scale)
    x_test = transform_with_preprocessor(test_df, preprocessor, scale=scale)
    model = build_classifier(model_config, tools)
    try:
        if model_config.estimator_type == "dummy_prior":
            model.fit(np.zeros((len(y_fit), 1)), y_fit, sample_weight=sample_weight)
            score = _positive_class_score(model, np.zeros((len(y_test), 1)))
        else:
            model.fit(x_fit, y_fit, sample_weight=sample_weight)
            score = _positive_class_score(model, x_test)
    except Exception as exc:  # pragma: no cover - defensive path for local runs
        return {
            "metrics": _status_metric_row(
                keys,
                diagnostics,
                "invalid",
                f"model_fit_or_score_failed:{type(exc).__name__}",
            ),
            "threshold": _invalid_threshold_row(keys, diagnostics),
            "top_risk": [],
            "prediction_sample": [],
            "error_structure": [],
        }

    predicted = (score >= 0.5).astype(int)
    metrics = {
        **keys,
        **diagnostics,
        **_preprocessing_summary(preprocessor, feature_set),
        **subsample,
        **compute_classification_metrics(y_test.to_numpy(dtype=int), score, predicted),
        "status": "valid",
        "invalid_reason": "",
    }
    threshold = {
        **keys,
        **diagnostics,
        **subsample,
        **compute_threshold_metrics(y_test.to_numpy(dtype=int), score, 0.5),
        "threshold_selection_policy": "fixed_default_0_5",
        "threshold_selected_using_test_labels": False,
        "status": "valid",
    }
    top_risk = build_top_risk_rows(test_df, y_test.to_numpy(dtype=int), score, keys, diagnostics)
    prediction_sample = build_prediction_sample(
        test_df,
        y_test.to_numpy(dtype=int),
        score,
        predicted,
        keys,
        config,
        max_rows=config.resource_budget.prediction_sample_max_rows,
    )
    error_structure = build_error_structure_rows(test_df, y_test.to_numpy(dtype=int), score, predicted, keys)
    return {
        "metrics": metrics,
        "threshold": threshold,
        "top_risk": top_risk,
        "prediction_sample": prediction_sample,
        "error_structure": error_structure,
    }


def fit_train_only_preprocessor(
    df: pd.DataFrame,
    *,
    numeric_features: list[str],
    categorical_features: list[str],
    missing_rate_threshold: float,
    near_constant_top_value_rate: float,
) -> TabularPreprocessor:
    """Fit numeric filtering/imputation/scaling and categorical vocabulary on train only."""
    numeric = df[numeric_features].apply(pd.to_numeric, errors="coerce") if numeric_features else pd.DataFrame(index=df.index)
    missing_rates = numeric.isna().mean() if numeric_features else pd.Series(dtype=float)
    removed = {"all_missing": [], "high_missing": [], "constant": []}
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
    retained_df = numeric[retained] if retained else pd.DataFrame(index=df.index)
    medians = retained_df.median(axis=0, skipna=True).fillna(0.0)
    imputed = retained_df.fillna(medians)
    means = imputed.mean(axis=0) if retained else pd.Series(dtype=float)
    stds = imputed.std(axis=0, ddof=0).replace(0, 1.0) if retained else pd.Series(dtype=float)
    vocabularies = {
        column: sorted(df[column].fillna("__missing__").astype(str).unique().tolist())
        for column in categorical_features
    }
    return TabularPreprocessor(
        retained_numeric_features=retained,
        categorical_features=categorical_features,
        category_vocabularies=vocabularies,
        removed_features=removed,
        near_constant_features=near_constant,
        medians=medians,
        means=means,
        stds=stds,
    )


def transform_with_preprocessor(
    df: pd.DataFrame,
    preprocessor: TabularPreprocessor,
    *,
    scale: bool,
) -> np.ndarray:
    """Apply train-fitted preprocessing state to train or holdout rows."""
    parts: list[np.ndarray] = []
    if preprocessor.retained_numeric_features:
        numeric = df[preprocessor.retained_numeric_features].apply(pd.to_numeric, errors="coerce")
        transformed = numeric.fillna(preprocessor.medians)
        if scale:
            transformed = (transformed - preprocessor.means) / preprocessor.stds
        parts.append(transformed.to_numpy(dtype=float))
    for column in preprocessor.categorical_features:
        values = df[column].fillna("__missing__").astype(str)
        vocabulary = preprocessor.category_vocabularies[column]
        encoded = np.zeros((len(values), len(vocabulary) + 1), dtype=float)
        position = {value: idx for idx, value in enumerate(vocabulary)}
        unknown_idx = len(vocabulary)
        for row_idx, value in enumerate(values):
            encoded[row_idx, position.get(value, unknown_idx)] = 1.0
        parts.append(encoded)
    if not parts:
        return np.empty((len(df), 0), dtype=float)
    return np.hstack(parts)


def deterministic_training_subsample(
    train_df: pd.DataFrame,
    *,
    target_column: str,
    asset_column: str,
    model_config: AssetTemporalModelConfig,
    budget: ResourceBudget,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Subsample training rows only when a model-specific resource cap applies."""
    cap = model_config.max_training_rows or budget.max_training_rows
    if model_config.estimator_type == "dummy_prior" or len(train_df) <= cap:
        return train_df, {
            "training_subsample_status": "not_subsampled",
            "fit_train_rows": int(len(train_df)),
            "fit_train_assets": int(train_df[asset_column].nunique()),
            "fit_train_positives": int(pd.to_numeric(train_df[target_column]).sum()),
            "test_set_subsampled": False,
        }
    y = pd.to_numeric(train_df[target_column], errors="raise").astype(int)
    positive = train_df[y.eq(1)]
    negative = train_df[y.eq(0)]
    remaining = max(cap - len(positive), 0)
    if remaining <= 0:
        sampled = positive.sort_values([asset_column]).head(cap)
    else:
        sampled_negative = _deterministic_row_sample(
            negative,
            n=min(remaining, len(negative)),
            columns=[asset_column, "prediction_origin"],
            random_state=model_config.random_state,
        )
        sampled = pd.concat([positive, sampled_negative], axis=0).sort_index(kind="mergesort")
    return sampled, {
        "training_subsample_status": "subsampled_training",
        "fit_train_rows": int(len(sampled)),
        "fit_train_assets": int(sampled[asset_column].nunique()),
        "fit_train_positives": int(pd.to_numeric(sampled[target_column]).sum()),
        "test_set_subsampled": False,
    }


def build_training_sample_weight(
    train_df: pd.DataFrame,
    *,
    target_column: str,
    asset_column: str,
    weighting_policy: str,
) -> np.ndarray:
    """Build class-imbalance and repeated-origin sample weights."""
    y = pd.to_numeric(train_df[target_column], errors="raise").astype(int)
    class_counts = y.value_counts().to_dict()
    total = len(y)
    class_weight = {
        cls: total / (2.0 * count) if count else 1.0
        for cls, count in class_counts.items()
    }
    weights = y.map(class_weight).astype(float).to_numpy()
    if weighting_policy == "asset_balanced":
        asset_counts = train_df[asset_column].astype(str).value_counts()
        asset_weight = train_df[asset_column].astype(str).map(lambda value: 1.0 / asset_counts[value])
        asset_weight = asset_weight.to_numpy(dtype=float)
        asset_weight = asset_weight / np.mean(asset_weight)
        weights = weights * asset_weight
    elif weighting_policy != "raw_row":
        raise ValueError(f"Unsupported weighting_policy: {weighting_policy}")
    return weights


def build_classifier(model_config: AssetTemporalModelConfig, tools: dict[str, Any]) -> Any:
    """Build one fixed classifier without hyperparameter search."""
    if model_config.estimator_type == "dummy_prior":
        return tools["DummyClassifier"](strategy="prior")
    if model_config.estimator_type == "logistic_regression":
        return tools["LogisticRegression"](
            max_iter=300,
            solver="liblinear",
            random_state=model_config.random_state,
        )
    if model_config.estimator_type == "random_forest":
        return tools["RandomForestClassifier"](
            n_estimators=12,
            max_depth=10,
            min_samples_leaf=5,
            max_features="sqrt",
            random_state=model_config.random_state,
            n_jobs=1,
        )
    if model_config.estimator_type == "hist_gradient_boosting":
        return tools["HistGradientBoostingClassifier"](
            max_iter=20,
            learning_rate=0.08,
            max_leaf_nodes=15,
            max_bins=32,
            random_state=model_config.random_state,
        )
    raise ValueError(f"Unsupported estimator_type: {model_config.estimator_type}")


def build_split_diagnostics(
    df: pd.DataFrame,
    split: dict[str, Any],
    config: AssetTemporalClassificationConfig,
) -> dict[str, Any]:
    """Build compact split diagnostics with overlap and time ordering checks."""
    train = df.loc[split["train_index"]]
    test = df.loc[split["test_index"]]
    train_assets = set(train[config.asset_column].astype(str))
    test_assets = set(test[config.asset_column].astype(str))
    train_time = pd.to_datetime(train[config.timestamp_column], errors="coerce")
    test_time = pd.to_datetime(test[config.timestamp_column], errors="coerce")
    asset_overlap = len(train_assets.intersection(test_assets))
    temporal_overlap = _temporal_overlap(train_time, test_time)
    return {
        "case_study_version": config.case_study_version,
        "source_artifact": config.source_artifact,
        "source_sha256": config.source_sha256,
        "split_id": split["split_id"],
        "split_type": split["split_type"],
        "validation_type": split["validation_type"],
        "claim_scope": split["claim_scope"],
        "train_rows": int(len(train)),
        "validation_rows": 0,
        "test_rows": int(len(test)),
        "train_assets": int(len(train_assets)),
        "validation_assets": 0,
        "test_assets": int(len(test_assets)),
        "train_positives": int(pd.to_numeric(train[config.target_column]).sum()),
        "validation_positives": 0,
        "test_positives": int(pd.to_numeric(test[config.target_column]).sum()),
        "train_positive_assets": int(train.loc[pd.to_numeric(train[config.target_column]).eq(1), config.asset_column].nunique()),
        "test_positive_assets": int(test.loc[pd.to_numeric(test[config.target_column]).eq(1), config.asset_column].nunique()),
        "train_date_start": _time_min(train_time),
        "train_date_end": _time_max(train_time),
        "test_date_start": _time_min(test_time),
        "test_date_end": _time_max(test_time),
        "asset_overlap_count": int(asset_overlap),
        "temporal_overlap": temporal_overlap,
        "sample_overlap_count": int(set(split["train_index"]).intersection(set(split["test_index"])).__len__()),
        "leakage_status": _leakage_status(split, asset_overlap, temporal_overlap),
        "feasibility_status": "feasible",
        "primary_evidence": not split["validation_type"].startswith("optimistic"),
    }


def split_support_status(
    df: pd.DataFrame,
    split: dict[str, Any],
    config: AssetTemporalClassificationConfig,
) -> dict[str, Any]:
    """Check minimum train/test support before fitting."""
    train = df.loc[split["train_index"]]
    test = df.loc[split["test_index"]]
    if train.empty or test.empty:
        return {"ready": False, "reason": "empty_train_or_test"}
    y_train = pd.to_numeric(train[config.target_column], errors="raise").astype(int)
    y_test = pd.to_numeric(test[config.target_column], errors="raise").astype(int)
    if y_train.nunique() < 2:
        return {"ready": False, "reason": "train_partition_one_class"}
    if y_test.sum() < 1:
        return {"ready": False, "reason": "test_partition_no_positives"}
    return {"ready": True, "reason": ""}


def build_top_risk_rows(
    test_df: pd.DataFrame,
    y_true: np.ndarray,
    score: np.ndarray,
    keys: dict[str, Any],
    diagnostics: dict[str, Any],
) -> list[dict[str, Any]]:
    """Calculate fixed top-risk fraction diagnostics without threshold tuning."""
    rows: list[dict[str, Any]] = []
    total_positives = int(np.sum(y_true))
    if len(score) == 0:
        return rows
    order = np.argsort(-score, kind="mergesort")
    asset_values = test_df["asset_id_hash"].astype(str).to_numpy() if "asset_id_hash" in test_df else None
    positive_assets_total = (
        len(set(asset_values[y_true == 1])) if asset_values is not None else 0
    )
    prevalence = float(np.mean(y_true)) if len(y_true) else np.nan
    for fraction in [0.001, 0.005, 0.01, 0.05]:
        top_n = max(1, int(math.ceil(len(score) * fraction)))
        top_idx = order[:top_n]
        positives = int(np.sum(y_true[top_idx]))
        positive_assets = (
            len(set(asset_values[top_idx][y_true[top_idx] == 1]))
            if asset_values is not None
            else 0
        )
        precision = positives / top_n if top_n else np.nan
        rows.append(
            {
                **keys,
                "split_rows": diagnostics["test_rows"],
                "top_fraction": fraction,
                "top_n": top_n,
                "positive_rows_in_top": positives,
                "precision_at_top_fraction": precision,
                "lift_over_prevalence": precision / prevalence if prevalence and prevalence > 0 else np.nan,
                "failed_asset_capture_rate": (
                    positive_assets / positive_assets_total
                    if positive_assets_total
                    else np.nan
                ),
                "status": "valid",
            }
        )
    return rows


def build_prediction_sample(
    test_df: pd.DataFrame,
    y_true: np.ndarray,
    score: np.ndarray,
    predicted: np.ndarray,
    keys: dict[str, Any],
    config: AssetTemporalClassificationConfig,
    *,
    max_rows: int,
) -> list[dict[str, Any]]:
    """Build deterministic local-only prediction diagnostics sample."""
    if len(test_df) == 0:
        return []
    frame = test_df[[config.timestamp_column, "asset_id_hash"]].copy()
    frame["_target"] = y_true
    frame["_score"] = score
    frame["_predicted"] = predicted
    positives = frame[frame["_target"].eq(1)]
    remaining = max(max_rows - len(positives), 0)
    negatives = frame[frame["_target"].eq(0)]
    if remaining > 0:
        negatives = _deterministic_row_sample(
            negatives,
            n=min(remaining, len(negatives)),
            columns=["asset_id_hash", config.timestamp_column],
            random_state=config.random_state,
        )
    sample = pd.concat([positives, negatives], axis=0).sort_values(
        [config.timestamp_column, "asset_id_hash"], kind="mergesort"
    )
    rows = []
    for _, row in sample.iterrows():
        actual = int(row["_target"])
        pred = int(row["_predicted"])
        rows.append(
            {
                **keys,
                "asset_id_hash": row["asset_id_hash"],
                "prediction_origin": row[config.timestamp_column],
                "target": actual,
                "score": float(row["_score"]),
                "prediction_0_5": pred,
                "selected_threshold": 0.5,
                "prediction_output_policy": "local_diagnostic_sample_all_positives_plus_deterministic_negatives",
                "is_false_positive": bool(actual == 0 and pred == 1),
                "is_false_negative": bool(actual == 1 and pred == 0),
            }
        )
    return rows


def build_error_structure_rows(
    test_df: pd.DataFrame,
    y_true: np.ndarray,
    score: np.ndarray,
    predicted: np.ndarray,
    keys: dict[str, Any],
) -> list[dict[str, Any]]:
    """Build compact error-structure diagnostics by safe strata."""
    frame = test_df.copy()
    frame["_target"] = y_true
    frame["_score"] = score
    frame["_predicted"] = predicted
    frame["_false_negative"] = (frame["_target"].eq(1) & frame["_predicted"].eq(0))
    frame["_false_positive"] = (frame["_target"].eq(0) & frame["_predicted"].eq(1))
    rows: list[dict[str, Any]] = []
    rows.append(_error_summary_row(frame, keys, "all", "all"))
    if "model" in frame:
        model_counts = frame["model"].astype(str).value_counts()
        supported = model_counts[model_counts >= 100].index[:10]
        for model_value in supported:
            rows.append(_error_summary_row(frame[frame["model"].astype(str).eq(model_value)], keys, "model", model_value))
    for column, label in [
        ("drive_age_days", "drive_age_quartile"),
        ("lookback_observation_density_7d", "lookback_density_quartile"),
        ("capacity_bytes", "capacity_quartile"),
    ]:
        if column in frame and frame[column].nunique(dropna=True) > 1:
            quantile = pd.qcut(
                pd.to_numeric(frame[column], errors="coerce"),
                q=min(4, frame[column].nunique(dropna=True)),
                labels=False,
                duplicates="drop",
            )
            frame["_quantile"] = quantile
            for value, group in frame.groupby("_quantile", dropna=False):
                rows.append(_error_summary_row(group, keys, label, str(value)))
    return rows


def build_model_summary(metrics: pd.DataFrame) -> pd.DataFrame:
    """Summarize model status without selecting a representative model."""
    if metrics.empty:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    valid = metrics[metrics["status"].eq("valid")]
    dummy = valid[valid["model_name"].eq("dummy_prior")]
    for (model, feature_set, weighting), group in valid.groupby(
        ["model_name", "feature_set", "weighting_policy"], dropna=False
    ):
        primary = group[~group["validation_type"].astype(str).str.startswith("optimistic")]
        combined = group[group["validation_type"].eq("primary_combined_asset_time")]
        random = group[group["validation_type"].astype(str).str.startswith("optimistic")]
        dummy_primary = dummy[
            (dummy["feature_set"].eq(feature_set))
            & (dummy["weighting_policy"].eq(weighting))
            & ~dummy["validation_type"].astype(str).str.startswith("optimistic")
        ]
        primary_ap = _median(primary, "average_precision")
        combined_ap = _median(combined, "average_precision")
        random_ap = _median(random, "average_precision")
        dummy_ap = _median(dummy_primary, "average_precision")
        improvement = _subtract(primary_ap, dummy_ap)
        status, basis = _model_status(primary_ap, combined_ap, improvement, group)
        rows.append(
            {
                "model_name": model,
                "feature_set": feature_set,
                "weighting_policy": weighting,
                "model_status": status,
                "selected_representative_model": False,
                "primary_median_pr_auc": primary_ap,
                "combined_pr_auc": combined_ap,
                "random_reference_pr_auc": random_ap,
                "dummy_primary_median_pr_auc": dummy_ap,
                "primary_pr_auc_improvement_vs_dummy": improvement,
                "random_primary_pr_auc_gap": _subtract(random_ap, primary_ap),
                "primary_median_roc_auc": _median(primary, "roc_auc"),
                "primary_median_mcc": _median(primary, "mcc"),
                "primary_median_recall": _median(primary, "recall"),
                "primary_median_precision": _median(primary, "precision"),
                "primary_median_brier_score": _median(primary, "brier_score"),
                "resource_status": _resource_status(group),
                "decision_basis": basis,
            }
        )
    return pd.DataFrame(rows)


def build_asset_time_gap_summary(metrics: pd.DataFrame) -> pd.DataFrame:
    """Compare random reference against primary asset/time evidence."""
    rows: list[dict[str, Any]] = []
    valid = metrics[metrics["status"].eq("valid")]
    metrics_to_compare = ["average_precision", "roc_auc", "mcc", "recall"]
    for (model, feature_set, weighting), group in valid.groupby(
        ["model_name", "feature_set", "weighting_policy"], dropna=False
    ):
        random = group[group["validation_type"].astype(str).str.startswith("optimistic")]
        primary = group[~group["validation_type"].astype(str).str.startswith("optimistic")]
        for metric in metrics_to_compare:
            rv = _median(random, metric)
            pv = _median(primary, metric)
            rows.append(
                {
                    "model_name": model,
                    "feature_set": feature_set,
                    "weighting_policy": weighting,
                    "metric": metric,
                    "random_reference": rv,
                    "primary_median": pv,
                    "random_minus_primary_gap": _subtract(rv, pv),
                    "interpretation": _gap_interpretation(rv, pv),
                }
            )
    return pd.DataFrame(rows)


def build_classification_conclusion(
    metrics: pd.DataFrame,
    model_summary: pd.DataFrame,
    split_diagnostics: pd.DataFrame,
) -> pd.DataFrame:
    """Build compact conclusion and claim-boundary rows."""
    best_primary = (
        model_summary["primary_median_pr_auc"].max()
        if not model_summary.empty
        else np.nan
    )
    best_combined = (
        model_summary["combined_pr_auc"].max() if not model_summary.empty else np.nan
    )
    strongest = (
        "none"
        if model_summary.empty
        else str(
            model_summary.sort_values(
                ["model_status", "primary_median_pr_auc"],
                ascending=[True, False],
            ).iloc[0]["model_name"]
        )
    )
    return pd.DataFrame(
        [
            {
                "field": "primary_task",
                "value": "binary_7_day_failure_risk",
                "evidence": "7-day horizon and 7-day lookback were fixed before modeling.",
            },
            {
                "field": "primary_evidence",
                "value": "asset_disjoint_time_aware_combined_validation",
                "evidence": "Random row split is optimistic reference only.",
            },
            {
                "field": "best_primary_median_pr_auc",
                "value": _fmt(best_primary),
                "evidence": "Average precision / PR-AUC is the primary metric.",
            },
            {
                "field": "best_combined_pr_auc",
                "value": _fmt(best_combined),
                "evidence": "Combined asset/time split is the strictest evidence.",
            },
            {
                "field": "representative_model",
                "value": "none_selected",
                "evidence": "No model is automatically promoted; use status and split stability.",
            },
            {
                "field": "strongest_diagnostic_model",
                "value": strongest,
                "evidence": "Descriptive only; not a production alert model.",
            },
            {
                "field": "allowed_claim",
                "value": "offline_retrospective_failure_risk_ranking_diagnostic",
                "evidence": "Classical baselines can be compared under fixed splits.",
            },
            {
                "field": "prohibited_claim",
                "value": "calibrated_probability_or_maintenance_decision",
                "evidence": "No survival, RUL, causal, calibrated operational, or production claim.",
            },
        ]
    )


def _split_from_masks(
    frame: pd.DataFrame,
    *,
    train_mask: pd.Series,
    test_mask: pd.Series,
    split_id: str,
    split_type: str,
    validation_type: str,
    claim_scope: str,
    leakage_status: str,
) -> dict[str, Any]:
    return {
        "split_id": split_id,
        "split_type": split_type,
        "validation_type": validation_type,
        "claim_scope": claim_scope,
        "leakage_status": leakage_status,
        "train_index": frame.index[train_mask].to_numpy(),
        "test_index": frame.index[test_mask].to_numpy(),
    }


def _asset_train_test_split(
    asset_target: pd.Series,
    config: AssetTemporalClassificationConfig,
    tools: dict[str, Any],
) -> tuple[np.ndarray, np.ndarray]:
    splitter = tools["StratifiedShuffleSplit"](
        n_splits=1,
        test_size=config.asset_test_size,
        random_state=config.random_state,
    )
    positions = np.arange(len(asset_target))
    train_pos, test_pos = next(splitter.split(positions, asset_target.to_numpy(dtype=int)))
    return asset_target.index.to_numpy()[train_pos], asset_target.index.to_numpy()[test_pos]


def _safe_asset_sample(
    asset_target: pd.Series,
    *,
    test_size: float,
    random_state: int,
    tools: dict[str, Any],
) -> np.ndarray:
    if asset_target.empty:
        return np.array([], dtype=object)
    if asset_target.nunique() == 2 and min(asset_target.value_counts()) >= 2:
        splitter = tools["StratifiedShuffleSplit"](
            n_splits=1,
            test_size=test_size,
            random_state=random_state,
        )
        _, test_pos = next(
            splitter.split(np.arange(len(asset_target)), asset_target.to_numpy(dtype=int))
        )
        return asset_target.index.to_numpy()[test_pos]
    sample_n = max(1, int(math.ceil(len(asset_target) * test_size)))
    return _deterministic_series_sample(asset_target.index.to_series(), sample_n, random_state).to_numpy()


def _deterministic_row_sample(
    df: pd.DataFrame,
    *,
    n: int,
    columns: list[str],
    random_state: int,
) -> pd.DataFrame:
    if n >= len(df):
        return df
    available = [column for column in columns if column in df.columns]
    if not available:
        available = list(df.columns[:1])
    hashes = pd.util.hash_pandas_object(df[available].astype(str), index=True).astype("uint64")
    shifted = hashes ^ np.uint64(random_state)
    return df.assign(_sample_hash=shifted).sort_values("_sample_hash", kind="mergesort").head(n).drop(columns="_sample_hash")


def _deterministic_series_sample(series: pd.Series, n: int, random_state: int) -> pd.Series:
    hashes = pd.util.hash_pandas_object(series.astype(str), index=False).astype("uint64")
    shifted = hashes ^ np.uint64(random_state)
    return series.iloc[np.argsort(shifted.to_numpy(), kind="mergesort")[:n]]


def _keys(
    split: dict[str, Any],
    feature_set: FeatureSetConfig,
    weighting_policy: str,
    model_config: AssetTemporalModelConfig,
    config: AssetTemporalClassificationConfig,
) -> dict[str, Any]:
    return {
        "case_study_version": config.case_study_version,
        "source_artifact": config.source_artifact,
        "source_sha256": config.source_sha256,
        "split_id": split["split_id"],
        "split_type": split["split_type"],
        "validation_type": split["validation_type"],
        "claim_scope": split["claim_scope"],
        "feature_set": feature_set.name,
        "weighting_policy": weighting_policy,
        "model_name": model_config.name,
        "model_type": model_config.estimator_type,
    }


def _preprocessing_summary(
    preprocessor: TabularPreprocessor,
    feature_set: FeatureSetConfig,
) -> dict[str, Any]:
    return {
        "original_numeric_feature_count": len(feature_set.numeric_features),
        "original_categorical_feature_count": len(feature_set.categorical_features),
        "retained_numeric_feature_count": len(preprocessor.retained_numeric_features),
        "retained_categorical_feature_count": len(preprocessor.categorical_features),
        "removed_all_missing_count": len(preprocessor.removed_features["all_missing"]),
        "removed_high_missing_count": len(preprocessor.removed_features["high_missing"]),
        "removed_constant_count": len(preprocessor.removed_features["constant"]),
        "near_constant_retained_count": len(preprocessor.near_constant_features),
    }


def _status_metric_row(
    keys: dict[str, Any],
    diagnostics: dict[str, Any],
    status: str,
    reason: str,
) -> dict[str, Any]:
    return {
        **keys,
        **diagnostics,
        "status": status,
        "invalid_reason": reason,
        "average_precision": np.nan,
        "roc_auc": np.nan,
        "balanced_accuracy": np.nan,
        "mcc": np.nan,
        "f1": np.nan,
        "precision": np.nan,
        "recall": np.nan,
        "specificity": np.nan,
        "negative_predictive_value": np.nan,
        "brier_score": np.nan,
        "log_loss": np.nan,
    }


def _invalid_threshold_row(keys: dict[str, Any], diagnostics: dict[str, Any]) -> dict[str, Any]:
    return {
        **keys,
        **diagnostics,
        "threshold": 0.5,
        "threshold_selection_policy": "fixed_default_0_5",
        "threshold_selected_using_test_labels": False,
        "status": "invalid",
    }


def _positive_class_score(model: Any, x: np.ndarray) -> np.ndarray:
    if hasattr(model, "predict_proba"):
        probabilities = model.predict_proba(x)
        classes = list(model.classes_)
        if 1 not in classes:
            return np.zeros(len(x), dtype=float)
        return np.asarray(probabilities[:, classes.index(1)], dtype=float)
    if hasattr(model, "decision_function"):
        raw = np.asarray(model.decision_function(x), dtype=float)
        return 1.0 / (1.0 + np.exp(-raw))
    return np.asarray(model.predict(x), dtype=float)


def _time_min(series: pd.Series) -> str:
    if series.empty:
        return ""
    return str(series.min().date())


def _time_max(series: pd.Series) -> str:
    if series.empty:
        return ""
    return str(series.max().date())


def _temporal_overlap(train_time: pd.Series, test_time: pd.Series) -> str:
    if train_time.empty or test_time.empty:
        return "not_applicable"
    return "none" if train_time.max() < test_time.min() else "overlap_allowed_or_reference"


def _leakage_status(split: dict[str, Any], asset_overlap: int, temporal_overlap: str) -> str:
    if split["split_type"] in {"asset_disjoint", "combined_asset_time"} and asset_overlap != 0:
        return "invalid_asset_overlap"
    if split["split_type"] in {"time_aware", "combined_asset_time"} and temporal_overlap != "none":
        return "invalid_temporal_overlap"
    return split["leakage_status"]


def _error_summary_row(
    frame: pd.DataFrame,
    keys: dict[str, Any],
    stratum_type: str,
    stratum_value: str,
) -> dict[str, Any]:
    target = frame["_target"] if "_target" in frame else pd.Series(dtype=int)
    return {
        **keys,
        "stratum_type": stratum_type,
        "stratum_value": stratum_value,
        "row_count": int(len(frame)),
        "positive_rows": int(target.sum()) if len(frame) else 0,
        "false_negative_count": int(frame["_false_negative"].sum()) if len(frame) else 0,
        "false_positive_count": int(frame["_false_positive"].sum()) if len(frame) else 0,
        "score_median": float(frame["_score"].median()) if len(frame) else np.nan,
        "support_status": "sufficient" if len(frame) >= 100 else "insufficient_support",
    }


def _model_status(
    primary_ap: float,
    combined_ap: float,
    improvement: float,
    rows: pd.DataFrame,
) -> tuple[str, str]:
    if rows.empty or rows["status"].ne("valid").all():
        return "not_run", "no_valid_metric_rows"
    if rows["training_subsample_status"].astype(str).eq("subsampled_training").all():
        resource_note = "all_non_dummy_models_resource_limited; "
    else:
        resource_note = ""
    if pd.isna(primary_ap) or pd.isna(combined_ap):
        return "diagnostic_only", resource_note + "primary_or_combined_metric_unavailable"
    if improvement < 0.001 or combined_ap < 0.01:
        return "diagnostic_only", resource_note + "small_lift_or_weak_combined_pr_auc"
    if improvement < 0.01:
        return "limited_predictive_evidence", resource_note + "modest_lift_over_dummy"
    return "candidate_for_further_validation", resource_note + "lift_observed_requires_trust_boundary_review"


def _resource_status(group: pd.DataFrame) -> str:
    statuses = set(group["training_subsample_status"].dropna().astype(str))
    if "subsampled_training" in statuses:
        return "resource_limited_subsampled_training"
    return "not_subsampled"


def _median(frame: pd.DataFrame, column: str) -> float:
    if frame.empty or column not in frame:
        return np.nan
    values = pd.to_numeric(frame[column], errors="coerce").dropna()
    return float(values.median()) if not values.empty else np.nan


def _subtract(left: float, right: float) -> float:
    if pd.isna(left) or pd.isna(right):
        return np.nan
    return float(left - right)


def _gap_interpretation(random_value: float, primary_value: float) -> str:
    gap = _subtract(random_value, primary_value)
    if pd.isna(gap):
        return "unavailable"
    if gap > 0.05:
        return "random_reference_substantially_higher_possible_same_asset_or_temporal_dependence"
    if gap > 0.01:
        return "random_reference_higher_possible_optimism"
    return "no_large_random_primary_gap"


def _fmt(value: float) -> str:
    if pd.isna(value):
        return "unavailable"
    return f"{float(value):.6g}"


def _load_sklearn_tools() -> dict[str, Any]:
    from sklearn.dummy import DummyClassifier
    from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import StratifiedShuffleSplit

    return {
        "DummyClassifier": DummyClassifier,
        "HistGradientBoostingClassifier": HistGradientBoostingClassifier,
        "RandomForestClassifier": RandomForestClassifier,
        "LogisticRegression": LogisticRegression,
        "StratifiedShuffleSplit": StratifiedShuffleSplit,
    }
