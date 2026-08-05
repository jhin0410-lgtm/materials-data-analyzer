"""Predeclared target-reference sensitivity for existing Battery predictions.

This module does not fit, tune, or select a model. It preserves each model's
predicted absolute discharge capacity and asks whether the Ridge-versus-
persistence conclusion changes when the same evaluated rows are expressed under
three reference-capacity definitions fixed in advance.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd

SCHEMA_VERSION = "1.0"
REFERENCE_DEFINITIONS: tuple[dict[str, Any], ...] = (
    {
        "reference_id": "declared_reference",
        "description": (
            "Median positive finite reference_capacity_ah already declared for each "
            "battery; this remains the primary target definition."
        ),
        "role": "primary",
    },
    {
        "reference_id": "early_window_median_capacity",
        "description": (
            "Median positive finite discharge_capacity_ah from the first five cycle "
            "indices, requiring at least three observations per battery."
        ),
        "role": "predeclared_sensitivity",
    },
    {
        "reference_id": "maximum_observed_capacity",
        "description": (
            "Maximum positive finite observed discharge_capacity_ah per battery; an "
            "upper-envelope stress test, not a replacement primary definition."
        ),
        "role": "predeclared_sensitivity",
    },
)
_REQUIRED_CYCLE_COLUMNS = {
    "reference_capacity_ah",
    "discharge_capacity_ah",
}
_REQUIRED_PREDICTION_COLUMNS = {"actual", "persistence_prediction", "ridge_prediction"}
_REFERENCE_TOLERANCE = 1e-6


class TargetReferenceSensitivityError(ValueError):
    """Raised when source tables violate the fixed sensitivity contract."""


def _finite_positive(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    return numeric[np.isfinite(numeric) & (numeric > 0)]


def _require_columns(frame: pd.DataFrame, columns: set[str], *, label: str) -> None:
    missing = sorted(columns - set(frame.columns))
    if missing:
        raise TargetReferenceSensitivityError(
            f"{label} is missing required columns: {', '.join(missing)}"
        )


def _model_columns(predictions: pd.DataFrame) -> list[str]:
    columns = sorted(
        column
        for column in predictions.columns
        if column.endswith("_prediction") and column != "actual"
    )
    if not columns:
        raise TargetReferenceSensitivityError(
            "validation predictions contain no *_prediction model columns"
        )
    return columns


def _declared_reference(values: pd.Series) -> tuple[float | None, str]:
    valid = _finite_positive(values)
    if len(valid) != len(values):
        return None, "non_positive_or_non_finite_declared_reference"
    median = float(valid.median())
    spread = float(valid.max() - valid.min())
    tolerance = _REFERENCE_TOLERANCE * max(1.0, abs(median))
    if spread > tolerance:
        return None, "declared_reference_not_constant_within_battery"
    return median, "complete"


def _reference_rows(
    cycle_summary: pd.DataFrame,
    *,
    group_column: str,
    cycle_column: str,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    ordered = cycle_summary.sort_values(
        [group_column, cycle_column], kind="mergesort"
    )
    for battery_id, battery in ordered.groupby(group_column, sort=True, dropna=False):
        declared, declared_status = _declared_reference(
            battery["reference_capacity_ah"]
        )
        early = battery.head(5)
        early_valid = _finite_positive(early["discharge_capacity_ah"])
        if len(early_valid) >= 3:
            early_reference: float | None = float(early_valid.median())
            early_status = "complete"
        else:
            early_reference = None
            early_status = "fewer_than_three_valid_early_window_observations"
        observed = _finite_positive(battery["discharge_capacity_ah"])
        if len(observed) == len(battery) and len(observed) > 0:
            maximum_reference: float | None = float(observed.max())
            maximum_status = "complete"
        else:
            maximum_reference = None
            maximum_status = "invalid_observed_discharge_capacity"

        values = {
            "declared_reference": (declared, declared_status),
            "early_window_median_capacity": (early_reference, early_status),
            "maximum_observed_capacity": (maximum_reference, maximum_status),
        }
        for definition in REFERENCE_DEFINITIONS:
            reference_id = str(definition["reference_id"])
            value, status = values[reference_id]
            rows.append(
                {
                    group_column: battery_id,
                    "reference_id": reference_id,
                    "reference_role": definition["role"],
                    "reference_capacity_ah": value,
                    "reference_status": status,
                    "source_cycle_count": int(len(battery)),
                    "early_window_valid_count": int(len(early_valid)),
                }
            )
    return pd.DataFrame(rows)


def _metric_rows(
    transformed: pd.DataFrame,
    *,
    group_column: str,
    model_columns: list[str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    model_rows: list[dict[str, Any]] = []
    battery_rows: list[dict[str, Any]] = []
    for reference_id, reference_frame in transformed.groupby(
        "reference_id", sort=True
    ):
        for prediction_column in model_columns:
            model = prediction_column.removesuffix("_prediction")
            errors = (
                reference_frame[prediction_column]
                - reference_frame["actual_reference_percent"]
            ).abs()
            by_battery = (
                reference_frame.assign(absolute_error=errors)
                .groupby(group_column, sort=True, dropna=False)["absolute_error"]
                .agg(["count", "mean"])
                .reset_index()
            )
            by_battery = by_battery.rename(
                columns={"count": "prediction_count", "mean": "battery_mae"}
            )
            for record in by_battery.to_dict(orient="records"):
                battery_rows.append(
                    {
                        "reference_id": reference_id,
                        group_column: record[group_column],
                        "model": model,
                        "prediction_count": int(record["prediction_count"]),
                        "battery_mae": float(record["battery_mae"]),
                    }
                )
            model_rows.append(
                {
                    "reference_id": reference_id,
                    "model": model,
                    "prediction_count": int(len(reference_frame)),
                    "evaluated_battery_count": int(by_battery[group_column].nunique()),
                    "row_weighted_mae": float(errors.mean()),
                    "battery_macro_mae": float(by_battery["battery_mae"].mean()),
                    "worst_battery_mae": float(by_battery["battery_mae"].max()),
                }
            )
    return pd.DataFrame(model_rows), pd.DataFrame(battery_rows)


def _summary(
    *,
    reference_table: pd.DataFrame,
    model_metrics: pd.DataFrame,
    prediction_count: int,
    prediction_battery_count: int,
    group_column: str,
    model_columns: list[str],
) -> dict[str, Any]:
    schemes: list[dict[str, Any]] = []
    complete_ids: list[str] = []
    for definition in REFERENCE_DEFINITIONS:
        reference_id = str(definition["reference_id"])
        subset = reference_table[reference_table["reference_id"] == reference_id]
        incomplete = subset[subset["reference_status"] != "complete"]
        complete = incomplete.empty and len(subset) == prediction_battery_count
        if complete:
            complete_ids.append(reference_id)
        schemes.append(
            {
                **definition,
                "complete": bool(complete),
                "battery_count": int(len(subset)),
                "incomplete_battery_count": int(len(incomplete)),
                "incomplete_reasons": sorted(
                    set(str(value) for value in incomplete["reference_status"])
                ),
            }
        )

    comparisons: list[dict[str, Any]] = []
    for reference_id in complete_ids:
        subset = model_metrics[model_metrics["reference_id"] == reference_id]
        persistence = subset[subset["model"] == "persistence"]
        ridge = subset[subset["model"] == "ridge"]
        if len(persistence) != 1 or len(ridge) != 1:
            continue
        persistence_mae = float(persistence.iloc[0]["battery_macro_mae"])
        ridge_mae = float(ridge.iloc[0]["battery_macro_mae"])
        comparisons.append(
            {
                "reference_id": reference_id,
                "persistence_battery_macro_mae": persistence_mae,
                "ridge_battery_macro_mae": ridge_mae,
                "ridge_minus_persistence_battery_macro_mae": ridge_mae
                - persistence_mae,
                "preferred_model": (
                    "ridge" if ridge_mae < persistence_mae else "persistence"
                ),
            }
        )

    expected_ids = {
        str(definition["reference_id"]) for definition in REFERENCE_DEFINITIONS
    }
    comparison_ids = {str(item["reference_id"]) for item in comparisons}
    if comparison_ids != expected_ids:
        outcome = "required_reference_metadata_missing"
        conclusion = (
            "At least one predeclared reference could not preserve the complete "
            "evaluated battery and row set; sensitivity remains inconclusive."
        )
    else:
        signs = {
            float(item["ridge_minus_persistence_battery_macro_mae"]) < 0
            for item in comparisons
        }
        if len(signs) > 1:
            outcome = "conclusion_sensitive_to_target_reference"
            conclusion = (
                "The Ridge-versus-persistence ordering changes across predeclared "
                "reference definitions. No alternative is promoted as primary."
            )
        else:
            outcome = "conclusion_stable_across_defensible_targets"
            conclusion = (
                "The Ridge-versus-persistence ordering is unchanged across all "
                "predeclared complete reference definitions."
            )

    return {
        "schema_version": SCHEMA_VERSION,
        "outcome": outcome,
        "conclusion": conclusion,
        "primary_reference_id": "declared_reference",
        "reference_definitions_predeclared": True,
        "model_refit_performed": False,
        "source_rows_removed": False,
        "source_batteries_removed": False,
        "prediction_count": prediction_count,
        "prediction_battery_count": prediction_battery_count,
        "group_column": group_column,
        "models": [column.removesuffix("_prediction") for column in model_columns],
        "schemes": schemes,
        "ridge_vs_persistence": comparisons,
        "scientific_boundary": (
            "This is a normalization robustness test of existing predictions. It "
            "does not repair targets, infer a physically superior reference, select "
            "the best-looking target, refit a model, establish mechanism, or change "
            "the primary declared reference."
        ),
    }


def build_target_reference_sensitivity(
    *,
    cycle_summary: pd.DataFrame,
    predictions: pd.DataFrame,
    config: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the fixed target-reference robustness analysis without refitting."""
    group_column = str(config.get("group_column", "battery_id"))
    cycle_column = str(config.get("cycle_column", "cycle_index"))
    _require_columns(
        cycle_summary,
        {group_column, cycle_column, *_REQUIRED_CYCLE_COLUMNS},
        label="validated cycle summary",
    )
    _require_columns(
        predictions,
        {group_column, cycle_column.replace("cycle_index", "target_cycle"), *_REQUIRED_PREDICTION_COLUMNS},
        label="validation predictions",
    )
    target_cycle_column = (
        "target_cycle" if "target_cycle" in predictions.columns else cycle_column
    )
    model_columns = _model_columns(predictions)
    numeric_columns = ["actual", *model_columns]
    numeric = predictions[numeric_columns].apply(pd.to_numeric, errors="coerce")
    if not np.isfinite(numeric.to_numpy(dtype=float)).all():
        raise TargetReferenceSensitivityError(
            "validation predictions contain non-finite actual or model values"
        )
    if predictions[[group_column, target_cycle_column]].duplicated().any():
        raise TargetReferenceSensitivityError(
            "validation predictions contain duplicate battery-target rows"
        )
    if cycle_summary[[group_column, cycle_column]].duplicated().any():
        raise TargetReferenceSensitivityError(
            "validated cycle summary contains duplicate battery-cycle rows"
        )

    references = _reference_rows(
        cycle_summary,
        group_column=group_column,
        cycle_column=cycle_column,
    )
    prediction_batteries = set(predictions[group_column].tolist())
    reference_batteries = set(references[group_column].tolist())
    if not prediction_batteries.issubset(reference_batteries):
        raise TargetReferenceSensitivityError(
            "one or more prediction batteries are absent from the cycle summary"
        )

    cycle_lookup = cycle_summary[
        [group_column, cycle_column, "discharge_capacity_ah"]
    ].rename(columns={cycle_column: target_cycle_column})
    joined = predictions.merge(
        cycle_lookup,
        on=[group_column, target_cycle_column],
        how="left",
        validate="one_to_one",
        indicator=True,
    )
    if not (joined["_merge"] == "both").all():
        raise TargetReferenceSensitivityError(
            "one or more prediction targets lack a matching observed discharge cycle"
        )
    joined = joined.drop(columns=["_merge"])
    observed = pd.to_numeric(joined["discharge_capacity_ah"], errors="coerce")
    if not (np.isfinite(observed) & (observed > 0)).all():
        raise TargetReferenceSensitivityError(
            "matched discharge capacities must be positive finite values"
        )

    declared = references[
        (references["reference_id"] == "declared_reference")
        & (references["reference_status"] == "complete")
    ][[group_column, "reference_capacity_ah"]].rename(
        columns={"reference_capacity_ah": "declared_reference_ah"}
    )
    joined = joined.merge(declared, on=group_column, how="left", validate="many_to_one")
    declared_values = pd.to_numeric(joined["declared_reference_ah"], errors="coerce")
    if not (np.isfinite(declared_values) & (declared_values > 0)).all():
        raise TargetReferenceSensitivityError(
            "declared reference is unavailable for one or more evaluated batteries"
        )
    reconstructed_actual = 100.0 * observed / declared_values
    if float((reconstructed_actual - numeric["actual"].to_numpy()).abs().max()) > 1e-5:
        raise TargetReferenceSensitivityError(
            "existing actual target is not reproducible from discharge and declared reference"
        )

    absolute_predictions = {
        column: numeric[column].to_numpy() * declared_values.to_numpy() / 100.0
        for column in model_columns
    }
    transformed_frames: list[pd.DataFrame] = []
    for definition in REFERENCE_DEFINITIONS:
        reference_id = str(definition["reference_id"])
        per_battery = references[
            (references["reference_id"] == reference_id)
            & (references["reference_status"] == "complete")
        ][[group_column, "reference_capacity_ah"]]
        if len(per_battery) != len(prediction_batteries):
            continue
        transformed = joined[[group_column, target_cycle_column]].merge(
            per_battery,
            on=group_column,
            how="left",
            validate="many_to_one",
        )
        denominator = pd.to_numeric(
            transformed["reference_capacity_ah"], errors="coerce"
        )
        if not (np.isfinite(denominator) & (denominator > 0)).all():
            continue
        transformed["reference_id"] = reference_id
        transformed["actual_reference_percent"] = 100.0 * observed.to_numpy() / denominator.to_numpy()
        for column in model_columns:
            transformed[column] = 100.0 * absolute_predictions[column] / denominator.to_numpy()
        transformed_frames.append(transformed)

    transformed_all = (
        pd.concat(transformed_frames, ignore_index=True)
        if transformed_frames
        else pd.DataFrame()
    )
    if transformed_all.empty:
        model_metrics = pd.DataFrame(
            columns=[
                "reference_id",
                "model",
                "prediction_count",
                "evaluated_battery_count",
                "row_weighted_mae",
                "battery_macro_mae",
                "worst_battery_mae",
            ]
        )
        battery_metrics = pd.DataFrame(
            columns=[
                "reference_id",
                group_column,
                "model",
                "prediction_count",
                "battery_mae",
            ]
        )
    else:
        model_metrics, battery_metrics = _metric_rows(
            transformed_all,
            group_column=group_column,
            model_columns=model_columns,
        )

    summary = _summary(
        reference_table=references[
            references[group_column].isin(prediction_batteries)
        ].reset_index(drop=True),
        model_metrics=model_metrics,
        prediction_count=int(len(predictions)),
        prediction_battery_count=int(len(prediction_batteries)),
        group_column=group_column,
        model_columns=model_columns,
    )
    return {
        "reference_definitions": list(REFERENCE_DEFINITIONS),
        "target_reference_by_battery": references[
            references[group_column].isin(prediction_batteries)
        ].reset_index(drop=True),
        "model_metrics_by_reference": model_metrics,
        "battery_metrics_by_reference": battery_metrics,
        "summary": summary,
    }
