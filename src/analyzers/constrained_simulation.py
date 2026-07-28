"""Constraint-aware closeout for surrogate candidate screening.

This module preserves the existing simulation implementation and its raw outputs,
then creates a safer final eligibility and ranking layer. It never evaluates
arbitrary expressions or treats model predictions as engineering approval.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from analyzers.simulation import add_or_clean_scenario_id, run_simulation_analysis
from config import OutputPaths
from io_utils import resolve_project_path, save_dataframe, save_json


CONSTRAINT_SCHEMA_VERSION = "1.0"
SUPPORTED_CONSTRAINT_KINDS = {"range", "allowed_values", "conditional_range"}
SUPPORTED_OPERATORS = {"<", "<=", "==", "!=", ">=", ">"}


def _require_mapping(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be a JSON object")
    return value


def _require_feature(record: dict[str, Any], field: str = "feature") -> str:
    feature = record.get(field)
    if not isinstance(feature, str) or not feature.strip():
        raise ValueError(f"constraint {field} must be a non-empty string")
    return feature.strip()


def validate_constraint_config(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate the allowlisted candidate-constraint schema."""
    if payload.get("schema_version") != CONSTRAINT_SCHEMA_VERSION:
        raise ValueError(
            "constraint config schema_version must be "
            f"'{CONSTRAINT_SCHEMA_VERSION}'"
        )
    constraints = payload.get("constraints")
    if not isinstance(constraints, list):
        raise ValueError("constraint config constraints must be a list")

    seen_ids: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for index, raw in enumerate(constraints, start=1):
        record = _require_mapping(raw, f"constraints[{index}]")
        constraint_id = record.get("constraint_id")
        if not isinstance(constraint_id, str) or not constraint_id.strip():
            raise ValueError(f"constraints[{index}].constraint_id is required")
        constraint_id = constraint_id.strip()
        if constraint_id in seen_ids:
            raise ValueError(f"duplicate constraint_id: {constraint_id}")
        seen_ids.add(constraint_id)

        kind = record.get("kind")
        if kind not in SUPPORTED_CONSTRAINT_KINDS:
            raise ValueError(
                f"unsupported constraint kind for {constraint_id}: {kind}; "
                f"supported kinds are {sorted(SUPPORTED_CONSTRAINT_KINDS)}"
            )

        normalized_record = dict(record)
        normalized_record["constraint_id"] = constraint_id
        normalized_record["kind"] = kind

        if kind == "range":
            _require_feature(record)
            if "minimum" not in record and "maximum" not in record:
                raise ValueError(
                    f"range constraint {constraint_id} needs minimum or maximum"
                )
        elif kind == "allowed_values":
            _require_feature(record)
            values = record.get("values")
            if not isinstance(values, list) or not values:
                raise ValueError(
                    f"allowed_values constraint {constraint_id} needs values"
                )
        elif kind == "conditional_range":
            condition = _require_mapping(record.get("if"), f"{constraint_id}.if")
            consequence = _require_mapping(
                record.get("then"), f"{constraint_id}.then"
            )
            _require_feature(condition)
            _require_feature(consequence)
            operator = condition.get("operator")
            if operator not in SUPPORTED_OPERATORS:
                raise ValueError(
                    f"unsupported operator for {constraint_id}: {operator}"
                )
            if "value" not in condition:
                raise ValueError(f"{constraint_id}.if.value is required")
            if "minimum" not in consequence and "maximum" not in consequence:
                raise ValueError(
                    f"conditional range {constraint_id} needs then.minimum or then.maximum"
                )

        normalized.append(normalized_record)

    return {
        "schema_version": CONSTRAINT_SCHEMA_VERSION,
        "constraints": normalized,
        "source_note": payload.get("source_note"),
    }


def load_constraint_config(path_value: str | Path) -> tuple[Path, dict[str, Any]]:
    """Load a repository-relative or absolute JSON constraint config."""
    path = resolve_project_path(path_value)
    if not path.is_file():
        raise FileNotFoundError(f"Constraint config was not found: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Constraint config is not valid JSON: {path}") from exc
    return path, validate_constraint_config(_require_mapping(payload, "config"))


