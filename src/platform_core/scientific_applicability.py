"""Applicability and small-input validation for scientific constraints."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .artifacts import validate_relative_path
from .scientific_constraint_registry import ScientificConstraintRegistry, build_default_scientific_constraint_registry
from .scientific_constraints import ScientificConstraint, ScientificFinding
from .scientific_evaluators import ScientificEvaluatorRegistry, build_default_evaluator_registry, evaluate_constraint
from .units import UnitRegistry, build_default_unit_registry


SUPPORTED_SCIENTIFIC_CONFIG_SCHEMA_VERSION = "2.1"
FORBIDDEN_CONFIG_FIELDS = {
    "input_path",
    "csv_path",
    "raw_path",
    "dataset_path",
    "model_path",
    "script_path",
    "callable",
    "callable_name",
    "module_path",
    "equation",
    "python_expression",
}


@dataclass(frozen=True)
class ApplicabilityResult:
    constraint_id: str
    status: str
    reasons: tuple[str, ...]
    missing_variables: tuple[str, ...] = ()
    missing_units: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "constraint_id": self.constraint_id,
            "status": self.status,
            "reasons": list(self.reasons),
            "missing_variables": list(self.missing_variables),
            "missing_units": list(self.missing_units),
        }


@dataclass(frozen=True)
class ScientificValidationResult:
    valid: bool
    status: str
    applicability: tuple[ApplicabilityResult, ...]
    findings: tuple[ScientificFinding, ...]
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "valid": self.valid,
            "status": self.status,
            "applicability": [item.to_dict() for item in self.applicability],
            "findings": [finding.to_dict() for finding in self.findings],
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


def load_scientific_config(config_path: str | Path) -> dict[str, Any]:
    path = Path(config_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("scientific config must be a JSON object")
    return payload


def _iter_paths(value: Any):
    if isinstance(value, dict):
        for key, item in value.items():
            if key in FORBIDDEN_CONFIG_FIELDS:
                yield key, item
            yield from _iter_paths(item)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_paths(item)


def validate_scientific_config_safety(config: dict[str, Any]) -> tuple[str, ...]:
    errors: list[str] = []
    if config.get("schema_version") != SUPPORTED_SCIENTIFIC_CONFIG_SCHEMA_VERSION:
        errors.append(
            f"unsupported schema_version: {config.get('schema_version')!r}; expected {SUPPORTED_SCIENTIFIC_CONFIG_SCHEMA_VERSION}"
        )
    credential_policy = config.get("credential_policy", {})
    if isinstance(credential_policy, dict) and credential_policy.get("store_credentials") is True:
        errors.append("credential_policy.store_credentials must not be true")
    for key, value in _iter_paths(config):
        errors.append(f"{key} is not allowed in scientific metadata configs")
        if isinstance(value, str):
            try:
                validate_relative_path(value)
            except ValueError as exc:
                errors.append(str(exc))
    text = json.dumps(config, sort_keys=True)
    lowered = text.lower()
    for marker in ("password", "secret", "token", "api_key"):
        if marker in lowered:
            errors.append("scientific config contains credential-like text")
    for marker in ("eval(", "exec(", "__import__", "lambda "):
        if marker in text:
            errors.append("scientific config contains executable-looking text")
    if ":/" in text or ":\\" in text or "\\users\\" in lowered or "/users/" in lowered:
        errors.append("scientific config contains an absolute local path")
    return tuple(errors)


def _variables(config: dict[str, Any]) -> dict[str, Any]:
    variables = config.get("variables", {})
    if not isinstance(variables, dict):
        return {}
    return variables


def _unit_map(config: dict[str, Any]) -> dict[str, str]:
    units = config.get("units", {})
    result: dict[str, str] = {}
    if isinstance(units, dict):
        result.update({str(key): str(value) for key, value in units.items() if isinstance(value, str)})
    for name, payload in _variables(config).items():
        if isinstance(payload, dict) and isinstance(payload.get("unit"), str):
            result[str(name)] = str(payload["unit"])
    return result


def _metadata(config: dict[str, Any]) -> dict[str, Any]:
    metadata = config.get("metadata", {})
    return metadata if isinstance(metadata, dict) else {}


def _requested_constraints(config: dict[str, Any], registry: ScientificConstraintRegistry) -> list[ScientificConstraint]:
    raw = config.get("constraint_ids", [])
    if not isinstance(raw, list) or not raw:
        raise ValueError("constraint_ids must be a non-empty list")
    constraints: list[ScientificConstraint] = []
    for item in raw:
        if not isinstance(item, str):
            raise ValueError("constraint_ids entries must be strings")
        constraints.append(registry.get(item))
    return constraints


def check_constraint_applicability(
    constraint: ScientificConstraint,
    values: dict[str, Any],
    units: dict[str, str],
    metadata: dict[str, Any],
    evaluator_registry: ScientificEvaluatorRegistry,
) -> ApplicabilityResult:
    missing_variables = tuple(variable.name for variable in constraint.required_variables if variable.required and variable.name not in values)
    if missing_variables:
        return ApplicabilityResult(
            constraint.constraint_id,
            "unavailable_missing_variable",
            ("required variable metadata is missing",),
            missing_variables=missing_variables,
        )
    missing_units = tuple(
        variable.name
        for variable in constraint.required_variables
        if variable.name in constraint.expected_units and variable.name not in units
    )
    if missing_units:
        return ApplicabilityResult(
            constraint.constraint_id,
            "unavailable_missing_unit",
            ("required unit metadata is missing",),
            missing_units=missing_units,
        )
    semantic_availability = metadata.get("semantic_availability", {})
    if isinstance(semantic_availability, dict):
        unknown = [name for name, available in semantic_availability.items() if available == "unknown" or available is False]
        if unknown and any(variable.name in unknown for variable in constraint.required_variables):
            return ApplicabilityResult(
                constraint.constraint_id,
                "unavailable_unknown_semantics",
                ("variable semantic meaning is unavailable",),
            )
    invalid_assumptions = metadata.get("invalid_assumptions", [])
    if isinstance(invalid_assumptions, list) and constraint.constraint_id in invalid_assumptions:
        return ApplicabilityResult(constraint.constraint_id, "invalid_assumption", ("declared invalid assumption",))
    if constraint.evaluator_id is not None:
        try:
            evaluator_registry.get(constraint.evaluator_id)
        except KeyError:
            return ApplicabilityResult(constraint.constraint_id, "unsupported_evaluator", ("evaluator is not registered",))
    if constraint.status == "metadata_only" or constraint.evaluation_role == "metadata_only":
        return ApplicabilityResult(constraint.constraint_id, "conditionally_applicable", ("metadata-only constraint",))
    return ApplicabilityResult(constraint.constraint_id, "applicable", ("all required metadata is present",))


def check_scientific_applicability(
    config: dict[str, Any],
    *,
    constraint_registry: ScientificConstraintRegistry | None = None,
    evaluator_registry: ScientificEvaluatorRegistry | None = None,
) -> ScientificValidationResult:
    constraint_registry = constraint_registry or build_default_scientific_constraint_registry()
    evaluator_registry = evaluator_registry or build_default_evaluator_registry()
    errors = list(validate_scientific_config_safety(config))
    if errors:
        return ScientificValidationResult(False, "invalid_config", (), (), tuple(errors), ())
    constraints = _requested_constraints(config, constraint_registry)
    values = _variables(config)
    units = _unit_map(config)
    metadata = _metadata(config)
    applicability = tuple(
        check_constraint_applicability(constraint, values, units, metadata, evaluator_registry)
        for constraint in constraints
    )
    valid = all(result.status in {"applicable", "conditionally_applicable"} for result in applicability)
    status = "applicable" if valid else "not_applicable"
    return ScientificValidationResult(valid, status, applicability, (), (), ())


def validate_scientific_input(
    config: dict[str, Any],
    *,
    constraint_registry: ScientificConstraintRegistry | None = None,
    evaluator_registry: ScientificEvaluatorRegistry | None = None,
    unit_registry: UnitRegistry | None = None,
) -> ScientificValidationResult:
    constraint_registry = constraint_registry or build_default_scientific_constraint_registry()
    evaluator_registry = evaluator_registry or build_default_evaluator_registry()
    unit_registry = unit_registry or build_default_unit_registry()
    applicability_result = check_scientific_applicability(
        config,
        constraint_registry=constraint_registry,
        evaluator_registry=evaluator_registry,
    )
    if not applicability_result.valid:
        return applicability_result
    values = _variables(config)
    units = _unit_map(config)
    metadata = _metadata(config)
    findings: list[ScientificFinding] = []
    for constraint in _requested_constraints(config, constraint_registry):
        findings.extend(
            evaluate_constraint(
                constraint,
                values,
                units=units,
                metadata=metadata,
                evaluator_registry=evaluator_registry,
                unit_registry=unit_registry,
            )
        )
    blocking_statuses = {"inconsistent", "outside_validity_range", "assumption_violation"}
    valid = not any(finding.status in blocking_statuses and finding.severity in {"error", "blocker"} for finding in findings)
    if any(finding.status in blocking_statuses for finding in findings):
        status = "scientific_warnings"
    else:
        status = "scientifically_consistent"
    return ScientificValidationResult(valid, status, applicability_result.applicability, tuple(findings), (), ())
