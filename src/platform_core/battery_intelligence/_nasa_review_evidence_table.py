"""Build diagnostic NASA PCoE review evidence tables without persistence."""
from __future__ import annotations

from collections import Counter
from typing import Any

import numpy as np
import pandas as pd

from ._nasa_review_evidence_validation import (
    _TOP_ERROR_ROWS,
    _validated_exclusions,
    _validated_predictions,
    _validated_queue,
)

def _action(row: pd.Series) -> str:
    if bool(row["evaluation_coverage_issue"]):
        return "evaluation_coverage_review"
    if bool(row["source_quality_issue"]) and bool(row["disproportionate_error_influence"]):
        return "source_quality_and_error_influence_review"
    if bool(row["trajectory_continuity_issue"]) and bool(row["disproportionate_error_influence"]):
        return "trajectory_continuity_and_error_influence_review"
    if bool(row["disproportionate_error_influence"]):
        return "model_or_unmodeled_protocol_review"
    if bool(row["source_quality_issue"]):
        return "source_quality_review"
    if bool(row["trajectory_continuity_issue"]):
        return "trajectory_continuity_review"
    if bool(row["reference_context_only"]):
        return "rated_reference_context_review"
    return "no_current_priority_review"


def _checks(row: pd.Series) -> str:
    values = ["verify_battery_and_source_identity"]
    if bool(row["evaluation_coverage_issue"]):
        values.append("inspect_exact_horizon_coverage")
    if bool(row["source_quality_issue"]):
        values.append("inspect_source_quality_and_quarantine_records")
    if bool(row["trajectory_continuity_issue"]):
        values.append("inspect_cycle_order_gaps_and_target_jumps")
    if bool(row["disproportionate_error_influence"]):
        values.append("inspect_high_error_rows_without_filtering")
    if bool(row["disproportionate_error_influence"]) and not bool(
        row["structural_or_coverage_issue"]
    ):
        values.append("inspect_protocol_or_feature_mismatch")
    if bool(row["reference_start_context_flag"]):
        values.append("retain_rated_reference_deviation_as_context")
    values.append("preserve_declared_evidence_and_all_batteries")
    return ";".join(values)


def _top_rows(frame: pd.DataFrame, error: str, prediction: str) -> str:
    if frame.empty:
        return ""
    ordered = frame.sort_values(
        [error, "validation_row_number"],
        ascending=[False, True],
        kind="mergesort",
    ).head(_TOP_ERROR_ROWS)
    return ";".join(
        "row={row},actual={actual:.12g},prediction={prediction:.12g},abs_error={error:.12g}".format(
            row=int(item["validation_row_number"]),
            actual=float(item["actual"]),
            prediction=float(item[prediction]),
            error=float(item[error]),
        )
        for _, item in ordered.iterrows()
    )


def _optional(value: Any) -> float | int | None:
    if value is None or pd.isna(value):
        return None
    number = float(value)
    if not np.isfinite(number):
        return None
    return int(number) if number.is_integer() else number


def _text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value)


