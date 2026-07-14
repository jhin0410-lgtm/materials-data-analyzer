"""Code-registered scientific evaluators.

Evaluators operate on explicit JSON-like metadata supplied by the caller. They
do not read raw data files, import user modules, parse equations, or execute
user-provided code.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from .scientific_constraints import ScientificConstraint, ScientificFinding
from .units import UnitRegistry, build_default_unit_registry


EvaluatorCallable = Callable[[ScientificConstraint, dict[str, Any], dict[str, str], dict[str, Any], UnitRegistry], tuple[ScientificFinding, ...]]


@dataclass(frozen=True)
class EvaluatorMetadata:
    evaluator_id: str
    description: str
    callable: EvaluatorCallable
    supported_roles: tuple[str, ...] = ("range_check", "consistency_check", "unit_check")
    max_input_items: int = 1000
    supported_scalar_types: tuple[str, ...] = ("int", "float")
    output_schema: dict[str, object] = field(default_factory=dict)
    numerical_tolerance: float = 1e-9
    failure_mode: str = "finding_unavailable"

    def to_dict(self) -> dict[str, object]:
        return {
            "evaluator_id": self.evaluator_id,
            "description": self.description,
            "supported_roles": list(self.supported_roles),
            "max_input_items": self.max_input_items,
            "supported_scalar_types": list(self.supported_scalar_types),
            "output_schema": dict(self.output_schema),
            "numerical_tolerance": self.numerical_tolerance,
            "failure_mode": self.failure_mode,
        }


@dataclass
class ScientificEvaluatorRegistry:
    _evaluators: dict[str, EvaluatorMetadata] = field(default_factory=dict)

    def register(self, evaluator: EvaluatorMetadata) -> None:
        if evaluator.evaluator_id in self._evaluators:
            raise ValueError(f"duplicate evaluator_id: {evaluator.evaluator_id}")
        if evaluator.callable.__module__ != __name__:
            raise ValueError("scientific evaluator callables must be code-registered in scientific_evaluators")
        self._evaluators[evaluator.evaluator_id] = evaluator

    def get(self, evaluator_id: str) -> EvaluatorMetadata:
        try:
            return self._evaluators[evaluator_id]
        except KeyError as exc:
            raise KeyError(f"unknown evaluator_id: {evaluator_id}") from exc

    def list_evaluators(self) -> list[EvaluatorMetadata]:
        return [self._evaluators[key] for key in sorted(self._evaluators)]

    def snapshot(self) -> list[dict[str, object]]:
        return [evaluator.to_dict() for evaluator in self.list_evaluators()]


def _finding_id(constraint_id: str, status: str, remediation_code: str, message: str) -> str:
    return hashlib.sha256(f"{constraint_id}:{status}:{remediation_code}:{message}".encode("utf-8")).hexdigest()[:24]


def _finding(
    constraint: ScientificConstraint,
    *,
    status: str,
    severity: str,
    message: str,
    remediation_code: str,
    category: str = "scientific_consistency",
    claim_impact: str | None = None,
    evidence_refs: tuple[str, ...] = (),
) -> ScientificFinding:
    return ScientificFinding(
        finding_id=_finding_id(constraint.constraint_id, status, remediation_code, message),
        constraint_id=constraint.constraint_id,
        status=status,
        severity=severity,
        message=message,
        remediation_code=remediation_code,
        category=category,
        claim_impact=claim_impact or constraint.claim_impact,
        evidence_refs=evidence_refs,
    )


def _values_for(name: str, values: dict[str, Any]) -> list[float] | None:
    if name not in values:
        return None
    item = values[name]
    if isinstance(item, dict):
        item = item.get("values", item.get("value"))
    if isinstance(item, (str, bytes)) or item is None:
        return None
    if isinstance(item, Iterable):
        try:
            return [float(value) for value in item]
        except (TypeError, ValueError):
            return None
    try:
        return [float(item)]
    except (TypeError, ValueError):
        return None


def _required_value(constraint: ScientificConstraint, values: dict[str, Any]) -> tuple[str | None, list[float] | None, ScientificFinding | None]:
    for variable in constraint.required_variables:
        found = _values_for(variable.name, values)
        if found is None:
            return (
                variable.name,
                None,
                _finding(
                    constraint,
                    status="unavailable",
                    severity="warning",
                    message=f"Required variable {variable.name} is missing or nonnumeric.",
                    remediation_code="provide_variable_metadata",
                    category="applicability",
                    claim_impact="narrow_claim",
                    evidence_refs=(f"variable:{variable.name}",),
                ),
            )
        return variable.name, found, None
    return None, None, _finding(
        constraint,
        status="insufficient_metadata",
        severity="warning",
        message="No required variable is declared for this evaluator.",
        remediation_code="register_required_variable",
        category="applicability",
    )


def _unit_for(variable: str, values: dict[str, Any], units: dict[str, str]) -> str | None:
    if variable in units:
        return units[variable]
    item = values.get(variable)
    if isinstance(item, dict) and isinstance(item.get("unit"), str):
        return str(item["unit"])
    return None


def _check_expected_units(
    constraint: ScientificConstraint,
    values: dict[str, Any],
    units: dict[str, str],
    unit_registry: UnitRegistry,
) -> list[ScientificFinding]:
    findings: list[ScientificFinding] = []
    for variable, expected_unit in sorted(constraint.expected_units.items()):
        supplied_unit = _unit_for(variable, values, units)
        if supplied_unit is None:
            findings.append(
                _finding(
                    constraint,
                    status="unavailable",
                    severity="warning",
                    message=f"Unit metadata for {variable} is missing; {expected_unit} expected.",
                    remediation_code="provide_unit_metadata",
                    category="unit_consistency",
                    claim_impact="narrow_claim",
                    evidence_refs=(f"variable:{variable}",),
                )
            )
            continue
        try:
            compatible = unit_registry.compatible(supplied_unit, expected_unit)
        except KeyError:
            findings.append(
                _finding(
                    constraint,
                    status="unavailable",
                    severity="warning",
                    message=f"Unsupported unit metadata for {variable}: {supplied_unit}.",
                    remediation_code="register_or_correct_unit",
                    category="unit_consistency",
                    claim_impact="narrow_claim",
                    evidence_refs=(f"unit:{supplied_unit}",),
                )
            )
            continue
        if not compatible:
            findings.append(
                _finding(
                    constraint,
                    status="inconsistent",
                    severity=constraint.severity_on_violation,
                    message=f"Unit {supplied_unit} for {variable} is incompatible with expected {expected_unit}.",
                    remediation_code="convert_to_compatible_unit",
                    category="unit_consistency",
                    claim_impact=constraint.claim_impact,
                    evidence_refs=(f"variable:{variable}",),
                )
            )
    return findings


def _all_finite(values: list[float]) -> bool:
    return all(math.isfinite(value) for value in values)


def check_finite(constraint: ScientificConstraint, values: dict[str, Any], units: dict[str, str], metadata: dict[str, Any], unit_registry: UnitRegistry) -> tuple[ScientificFinding, ...]:
    del units, metadata, unit_registry
    _, found, missing = _required_value(constraint, values)
    if missing:
        return (missing,)
    assert found is not None
    if _all_finite(found):
        return (_finding(constraint, status="consistent", severity="info", message="All supplied values are finite.", remediation_code="none"),)
    return (
        _finding(
            constraint,
            status="inconsistent",
            severity=constraint.severity_on_violation,
            message="At least one supplied value is not finite.",
            remediation_code="remove_or_impute_nonfinite_values",
        ),
    )


def check_non_negative(constraint: ScientificConstraint, values: dict[str, Any], units: dict[str, str], metadata: dict[str, Any], unit_registry: UnitRegistry) -> tuple[ScientificFinding, ...]:
    del units, metadata, unit_registry
    _, found, missing = _required_value(constraint, values)
    if missing:
        return (missing,)
    assert found is not None
    tolerance = float(constraint.tolerance_policy.get("lower_tolerance", 0.0))
    if min(found) >= -abs(tolerance):
        status = "conditionally_consistent" if min(found) < 0 else "consistent"
        return (_finding(constraint, status=status, severity="info", message="Values satisfy the non-negative bound within tolerance.", remediation_code="none"),)
    return (
        _finding(
            constraint,
            status="inconsistent",
            severity=constraint.severity_on_violation,
            message="A value is below the allowed non-negative bound.",
            remediation_code="inspect_negative_values",
        ),
    )


def check_positive(constraint: ScientificConstraint, values: dict[str, Any], units: dict[str, str], metadata: dict[str, Any], unit_registry: UnitRegistry) -> tuple[ScientificFinding, ...]:
    del units, metadata, unit_registry
    _, found, missing = _required_value(constraint, values)
    if missing:
        return (missing,)
    assert found is not None
    if min(found) > 0:
        return (_finding(constraint, status="consistent", severity="info", message="Values are strictly positive.", remediation_code="none"),)
    return (
        _finding(
            constraint,
            status="outside_validity_range",
            severity=constraint.severity_on_violation,
            message="A value is not strictly positive.",
            remediation_code="provide_positive_values",
        ),
    )


def check_closed_interval(constraint: ScientificConstraint, values: dict[str, Any], units: dict[str, str], metadata: dict[str, Any], unit_registry: UnitRegistry) -> tuple[ScientificFinding, ...]:
    del units, metadata, unit_registry
    _, found, missing = _required_value(constraint, values)
    if missing:
        return (missing,)
    assert found is not None
    lower = constraint.tolerance_policy.get("min")
    upper = constraint.tolerance_policy.get("max")
    tolerance = float(constraint.tolerance_policy.get("tolerance", 0.0))
    low_ok = True if lower is None else min(found) >= float(lower) - abs(tolerance)
    high_ok = True if upper is None else max(found) <= float(upper) + abs(tolerance)
    if low_ok and high_ok:
        return (_finding(constraint, status="consistent", severity="info", message="Values are inside the configured closed interval.", remediation_code="none"),)
    return (
        _finding(
            constraint,
            status="outside_validity_range",
            severity=constraint.severity_on_violation,
            message="At least one value is outside the configured closed interval.",
            remediation_code="inspect_range_or_units",
        ),
    )


def check_sum_to_target(constraint: ScientificConstraint, values: dict[str, Any], units: dict[str, str], metadata: dict[str, Any], unit_registry: UnitRegistry) -> tuple[ScientificFinding, ...]:
    del units, metadata, unit_registry
    _, found, missing = _required_value(constraint, values)
    if missing:
        return (missing,)
    assert found is not None
    target = float(constraint.tolerance_policy.get("target", 1.0))
    tolerance = float(constraint.tolerance_policy.get("tolerance", 1e-6))
    total = sum(found)
    if abs(total - target) <= tolerance:
        return (_finding(constraint, status="consistent", severity="info", message=f"Values sum to {total:.12g}, within tolerance.", remediation_code="none"),)
    return (
        _finding(
            constraint,
            status="inconsistent",
            severity=constraint.severity_on_violation,
            message=f"Values sum to {total:.12g}, outside target {target:.12g} +/- {tolerance:.12g}.",
            remediation_code="normalize_or_verify_composition_fractions",
        ),
    )


def check_unit_compatibility(constraint: ScientificConstraint, values: dict[str, Any], units: dict[str, str], metadata: dict[str, Any], unit_registry: UnitRegistry) -> tuple[ScientificFinding, ...]:
    del metadata
    findings = _check_expected_units(constraint, values, units, unit_registry)
    if findings:
        return tuple(findings)
    return (
        _finding(
            constraint,
            status="consistent",
            severity="info",
            message="Declared units are compatible with expected units.",
            remediation_code="none",
            category="unit_consistency",
        ),
    )


def check_monotonic_non_decreasing(constraint: ScientificConstraint, values: dict[str, Any], units: dict[str, str], metadata: dict[str, Any], unit_registry: UnitRegistry) -> tuple[ScientificFinding, ...]:
    del units, metadata, unit_registry
    _, found, missing = _required_value(constraint, values)
    if missing:
        return (missing,)
    assert found is not None
    if all(left <= right for left, right in zip(found, found[1:])):
        return (_finding(constraint, status="consistent", severity="info", message="Values are monotonic non-decreasing.", remediation_code="none"),)
    return (_finding(constraint, status="inconsistent", severity=constraint.severity_on_violation, message="Values are not monotonic non-decreasing.", remediation_code="inspect_temporal_order"),)


def check_monotonic_non_increasing(constraint: ScientificConstraint, values: dict[str, Any], units: dict[str, str], metadata: dict[str, Any], unit_registry: UnitRegistry) -> tuple[ScientificFinding, ...]:
    del units, metadata, unit_registry
    _, found, missing = _required_value(constraint, values)
    if missing:
        return (missing,)
    assert found is not None
    if all(left >= right for left, right in zip(found, found[1:])):
        return (_finding(constraint, status="consistent", severity="info", message="Values are monotonic non-increasing.", remediation_code="none"),)
    return (_finding(constraint, status="inconsistent", severity=constraint.severity_on_violation, message="Values are not monotonic non-increasing.", remediation_code="inspect_temporal_order"),)


def check_ratio_range(constraint: ScientificConstraint, values: dict[str, Any], units: dict[str, str], metadata: dict[str, Any], unit_registry: UnitRegistry) -> tuple[ScientificFinding, ...]:
    return check_closed_interval(constraint, values, units, metadata, unit_registry)


def check_fraction_bounds(constraint: ScientificConstraint, values: dict[str, Any], units: dict[str, str], metadata: dict[str, Any], unit_registry: UnitRegistry) -> tuple[ScientificFinding, ...]:
    del units, metadata, unit_registry
    _, found, missing = _required_value(constraint, values)
    if missing:
        return (missing,)
    assert found is not None
    lower = float(constraint.tolerance_policy.get("min", 0.0))
    upper = float(constraint.tolerance_policy.get("max", 1.0))
    tolerance = float(constraint.tolerance_policy.get("tolerance", 1e-9))
    if min(found) >= lower - tolerance and max(found) <= upper + tolerance:
        return (_finding(constraint, status="consistent", severity="info", message="Fraction values are inside [0, 1] within tolerance.", remediation_code="none"),)
    return (_finding(constraint, status="outside_validity_range", severity=constraint.severity_on_violation, message="Fraction values are outside [0, 1].", remediation_code="inspect_fraction_bounds"),)


def check_arrhenius_temperature_domain(constraint: ScientificConstraint, values: dict[str, Any], units: dict[str, str], metadata: dict[str, Any], unit_registry: UnitRegistry) -> tuple[ScientificFinding, ...]:
    del metadata
    variable, found, missing = _required_value(constraint, values)
    if missing:
        return (missing,)
    assert variable is not None and found is not None
    supplied_unit = _unit_for(variable, values, units)
    if supplied_unit is None:
        return (
            _finding(
                constraint,
                status="unavailable",
                severity="warning",
                message="Temperature unit metadata is missing; Kelvin-domain check is unavailable.",
                remediation_code="provide_unit_metadata",
                category="unit_consistency",
            ),
        )
    try:
        converted = [unit_registry.convert_value(value, supplied_unit, "K") for value in found]
    except (KeyError, ValueError):
        return (
            _finding(
                constraint,
                status="unavailable",
                severity="warning",
                message=f"Temperature unit {supplied_unit} is unsupported or incompatible with Kelvin.",
                remediation_code="convert_to_kelvin",
                category="unit_consistency",
            ),
        )
    if min(converted) > 0:
        return (
            _finding(
                constraint,
                status="conditionally_consistent",
                severity="info",
                message="Temperatures are physically positive in Kelvin; Arrhenius mechanism still requires domain evidence.",
                remediation_code="document_arrhenius_assumptions",
                category="applicability",
                claim_impact="narrow_claim",
            ),
        )
    return (
        _finding(
            constraint,
            status="outside_validity_range",
            severity=constraint.severity_on_violation,
            message="Temperature is not physically positive in Kelvin.",
            remediation_code="convert_to_kelvin",
            category="applicability",
        ),
    )


def check_charge_balance_metadata(constraint: ScientificConstraint, values: dict[str, Any], units: dict[str, str], metadata: dict[str, Any], unit_registry: UnitRegistry) -> tuple[ScientificFinding, ...]:
    del values, units, unit_registry
    if metadata.get("oxidation_state_metadata_available") is True:
        return (_finding(constraint, status="conditionally_consistent", severity="info", message="Oxidation-state metadata is available; charge balance can be audited separately.", remediation_code="none", category="applicability"),)
    return (_finding(constraint, status="insufficient_metadata", severity="warning", message="Oxidation-state metadata is unavailable; charge-balance claim is unsupported.", remediation_code="provide_oxidation_state_metadata", category="applicability"),)


def check_bragg_geometry(constraint: ScientificConstraint, values: dict[str, Any], units: dict[str, str], metadata: dict[str, Any], unit_registry: UnitRegistry) -> tuple[ScientificFinding, ...]:
    del metadata
    unit_findings = _check_expected_units(constraint, values, units, unit_registry)
    if any(finding.status in {"inconsistent", "unavailable"} for finding in unit_findings):
        return tuple(unit_findings)
    two_theta = _values_for("two_theta", values)
    wavelength = _values_for("wavelength", values)
    if two_theta is None or wavelength is None:
        return (_finding(constraint, status="unavailable", severity="warning", message="two_theta and wavelength are required for Bragg geometry checks.", remediation_code="provide_xrd_geometry_metadata", category="applicability"),)
    two_theta_unit = _unit_for("two_theta", values, units) or constraint.expected_units.get("two_theta", "degree")
    try:
        two_theta_degrees = [unit_registry.convert_value(value, two_theta_unit, "degree") for value in two_theta]
    except (KeyError, ValueError):
        return (_finding(constraint, status="unavailable", severity="warning", message="two_theta unit cannot be converted to degrees.", remediation_code="provide_angle_unit_metadata", category="unit_consistency"),)
    if min(two_theta_degrees) <= 0 or max(two_theta_degrees) >= 180:
        return (_finding(constraint, status="outside_validity_range", severity=constraint.severity_on_violation, message="two_theta must be between 0 and 180 degrees for the simple Bragg geometry check.", remediation_code="inspect_peak_positions", category="applicability"),)
    if min(wavelength) <= 0:
        return (_finding(constraint, status="outside_validity_range", severity=constraint.severity_on_violation, message="Wavelength must be positive.", remediation_code="provide_positive_wavelength", category="applicability"),)
    return (_finding(constraint, status="conditionally_consistent", severity="info", message="Bragg geometry metadata is in the supported range; phase identification is not inferred.", remediation_code="none", category="scientific_consistency"),)


def check_scherrer_preconditions(constraint: ScientificConstraint, values: dict[str, Any], units: dict[str, str], metadata: dict[str, Any], unit_registry: UnitRegistry) -> tuple[ScientificFinding, ...]:
    unit_findings = _check_expected_units(constraint, values, units, unit_registry)
    if any(finding.status in {"inconsistent", "unavailable"} for finding in unit_findings):
        return tuple(unit_findings)
    fwhm = _values_for("fwhm", values)
    shape_factor = _values_for("shape_factor", values)
    if fwhm is None:
        return (_finding(constraint, status="unavailable", severity="warning", message="FWHM metadata is required for Scherrer precondition checks.", remediation_code="provide_fwhm_metadata", category="applicability"),)
    if min(fwhm) <= 0:
        return (_finding(constraint, status="outside_validity_range", severity=constraint.severity_on_violation, message="FWHM must be positive for Scherrer precondition checks.", remediation_code="provide_positive_fwhm", category="applicability"),)
    if shape_factor is not None and not all(0.5 <= value <= 2.0 for value in shape_factor):
        return (_finding(constraint, status="outside_validity_range", severity=constraint.severity_on_violation, message="Shape factor is outside the conservative metadata range.", remediation_code="inspect_shape_factor", category="applicability"),)
    if metadata.get("instrumental_broadening_corrected") is not True:
        return (_finding(constraint, status="conditionally_consistent", severity="warning", message="Scherrer estimate is metadata-only/conditional unless instrumental broadening is corrected; do not claim particle size.", remediation_code="provide_instrumental_broadening_correction", category="physics_claim_boundary", claim_impact="narrow_claim"),)
    return (_finding(constraint, status="conditionally_consistent", severity="info", message="Scherrer preconditions are declared, but output remains a crystallite-size estimate only.", remediation_code="none", category="physics_claim_boundary"),)


def evaluate_constraint(
    constraint: ScientificConstraint,
    values: dict[str, Any],
    *,
    units: dict[str, str] | None = None,
    metadata: dict[str, Any] | None = None,
    evaluator_registry: ScientificEvaluatorRegistry | None = None,
    unit_registry: UnitRegistry | None = None,
) -> tuple[ScientificFinding, ...]:
    if constraint.evaluator_id is None or constraint.evaluation_role == "metadata_only":
        return (
            _finding(
                constraint,
                status="unavailable",
                severity="info",
                message="Constraint is metadata-only in this scaffold.",
                remediation_code="none",
                category="applicability",
                claim_impact="narrow_claim",
            ),
        )
    registry = evaluator_registry or build_default_evaluator_registry()
    evaluator = registry.get(constraint.evaluator_id)
    return evaluator.callable(constraint, values, units or {}, metadata or {}, unit_registry or build_default_unit_registry())


def build_default_evaluator_registry() -> ScientificEvaluatorRegistry:
    registry = ScientificEvaluatorRegistry()
    for evaluator_id, description, function in [
        ("check_non_negative", "Check values are non-negative within optional tolerance.", check_non_negative),
        ("check_positive", "Check values are strictly positive.", check_positive),
        ("check_closed_interval", "Check values against a configured closed interval.", check_closed_interval),
        ("check_sum_to_target", "Check numeric values sum to a configured target.", check_sum_to_target),
        ("check_finite", "Check values are finite.", check_finite),
        ("check_unit_compatibility", "Check supplied units are dimensionally compatible with expected units.", check_unit_compatibility),
        ("check_monotonic_non_decreasing", "Check sequence is monotonic non-decreasing.", check_monotonic_non_decreasing),
        ("check_monotonic_non_increasing", "Check sequence is monotonic non-increasing.", check_monotonic_non_increasing),
        ("check_ratio_range", "Check ratio values against a configured range.", check_ratio_range),
        ("check_bragg_geometry", "Check XRD Bragg geometry metadata ranges.", check_bragg_geometry),
        ("check_scherrer_preconditions", "Check Scherrer estimate metadata preconditions.", check_scherrer_preconditions),
        ("check_arrhenius_temperature_domain", "Check Kelvin-positive temperature metadata for Arrhenius applicability.", check_arrhenius_temperature_domain),
        ("check_fraction_bounds", "Check fraction values are in [0, 1] within tolerance.", check_fraction_bounds),
        ("check_charge_balance_metadata", "Check oxidation-state metadata availability for charge-balance claims.", check_charge_balance_metadata),
    ]:
        registry.register(EvaluatorMetadata(evaluator_id, description, function))
    return registry
