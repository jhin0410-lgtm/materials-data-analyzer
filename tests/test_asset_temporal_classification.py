from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from analyzers.asset_temporal_classification import (  # noqa: E402
    AssetTemporalClassificationConfig,
    AssetTemporalModelConfig,
    FeatureSetConfig,
    ResourceBudget,
    build_asset_time_splits,
    build_training_sample_weight,
    deterministic_training_subsample,
    evaluate_asset_temporal_classification,
    fit_train_only_preprocessor,
    transform_with_preprocessor,
)


def _feature_frame(asset_count: int = 24, days: int = 18) -> pd.DataFrame:
    rows = []
    positive_assets = {1, 5, 9, 13, 17, 21}
    for asset in range(asset_count):
        for day in range(days):
            target = int(asset in positive_assets and day in {8, 9, 10})
            rows.append(
                {
                    "serial_number": f"asset_{asset:03d}",
                    "asset_id_hash": f"hash_{asset:03d}",
                    "prediction_origin": pd.Timestamp("2020-01-01") + pd.Timedelta(days=day),
                    "target_failure_within_7d": target,
                    "model": "model_a" if asset < asset_count // 2 else "model_b",
                    "capacity_bytes": 1000 + asset,
                    "drive_age_days": day,
                    "observation_number_within_asset": day + 1,
                    "lookback_observation_count": min(day + 1, 7),
                    "lookback_days_observed": min(day + 1, 7),
                    "lookback_observation_density_7d": min(day + 1, 7) / 7,
                    "prediction_origin_weekday": day % 7,
                    "smart_1_raw__current": float(asset + day),
                    "smart_1_raw__mean_7d": float(asset + day / 2),
                    "smart_1_raw__std_7d": float(day % 3),
                    "smart_1_raw__delta_7d": float(min(day, 6)),
                    "smart_1_raw__slope_7d": 1.0 if day >= 1 else np.nan,
                }
            )
    return pd.DataFrame(rows)


def _config(models: tuple[AssetTemporalModelConfig, ...] | None = None) -> AssetTemporalClassificationConfig:
    feature_set = FeatureSetConfig(
        name="synthetic_features",
        numeric_features=(
            "smart_1_raw__current",
            "smart_1_raw__mean_7d",
            "smart_1_raw__std_7d",
            "smart_1_raw__delta_7d",
            "smart_1_raw__slope_7d",
            "capacity_bytes",
            "drive_age_days",
            "lookback_observation_density_7d",
        ),
        categorical_features=("model",),
    )
    return AssetTemporalClassificationConfig(
        case_study_version="test",
        source_artifact="synthetic",
        source_sha256="sha",
        asset_column="serial_number",
        timestamp_column="prediction_origin",
        target_column="target_failure_within_7d",
        feature_sets=(feature_set,),
        model_configs=models
        or (
            AssetTemporalModelConfig("dummy_prior", "dummy_prior", 42, None),
            AssetTemporalModelConfig("logistic", "logistic_regression", 42, 80),
            AssetTemporalModelConfig("random_forest", "random_forest", 42, 80),
            AssetTemporalModelConfig("hgb", "hist_gradient_boosting", 42, 80),
        ),
        final_holdout_start="2020-01-12",
        resource_budget=ResourceBudget(max_training_rows=80, prediction_sample_max_rows=8),
    )


def test_asset_and_combined_splits_have_zero_asset_overlap() -> None:
    df = _feature_frame()
    splits = build_asset_time_splits(df, _config())

    for split in splits:
        train_assets = set(df.loc[split["train_index"], "serial_number"])
        test_assets = set(df.loc[split["test_index"], "serial_number"])
        if split["split_type"] in {"asset_disjoint", "combined_asset_time"}:
            assert train_assets.isdisjoint(test_assets)


def test_time_aware_splits_preserve_chronological_order() -> None:
    df = _feature_frame()
    splits = build_asset_time_splits(df, _config())
    for split in splits:
        if split["split_type"] in {"time_aware", "combined_asset_time"}:
            train_max = df.loc[split["train_index"], "prediction_origin"].max()
            test_min = df.loc[split["test_index"], "prediction_origin"].min()
            assert train_max < test_min


def test_random_split_is_optimistic_reference_not_primary() -> None:
    splits = build_asset_time_splits(_feature_frame(), _config())
    random_split = [split for split in splits if split["split_type"] == "random_row_reference"][0]

    assert random_split["validation_type"] == "optimistic_random_reference"
    assert random_split["claim_scope"] == "optimistic_reference_only"


def test_train_only_preprocessing_uses_train_vocabulary_and_medians() -> None:
    train = _feature_frame(asset_count=4, days=4)
    holdout = train.copy()
    holdout.loc[0, "model"] = "unseen_model"
    holdout.loc[0, "smart_1_raw__current"] = np.nan
    preprocessor = fit_train_only_preprocessor(
        train,
        numeric_features=["smart_1_raw__current", "smart_1_raw__slope_7d"],
        categorical_features=["model"],
        missing_rate_threshold=0.95,
        near_constant_top_value_rate=0.99,
    )
    transformed = transform_with_preprocessor(holdout.head(2), preprocessor, scale=True)

    assert "unseen_model" not in preprocessor.category_vocabularies["model"]
    assert transformed.shape[0] == 2
    assert not np.isnan(transformed).any()


def test_asset_balanced_weights_equalize_asset_weight_sum() -> None:
    df = _feature_frame(asset_count=4, days=6)
    weights = build_training_sample_weight(
        df,
        target_column="target_failure_within_7d",
        asset_column="serial_number",
        weighting_policy="asset_balanced",
    )
    weighted = df.assign(weight=weights).groupby("serial_number")["weight"].sum()

    assert weighted.max() / weighted.min() < 5


def test_training_subsample_preserves_positive_rows_and_does_not_touch_test() -> None:
    df = _feature_frame(asset_count=30, days=20)
    model = AssetTemporalModelConfig("logistic", "logistic_regression", 42, 60)
    sampled, metadata = deterministic_training_subsample(
        df,
        target_column="target_failure_within_7d",
        asset_column="serial_number",
        model_config=model,
        budget=ResourceBudget(max_training_rows=60),
    )

    assert len(sampled) <= 60
    assert sampled["target_failure_within_7d"].sum() == df["target_failure_within_7d"].sum()
    assert metadata["test_set_subsampled"] is False
    assert metadata["training_subsample_status"] == "subsampled_training"


def test_fixed_baselines_generate_metrics_and_top_risk_outputs() -> None:
    df = _feature_frame()
    outputs = evaluate_asset_temporal_classification(df, _config())

    assert not outputs["metrics"].empty
    assert {"dummy_prior", "logistic", "random_forest", "hgb"}.issubset(
        set(outputs["metrics"]["model_name"])
    )
    assert "average_precision" in outputs["metrics"].columns
    assert outputs["top_risk_summary"]["top_fraction"].isin([0.001, 0.005, 0.01, 0.05]).all()
    assert outputs["threshold_summary"]["threshold"].eq(0.5).all()
