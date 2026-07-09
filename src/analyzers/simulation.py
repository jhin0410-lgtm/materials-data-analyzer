"""Data-driven virtual experiment simulation mode."""

from __future__ import annotations

from itertools import product
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from config import OutputPaths
from data_io import load_engineering_csv
from io_utils import load_data, resolve_project_path, save_dataframe, save_text_report
from preprocessing import clean_column_name, standardize_column_names
from reports import build_simulation_report
from visualization import (
    create_feature_response_figures,
    create_scenario_prediction_figures,
    create_simulation_figures,
)


MAX_GRID_DESIGN_ROWS = 10_000


def load_sklearn_tools() -> dict[str, Any]:
    """Import scikit-learn only when simulation mode is actually used."""
    try:
        from sklearn.base import clone
        from sklearn.ensemble import RandomForestRegressor
        from sklearn.linear_model import LinearRegression
        from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
        from sklearn.model_selection import (
            GroupKFold,
            GroupShuffleSplit,
            KFold,
            train_test_split,
        )
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Missing Python package: scikit-learn\n"
            "Please install the project dependencies with: "
            "pip install -r requirements.txt"
        ) from exc

    return {
        "GroupKFold": GroupKFold,
        "GroupShuffleSplit": GroupShuffleSplit,
        "KFold": KFold,
        "LinearRegression": LinearRegression,
        "RandomForestRegressor": RandomForestRegressor,
        "clone": clone,
        "mean_absolute_error": mean_absolute_error,
        "mean_squared_error": mean_squared_error,
        "r2_score": r2_score,
        "train_test_split": train_test_split,
    }


def validate_simulation_inputs(
    df: pd.DataFrame, target: str | None, features: list[str] | None
) -> tuple[str, list[str]]:
    """Clean and validate target/features for surrogate modeling."""
    if target is None:
        raise ValueError(
            "Simulation mode needs a numeric target column. Please provide --target."
        )

    if features is None or len(features) == 0:
        raise ValueError(
            "Simulation mode needs at least one numeric feature column. "
            "Please provide --features."
        )

    target_column = clean_column_name(target)
    feature_columns = [clean_column_name(feature) for feature in features]

    if target_column not in df.columns:
        available_columns = ", ".join(df.columns)
        raise ValueError(
            "Simulation mode could not find the target column.\n"
            f"Requested target: {target}\n"
            f"After column-name cleanup, it was searched as: {target_column}\n"
            f"Available columns are: {available_columns}"
        )

    if target_column in feature_columns:
        raise ValueError(
            "Simulation mode needs separate target and feature columns.\n"
            f"The target column was also provided as a feature: {target_column}"
        )

    duplicate_features = sorted(
        {
            feature
            for feature in feature_columns
            if feature_columns.count(feature) > 1
        }
    )
    if duplicate_features:
        raise ValueError(
            "Duplicate feature columns were provided after column-name cleanup: "
            f"{duplicate_features}"
        )

    missing_features = [
        feature for feature in feature_columns if feature not in df.columns
    ]
    if missing_features:
        available_columns = ", ".join(df.columns)
        raise ValueError(
            "Simulation mode could not find one or more feature columns.\n"
            f"Requested features after cleanup: {feature_columns}\n"
            f"Missing features: {missing_features}\n"
            f"Available columns are: {available_columns}"
        )

    if not pd.api.types.is_numeric_dtype(df[target_column]):
        raise ValueError(
            "Simulation mode needs a numeric target column.\n"
            f"Column exists but is not numeric: {target_column}"
        )

    non_numeric_features = [
        feature
        for feature in feature_columns
        if not pd.api.types.is_numeric_dtype(df[feature])
    ]
    if non_numeric_features:
        raise ValueError(
            "Simulation mode needs numeric feature columns.\n"
            f"Non-numeric features: {non_numeric_features}"
        )

    return target_column, feature_columns


def validate_simulation_columns(
    df: pd.DataFrame, target: str | None, features: list[str] | None
) -> tuple[str, list[str]]:
    """Backward-compatible wrapper for v0.2 tests and callers."""
    return validate_simulation_inputs(df=df, target=target, features=features)


def validate_group_column(df: pd.DataFrame, group_column: str | None) -> str | None:
    """Clean and validate an optional group column for group-aware validation."""
    if group_column is None:
        return None

    cleaned_group_column = clean_column_name(group_column)
    if cleaned_group_column not in df.columns:
        available_columns = ", ".join(df.columns)
        raise ValueError(
            "Simulation mode could not find the group column.\n"
            f"Requested group column: {group_column}\n"
            "After column-name cleanup, it was searched as: "
            f"{cleaned_group_column}\n"
            f"Available columns are: {available_columns}"
        )

    return cleaned_group_column


def prepare_virtual_experiment_training_data(
    df: pd.DataFrame,
    target_column: str,
    feature_columns: list[str],
    group_column: str | None = None,
) -> pd.DataFrame:
    """Drop rows with missing target/features and keep modeling columns."""
    modeling_columns = feature_columns + [target_column]
    if group_column and group_column not in modeling_columns:
        modeling_columns.append(group_column)

    required_columns = feature_columns + [target_column]
    if group_column:
        required_columns.append(group_column)
    training_df = df[modeling_columns].dropna(subset=required_columns).copy()

    if len(training_df) < 5:
        raise ValueError(
            "Simulation mode needs at least 5 complete rows after removing "
            "missing target/feature values. Please provide more data."
        )

    training_df = training_df.reset_index(drop=True)
    training_df.insert(0, "model_row_id", np.arange(1, len(training_df) + 1))
    return training_df


def prepare_simulation_training_data(
    df: pd.DataFrame,
    target_column: str,
    feature_columns: list[str],
    group_column: str | None = None,
) -> pd.DataFrame:
    """Backward-compatible wrapper for simulation training data preparation."""
    return prepare_virtual_experiment_training_data(
        df=df,
        target_column=target_column,
        feature_columns=feature_columns,
        group_column=group_column,
    )


def summarize_feature_ranges(
    training_df: pd.DataFrame, feature_columns: list[str]
) -> pd.DataFrame:
    """Summarize observed feature ranges used for virtual design generation."""
    rows: list[dict[str, object]] = []
    for feature in feature_columns:
        series = training_df[feature].dropna()
        rows.append(
            {
                "feature": feature,
                "min": series.min(),
                "max": series.max(),
                "mean": series.mean(),
                "std": series.std(),
            }
        )
    return pd.DataFrame(rows)


def create_surrogate_model(
    model_name: str = "random_forest",
) -> tuple[Any, str]:
    """Create a baseline surrogate model by name."""
    sklearn_tools = load_sklearn_tools()

    if model_name == "random_forest":
        model = sklearn_tools["RandomForestRegressor"](
            n_estimators=100,
            random_state=42,
        )
        return model, "RandomForestRegressor(n_estimators=100, random_state=42)"

    if model_name == "linear_regression":
        model = sklearn_tools["LinearRegression"]()
        return model, "LinearRegression()"

    raise ValueError(
        "Unsupported surrogate model. Supported values are: "
        "random_forest, linear_regression."
    )