def _compare(left: object, operator: str, right: object) -> bool:
    if pd.isna(left):
        return False
    if operator == "<":
        return bool(left < right)
    if operator == "<=":
        return bool(left <= right)
    if operator == "==":
        return bool(left == right)
    if operator == "!=":
        return bool(left != right)
    if operator == ">=":
        return bool(left >= right)
    if operator == ">":
        return bool(left > right)
    raise ValueError(f"unsupported operator: {operator}")


def _range_passes(value: object, minimum: object, maximum: object) -> bool:
    if pd.isna(value):
        return False
    if minimum is not None and value < minimum:
        return False
    if maximum is not None and value > maximum:
        return False
    return True


def _evaluate_constraint(
    row: pd.Series, constraint: dict[str, Any]
) -> tuple[bool, str]:
    constraint_id = constraint["constraint_id"]
    kind = constraint["kind"]

    if kind == "range":
        feature = _require_feature(constraint)
        if feature not in row.index:
            return False, f"required feature '{feature}' is absent"
        minimum = constraint.get("minimum")
        maximum = constraint.get("maximum")
        passed = _range_passes(row[feature], minimum, maximum)
        return passed, (
            f"{feature}={row[feature]!r} within [{minimum!r}, {maximum!r}]"
            if passed
            else f"{feature}={row[feature]!r} violates [{minimum!r}, {maximum!r}]"
        )

    if kind == "allowed_values":
        feature = _require_feature(constraint)
        if feature not in row.index:
            return False, f"required feature '{feature}' is absent"
        values = constraint["values"]
        passed = row[feature] in values
        return passed, (
            f"{feature}={row[feature]!r} is allowed"
            if passed
            else f"{feature}={row[feature]!r} is not in {values!r}"
        )

    if kind == "conditional_range":
        condition = _require_mapping(constraint["if"], f"{constraint_id}.if")
        consequence = _require_mapping(
            constraint["then"], f"{constraint_id}.then"
        )
        condition_feature = _require_feature(condition)
        consequence_feature = _require_feature(consequence)
        missing = [
            feature
            for feature in (condition_feature, consequence_feature)
            if feature not in row.index
        ]
        if missing:
            return False, f"required feature(s) absent: {missing}"
        condition_met = _compare(
            row[condition_feature], condition["operator"], condition["value"]
        )
        if not condition_met:
            return True, "condition not active for this candidate"
        minimum = consequence.get("minimum")
        maximum = consequence.get("maximum")
        passed = _range_passes(row[consequence_feature], minimum, maximum)
        return passed, (
            f"active condition satisfied; {consequence_feature} is within range"
            if passed
            else (
                f"active condition requires {consequence_feature} within "
                f"[{minimum!r}, {maximum!r}]"
            )
        )

    raise ValueError(f"unsupported constraint kind: {kind}")


def evaluate_candidate_constraints(
    candidate_df: pd.DataFrame,
    config: dict[str, Any],
) -> pd.DataFrame:
    """Evaluate every candidate against every declared safe constraint."""
    validated = validate_constraint_config(config)
    prepared = add_or_clean_scenario_id(candidate_df)
    rows: list[dict[str, Any]] = []
    for _, candidate in prepared.iterrows():
        candidate_id = str(candidate["candidate_id"])
        for constraint in validated["constraints"]:
            passed, message = _evaluate_constraint(candidate, constraint)
            rows.append(
                {
                    "candidate_id": candidate_id,
                    "constraint_id": constraint["constraint_id"],
                    "constraint_kind": constraint["kind"],
                    "passed": bool(passed),
                    "message": message,
                }
            )
    return pd.DataFrame(
        rows,
        columns=[
            "candidate_id",
            "constraint_id",
            "constraint_kind",
            "passed",
            "message",
        ],
    )


