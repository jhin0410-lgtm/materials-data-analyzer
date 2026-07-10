"""Generic tabular property filtering and ranking helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


SCREENING_SPEC_REQUIRED_FIELDS = [
    "schema_version",
    "dataset_name",
    "screening_mode",
    "identifier_column",
    "display_columns",
    "filters",
    "objectives",
    "missing_value_policy",
    "tie_policy",
    "top_n",
    "provenance_status",
    "limitations",
    "notes",
]
ALLOWED_OBJECTIVE_MODES = {"minimize", "maximize", "target_value", "target_range"}
ALLOWED_FILTER_OPERATORS = {
    "equals",
    "not_equals",
    "in",
    "not_in",
    "min",
    "max",
    "between",
    "non_missing",
}
ALLOWED_MISSING_POLICIES = {"exclude_from_ranking", "score_as_missing"}
ALLOWED_TIE_POLICIES = {"min_rank", "dense_rank"}
ALLOWED_PROVENANCE_STATUS = {"exact", "reconstructed", "incomplete"}
CREDENTIAL_TOKENS = {
    "api_key",
    "apikey",
    "token",
    "secret",
    "credential",
    "password",
}


def load_screening_spec(path: str | Path) -> dict[str, Any]:
    """Load and validate a credential-free property screening specification."""
    with Path(path).open(encoding="utf-8") as handle:
        spec = json.load(handle)
    if not isinstance(spec, dict):
        raise ValueError("Property screening spec must be a JSON object.")
    validate_screening_spec(spec)
    return spec


def validate_screening_spec(spec: dict[str, Any]) -> None:
    """Validate screening specification structure without inspecting data."""
    missing_fields = [
        field for field in SCREENING_SPEC_REQUIRED_FIELDS if field not in spec
    ]
    if missing_fields:
        raise ValueError(
            "Property screening spec is missing required field(s): "
            + ", ".join(missing_fields)
        )
    if _contains_credential_like_key(spec):
        raise ValueError("Property screening spec must not contain credential-like keys.")
    if _contains_absolute_path(spec):
        raise ValueError("Property screening spec must not contain absolute paths.")

    _require_nonempty_string(spec["identifier_column"], "identifier_column")
    if (
        not isinstance(spec["display_columns"], list)
        or not all(isinstance(column, str) for column in spec["display_columns"])
    ):
        raise ValueError("display_columns must be a list of column names.")
    if spec["missing_value_policy"] not in ALLOWED_MISSING_POLICIES:
        raise ValueError(
            "missing_value_policy must be one of: "
            + ", ".join(sorted(ALLOWED_MISSING_POLICIES))
        )
    if spec["tie_policy"] not in ALLOWED_TIE_POLICIES:
        raise ValueError(
            "tie_policy must be one of: " + ", ".join(sorted(ALLOWED_TIE_POLICIES))
        )
    if spec["provenance_status"] not in ALLOWED_PROVENANCE_STATUS:
        raise ValueError(
            "provenance_status must be one of: "
            + ", ".join(sorted(ALLOWED_PROVENANCE_STATUS))
        )
    if not isinstance(spec["top_n"], int) or spec["top_n"] <= 0:
        raise ValueError("top_n must be a positive integer.")

    filters = spec["filters"]
    if not isinstance(filters, list):
        raise ValueError("filters must be a list.")
    for filter_spec in filters:
        _validate_filter_spec(filter_spec)

    objectives = spec["objectives"]
    if not isinstance(objectives, list) or not objectives:
        raise ValueError("objectives must be a non-empty list.")
    for objective in objectives:
        _validate_objective_spec(objective)


def validate_screening_inputs(df: pd.DataFrame, spec: dict[str, Any]) -> None:
    """Validate that a DataFrame has the columns required by a screening spec."""
    validate_screening_spec(spec)
    identifier_column = spec["identifier_column"]
    if identifier_column not in df.columns:
        raise ValueError(f"Identifier column not found: {identifier_column}")

    missing_display_columns = [
        column for column in spec["display_columns"] if column not in df.columns
    ]
    if missing_display_columns:
        raise ValueError(
            "Display column(s) not found: " + ", ".join(missing_display_columns)
        )

    prohibited_objectives = {
        identifier_column,
        *spec["display_columns"],
        "formula",
        "material_id",
    }
    for objective in spec["objectives"]:
        property_name = objective["property"]
        if property_name not in df.columns:
            raise ValueError(f"Objective property not found: {property_name}")
        if property_name in prohibited_objectives:
            raise ValueError(
                f"Objective property is not a numeric screening property: {property_name}"
            )
        if not pd.api.types.is_numeric_dtype(df[property_name]):
            raise ValueError(f"Objective property must be numeric: {property_name}")

    for filter_spec in spec["filters"]:
        column = filter_spec["column"]
        if column not in df.columns:
            raise ValueError(f"Filter column not found: {column}")


def apply_screening_filters(
    df: pd.DataFrame,
    spec: dict[str, Any],
) -> pd.DataFrame:
    """Add transparent pass/fail filter status columns without dropping rows."""
    validate_screening_inputs(df, spec)
    result = df.copy()
    pass_masks: list[pd.Series] = []
    filter_notes: list[list[str]] = [[] for _ in range(len(result))]

    for filter_spec in spec["filters"]:
        mask = _evaluate_filter(result, filter_spec)
        pass_masks.append(mask)
        failed_mask = ~mask.fillna(False)
        note = _filter_note(filter_spec)
        for idx, failed in enumerate(failed_mask.tolist()):
            if failed:
                filter_notes[idx].append(note)

    if pass_masks:
        combined = pass_masks[0].fillna(False)
        for mask in pass_masks[1:]:
            combined = combined & mask.fillna(False)
    else:
        combined = pd.Series(True, index=result.index)

    result["passes_filters"] = combined.astype(bool)
    result["filter_status"] = np.where(result["passes_filters"], "pass", "fail")
    result["filter_notes"] = [";".join(notes) for notes in filter_notes]
    return result


def rank_screening_candidates(
    df: pd.DataFrame,
    spec: dict[str, Any],
) -> pd.DataFrame:
    """Rank rows using observed numeric properties and a transparent spec."""
    filtered_df = apply_screening_filters(df, spec)
    result = filtered_df.copy()
    objectives = spec["objectives"]
    weight_sum = sum(float(objective["weight"]) for objective in objectives)
    score_columns: list[str] = []
    missing_objective_mask = pd.Series(False, index=result.index)

    for objective in objectives:
        property_name = objective["property"]
        score_column = f"{property_name}_objective_score"
        rank_column = f"{property_name}_objective_rank"
        normalized_weight_column = f"{property_name}_normalized_weight"
        raw_series = pd.to_numeric(result[property_name], errors="coerce")
        score = _calculate_objective_score(raw_series, objective)
        if spec["missing_value_policy"] == "score_as_missing":
            score = score.fillna(0.0)
        rank_basis = _calculate_rank_basis(raw_series, objective)
        rank = rank_basis.rank(
            ascending=True,
            method=_pandas_rank_method(spec["tie_policy"]),
            na_option="bottom",
        )
        rank = rank.where(raw_series.notna(), np.nan)

        result[score_column] = score
        result[rank_column] = rank
        result[normalized_weight_column] = float(objective["weight"]) / weight_sum
        score_columns.append(score_column)
        if spec["missing_value_policy"] == "exclude_from_ranking":
            missing_objective_mask = missing_objective_mask | raw_series.isna()

    composite = pd.Series(0.0, index=result.index)
    for objective in objectives:
        property_name = objective["property"]
        score_column = f"{property_name}_objective_score"
        weight = float(objective["weight"]) / weight_sum
        composite = composite + result[score_column] * weight
    composite = composite.where(~missing_objective_mask, np.nan)
    result["composite_score"] = composite

    eligible_mask = result["passes_filters"] & result["composite_score"].notna()
    result["overall_rank"] = np.nan
    result.loc[eligible_mask, "overall_rank"] = result.loc[
        eligible_mask,
        "composite_score",
    ].rank(
        ascending=False,
        method=_pandas_rank_method(spec["tie_policy"]),
    )

    result["screening_status"] = "ranked"
    result.loc[~result["passes_filters"], "screening_status"] = "filter_failed"
    result.loc[
        result["passes_filters"] & missing_objective_mask,
        "screening_status",
    ] = "missing_objective"
    result["screening_notes"] = result.apply(
        lambda row: _screening_note(row, objectives),
        axis=1,
    )

    sort_columns = ["overall_rank", "composite_score", spec["identifier_column"]]
    result = result.sort_values(
        sort_columns,
        ascending=[True, False, True],
        na_position="last",
    ).reset_index(drop=True)
    return result


def build_screening_summary(
    results_df: pd.DataFrame,
    spec: dict[str, Any],
) -> pd.DataFrame:
    """Build a compact top-N screening summary from full screening results."""
    validate_screening_spec(spec)
    top_n = spec["top_n"]
    identifier_column = spec["identifier_column"]
    display_columns = [
        column for column in spec["display_columns"] if column in results_df.columns
    ]
    objective_properties = [objective["property"] for objective in spec["objectives"]]
    objective_columns: list[str] = []
    for property_name in objective_properties:
        objective_columns.extend(
            [
                property_name,
                f"{property_name}_objective_rank",
                f"{property_name}_objective_score",
            ]
        )

    columns = [
        identifier_column,
        *display_columns,
        *objective_columns,
        "composite_score",
        "overall_rank",
        "screening_status",
        "screening_notes",
    ]
    columns = [column for column in columns if column in results_df.columns]
    ranked = results_df[results_df["screening_status"].eq("ranked")]
    summary = ranked.sort_values(
        ["overall_rank", "composite_score", identifier_column],
        ascending=[True, False, True],
        na_position="last",
    ).head(top_n)
    summary = summary[columns].copy()
    summary["provenance_status"] = spec["provenance_status"]
    summary["limitation_flag"] = "descriptive_screening_not_prediction"
    return summary.reset_index(drop=True)


def _validate_filter_spec(filter_spec: Any) -> None:
    if not isinstance(filter_spec, dict):
        raise ValueError("Each filter must be a JSON object.")
    _require_nonempty_string(filter_spec.get("column"), "filter column")
    operator = filter_spec.get("operator")
    if operator not in ALLOWED_FILTER_OPERATORS:
        raise ValueError(f"Unsupported filter operator: {operator}")
    if operator in {"equals", "not_equals", "min", "max"} and "value" not in filter_spec:
        raise ValueError(f"Filter operator {operator} requires value.")
    if operator in {"in", "not_in"} and not isinstance(filter_spec.get("values"), list):
        raise ValueError(f"Filter operator {operator} requires values list.")
    if operator == "between" and (
        "lower_bound" not in filter_spec or "upper_bound" not in filter_spec
    ):
        raise ValueError("Filter operator between requires lower_bound and upper_bound.")


def _validate_objective_spec(objective: Any) -> None:
    if not isinstance(objective, dict):
        raise ValueError("Each objective must be a JSON object.")
    _require_nonempty_string(objective.get("property"), "objective property")
    mode = objective.get("mode")
    if mode not in ALLOWED_OBJECTIVE_MODES:
        raise ValueError(f"Unsupported objective mode: {mode}")
    weight = objective.get("weight")
    if not isinstance(weight, (int, float)) or weight <= 0:
        raise ValueError("Objective weight must be a positive number.")
    if mode == "target_value" and "target" not in objective:
        raise ValueError("target_value objective requires target.")
    if mode == "target_range" and (
        "lower_bound" not in objective or "upper_bound" not in objective
    ):
        raise ValueError("target_range objective requires lower_bound and upper_bound.")
    if mode == "target_range" and objective["lower_bound"] > objective["upper_bound"]:
        raise ValueError("target_range lower_bound must be <= upper_bound.")


def _evaluate_filter(df: pd.DataFrame, filter_spec: dict[str, Any]) -> pd.Series:
    column = filter_spec["column"]
    operator = filter_spec["operator"]
    series = df[column]

    if operator == "equals":
        return series.eq(filter_spec["value"])
    if operator == "not_equals":
        return series.ne(filter_spec["value"])
    if operator == "in":
        return series.isin(filter_spec["values"])
    if operator == "not_in":
        return ~series.isin(filter_spec["values"])
    if operator == "min":
        return pd.to_numeric(series, errors="coerce") >= float(filter_spec["value"])
    if operator == "max":
        return pd.to_numeric(series, errors="coerce") <= float(filter_spec["value"])
    if operator == "between":
        numeric = pd.to_numeric(series, errors="coerce")
        return numeric.between(
            float(filter_spec["lower_bound"]),
            float(filter_spec["upper_bound"]),
            inclusive="both",
        )
    if operator == "non_missing":
        return series.notna()
    raise ValueError(f"Unsupported filter operator: {operator}")


def _calculate_objective_score(
    series: pd.Series,
    objective: dict[str, Any],
) -> pd.Series:
    mode = objective["mode"]
    if mode in {"minimize", "maximize"}:
        return _min_max_score(series, maximize=mode == "maximize")
    if mode == "target_value":
        target = float(objective["target"])
        distance = (series - target).abs()
        return _distance_score(distance)
    if mode == "target_range":
        lower = float(objective["lower_bound"])
        upper = float(objective["upper_bound"])
        distance = pd.Series(0.0, index=series.index)
        distance = distance.where(series >= lower, lower - series)
        distance = distance.where(series <= upper, series - upper)
        return _distance_score(distance.abs())
    raise ValueError(f"Unsupported objective mode: {mode}")


def _calculate_rank_basis(series: pd.Series, objective: dict[str, Any]) -> pd.Series:
    mode = objective["mode"]
    if mode == "minimize":
        return series
    if mode == "maximize":
        return -series
    if mode == "target_value":
        return (series - float(objective["target"])).abs()
    if mode == "target_range":
        lower = float(objective["lower_bound"])
        upper = float(objective["upper_bound"])
        distance = pd.Series(0.0, index=series.index)
        distance = distance.where(series >= lower, lower - series)
        distance = distance.where(series <= upper, series - upper)
        return distance.abs()
    raise ValueError(f"Unsupported objective mode: {mode}")


def _min_max_score(series: pd.Series, maximize: bool) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    min_value = numeric.min(skipna=True)
    max_value = numeric.max(skipna=True)
    if pd.isna(min_value) or pd.isna(max_value):
        return pd.Series(np.nan, index=series.index)
    value_range = max_value - min_value
    if np.isclose(value_range, 0):
        return numeric.where(numeric.isna(), 1.0)
    if maximize:
        return ((numeric - min_value) / value_range).clip(0, 1)
    return ((max_value - numeric) / value_range).clip(0, 1)


def _distance_score(distance: pd.Series) -> pd.Series:
    max_distance = distance.max(skipna=True)
    if pd.isna(max_distance):
        return pd.Series(np.nan, index=distance.index)
    if np.isclose(max_distance, 0):
        return distance.where(distance.isna(), 1.0)
    return (1.0 - (distance / max_distance)).clip(0, 1)


def _pandas_rank_method(tie_policy: str) -> str:
    return "dense" if tie_policy == "dense_rank" else "min"


def _filter_note(filter_spec: dict[str, Any]) -> str:
    column = filter_spec["column"]
    operator = filter_spec["operator"]
    if operator in {"in", "not_in"}:
        value = filter_spec["values"]
    elif operator == "between":
        value = f"{filter_spec['lower_bound']}..{filter_spec['upper_bound']}"
    elif operator == "non_missing":
        value = "non-missing"
    else:
        value = filter_spec["value"]
    return f"{column} {operator} {value}"


def _screening_note(row: pd.Series, objectives: list[dict[str, Any]]) -> str:
    if row["screening_status"] == "filter_failed":
        return "not ranked because one or more filters failed"
    if row["screening_status"] == "missing_objective":
        missing = [
            objective["property"]
            for objective in objectives
            if pd.isna(row.get(objective["property"]))
        ]
        return "not ranked because objective value is missing: " + ", ".join(missing)
    return "ranked using observed/computed property values only"


def _contains_absolute_path(value: Any) -> bool:
    if isinstance(value, str):
        stripped = value.strip()
        return bool(stripped.startswith("/") or (len(stripped) >= 3 and stripped[1:3] == ":\\"))
    if isinstance(value, dict):
        return any(_contains_absolute_path(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_absolute_path(item) for item in value)
    return False


def _contains_credential_like_key(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized_key = str(key).lower().replace("-", "_")
            if any(token in normalized_key for token in CREDENTIAL_TOKENS):
                return True
            if _contains_credential_like_key(item):
                return True
    if isinstance(value, list):
        return any(_contains_credential_like_key(item) for item in value)
    return False


def _require_nonempty_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be a non-empty string.")
    return value
