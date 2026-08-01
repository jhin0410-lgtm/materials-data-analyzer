"""Battery-level influence and observed-condition triage for pooled forecasts.

This module is diagnostic only. Leave-one-battery-out metrics quantify sensitivity
to an observed battery; they are not replacement validation scores and do not
authorize filtering, cohort reassignment, or protocol inference.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

from .common import canonical_json, file_sha256

_FIRST_TARGET_TOLERANCE_PERCENT = 5.0
_LARGE_TARGET_STEP_PERCENT = 20.0


def _model_names(predictions: pd.DataFrame) -> list[str]:
    models = sorted(
        {
            column.removesuffix("_prediction")
            for column in predictions.columns
            if column.endswith("_prediction")
            and column
            not in {"prediction_interval_low", "prediction_interval_high"}
        }
    )
    if not models:
        raise ValueError("validation predictions contain no model prediction columns")
    return models


def _flag_reasons(row: pd.Series) -> list[str]:
    reasons: list[str] = []
    if float(row.get("outside_plausibility_count", 0) or 0) > 0:
        reasons.append("target_outside_plausibility_range")
    if bool(row.get("reference_consistency_flag", False)):
        reasons.append("reference_capacity_inconsistent")
    if (
        float(row.get("first_target_deviation_from_100_percent", 0) or 0)
        > _FIRST_TARGET_TOLERANCE_PERCENT
    ):
        reasons.append("first_target_not_near_100_percent")
    if (
        float(row.get("maximum_absolute_adjacent_target_change_percent", 0) or 0)
        > _LARGE_TARGET_STEP_PERCENT
    ):
        reasons.append("large_adjacent_target_jump")
    if float(row.get("cycle_gap_count", 0) or 0) > 0:
        reasons.append("cycle_index_gap")
    return reasons


def _build_influence_table(
    predictions: pd.DataFrame,
    *,
    group_column: str,
) -> tuple[pd.DataFrame, dict[str, dict[str, float]]]:
    required = {group_column, "actual"}
    missing = sorted(required - set(predictions.columns))
    if missing:
        raise ValueError(
            "validation predictions missing required influence columns: "
            + ", ".join(missing)
        )
    models = _model_names(predictions)
    rows: list[dict[str, Any]] = []
    model_summary: dict[str, dict[str, float]] = {}

    for model in models:
        prediction_column = f"{model}_prediction"
        actual = predictions["actual"].to_numpy(dtype=float)
        predicted = predictions[prediction_column].to_numpy(dtype=float)
        errors = np.abs(actual - predicted)
        if not np.isfinite(errors).all():
            raise ValueError(f"{model} absolute errors must be finite")

        working = predictions[[group_column]].copy()
        working["absolute_error"] = errors
        per_battery = (
            working.groupby(group_column, sort=True)["absolute_error"]
            .agg(["count", "sum", "mean", "median", "max"])
            .reset_index()
        )
        full_row_mae = float(np.mean(errors))
        full_macro_mae = float(per_battery["mean"].mean())
        total_error = float(np.sum(errors))
        model_summary[model] = {
            "row_weighted_mae": full_row_mae,
            "battery_macro_mae": full_macro_mae,
            "row_to_macro_mae_ratio": float(
                full_row_mae / max(full_macro_mae, np.finfo(float).eps)
            ),
        }

        for _, battery in per_battery.iterrows():
            battery_id = battery[group_column]
            mask = predictions[group_column] != battery_id
            remaining = predictions.loc[mask]
            if remaining.empty:
                omitted_row_mae: float | None = None
                omitted_macro_mae: float | None = None
            else:
                remaining_errors = np.abs(
                    remaining["actual"].to_numpy(dtype=float)
                    - remaining[prediction_column].to_numpy(dtype=float)
                )
                omitted_row_mae = float(np.mean(remaining_errors))
                remaining_macro = (
                    pd.DataFrame(
                        {
                            group_column: remaining[group_column].to_numpy(),
                            "absolute_error": remaining_errors,
                        }
                    )
                    .groupby(group_column, sort=True)["absolute_error"]
                    .mean()
                )
                omitted_macro_mae = float(remaining_macro.mean())

            error_fraction = float(
                battery["sum"] / max(total_error, np.finfo(float).eps)
            )
            equal_share = float(1.0 / len(per_battery))
            rows.append(
                {
                    group_column: battery_id,
                    "model": model,
                    "prediction_count": int(battery["count"]),
                    "battery_absolute_error_sum": float(battery["sum"]),
                    "battery_mae": float(battery["mean"]),
                    "battery_median_absolute_error": float(battery["median"]),
                    "battery_maximum_absolute_error": float(battery["max"]),
                    "total_absolute_error_fraction": error_fraction,
                    "equal_error_share_baseline": equal_share,
                    "absolute_error_contribution_excess_ratio": float(
                        error_fraction / max(equal_share, np.finfo(float).eps)
                    ),
                    "full_row_weighted_mae": full_row_mae,
                    "row_weighted_mae_without_battery": omitted_row_mae,
                    "row_weighted_mae_reduction_if_omitted": (
                        float(full_row_mae - omitted_row_mae)
                        if omitted_row_mae is not None
                        else None
                    ),
                    "full_battery_macro_mae": full_macro_mae,
                    "battery_macro_mae_without_battery": omitted_macro_mae,
                    "battery_macro_mae_reduction_if_omitted": (
                        float(full_macro_mae - omitted_macro_mae)
                        if omitted_macro_mae is not None
                        else None
                    ),
                    "interpretation_boundary": (
                        "Sensitivity only; omission metrics are not replacement "
                        "validation scores and do not authorize battery removal."
                    ),
                }
            )

    result = pd.DataFrame(rows)
    result["absolute_error_contribution_rank"] = (
        result.groupby("model", sort=False)["total_absolute_error_fraction"]
        .rank(method="first", ascending=False)
        .astype(int)
    )
    result["row_weighted_influence_rank"] = (
        result.groupby("model", sort=False)["row_weighted_mae_reduction_if_omitted"]
        .rank(method="first", ascending=False, na_option="bottom")
        .astype(int)
    )
    result["is_top_three_absolute_error_contributor"] = (
        result["absolute_error_contribution_rank"] <= 3
    )
    result["is_top_three_row_weighted_influence"] = (
        result["row_weighted_influence_rank"] <= 3
    )
    result["is_disproportionate_absolute_error_contributor"] = (
        result["absolute_error_contribution_excess_ratio"] > 1.5
    )
    return (
        result.sort_values(
            ["model", "absolute_error_contribution_rank", group_column],
            kind="mergesort",
        ).reset_index(drop=True),
        model_summary,
    )


def _build_priority_table(
    target_integrity: pd.DataFrame,
    influence: pd.DataFrame,
    *,
    group_column: str,
) -> pd.DataFrame:
    priority = target_integrity.copy()
    priority["diagnostic_flag_reasons"] = priority.apply(
        lambda row: ";".join(_flag_reasons(row)), axis=1
    )
    priority["has_diagnostic_flag_reason"] = (
        priority["diagnostic_flag_reasons"].str.len() > 0
    )

    for model in sorted(influence["model"].unique()):
        columns = [
            "battery_mae",
            "total_absolute_error_fraction",
            "row_weighted_mae_reduction_if_omitted",
            "battery_macro_mae_reduction_if_omitted",
            "absolute_error_contribution_rank",
            "row_weighted_influence_rank",
            "is_top_three_absolute_error_contributor",
            "is_top_three_row_weighted_influence",
            "absolute_error_contribution_excess_ratio",
            "is_disproportionate_absolute_error_contributor",
        ]
        model_rows = influence[influence["model"] == model][
            [group_column, *columns]
        ].rename(columns={column: f"{model}_{column}" for column in columns})
        priority = priority.merge(
            model_rows,
            on=group_column,
            how="left",
            validate="one_to_one",
        )

    disproportionate_columns = [
        column
        for column in priority.columns
        if column.endswith("_is_disproportionate_absolute_error_contributor")
    ]
    fraction_columns = [
        column
        for column in priority.columns
        if column.endswith("_total_absolute_error_fraction")
    ]
    influence_columns = [
        column
        for column in priority.columns
        if column.endswith("_row_weighted_mae_reduction_if_omitted")
    ]
    priority["disproportionate_error_contributor_any_model"] = (
        priority[disproportionate_columns].fillna(False).any(axis=1)
        if disproportionate_columns
        else False
    )
    priority["maximum_model_absolute_error_fraction"] = (
        priority[fraction_columns].max(axis=1, skipna=True)
        if fraction_columns
        else np.nan
    )
    priority["maximum_row_weighted_mae_reduction_if_omitted"] = (
        priority[influence_columns].max(axis=1, skipna=True)
        if influence_columns
        else np.nan
    )
    priority["requires_source_protocol_review"] = (
        priority["has_diagnostic_flag_reason"]
        | priority["disproportionate_error_contributor_any_model"]
    )
    priority = priority.sort_values(
        [
            "requires_source_protocol_review",
            "maximum_model_absolute_error_fraction",
            "maximum_row_weighted_mae_reduction_if_omitted",
            group_column,
        ],
        ascending=[False, False, False, True],
        kind="mergesort",
    ).reset_index(drop=True)
    priority["diagnostic_review_order"] = np.arange(1, len(priority) + 1)
    return priority


def _top_records(
    influence: pd.DataFrame,
    *,
    model: str,
    group_column: str,
    order_column: str,
    count: int = 5,
) -> list[dict[str, Any]]:
    subset = (
        influence[influence["model"] == model]
        .sort_values(
            [order_column, group_column],
            ascending=[False, True],
            kind="mergesort",
        )
        .head(count)
    )
    fields = [
        group_column,
        "battery_mae",
        "total_absolute_error_fraction",
        "row_weighted_mae_reduction_if_omitted",
        "battery_macro_mae_reduction_if_omitted",
    ]
    return [
        {
            key: (
                None
                if pd.isna(row[key])
                else float(row[key])
                if key != group_column
                else row[key]
            )
            for key in fields
        }
        for _, row in subset.iterrows()
    ]


def build_battery_influence_triage(
    *,
    target_integrity: pd.DataFrame,
    predictions: pd.DataFrame,
    group_column: str,
) -> dict[str, Any]:
    """Build influence and condition-review tables without changing validation."""
    if group_column not in target_integrity.columns:
        raise ValueError(
            f"target integrity table missing configured group column: {group_column}"
        )
    influence, model_summary = _build_influence_table(
        predictions,
        group_column=group_column,
    )
    priority = _build_priority_table(
        target_integrity,
        influence,
        group_column=group_column,
    )

    models = sorted(influence["model"].unique())
    top_error = {
        model: _top_records(
            influence,
            model=model,
            group_column=group_column,
            order_column="total_absolute_error_fraction",
        )
        for model in models
    }
    top_influence = {
        model: _top_records(
            influence,
            model=model,
            group_column=group_column,
            order_column="row_weighted_mae_reduction_if_omitted",
        )
        for model in models
    }
    condition_columns = [
        column
        for column in priority.columns
        if column.startswith("median_observed_")
    ]
    model_profile_columns = [
        column
        for column in priority.columns
        if column.endswith("_battery_mae")
        or column.endswith("_total_absolute_error_fraction")
        or column.endswith("_row_weighted_mae_reduction_if_omitted")
    ]
    condition_profile = priority[
        [
            group_column,
            "diagnostic_review_order",
            "diagnostic_flag_reasons",
            "requires_source_protocol_review",
            *condition_columns,
            *model_profile_columns,
        ]
    ].copy()

    review_count = int(priority["requires_source_protocol_review"].sum())
    summary = {
        "schema_version": "1.0",
        "battery_count": int(len(priority)),
        "models": models,
        "model_metric_summary": model_summary,
        "source_protocol_review_battery_count": review_count,
        "target_or_continuity_flag_battery_count": int(
            priority["has_diagnostic_flag_reason"].sum()
        ),
        "disproportionate_error_contributor_battery_count": int(
            priority["disproportionate_error_contributor_any_model"].sum()
        ),
        "top_absolute_error_contributors": top_error,
        "top_row_weighted_influence": top_influence,
        "observed_condition_columns": condition_columns,
        "pooled_interpretation": (
            "diagnostic_only"
            if review_count > 0
            else "not_flagged_but_protocol_identity_unverified"
        ),
        "scientific_boundary": (
            "Leave-one-battery-out deltas quantify sensitivity of the already "
            "computed pooled metric. They are not replacement validation scores, "
            "do not prove a battery is erroneous, do not infer protocol identity, "
            "and do not justify deletion or favorable cohort selection."
        ),
    }
    return {
        "influence_by_model": influence,
        "diagnostic_priority": priority,
        "condition_error_profile": condition_profile,
        "summary": summary,
    }


def _markdown(summary: Mapping[str, Any]) -> str:
    lines = [
        "# Battery Influence and Observed-Condition Triage",
        "",
        "This report is diagnostic only. No battery, row, target, or prediction was removed or recomputed.",
        "",
        "## Result",
        "",
        f"- Pooled interpretation: `{summary['pooled_interpretation']}`",
        f"- Batteries requiring source/protocol review: `{summary['source_protocol_review_battery_count']}` / `{summary['battery_count']}`",
        f"- Batteries with target or continuity reasons: `{summary['target_or_continuity_flag_battery_count']}`",
        f"- Batteries with disproportionate error contribution: `{summary['disproportionate_error_contributor_battery_count']}`",
        "",
        "## Model Metrics",
        "",
    ]
    for model, metrics in summary["model_metric_summary"].items():
        lines.append(
            f"- `{model}` row-weighted MAE `{metrics['row_weighted_mae']}`, "
            f"battery-macro MAE `{metrics['battery_macro_mae']}`, "
            f"row/macro ratio `{metrics['row_to_macro_mae_ratio']}`"
        )
    lines.extend(["", "## Top Absolute-Error Contributors", ""])
    for model, records in summary["top_absolute_error_contributors"].items():
        rendered = ", ".join(
            f"{record[next(iter(record))]} ({record['total_absolute_error_fraction']:.6f})"
            for record in records
        )
        lines.append(f"- `{model}`: {rendered}")
    lines.extend(
        [
            "",
            "## Interpretation Boundary",
            "",
            str(summary["scientific_boundary"]),
            "",
        ]
    )
    return "\n".join(lines)


def _update_closeout(output: Path, summary: Mapping[str, Any]) -> None:
    reports = output / "reports"
    closeout_path = reports / "scientific_closeout.json"
    markdown_path = reports / "scientific_closeout.md"
    limitation = (
        "Battery-level omission deltas and observed-condition profiles show that "
        "pooled scores require source- and protocol-aware review; omission "
        "sensitivity is diagnostic and cannot be used as a replacement score."
    )
    if closeout_path.is_file():
        closeout = json.loads(closeout_path.read_text(encoding="utf-8"))
        closeout.setdefault("component_statuses", {})[
            "battery_influence_and_observed_condition_triage"
        ] = {
            "status": (
                "Diagnostic"
                if summary["source_protocol_review_battery_count"] > 0
                else "Inconclusive"
            ),
            "scope": (
                "Battery-level pooled-error influence, target/continuity reasons, "
                "and observed-condition profiles were reported without filtering."
            ),
        }
        closeout.setdefault("strongest_evidence", {})[
            "battery_influence_triage"
        ] = dict(summary)
        limitations = closeout.setdefault("limitations", [])
        if limitation not in limitations:
            limitations.append(limitation)
        current_primary = str(closeout.get("primary_limitation", ""))
        if limitation not in current_primary:
            closeout["primary_limitation"] = (
                limitation + " " + current_primary
            ).strip()
        closeout_path.write_text(canonical_json(closeout), encoding="utf-8")

    if markdown_path.is_file():
        start = "<!-- battery-influence-triage:start -->"
        end = "<!-- battery-influence-triage:end -->"
        current = markdown_path.read_text(encoding="utf-8")
        prefix = (
            current.split(start, 1)[0].rstrip()
            if start in current
            else current.rstrip()
        )
        section = (
            f"{start}\n\n## Battery Influence and Observed-Condition Triage\n\n"
            f"- Pooled interpretation: `{summary['pooled_interpretation']}`\n"
            f"- Batteries requiring source/protocol review: "
            f"`{summary['source_protocol_review_battery_count']}` / "
            f"`{summary['battery_count']}`\n"
            f"- Scientific boundary: {summary['scientific_boundary']}\n\n{end}\n"
        )
        markdown_path.write_text(prefix + "\n\n" + section, encoding="utf-8")


def audit_battery_influence_run(output_dir: str | Path) -> dict[str, Any]:
    """Audit an existing Battery Intelligence run and persist influence artifacts."""
    output = Path(output_dir)
    tables = output / "tables"
    reports = output / "reports"
    required = {
        "target": tables / "target_integrity_by_battery.csv",
        "predictions": tables / "validation_predictions.csv",
        "config": output / "config_snapshot.json",
    }
    missing = [name for name, path in required.items() if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            "battery run is missing required influence artifacts: " + ", ".join(missing)
        )
    config_payload = json.loads(required["config"].read_text(encoding="utf-8"))
    group_column = str(config_payload["config"]["group_column"])
    triage = build_battery_influence_triage(
        target_integrity=pd.read_csv(required["target"]),
        predictions=pd.read_csv(required["predictions"]),
        group_column=group_column,
    )

    influence_path = tables / "battery_influence_by_model.csv"
    priority_path = tables / "battery_diagnostic_priority.csv"
    condition_path = tables / "battery_condition_error_profile.csv"
    report_path = reports / "battery_influence_triage.json"
    markdown_path = reports / "battery_influence_triage.md"
    triage["influence_by_model"].to_csv(influence_path, index=False)
    triage["diagnostic_priority"].to_csv(priority_path, index=False)
    triage["condition_error_profile"].to_csv(condition_path, index=False)
    report_path.write_text(canonical_json(triage["summary"]), encoding="utf-8")
    markdown_path.write_text(_markdown(triage["summary"]), encoding="utf-8")
    _update_closeout(output, triage["summary"])

    manifest_path = output / "run_manifest.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        closeout_path = reports / "scientific_closeout.json"
        if closeout_path.is_file():
            closeout = json.loads(closeout_path.read_text(encoding="utf-8"))
            manifest["scientific_closeout"] = closeout
            manifest["limitations"] = list(closeout.get("limitations", []))
            if "evidence_level" in closeout:
                manifest["scientific_validation"] = closeout["evidence_level"]
        manifest["battery_influence_triage"] = triage["summary"]
        paths = [
            influence_path,
            priority_path,
            condition_path,
            report_path,
            markdown_path,
            reports / "scientific_closeout.json",
            reports / "scientific_closeout.md",
        ]
        relative_paths = [path.relative_to(output).as_posix() for path in paths]
        manifest["artifact_paths"] = sorted(
            set(manifest.get("artifact_paths", [])) | set(relative_paths)
        )
        checksums = dict(manifest.get("artifact_checksums", {}))
        for path, relative in zip(paths, relative_paths, strict=True):
            if path.is_file():
                checksums[relative] = file_sha256(path)
        manifest["artifact_checksums"] = checksums
        manifest_path.write_text(canonical_json(manifest), encoding="utf-8")

    return {
        "summary": triage["summary"],
        "outputs": {
            "battery_influence_by_model": str(influence_path),
            "battery_diagnostic_priority": str(priority_path),
            "battery_condition_error_profile": str(condition_path),
            "battery_influence_triage": str(report_path),
            "battery_influence_markdown": str(markdown_path),
        },
    }