def _build_final_ranking(
    predictions: pd.DataFrame,
    *,
    goal: str,
) -> pd.DataFrame:
    ranking = predictions.copy()
    for column in ("rank", "goal", "ranking_status", "ranking_note"):
        if column in ranking.columns:
            ranking = ranking.drop(columns=column)

    eligible_mask = (
        ranking["validation_status"].eq("valid")
        & ranking["predicted_target"].notna()
        & ranking["eligibility_status"].eq("eligible")
    )
    eligible = ranking.loc[eligible_mask].sort_values(
        ["predicted_target", "candidate_id"],
        ascending=[goal == "minimize", True],
        kind="mergesort",
    )
    noneligible = ranking.loc[~eligible_mask]
    ordered = pd.concat([eligible, noneligible], ignore_index=True)
    ordered.insert(0, "rank", pd.NA)
    ordered.insert(4, "goal", goal)
    ordered.insert(5, "ranking_status", "not_ranked")
    ordered.insert(6, "ranking_note", ordered["eligibility_status"])

    if len(eligible):
        ordered.loc[: len(eligible) - 1, "rank"] = range(1, len(eligible) + 1)
        ordered.loc[: len(eligible) - 1, "ranking_status"] = "ranked"
        ordered.loc[: len(eligible) - 1, "ranking_note"] = "eligible_and_ranked"
    return ordered