def fit_surrogate_model(
    model: Any,
    train_df: pd.DataFrame,
    feature_columns: list[str],
    target_column: str,
) -> Any:
    """Fit the surrogate model on selected feature and target columns."""
    model.fit(train_df[feature_columns], train_df[target_column])
    return model


def split_training_evaluation_data(
    training_df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, str, str, str]:
    """Split data for evaluation, with a clear fallback for small datasets."""
    sklearn_tools = load_sklearn_tools()

    if len(training_df) >= 10:
        train_df, test_df = sklearn_tools["train_test_split"](
            training_df, test_size=0.2, random_state=42
        )
        split_note = "train/test split used (test_size=0.2, random_state=42)"
        metric_dataset = "test"
        return train_df, test_df, split_note, metric_dataset, "random_split"

    split_note = (
        "Small dataset fallback: train/test split was skipped; metrics use "
        "the training rows."
    )
    return training_df, training_df, split_note, "training", "random_split"


def split_training_evaluation_data_grouped(
    training_df: pd.DataFrame,
    group_column: str,
) -> tuple[pd.DataFrame, pd.DataFrame, str, str, str]:
    """Split data with GroupShuffleSplit so groups do not cross train/test."""
    sklearn_tools = load_sklearn_tools()
    validation_type = f"group_split_by_{group_column}"
    group_count = training_df[group_column].nunique(dropna=False)
    if group_count < 2:
        split_note = (
            "Group train/test split skipped because fewer than 2 unique groups "
            f"were available in group_column={group_column}."
        )
        return training_df, training_df, split_note, "training", validation_type

    splitter = sklearn_tools["GroupShuffleSplit"](
        n_splits=1,
        test_size=0.2,
        random_state=42,
    )
    groups = training_df[group_column]
    train_index, test_index = next(
        splitter.split(training_df, training_df.index, groups=groups)
    )
    train_df = training_df.iloc[train_index].copy()
    test_df = training_df.iloc[test_index].copy()
    split_note = (
        "Group-aware train/test split used "
        f"(GroupShuffleSplit, test_size=0.2, group_column={group_column})."
    )
    return train_df, test_df, split_note, "test", validation_type


def split_model_validation_data(
    training_df: pd.DataFrame,
    group_column: str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, str, str, str]:
    """Choose random or group-aware train/test validation split."""
    if group_column:
        return split_training_evaluation_data_grouped(training_df, group_column)
    return split_training_evaluation_data(training_df)


def build_prediction_rows(
    dataset_name: str,
    model: Any,
    dataset_df: pd.DataFrame,
    feature_columns: list[str],
    target_column: str,
    group_column: str | None = None,
) -> pd.DataFrame:
    """Create prediction rows with actual value, prediction, and residual."""
    predictions = model.predict(dataset_df[feature_columns])
    prediction_columns = ["model_row_id", *feature_columns, target_column]
    if (
        group_column
        and group_column in dataset_df.columns
        and group_column not in prediction_columns
    ):
        prediction_columns.append(group_column)
    prediction_df = dataset_df[prediction_columns].copy()
    prediction_df.insert(1, "dataset", dataset_name)
    prediction_df["actual"] = prediction_df[target_column]
    prediction_df["predicted"] = predictions
    prediction_df["residual"] = prediction_df["actual"] - prediction_df["predicted"]
    return prediction_df


def calculate_model_metrics(
    actual: pd.Series,
    predicted: np.ndarray,
    dataset_name: str,
    row_count: int,
    split_note: str,
    validation_type: str,
    r2_score: Any,
    mean_absolute_error: Any,
    mean_squared_error: Any,
) -> pd.DataFrame:
    """Calculate R2, MAE, and RMSE for the selected evaluation dataset."""
    r2 = np.nan if row_count < 2 else r2_score(actual, predicted)
    mae = mean_absolute_error(actual, predicted)
    rmse = float(np.sqrt(mean_squared_error(actual, predicted)))

    return pd.DataFrame(
        [
            {
                "dataset": dataset_name,
                "validation_type": validation_type,
                "row_count": row_count,
                "r2": r2,
                "mae": mae,
                "rmse": rmse,
                "note": split_note,
            }
        ]
    )


def evaluate_surrogate_model(
    model: Any,
    eval_df: pd.DataFrame,
    feature_columns: list[str],
    target_column: str,
    dataset_name: str,
    split_note: str,
    validation_type: str = "random_split",
) -> pd.DataFrame:
    """Evaluate a fitted surrogate model on an evaluation table."""
    sklearn_tools = load_sklearn_tools()
    predicted = model.predict(eval_df[feature_columns])
    return calculate_model_metrics(
        actual=eval_df[target_column],
        predicted=predicted,
        dataset_name=dataset_name,
        row_count=len(eval_df),
        split_note=split_note,
        validation_type=validation_type,
        r2_score=sklearn_tools["r2_score"],
        mean_absolute_error=sklearn_tools["mean_absolute_error"],
        mean_squared_error=sklearn_tools["mean_squared_error"],
    )


def build_train_test_metrics(
    model: Any,
    train_df: pd.DataFrame,
    eval_df: pd.DataFrame,
    feature_columns: list[str],
    target_column: str,
    metric_dataset: str,
    split_note: str,
    validation_type: str = "random_split",
) -> pd.DataFrame:
    """Build train and optional test metrics for model validation."""
    train_metrics = evaluate_surrogate_model(
        model=model,
        eval_df=train_df,
        feature_columns=feature_columns,
        target_column=target_column,
        dataset_name="train",
        split_note=split_note,
        validation_type=validation_type,
    )
    if metric_dataset != "test":
        return train_metrics

    test_metrics = evaluate_surrogate_model(
        model=model,
        eval_df=eval_df,
        feature_columns=feature_columns,
        target_column=target_column,
        dataset_name="test",
        split_note=split_note,
        validation_type=validation_type,
    )
    return pd.concat([train_metrics, test_metrics], ignore_index=True)


