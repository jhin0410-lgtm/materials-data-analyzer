"""Bounded scientific execution layer for scalar/small-list consistency checks.

This module executes only code-registered scientific evaluators and small
domain-specific derivations. It does not parse equations, read raw datasets,
train models, call networks, or execute user-provided callables.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
import subprocess
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .artifacts import validate_relative_path
from .claim_diagnostics import evaluate_claim_id
from .diagnostics import ClaimEvaluation
from .domain_knowledge import (
    DomainKnowledgePack,
    DomainKnowledgeRegistry,
    build_default_domain_knowledge_registry,
)
from .evidence_graph import build_scientific_execution_evidence_graph
from .run_registry import (
    DEFAULT_REGISTRY_PATH,
    REGISTRY_SCHEMA_VERSION,
    RegistryConflictError,
    RegistryPathError,
    _connect,
    assert_no_sensitive_strings,
    canonical_json_sha256,
    initialize_registry,
    utc_now_iso,
)
from .scientific_applicability import check_scientific_applicability, validate_scientific_config_safety
from .scientific_constraint_registry import (
    ScientificConstraintRegistry,
    build_default_scientific_constraint_registry,
)
from .scientific_constraints import ScientificConstraint, ScientificFinding
from .scientific_evaluators import (
    ScientificEvaluatorRegistry,
    build_default_evaluator_registry,
    evaluate_constraint,
)
from .units import UnitRegistry, build_default_unit_registry


SCIENTIFIC_EXECUTION_SCHEMA_VERSION = "2.1"
SCIENTIFIC_EXECUTION_OUTPUT_SCHEMA_VERSION = "2.1"
RESULT_STATUSES = (
    "consistent",
    "conditionally_consistent",
    "inconsistent",
    "unavailable",
    "invalid_input",
    "failed",
)
TOLERANCE_STATUSES = (
    "within_tolerance",
    "within_uncertainty",
    "borderline",
    "outside_tolerance",
    "uncertainty_unavailable",
)
FORBIDDEN_REQUEST_KEYS = {
    "input_path",
    "csv_path",
    "raw_path",
    "dataset_path",
    "model_path",
    "script_path",
    "callable",
    "callable_name",
    "module_path",
    "python_expression",
    "equation",
    "raw_table",
    "dataframe",
}
FORBIDDEN_TEXT_MARKERS = (
    "eval(",
    "exec(",
    "__import__",
    "subprocess",
    "socket.",
    "requests.",
    "file://",
)
LOCAL_OUTPUT_ROOT = "outputs/platform_science"


def _safe_id(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} is required")
    if any(part in value for part in ("..", "/", "\\")):
        raise ValueError(f"{field_name} must be an identifier, not a path")
    return value.strip()


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise ValueError(f"unsupported JSON value type: {type(value).__name__}")


def _assert_request_safe(payload: Any, *, location: str = "request") -> None:
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            key_text = str(key)
            if key_text in FORBIDDEN_REQUEST_KEYS:
                raise ValueError(f"forbidden scientific execution field: {location}.{key_text}")
            _assert_request_safe(value, location=f"{location}.{key_text}")
        return
    if isinstance(payload, (list, tuple)):
        for index, value in enumerate(payload):
            _assert_request_safe(value, location=f"{location}[{index}]")
        return
    if isinstance(payload, str):
        lowered = payload.lower()
        if any(marker in lowered for marker in FORBIDDEN_TEXT_MARKERS):
            raise ValueError(f"forbidden executable-looking text at {location}")
        if os.path.isabs(payload):
            raise ValueError(f"absolute path-like scientific input is forbidden at {location}")
        if "\n" in payload and "," in payload:
            raise ValueError(f"raw table-like scientific input is forbidden at {location}")


def _as_float(value: Any, *, variable_id: str) -> float:
    if isinstance(value, bool) or isinstance(value, (str, bytes)) or value is None:
        raise ValueError(f"{variable_id} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{variable_id} must be finite")
    return number


def _as_float_list(value: Any, *, variable_id: str) -> list[float]:
    if isinstance(value, Mapping):
        value = value.get("values", value.get("value"))
    if isinstance(value, (list, tuple)):
        return [_as_float(item, variable_id=variable_id) for item in value]
    return [_as_float(value, variable_id=variable_id)]


def _value_for(values: Mapping[str, Any], variable_id: str) -> Any | None:
    if variable_id in values:
        return values[variable_id]
    aliases = {
        "two_theta": ("peak_two_theta",),
        "fwhm": ("FWHM", "beta"),
        "instrumental_broadening": ("instrumental_fwhm", "instrumental_beta"),
        "capacity": ("discharge_capacity",),
    }
    for alias in aliases.get(variable_id, ()):
        if alias in values:
            return values[alias]
    return None


def _hash_payload(payload: Mapping[str, Any]) -> str:
    return canonical_json_sha256(dict(payload))


def _git_commit(repo_root: str | Path = ".") -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(repo_root),
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return completed.stdout.strip() or "unknown"


def _finding_id(*parts: object) -> str:
    return hashlib.sha256(":".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:24]


def _extra_finding(
    constraint_id: str,
    *,
    status: str,
    severity: str,
    message: str,
    remediation_code: str,
    category: str = "scientific_execution",
    claim_impact: str = "narrow_claim",
    evidence_refs: tuple[str, ...] = (),
) -> ScientificFinding:
    return ScientificFinding(
        finding_id=_finding_id(constraint_id, status, remediation_code, message),
        constraint_id=constraint_id,
        status=status,
        severity=severity,
        message=message,
        remediation_code=remediation_code,
        category=category,
        claim_impact=claim_impact,
        evidence_refs=evidence_refs,
    )


@dataclass(frozen=True)
class ScientificInputValue:
    variable_id: str
    value: Any
    unit: str | None = None
    uncertainty: Mapping[str, Any] | None = None
    source: str = "config"
    semantic_status: str = "known"

    def __post_init__(self) -> None:
        _safe_id(self.variable_id, "variable_id")
        if self.unit is not None:
            _safe_id(self.unit, "unit")
        _json_safe(self.value)
        _json_safe(self.uncertainty or {})

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ScientificInputValue":
        return cls(
            variable_id=str(payload["variable_id"]),
            value=payload["value"],
            unit=payload.get("unit"),
            uncertainty=payload.get("uncertainty"),
            source=str(payload.get("source", "config")),
            semantic_status=str(payload.get("semantic_status", "known")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "variable_id": self.variable_id,
            "value": _json_safe(self.value),
            "unit": self.unit,
            "uncertainty": _json_safe(self.uncertainty or {}),
            "source": self.source,
            "semantic_status": self.semantic_status,
        }


@dataclass(frozen=True)
class ScientificExecutionRequest:
    execution_id: str
    knowledge_pack_id: str
    constraint_ids: tuple[str, ...]
    inputs: tuple[ScientificInputValue, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)
    requested_claim_ids: tuple[str, ...] = ()
    persist_findings: bool = False
    run_id: str | None = None
    strict_mode: bool = False
    output_policy: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> "ScientificExecutionRequest":
        _assert_request_safe(config)
        assert_no_sensitive_strings(config)
        safety_errors = validate_scientific_config_safety(
            {
                "schema_version": config.get("schema_version", SCIENTIFIC_EXECUTION_SCHEMA_VERSION),
                "variables": {item["variable_id"]: item.get("value") for item in config.get("inputs", [])},
                "metadata": config.get("metadata", {}),
                "credential_policy": config.get("credential_policy", {"store_credentials": False}),
            }
        )
        if safety_errors:
            raise ValueError("; ".join(safety_errors))
        return cls(
            execution_id=_safe_id(str(config["execution_id"]), "execution_id"),
            knowledge_pack_id=_safe_id(str(config["knowledge_pack_id"]), "knowledge_pack_id"),
            constraint_ids=tuple(str(item) for item in config.get("constraint_ids", ())),
            inputs=tuple(ScientificInputValue.from_dict(item) for item in config.get("inputs", ())),
            metadata=_json_safe(config.get("metadata", {})),
            requested_claim_ids=tuple(str(item) for item in config.get("requested_claim_ids", ())),
            persist_findings=bool(config.get("persist_findings", False)),
            run_id=config.get("run_id"),
            strict_mode=bool(config.get("strict_mode", False)),
            output_policy=_json_safe(config.get("output_policy", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCIENTIFIC_EXECUTION_SCHEMA_VERSION,
            "execution_id": self.execution_id,
            "knowledge_pack_id": self.knowledge_pack_id,
            "constraint_ids": list(self.constraint_ids),
            "inputs": [item.to_dict() for item in self.inputs],
            "metadata": _json_safe(self.metadata),
            "requested_claim_ids": list(self.requested_claim_ids),
            "persist_findings": self.persist_findings,
            "run_id": self.run_id,
            "strict_mode": self.strict_mode,
            "output_policy": _json_safe(self.output_policy),
        }

    def request_hash(self) -> str:
        return _hash_payload(self.to_dict())


@dataclass(frozen=True)
class ScientificExecutionContext:
    code_commit: str
    registry_version: int
    started_at: str
    repo_root: str
    registry_path: str
    constraint_registry: ScientificConstraintRegistry
    domain_registry: DomainKnowledgeRegistry
    evaluator_registry: ScientificEvaluatorRegistry
    unit_registry: UnitRegistry

    @classmethod
    def build(
        cls,
        *,
        repo_root: str | Path = ".",
        registry_path: str = DEFAULT_REGISTRY_PATH,
        constraint_registry: ScientificConstraintRegistry | None = None,
        domain_registry: DomainKnowledgeRegistry | None = None,
        evaluator_registry: ScientificEvaluatorRegistry | None = None,
        unit_registry: UnitRegistry | None = None,
    ) -> "ScientificExecutionContext":
        unit_registry = unit_registry or build_default_unit_registry()
        evaluator_registry = evaluator_registry or build_default_evaluator_registry()
        constraint_registry = constraint_registry or build_default_scientific_constraint_registry(
            evaluator_registry,
            unit_registry,
        )
        return cls(
            code_commit=_git_commit(repo_root),
            registry_version=REGISTRY_SCHEMA_VERSION,
            started_at=utc_now_iso(),
            repo_root=str(Path(repo_root)),
            registry_path=registry_path,
            constraint_registry=constraint_registry,
            domain_registry=domain_registry or build_default_domain_knowledge_registry(),
            evaluator_registry=evaluator_registry,
            unit_registry=unit_registry,
        )


@dataclass(frozen=True)
class UnitConversionRecord:
    conversion_id: str
    execution_id: str
    variable_id: str
    original_value: Any
    original_unit: str | None
    normalized_value: Any
    normalized_unit: str | None
    conversion_status: str
    tolerance_status: str = "uncertainty_unavailable"
    precision_tolerance: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "conversion_id": self.conversion_id,
            "execution_id": self.execution_id,
            "variable_id": self.variable_id,
            "original_value": self.original_value,
            "original_unit": self.original_unit,
            "normalized_value": self.normalized_value,
            "normalized_unit": self.normalized_unit,
            "conversion_status": self.conversion_status,
            "tolerance_status": self.tolerance_status,
            "precision_tolerance": self.precision_tolerance,
        }


@dataclass(frozen=True)
class AssumptionResult:
    constraint_id: str
    status: str
    assumptions: tuple[str, ...]
    reason_code: str = "declared_or_not_required"

    def to_dict(self) -> dict[str, Any]:
        return {
            "constraint_id": self.constraint_id,
            "status": self.status,
            "assumptions": list(self.assumptions),
            "reason_code": self.reason_code,
        }


@dataclass(frozen=True)
class ScientificExecutionResult:
    execution_id: str
    knowledge_pack_id: str
    overall_status: str
    applicability_status: str
    finding_count: int
    blocker_count: int
    findings: tuple[ScientificFinding, ...]
    normalized_inputs: Mapping[str, Any]
    unit_conversions: tuple[UnitConversionRecord, ...]
    assumption_results: tuple[AssumptionResult, ...]
    claim_evaluations: tuple[ClaimEvaluation, ...]
    evidence_refs: tuple[str, ...]
    warnings: tuple[str, ...]
    errors: tuple[str, ...]
    scientific_recomputation_performed: bool
    raw_data_read: bool
    model_training_performed: bool
    request_hash: str
    code_commit: str
    registry_schema_version: int
    started_at: str
    completed_at: str
    derived_outputs: Mapping[str, Any] = field(default_factory=dict)
    execution_manifest: Mapping[str, Any] = field(default_factory=dict)
    result_schema_id: str | None = None
    result_schema_version: str | None = None
    output_entities: tuple[Mapping[str, Any], ...] = ()
    output_quantities: tuple[Mapping[str, Any], ...] = ()
    uncertainty_summary: Mapping[str, Any] = field(default_factory=dict)
    uncertainty_status: str = "not_evaluated"
    provenance_summary: Mapping[str, Any] = field(default_factory=dict)
    relation_refs: tuple[str, ...] = ()
    operator_refs: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCIENTIFIC_EXECUTION_OUTPUT_SCHEMA_VERSION,
            "execution_id": self.execution_id,
            "knowledge_pack_id": self.knowledge_pack_id,
            "overall_status": self.overall_status,
            "applicability_status": self.applicability_status,
            "finding_count": self.finding_count,
            "blocker_count": self.blocker_count,
            "findings": [finding.to_dict() for finding in self.findings],
            "normalized_inputs": _json_safe(self.normalized_inputs),
            "unit_conversions": [item.to_dict() for item in self.unit_conversions],
            "assumption_results": [item.to_dict() for item in self.assumption_results],
            "claim_evaluations": [item.to_dict() for item in self.claim_evaluations],
            "evidence_refs": list(self.evidence_refs),
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "scientific_recomputation_performed": self.scientific_recomputation_performed,
            "raw_data_read": self.raw_data_read,
            "model_training_performed": self.model_training_performed,
            "request_hash": self.request_hash,
            "code_commit": self.code_commit,
            "registry_schema_version": self.registry_schema_version,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "derived_outputs": _json_safe(self.derived_outputs),
            "execution_manifest": _json_safe(self.execution_manifest),
            "result_schema_id": self.result_schema_id,
            "result_schema_version": self.result_schema_version,
            "output_entities": [_json_safe(item) for item in self.output_entities],
            "output_quantities": [_json_safe(item) for item in self.output_quantities],
            "uncertainty_summary": _json_safe(self.uncertainty_summary),
            "uncertainty_status": self.uncertainty_status,
            "provenance_summary": _json_safe(self.provenance_summary),
            "relation_refs": list(self.relation_refs),
            "operator_refs": list(self.operator_refs),
        }

    def to_markdown(self) -> str:
        lines = [
            "# Scientific Execution Report",
            "",
            "## Run Summary",
            f"- execution_id: `{self.execution_id}`",
            f"- knowledge_pack_id: `{self.knowledge_pack_id}`",
            f"- overall_status: `{self.overall_status}`",
            f"- applicability_status: `{self.applicability_status}`",
            f"- findings: `{self.finding_count}`",
            f"- blockers: `{self.blocker_count}`",
            "",
            "## Claim Boundary",
            "- This report records bounded scalar/small-list consistency checks.",
            "- It does not read raw datasets, train models, perform DFT/FEM/CFD, or identify phases.",
            "- Scientific consistency findings narrow claims; they do not prove full scientific correctness.",
            "",
            "## Findings",
        ]
        for finding in self.findings:
            lines.append(
                f"- `{finding.constraint_id}`: `{finding.status}` / `{finding.severity}` - {finding.message}"
            )
        lines.extend(["", "## Derived Outputs"])
        for key, value in sorted(self.derived_outputs.items()):
            lines.append(f"- `{key}`: `{value}`")
        lines.extend(["", "## Claim Evaluations"])
        for claim in self.claim_evaluations:
            lines.append(f"- `{claim.claim_id}`: `{claim.status}` (`{claim.reason_code}`)")
        lines.append("")
        return "\n".join(lines)


def load_execution_config(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("scientific execution config must be a JSON object")
    _assert_request_safe(payload)
    assert_no_sensitive_strings(payload)
    return payload


def _values_and_units(request: ScientificExecutionRequest) -> tuple[dict[str, Any], dict[str, str], dict[str, ScientificInputValue]]:
    values: dict[str, Any] = {}
    units: dict[str, str] = {}
    input_by_id: dict[str, ScientificInputValue] = {}
    for item in request.inputs:
        if item.variable_id in input_by_id:
            raise ValueError(f"duplicate variable_id: {item.variable_id}")
        input_by_id[item.variable_id] = item
        values[item.variable_id] = item.value
        if item.unit:
            units[item.variable_id] = item.unit
    return values, units, input_by_id


def _normalize_value(
    *,
    execution_id: str,
    variable_id: str,
    value: Any,
    supplied_unit: str | None,
    expected_unit: str,
    unit_registry: UnitRegistry,
    uncertainty: Mapping[str, Any] | None = None,
) -> tuple[Any | None, UnitConversionRecord, str | None]:
    if supplied_unit is None:
        return (
            None,
            UnitConversionRecord(
                _finding_id(execution_id, variable_id, "missing_unit"),
                execution_id,
                variable_id,
                value,
                supplied_unit,
                None,
                expected_unit,
                "missing_unit",
            ),
            "missing_unit",
        )
    try:
        if not unit_registry.compatible(supplied_unit, expected_unit):
            raise ValueError(f"incompatible unit dimension: {supplied_unit} -> {expected_unit}")
        numeric_values = _as_float_list(value, variable_id=variable_id)
        converted = [unit_registry.convert_value(item, supplied_unit, expected_unit) for item in numeric_values]
    except (KeyError, ValueError) as exc:
        return (
            None,
            UnitConversionRecord(
                _finding_id(execution_id, variable_id, "incompatible_unit"),
                execution_id,
                variable_id,
                value,
                supplied_unit,
                None,
                expected_unit,
                "incompatible_unit",
            ),
            str(exc),
        )
    normalized: float | list[float] = converted[0] if not isinstance(value, (list, tuple)) else converted
    tolerance_status = "uncertainty_unavailable"
    if uncertainty:
        absolute = uncertainty.get("absolute_uncertainty")
        relative = uncertainty.get("relative_uncertainty")
        if absolute is not None or relative is not None:
            tolerance_status = "within_uncertainty"
    status = "already_canonical" if supplied_unit == expected_unit else "converted"
    return (
        normalized,
        UnitConversionRecord(
            _finding_id(execution_id, variable_id, supplied_unit, expected_unit),
            execution_id,
            variable_id,
            value,
            supplied_unit,
            normalized,
            expected_unit,
            status,
            tolerance_status=tolerance_status,
            precision_tolerance=1e-12,
        ),
        None,
    )


def _normalize_for_constraint(
    request: ScientificExecutionRequest,
    constraint: ScientificConstraint,
    values: Mapping[str, Any],
    units: Mapping[str, str],
    inputs: Mapping[str, ScientificInputValue],
    unit_registry: UnitRegistry,
) -> tuple[dict[str, Any], dict[str, str], list[UnitConversionRecord], list[ScientificFinding], dict[str, Any]]:
    normalized = dict(values)
    normalized_units = dict(units)
    conversions: list[UnitConversionRecord] = []
    findings: list[ScientificFinding] = []
    per_constraint: dict[str, Any] = {}
    for variable_id, expected_unit in sorted(constraint.expected_units.items()):
        source_input = inputs.get(variable_id)
        source_value = _value_for(values, variable_id)
        if source_value is None:
            findings.append(
                _extra_finding(
                    constraint.constraint_id,
                    status="unavailable",
                    severity="warning",
                    message=f"Required variable {variable_id} is missing.",
                    remediation_code="provide_variable_metadata",
                    category="applicability",
                    evidence_refs=(f"variable:{variable_id}",),
                )
            )
            continue
        supplied_unit = units.get(variable_id)
        normalized_value, conversion, error = _normalize_value(
            execution_id=request.execution_id,
            variable_id=variable_id,
            value=source_value,
            supplied_unit=supplied_unit,
            expected_unit=expected_unit,
            unit_registry=unit_registry,
            uncertainty=source_input.uncertainty if source_input else None,
        )
        conversions.append(conversion)
        per_constraint[variable_id] = conversion.to_dict()
        if error:
            remediation = "provide_unit_metadata" if error == "missing_unit" else "correct_unit_dimension"
            findings.append(
                _extra_finding(
                    constraint.constraint_id,
                    status="unavailable" if error == "missing_unit" else "inconsistent",
                    severity="warning",
                    message=f"Unit conversion for {variable_id} failed: {error}.",
                    remediation_code=remediation,
                    category="unit_consistency",
                    claim_impact=constraint.claim_impact,
                    evidence_refs=(f"variable:{variable_id}",),
                )
            )
            continue
        normalized[variable_id] = normalized_value
        normalized_units[variable_id] = expected_unit
    return normalized, normalized_units, conversions, findings, per_constraint


def _constraint_applicability_config(request: ScientificExecutionRequest) -> dict[str, Any]:
    values, units, _ = _values_and_units(request)
    return {
        "schema_version": "2.1",
        "constraint_ids": list(request.constraint_ids),
        "variables": values,
        "units": units,
        "metadata": _json_safe(request.metadata),
    }


def _bragg_derivation(
    request: ScientificExecutionRequest,
    values: Mapping[str, Any],
    units: Mapping[str, str],
    unit_registry: UnitRegistry,
) -> tuple[dict[str, Any], tuple[ScientificFinding, ...]]:
    try:
        two_theta = _as_float_list(_value_for(values, "two_theta"), variable_id="two_theta")[0]
        wavelength = _as_float_list(_value_for(values, "wavelength"), variable_id="wavelength")[0]
        two_theta_degree = unit_registry.convert_value(two_theta, units.get("two_theta", "degree"), "degree")
        wavelength_angstrom = unit_registry.convert_value(wavelength, units.get("wavelength", "angstrom"), "angstrom")
        order = int(_as_float(_value_for(values, "diffraction_order") or request.metadata.get("diffraction_order", 1), variable_id="diffraction_order"))
    except (KeyError, ValueError, TypeError) as exc:
        return {}, (
            _extra_finding(
                "xrd.bragg.geometry",
                status="unavailable",
                severity="warning",
                message=f"Bragg derivation unavailable: {exc}.",
                remediation_code="provide_xrd_geometry_metadata",
                category="derived_feature",
            ),
        )
    if order <= 0 or two_theta_degree <= 0 or two_theta_degree >= 180 or wavelength_angstrom <= 0:
        return {}, (
            _extra_finding(
                "xrd.bragg.geometry",
                status="outside_validity_range",
                severity="warning",
                message="Bragg derivation inputs are outside the supported domain.",
                remediation_code="inspect_peak_positions",
                category="derived_feature",
            ),
        )
    theta_rad = math.radians(two_theta_degree / 2.0)
    d_spacing = (order * wavelength_angstrom) / (2.0 * math.sin(theta_rad))
    tolerance = float(request.metadata.get("d_spacing_tolerance_angstrom", 1e-3))
    output: dict[str, Any] = {
        "bragg_theta_degree": two_theta_degree / 2.0,
        "bragg_theta_rad": theta_rad,
        "bragg_diffraction_order": order,
        "derived_d_spacing_angstrom": d_spacing,
        "d_spacing_tolerance_angstrom": tolerance,
    }
    supplied = _value_for(values, "supplied_d_spacing")
    if supplied is None:
        finding = _extra_finding(
            "xrd.bragg.geometry",
            status="conditionally_consistent",
            severity="info",
            message="Bragg d-spacing was derived; no supplied d-spacing was provided for residual comparison.",
            remediation_code="none",
            category="derived_feature",
            evidence_refs=("scientific_evidence:lattice_spacing_estimated",),
        )
    else:
        supplied_unit = units.get("supplied_d_spacing", "angstrom")
        supplied_angstrom = unit_registry.convert_value(_as_float_list(supplied, variable_id="supplied_d_spacing")[0], supplied_unit, "angstrom")
        residual = supplied_angstrom - d_spacing
        absolute = abs(residual)
        uncertainty = request.metadata.get("supplied_d_spacing_uncertainty_angstrom")
        tolerance_status = _compare_tolerance(absolute, tolerance, uncertainty)
        output.update(
            {
                "supplied_d_spacing_angstrom": supplied_angstrom,
                "d_spacing_residual_angstrom": residual,
                "d_spacing_tolerance_status": tolerance_status,
            }
        )
        finding = _extra_finding(
            "xrd.bragg.geometry",
            status="consistent" if tolerance_status in {"within_tolerance", "within_uncertainty", "borderline"} else "inconsistent",
            severity="info" if tolerance_status in {"within_tolerance", "within_uncertainty"} else "warning",
            message=f"Bragg derived d-spacing residual is {residual:.6g} angstrom ({tolerance_status}).",
            remediation_code="none" if tolerance_status != "outside_tolerance" else "inspect_bragg_d_spacing",
            category="derived_feature",
            evidence_refs=("scientific_evidence:bragg_geometry_consistent", "scientific_evidence:lattice_spacing_estimated"),
        )
    return output, (finding,)


def _compare_tolerance(residual_abs: float, tolerance: float, uncertainty: Any = None) -> str:
    if residual_abs <= abs(tolerance):
        return "within_tolerance"
    if uncertainty is not None and residual_abs <= abs(tolerance) + abs(float(uncertainty)):
        return "within_uncertainty"
    if residual_abs <= abs(tolerance) * 1.5:
        return "borderline"
    return "outside_tolerance"


def _scherrer_derivation(
    request: ScientificExecutionRequest,
    values: Mapping[str, Any],
    units: Mapping[str, str],
    unit_registry: UnitRegistry,
) -> tuple[dict[str, Any], tuple[ScientificFinding, ...]]:
    try:
        two_theta = _as_float_list(_value_for(values, "two_theta"), variable_id="two_theta")[0]
        wavelength = _as_float_list(_value_for(values, "wavelength"), variable_id="wavelength")[0]
        fwhm = _as_float_list(_value_for(values, "fwhm"), variable_id="fwhm")[0]
        shape_factor_raw = _value_for(values, "shape_factor")
        shape_factor = _as_float(shape_factor_raw if shape_factor_raw is not None else request.metadata.get("shape_factor", 0.9), variable_id="shape_factor")
        two_theta_degree = unit_registry.convert_value(two_theta, units.get("two_theta", "degree"), "degree")
        wavelength_angstrom = unit_registry.convert_value(wavelength, units.get("wavelength", "angstrom"), "angstrom")
        beta_rad = unit_registry.convert_value(fwhm, units.get("fwhm", "rad"), "rad")
    except (KeyError, ValueError, TypeError) as exc:
        return {}, (
            _extra_finding(
                "xrd.scherrer.preconditions",
                status="unavailable",
                severity="warning",
                message=f"Scherrer derivation unavailable: {exc}.",
                remediation_code="provide_scherrer_metadata",
                category="derived_feature",
            ),
        )
    if beta_rad <= 0 or wavelength_angstrom <= 0 or not 0 < two_theta_degree < 180:
        return {}, (
            _extra_finding(
                "xrd.scherrer.preconditions",
                status="outside_validity_range",
                severity="warning",
                message="Scherrer inputs are outside the supported domain.",
                remediation_code="provide_positive_fwhm",
                category="derived_feature",
            ),
        )
    inst_value = _value_for(values, "instrumental_broadening")
    correction_status = "uncorrected_estimate"
    beta_corrected = beta_rad
    findings: list[ScientificFinding] = []
    if inst_value is not None:
        inst_rad = unit_registry.convert_value(
            _as_float_list(inst_value, variable_id="instrumental_broadening")[0],
            units.get("instrumental_broadening", units.get("fwhm", "rad")),
            "rad",
        )
        if beta_rad <= inst_rad:
            return {
                "scherrer_beta_rad": beta_rad,
                "instrumental_broadening_rad": inst_rad,
                "instrumental_correction_status": "invalid_corrected_beta",
            }, (
                _extra_finding(
                    "xrd.scherrer.preconditions",
                    status="outside_validity_range",
                    severity="warning",
                    message="Instrumental broadening is greater than or equal to measured FWHM; corrected beta is invalid.",
                    remediation_code="inspect_instrumental_broadening",
                    category="derived_feature",
                ),
            )
        beta_corrected = math.sqrt(beta_rad**2 - inst_rad**2)
        correction_status = "instrumental_broadening_corrected"
    else:
        findings.append(
            _extra_finding(
                "xrd.scherrer.preconditions",
                status="conditionally_consistent",
                severity="warning",
                message="No instrumental broadening value was supplied; Scherrer result is an uncorrected crystallite-size estimate.",
                remediation_code="provide_instrumental_broadening",
                category="physics_claim_boundary",
                claim_impact="narrow_claim",
            )
        )
    theta_rad = math.radians(two_theta_degree / 2.0)
    cos_theta = math.cos(theta_rad)
    if cos_theta <= 0:
        return {}, (
            _extra_finding(
                "xrd.scherrer.preconditions",
                status="outside_validity_range",
                severity="warning",
                message="Scherrer theta is outside the supported cosine domain.",
                remediation_code="inspect_peak_positions",
                category="derived_feature",
            ),
        )
    crystallite_angstrom = (shape_factor * wavelength_angstrom) / (beta_corrected * cos_theta)
    crystallite_nm = crystallite_angstrom / 10.0
    findings.append(
        _extra_finding(
            "xrd.scherrer.preconditions",
            status="conditionally_consistent",
            severity="info",
            message="Scherrer crystallite-size estimate was derived; this is not particle size or phase identification.",
            remediation_code="none",
            category="derived_feature",
            claim_impact="narrow_claim",
            evidence_refs=("scientific_evidence:crystallite_size_estimated",),
        )
    )
    if request.metadata.get("strain_broadening_separated") is not True:
        findings.append(
            _extra_finding(
                "xrd.scherrer.preconditions",
                status="conditionally_consistent",
                severity="warning",
                message="Strain broadening was not separated; claim boundary remains limited.",
                remediation_code="document_strain_broadening_policy",
                category="physics_claim_boundary",
                claim_impact="narrow_claim",
            )
        )
    return (
        {
            "scherrer_theta_degree": two_theta_degree / 2.0,
            "scherrer_beta_rad": beta_rad,
            "scherrer_corrected_beta_rad": beta_corrected,
            "shape_factor": shape_factor,
            "instrumental_correction_status": correction_status,
            "crystallite_size_angstrom": crystallite_angstrom,
            "crystallite_size_nm": crystallite_nm,
        },
        tuple(findings),
    )


def _materials_derivations(request: ScientificExecutionRequest, values: Mapping[str, Any]) -> tuple[dict[str, Any], tuple[ScientificFinding, ...]]:
    outputs: dict[str, Any] = {}
    findings: list[ScientificFinding] = []
    elements = request.metadata.get("elements")
    if elements is not None:
        if not isinstance(elements, list) or not all(isinstance(item, str) and item[:1].isalpha() and item[0].isupper() for item in elements):
            findings.append(
                _extra_finding("materials.composition_fraction.sum_to_one", status="inconsistent", severity="warning", message="Element identity metadata is malformed.", remediation_code="inspect_element_symbols")
            )
        elif len(set(elements)) != len(elements):
            findings.append(
                _extra_finding("materials.composition_fraction.sum_to_one", status="inconsistent", severity="warning", message="Duplicate element symbols were supplied.", remediation_code="deduplicate_composition_elements")
            )
    fractions_raw = _value_for(values, "composition_fraction")
    property_values = request.metadata.get("element_property_values")
    if fractions_raw is not None and isinstance(property_values, list):
        fractions = _as_float_list(fractions_raw, variable_id="composition_fraction")
        properties = [_as_float(item, variable_id="element_property_values") for item in property_values]
        if len(fractions) == len(properties):
            mean = sum(f * p for f, p in zip(fractions, properties))
            variance = sum(f * ((p - mean) ** 2) for f, p in zip(fractions, properties))
            outputs["composition_weighted_property_mean"] = mean
            outputs["composition_weighted_property_variance"] = variance
            findings.append(
                _extra_finding("materials.composition_fraction.sum_to_one", status="consistent", severity="info", message="Synthetic composition-weighted descriptor was derived from explicit fixture metadata.", remediation_code="none", category="derived_feature")
            )
    return outputs, tuple(findings)


def _battery_derivations(request: ScientificExecutionRequest, values: Mapping[str, Any], units: Mapping[str, str], unit_registry: UnitRegistry) -> tuple[dict[str, Any], tuple[ScientificFinding, ...]]:
    outputs: dict[str, Any] = {}
    findings: list[ScientificFinding] = []
    capacity_raw = _value_for(values, "capacity")
    baseline = request.metadata.get("baseline_capacity")
    if capacity_raw is not None and baseline is not None:
        capacity = _as_float_list(capacity_raw, variable_id="capacity")
        baseline_capacity = _as_float(baseline, variable_id="baseline_capacity")
        if baseline_capacity > 0:
            outputs["capacity_retention"] = [item / baseline_capacity for item in capacity]
            findings.append(
                _extra_finding("battery.capacity.non_negative", status="consistent", severity="info", message="Capacity retention was derived from explicit baseline metadata.", remediation_code="none", category="derived_feature")
            )
    voltage = _value_for(values, "voltage")
    if voltage is not None and "voltage_range" in request.metadata:
        lower, upper = request.metadata["voltage_range"]
        voltages = _as_float_list(voltage, variable_id="voltage")
        if min(voltages) < float(lower) or max(voltages) > float(upper):
            findings.append(
                _extra_finding("battery.capacity.non_negative", status="outside_validity_range", severity="warning", message="Voltage metadata is outside supplied range.", remediation_code="inspect_voltage_metadata", category="measurement_constraint")
            )
    resistance = _value_for(values, "resistance")
    if resistance is not None and min(_as_float_list(resistance, variable_id="resistance")) < 0:
        findings.append(
            _extra_finding("battery.capacity.non_negative", status="inconsistent", severity="warning", message="Resistance metadata is negative.", remediation_code="inspect_resistance_metadata", category="measurement_constraint")
        )
    del units, unit_registry
    return outputs, tuple(findings)


def _derive_outputs(
    request: ScientificExecutionRequest,
    values: Mapping[str, Any],
    units: Mapping[str, str],
    unit_registry: UnitRegistry,
) -> tuple[dict[str, Any], tuple[ScientificFinding, ...]]:
    outputs: dict[str, Any] = {}
    findings: list[ScientificFinding] = []
    constraint_ids = set(request.constraint_ids)
    if "xrd.bragg.geometry" in constraint_ids:
        derived, extra = _bragg_derivation(request, values, units, unit_registry)
        outputs.update(derived)
        findings.extend(extra)
    if "xrd.scherrer.preconditions" in constraint_ids:
        derived, extra = _scherrer_derivation(request, values, units, unit_registry)
        outputs.update(derived)
        findings.extend(extra)
    if any(item.startswith("materials.") for item in constraint_ids):
        derived, extra = _materials_derivations(request, values)
        outputs.update(derived)
        findings.extend(extra)
    if any(item.startswith("battery.") for item in constraint_ids):
        derived, extra = _battery_derivations(request, values, units, unit_registry)
        outputs.update(derived)
        findings.extend(extra)
    if {"xrd.bragg.geometry", "xrd.scherrer.preconditions"} <= constraint_ids:
        outputs["xrd_combined_summary"] = {
            "phase_identification_performed": False,
            "metadata_completeness_status": "bounded_scalar_metadata_only",
            "claim_boundary": "geometry and crystallite-size estimate only",
        }
    return outputs, tuple(findings)


def _overall_status(findings: Sequence[ScientificFinding], errors: Sequence[str]) -> str:
    if errors:
        return "invalid_input"
    if any(finding.severity == "blocker" for finding in findings):
        return "failed"
    if any(finding.status in {"inconsistent", "outside_validity_range", "assumption_violation"} for finding in findings):
        return "inconsistent"
    if any(finding.status in {"unavailable", "insufficient_metadata"} for finding in findings):
        return "unavailable"
    if any(finding.status == "conditionally_consistent" for finding in findings):
        return "conditionally_consistent"
    return "consistent"


def _available_scientific_evidence(findings: Sequence[ScientificFinding], derived_outputs: Mapping[str, Any]) -> tuple[str, ...]:
    evidence = set()
    if all(finding.category != "unit_consistency" or finding.status in {"consistent", "conditionally_consistent"} for finding in findings):
        evidence.add("scientific_evidence:dimensionally_consistent")
    if not any(finding.status in {"inconsistent", "outside_validity_range", "assumption_violation"} for finding in findings):
        evidence.add("scientific_evidence:physically_consistent_input")
    if any(finding.status == "consistent" for finding in findings if "composition_fraction.sum" in finding.constraint_id):
        evidence.add("scientific_evidence:conservation_respected")
    if "derived_d_spacing_angstrom" in derived_outputs:
        evidence.add("scientific_evidence:bragg_geometry_consistent")
        evidence.add("scientific_evidence:lattice_spacing_estimated")
    if "crystallite_size_nm" in derived_outputs:
        evidence.add("scientific_evidence:crystallite_size_estimated")
    return tuple(sorted(evidence))


def _evaluate_claims(request: ScientificExecutionRequest, findings: Sequence[ScientificFinding], derived_outputs: Mapping[str, Any]) -> tuple[ClaimEvaluation, ...]:
    evidence = _available_scientific_evidence(findings, derived_outputs)
    allowed = (
        "physically consistent input",
        "dimensionally consistent",
        "conservation respected",
        "thermodynamic consistency",
        "crystallite size estimated",
        "bragg geometry consistent",
        "lattice spacing estimated",
    )
    prohibited = (
        "phase identification supported",
        "particle size",
        "crystal structure confirmed",
        "material composition confirmed",
        "physics-constrained model",
        "hybrid physics ml",
    )
    evaluations: list[ClaimEvaluation] = []
    for claim_id in request.requested_claim_ids:
        if claim_id == "phase_identification_supported":
            evaluations.append(
                ClaimEvaluation(
                    claim_id,
                    "prohibited",
                    conflicting_evidence=("xrd_phase_identification_not_performed",),
                    reason_code="phase_identification_out_of_scope",
                )
            )
            continue
        if claim_id == "physics_constrained_model":
            evaluations.append(
                ClaimEvaluation(
                    claim_id,
                    "unsupported",
                    conflicting_evidence=("missing:model_scientific_constraint_evidence",),
                    reason_code="model_evidence_not_available",
                )
            )
            continue
        evaluations.append(
            evaluate_claim_id(
                claim_id,
                allowed_claims=allowed,
                prohibited_claims=prohibited,
                available_evidence=evidence,
            )
        )
    return tuple(evaluations)


def execute_scientific_request(
    request: ScientificExecutionRequest,
    *,
    context: ScientificExecutionContext | None = None,
) -> ScientificExecutionResult:
    context = context or ScientificExecutionContext.build()
    started_at = context.started_at
    warnings: list[str] = []
    errors: list[str] = []
    try:
        pack = context.domain_registry.get(request.knowledge_pack_id)
    except KeyError as exc:
        errors.append(str(exc))
        pack = DomainKnowledgePack(
            pack_id=request.knowledge_pack_id,
            domain="unknown",
            name="unknown",
            description="unknown",
            constraint_ids=(),
        )
    values: dict[str, Any] = {}
    units: dict[str, str] = {}
    inputs: dict[str, ScientificInputValue] = {}
    findings: list[ScientificFinding] = []
    conversions: list[UnitConversionRecord] = []
    assumption_results: list[AssumptionResult] = []
    normalized_snapshot: dict[str, Any] = {}
    scientific_recomputed = False
    applicability_status = "applicable"

    if not errors:
        values, units, inputs = _values_and_units(request)
        unknown_constraints = [item for item in request.constraint_ids if item not in set(pack.constraint_ids)]
        if unknown_constraints and request.strict_mode:
            errors.append(f"constraints outside knowledge pack: {', '.join(unknown_constraints)}")
        try:
            applicability = check_scientific_applicability(
                _constraint_applicability_config(request),
                constraint_registry=context.constraint_registry,
                evaluator_registry=context.evaluator_registry,
            )
            applicability_status = applicability.status
        except (ValueError, KeyError) as exc:
            errors.append(str(exc))
    for constraint_id in request.constraint_ids:
        if errors:
            break
        try:
            constraint = context.constraint_registry.get(constraint_id)
        except KeyError as exc:
            errors.append(str(exc))
            break
        normalized_values, normalized_units, unit_conversions, unit_findings, per_constraint = _normalize_for_constraint(
            request,
            constraint,
            values,
            units,
            inputs,
            context.unit_registry,
        )
        conversions.extend(unit_conversions)
        findings.extend(unit_findings)
        normalized_snapshot[constraint_id] = {
            "values": _json_safe(normalized_values),
            "units": _json_safe(normalized_units),
            "unit_conversions": per_constraint,
        }
        blocked_by_units = any(finding.category == "unit_consistency" and finding.status in {"unavailable", "inconsistent"} for finding in unit_findings)
        invalid_assumptions = set(request.metadata.get("invalid_assumptions", ()))
        if constraint_id in invalid_assumptions:
            assumption_results.append(
                AssumptionResult(
                    constraint_id,
                    "invalid_assumption",
                    constraint.assumptions,
                    reason_code="declared_invalid_by_request",
                )
            )
            findings.append(
                _extra_finding(
                    constraint_id,
                    status="assumption_violation",
                    severity=constraint.severity_on_violation,
                    message="A required scientific assumption was declared invalid by the request.",
                    remediation_code="document_or_restrict_assumption",
                    category="applicability",
                    claim_impact=constraint.claim_impact,
                )
            )
            continue
        assumption_results.append(AssumptionResult(constraint_id, "satisfied_or_not_required", constraint.assumptions))
        if blocked_by_units:
            continue
        try:
            evaluated = evaluate_constraint(
                constraint,
                normalized_values,
                units=normalized_units,
                metadata=dict(request.metadata),
                evaluator_registry=context.evaluator_registry,
                unit_registry=context.unit_registry,
            )
            findings.extend(evaluated)
            scientific_recomputed = True
        except Exception as exc:  # noqa: BLE001 - isolate registered evaluator failures.
            findings.append(
                _extra_finding(
                    constraint_id,
                    status="unavailable",
                    severity="warning",
                    message=f"Registered evaluator failed safely: {type(exc).__name__}.",
                    remediation_code="inspect_registered_evaluator",
                    category="execution_failure",
                )
            )
            warnings.append(f"evaluator_failed:{constraint_id}:{type(exc).__name__}")

    if not errors:
        derived_outputs, derived_findings = _derive_outputs(request, values, units, context.unit_registry)
        findings.extend(derived_findings)
        scientific_recomputed = scientific_recomputed or bool(derived_outputs)
    else:
        derived_outputs = {}

    evidence_refs = _available_scientific_evidence(findings, derived_outputs)
    claim_evaluations = _evaluate_claims(request, findings, derived_outputs)
    constraints_for_graph = [
        context.constraint_registry.get(item).to_dict()
        for item in request.constraint_ids
        if item in {constraint.constraint_id for constraint in context.constraint_registry.list_constraints()}
    ]
    graph = build_scientific_execution_evidence_graph(
        execution_id=request.execution_id,
        knowledge_pack=pack.to_dict(),
        constraints=constraints_for_graph,
        inputs=[item.to_dict() for item in request.inputs],
        findings=[finding.to_dict() for finding in findings],
        claim_evaluations=[claim.to_dict() for claim in claim_evaluations],
        trust_policy_id="scientific_bounded_execution",
    )
    completed_at = utc_now_iso()
    overall = _overall_status(findings, errors)
    result = ScientificExecutionResult(
        execution_id=request.execution_id,
        knowledge_pack_id=request.knowledge_pack_id,
        overall_status=overall,
        applicability_status=applicability_status,
        finding_count=len(findings),
        blocker_count=sum(1 for finding in findings if finding.severity == "blocker"),
        findings=tuple(findings),
        normalized_inputs=normalized_snapshot,
        unit_conversions=tuple(conversions),
        assumption_results=tuple(assumption_results),
        claim_evaluations=claim_evaluations,
        evidence_refs=evidence_refs,
        warnings=tuple(warnings),
        errors=tuple(errors),
        scientific_recomputation_performed=scientific_recomputed,
        raw_data_read=False,
        model_training_performed=False,
        request_hash=request.request_hash(),
        code_commit=context.code_commit,
        registry_schema_version=context.registry_version,
        started_at=started_at,
        completed_at=completed_at,
        derived_outputs=derived_outputs,
        execution_manifest={
            "execution_id": request.execution_id,
            "knowledge_pack_id": request.knowledge_pack_id,
            "request_hash": request.request_hash(),
            "code_commit": context.code_commit,
            "evidence_graph_node_count": len(graph.get("nodes", [])),
            "evidence_graph_edge_count": len(graph.get("edges", [])),
        },
    )
    assert_no_sensitive_strings(result.to_dict())
    return result


def execute_scientific_config(
    config: Mapping[str, Any],
    *,
    repo_root: str | Path = ".",
    registry_path: str = DEFAULT_REGISTRY_PATH,
    persist: bool | None = None,
) -> ScientificExecutionResult:
    request = ScientificExecutionRequest.from_config(config)
    if persist is not None:
        request = ScientificExecutionRequest(
            execution_id=request.execution_id,
            knowledge_pack_id=request.knowledge_pack_id,
            constraint_ids=request.constraint_ids,
            inputs=request.inputs,
            metadata=request.metadata,
            requested_claim_ids=request.requested_claim_ids,
            persist_findings=bool(persist),
            run_id=request.run_id,
            strict_mode=request.strict_mode,
            output_policy=request.output_policy,
        )
    context = ScientificExecutionContext.build(repo_root=repo_root, registry_path=registry_path)
    result = execute_scientific_request(request, context=context)
    if request.persist_findings:
        persist_scientific_execution(request, result, repo_root=repo_root, registry_path=registry_path)
    return result


def _scientific_tables_script() -> str:
    return """
    CREATE TABLE IF NOT EXISTS scientific_executions (
        execution_id TEXT PRIMARY KEY,
        run_id TEXT,
        knowledge_pack_id TEXT NOT NULL,
        request_hash TEXT NOT NULL,
        status TEXT NOT NULL,
        started_at TEXT NOT NULL,
        completed_at TEXT NOT NULL,
        finding_count INTEGER NOT NULL,
        blocker_count INTEGER NOT NULL,
        rule_registry_version INTEGER NOT NULL,
        code_commit TEXT NOT NULL,
        knowledge_pack_version TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS scientific_findings (
        finding_id TEXT PRIMARY KEY,
        execution_id TEXT NOT NULL REFERENCES scientific_executions(execution_id) ON DELETE CASCADE,
        constraint_id TEXT NOT NULL,
        evaluator_id TEXT,
        status TEXT NOT NULL,
        severity TEXT NOT NULL,
        message_code TEXT NOT NULL,
        claim_impact TEXT NOT NULL,
        normalized_values_json TEXT NOT NULL,
        assumptions_json TEXT NOT NULL,
        evidence_refs_json TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS scientific_claim_evaluations (
        claim_eval_id TEXT PRIMARY KEY,
        execution_id TEXT NOT NULL REFERENCES scientific_executions(execution_id) ON DELETE CASCADE,
        claim_id TEXT NOT NULL,
        status TEXT NOT NULL,
        support_refs_json TEXT NOT NULL,
        conflict_refs_json TEXT NOT NULL,
        reason_code TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS scientific_unit_conversions (
        conversion_id TEXT PRIMARY KEY,
        execution_id TEXT NOT NULL REFERENCES scientific_executions(execution_id) ON DELETE CASCADE,
        variable_id TEXT NOT NULL,
        original_value TEXT,
        original_unit TEXT,
        normalized_value TEXT,
        normalized_unit TEXT,
        conversion_status TEXT NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_science_findings_execution ON scientific_findings(execution_id, severity, status);
    CREATE INDEX IF NOT EXISTS idx_science_claims_execution ON scientific_claim_evaluations(execution_id, claim_id);
    """


def ensure_scientific_registry_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(_scientific_tables_script())


def persist_scientific_execution(
    request: ScientificExecutionRequest,
    result: ScientificExecutionResult,
    *,
    repo_root: str | Path = ".",
    registry_path: str = DEFAULT_REGISTRY_PATH,
) -> dict[str, Any]:
    assert_no_sensitive_strings(result.to_dict())
    path = initialize_registry(repo_root, registry_path)
    request_hash = result.request_hash
    pack_version = "unknown"
    try:
        pack_version = build_default_domain_knowledge_registry().get(request.knowledge_pack_id).version
    except KeyError:
        pass
    with _connect(path) as connection:
        ensure_scientific_registry_schema(connection)
        existing = connection.execute(
            "SELECT request_hash, rule_registry_version, code_commit, knowledge_pack_version FROM scientific_executions WHERE execution_id = ?",
            (request.execution_id,),
        ).fetchone()
        if existing is not None:
            if (
                existing["request_hash"] == request_hash
                and int(existing["rule_registry_version"]) == REGISTRY_SCHEMA_VERSION
                and existing["code_commit"] == result.code_commit
                and existing["knowledge_pack_version"] == pack_version
            ):
                return {"status": "idempotent", "execution_id": request.execution_id}
            raise RegistryConflictError(f"scientific execution already exists with different metadata: {request.execution_id}")
        with connection:
            connection.execute(
                """
                INSERT INTO scientific_executions(
                    execution_id, run_id, knowledge_pack_id, request_hash, status,
                    started_at, completed_at, finding_count, blocker_count,
                    rule_registry_version, code_commit, knowledge_pack_version
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.execution_id,
                    request.run_id,
                    result.knowledge_pack_id,
                    request_hash,
                    result.overall_status,
                    result.started_at,
                    result.completed_at,
                    result.finding_count,
                    result.blocker_count,
                    REGISTRY_SCHEMA_VERSION,
                    result.code_commit,
                    pack_version,
                ),
            )
            normalized_json = json.dumps(result.normalized_inputs, sort_keys=True)
            assumptions_json = json.dumps([item.to_dict() for item in result.assumption_results], sort_keys=True)
            for finding in result.findings:
                connection.execute(
                    """
                    INSERT INTO scientific_findings(
                        finding_id, execution_id, constraint_id, evaluator_id, status, severity,
                        message_code, claim_impact, normalized_values_json, assumptions_json,
                        evidence_refs_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        f"{result.execution_id}:{finding.finding_id}",
                        result.execution_id,
                        finding.constraint_id,
                        _evaluator_for_constraint(finding.constraint_id),
                        finding.status,
                        finding.severity,
                        finding.remediation_code,
                        finding.claim_impact,
                        normalized_json,
                        assumptions_json,
                        json.dumps(list(finding.evidence_refs), sort_keys=True),
                    ),
                )
            for claim in result.claim_evaluations:
                connection.execute(
                    """
                    INSERT INTO scientific_claim_evaluations(
                        claim_eval_id, execution_id, claim_id, status, support_refs_json,
                        conflict_refs_json, reason_code
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        f"{result.execution_id}:{claim.claim_id}",
                        result.execution_id,
                        claim.claim_id,
                        claim.status,
                        json.dumps(list(claim.supporting_evidence), sort_keys=True),
                        json.dumps(list(claim.conflicting_evidence), sort_keys=True),
                        claim.reason_code,
                    ),
                )
            for index, conversion in enumerate(result.unit_conversions):
                connection.execute(
                    """
                    INSERT INTO scientific_unit_conversions(
                        conversion_id, execution_id, variable_id, original_value, original_unit,
                        normalized_value, normalized_unit, conversion_status
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        f"{result.execution_id}:{index}:{conversion.conversion_id}",
                        result.execution_id,
                        conversion.variable_id,
                        json.dumps(conversion.original_value, sort_keys=True),
                        conversion.original_unit,
                        json.dumps(conversion.normalized_value, sort_keys=True),
                        conversion.normalized_unit,
                        conversion.conversion_status,
                    ),
                )
    return {
        "status": "stored",
        "execution_id": request.execution_id,
        "finding_count": result.finding_count,
        "claim_evaluation_count": len(result.claim_evaluations),
        "unit_conversion_count": len(result.unit_conversions),
    }


def _evaluator_for_constraint(constraint_id: str) -> str | None:
    try:
        return build_default_scientific_constraint_registry().get(constraint_id).evaluator_id
    except KeyError:
        return None


def get_scientific_execution(
    execution_id: str,
    *,
    repo_root: str | Path = ".",
    registry_path: str = DEFAULT_REGISTRY_PATH,
) -> dict[str, Any]:
    path = initialize_registry(repo_root, registry_path)
    with _connect(path) as connection:
        ensure_scientific_registry_schema(connection)
        row = connection.execute("SELECT * FROM scientific_executions WHERE execution_id = ?", (execution_id,)).fetchone()
        if row is None:
            raise KeyError(f"unknown scientific execution_id: {execution_id}")
        findings = [dict(item) for item in connection.execute("SELECT * FROM scientific_findings WHERE execution_id = ? ORDER BY severity, constraint_id, finding_id", (execution_id,))]
        claims = [dict(item) for item in connection.execute("SELECT * FROM scientific_claim_evaluations WHERE execution_id = ? ORDER BY claim_id", (execution_id,))]
        conversions = [dict(item) for item in connection.execute("SELECT * FROM scientific_unit_conversions WHERE execution_id = ? ORDER BY variable_id, conversion_id", (execution_id,))]
    return {"execution": dict(row), "findings": findings, "claim_evaluations": claims, "unit_conversions": conversions}


def list_scientific_findings(
    *,
    execution_id: str | None = None,
    severity: str | None = None,
    repo_root: str | Path = ".",
    registry_path: str = DEFAULT_REGISTRY_PATH,
) -> list[dict[str, Any]]:
    path = initialize_registry(repo_root, registry_path)
    query = "SELECT * FROM scientific_findings"
    clauses: list[str] = []
    params: list[Any] = []
    if execution_id:
        clauses.append("execution_id = ?")
        params.append(execution_id)
    if severity:
        clauses.append("severity = ?")
        params.append(severity)
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY execution_id, severity, constraint_id, finding_id"
    with _connect(path) as connection:
        ensure_scientific_registry_schema(connection)
        return [dict(row) for row in connection.execute(query, tuple(params))]


def get_scientific_claim_evaluation(
    execution_id: str,
    claim_id: str,
    *,
    repo_root: str | Path = ".",
    registry_path: str = DEFAULT_REGISTRY_PATH,
) -> dict[str, Any]:
    payload = get_scientific_execution(execution_id, repo_root=repo_root, registry_path=registry_path)
    for claim in payload["claim_evaluations"]:
        if claim["claim_id"] == claim_id:
            return claim
    return {
        "execution_id": execution_id,
        "claim_id": claim_id,
        "status": "unsupported",
        "support_refs_json": "[]",
        "conflict_refs_json": json.dumps([f"missing:claim_evaluation:{claim_id}"]),
        "reason_code": "claim_not_requested",
    }


def export_scientific_findings(
    *,
    repo_root: str | Path = ".",
    registry_path: str = DEFAULT_REGISTRY_PATH,
    output: str = "outputs/platform_science/scientific_findings_export.json",
    overwrite: bool = False,
) -> dict[str, Any]:
    validate_relative_path(output)
    normalized = output.replace("\\", "/")
    if not normalized.startswith("outputs/platform_science/"):
        raise RegistryPathError("scientific findings export must be under outputs/platform_science/")
    root = Path(repo_root).resolve()
    target = (root / output).resolve()
    if root != target and root not in target.parents:
        raise RegistryPathError("scientific findings export must stay inside repository root")
    if target.exists() and not overwrite:
        raise FileExistsError(f"export already exists: {target.relative_to(root).as_posix()}")
    payload = {
        "schema_version": SCIENTIFIC_EXECUTION_OUTPUT_SCHEMA_VERSION,
        "exported_at": utc_now_iso(),
        "findings": list_scientific_findings(repo_root=root, registry_path=registry_path),
    }
    assert_no_sensitive_strings(payload)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(f".{target.name}.tmp")
    try:
        temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temp.replace(target)
    finally:
        if temp.exists():
            temp.unlink()
    return {"status": "exported", "output": target.relative_to(root).as_posix(), "finding_count": len(payload["findings"])}


def validate_scientific_registry(
    *,
    repo_root: str | Path = ".",
    registry_path: str = DEFAULT_REGISTRY_PATH,
) -> dict[str, Any]:
    errors: list[str] = []
    path = initialize_registry(repo_root, registry_path)
    with _connect(path) as connection:
        ensure_scientific_registry_schema(connection)
        fk_rows = connection.execute("PRAGMA foreign_key_check").fetchall()
        errors.extend(f"foreign_key:{dict(row)}" for row in fk_rows)
        orphan_claims = connection.execute(
            """
            SELECT COUNT(*) AS count FROM scientific_claim_evaluations c
            LEFT JOIN scientific_executions e ON e.execution_id = c.execution_id
            WHERE e.execution_id IS NULL
            """
        ).fetchone()["count"]
        if orphan_claims:
            errors.append(f"orphan scientific claim evaluations: {orphan_claims}")
        orphan_trust = connection.execute(
            """
            SELECT COUNT(*) AS count FROM scientific_trust_evaluations t
            LEFT JOIN scientific_executions e ON e.execution_id = t.execution_id
            WHERE e.execution_id IS NULL
            """
        ).fetchone()["count"]
        if orphan_trust:
            errors.append(f"orphan scientific trust evaluations: {orphan_trust}")
        for row in connection.execute("SELECT normalized_values_json, assumptions_json, evidence_refs_json FROM scientific_findings"):
            for field in ("normalized_values_json", "assumptions_json", "evidence_refs_json"):
                try:
                    assert_no_sensitive_strings(json.loads(row[field]))
                except (json.JSONDecodeError, ValueError) as exc:
                    errors.append(f"{field}:{exc}")
        for table, fields in {
            "scientific_constraint_eligibility": ("reason_codes_json", "remediation_codes_json"),
            "scientific_feature_eligibility": ("reason_codes_json",),
            "scientific_claim_boundaries": ("support_refs_json", "conflict_refs_json"),
        }.items():
            for row in connection.execute(f"SELECT {', '.join(fields)} FROM {table}"):
                for field in fields:
                    try:
                        assert_no_sensitive_strings(json.loads(row[field]))
                    except (json.JSONDecodeError, ValueError) as exc:
                        errors.append(f"{table}.{field}:{exc}")
    return {"valid": not errors, "errors": errors, "schema_version": REGISTRY_SCHEMA_VERSION}


def write_scientific_outputs(
    result: ScientificExecutionResult,
    *,
    repo_root: str | Path = ".",
    output_dir: str | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    relative_dir = output_dir or f"{LOCAL_OUTPUT_ROOT}/{result.execution_id}"
    validate_relative_path(relative_dir)
    normalized = relative_dir.replace("\\", "/")
    if not normalized.startswith(f"{LOCAL_OUTPUT_ROOT}/"):
        raise RegistryPathError(f"scientific outputs must be under {LOCAL_OUTPUT_ROOT}/")
    root = Path(repo_root).resolve()
    target_dir = (root / relative_dir).resolve()
    if root != target_dir and root not in target_dir.parents:
        raise RegistryPathError("scientific output directory must stay inside repository root")
    target_dir.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "scientific_result.json": json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n",
        "scientific_report.md": result.to_markdown(),
        "execution_manifest.json": json.dumps(result.execution_manifest, indent=2, sort_keys=True) + "\n",
    }
    written: dict[str, str] = {}
    checksums: dict[str, str] = {}
    for name, content in artifacts.items():
        target = target_dir / name
        if target.exists() and not overwrite:
            raise FileExistsError(f"scientific output already exists: {target.relative_to(root).as_posix()}")
        assert_no_sensitive_strings(content)
        temp = target.with_name(f".{target.name}.tmp")
        try:
            temp.write_text(content, encoding="utf-8")
            temp.replace(target)
        finally:
            if temp.exists():
                temp.unlink()
        rel = target.relative_to(root).as_posix()
        written[name] = rel
        checksums[name] = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return {"status": "written", "output_dir": target_dir.relative_to(root).as_posix(), "files": written, "checksums": checksums}


def validate_scientific_result_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    required = {
        "execution_id",
        "knowledge_pack_id",
        "overall_status",
        "findings",
        "unit_conversions",
        "claim_evaluations",
        "scientific_recomputation_performed",
        "raw_data_read",
        "model_training_performed",
    }
    missing = sorted(required - set(payload))
    errors.extend(f"missing:{field}" for field in missing)
    if payload.get("overall_status") not in RESULT_STATUSES:
        errors.append("invalid:overall_status")
    if payload.get("raw_data_read") is not False:
        errors.append("raw_data_read must be false")
    if payload.get("model_training_performed") is not False:
        errors.append("model_training_performed must be false")
    try:
        assert_no_sensitive_strings(payload)
    except ValueError as exc:
        errors.append(str(exc))
    return {"valid": not errors, "errors": errors}