def _apply_eligibility_closeout(
    candidate_predictions: pd.DataFrame,
    constraint_audit: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    predictions = candidate_predictions.copy()
    predictions["constraint_violation_count"] = 0
    predictions["constraint_eligible"] = True

    if not constraint_audit.empty:
        failed = constraint_audit.loc[~constraint_audit["passed"].astype(bool)]
        violation_counts = failed.groupby("candidate_id").size()
        predictions["constraint_violation_count"] = (
            predictions["candidate_id"].map(violation_counts).fillna(0).astype(int)
        )
        predictions["constraint_eligible"] = (
            predictions["constraint_violation_count"] == 0
        )

    predictions["eligibility_status"] = "eligible"
    existing_invalid = ~predictions["validation_status"].eq("valid")
    predictions.loc[existing_invalid, "eligibility_status"] = "invalid_input"

    domain_mask = (
        predictions["validation_status"].eq("valid")
        & predictions["has_domain_warning"].astype(bool)
    )
    predictions.loc[
        domain_mask, "eligibility_status"
    ] = "not_eligible_outside_training_domain"

    constraint_mask = ~predictions["constraint_eligible"].astype(bool)
    predictions.loc[
        constraint_mask, "eligibility_status"
    ] = "excluded_constraint_violation"
    predictions.loc[
        constraint_mask, "validation_status"
    ] = "excluded_constraint_violation"
    predictions.loc[constraint_mask, "predicted_target"] = np.nan
    predictions.loc[constraint_mask, "validation_message"] = predictions.loc[
        constraint_mask, "constraint_violation_count"
    ].map(lambda count: f"Excluded by {count} declared candidate constraint(s).")

    summary = (
        predictions.groupby("eligibility_status", dropna=False)
        .size()
        .rename("candidate_count")
        .reset_index()
        .sort_values("eligibility_status")
        .reset_index(drop=True)
    )
    return predictions, summary


def _append_closeout_report(
    report_path: Path,
    *,
    constraint_config_path: Path | None,
    constraint_count: int,
    eligibility_summary: pd.DataFrame,
) -> None:
    lines = [
        "",
        "## Candidate Eligibility Closeout",
        "",
        "The surrogate predictions remain screening outputs, not engineering approval.",
        "Candidates outside any observed training feature range are not included in",
        "the final ranking. Declared constraints are evaluated through fixed,",
        "allowlisted operators; arbitrary expressions are not executed.",
        "",
        f"- Constraint config: `{constraint_config_path}`"
        if constraint_config_path
        else "- Constraint config: none supplied; training-domain eligibility still enforced.",
        f"- Declared constraints: {constraint_count}",
        "",
        "| eligibility_status | candidate_count |",
        "| --- | ---: |",
    ]
    for _, row in eligibility_summary.iterrows():
        lines.append(f"| {row['eligibility_status']} | {int(row['candidate_count'])} |")
    lines.extend(
        [
            "",
            "The original unconstrained prediction and ranking files are retained",
            "with `_unconstrained` filenames for provenance and comparison.",
            "",
        ]
    )
    with report_path.open("a", encoding="utf-8") as report_file:
        report_file.write("\n".join(lines))


def run_constraint_aware_simulation_analysis(
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
    constraint_config: str | None = None,
) -> dict[str, Path]:
    """Run the existing surrogate workflow and apply a safe final eligibility gate."""
    output_files = run_simulation_analysis(
        df=df,
        input_path=input_path,
        target=target,
        output_paths=output_paths,
        features=features,
        scenario_input=scenario_input,
        goal=goal,
        design_method=design_method,
        design_samples=design_samples,
        grid_levels=grid_levels,
        group_column=group_column,
    )

    predictions_path = output_paths.processed / "candidate_predictions.csv"
    ranking_path = output_paths.processed / "candidate_ranking.csv"
    candidates_path = output_paths.processed / "candidate_conditions.csv"
    if not predictions_path.is_file() or not candidates_path.is_file():
        raise RuntimeError("Simulation candidate outputs were not generated")

    candidate_predictions = pd.read_csv(predictions_path)
    candidates = pd.read_csv(candidates_path)
    unconstrained_predictions_path = save_dataframe(
        candidate_predictions,
        output_paths.processed / "candidate_predictions_unconstrained.csv",
    )
    unconstrained_ranking_path = output_paths.processed / "candidate_ranking_unconstrained.csv"
    if ranking_path.is_file():
        save_dataframe(pd.read_csv(ranking_path), unconstrained_ranking_path)
    else:
        save_dataframe(pd.DataFrame(), unconstrained_ranking_path)

    constraint_config_path: Path | None = None
    config: dict[str, Any] = {
        "schema_version": CONSTRAINT_SCHEMA_VERSION,
        "constraints": [],
        "source_note": None,
    }
    if constraint_config:
        constraint_config_path, config = load_constraint_config(constraint_config)

    constraint_audit = evaluate_candidate_constraints(candidates, config)
    constraint_audit_path = save_dataframe(
        constraint_audit,
        output_paths.processed / "candidate_constraint_audit.csv",
    )
    constraint_snapshot_path = save_json(
        {
            **config,
            "source_path": str(constraint_config_path) if constraint_config_path else None,
        },
        output_paths.processed / "candidate_constraint_config_snapshot.json",
    )

    final_predictions, eligibility_summary = _apply_eligibility_closeout(
        candidate_predictions,
        constraint_audit,
    )
    final_predictions_path = save_dataframe(final_predictions, predictions_path)
    final_ranking = _build_final_ranking(final_predictions, goal=goal)
    final_ranking_path = save_dataframe(final_ranking, ranking_path)
    eligibility_summary_path = save_dataframe(
        eligibility_summary,
        output_paths.processed / "candidate_eligibility_summary.csv",
    )

    report_path = output_files["report"]
    _append_closeout_report(
        report_path,
        constraint_config_path=constraint_config_path,
        constraint_count=len(config["constraints"]),
        eligibility_summary=eligibility_summary,
    )

    return {
        **output_files,
        "candidate_predictions": final_predictions_path,
        "candidate_ranking": final_ranking_path,
        "candidate_constraint_audit": constraint_audit_path,
        "candidate_constraint_config_snapshot": constraint_snapshot_path,
        "candidate_eligibility_summary": eligibility_summary_path,
        "candidate_predictions_unconstrained": unconstrained_predictions_path,
        "candidate_ranking_unconstrained": unconstrained_ranking_path,
    }