def build_nasa_review_evidence_table(
    *,
    review_queue: pd.DataFrame,
    excluded_operations: pd.DataFrame,
    validation_predictions: pd.DataFrame,
    predictive_evidence_level: str,
) -> dict[str, Any]:
    """Build one auditable evidence row per battery without changing the data."""
    queue = _validated_queue(review_queue)
    known_ids = set(queue["battery_id"])
    predictions = _validated_predictions(validation_predictions, known_ids)
    exclusions = _validated_exclusions(excluded_operations, known_ids)

    expected_predictions = queue.set_index("battery_id")["prediction_count"]
    observed_predictions = (
        predictions.groupby("battery_id").size()
        .reindex(expected_predictions.index)
        .fillna(0)
        .astype(int)
    )
    if not observed_predictions.equals(expected_predictions.astype(int)):
        raise ValueError("review queue prediction counts do not match validation predictions")

    expected_exclusions = queue.set_index("battery_id")[
        "excluded_discharge_operation_count"
    ]
    observed_exclusions = (
        exclusions.groupby("battery_id").size()
        .reindex(expected_exclusions.index)
        .fillna(0)
        .astype(int)
    )
    if not observed_exclusions.equals(expected_exclusions.astype(int)):
        raise ValueError("review queue exclusion counts do not match excluded operations")

    total_persistence = float(predictions["persistence_absolute_error"].sum())
    total_ridge = float(predictions["ridge_absolute_error"].sum())
    rows: list[dict[str, Any]] = []
    for _, queue_row in queue.iterrows():
        battery_id = str(queue_row["battery_id"])
        pred = predictions[predictions["battery_id"] == battery_id]
        excluded = exclusions[exclusions["battery_id"] == battery_id]
        persistence_sum = float(pred["persistence_absolute_error"].sum())
        ridge_sum = float(pred["ridge_absolute_error"].sum())
        persistence_mae = (
            float(pred["persistence_absolute_error"].mean()) if not pred.empty else None
        )
        ridge_mae = float(pred["ridge_absolute_error"].mean()) if not pred.empty else None
        if bool(queue_row["is_evaluated"]):
            if not np.isclose(persistence_mae, float(queue_row["persistence_mae"])):
                raise ValueError(f"{battery_id}: persistence MAE does not reconcile")
            if not np.isclose(ridge_mae, float(queue_row["ridge_mae"])):
                raise ValueError(f"{battery_id}: Ridge MAE does not reconcile")

        issue_counts = Counter(str(value) for value in excluded["capacity_issue"].tolist())
        row = {
            "review_order": int(queue_row["review_order"]),
            "battery_id": battery_id,
            "review_tier": int(queue_row["review_tier"]),
            "review_tier_label": _text(queue_row["review_tier_label"]),
            "review_dimensions": _text(queue_row["review_dimensions"]),
            "recommended_action_class": _action(queue_row),
            "review_check_codes": _checks(queue_row),
            "context_reasons": _text(queue_row.get("context_reasons", "")),
            "structural_review_reasons": _text(
                queue_row.get("structural_review_reasons", "")
            ),
            "influence_review_reasons": _text(
                queue_row.get("influence_review_reasons", "")
            ),
            "excluded_operation_count": int(len(excluded)),
            "excluded_cycle_indices": ";".join(
                str(int(value)) for value in excluded["cycle_index"].tolist()
            ),
            "excluded_capacity_issue_counts": ";".join(
                f"{name}:{count}" for name, count in sorted(issue_counts.items())
            ),
            "excluded_source_locations": ";".join(
                sorted(set(excluded["source_location"].astype(str)))
            ),
            "excluded_source_operation_indices": ";".join(
                str(int(value)) for value in excluded["source_operation_index"].tolist()
            ),
            "cycle_gap_count": int(queue_row["cycle_gap_count"]),
            "maximum_absolute_adjacent_target_change_percent": _optional(
                queue_row["maximum_absolute_adjacent_target_change_percent"]
            ),
            "prediction_count": int(len(pred)),
            "persistence_mae": persistence_mae,
            "ridge_mae": ridge_mae,
            "ridge_minus_persistence_mae": (
                None if persistence_mae is None else ridge_mae - persistence_mae
            ),
            "persistence_absolute_error_sum": persistence_sum,
            "ridge_absolute_error_sum": ridge_sum,
            "persistence_absolute_error_fraction": (
                persistence_sum / total_persistence if total_persistence > 0 else 0.0
            ),
            "ridge_absolute_error_fraction": (
                ridge_sum / total_ridge if total_ridge > 0 else 0.0
            ),
            "top_persistence_error_rows": _top_rows(
                pred, "persistence_absolute_error", "persistence_prediction"
            ),
            "top_ridge_error_rows": _top_rows(
                pred, "ridge_absolute_error", "ridge_prediction"
            ),
            "predictive_evidence_level": str(predictive_evidence_level),
            "causal_attribution_established": False,
            "battery_removal_authorized": False,
            "data_repair_authorized": False,
            "interpretation_boundary": (
                "Linked evidence is diagnostic only. Co-occurrence does not establish "
                "causality or authorize filtering, renormalization, interpolation, "
                "target repair, or replacement of the declared validation result."
            ),
        }
        for column in (
            "ambient_temperature_median_c",
            "current_abs_median_a",
            "current_abs_max_a",
            "voltage_min_v",
            "voltage_max_v",
            "sample_interval_median_s",
            "discharge_duration_median_s",
            "initial_discharge_capacity_fraction_of_rated",
            "median_capacity_retention_percent",
        ):
            if column in queue.columns:
                row[column] = _optional(queue_row[column])
        rows.append(row)

    table = pd.DataFrame(rows).sort_values("review_order", kind="mergesort")
    action_counts = Counter(table["recommended_action_class"].astype(str))
    summary = {
        "schema_version": "1.0",
        "review_status": "Diagnostic",
        "packet_count": int(len(table)),
        "priority_packet_count": int((table["review_tier"] <= 4).sum()),
        "linked_excluded_operation_count": int(len(exclusions)),
        "linked_validation_prediction_count": int(len(predictions)),
        "recommended_action_class_counts": dict(sorted(action_counts.items())),
        "priority_battery_ids": table.loc[
            table["review_tier"] <= 4, "battery_id"
        ].astype(str).tolist(),
        "source_quality_and_error_influence_battery_ids": table.loc[
            table["recommended_action_class"]
            == "source_quality_and_error_influence_review",
            "battery_id",
        ].astype(str).tolist(),
        "trajectory_continuity_and_error_influence_battery_ids": table.loc[
            table["recommended_action_class"]
            == "trajectory_continuity_and_error_influence_review",
            "battery_id",
        ].astype(str).tolist(),
        "model_or_unmodeled_protocol_battery_ids": table.loc[
            table["recommended_action_class"]
            == "model_or_unmodeled_protocol_review",
            "battery_id",
        ].astype(str).tolist(),
        "predictive_evidence_level": str(predictive_evidence_level),
        "causal_attribution_established": False,
        "battery_removal_authorized": False,
        "data_repair_authorized": False,
        "scientific_boundary": (
            "The packets are diagnostic review aids that preserve every battery and "
            "the declared evidence level. They do not establish mechanism, causality, "
            "external generalization, or engineering readiness."
        ),
    }
    return {"table": table.reset_index(drop=True), "summary": summary}