def build_overfitting_diagnostics(metrics_df: pd.DataFrame) -> pd.DataFrame:
    """Compare train/test metrics and flag possible overfitting signals."""
    columns = ["diagnostic", "train_value", "test_value", "gap", "interpretation"]
    if "test" not in metrics_df["dataset"].tolist():
        return pd.DataFrame(
            [
                {
                    "diagnostic": "train_test_split",
                    "train_value": np.nan,
                    "test_value": np.nan,
                    "gap": np.nan,
                    "interpretation": (
                        "Train/test split was not available; overfitting "
                        "diagnostics were not assessed."
                    ),
                }
            ],
            columns=columns,
        )

    train_row = metrics_df[metrics_df["dataset"] == "train"].iloc[0]
    test_row = metrics_df[metrics_df["dataset"] == "test"].iloc[0]
    r2_gap = train_row["r2"] - test_row["r2"]
    rmse_ratio = (
        test_row["rmse"] / train_row["rmse"]
        if pd.notna(train_row["rmse"]) and train_row["rmse"] != 0
        else np.nan
    )

    r2_interpretation = (
        "possible overfitting signal: train R2 is much higher than test R2"
        if pd.notna(r2_gap) and r2_gap > 0.2
        else "no strong overfitting signal from R2 gap"
    )
    rmse_interpretation = (
        "possible overfitting signal: test RMSE is much higher than train RMSE"
        if pd.notna(rmse_ratio) and rmse_ratio > 1.5
        else "no strong overfitting signal from RMSE ratio"
    )

    return pd.DataFrame(
        [
            {
                "diagnostic": "r2_gap",
                "train_value": train_row["r2"],
                "test_value": test_row["r2"],
                "gap": r2_gap,
                "interpretation": r2_interpretation,
            },
            {
                "diagnostic": "rmse_ratio",
                "train_value": train_row["rmse"],
                "test_value": test_row["rmse"],
                "gap": rmse_ratio,
                "interpretation": rmse_interpretation,
            },
        ],
        columns=columns,
    )


