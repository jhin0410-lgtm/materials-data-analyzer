"""Materials Project local table schema and quality helpers."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

import pandas as pd


SCHEMA_CONTRACT_REQUIRED_FIELDS = [
    "schema_version",
    "dataset_name",
    "provenance_status",
    "identifier_column",
    "required_columns",
    "optional_columns",
    "column_mappings",
    "data_types",
    "units",
    "nullable_policy",
    "uniqueness_policy",
    "quality_rules",
    "notes",
]
COLUMN_MAPPING_REQUIRED_FIELDS = [
    "source_column",
    "canonical_column",
    "semantic_role",
    "expected_dtype",
    "unit",
    "required",
    "nullable",
    "identifier",
    "target_candidate",
    "feature_candidate",
    "leakage_risk",
    "interpretation_note",
]
ALLOWED_PROVENANCE_STATUS = {"exact", "reconstructed", "incomplete"}
ALLOWED_SEMANTIC_ROLES = {
    "identifier",
    "composition",
    "structure",
    "thermodynamic_property",
    "electronic_property",
    "metadata",
    "ambiguous",
}
ALLOWED_DTYPES = {"string", "float", "integer", "numeric"}
ALLOWED_UNITS = {"unknown", "eV", "eV/atom", "g/cm3", "A^3"}
CREDENTIAL_TOKENS = {
    "api_key",
    "apikey",
    "token",
    "secret",
    "credential",
    "password",
}
QUALITY_COLUMNS = ["quality_status", "quality_issue_count", "quality_issues"]


def load_schema_contract(path: str | Path) -> dict[str, Any]:
    """Load and validate a Materials Project schema contract."""
    with Path(path).open(encoding="utf-8") as handle:
        contract = json.load(handle)
    if not isinstance(contract, dict):
        raise ValueError("Materials Project schema contract must be a JSON object.")
    validate_schema_contract(contract)
    return contract


def validate_schema_contract(contract: dict[str, Any]) -> None:
    """Validate a credential-free Materials Project schema contract."""
    missing_fields = [
        field for field in SCHEMA_CONTRACT_REQUIRED_FIELDS if field not in contract
    ]
    if missing_fields:
        raise ValueError(
            "Materials Project schema contract is missing required field(s): "
            + ", ".join(missing_fields)
        )
    if _contains_credential_like_key(contract):
        raise ValueError("Materials Project schema contract must not contain credential-like keys.")
    if _contains_absolute_path(contract):
        raise ValueError("Materials Project schema contract must not contain absolute paths.")

    if contract["provenance_status"] not in ALLOWED_PROVENANCE_STATUS:
        raise ValueError(
            "provenance_status must be one of: "
            + ", ".join(sorted(ALLOWED_PROVENANCE_STATUS))
        )

    mappings = contract["column_mappings"]
    if not isinstance(mappings, list) or not mappings:
        raise ValueError("column_mappings must be a non-empty list.")

    source_columns: list[str] = []
    canonical_columns: list[str] = []
    identifier_columns: list[str] = []
    for mapping in mappings:
        if not isinstance(mapping, dict):
            raise ValueError("Each column mapping must be a JSON object.")
        missing_mapping_fields = [
            field for field in COLUMN_MAPPING_REQUIRED_FIELDS if field not in mapping
        ]
        if missing_mapping_fields:
            raise ValueError(
                "Column mapping is missing required field(s): "
                + ", ".join(missing_mapping_fields)
            )
        source_column = _require_nonempty_string(mapping["source_column"], "source_column")
        canonical_column = _require_nonempty_string(
            mapping["canonical_column"], "canonical_column"
        )
        source_columns.append(source_column)
        canonical_columns.append(canonical_column)
        if mapping["semantic_role"] not in ALLOWED_SEMANTIC_ROLES:
            raise ValueError(f"Unsupported semantic_role: {mapping['semantic_role']}")
        if mapping["expected_dtype"] not in ALLOWED_DTYPES:
            raise ValueError(f"Unsupported expected_dtype: {mapping['expected_dtype']}")
        if mapping["unit"] not in ALLOWED_UNITS:
            raise ValueError(f"Unsupported unit: {mapping['unit']}")
        if mapping["identifier"]:
            identifier_columns.append(canonical_column)

    duplicate_canonical = sorted(_duplicates(canonical_columns))
    if duplicate_canonical:
        raise ValueError(
            "Schema contract contains duplicate canonical column(s): "
            + ", ".join(duplicate_canonical)
        )
    duplicate_source = sorted(_duplicates(source_columns))
    if duplicate_source:
        raise ValueError(
            "Schema contract contains duplicate source column(s): "
            + ", ".join(duplicate_source)
        )
    identifier_column = contract["identifier_column"]
    if identifier_column not in canonical_columns:
        raise ValueError("identifier_column must be one of the canonical columns.")
    if identifier_columns != [identifier_column]:
        raise ValueError("Exactly one column mapping must identify the identifier column.")

    required_columns = contract["required_columns"]
    if not isinstance(required_columns, list) or not all(
        isinstance(column, str) for column in required_columns
    ):
        raise ValueError("required_columns must be a list of strings.")
    missing_required_mappings = [
        column for column in required_columns if column not in source_columns
    ]
    if missing_required_mappings:
        raise ValueError(
            "required_columns contain unmapped source column(s): "
            + ", ".join(missing_required_mappings)
        )


def validate_local_table_schema(df: pd.DataFrame, contract: dict[str, Any]) -> None:
    """Validate that a local Materials Project table satisfies the contract shape."""
    validate_schema_contract(contract)
    required_columns = list(contract["required_columns"])
    missing_columns = [column for column in required_columns if column not in df.columns]
    if missing_columns:
        raise ValueError(
            "Materials Project local table is missing required column(s): "
            + ", ".join(missing_columns)
        )
    identifier_source = _identifier_source_column(contract)
    if identifier_source not in df.columns:
        raise ValueError("Identifier source column is missing from the local table.")


def normalize_materials_project_dataframe(
    df: pd.DataFrame,
    contract: dict[str, Any],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Conservatively normalize a local Materials Project table and audit rows."""
    validate_local_table_schema(df, contract)

    normalized = pd.DataFrame(index=df.index)
    conversion_failures_by_column: dict[str, int] = {}
    conversion_failure_masks_by_column: dict[str, pd.Series] = {}
    nonfinite_by_column: dict[str, int] = {}
    nonfinite_masks_by_column: dict[str, pd.Series] = {}
    missing_by_column: dict[str, int] = {}

    for mapping in contract["column_mappings"]:
        source_column = mapping["source_column"]
        canonical_column = mapping["canonical_column"]
        source = df[source_column]
        if mapping["expected_dtype"] == "string":
            normalized[canonical_column] = source.map(_clean_string_cell)
        else:
            numeric = pd.to_numeric(source, errors="coerce")
            conversion_failures = source.notna() & numeric.isna()
            conversion_failures_by_column[canonical_column] = int(conversion_failures.sum())
            conversion_failure_masks_by_column[canonical_column] = conversion_failures
            nonfinite_mask = numeric.notna() & ~numeric.map(_is_finite_number)
            nonfinite_by_column[canonical_column] = int(nonfinite_mask.sum())
            nonfinite_masks_by_column[canonical_column] = nonfinite_mask
            normalized[canonical_column] = numeric
        missing_by_column[canonical_column] = int(normalized[canonical_column].isna().sum())

    row_issues = _build_row_quality_issues(
        normalized,
        contract,
        conversion_failure_masks_by_column,
        nonfinite_masks_by_column,
    )
    normalized["quality_issues"] = [";".join(issues) for issues in row_issues]
    normalized["quality_issue_count"] = [len(issues) for issues in row_issues]
    normalized["quality_status"] = [
        _quality_status_from_issues(issues) for issues in row_issues
    ]
    normalized = normalized[
        [mapping["canonical_column"] for mapping in contract["column_mappings"]]
        + QUALITY_COLUMNS
    ]

    audit = {
        "row_count": int(len(normalized)),
        "source_column_count": int(len(df.columns)),
        "normalized_column_count": int(len(normalized.columns)),
        "conversion_failures_by_column": conversion_failures_by_column,
        "nonfinite_by_column": nonfinite_by_column,
        "missing_by_column": missing_by_column,
        "constant_columns": _constant_columns(normalized, contract),
    }
    return normalized, audit


