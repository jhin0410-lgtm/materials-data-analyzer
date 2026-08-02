"""Manifest-bound battery review evidence for an existing NASA PCoE audit.

This module links the focused review queue to exact source quarantines and
validation-error rows. It is diagnostic only: no battery is removed, no value is
repaired, no model is refit, and no causal degradation mechanism is assigned.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

from .common import canonical_json, file_sha256

_REQUIRED_QUEUE_COLUMNS = {
    "battery_id",
    "review_order",
    "review_tier",
    "review_tier_label",
    "review_dimensions",
    "is_evaluated",
    "prediction_count",
    "reference_start_context_flag",
    "reference_context_only",
    "source_quality_issue",
    "trajectory_continuity_issue",
    "evaluation_coverage_issue",
    "structural_or_coverage_issue",
    "disproportionate_error_influence",
    "context_reasons",
    "structural_review_reasons",
    "influence_review_reasons",
    "persistence_mae",
    "ridge_mae",
    "ridge_minus_persistence_mae",
    "excluded_discharge_operation_count",
    "invalid_capacity_operation_count",
    "cycle_gap_count",
    "maximum_absolute_adjacent_target_change_percent",
}
_REQUIRED_PREDICTION_COLUMNS = {
    "battery_id",
    "actual",
    "persistence_prediction",
    "ridge_prediction",
}
_REQUIRED_EXCLUSION_COLUMNS = {
    "source_location",
    "battery_id",
    "source_operation_index",
    "cycle_index",
    "capacity_issue",
    "observed_value",
    "severity",
    "code",
    "message",
}
_BOOLEAN_COLUMNS = {
    "is_evaluated",
    "reference_start_context_flag",
    "reference_context_only",
    "source_quality_issue",
    "trajectory_continuity_issue",
    "evaluation_coverage_issue",
    "structural_or_coverage_issue",
    "disproportionate_error_influence",
}
_INVENTORY_COUNT_FIELDS = (
    "imported_discharge_operation_count",
    "excluded_discharge_operation_count",
    "invalid_capacity_operation_count",
    "missing_capacity_operation_count",
    "nonnumeric_capacity_operation_count",
    "nonscalar_capacity_operation_count",
    "complex_capacity_operation_count",
    "nonfinite_capacity_operation_count",
    "nonpositive_capacity_operation_count",
)
_TRUE_TOKENS = {"true", "1", "yes"}
_FALSE_TOKENS = {"false", "0", "no"}
_DUPLICATE_SKIP_REASON = "duplicate_identical_source_copy"
_TOP_ERROR_ROWS = 3


def _require_columns(frame: pd.DataFrame, required: set[str], *, context: str) -> None:
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"{context} missing required columns: {', '.join(missing)}")


def _ids(frame: pd.DataFrame, *, context: str) -> pd.Series:
    _require_columns(frame, {"battery_id"}, context=context)
    if frame["battery_id"].isna().any():
        raise ValueError(f"{context} battery_id may not be missing")
    values = frame["battery_id"].astype(str).str.strip()
    if (values == "").any():
        raise ValueError(f"{context} battery_id may not be blank")
    return values


def _bools(series: pd.Series, *, context: str) -> pd.Series:
    if series.isna().any():
        raise ValueError(f"{context} contains missing boolean values")
    if pd.api.types.is_bool_dtype(series):
        return series.astype(bool)
    normalized = series.astype(str).str.strip().str.casefold()
    invalid = ~normalized.isin(_TRUE_TOKENS | _FALSE_TOKENS)
    if invalid.any():
        values = sorted({repr(value) for value in series.loc[invalid].tolist()})
        raise ValueError(
            f"{context} contains invalid boolean values: {', '.join(values)}"
        )
    return normalized.isin(_TRUE_TOKENS)


def _integer_column(frame: pd.DataFrame, column: str, *, minimum: int = 0) -> None:
    values = pd.to_numeric(frame[column], errors="coerce")
    if values.isna().any() or (values < minimum).any():
        raise ValueError(f"{column} must contain integers >= {minimum}")
    if not np.isclose(values, np.round(values)).all():
        raise ValueError(f"{column} must contain integer values")
    frame[column] = values.astype(int)


def _finite_column(frame: pd.DataFrame, column: str, *, context: str) -> None:
    values = pd.to_numeric(frame[column], errors="coerce")
    if not np.isfinite(values.to_numpy(dtype=float)).all():
        raise ValueError(f"{context}.{column} must contain finite numeric values")
    frame[column] = values.astype(float)


def _validated_queue(frame: pd.DataFrame) -> pd.DataFrame:
    context = "NASA protocol review queue"
    _require_columns(frame, _REQUIRED_QUEUE_COLUMNS, context=context)
    result = frame.copy()
    result["battery_id"] = _ids(result, context=context)
    if result["battery_id"].duplicated().any():
        raise ValueError("NASA protocol review queue battery_id values must be unique")
    for column in _BOOLEAN_COLUMNS:
        result[column] = _bools(result[column], context=f"{context}.{column}")
    for column in (
        "review_order",
        "review_tier",
        "prediction_count",
        "excluded_discharge_operation_count",
        "invalid_capacity_operation_count",
        "cycle_gap_count",
    ):
        _integer_column(result, column, minimum=0)
    if sorted(result["review_order"].tolist()) != list(range(1, len(result) + 1)):
        raise ValueError("review_order must be a complete one-based sequence")
    if (result["review_tier"] < 1).any():
        raise ValueError("review_tier must be positive")
    for column in (
        "persistence_mae",
        "ridge_mae",
        "ridge_minus_persistence_mae",
        "maximum_absolute_adjacent_target_change_percent",
    ):
        result[column] = pd.to_numeric(result[column], errors="coerce")
    evaluated = result["is_evaluated"]
    model_columns = ["persistence_mae", "ridge_mae", "ridge_minus_persistence_mae"]
    if result.loc[evaluated, model_columns].isna().any().any():
        raise ValueError("evaluated batteries require finite model MAE values")
    if not np.isfinite(result.loc[evaluated, model_columns].to_numpy(dtype=float)).all():
        raise ValueError("evaluated battery MAE values must be finite")
    if (result["is_evaluated"] != (result["prediction_count"] > 0)).any():
        raise ValueError("evaluation status conflicts with prediction_count")
    if (
        result["excluded_discharge_operation_count"]
        != result["invalid_capacity_operation_count"]
    ).any():
        raise ValueError("excluded and invalid Capacity counts differ")
    return result.sort_values("review_order", kind="mergesort").reset_index(drop=True)


def _validated_predictions(frame: pd.DataFrame, known_ids: set[str]) -> pd.DataFrame:
    context = "NASA validation predictions"
    _require_columns(frame, _REQUIRED_PREDICTION_COLUMNS, context=context)
    result = frame.copy()
    result["battery_id"] = _ids(result, context=context)
    unknown = sorted(set(result["battery_id"]) - known_ids)
    if unknown:
        raise ValueError(f"validation predictions contain unknown batteries: {', '.join(unknown)}")
    for column in ("actual", "persistence_prediction", "ridge_prediction"):
        _finite_column(result, column, context=context)
    result["validation_row_number"] = np.arange(2, len(result) + 2)
    result["persistence_absolute_error"] = (
        result["actual"] - result["persistence_prediction"]
    ).abs()
    result["ridge_absolute_error"] = (
        result["actual"] - result["ridge_prediction"]
    ).abs()
    return result


def _validated_exclusions(frame: pd.DataFrame, known_ids: set[str]) -> pd.DataFrame:
    context = "NASA excluded operations"
    _require_columns(frame, _REQUIRED_EXCLUSION_COLUMNS, context=context)
    result = frame.copy()
    if result.empty:
        return result
    result["battery_id"] = _ids(result, context=context)
    unknown = sorted(set(result["battery_id"]) - known_ids)
    if unknown:
        raise ValueError(f"excluded operations contain unknown batteries: {', '.join(unknown)}")
    for column in ("source_operation_index", "cycle_index"):
        _integer_column(result, column, minimum=1)
    if (result["capacity_issue"].fillna("").astype(str).str.strip() == "").any():
        raise ValueError("excluded operation capacity_issue may not be blank")
    return result.sort_values(
        ["battery_id", "cycle_index", "source_operation_index"],
        kind="mergesort",
    ).reset_index(drop=True)


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
            "review_tier_label": str(queue_row["review_tier_label"]),
            "review_dimensions": str(queue_row["review_dimensions"]),
            "recommended_action_class": _action(queue_row),
            "review_check_codes": _checks(queue_row),
            "context_reasons": str(queue_row.get("context_reasons", "")),
            "structural_review_reasons": str(
                queue_row.get("structural_review_reasons", "")
            ),
            "influence_review_reasons": str(
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


def _verify(checksums: Mapping[str, Any], key: str, path: Path, context: str) -> str:
    expected = checksums.get(key)
    if not isinstance(expected, str) or not expected.strip():
        raise ValueError(f"{context} missing checksum: {key}")
    observed = file_sha256(path)
    if observed.lower() != expected.strip().lower():
        raise ValueError(f"{context} checksum mismatch: {key}")
    return observed


def _aggregated_inventory(frame: pd.DataFrame) -> pd.DataFrame:
    working = frame.copy()
    working["battery_id"] = _ids(working, context="NASA source inventory")
    if "skip_reason" in working.columns:
        working = working[
            working["skip_reason"].fillna("") != _DUPLICATE_SKIP_REASON
        ].copy()
    count_columns = [
        column for column in _INVENTORY_COUNT_FIELDS if column in working.columns
    ]
    if not count_columns:
        return pd.DataFrame({"battery_id": sorted(set(working["battery_id"]))})
    for column in count_columns:
        working[column] = pd.to_numeric(working[column], errors="coerce").fillna(0)
    return working.groupby("battery_id", sort=True)[count_columns].sum().reset_index()


def _same_column(left: pd.Series, right: pd.Series, *, context: str) -> None:
    left_num = pd.to_numeric(left, errors="coerce")
    right_num = pd.to_numeric(right, errors="coerce")
    numeric = (
        left_num[~left.isna()].notna().all()
        and right_num[~right.isna()].notna().all()
    )
    if numeric:
        if not left_num.isna().equals(right_num.isna()) or not np.isclose(
            left_num.fillna(0).to_numpy(dtype=float),
            right_num.fillna(0).to_numpy(dtype=float),
            rtol=1e-9,
            atol=1e-9,
        ).all():
            raise ValueError(f"NASA analysis/import content mismatch: {context}")
        return
    left_text = left.astype("string").str.strip().fillna("<missing>")
    right_text = right.astype("string").str.strip().fillna("<missing>")
    if not left_text.equals(right_text):
        raise ValueError(f"NASA analysis/import content mismatch: {context}")


def _bind_import_content(
    queue: pd.DataFrame,
    protocol: pd.DataFrame,
    inventory: pd.DataFrame,
) -> None:
    queue = queue.copy()
    protocol = protocol.copy()
    queue["battery_id"] = _ids(queue, context="NASA protocol review queue")
    protocol["battery_id"] = _ids(protocol, context="NASA protocol summary")
    inventory = _aggregated_inventory(inventory)
    queue_ids = set(queue["battery_id"])
    if queue_ids != set(protocol["battery_id"]):
        raise ValueError("review queue and protocol-summary battery identities differ")
    if queue_ids != set(inventory["battery_id"].astype(str)):
        raise ValueError("review queue and source-inventory battery identities differ")
    queue = queue.set_index("battery_id").sort_index()
    protocol = protocol.set_index("battery_id").sort_index()
    inventory = inventory.set_index("battery_id").sort_index()
    protocol_columns = sorted(set(queue.columns) & set(protocol.columns))
    if not protocol_columns:
        raise ValueError("review queue and protocol summary share no auditable columns")
    for column in protocol_columns:
        _same_column(queue[column], protocol[column], context=f"protocol.{column}")
    for column in sorted(set(queue.columns) & set(inventory.columns)):
        _same_column(queue[column], inventory[column], context=f"inventory.{column}")


def _bindings(
    import_root: Path,
    analysis_root: Path,
    analysis_paths: Mapping[str, Path],
    import_paths: Mapping[str, Path],
) -> dict[str, Any]:
    analysis_manifest_path = analysis_root / "run_manifest.json"
    import_manifest_path = import_root / "nasa_pcoe_import_manifest.json"
    if not analysis_manifest_path.is_file():
        raise FileNotFoundError("review evidence requires analysis run_manifest.json")
    if not import_manifest_path.is_file():
        raise FileNotFoundError("review evidence requires nasa_pcoe_import_manifest.json")
    analysis_manifest = json.loads(analysis_manifest_path.read_text(encoding="utf-8"))
    import_manifest = json.loads(import_manifest_path.read_text(encoding="utf-8"))
    queue_summary = json.loads(
        analysis_paths["reports/nasa_protocol_review_queue.json"].read_text(
            encoding="utf-8"
        )
    )
    if analysis_manifest.get("nasa_focused_review_queue") != queue_summary:
        raise ValueError("analysis manifest review-queue summary does not match its JSON")
    if not isinstance(
        analysis_manifest.get("nasa_protocol_aware_posthoc_audit"), Mapping
    ):
        raise ValueError("analysis manifest is missing the protocol audit summary")
    analysis_checksums = analysis_manifest.get("artifact_checksums")
    import_checksums = import_manifest.get("output_sha256")
    if not isinstance(analysis_checksums, Mapping):
        raise ValueError("analysis manifest is missing artifact_checksums")
    if not isinstance(import_checksums, Mapping):
        raise ValueError("NASA import manifest is missing output_sha256")
    verified_analysis = {
        name: _verify(analysis_checksums, name, path, "analysis manifest")
        for name, path in analysis_paths.items()
    }
    import_key = {
        "nasa_pcoe_protocol_summary.csv": "protocol_summary",
        "nasa_pcoe_source_inventory.csv": "source_inventory",
        "nasa_pcoe_excluded_operations.csv": "excluded_operations",
    }
    verified_import = {
        name: _verify(import_checksums, import_key[name], path, "NASA import manifest")
        for name, path in import_paths.items()
    }
    return {
        "analysis_manifest": analysis_manifest,
        "import_manifest": import_manifest,
        "queue_summary": queue_summary,
        "verified_analysis": verified_analysis,
        "verified_import": verified_import,
    }


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in frame.to_dict(orient="records"):
        record: dict[str, Any] = {}
        for key, value in row.items():
            if value is None or (isinstance(value, float) and not np.isfinite(value)):
                record[key] = None
            elif isinstance(value, (np.integer, int)):
                record[key] = int(value)
            elif isinstance(value, (np.floating, float)):
                record[key] = float(value)
            elif isinstance(value, (np.bool_, bool)):
                record[key] = bool(value)
            else:
                record[key] = str(value)
        records.append(record)
    return records


def _markdown(summary: Mapping[str, Any], table: pd.DataFrame) -> str:
    lines = [
        "# NASA PCoE Battery Review Evidence",
        "",
        "## Result",
        "",
        f"- Status: `{summary['review_status']}`",
        f"- Preserved predictive evidence: `{summary['predictive_evidence_level']}`",
        f"- Battery packets: `{summary['packet_count']}`",
        f"- Priority packets (tiers 1-4): `{summary['priority_packet_count']}`",
        f"- Linked excluded operations: `{summary['linked_excluded_operation_count']}`",
        f"- Linked validation rows: `{summary['linked_validation_prediction_count']}`",
        f"- Retrieval receipt verified: `{summary['retrieval_receipt_verified']}`",
        "",
        "## Scientific boundary",
        "",
        str(summary["scientific_boundary"]),
        "",
        "## Battery packets",
        "",
    ]
    for _, row in table.iterrows():
        lines.extend(
            [
                f"### {int(row['review_order'])}. {row['battery_id']}",
                "",
                f"- Tier: `{int(row['review_tier'])}` / `{row['review_tier_label']}`",
                f"- Dimensions: `{row['review_dimensions'] or 'none'}`",
                f"- Action: `{row['recommended_action_class']}`",
                f"- Structural reasons: `{row['structural_review_reasons'] or 'none'}`",
                f"- Excluded operations: `{int(row['excluded_operation_count'])}`",
                f"- Excluded cycles: `{row['excluded_cycle_indices'] or 'none'}`",
                f"- Capacity issues: `{row['excluded_capacity_issue_counts'] or 'none'}`",
                f"- Cycle gaps: `{int(row['cycle_gap_count'])}`",
                f"- Exact-horizon rows: `{int(row['prediction_count'])}`",
                f"- Persistence MAE: `{row['persistence_mae']}`",
                f"- Ridge MAE: `{row['ridge_mae']}`",
                f"- Review checks: `{row['review_check_codes']}`",
                "- Boundary: no causal attribution, battery removal, or data repair is authorized.",
                "",
            ]
        )
    return "\n".join(lines)


def audit_nasa_review_evidence(
    *,
    import_output: str | Path,
    analysis_output: str | Path,
) -> dict[str, Any]:
    """Persist battery-level review evidence from existing official-run artifacts."""
    import_root = Path(import_output)
    analysis_root = Path(analysis_output)
    tables = analysis_root / "tables"
    reports = analysis_root / "reports"
    analysis_paths = {
        "tables/nasa_protocol_review_queue.csv": tables
        / "nasa_protocol_review_queue.csv",
        "reports/nasa_protocol_review_queue.json": reports
        / "nasa_protocol_review_queue.json",
        "tables/validation_predictions.csv": tables / "validation_predictions.csv",
    }
    import_paths = {
        "nasa_pcoe_protocol_summary.csv": import_root
        / "nasa_pcoe_protocol_summary.csv",
        "nasa_pcoe_source_inventory.csv": import_root
        / "nasa_pcoe_source_inventory.csv",
        "nasa_pcoe_excluded_operations.csv": import_root
        / "nasa_pcoe_excluded_operations.csv",
    }
    missing = [
        name
        for name, path in {**analysis_paths, **import_paths}.items()
        if not path.is_file()
    ]
    if missing:
        raise FileNotFoundError(
            "NASA review evidence missing required artifacts: " + ", ".join(missing)
        )
    binding = _bindings(import_root, analysis_root, analysis_paths, import_paths)
    queue = pd.read_csv(analysis_paths["tables/nasa_protocol_review_queue.csv"])
    _bind_import_content(
        queue,
        pd.read_csv(import_paths["nasa_pcoe_protocol_summary.csv"]),
        pd.read_csv(import_paths["nasa_pcoe_source_inventory.csv"]),
    )
    result = build_nasa_review_evidence_table(
        review_queue=queue,
        excluded_operations=pd.read_csv(
            import_paths["nasa_pcoe_excluded_operations.csv"]
        ),
        validation_predictions=pd.read_csv(
            analysis_paths["tables/validation_predictions.csv"]
        ),
        predictive_evidence_level=str(
            binding["queue_summary"].get("predictive_evidence_level", "Inconclusive")
        ),
    )
    summary = result["summary"]
    summary["retrieval_receipt_verified"] = bool(
        binding["import_manifest"].get("retrieval_receipt_verified", False)
    )
    summary["source_analysis_run_manifest"] = "run_manifest.json"
    summary["source_import_manifest"] = "nasa_pcoe_import_manifest.json"
    summary["source_analysis_artifact_checksums"] = binding["verified_analysis"]
    summary["source_import_artifact_checksums"] = binding["verified_import"]

    table_path = tables / "nasa_protocol_review_evidence.csv"
    report_path = reports / "nasa_protocol_review_evidence.json"
    markdown_path = reports / "nasa_protocol_review_evidence.md"
    result["table"].to_csv(table_path, index=False, lineterminator="\n")
    report_path.write_text(
        canonical_json({"summary": summary, "batteries": _records(result["table"])}),
        encoding="utf-8",
    )
    markdown_path.write_text(_markdown(summary, result["table"]), encoding="utf-8")

    manifest_path = analysis_root / "run_manifest.json"
    manifest = binding["analysis_manifest"]
    manifest["nasa_protocol_review_evidence"] = summary
    paths = [table_path, report_path, markdown_path]
    relative = [path.relative_to(analysis_root).as_posix() for path in paths]
    manifest["artifact_paths"] = sorted(
        set(manifest.get("artifact_paths", [])) | set(relative)
    )
    checksums = dict(manifest.get("artifact_checksums", {}))
    for path, name in zip(paths, relative, strict=True):
        checksums[name] = file_sha256(path)
    manifest["artifact_checksums"] = checksums
    manifest_path.write_text(canonical_json(manifest), encoding="utf-8")
    return {
        "summary": summary,
        "outputs": {
            "review_evidence_table": str(table_path),
            "review_evidence_report": str(report_path),
            "review_evidence_markdown": str(markdown_path),
        },
    }
