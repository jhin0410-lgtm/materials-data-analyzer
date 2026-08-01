"""Protocol-aware post-hoc audit for official NASA PCoE battery results.

The audit separates rated-capacity start context from source quality,
trajectory continuity, evaluation coverage, and error influence. It never
removes batteries, changes targets, refits a model, invents protocol metadata,
or promotes a favorable subgroup score to the declared validation result.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

from .common import canonical_json, file_sha256

_FIRST_TARGET_CONTEXT_THRESHOLD_PERCENT = 5.0
_LARGE_TARGET_STEP_PERCENT = 20.0
_MIN_ASSOCIATION_BATTERIES = 5
_MIN_TEMPERATURE_STRATUM_BATTERIES = 3
_DUPLICATE_SKIP_REASON = "duplicate_identical_source_copy"

_PROTOCOL_FIELDS = (
    "ambient_temperature_median_c",
    "current_abs_median_a",
    "current_abs_max_a",
    "voltage_min_v",
    "voltage_max_v",
    "sample_interval_median_s",
    "discharge_duration_median_s",
    "initial_discharge_capacity_fraction_of_rated",
    "median_capacity_retention_percent",
)

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


def _as_bool(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False).astype(bool)
    return (
        series.astype(str)
        .str.strip()
        .str.casefold()
        .isin({"true", "1", "yes"})
    )


def _numeric_series(
    frame: pd.DataFrame,
    column: str,
    *,
    default: float = 0.0,
) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(default, index=frame.index, dtype=float)
    return pd.to_numeric(frame[column], errors="coerce").fillna(default)


def _require_columns(frame: pd.DataFrame, required: set[str], *, context: str) -> None:
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"{context} missing required columns: {', '.join(missing)}")


def _normalized_ids(frame: pd.DataFrame, *, context: str) -> pd.Series:
    _require_columns(frame, {"battery_id"}, context=context)
    if frame["battery_id"].isna().any():
        raise ValueError(f"{context} battery_id may not be missing")
    values = frame["battery_id"].astype(str).str.strip()
    if (values == "").any():
        raise ValueError(f"{context} battery_id may not be blank")
    return values


def _stable_ids(frame: pd.DataFrame, *, context: str) -> set[str]:
    return set(_normalized_ids(frame, context=context))


def _inventory_by_battery(inventory: pd.DataFrame) -> pd.DataFrame:
    working = inventory.copy()
    working["battery_id"] = _normalized_ids(
        working, context="NASA source inventory"
    )
    if "skip_reason" in working.columns:
        working = working[
            working["skip_reason"].fillna("") != _DUPLICATE_SKIP_REASON
        ].copy()
    if working.empty:
        raise ValueError("NASA source inventory contains no nonduplicate battery rows")

    count_columns = [
        column for column in _INVENTORY_COUNT_FIELDS if column in working.columns
    ]
    if not count_columns:
        return pd.DataFrame(
            {"battery_id": sorted(set(working["battery_id"]))}
        )
    for column in count_columns:
        working[column] = pd.to_numeric(
            working[column], errors="coerce"
        ).fillna(0)
    return (
        working.groupby("battery_id", sort=True)[count_columns]
        .sum()
        .reset_index()
    )


def _battery_errors(predictions: pd.DataFrame) -> pd.DataFrame:
    required = {
        "battery_id",
        "actual",
        "persistence_prediction",
        "ridge_prediction",
    }
    _require_columns(predictions, required, context="validation predictions")
    if predictions.empty:
        raise ValueError("validation predictions contain no exact-horizon rows")

    working = predictions[list(required)].copy()
    working["battery_id"] = _normalized_ids(
        working, context="validation predictions"
    )
    numeric_columns = ("actual", "persistence_prediction", "ridge_prediction")
    for column in numeric_columns:
        working[column] = pd.to_numeric(working[column], errors="coerce")
    if not np.isfinite(working[list(numeric_columns)].to_numpy(dtype=float)).all():
        raise ValueError("validation predictions must contain finite numeric values")

    working["persistence_absolute_error"] = (
        working["actual"] - working["persistence_prediction"]
    ).abs()
    working["ridge_absolute_error"] = (
        working["actual"] - working["ridge_prediction"]
    ).abs()
    grouped = working.groupby("battery_id", sort=True)
    result = grouped.agg(
        prediction_count=("actual", "size"),
        actual_minimum=("actual", "min"),
        actual_median=("actual", "median"),
        actual_maximum=("actual", "max"),
        persistence_mae=("persistence_absolute_error", "mean"),
        persistence_median_absolute_error=(
            "persistence_absolute_error", "median"
        ),
        ridge_mae=("ridge_absolute_error", "mean"),
        ridge_median_absolute_error=("ridge_absolute_error", "median"),
    ).reset_index()
    result["ridge_minus_persistence_mae"] = (
        result["ridge_mae"] - result["persistence_mae"]
    )
    result["ridge_better_than_persistence"] = (
        result["ridge_minus_persistence_mae"] < 0
    )
    return result


def _reason_columns(profile: pd.DataFrame) -> pd.DataFrame:
    result = profile.copy()
    result["reference_start_context_flag"] = (
        _numeric_series(result, "first_target_deviation_from_100_percent")
        > _FIRST_TARGET_CONTEXT_THRESHOLD_PERCENT
    )
    result["reference_consistency_issue"] = _as_bool(
        result["reference_consistency_flag"]
    )
    result["plausibility_issue"] = (
        _numeric_series(result, "outside_plausibility_count") > 0
    )
    result["cycle_gap_issue"] = _numeric_series(result, "cycle_gap_count") > 0
    result["large_adjacent_target_jump_issue"] = (
        _numeric_series(
            result, "maximum_absolute_adjacent_target_change_percent"
        )
        > _LARGE_TARGET_STEP_PERCENT
    )
    result["invalid_capacity_quarantine_issue"] = (
        _numeric_series(result, "invalid_capacity_operation_count") > 0
    )
    result["evaluation_coverage_issue"] = ~_as_bool(result["is_evaluated"])

    disproportionate_columns = [
        column
        for column in result.columns
        if column.endswith(
            "_is_disproportionate_absolute_error_contributor"
        )
    ]
    result["disproportionate_error_influence"] = (
        result[disproportionate_columns].apply(_as_bool).any(axis=1)
        if disproportionate_columns
        else False
    )
    result["source_quality_issue"] = (
        result["reference_consistency_issue"]
        | result["plausibility_issue"]
        | result["invalid_capacity_quarantine_issue"]
    )
    result["trajectory_continuity_issue"] = (
        result["cycle_gap_issue"] | result["large_adjacent_target_jump_issue"]
    )
    result["structural_or_coverage_issue"] = (
        result["source_quality_issue"]
        | result["trajectory_continuity_issue"]
        | result["evaluation_coverage_issue"]
    )
    result["reference_context_only"] = (
        result["reference_start_context_flag"]
        & ~result["structural_or_coverage_issue"]
        & ~result["disproportionate_error_influence"]
    )

    def render(row: pd.Series, pairs: tuple[tuple[str, str], ...]) -> str:
        return ";".join(label for column, label in pairs if bool(row[column]))

    result["context_reasons"] = result.apply(
        lambda row: render(
            row,
            (("reference_start_context_flag", "first_target_not_near_rated_capacity"),),
        ),
        axis=1,
    )
    result["structural_review_reasons"] = result.apply(
        lambda row: render(
            row,
            (
                ("reference_consistency_issue", "reference_capacity_inconsistent"),
                ("plausibility_issue", "target_outside_plausibility_range"),
                ("invalid_capacity_quarantine_issue", "invalid_capacity_quarantine"),
                ("cycle_gap_issue", "cycle_index_gap"),
                ("large_adjacent_target_jump_issue", "large_adjacent_target_jump"),
                ("evaluation_coverage_issue", "no_exact_horizon_forecast_rows"),
            ),
        ),
        axis=1,
    )
    result["influence_review_reasons"] = result.apply(
        lambda row: render(
            row,
            (("disproportionate_error_influence", "disproportionate_error_influence"),),
        ),
        axis=1,
    )
    return result


def _spearman(x: pd.Series, y: pd.Series) -> float | None:
    pair = pd.DataFrame({"x": x, "y": y}).dropna()
    if len(pair) < _MIN_ASSOCIATION_BATTERIES:
        return None
    if pair["x"].nunique() < 2 or pair["y"].nunique() < 2:
        return None
    ranked = pair.rank(method="average")
    value = float(np.corrcoef(ranked["x"], ranked["y"])[0, 1])
    return value if np.isfinite(value) else None


def _association_table(profile: pd.DataFrame) -> pd.DataFrame:
    outcomes = (
        "persistence_mae",
        "ridge_mae",
        "ridge_minus_persistence_mae",
    )
    rows: list[dict[str, Any]] = []
    for field in _PROTOCOL_FIELDS:
        if field not in profile.columns:
            continue
        values = pd.to_numeric(profile[field], errors="coerce")
        for outcome in outcomes:
            outcome_values = pd.to_numeric(profile[outcome], errors="coerce")
            pair = pd.DataFrame(
                {"condition": values, "outcome": outcome_values}
            ).dropna()
            rho = _spearman(pair["condition"], pair["outcome"])
            rows.append(
                {
                    "condition_field": field,
                    "outcome_field": outcome,
                    "complete_battery_count": int(len(pair)),
                    "condition_unique_value_count": int(
                        pair["condition"].nunique()
                    ),
                    "spearman_rho": rho,
                    "association_status": (
                        "diagnostic_available"
                        if rho is not None
                        else "insufficient_variation_or_support"
                    ),
                    "interpretation_boundary": (
                        "Univariate battery-level rank association only; protocol "
                        "fields are observational, confounded, and do not establish "
                        "causality."
                    ),
                }
            )
    return pd.DataFrame(rows)


def _temperature_strata(
    profile: pd.DataFrame,
    predictions: pd.DataFrame,
) -> pd.DataFrame:
    field = "ambient_temperature_median_c"
    metric_columns = (
        "persistence_row_weighted_mae",
        "ridge_row_weighted_mae",
        "persistence_battery_macro_mae",
        "ridge_battery_macro_mae",
        "ridge_improvement_vs_persistence_percent",
    )
    columns = [
        field,
        "battery_count",
        "evaluated_battery_count",
        "prediction_count",
        "supported_for_within_stratum_description",
        "minimum_required_evaluated_batteries",
        *metric_columns,
        "interpretation_boundary",
    ]
    if field not in profile.columns:
        return pd.DataFrame(columns=columns)

    mapping = profile[["battery_id", field]].copy()
    mapping[field] = pd.to_numeric(mapping[field], errors="coerce")
    rows: list[dict[str, Any]] = []
    for temperature, group in mapping.dropna().groupby(field, sort=True):
        battery_ids = set(group["battery_id"].astype(str))
        subset = predictions[
            predictions["battery_id"].astype(str).isin(battery_ids)
        ].copy()
        evaluated = set(subset["battery_id"].astype(str))
        supported = len(evaluated) >= _MIN_TEMPERATURE_STRATUM_BATTERIES
        row: dict[str, Any] = {
            field: float(temperature),
            "battery_count": int(len(battery_ids)),
            "evaluated_battery_count": int(len(evaluated)),
            "prediction_count": int(len(subset)),
            "supported_for_within_stratum_description": supported,
            "minimum_required_evaluated_batteries": (
                _MIN_TEMPERATURE_STRATUM_BATTERIES
            ),
            "interpretation_boundary": (
                "Exact-temperature metadata are retained for every stratum, but "
                "model metrics are emitted only when at least three evaluated "
                "batteries support within-stratum description."
            ),
        }
        if not supported:
            row.update({column: None for column in metric_columns})
            rows.append(row)
            continue

        subset["persistence_absolute_error"] = (
            subset["actual"] - subset["persistence_prediction"]
        ).abs()
        subset["ridge_absolute_error"] = (
            subset["actual"] - subset["ridge_prediction"]
        ).abs()
        persistence_row = float(subset["persistence_absolute_error"].mean())
        ridge_row = float(subset["ridge_absolute_error"].mean())
        persistence_macro = float(
            subset.groupby("battery_id")["persistence_absolute_error"].mean().mean()
        )
        ridge_macro = float(
            subset.groupby("battery_id")["ridge_absolute_error"].mean().mean()
        )
        row.update(
            {
                "persistence_row_weighted_mae": persistence_row,
                "ridge_row_weighted_mae": ridge_row,
                "persistence_battery_macro_mae": persistence_macro,
                "ridge_battery_macro_mae": ridge_macro,
                "ridge_improvement_vs_persistence_percent": float(
                    100.0
                    * (persistence_row - ridge_row)
                    / max(persistence_row, np.finfo(float).eps)
                ),
            }
        )
        rows.append(row)
    return pd.DataFrame(rows, columns=columns)


def _primary_model_result(persistence_mae: float, ridge_mae: float) -> str:
    if ridge_mae > persistence_mae:
        return "Persistence remains better than Ridge on the declared pooled validation."
    if ridge_mae < persistence_mae:
        return (
            "Ridge is lower than persistence on the declared pooled validation; "
            "protocol diagnostics remain post-hoc and do not independently upgrade "
            "the declared evidence level."
        )
    return "Persistence and Ridge have equal pooled MAE on the declared validation."


def build_nasa_protocol_audit(
    *,
    protocol_summary: pd.DataFrame,
    source_inventory: pd.DataFrame,
    target_integrity: pd.DataFrame,
    diagnostic_priority: pd.DataFrame,
    predictions: pd.DataFrame,
    signal_feature_comparison: Mapping[str, Any] | None = None,
    declared_evidence_level: str | None = None,
) -> dict[str, Any]:
    """Build protocol-aware diagnostics from existing official-run artifacts."""
    protocol_ids = _stable_ids(protocol_summary, context="NASA protocol summary")
    target_ids = _stable_ids(target_integrity, context="target integrity")
    priority_ids = _stable_ids(diagnostic_priority, context="diagnostic priority")
    if target_ids != protocol_ids:
        raise ValueError("NASA protocol and target-integrity battery identities differ")
    if priority_ids != protocol_ids:
        raise ValueError("NASA protocol and diagnostic-priority battery identities differ")

    inventory = _inventory_by_battery(source_inventory)
    inventory_ids = set(inventory["battery_id"].astype(str))
    missing_inventory = protocol_ids - inventory_ids
    if missing_inventory:
        raise ValueError(
            "NASA source inventory is missing protocol batteries: "
            + ", ".join(sorted(missing_inventory))
        )

    prediction_ids = _stable_ids(predictions, context="validation predictions")
    unknown_predictions = prediction_ids - protocol_ids
    if unknown_predictions:
        raise ValueError(
            "validation predictions contain batteries absent from NASA protocol "
            "summary: " + ", ".join(sorted(unknown_predictions))
        )

    protocol = protocol_summary.copy()
    protocol["battery_id"] = _normalized_ids(
        protocol, context="NASA protocol summary"
    )
    target = target_integrity.copy()
    target["battery_id"] = _normalized_ids(target, context="target integrity")
    priority = diagnostic_priority.copy()
    priority["battery_id"] = _normalized_ids(
        priority, context="diagnostic priority"
    )
    errors = _battery_errors(predictions)

    _require_columns(
        target,
        {
            "battery_id",
            "first_target_deviation_from_100_percent",
            "reference_consistency_flag",
            "outside_plausibility_count",
            "cycle_gap_count",
            "maximum_absolute_adjacent_target_change_percent",
        },
        context="target integrity",
    )
    priority_columns = [
        "battery_id",
        *[
            column
            for column in priority.columns
            if column.endswith(
                "_is_disproportionate_absolute_error_contributor"
            )
        ],
    ]
    profile = protocol.merge(
        target, on="battery_id", how="left", validate="one_to_one"
    )
    profile = profile.merge(
        priority[priority_columns],
        on="battery_id",
        how="left",
        validate="one_to_one",
    )
    profile = profile.merge(
        inventory, on="battery_id", how="left", validate="one_to_one"
    )
    profile = profile.merge(
        errors, on="battery_id", how="left", validate="one_to_one"
    )
    profile["is_evaluated"] = profile["prediction_count"].notna()
    profile["prediction_count"] = profile["prediction_count"].fillna(0).astype(int)
    profile = _reason_columns(profile)

    predictions_working = predictions.copy()
    predictions_working["battery_id"] = _normalized_ids(
        predictions_working, context="validation predictions"
    )
    for column in ("actual", "persistence_prediction", "ridge_prediction"):
        predictions_working[column] = pd.to_numeric(
            predictions_working[column], errors="coerce"
        )

    associations = _association_table(profile)
    strata = _temperature_strata(profile, predictions_working)
    evaluated = profile[profile["is_evaluated"]].copy()
    persistence_errors = np.abs(
        predictions_working["actual"].to_numpy(dtype=float)
        - predictions_working["persistence_prediction"].to_numpy(dtype=float)
    )
    ridge_errors = np.abs(
        predictions_working["actual"].to_numpy(dtype=float)
        - predictions_working["ridge_prediction"].to_numpy(dtype=float)
    )
    persistence_row = float(np.mean(persistence_errors))
    ridge_row = float(np.mean(ridge_errors))
    signal_comparison = dict(signal_feature_comparison or {})
    evidence_level = str(declared_evidence_level or "Inconclusive")

    summary = {
        "schema_version": "1.2",
        "battery_count": int(len(profile)),
        "evaluated_battery_count": int(profile["is_evaluated"].sum()),
        "unevaluated_battery_count": int((~profile["is_evaluated"]).sum()),
        "reference_start_context_battery_count": int(
            profile["reference_start_context_flag"].sum()
        ),
        "reference_context_only_battery_count": int(
            profile["reference_context_only"].sum()
        ),
        "source_quality_issue_battery_count": int(
            profile["source_quality_issue"].sum()
        ),
        "trajectory_continuity_issue_battery_count": int(
            profile["trajectory_continuity_issue"].sum()
        ),
        "structural_or_coverage_issue_battery_count": int(
            profile["structural_or_coverage_issue"].sum()
        ),
        "disproportionate_error_influence_battery_count": int(
            profile["disproportionate_error_influence"].sum()
        ),
        "invalid_capacity_quarantine_operation_count": int(
            _numeric_series(profile, "invalid_capacity_operation_count").sum()
        ),
        "cycle_gap_battery_count": int(profile["cycle_gap_issue"].sum()),
        "large_adjacent_target_jump_battery_count": int(
            profile["large_adjacent_target_jump_issue"].sum()
        ),
        "persistence_row_weighted_mae": persistence_row,
        "ridge_row_weighted_mae": ridge_row,
        "ridge_improvement_vs_persistence_percent": float(
            100.0
            * (persistence_row - ridge_row)
            / max(persistence_row, np.finfo(float).eps)
        ),
        "ridge_better_than_persistence_battery_count": int(
            evaluated["ridge_better_than_persistence"].sum()
        ),
        "evaluated_battery_count_for_pairwise_model_comparison": int(
            len(evaluated)
        ),
        "capacity_only_ridge_mae": signal_comparison.get(
            "capacity_only_ridge_mae"
        ),
        "signal_enriched_ridge_mae": signal_comparison.get(
            "signal_enriched_ridge_mae"
        ),
        "signal_enriched_improvement_percent": signal_comparison.get(
            "improvement_percent"
        ),
        "temperature_stratum_count": int(len(strata)),
        "supported_temperature_stratum_count": int(
            strata.get(
                "supported_for_within_stratum_description",
                pd.Series(dtype=bool),
            )
            .fillna(False)
            .sum()
        ),
        "association_count": int(len(associations)),
        "diagnostic_association_count": int(
            (
                associations.get(
                    "association_status", pd.Series(dtype=str)
                )
                == "diagnostic_available"
            ).sum()
        ),
        "predictive_evidence_level": evidence_level,
        "protocol_audit_status": "Diagnostic",
        "primary_model_result": _primary_model_result(
            persistence_row, ridge_row
        ),
        "reference_start_semantics": (
            "Deviation of the first observed discharge from the documented 2 Ah "
            "rating is context, not by itself a hard target-integrity failure."
        ),
        "evidence_preservation_boundary": (
            "The protocol audit preserves the pre-existing scientific closeout "
            "evidence level and does not independently upgrade or downgrade it."
        ),
        "scientific_boundary": (
            "All batteries remain in the profile. Supported exact-temperature "
            "strata and rank associations are post-hoc diagnostics only. No protocol "
            "identity is invented, no battery is deleted, no model is refit, and no "
            "subgroup metric replaces the declared battery-disjoint validation result."
        ),
    }
    return {
        "battery_profile": profile.sort_values(
            "battery_id", kind="mergesort"
        ).reset_index(drop=True),
        "temperature_strata": strata,
        "error_associations": associations,
        "summary": summary,
    }


def _markdown(summary: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            "# NASA PCoE Protocol-Aware Post-hoc Audit",
            "",
            "## Result",
            "",
            f"- Protocol audit status: `{summary['protocol_audit_status']}`",
            f"- Preserved predictive evidence level: `{summary['predictive_evidence_level']}`",
            f"- Evaluated batteries: `{summary['evaluated_battery_count']}` / `{summary['battery_count']}`",
            f"- Rated-reference start context: `{summary['reference_start_context_battery_count']}` batteries",
            f"- Reference-context-only batteries: `{summary['reference_context_only_battery_count']}`",
            f"- Source-quality issues: `{summary['source_quality_issue_battery_count']}` batteries",
            f"- Trajectory-continuity issues: `{summary['trajectory_continuity_issue_battery_count']}` batteries",
            f"- Structural or coverage issues: `{summary['structural_or_coverage_issue_battery_count']}` batteries",
            f"- Disproportionate error influence: `{summary['disproportionate_error_influence_battery_count']}` batteries",
            f"- Invalid Capacity operations quarantined: `{summary['invalid_capacity_quarantine_operation_count']}`",
            f"- Persistence row-weighted MAE: `{summary['persistence_row_weighted_mae']}`",
            f"- Ridge row-weighted MAE: `{summary['ridge_row_weighted_mae']}`",
            f"- Ridge improvement vs persistence: `{summary['ridge_improvement_vs_persistence_percent']}%`",
            f"- Batteries where Ridge beats persistence: `{summary['ridge_better_than_persistence_battery_count']}` / `{summary['evaluated_battery_count_for_pairwise_model_comparison']}`",
            f"- Signal-enriched Ridge improvement: `{summary['signal_enriched_improvement_percent']}%`",
            "",
            "## Primary model result",
            "",
            str(summary["primary_model_result"]),
            "",
            "## Reference-start interpretation",
            "",
            str(summary["reference_start_semantics"]),
            "",
            "## Evidence preservation",
            "",
            str(summary["evidence_preservation_boundary"]),
            "",
            "## Scientific boundary",
            "",
            str(summary["scientific_boundary"]),
            "",
        ]
    )


def _diagnostic_limitation(summary: Mapping[str, Any]) -> str:
    observed: list[str] = []
    if int(summary["reference_start_context_battery_count"]) > 0:
        observed.append("rated-reference start heterogeneity")
    if int(summary["source_quality_issue_battery_count"]) > 0:
        observed.append("source-quality quarantine or consistency concerns")
    if int(summary["trajectory_continuity_issue_battery_count"]) > 0:
        observed.append("trajectory discontinuities")
    if int(summary["unevaluated_battery_count"]) > 0:
        observed.append("incomplete exact-horizon coverage")
    if int(summary["supported_temperature_stratum_count"]) > 0 or int(
        summary["diagnostic_association_count"]
    ) > 0:
        observed.append("supported condition-related diagnostic structure")

    if observed:
        return (
            "Protocol-aware post-hoc diagnostics identified "
            + ", ".join(observed)
            + "; these observations are diagnostic and do not establish a "
            "transferable predictive model."
        )
    return (
        "Protocol-aware post-hoc diagnostics did not identify supported structural "
        "or condition-related evidence; predictive transferability remains "
        "unestablished."
    )


def _replace_marked_section(
    current: str,
    *,
    start: str,
    end: str,
    section: str,
) -> str:
    if start not in current:
        prefix = current.rstrip()
        return (prefix + "\n\n" + section.strip() + "\n").lstrip("\n")
    start_index = current.index(start)
    end_index = current.find(end, start_index + len(start))
    if end_index < 0:
        raise ValueError(f"closeout markdown contains {start!r} without {end!r}")
    end_index += len(end)
    prefix = current[:start_index].rstrip()
    suffix = current[end_index:].strip("\n")
    parts = [part for part in (prefix, section.strip(), suffix) if part]
    return "\n\n".join(parts) + "\n"


def _update_closeout(analysis_output: Path, summary: Mapping[str, Any]) -> None:
    reports = analysis_output / "reports"
    closeout_path = reports / "scientific_closeout.json"
    markdown_path = reports / "scientific_closeout.md"
    limitation = _diagnostic_limitation(summary)

    if closeout_path.is_file():
        closeout = json.loads(closeout_path.read_text(encoding="utf-8"))
        closeout.setdefault("component_statuses", {})[
            "nasa_protocol_aware_posthoc_audit"
        ] = {
            "status": "Diagnostic",
            "scope": (
                "Rated-reference start context, source-quality quarantine, "
                "trajectory continuity, validation coverage, protocol fields, and "
                "model error were separated without filtering or refitting."
            ),
        }
        closeout.setdefault("strongest_evidence", {})[
            "nasa_protocol_aware_posthoc_audit"
        ] = dict(summary)
        limitations = closeout.setdefault("limitations", [])
        if limitation not in limitations:
            limitations.append(limitation)
        primary = str(closeout.get("primary_limitation", ""))
        if limitation not in primary:
            closeout["primary_limitation"] = (limitation + " " + primary).strip()
        closeout_path.write_text(canonical_json(closeout), encoding="utf-8")

    if markdown_path.is_file():
        start = "<!-- nasa-protocol-audit:start -->"
        end = "<!-- nasa-protocol-audit:end -->"
        current = markdown_path.read_text(encoding="utf-8")
        section = (
            f"{start}\n\n## NASA Protocol-Aware Post-hoc Audit\n\n"
            f"- Status: `Diagnostic`\n"
            f"- Preserved predictive evidence: "
            f"`{summary['predictive_evidence_level']}`\n"
            f"- Structural or coverage issues: "
            f"`{summary['structural_or_coverage_issue_battery_count']}` / "
            f"`{summary['battery_count']}` batteries\n"
            f"- Reference-start context only: "
            f"`{summary['reference_context_only_battery_count']}` batteries\n"
            f"- Limitation: {limitation}\n"
            f"- Scientific boundary: {summary['scientific_boundary']}\n\n{end}"
        )
        markdown_path.write_text(
            _replace_marked_section(
                current, start=start, end=end, section=section
            ),
            encoding="utf-8",
        )


def audit_nasa_protocol_run(
    *,
    import_output: str | Path,
    analysis_output: str | Path,
) -> dict[str, Any]:
    """Audit an existing official NASA import and analysis without model refitting."""
    import_root = Path(import_output)
    analysis_root = Path(analysis_output)
    tables = analysis_root / "tables"
    reports = analysis_root / "reports"
    required = {
        "protocol": import_root / "nasa_pcoe_protocol_summary.csv",
        "inventory": import_root / "nasa_pcoe_source_inventory.csv",
        "target": tables / "target_integrity_by_battery.csv",
        "priority": tables / "battery_diagnostic_priority.csv",
        "predictions": tables / "validation_predictions.csv",
    }
    missing = [name for name, path in required.items() if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            "NASA protocol audit missing required artifacts: "
            + ", ".join(missing)
        )

    signal_path = reports / "signal_feature_comparison.json"
    signal_comparison = (
        json.loads(signal_path.read_text(encoding="utf-8"))
        if signal_path.is_file()
        else None
    )
    closeout_path = reports / "scientific_closeout.json"
    declared_evidence_level: str | None = None
    if closeout_path.is_file():
        closeout = json.loads(closeout_path.read_text(encoding="utf-8"))
        if closeout.get("evidence_level") is not None:
            declared_evidence_level = str(closeout["evidence_level"])

    audit = build_nasa_protocol_audit(
        protocol_summary=pd.read_csv(required["protocol"]),
        source_inventory=pd.read_csv(required["inventory"]),
        target_integrity=pd.read_csv(required["target"]),
        diagnostic_priority=pd.read_csv(required["priority"]),
        predictions=pd.read_csv(required["predictions"]),
        signal_feature_comparison=signal_comparison,
        declared_evidence_level=declared_evidence_level,
    )

    profile_path = tables / "nasa_protocol_battery_profile.csv"
    strata_path = tables / "nasa_protocol_temperature_strata.csv"
    association_path = tables / "nasa_protocol_error_associations.csv"
    report_path = reports / "nasa_protocol_audit.json"
    markdown_path = reports / "nasa_protocol_audit.md"
    audit["battery_profile"].to_csv(profile_path, index=False)
    audit["temperature_strata"].to_csv(strata_path, index=False)
    audit["error_associations"].to_csv(association_path, index=False)
    report_path.write_text(canonical_json(audit["summary"]), encoding="utf-8")
    markdown_path.write_text(_markdown(audit["summary"]), encoding="utf-8")
    _update_closeout(analysis_root, audit["summary"])

    manifest_path = analysis_root / "run_manifest.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["nasa_protocol_aware_posthoc_audit"] = audit["summary"]
        if closeout_path.is_file():
            closeout = json.loads(closeout_path.read_text(encoding="utf-8"))
            manifest["scientific_closeout"] = closeout
            manifest["limitations"] = list(closeout.get("limitations", []))
            manifest["scientific_validation"] = closeout.get(
                "evidence_level", manifest.get("scientific_validation")
            )
        paths = [
            profile_path,
            strata_path,
            association_path,
            report_path,
            markdown_path,
            reports / "scientific_closeout.json",
            reports / "scientific_closeout.md",
        ]
        relative = [
            path.relative_to(analysis_root).as_posix() for path in paths
        ]
        manifest["artifact_paths"] = sorted(
            set(manifest.get("artifact_paths", [])) | set(relative)
        )
        checksums = dict(manifest.get("artifact_checksums", {}))
        for path, name in zip(paths, relative, strict=True):
            if path.is_file():
                checksums[name] = file_sha256(path)
        manifest["artifact_checksums"] = checksums
        manifest_path.write_text(canonical_json(manifest), encoding="utf-8")

    return {
        "summary": audit["summary"],
        "outputs": {
            "battery_profile": str(profile_path),
            "temperature_strata": str(strata_path),
            "error_associations": str(association_path),
            "protocol_audit": str(report_path),
            "protocol_audit_markdown": str(markdown_path),
        },
    }
