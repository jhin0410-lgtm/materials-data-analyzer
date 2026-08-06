"""Target-reference sensitivity for existing Battery Intelligence validation results.

This module does not refit models or select a favorable target after seeing results.
It re-expresses the same exact-horizon predictions under two predeclared target
views and checks whether the primary Ridge-versus-persistence conclusion changes.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

_PRIMARY_TARGET = "rated_capacity_retention_percent"
_ALTERNATIVE_TARGET = "absolute_discharge_capacity_ah"
_REQUIRED_CYCLE_COLUMNS = {
    "cycle_index",
    "capacity_retention_percent",
    "reference_capacity_ah",
    "discharge_capacity_ah",
}
_REQUIRED_PREDICTION_COLUMNS = {"target_cycle", "actual"}


def _require_columns(frame: pd.DataFrame, required: set[str], *, name: str) -> None:
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"{name} is missing required columns: {', '.join(missing)}")


def _model_columns(predictions: pd.DataFrame) -> list[str]:
    columns = sorted(
        column for column in predictions.columns if column.endswith("_prediction")
    )
    required = {"persistence_prediction", "ridge_prediction"}
    missing = sorted(required - set(columns))
    if missing:
        raise ValueError(
            "validation predictions are missing required model columns: "
            + ", ".join(missing)
        )
    return columns


def _finite_positive(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    return numeric.notna() & np.isfinite(numeric) & (numeric > 0)


def _finite_nonnegative(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    return numeric.notna() & np.isfinite(numeric) & (numeric >= 0)


def _mae(actual: pd.Series, prediction: pd.Series) -> float:
    return float(np.mean(np.abs(actual.to_numpy(float) - prediction.to_numpy(float))))


def _metric_rows(
    frame: pd.DataFrame,
    *,
    group_column: str,
    target_name: str,
    model_columns: list[str],
    pooled_comparability: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    per_battery_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    for model_column in model_columns:
        model = model_column[: -len("_prediction")]
        prediction_column = f"{target_name}__{model}_prediction"
        actual_name = f"{target_name}__actual"
        subset = frame[[group_column, actual_name, prediction_column]].dropna()
        if subset.empty:
            raise ValueError(f"no finite validation rows for model {model!r}")
        battery_mae = (
            subset.assign(
                absolute_error=(subset[actual_name] - subset[prediction_column]).abs()
            )
            .groupby(group_column, sort=True)["absolute_error"]
            .mean()
        )
        for battery_id, value in battery_mae.items():
            per_battery_rows.append(
                {
                    group_column: battery_id,
                    "target_definition": target_name,
                    "model": model,
                    "battery_mae": float(value),
                    "prediction_count": int(
                        (subset[group_column] == battery_id).sum()
                    ),
                }
            )
        summary_rows.append(
            {
                "target_definition": target_name,
                "model": model,
                "row_weighted_mae": _mae(
                    subset[actual_name], subset[prediction_column]
                ),
                "battery_macro_mae": float(battery_mae.mean()),
                "evaluated_battery_count": int(len(battery_mae)),
                "prediction_count": int(len(subset)),
                "pooled_comparability": pooled_comparability,
            }
        )
    return pd.DataFrame(summary_rows), pd.DataFrame(per_battery_rows)


def _comparison(summary: pd.DataFrame, target_name: str) -> dict[str, Any]:
    target = summary.loc[summary["target_definition"] == target_name].set_index("model")
    persistence = target.loc["persistence"]
    ridge = target.loc["ridge"]
    row_delta = float(ridge["row_weighted_mae"] - persistence["row_weighted_mae"])
    macro_delta = float(ridge["battery_macro_mae"] - persistence["battery_macro_mae"])
    return {
        "target_definition": target_name,
        "persistence_row_weighted_mae": float(persistence["row_weighted_mae"]),
        "ridge_row_weighted_mae": float(ridge["row_weighted_mae"]),
        "ridge_minus_persistence_row_weighted_mae": row_delta,
        "persistence_battery_macro_mae": float(persistence["battery_macro_mae"]),
        "ridge_battery_macro_mae": float(ridge["battery_macro_mae"]),
        "ridge_minus_persistence_battery_macro_mae": macro_delta,
        "ridge_beats_persistence_row_weighted": bool(row_delta < 0),
        "ridge_beats_persistence_battery_macro": bool(macro_delta < 0),
    }


def _missing_reference_result() -> dict[str, Any]:
    return {
        "summary": {
            "schema_version": "1.0",
            "outcome": "required_reference_metadata_missing",
            "primary_target": _PRIMARY_TARGET,
            "alternative_target": _ALTERNATIVE_TARGET,
            "scientific_boundary": (
                "No target was changed or repaired. Sensitivity cannot be evaluated "
                "because one or more evaluated target rows lack finite positive "
                "reference capacity or finite non-negative discharge capacity."
            ),
        },
        "model_comparison": pd.DataFrame(),
        "per_battery_comparison": pd.DataFrame(),
        "bound_predictions": pd.DataFrame(),
    }


def build_target_reference_sensitivity(
    *,
    cycle_summary: pd.DataFrame,
    predictions: pd.DataFrame,
    group_column: str,
    target_tolerance_percent: float = 1e-6,
) -> dict[str, Any]:
    """Compare fixed predictions under predeclared retention and absolute-Ah views.

    The primary view is rated-capacity retention percent. The alternative view is
    absolute discharge capacity in Ah, reconstructed only from the recorded
    per-row reference capacity. Absolute-Ah pooled metrics are diagnostic because
    batteries with different rated capacities are not interchangeable.
    """
    if not isinstance(group_column, str) or not group_column.strip():
        raise ValueError("group_column must be a non-empty string")
    group_column = group_column.strip()
    _require_columns(
        cycle_summary,
        _REQUIRED_CYCLE_COLUMNS | {group_column},
        name="cycle summary",
    )
    _require_columns(
        predictions,
        _REQUIRED_PREDICTION_COLUMNS | {group_column},
        name="validation predictions",
    )
    model_columns = _model_columns(predictions)

    cycle = cycle_summary[
        [
            group_column,
            "cycle_index",
            "capacity_retention_percent",
            "reference_capacity_ah",
            "discharge_capacity_ah",
        ]
    ].copy()
    duplicates = cycle.duplicated([group_column, "cycle_index"], keep=False)
    if duplicates.any():
        raise ValueError(
            "cycle summary contains duplicate group/cycle rows required for target binding"
        )

    prediction_columns = [group_column, "target_cycle", "actual", *model_columns]
    bound = predictions[prediction_columns].merge(
        cycle,
        how="left",
        left_on=[group_column, "target_cycle"],
        right_on=[group_column, "cycle_index"],
        validate="many_to_one",
        indicator=True,
    )
    if not (bound["_merge"] == "both").all():
        missing_count = int((bound["_merge"] != "both").sum())
        raise ValueError(
            f"{missing_count} validation rows could not be bound to target-cycle evidence"
        )
    bound = bound.drop(columns=["_merge"])
    if not _finite_positive(bound["reference_capacity_ah"]).all():
        return _missing_reference_result()
    if not _finite_nonnegative(bound["discharge_capacity_ah"]).all():
        return _missing_reference_result()

    actual_difference = (
        pd.to_numeric(bound["actual"], errors="coerce")
        - pd.to_numeric(bound["capacity_retention_percent"], errors="coerce")
    ).abs()
    if (
        actual_difference.isna().any()
        or float(actual_difference.max()) > target_tolerance_percent
    ):
        raise ValueError(
            "validation actual values do not match the bound rated-capacity retention target"
        )
    reconstructed_retention = (
        pd.to_numeric(bound["discharge_capacity_ah"], errors="coerce")
        / pd.to_numeric(bound["reference_capacity_ah"], errors="coerce")
        * 100.0
    )
    reconstruction_error = (
        reconstructed_retention
        - pd.to_numeric(bound["capacity_retention_percent"], errors="coerce")
    ).abs()
    if (
        reconstruction_error.isna().any()
        or float(reconstruction_error.max()) > target_tolerance_percent
    ):
        raise ValueError(
            "source discharge capacity does not reproduce the recorded retention target"
        )

    reference = pd.to_numeric(bound["reference_capacity_ah"], errors="coerce")
    bound[f"{_PRIMARY_TARGET}__actual"] = pd.to_numeric(bound["actual"])
    bound[f"{_ALTERNATIVE_TARGET}__actual"] = (
        pd.to_numeric(bound["actual"]) * reference / 100.0
    )
    for model_column in model_columns:
        model = model_column[: -len("_prediction")]
        prediction = pd.to_numeric(bound[model_column], errors="coerce")
        if prediction.isna().any() or not np.isfinite(prediction).all():
            raise ValueError(
                f"model prediction column contains non-finite values: {model_column}"
            )
        bound[f"{_PRIMARY_TARGET}__{model}_prediction"] = prediction
        bound[f"{_ALTERNATIVE_TARGET}__{model}_prediction"] = (
            prediction * reference / 100.0
        )

    primary_summary, primary_battery = _metric_rows(
        bound,
        group_column=group_column,
        target_name=_PRIMARY_TARGET,
        model_columns=model_columns,
        pooled_comparability="declared_primary_cross_battery_metric",
    )
    alternative_summary, alternative_battery = _metric_rows(
        bound,
        group_column=group_column,
        target_name=_ALTERNATIVE_TARGET,
        model_columns=model_columns,
        pooled_comparability="diagnostic_only_capacity_scale_dependent",
    )
    model_comparison = pd.concat(
        [primary_summary, alternative_summary], ignore_index=True
    )
    per_battery = pd.concat(
        [primary_battery, alternative_battery], ignore_index=True
    )
    primary = _comparison(model_comparison, _PRIMARY_TARGET)
    alternative = _comparison(model_comparison, _ALTERNATIVE_TARGET)
    stable = (
        primary["ridge_beats_persistence_row_weighted"]
        == alternative["ridge_beats_persistence_row_weighted"]
        and primary["ridge_beats_persistence_battery_macro"]
        == alternative["ridge_beats_persistence_battery_macro"]
    )
    outcome = (
        "conclusion_stable_across_defensible_targets"
        if stable
        else "conclusion_sensitive_to_target_reference"
    )
    reference_values = sorted(float(value) for value in reference.unique())
    summary: dict[str, Any] = {
        "schema_version": "1.0",
        "outcome": outcome,
        "primary_target": _PRIMARY_TARGET,
        "alternative_target": _ALTERNATIVE_TARGET,
        "validation_prediction_rows": int(len(bound)),
        "evaluated_battery_count": int(bound[group_column].nunique()),
        "reference_capacity_unique_values_ah": reference_values,
        "reference_capacity_min_ah": float(reference.min()),
        "reference_capacity_max_ah": float(reference.max()),
        "primary_comparison": primary,
        "alternative_comparison": alternative,
        "primary_conclusion_stable": bool(stable),
        "alternative_target_scope": (
            "Absolute discharge capacity is observable but pooled Ah error is capacity-scale "
            "dependent and is diagnostic only when rated capacities differ."
        ),
        "scientific_boundary": (
            "The same validation rows, predictions, battery identities, and splits are reused. "
            "No model is refit, no target is clipped or repaired, no first-observed reference "
            "is introduced, and the alternative target is not promoted merely because it is "
            "more favorable. Stability here does not establish external validity or mechanism."
        ),
    }
    output_columns = [
        group_column,
        "target_cycle",
        "reference_capacity_ah",
        "discharge_capacity_ah",
        "capacity_retention_percent",
        *[column for column in bound.columns if "__" in column],
    ]
    return {
        "summary": summary,
        "model_comparison": model_comparison,
        "per_battery_comparison": per_battery,
        "bound_predictions": bound[output_columns].copy(),
    }


def target_reference_markdown(summary: Mapping[str, Any]) -> str:
    """Render a bounded human-readable target-reference sensitivity report."""
    lines = [
        "# Battery Target-Reference Sensitivity",
        "",
        f"- Outcome: `{summary['outcome']}`",
        f"- Primary target: `{summary['primary_target']}`",
        f"- Alternative target: `{summary['alternative_target']}`",
        f"- Validation rows: `{summary.get('validation_prediction_rows', 'unavailable')}`",
        f"- Evaluated batteries: `{summary.get('evaluated_battery_count', 'unavailable')}`",
        "",
    ]
    if "primary_comparison" in summary:
        primary = summary["primary_comparison"]
        alternative = summary["alternative_comparison"]
        lines.extend(
            [
                "## Ridge versus Persistence",
                "",
                "- Primary battery-macro Ridge minus persistence MAE: "
                f"`{primary['ridge_minus_persistence_battery_macro_mae']}`",
                "- Alternative battery-macro Ridge minus persistence MAE: "
                f"`{alternative['ridge_minus_persistence_battery_macro_mae']}`",
                f"- Primary conclusion stable: `{summary['primary_conclusion_stable']}`",
                "",
            ]
        )
    lines.extend(
        [
            "## Interpretation Boundary",
            "",
            str(summary["scientific_boundary"]),
            "",
        ]
    )
    return "\n".join(lines)


def load_target_reference_inputs(
    output_dir: str | Path,
) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    """Load the fixed existing-run inputs required by the sensitivity analysis."""
    output = Path(output_dir)
    cycle_path = output / "tables/validated_cycle_summary.csv"
    prediction_path = output / "tables/validation_predictions.csv"
    config_path = output / "config_snapshot.json"
    missing = [
        str(path.relative_to(output))
        for path in (cycle_path, prediction_path, config_path)
        if not path.is_file()
    ]
    if missing:
        raise FileNotFoundError(
            "battery run is missing target-sensitivity inputs: " + ", ".join(missing)
        )
    config = json.loads(config_path.read_text(encoding="utf-8"))
    group_column = str(config["config"]["group_column"])
    return pd.read_csv(cycle_path), pd.read_csv(prediction_path), group_column