def build_quality_summary(
    normalized_df: pd.DataFrame,
    contract: dict[str, Any],
    audit: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """Build a compact Materials Project row and schema quality summary."""
    validate_schema_contract(contract)
    audit = audit or {}
    total_rows = len(normalized_df)
    identifier_column = contract["identifier_column"]
    formula_column = _formula_column(contract)
    numeric_columns = _numeric_canonical_columns(contract)
    target_candidate_columns = _target_candidate_columns(contract)

    formula_elements = (
        normalized_df[formula_column].map(_formula_elements)
        if formula_column in normalized_df.columns
        else pd.Series([set() for _ in range(total_rows)])
    )
    required_elements = set(contract["quality_rules"].get("required_elements", []))
    contains_fe = formula_elements.map(lambda elements: "Fe" in elements)
    contains_si = formula_elements.map(lambda elements: "Si" in elements)
    contains_both = formula_elements.map(lambda elements: required_elements.issubset(elements))
    binary_rows = formula_elements.map(lambda elements: elements == required_elements)
    multinary_rows = contains_both & ~binary_rows

    rows: list[dict[str, Any]] = []
    _add_metric(rows, "total_rows", total_rows, total_rows, "info", "Total normalized rows.")
    for status in ["valid", "warning", "invalid"]:
        count = int(normalized_df["quality_status"].eq(status).sum())
        severity = "error" if status == "invalid" else "warning" if status == "warning" else "info"
        _add_metric(rows, f"{status}_rows", count, total_rows, severity, f"Rows with {status} quality_status.")

    duplicate_identifier_count = (
        int(normalized_df[identifier_column].duplicated().sum())
        if identifier_column in normalized_df.columns
        else total_rows
    )
    unique_identifiers = (
        int(normalized_df[identifier_column].nunique(dropna=True))
        if identifier_column in normalized_df.columns
        else 0
    )
    identifier_coverage = (
        int(normalized_df[identifier_column].notna().sum())
        if identifier_column in normalized_df.columns
        else 0
    )
    _add_metric(rows, "unique_identifiers", unique_identifiers, total_rows, "info", "Unique non-null material identifiers.")
    _add_metric(rows, "duplicate_identifiers", duplicate_identifier_count, total_rows, "warning", "Rows with duplicate material identifiers.")
    _add_metric(rows, "identifier_coverage", identifier_coverage, total_rows, "info", "Rows with a non-null identifier.")
    _add_metric(rows, "rows_containing_fe", int(contains_fe.sum()), total_rows, "info", "Rows whose formula string contains Fe.")
    _add_metric(rows, "rows_containing_si", int(contains_si.sum()), total_rows, "info", "Rows whose formula string contains Si.")
    _add_metric(rows, "rows_containing_both_fe_si", int(contains_both.sum()), total_rows, "info", "Rows whose formula string contains both Fe and Si.")
    _add_metric(rows, "binary_fe_si_rows", int(binary_rows.sum()), total_rows, "warning", "Rows whose parsed formula tokens are only Fe and Si.")
    _add_metric(rows, "multinary_fe_si_containing_rows", int(multinary_rows.sum()), total_rows, "info", "Rows containing Fe and Si plus at least one additional element.")

    for column in [mapping["canonical_column"] for mapping in contract["column_mappings"]]:
        missing_count = int(normalized_df[column].isna().sum())
        _add_metric(rows, f"missing_count:{column}", missing_count, total_rows, "warning", f"Missing values in {column}.")

    conversion_failures = audit.get("conversion_failures_by_column", {})
    for column in numeric_columns:
        count = int(conversion_failures.get(column, 0))
        _add_metric(rows, f"numeric_conversion_failure_count:{column}", count, total_rows, "warning", f"Non-numeric values coerced to missing in {column}.")

    nonfinite = audit.get("nonfinite_by_column", {})
    for column in numeric_columns:
        count = int(nonfinite.get(column, 0))
        _add_metric(rows, f"nonfinite_numeric_count:{column}", count, total_rows, "warning", f"Non-finite numeric values in {column}.")

    constant_columns = audit.get("constant_columns", _constant_columns(normalized_df, contract))
    _add_metric(rows, "constant_column_count", len(constant_columns), len(contract["column_mappings"]), "warning", "Number of constant canonical columns.")

    for column in target_candidate_columns:
        count = int(normalized_df[column].notna().sum())
        _add_metric(rows, f"target_candidate_coverage:{column}", count, total_rows, "info", f"Non-null coverage for target candidate {column}.")

    return pd.DataFrame(rows, columns=["metric", "count", "percentage", "severity", "description"])


def summarize_actual_schema(df: pd.DataFrame, contract: dict[str, Any]) -> pd.DataFrame:
    """Summarize the actual seven-column local pilot schema."""
    validate_local_table_schema(df, contract)
    rows: list[dict[str, Any]] = []
    for mapping in contract["column_mappings"]:
        column = mapping["source_column"]
        series = df[column]
        numeric = pd.to_numeric(series, errors="coerce") if mapping["expected_dtype"] != "string" else None
        rows.append(
            {
                "original_column_name": column,
                "canonical_column": mapping["canonical_column"],
                "inferred_dtype": str(series.dtype),
                "semantic_role": mapping["semantic_role"],
                "unit": mapping["unit"],
                "non_null_count": int(series.notna().sum()),
                "unique_count": int(series.nunique(dropna=True)),
                "numeric_min": numeric.min() if numeric is not None else pd.NA,
                "numeric_median": numeric.median() if numeric is not None else pd.NA,
                "numeric_max": numeric.max() if numeric is not None else pd.NA,
                "example_values": _example_values(series),
                "identifier": bool(mapping["identifier"]),
                "target_candidate": bool(mapping["target_candidate"]),
                "feature_candidate": bool(mapping["feature_candidate"]),
                "leakage_risk": mapping["leakage_risk"],
                "normalization_needed": _normalization_needed(mapping),
            }
        )
    return pd.DataFrame(rows)


def _build_row_quality_issues(
    normalized: pd.DataFrame,
    contract: dict[str, Any],
    conversion_failure_masks_by_column: dict[str, pd.Series],
    nonfinite_masks_by_column: dict[str, pd.Series],
) -> list[list[str]]:
    row_issues: list[list[str]] = [[] for _ in range(len(normalized))]
    identifier_column = contract["identifier_column"]
    formula_column = _formula_column(contract)
    required_elements = set(contract["quality_rules"].get("required_elements", []))
    mappings_by_canonical = {
        mapping["canonical_column"]: mapping for mapping in contract["column_mappings"]
    }

    if identifier_column in normalized.columns:
        missing_identifier = normalized[identifier_column].isna()
        duplicate_identifier = normalized[identifier_column].duplicated(keep=False) & normalized[identifier_column].notna()
        _append_issue(row_issues, missing_identifier, "missing_identifier")
        _append_issue(row_issues, duplicate_identifier, "duplicate_identifier")

    if formula_column in normalized.columns:
        missing_formula = normalized[formula_column].isna()
        _append_issue(row_issues, missing_formula, "missing_formula_or_composition")
        formula_elements = normalized[formula_column].map(_formula_elements)
        if "Fe" in required_elements:
            _append_issue(
                row_issues,
                normalized[formula_column].notna() & ~formula_elements.map(lambda elements: "Fe" in elements),
                "required_element_missing_fe",
            )
        if "Si" in required_elements:
            _append_issue(
                row_issues,
                normalized[formula_column].notna() & ~formula_elements.map(lambda elements: "Si" in elements),
                "required_element_missing_si",
            )
        _append_issue(
            row_issues,
            normalized[formula_column].notna() & formula_elements.map(lambda elements: elements == required_elements),
            "binary_scope_mismatch",
        )

    for column, mapping in mappings_by_canonical.items():
        if mapping["expected_dtype"] == "string":
            continue
        if mapping["required"]:
            _append_issue(
                row_issues,
                normalized[column].isna(),
                f"missing_numeric_property:{column}",
            )
        conversion_failure_mask = conversion_failure_masks_by_column.get(
            column,
            pd.Series(False, index=normalized.index),
        )
        if bool(conversion_failure_mask.any()):
            _append_issue(
                row_issues,
                conversion_failure_mask,
                f"nonnumeric_property_value:{column}",
            )
        nonfinite_mask = nonfinite_masks_by_column.get(
            column,
            pd.Series(False, index=normalized.index),
        )
        if bool(nonfinite_mask.any()):
            _append_issue(
                row_issues,
                nonfinite_mask,
                f"nonfinite_numeric_value:{column}",
            )
        if _has_suspicious_numeric_range(normalized[column], column):
            mask = _suspicious_numeric_range_mask(normalized[column], column)
            _append_issue(row_issues, mask, f"suspicious_numeric_range:{column}")
        if mapping["unit"] == "unknown":
            _append_issue(
                row_issues,
                normalized[column].notna(),
                f"unknown_unit:{column}",
            )

    for column in _constant_columns(normalized, contract):
        _append_issue(row_issues, normalized[column].notna(), f"constant_property:{column}")

    return row_issues


def _append_issue(row_issues: list[list[str]], mask: pd.Series, issue: str) -> None:
    for idx, flagged in enumerate(mask.fillna(False).tolist()):
        if flagged:
            row_issues[idx].append(issue)


def _quality_status_from_issues(issues: list[str]) -> str:
    if any(issue == "missing_identifier" for issue in issues):
        return "invalid"
    if issues:
        return "warning"
    return "valid"


def _clean_string_cell(value: Any) -> str | pd.NA:
    if pd.isna(value):
        return pd.NA
    text = str(value).strip()
    return text if text else pd.NA


def _formula_elements(formula: Any) -> set[str]:
    if pd.isna(formula):
        return set()
    return set(re.findall(r"[A-Z][a-z]?", str(formula)))


def _identifier_source_column(contract: dict[str, Any]) -> str:
    for mapping in contract["column_mappings"]:
        if mapping["canonical_column"] == contract["identifier_column"]:
            return mapping["source_column"]
    raise ValueError("Identifier column is not mapped.")


def _formula_column(contract: dict[str, Any]) -> str:
    for mapping in contract["column_mappings"]:
        if mapping["semantic_role"] == "composition":
            return mapping["canonical_column"]
    return "formula"


def _numeric_canonical_columns(contract: dict[str, Any]) -> list[str]:
    return [
        mapping["canonical_column"]
        for mapping in contract["column_mappings"]
        if mapping["expected_dtype"] != "string"
    ]


def _target_candidate_columns(contract: dict[str, Any]) -> list[str]:
    return [
        mapping["canonical_column"]
        for mapping in contract["column_mappings"]
        if mapping["target_candidate"]
    ]


def _constant_columns(df: pd.DataFrame, contract: dict[str, Any]) -> list[str]:
    columns: list[str] = []
    for column in _numeric_canonical_columns(contract):
        if column in df.columns and df[column].nunique(dropna=False) <= 1:
            columns.append(column)
    return columns


def _has_suspicious_numeric_range(series: pd.Series, column: str) -> bool:
    return bool(_suspicious_numeric_range_mask(series, column).any())


def _suspicious_numeric_range_mask(series: pd.Series, column: str) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    if column in {"band_gap_ev", "energy_above_hull_ev_atom"}:
        return numeric < 0
    if column in {"density_g_cm3", "volume_a3"}:
        return numeric <= 0
    return pd.Series(False, index=series.index)


def _normalization_needed(mapping: dict[str, Any]) -> str:
    if mapping["identifier"]:
        return "trim string only"
    if mapping["expected_dtype"] == "string":
        return "trim string; no composition featurization"
    return "numeric coercion with quality audit"


def _is_finite_number(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _example_values(series: pd.Series, limit: int = 3) -> str:
    values = series.dropna().astype(str).drop_duplicates().head(limit).tolist()
    return "; ".join(values)


def _add_metric(
    rows: list[dict[str, Any]],
    metric: str,
    count: int,
    denominator: int,
    severity: str,
    description: str,
) -> None:
    percentage = round(float(count / denominator * 100.0), 4) if denominator else 0.0
    rows.append(
        {
            "metric": metric,
            "count": int(count),
            "percentage": percentage,
            "severity": severity,
            "description": description,
        }
    )


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


def _duplicates(values: list[str]) -> set[str]:
    return {value for value in values if values.count(value) > 1}