def choose_cross_validation_splits(row_count: int) -> int | None:
    """Choose an adjusted cross-validation split count for small datasets."""
    if row_count < 2:
        return None
    if row_count >= 10:
        return 5
    return max(2, min(5, row_count // 2))


def calculate_cross_validation_metrics(
    model: Any,
    training_df: pd.DataFrame,
    feature_columns: list[str],
    target_column: str,
    group_column: str | None = None,
) -> pd.DataFrame:
    """Run adjusted K-fold cross-validation for the surrogate model."""
    columns = ["fold", "validation_type", "r2", "mae", "rmse", "note"]
    sklearn_tools = load_sklearn_tools()
    if group_column:
        validation_type = f"group_kfold_by_{group_column}"
        group_count = training_df[group_column].nunique(dropna=False)
        if group_count < 2:
            return pd.DataFrame(
                [
                    {
                        "fold": "skipped",
                        "validation_type": validation_type,
                        "r2": np.nan,
                        "mae": np.nan,
                        "rmse": np.nan,
                        "note": (
                            "Group cross-validation skipped because fewer than "
                            "2 unique groups were available."
                        ),
                    }
                ],
                columns=columns,
            )
        splitter = sklearn_tools["GroupKFold"](n_splits=min(5, group_count))
        split_iterator = splitter.split(
            training_df,
            training_df[target_column],
            groups=training_df[group_column],
        )
    else:
        validation_type = "random_kfold"
        n_splits = choose_cross_validation_splits(len(training_df))
        if n_splits is None:
            return pd.DataFrame(columns=columns)
        splitter = sklearn_tools["KFold"](
            n_splits=n_splits,
            shuffle=True,
            random_state=42,
        )
        split_iterator = splitter.split(training_df)
    rows: list[dict[str, object]] = []

    for fold_index, (train_index, test_index) in enumerate(
        split_iterator, start=1
    ):
        fold_train_df = training_df.iloc[train_index]
        fold_test_df = training_df.iloc[test_index]
        fold_model = sklearn_tools["clone"](model)
        fold_model.fit(fold_train_df[feature_columns], fold_train_df[target_column])
        predicted = fold_model.predict(fold_test_df[feature_columns])
        r2 = (
            np.nan
            if len(fold_test_df) < 2
            else sklearn_tools["r2_score"](fold_test_df[target_column], predicted)
        )
        mae = sklearn_tools["mean_absolute_error"](
            fold_test_df[target_column], predicted
        )
        rmse = float(
            np.sqrt(
                sklearn_tools["mean_squared_error"](
                    fold_test_df[target_column], predicted
                )
            )
        )
        rows.append(
            {
                "fold": fold_index,
                "validation_type": validation_type,
                "r2": r2,
                "mae": mae,
                "rmse": rmse,
                "note": "",
            }
        )

    return pd.DataFrame(rows, columns=columns)


def build_feature_summary_table(
    model: Any, feature_columns: list[str]
) -> pd.DataFrame:
    """Build feature importance or coefficient summary for the model."""
    if hasattr(model, "feature_importances_"):
        summary_df = pd.DataFrame(
            {
                "feature": feature_columns,
                "summary_type": "random_forest_importance",
                "importance": model.feature_importances_,
                "coefficient": np.nan,
                "abs_coefficient": np.nan,
            }
        )
        summary_df = summary_df.sort_values(
            "importance", ascending=False
        ).reset_index(drop=True)
    elif hasattr(model, "coef_"):
        coefficients = np.asarray(model.coef_, dtype=float)
        summary_df = pd.DataFrame(
            {
                "feature": feature_columns,
                "summary_type": "linear_regression_coefficient",
                "importance": np.nan,
                "coefficient": coefficients,
                "abs_coefficient": np.abs(coefficients),
            }
        )
        summary_df = summary_df.sort_values(
            "abs_coefficient", ascending=False
        ).reset_index(drop=True)
    else:
        summary_df = pd.DataFrame(
            {
                "feature": feature_columns,
                "summary_type": "not_available",
                "importance": np.nan,
                "coefficient": np.nan,
                "abs_coefficient": np.nan,
            }
        )

    summary_df.insert(0, "rank", np.arange(1, len(summary_df) + 1))
    return summary_df


def build_feature_importance_table(
    feature_columns: list[str], importances: np.ndarray
) -> pd.DataFrame:
    """Turn RandomForest feature importances into a sorted table."""
    importance_df = pd.DataFrame(
        {
            "feature": feature_columns,
            "importance": importances,
        }
    )
    importance_df = importance_df.sort_values(
        "importance", ascending=False
    ).reset_index(drop=True)
    importance_df.insert(0, "rank", np.arange(1, len(importance_df) + 1))
    return importance_df


def get_feature_range(
    feature_ranges: pd.DataFrame, feature: str
) -> tuple[float, float]:
    """Return min/max range for one feature from the range summary table."""
    matching_rows = feature_ranges[feature_ranges["feature"] == feature]
    if matching_rows.empty:
        raise ValueError(f"Feature range was not found for: {feature}")

    min_value = float(matching_rows.iloc[0]["min"])
    max_value = float(matching_rows.iloc[0]["max"])
    if not np.isfinite(min_value) or not np.isfinite(max_value):
        raise ValueError(f"Feature range has non-finite values for: {feature}")
    if min_value > max_value:
        raise ValueError(f"Feature range min is greater than max for: {feature}")
    return min_value, max_value


def generate_virtual_experiment_design(
    feature_ranges: pd.DataFrame,
    method: str = "random",
    n_samples: int = 100,
    grid_levels: int = 5,
    random_state: int = 42,
) -> pd.DataFrame:
    """Generate a virtual experiment candidate table from observed ranges."""
    feature_columns = feature_ranges["feature"].tolist()
    if not feature_columns:
        raise ValueError("Virtual experiment design needs at least one feature.")

    if method == "random":
        if n_samples < 1:
            raise ValueError("--design-samples must be at least 1.")
        rng = np.random.default_rng(random_state)
        design_data: dict[str, np.ndarray] = {}
        for feature in feature_columns:
            min_value, max_value = get_feature_range(feature_ranges, feature)
            if min_value == max_value:
                design_data[feature] = np.full(n_samples, min_value)
            else:
                design_data[feature] = rng.uniform(min_value, max_value, n_samples)

        design_df = pd.DataFrame(design_data)
        design_df.insert(0, "design_source", "generated_random")
        design_df.insert(
            0,
            "scenario_id",
            [f"virtual_{index + 1:04d}" for index in range(n_samples)],
        )
        return design_df

    if method == "grid":
        if grid_levels < 2:
            raise ValueError("--grid-levels must be at least 2 for grid design.")
        total_rows = grid_levels ** len(feature_columns)
        if total_rows > MAX_GRID_DESIGN_ROWS:
            raise ValueError(
                "Grid virtual experiment design would create too many rows.\n"
                f"Requested rows: {total_rows}\n"
                f"Limit: {MAX_GRID_DESIGN_ROWS}\n"
                "Use --design-method random, reduce --grid-levels, or use fewer features."
            )

        value_lists = []
        for feature in feature_columns:
            min_value, max_value = get_feature_range(feature_ranges, feature)
            if min_value == max_value:
                value_lists.append(np.array([min_value]))
            else:
                value_lists.append(np.linspace(min_value, max_value, grid_levels))

        rows = list(product(*value_lists))
        design_df = pd.DataFrame(rows, columns=feature_columns)
        design_df.insert(0, "design_source", "generated_grid")
        design_df.insert(
            0,
            "scenario_id",
            [f"virtual_{index + 1:04d}" for index in range(len(design_df))],
        )
        return design_df

    raise ValueError("Unsupported design method. Use random or grid.")


def _clean_candidate_text_values(df: pd.DataFrame) -> pd.DataFrame:
    """Strip text cells and normalize empty candidate values to missing."""
    cleaned_df = df.copy()
    for column in cleaned_df.columns:
        if (
            pd.api.types.is_object_dtype(cleaned_df[column])
            or pd.api.types.is_string_dtype(cleaned_df[column])
        ):
            cleaned_df[column] = cleaned_df[column].astype("string").str.strip()
            cleaned_df[column] = cleaned_df[column].replace("", pd.NA)
    return cleaned_df


def load_and_prepare_scenario_data(
    scenario_input: str | Path,
) -> tuple[Path, pd.DataFrame]:
    """Load a scenario/candidate CSV and apply scenario-specific cleanup."""
    scenario_path = resolve_project_path(scenario_input)
    if not scenario_path.exists():
        raise FileNotFoundError(
            f"Scenario input file was not found: {scenario_path}\n"
            "Please check --scenario-input and try again."
        )

    try:
        raw_scenario_df = load_engineering_csv(scenario_path, min_rows=1)
    except ValueError as exc:
        raise ValueError(
            f"Scenario input CSV is empty or invalid: {scenario_path}\n"
            "Please provide at least one candidate row with the required "
            "feature columns."
        ) from exc

    scenario_df = standardize_column_names(raw_scenario_df)
    scenario_df = _clean_candidate_text_values(scenario_df)
    if scenario_df.empty:
        raise ValueError(
            f"Scenario input CSV has no candidate rows after cleanup: {scenario_path}"
        )
    return scenario_path, scenario_df


def validate_scenario_input(
    scenario_df: pd.DataFrame, feature_columns: list[str]
) -> None:
    """Check that scenario data has all required numeric feature columns."""
    if scenario_df.empty:
        raise ValueError(
            "Scenario CSV has no candidate rows. Please provide at least one row."
        )

    missing_features = [
        feature for feature in feature_columns if feature not in scenario_df.columns
    ]
    if missing_features:
        available_columns = ", ".join(scenario_df.columns)
        raise ValueError(
            "Scenario CSV is missing one or more feature columns.\n"
            f"Required features: {feature_columns}\n"
            f"Missing features: {missing_features}\n"
            f"Available scenario columns are: {available_columns}"
        )

    invalid_numeric_values: list[str] = []
    for feature in feature_columns:
        converted = pd.to_numeric(scenario_df[feature], errors="coerce")
        invalid_mask = scenario_df[feature].notna() & converted.isna()
        if invalid_mask.any():
            examples = (
                scenario_df.loc[invalid_mask, feature]
                .astype("string")
                .dropna()
                .head(3)
                .tolist()
            )
            example_text = ", ".join(str(value) for value in examples)
            invalid_numeric_values.append(f"{feature} (examples: {example_text})")
        else:
            scenario_df[feature] = converted

    if invalid_numeric_values:
        raise ValueError(
            "Scenario CSV feature columns must contain numeric values or blanks.\n"
            "Values that cannot be converted to numeric were found in: "
            f"{invalid_numeric_values}"
        )


def validate_scenario_dataframe(
    scenario_df: pd.DataFrame, feature_columns: list[str]
) -> None:
    """Backward-compatible wrapper for scenario validation."""
    validate_scenario_input(scenario_df=scenario_df, feature_columns=feature_columns)


def add_or_clean_scenario_id(scenario_df: pd.DataFrame) -> pd.DataFrame:
    """Keep scenario_id and create a standardized candidate_id."""
    prepared_df = scenario_df.copy()

    if "candidate_id" in prepared_df.columns:
        prepared_df["candidate_id"] = prepared_df["candidate_id"].astype("string")
    elif "scenario_id" in prepared_df.columns:
        candidate_ids = prepared_df["scenario_id"].astype("string")
        prepared_df.insert(0, "candidate_id", candidate_ids)
    else:
        prepared_df.insert(
            0,
            "candidate_id",
            [f"candidate_{index + 1:03d}" for index in range(len(prepared_df))],
        )

    if "scenario_id" in prepared_df.columns:
        prepared_df["scenario_id"] = prepared_df["scenario_id"].astype("string")
    else:
        scenario_position = (
            prepared_df.columns.get_loc("candidate_id") + 1
            if "candidate_id" in prepared_df.columns
            else 0
        )
        prepared_df.insert(
            scenario_position,
            "scenario_id",
            prepared_df["candidate_id"].astype("string"),
        )

    return prepared_df


def predict_virtual_experiments(
    model: Any,
    design_df: pd.DataFrame,
    feature_columns: list[str],
    target_column: str,
) -> tuple[pd.DataFrame, int]:
    """Predict target values for a candidate condition table."""
    design_with_id = add_or_clean_scenario_id(design_df)
    valid_mask = design_with_id[feature_columns].notna().all(axis=1)
    valid_design_df = design_with_id.loc[valid_mask].copy()
    excluded_row_count = int((~valid_mask).sum())

    if valid_design_df.empty:
        raise ValueError(
            "Virtual experiment prediction could not run because all candidate "
            "rows have missing feature values."
        )

    predicted_column = f"predicted_{target_column}"
    valid_design_df[predicted_column] = model.predict(
        valid_design_df[feature_columns]
    )
    return valid_design_df, excluded_row_count


def build_virtual_experiment_ranking(
    predictions_df: pd.DataFrame, target_column: str, goal: str
) -> pd.DataFrame:
    """Rank candidate rows by predicted target value."""
    predicted_column = f"predicted_{target_column}"
    if predicted_column not in predictions_df.columns:
        raise ValueError(f"Missing prediction column: {predicted_column}")

    ranking_df = predictions_df.sort_values(
        predicted_column,
        ascending=(goal == "minimize"),
    ).reset_index(drop=True)
    ranking_df.insert(0, "screening_rank", np.arange(1, len(ranking_df) + 1))
    return ranking_df


def _missing_feature_message(row: pd.Series, feature_columns: list[str]) -> str:
    missing_features = [
        feature for feature in feature_columns if pd.isna(row.get(feature))
    ]
    if not missing_features:
        return "Predicted successfully."
    return "Excluded from prediction because required feature value(s) are missing: " + ", ".join(
        missing_features
    )


def build_candidate_predictions_table(
    candidate_df: pd.DataFrame,
    predictions_df: pd.DataFrame,
    feature_columns: list[str],
    target_column: str,
    model_type: str,
    domain_warnings_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Build a standard candidate prediction table including invalid rows."""
    candidate_predictions = add_or_clean_scenario_id(candidate_df)
    predicted_column = f"predicted_{target_column}"

    candidate_predictions.insert(
        1,
        "row_index",
        np.arange(1, len(candidate_predictions) + 1),
    )
    candidate_predictions.insert(2, "predicted_target", np.nan)
    candidate_predictions.insert(3, "target_name", target_column)
    candidate_predictions.insert(4, "model_type", model_type)
    candidate_predictions.insert(5, "validation_status", "valid")
    candidate_predictions.insert(6, "validation_message", "Predicted successfully.")
    candidate_predictions.insert(7, "domain_warning_count", 0)
    candidate_predictions.insert(8, "has_domain_warning", False)

    valid_prediction_index = predictions_df.index
    if predicted_column in predictions_df.columns:
        candidate_predictions.loc[
            valid_prediction_index, "predicted_target"
        ] = predictions_df[predicted_column]

    if domain_warnings_df is not None and not domain_warnings_df.empty:
        warning_counts = domain_warnings_df.groupby("candidate_id").size()
        candidate_predictions["domain_warning_count"] = (
            candidate_predictions["candidate_id"]
            .map(warning_counts)
            .fillna(0)
            .astype(int)
        )
        candidate_predictions["has_domain_warning"] = (
            candidate_predictions["domain_warning_count"] > 0
        )

    missing_feature_mask = candidate_predictions[feature_columns].isna().any(axis=1)
    if missing_feature_mask.any():
        candidate_predictions.loc[
            missing_feature_mask, "validation_status"
        ] = "excluded_missing_feature"
        candidate_predictions.loc[
            missing_feature_mask, "validation_message"
        ] = candidate_predictions.loc[missing_feature_mask].apply(
            lambda row: _missing_feature_message(row, feature_columns),
            axis=1,
        )

    preferred_columns = [
        "candidate_id",
        "row_index",
        "predicted_target",
        "target_name",
        "model_type",
        "validation_status",
        "validation_message",
        "domain_warning_count",
        "has_domain_warning",
        *feature_columns,
    ]
    remaining_columns = [
        column for column in candidate_predictions.columns if column not in preferred_columns
    ]
    return candidate_predictions[preferred_columns + remaining_columns]


def build_candidate_ranking_table(
    candidate_predictions_df: pd.DataFrame,
    feature_columns: list[str],
    goal: str,
) -> pd.DataFrame:
    """Rank valid candidate predictions while keeping invalid rows visible."""
    candidate_ranking = candidate_predictions_df.copy()
    valid_mask = (
        (candidate_ranking["validation_status"] == "valid")
        & candidate_ranking["predicted_target"].notna()
    )
    ascending = goal == "minimize"

    ranked_candidates = candidate_ranking.loc[valid_mask].sort_values(
        ["predicted_target", "candidate_id"],
        ascending=[ascending, True],
        kind="mergesort",
    )
    invalid_candidates = candidate_ranking.loc[~valid_mask]

    ordered_ranking = pd.concat(
        [ranked_candidates, invalid_candidates],
        ignore_index=False,
    ).copy()
    ordered_ranking.insert(0, "rank", pd.NA)
    ordered_ranking.insert(4, "goal", goal)
    ordered_ranking.insert(5, "ranking_status", "invalid_candidate")
    ordered_ranking.insert(10, "ranking_note", "invalid_candidate")

    rank_values = list(range(1, len(ranked_candidates) + 1))
    ordered_ranking.loc[ranked_candidates.index, "rank"] = rank_values
    ordered_ranking.loc[ranked_candidates.index, "ranking_status"] = "ranked"
    ordered_ranking.loc[ranked_candidates.index, "ranking_note"] = "ranked"

    warning_ranked_mask = (
        ordered_ranking["ranking_status"].eq("ranked")
        & ordered_ranking["has_domain_warning"].astype(bool)
    )
    ordered_ranking.loc[
        warning_ranked_mask, "ranking_note"
    ] = "ranked_with_domain_warning"

    preferred_columns = [
        "rank",
        "candidate_id",
        "predicted_target",
        "target_name",
        "goal",
        "ranking_status",
        "validation_status",
        "validation_message",
        "has_domain_warning",
        "domain_warning_count",
        "ranking_note",
        *feature_columns,
    ]
    remaining_columns = [
        column for column in ordered_ranking.columns if column not in preferred_columns
    ]
    return ordered_ranking[preferred_columns + remaining_columns].reset_index(drop=True)


def build_candidate_domain_warnings(
    candidate_df: pd.DataFrame,
    feature_ranges_df: pd.DataFrame,
    feature_columns: list[str],
) -> pd.DataFrame:
    """Flag candidate feature values outside observed training min/max ranges."""
    columns = [
        "candidate_id",
        "feature",
        "candidate_value",
        "train_min",
        "train_max",
        "train_mean",
        "train_std",
        "warning_type",
        "severity",
        "message",
    ]
    candidate_with_id = add_or_clean_scenario_id(candidate_df)
    range_lookup = feature_ranges_df.set_index("feature")
    rows: list[dict[str, object]] = []

    for _, candidate_row in candidate_with_id.iterrows():
        candidate_id = str(candidate_row["candidate_id"])
        for feature in feature_columns:
            if feature not in range_lookup.index:
                continue

            candidate_value = candidate_row.get(feature)
            if pd.isna(candidate_value):
                continue

            range_row = range_lookup.loc[feature]
            train_min = range_row["min"]
            train_max = range_row["max"]
            train_mean = range_row["mean"]
            train_std = range_row["std"]

            warning_type: str | None = None
            if candidate_value < train_min:
                warning_type = "below_training_range"
            elif candidate_value > train_max:
                warning_type = "above_training_range"

            if warning_type is None:
                continue

            direction = "below" if warning_type == "below_training_range" else "above"
            rows.append(
                {
                    "candidate_id": candidate_id,
                    "feature": feature,
                    "candidate_value": candidate_value,
                    "train_min": train_min,
                    "train_max": train_max,
                    "train_mean": train_mean,
                    "train_std": train_std,
                    "warning_type": warning_type,
                    "severity": "outside_range",
                    "message": (
                        f"Candidate value for {feature} is {direction} the "
                        "training feature range."
                    ),
                }
            )

    return pd.DataFrame(rows, columns=columns)


def summarize_candidate_domain_warnings(
    domain_warnings_df: pd.DataFrame,
) -> tuple[int, int, pd.DataFrame]:
    """Summarize candidate domain warnings for reports."""
    if domain_warnings_df.empty:
        return 0, 0, pd.DataFrame(columns=["feature", "warning_count"])

    total_warning_count = len(domain_warnings_df)
    candidates_with_warning = int(domain_warnings_df["candidate_id"].nunique())
    top_warning_features = (
        domain_warnings_df.groupby("feature")
        .size()
        .rename("warning_count")
        .reset_index()
        .sort_values("warning_count", ascending=False)
        .reset_index(drop=True)
    )
    return candidates_with_warning, total_warning_count, top_warning_features


def summarize_candidate_validation(candidate_predictions_df: pd.DataFrame) -> pd.DataFrame:
    """Summarize candidate validation statuses for report output."""
    if candidate_predictions_df.empty:
        return pd.DataFrame(
            columns=["validation_status", "candidate_count", "validation_message"]
        )

    rows: list[dict[str, object]] = []
    for status, status_df in candidate_predictions_df.groupby(
        "validation_status", dropna=False
    ):
        messages = (
            status_df["validation_message"]
            .dropna()
            .astype(str)
            .drop_duplicates()
            .head(3)
            .tolist()
        )
        rows.append(
            {
                "validation_status": status,
                "candidate_count": len(status_df),
                "validation_message": "; ".join(messages),
            }
        )
    return pd.DataFrame(rows)


def build_scenario_predictions(
    model: Any,
    scenario_df: pd.DataFrame,
    feature_columns: list[str],
    target_column: str,
    goal: str,
) -> tuple[pd.DataFrame, pd.DataFrame, int]:
    """Predict scenario target values and return goal-based ranking."""
    scenario_predictions, excluded_row_count = predict_virtual_experiments(
        model=model,
        design_df=scenario_df,
        feature_columns=feature_columns,
        target_column=target_column,
    )
    scenario_ranking = build_virtual_experiment_ranking(
        predictions_df=scenario_predictions,
        target_column=target_column,
        goal=goal,
    )
    return scenario_predictions, scenario_ranking, excluded_row_count


def build_sensitivity_summary(
    model: Any,
    design_or_prediction_df: pd.DataFrame,
    feature_columns: list[str],
    target_column: str,
) -> pd.DataFrame:
    """Summarize simple feature sensitivity over candidate predictions."""
    predicted_column = f"predicted_{target_column}"
    analysis_df = design_or_prediction_df.copy()
    if predicted_column not in analysis_df.columns:
        analysis_df[predicted_column] = model.predict(analysis_df[feature_columns])

    importances = (
        list(model.feature_importances_)
        if hasattr(model, "feature_importances_")
        else [np.nan] * len(feature_columns)
    )
    coefficients = (
        list(np.asarray(model.coef_, dtype=float))
        if hasattr(model, "coef_")
        else [np.nan] * len(feature_columns)
    )

    rows: list[dict[str, object]] = []
    predicted_series = analysis_df[predicted_column]
    for feature, importance, coefficient in zip(
        feature_columns, importances, coefficients
    ):
        feature_series = analysis_df[feature]
        if feature_series.nunique(dropna=True) < 2 or predicted_series.nunique(
            dropna=True
        ) < 2:
            correlation = np.nan
        else:
            correlation = feature_series.corr(predicted_series)

        abs_correlation = abs(correlation) if pd.notna(correlation) else np.nan
        sensitivity_metric = (
            abs_correlation if pd.notna(abs_correlation) else importance
        )
        rows.append(
            {
                "feature": feature,
                "correlation_with_prediction": correlation,
                "absolute_correlation": abs_correlation,
                "model_feature_importance": importance,
                "model_coefficient": coefficient,
                "sensitivity_metric": sensitivity_metric,
                "interpretation_note": (
                    "Correlation with predicted target across candidate "
                    "conditions; screening aid only."
                ),
            }
        )

    summary_df = pd.DataFrame(rows)
    summary_df = summary_df.sort_values(
        "sensitivity_metric", ascending=False, na_position="last"
    ).reset_index(drop=True)
    summary_df.insert(0, "rank", np.arange(1, len(summary_df) + 1))
    return summary_df


def run_scenario_prediction(
    model: Any,
    scenario_input: str | Path,
    feature_columns: list[str],
    target_column: str,
    goal: str,
    output_paths: OutputPaths,
) -> dict[str, object]:
    """Run scenario-based virtual experiment prediction."""
    scenario_input_path, scenario_df = load_and_prepare_scenario_data(scenario_input)
    validate_scenario_input(scenario_df, feature_columns)
    design_df = add_or_clean_scenario_id(scenario_df)
    design_df.insert(1, "design_source", "scenario_input")

    scenario_predictions, scenario_ranking, excluded_row_count = (
        build_scenario_predictions(
            model=model,
            scenario_df=design_df,
            feature_columns=feature_columns,
            target_column=target_column,
            goal=goal,
        )
    )

    predicted_column = f"predicted_{target_column}"
    predictions_path = save_dataframe(
        scenario_predictions, output_paths.processed / "scenario_predictions.csv"
    )
    ranking_path = save_dataframe(
        scenario_ranking, output_paths.processed / "scenario_ranking.csv"
    )
    figure_results = create_scenario_prediction_figures(
        scenario_ranking_df=scenario_ranking,
        predicted_column=predicted_column,
        output_paths=output_paths,
    )

    return {
        "candidate_source": "scenario_input",
        "scenario_input_path": scenario_input_path,
        "scenario_row_count": len(scenario_df),
        "valid_prediction_row_count": len(scenario_predictions),
        "excluded_row_count": excluded_row_count,
        "predicted_column": predicted_column,
        "goal": goal,
        "predictions_path": predictions_path,
        "ranking_path": ranking_path,
        "top5_ranking": scenario_ranking.head(5),
        "figure_results": figure_results,
    }


def build_virtual_experiment_candidates(
    scenario_input: str | None,
    feature_ranges_df: pd.DataFrame,
    feature_columns: list[str],
    design_method: str,
    design_samples: int,
    grid_levels: int,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Load scenario candidates or generate a virtual experiment design."""
    if scenario_input:
        scenario_input_path, scenario_df = load_and_prepare_scenario_data(
            scenario_input
        )
        validate_scenario_input(scenario_df, feature_columns)
        design_df = add_or_clean_scenario_id(scenario_df)
        if "design_source" not in design_df.columns:
            design_df.insert(1, "design_source", "scenario_input")
        metadata = {
            "candidate_source": "scenario_input",
            "scenario_input_path": scenario_input_path,
            "design_method": "scenario_input",
            "requested_design_samples": None,
            "grid_levels": None,
        }
        return design_df, metadata

    design_df = generate_virtual_experiment_design(
        feature_ranges=feature_ranges_df,
        method=design_method,
        n_samples=design_samples,
        grid_levels=grid_levels,
        random_state=42,
    )
    metadata = {
        "candidate_source": "generated_design",
        "scenario_input_path": None,
        "design_method": design_method,
        "requested_design_samples": design_samples,
        "grid_levels": grid_levels,
    }
    return design_df, metadata


def run_virtual_experiment_screening(
    model: Any,
    design_df: pd.DataFrame,
    candidate_metadata: dict[str, object],
    feature_ranges_df: pd.DataFrame,
    feature_columns: list[str],
    target_column: str,
    goal: str,
    output_paths: OutputPaths,
    model_type: str,
) -> tuple[dict[str, object], pd.DataFrame]:
    """Predict, rank, and save virtual experiment candidate outputs."""
    predicted_column = f"predicted_{target_column}"
    prepared_design_df = add_or_clean_scenario_id(design_df)
    candidate_conditions_path = save_dataframe(
        prepared_design_df, output_paths.processed / "candidate_conditions.csv"
    )
    design_path = save_dataframe(
        prepared_design_df, output_paths.processed / "virtual_experiment_design.csv"
    )

    predictions_df, excluded_row_count = predict_virtual_experiments(
        model=model,
        design_df=prepared_design_df,
        feature_columns=feature_columns,
        target_column=target_column,
    )
    domain_warnings_df = build_candidate_domain_warnings(
        candidate_df=prepared_design_df,
        feature_ranges_df=feature_ranges_df,
        feature_columns=feature_columns,
    )
    domain_warnings_path = save_dataframe(
        domain_warnings_df,
        output_paths.processed / "candidate_domain_warnings.csv",
    )
    candidate_predictions_df = build_candidate_predictions_table(
        candidate_df=prepared_design_df,
        predictions_df=predictions_df,
        feature_columns=feature_columns,
        target_column=target_column,
        model_type=model_type,
        domain_warnings_df=domain_warnings_df,
    )
    candidate_predictions_path = save_dataframe(
        candidate_predictions_df,
        output_paths.processed / "candidate_predictions.csv",
    )
    candidate_ranking_df = build_candidate_ranking_table(
        candidate_predictions_df=candidate_predictions_df,
        feature_columns=feature_columns,
        goal=goal,
    )
    candidate_ranking_path = save_dataframe(
        candidate_ranking_df,
        output_paths.processed / "candidate_ranking.csv",
    )
    candidate_validation_summary_df = summarize_candidate_validation(
        candidate_predictions_df
    )
    (
        candidates_with_domain_warning,
        domain_warning_count,
        top_warning_features_df,
    ) = summarize_candidate_domain_warnings(domain_warnings_df)
    ranking_df = build_virtual_experiment_ranking(
        predictions_df=predictions_df,
        target_column=target_column,
        goal=goal,
    )

    virtual_predictions_path = save_dataframe(
        predictions_df,
        output_paths.processed / "virtual_experiment_predictions.csv",
    )
    scenario_predictions_path = save_dataframe(
        predictions_df,
        output_paths.processed / "scenario_predictions.csv",
    )
    ranking_path = save_dataframe(
        ranking_df, output_paths.processed / "scenario_ranking.csv"
    )

    ranking_figures = create_scenario_prediction_figures(
        scenario_ranking_df=ranking_df,
        predicted_column=predicted_column,
        output_paths=output_paths,
    )
    response_figures = create_feature_response_figures(
        predictions_df=predictions_df,
        feature_columns=feature_columns,
        predicted_column=predicted_column,
        output_paths=output_paths,
    )

    result = {
        **candidate_metadata,
        "candidate_row_count": len(prepared_design_df),
        "valid_prediction_row_count": len(predictions_df),
        "excluded_row_count": excluded_row_count,
        "predicted_column": predicted_column,
        "goal": goal,
        "target_name": target_column,
        "candidate_conditions_path": candidate_conditions_path,
        "design_path": design_path,
        "candidate_predictions_path": candidate_predictions_path,
        "candidate_ranking_path": candidate_ranking_path,
        "candidate_domain_warnings_path": domain_warnings_path,
        "virtual_predictions_path": virtual_predictions_path,
        "scenario_predictions_path": scenario_predictions_path,
        "ranking_path": ranking_path,
        "ranked_candidate_count": int(
            (candidate_ranking_df["ranking_status"] == "ranked").sum()
        ),
        "invalid_candidate_count": int(
            (candidate_ranking_df["ranking_status"] == "invalid_candidate").sum()
        ),
        "candidates_with_domain_warning": candidates_with_domain_warning,
        "domain_warning_count": domain_warning_count,
        "top_warning_features": top_warning_features_df,
        "top5_candidate_ranking": candidate_ranking_df[
            candidate_ranking_df["ranking_status"] == "ranked"
        ].head(5),
        "top5_ranking": ranking_df.head(5),
        "top5_candidate_predictions": candidate_predictions_df[
            candidate_predictions_df["validation_status"] == "valid"
        ]
        .sort_values("predicted_target", ascending=(goal == "minimize"))
        .head(5),
        "candidate_validation_summary": candidate_validation_summary_df,
        "figure_results": ranking_figures + response_figures,
    }
    return result, predictions_df


def run_simulation_analysis(
    df: pd.DataFrame,
    input_path: Path,
    target: str | None,
    output_paths: OutputPaths,
    features: list[str] | None = None,
    scenario_input: str | None = None,
    goal: str = "maximize",
    design_method: str = "random",
    design_samples: int = 100,
    grid_levels: int = 5,
    group_column: str | None = None,
) -> dict[str, Path]:
    """Run data-driven virtual experiment screening with a surrogate model."""
    target_column, feature_columns = validate_simulation_inputs(
        df=df, target=target, features=features
    )
    cleaned_group_column = validate_group_column(df=df, group_column=group_column)
    training_df = prepare_virtual_experiment_training_data(
        df=df,
        target_column=target_column,
        feature_columns=feature_columns,
        group_column=cleaned_group_column,
    )
    feature_ranges_df = summarize_feature_ranges(
        training_df=training_df,
        feature_columns=feature_columns,
    )

    train_df, eval_df, split_note, metric_dataset, validation_type = (
        split_model_validation_data(
            training_df=training_df,
            group_column=cleaned_group_column,
        )
    )
    train_test_group_overlap_count: int | None = None
    if cleaned_group_column and metric_dataset == "test":
        train_groups = set(train_df[cleaned_group_column].dropna().astype(str))
        test_groups = set(eval_df[cleaned_group_column].dropna().astype(str))
        train_test_group_overlap_count = len(train_groups & test_groups)

    model, model_type = create_surrogate_model("random_forest")
    model = fit_surrogate_model(
        model=model,
        train_df=train_df,
        feature_columns=feature_columns,
        target_column=target_column,
    )

    train_predictions = build_prediction_rows(
        dataset_name="train",
        model=model,
        dataset_df=train_df,
        feature_columns=feature_columns,
        target_column=target_column,
        group_column=cleaned_group_column,
    )
    if metric_dataset == "test":
        eval_predictions = build_prediction_rows(
            dataset_name="test",
            model=model,
            dataset_df=eval_df,
            feature_columns=feature_columns,
            target_column=target_column,
            group_column=cleaned_group_column,
        )
        predictions_df = pd.concat(
            [train_predictions, eval_predictions], ignore_index=True
        )
    else:
        eval_predictions = train_predictions
        predictions_df = train_predictions

    train_test_metrics_df = build_train_test_metrics(
        model=model,
        train_df=train_df,
        eval_df=eval_df,
        feature_columns=feature_columns,
        target_column=target_column,
        metric_dataset=metric_dataset,
        split_note=split_note,
        validation_type=validation_type,
    )
    metrics_df = train_test_metrics_df
    overfitting_diagnostics_df = build_overfitting_diagnostics(
        train_test_metrics_df
    )
    cross_validation_metrics_df = calculate_cross_validation_metrics(
        model=model,
        training_df=training_df,
        feature_columns=feature_columns,
        target_column=target_column,
        group_column=cleaned_group_column,
    )
    feature_summary_df = build_feature_summary_table(
        model=model, feature_columns=feature_columns
    )

    design_df, candidate_metadata = build_virtual_experiment_candidates(
        scenario_input=scenario_input,
        feature_ranges_df=feature_ranges_df,
        feature_columns=feature_columns,
        design_method=design_method,
        design_samples=design_samples,
        grid_levels=grid_levels,
    )
    virtual_experiment_result, virtual_predictions_df = (
        run_virtual_experiment_screening(
            model=model,
            design_df=design_df,
            candidate_metadata=candidate_metadata,
            feature_ranges_df=feature_ranges_df,
            feature_columns=feature_columns,
            target_column=target_column,
            goal=goal,
            output_paths=output_paths,
            model_type=model_type,
        )
    )
    sensitivity_summary_df = build_sensitivity_summary(
        model=model,
        design_or_prediction_df=virtual_predictions_df,
        feature_columns=feature_columns,
        target_column=target_column,
    )

    training_data_path = save_dataframe(
        training_df, output_paths.processed / "simulation_training_data.csv"
    )
    predictions_path = save_dataframe(
        predictions_df, output_paths.processed / "simulation_predictions.csv"
    )
    metrics_path = save_dataframe(
        metrics_df, output_paths.processed / "model_metrics.csv"
    )
    train_test_metrics_path = save_dataframe(
        train_test_metrics_df, output_paths.processed / "train_test_metrics.csv"
    )
    overfitting_diagnostics_path = save_dataframe(
        overfitting_diagnostics_df,
        output_paths.processed / "overfitting_diagnostics.csv",
    )
    cross_validation_metrics_path = save_dataframe(
        cross_validation_metrics_df,
        output_paths.processed / "cross_validation_metrics.csv",
    )
    feature_ranges_path = save_dataframe(
        feature_ranges_df, output_paths.processed / "feature_ranges.csv"
    )
    feature_summary_path = save_dataframe(
        feature_summary_df, output_paths.processed / "feature_summary.csv"
    )
    feature_importance_path = save_dataframe(
        feature_summary_df, output_paths.processed / "feature_importance.csv"
    )
    sensitivity_summary_path = save_dataframe(
        sensitivity_summary_df, output_paths.processed / "sensitivity_summary.csv"
    )

    figure_results = create_simulation_figures(
        predictions_df=predictions_df,
        feature_summary_df=feature_summary_df,
        output_paths=output_paths,
    )

    report_text = build_simulation_report(
        input_path=input_path,
        output_paths=output_paths,
        training_data_path=training_data_path,
        predictions_path=predictions_path,
        metrics_path=metrics_path,
        feature_importance_path=feature_importance_path,
        target_column=target_column,
        feature_columns=feature_columns,
        row_count=len(training_df),
        model_type=model_type,
        split_note=split_note,
        metrics_df=metrics_df,
        feature_importance_df=feature_summary_df,
        figure_results=figure_results,
        feature_summary_path=feature_summary_path,
        feature_ranges_path=feature_ranges_path,
        sensitivity_summary_path=sensitivity_summary_path,
        feature_ranges_df=feature_ranges_df,
        sensitivity_summary_df=sensitivity_summary_df,
        train_test_metrics_path=train_test_metrics_path,
        overfitting_diagnostics_path=overfitting_diagnostics_path,
        cross_validation_metrics_path=cross_validation_metrics_path,
        train_test_metrics_df=train_test_metrics_df,
        overfitting_diagnostics_df=overfitting_diagnostics_df,
        cross_validation_metrics_df=cross_validation_metrics_df,
        virtual_experiment_result=virtual_experiment_result,
        group_column=cleaned_group_column,
        validation_type=validation_type,
        train_test_group_overlap_count=train_test_group_overlap_count,
    )
    report_path = save_text_report(
        report_text, output_paths.reports / "simulation_report.md"
    )

    return {"report": report_path}
