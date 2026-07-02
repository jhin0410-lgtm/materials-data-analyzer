"""Data-driven virtual experiment simulation mode."""

from __future__ import annotations

from itertools import product
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from config import OutputPaths
from io_utils import load_data, resolve_project_path, save_dataframe, save_text_report
from preprocessing import clean_column_name, clean_data, standardize_column_names
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
        from sklearn.ensemble import RandomForestRegressor
        from sklearn.linear_model import LinearRegression
        from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
        from sklearn.model_selection import train_test_split
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Missing Python package: scikit-learn\n"
            "Please install the project dependencies with: "
            "pip install -r requirements.txt"
        ) from exc

    return {
        "LinearRegression": LinearRegression,
        "RandomForestRegressor": RandomForestRegressor,
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


def prepare_virtual_experiment_training_data(
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

    training_df = training_df.reset_index(drop=True)
    training_df.insert(0, "model_row_id", np.arange(1, len(training_df) + 1))
    return training_df


def prepare_simulation_training_data(
    df: pd.DataFrame, target_column: str, feature_columns: list[str]
) -> pd.DataFrame:
    """Backward-compatible wrapper for simulation training data preparation."""
    return prepare_virtual_experiment_training_data(
        df=df,
        target_column=target_column,
        feature_columns=feature_columns,
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
) -> tuple[pd.DataFrame, pd.DataFrame, str, str]:
    """Split data for evaluation, with a clear fallback for small datasets."""
    sklearn_tools = load_sklearn_tools()

    if len(training_df) >= 10:
        train_df, test_df = sklearn_tools["train_test_split"](
            training_df, test_size=0.2, random_state=42
        )
        split_note = "train/test split used (test_size=0.2, random_state=42)"
        metric_dataset = "test"
        return train_df, test_df, split_note, metric_dataset

    split_note = (
        "Small dataset fallback: train/test split was skipped; metrics use "
        "the training rows."
    )
    return training_df, training_df, split_note, "training"


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
    r2 = np.nan if row_count < 2 else r2_score(actual, predicted)
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


def evaluate_surrogate_model(
    model: Any,
    eval_df: pd.DataFrame,
    feature_columns: list[str],
    target_column: str,
    dataset_name: str,
    split_note: str,
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
        r2_score=sklearn_tools["r2_score"],
        mean_absolute_error=sklearn_tools["mean_absolute_error"],
        mean_squared_error=sklearn_tools["mean_squared_error"],
    )


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


def validate_scenario_input(
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


def validate_scenario_dataframe(
    scenario_df: pd.DataFrame, feature_columns: list[str]
) -> None:
    """Backward-compatible wrapper for scenario validation."""
    validate_scenario_input(scenario_df=scenario_df, feature_columns=feature_columns)


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
    feature_columns: list[str],
    target_column: str,
    goal: str,
    output_paths: OutputPaths,
) -> tuple[dict[str, object], pd.DataFrame]:
    """Predict, rank, and save virtual experiment candidate outputs."""
    predicted_column = f"predicted_{target_column}"
    design_path = save_dataframe(
        design_df, output_paths.processed / "virtual_experiment_design.csv"
    )

    predictions_df, excluded_row_count = predict_virtual_experiments(
        model=model,
        design_df=design_df,
        feature_columns=feature_columns,
        target_column=target_column,
    )
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
        "candidate_row_count": len(design_df),
        "valid_prediction_row_count": len(predictions_df),
        "excluded_row_count": excluded_row_count,
        "predicted_column": predicted_column,
        "goal": goal,
        "design_path": design_path,
        "virtual_predictions_path": virtual_predictions_path,
        "scenario_predictions_path": scenario_predictions_path,
        "ranking_path": ranking_path,
        "top5_ranking": ranking_df.head(5),
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
) -> dict[str, Path]:
    """Run data-driven virtual experiment screening with a surrogate model."""
    target_column, feature_columns = validate_simulation_inputs(
        df=df, target=target, features=features
    )
    training_df = prepare_virtual_experiment_training_data(
        df=df,
        target_column=target_column,
        feature_columns=feature_columns,
    )
    feature_ranges_df = summarize_feature_ranges(
        training_df=training_df,
        feature_columns=feature_columns,
    )

    train_df, eval_df, split_note, metric_dataset = split_training_evaluation_data(
        training_df
    )
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
    )
    if metric_dataset == "test":
        eval_predictions = build_prediction_rows(
            dataset_name="test",
            model=model,
            dataset_df=eval_df,
            feature_columns=feature_columns,
            target_column=target_column,
        )
        predictions_df = pd.concat(
            [train_predictions, eval_predictions], ignore_index=True
        )
    else:
        eval_predictions = train_predictions
        predictions_df = train_predictions

    metrics_df = evaluate_surrogate_model(
        model=model,
        eval_df=eval_df,
        feature_columns=feature_columns,
        target_column=target_column,
        dataset_name=metric_dataset,
        split_note=split_note,
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
            feature_columns=feature_columns,
            target_column=target_column,
            goal=goal,
            output_paths=output_paths,
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
        virtual_experiment_result=virtual_experiment_result,
    )
    report_path = save_text_report(
        report_text, output_paths.reports / "simulation_report.md"
    )

    return {"report": report_path}
