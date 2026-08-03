"""Versioned dataset semantic contract for decision-grade generic workflows."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pandas as pd

from preprocessing import clean_column_name

SCHEMA_VERSION = "1.0"
ALLOWED_ROLES = {
    "identifier",
    "group",
    "timestamp",
    "feature",
    "target",
    "method",
    "unit",
    "provenance",
    "outcome",
    "exposure",
    "censoring",
}
PROTECTED_ROLES = {
    "identifier",
    "group",
    "timestamp",
    "method",
    "unit",
    "provenance",
}


def load_dataset_contract(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"dataset contract not found: {source}")
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise TypeError("dataset contract must be a JSON object")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(
            f"unsupported dataset contract schema_version: {payload.get('schema_version')!r}"
        )
    columns = payload.get("columns")
    if not isinstance(columns, Mapping) or not columns:
        raise ValueError("dataset contract must define a non-empty columns object")
    normalized: dict[str, dict[str, Any]] = {}
    for raw_name, raw_spec in columns.items():
        name = clean_column_name(str(raw_name))
        if not name:
            raise ValueError("dataset contract contains a blank column name")
        if name in normalized:
            raise ValueError(f"dataset contract columns collide after normalization: {name}")
        if not isinstance(raw_spec, Mapping):
            raise TypeError(f"dataset contract column spec must be an object: {raw_name}")
        role = str(raw_spec.get("role", "")).strip()
        if role not in ALLOWED_ROLES:
            raise ValueError(
                f"dataset contract column {raw_name!r} has unsupported role {role!r}"
            )
        spec = dict(raw_spec)
        spec["role"] = role
        normalized[name] = spec
    result = dict(payload)
    result["columns"] = normalized
    return result


def protected_columns(contract: Mapping[str, Any] | None) -> set[str]:
    if contract is None:
        return set()
    return {
        name
        for name, spec in contract["columns"].items()
        if spec.get("role") in PROTECTED_ROLES
    }


def audit_dataset_contract(
    contract: Mapping[str, Any] | None,
    df: pd.DataFrame,
    *,
    mode: str,
    target_columns: list[str],
    decision_grade: bool,
) -> dict[str, Any]:
    if contract is None:
        if decision_grade:
            raise ValueError("--decision-grade requires --dataset-contract")
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "not_supplied",
            "decision_grade": False,
            "limitations": [
                "Units, semantic roles, measurement method, identity, and provenance were not contract-validated."
            ],
        }

    specs: Mapping[str, Mapping[str, Any]] = contract["columns"]
    missing_columns = sorted(set(specs) - set(df.columns))
    undeclared_columns = sorted(set(df.columns) - set(specs))
    issues: list[dict[str, str]] = []
    for column in missing_columns:
        issues.append({"code": "declared_column_missing", "column": column})

    numeric_roles = {"feature", "target", "outcome", "exposure"}
    for column, spec in specs.items():
        if column not in df.columns:
            continue
        role = str(spec["role"])
        if role in numeric_roles and not pd.api.types.is_numeric_dtype(df[column]):
            issues.append({"code": "numeric_role_not_numeric", "column": column})
        if role in {"feature", "target", "exposure"} and not str(
            spec.get("unit", "")
        ).strip():
            issues.append({"code": "physical_role_unit_missing", "column": column})

    for target in target_columns:
        normalized = clean_column_name(target)
        if normalized not in specs:
            issues.append({"code": "target_not_declared", "column": normalized})
        elif specs[normalized].get("role") not in {"target", "outcome"}:
            issues.append({"code": "target_role_mismatch", "column": normalized})

    roles = {str(spec.get("role")) for spec in specs.values()}
    if decision_grade and "identifier" not in roles:
        issues.append({"code": "identifier_role_missing", "column": ""})
    if decision_grade and mode == "simulation" and "group" not in roles:
        issues.append({
            "code": "group_role_missing_for_decision_grade_simulation",
            "column": "",
        })
    if decision_grade and mode == "spc" and "timestamp" not in roles:
        issues.append({
            "code": "timestamp_role_missing_for_decision_grade_spc",
            "column": "",
        })
    if decision_grade and mode == "reliability" and not (
        {"exposure", "censoring"} <= roles
    ):
        issues.append({"code": "exposure_or_censoring_role_missing", "column": ""})

    status = "valid" if not issues else "invalid"
    if decision_grade and issues:
        codes = ", ".join(sorted({item["code"] for item in issues}))
        raise ValueError(f"decision-grade dataset contract validation failed: {codes}")
    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "decision_grade": decision_grade,
        "mode": mode,
        "declared_column_count": len(specs),
        "undeclared_columns": undeclared_columns,
        "issues": issues,
        "scientific_boundary": (
            "A valid contract establishes declared semantics and units only; it does not establish comparability, calibration, causality, or predictive validity."
        ),
    }
