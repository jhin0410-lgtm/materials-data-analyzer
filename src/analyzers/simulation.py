"""Regression-based what-if simulation mode."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from config import OutputPaths
from io_utils import load_data, resolve_project_path, save_dataframe, save_text_report
from preprocessing import clean_column_name, clean_data, standardize_column_names
from reports import build_simulation_report
from visualization import create_scenario_prediction_figures, create_simulation_figures


def load_sklearn_tools() -> tuple[Any, Any, Any, Any, Any]:
    """Import scikit-learn only when simulation mode is actually used."""
    try:
        from sklearn.ensemble import RandomForestRegressor
        from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
        from sklearn.model_selection import train_test_split
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Missing Python package: scikit-learn\n"
            "Please install the project dependencies with: "
            "pip install -r requirements.txt"
        ) from exc

    return (
        RandomForestRegressor,
        train_test_split,
        r2_score,
        mean_absolute_error,
        mean_squared_error,
    )


def validate_simulation_columns(
    df: pd.DataFrame, target: str | None, features: list[str] | None
) -> tuple[str, list[str]]:
    """Clean and validate target/features for regression modeling."""
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

    if not pd.api.types.is_numeric_dtype(df[target_column]):
        raise ValueError(
            "Simulation mode needs a numeric target column.\n"
            f"Column exists but is not numeric: {target_column}"
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


def prepare_simulation_training_data(
    df: pd.DataFrame, target_column: str, feature_columns: list[str]
) -> pd.DataFrame:
    """Drop rows with missing target/features and keep modeling columns."""
    modeling_columns = feature_columns + [target_column]
    training_df = df[modeling_columns].dropna().copy()

    if len(training_df) < 5:
        raise ValueError(
            "Simulation mode needs at least 5 complete rows after removing "
            "missing target/feature values. Please provide more data."
        )

    # Keep a simple row id so predictions can be traced back to the modeling
    # table even after train/test split shuffles the data.
    training_df = training_df.reset_index(drop=True)
    training_df.insert(0, "model_row_id", np.arange(1, len(training_df) + 1))
    return training_df


def build_prediction_rows(
    dataset_name: str,
    model: Any,
    dataset_df: pd.DataFrame,
    feature_columns: list[str],
    target_column: str,
) -> pd.DataFrame:
    """Create prediction rows with actual value, prediction, and residual."""
    predictions = model.predict(dataset_df[feature_columns])
    prediction_df = dataset_df[["model_row_id", *feature_columns, target_column]].copy()
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
    r2_score: Any,
    mean_absolute_error: Any,
    mean_squared_error: Any,
) -> pd.DataFrame:
    """Calculate R2, MAE, and RMSE for the selected evaluation dataset."""
    r2 = r2_score(actual, predicted)
    mae = mean_absolute_error(actual, predicted)
    rmse = float(np.sqrt(mean_squared_error(actual, predicted)))

    return pd.DataFrame(
        [
            {
                "dataset": dataset_name,
                "row_count": row_count,
                "r2": r2,
                "mae": mae,
                "rmse": rmse,
                "note": split_note,
            }
        ]
    )


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


def load_and_prepare_scenario_data(
    scenario_input: str | Path,
) -> tuple[Path, pd.DataFrame]:
    """Load a scenario CSV and apply the same light cleanup as input data."""
    scenario_path = resolve_project_path(scenario_input)
    if not scenario_path.exists():
        raise FileNotFoundError(
            f"Scenario input file was not found: {scenario_path}\n"
            "Please check --scenario-input and try again."
        )

    raw_scenario_df = load_data(scenario_path)
    scenario_df = standardize_column_names(raw_scenario_df)
    scenario_df = clean_data(scenario_df)
    return scenario_path, scenario_df


def validate_scenario_dataframe(
    scenario_df: pd.DataFrame, feature_columns: list[str]
) -> None:
    """Check that scenario data has all numeric feature columns."""
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

    non_numeric_features = [
        feature
        for feature in feature_columns
        if not pd.api.types.is_numeric_dtype(scenario_df[feature])
    ]
    if non_numeric_features:
        raise ValueError(
            "Scenario CSV feature columns must be numeric.\n"
            f"Non-numeric scenario features: {non_numeric_features}"
        )


def add_or_clean_scenario_id(scenario_df: pd.DataFrame) -> pd.DataFrame:
    """Keep scenario_id when present or create one from row order."""
    prepared_df = scenario_df.copy()

    if "scenario_id" in prepared_df.columns:
        prepared_df["scenario_id"] = prepared_df["scenario_id"].astype("string")
    else:
        prepared_df.insert(
            0,
            "scenario_id",
            [f"scenario_{index}" for index in range(len(prepared_df))],
        )

    return prepared_df


def build_scenario_predictions(
    model: Any,
    scenario_df: pd.DataFrame,
    feature_columns: list[str],
    target_column: str,
    goal: str,
) -> tuple[pd.DataFrame, pd.DataFrame, int]:
    """Predict scenario target values and return goal-based ranking."""
    scenario_with_id = add_or_clean_scenario_id(scenario_df)
    valid_mask = scenario_with_id[feature_columns].notna().all(axis=1)
    valid_scenario_df = scenario_with_id.loc[valid_mask].copy()
    excluded_row_count = int((~valid_mask).sum())

    if valid_scenario_df.empty:
        raise ValueError(
            "Scenario prediction could not run because all scenario rows have "
            "missing feature values."
        )

    predicted_column = f"predicted_{target_column}"
    prediction_values = model.predict(valid_scenario_df[feature_columns])
    scenario_predictions = valid_scenario_df[["scenario_id", *feature_columns]].copy()
    scenario_predictions[predicted_column] = prediction_values

    scenario_ranking = scenario_predictions.sort_values(
        predicted_column,
        ascending=(goal == "minimize"),
    ).reset_index(drop=True)

    return scenario_predictions, scenario_ranking, excluded_row_count


def run_scenario_prediction(
    model: Any,
    scenario_input: str | Path,
    feature_columns: list[str],
    target_column: str,
    goal: str,
    output_paths: OutputPaths,
) -> dict[str, object]:
    """Run optional scenario-based what-if prediction."""
    scenario_input_path, scenario_df = load_and_prepare_scenario_data(scenario_input)
    validate_scenario_dataframe(scenario_df, feature_columns)

    scenario_predictions, scenario_ranking, excluded_row_count = (
        build_scenario_predictions(
            model=model,
            scenario_df=scenario_df,
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


def run_simulation_analysis(
    df: pd.DataFrame,
    input_path: Path,
    target: str | None,
    output_paths: OutputPaths,
    features: list[str] | None = None,
    scenario_input: str | None = None,
    goal: str = "maximize",
) -> dict[str, Path]:
    """Train a RandomForest regression model and report prediction behavior."""
    (
        RandomForestRegressor,
        train_test_split,
        r2_score,
        mean_absolute_error,
        mean_squared_error,
    ) = load_sklearn_tools()

    target_column, feature_columns = validate_simulation_columns(
        df=df, target=target, features=features
    )
    training_df = prepare_simulation_training_data(
        df=df,
        target_column=target_column,
        feature_columns=feature_columns,
    )

    model = RandomForestRegressor(n_estimators=100, random_state=42)
    model_type = "RandomForestRegressor(n_estimators=100, random_state=42)"

    if len(training_df) >= 10:
        train_df, test_df = train_test_split(
            training_df, test_size=0.2, random_state=42
        )
        split_note = "train/test split used (test_size=0.2, random_state=42)"
        metric_dataset = "test"
    else:
        train_df = training_df
        test_df = training_df
        split_note = "데이터 수가 적어 train/test split을 생략함"
        metric_dataset = "training"

    model.fit(train_df[feature_columns], train_df[target_column])

    train_predictions = build_prediction_rows(
        dataset_name="train",
        model=model,
        dataset_df=train_df,
        feature_columns=feature_columns,
        target_column=target_column,
    )

    if metric_dataset == "test":
        test_predictions = build_prediction_rows(
            dataset_name="test",
            model=model,
            dataset_df=test_df,
            feature_columns=feature_columns,
            target_column=target_column,
        )
        predictions_df = pd.concat(
            [train_predictions, test_predictions], ignore_index=True
        )
        evaluation_predictions = test_predictions
    else:
        predictions_df = train_predictions
        evaluation_predictions = train_predictions

    metrics_df = calculate_model_metrics(
        actual=evaluation_predictions["actual"],
        predicted=evaluation_predictions["predicted"].to_numpy(),
        dataset_name=metric_dataset,
        row_count=len(evaluation_predictions),
        split_note=split_note,
        r2_score=r2_score,
        mean_absolute_error=mean_absolute_error,
        mean_squared_error=mean_squared_error,
    )
    feature_importance_df = build_feature_importance_table(
        feature_columns=feature_columns,
        importances=model.feature_importances_,
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
    feature_importance_path = save_dataframe(
        feature_importance_df, output_paths.processed / "feature_importance.csv"
    )

    figure_results = create_simulation_figures(
        predictions_df=predictions_df,
        feature_importance_df=feature_importance_df,
        output_paths=output_paths,
    )

    scenario_result = None
    if scenario_input:
        scenario_result = run_scenario_prediction(
            model=model,
            scenario_input=scenario_input,
            feature_columns=feature_columns,
            target_column=target_column,
            goal=goal,
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
        feature_importance_df=feature_importance_df,
        figure_results=figure_results,
        scenario_result=scenario_result,
    )
    report_path = save_text_report(
        report_text, output_paths.reports / "simulation_report.md"
    )

    return {"report": report_path}
