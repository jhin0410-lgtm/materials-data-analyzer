"""Scientific constraint metadata model.

Constraints are contracts. `equation_display` is human-readable documentation,
not executable code. Evaluation is allowed only through code-registered
`evaluator_id` values.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


SCIENTIFIC_CONSTRAINT_CATEGORIES = (
    "domain_constraint",
    "conservation_constraint",
    "dimensional_constraint",
    "monotonic_constraint",
    "constitutive_relation",
    "empirical_engineering_law",
    "thermodynamic_constraint",
    "kinetic_constraint",
    "geometric_structural_constraint",
    "measurement_constraint",
    "physics_inspired_feature",
    "hybrid_residual_model_contract",
)

SCIENTIFIC_EVALUATION_ROLES = (
    "metadata_only",
    "unit_check",
    "range_check",
    "consistency_check",
    "derived_feature",
    "model_constraint",
    "post_prediction_check",
)

EXECUTABLE_EVALUATION_ROLES = ("metadata_only", "unit_check", "range_check", "consistency_check")

SCIENTIFIC_CONSTRAINT_STATUSES = (
    "metadata_only",
    "validation_ready",
    "feature_candidate",
    "model_constraint_candidate",
    "deprecated_candidate",
)

SCIENTIFIC_FINDING_STATUSES = (
    "consistent",
    "inconsistent",
    "conditionally_consistent",
    "unavailable",
    "insufficient_metadata",
    "outside_validity_range",
    "assumption_violation",
)

SCIENTIFIC_FINDING_SEVERITIES = ("info", "warning", "error", "blocker")

SCIENTIFIC_APPLICABILITY_STATUSES = (
    "applicable",
    "conditionally_applicable",
    "unavailable_missing_variable",
    "unavailable_missing_unit",
    "unavailable_unknown_semantics",
    "invalid_assumption",
    "unsupported_evaluator",
)


@dataclass(frozen=True)
class VariableRequirement:
    name: str
    dimension: str | None = None
    expected_unit: str | None = None
    required: bool = True
    semantic_type: str | None = None
    description: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("variable requirement name is required")

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "dimension": self.dimension,
            "expected_unit": self.expected_unit,
            "required": self.required,
            "semantic_type": self.semantic_type,
            "description": self.description,
        }


@dataclass(frozen=True)
class ScientificFinding:
    finding_id: str
    constraint_id: str
    status: str
    severity: str
    message: str
    remediation_code: str
    claim_impact: str = "none"
    evidence_refs: tuple[str, ...] = ()
    category: str = "scientific_consistency"

    def __post_init__(self) -> None:
        if self.status not in SCIENTIFIC_FINDING_STATUSES:
            raise ValueError(f"unsupported scientific finding status: {self.status}")
        if self.severity not in SCIENTIFIC_FINDING_SEVERITIES:
            raise ValueError(f"unsupported scientific finding severity: {self.severity}")

    def to_dict(self) -> dict[str, object]:
        return {
            "finding_id": self.finding_id,
            "constraint_id": self.constraint_id,
            "status": self.status,
            "severity": self.severity,
            "message": self.message,
            "remediation_code": self.remediation_code,
            "claim_impact": self.claim_impact,
            "evidence_refs": list(self.evidence_refs),
            "category": self.category,
        }


@dataclass(frozen=True)
class ScientificConstraint:
    constraint_id: str
    name: str
    domain: str
    category: str
    description: str
    equation_display: str | None = None
    evaluator_id: str | None = None
    required_variables: tuple[VariableRequirement, ...] = ()
    optional_variables: tuple[VariableRequirement, ...] = ()
    expected_units: dict[str, str] = field(default_factory=dict)
    output_unit: str | None = None
    dimensional_signature: str = ""
    assumptions: tuple[str, ...] = ()
    validity_conditions: tuple[str, ...] = ()
    invalidity_conditions: tuple[str, ...] = ()
    tolerance_policy: dict[str, Any] = field(default_factory=dict)
    severity_on_violation: str = "warning"
    evaluation_role: str = "metadata_only"
    feature_role: str = "none"
    model_role: str = "none"
    claim_impact: str = "narrow_claim"
    references: tuple[str, ...] = ()
    version: str = "1"
    status: str = "metadata_only"

    def __post_init__(self) -> None:
        if not self.constraint_id:
            raise ValueError("constraint_id is required")
        if self.category not in SCIENTIFIC_CONSTRAINT_CATEGORIES:
            raise ValueError(f"unsupported scientific constraint category: {self.category}")
        if self.evaluation_role not in SCIENTIFIC_EVALUATION_ROLES:
            raise ValueError(f"unsupported evaluation_role: {self.evaluation_role}")
        if self.status not in SCIENTIFIC_CONSTRAINT_STATUSES:
            raise ValueError(f"unsupported constraint status: {self.status}")
        if self.severity_on_violation not in SCIENTIFIC_FINDING_SEVERITIES:
            raise ValueError(f"unsupported severity_on_violation: {self.severity_on_violation}")
        forbidden_tokens = ("eval(", "exec(", "__import__")
        if self.equation_display and any(token in self.equation_display for token in forbidden_tokens):
            raise ValueError("equation_display must not contain executable-looking Python tokens")

    def to_dict(self) -> dict[str, object]:
        return {
            "constraint_id": self.constraint_id,
            "name": self.name,
            "domain": self.domain,
            "category": self.category,
            "description": self.description,
            "equation_display": self.equation_display,
            "evaluator_id": self.evaluator_id,
            "required_variables": [variable.to_dict() for variable in self.required_variables],
            "optional_variables": [variable.to_dict() for variable in self.optional_variables],
            "expected_units": dict(self.expected_units),
            "output_unit": self.output_unit,
            "dimensional_signature": self.dimensional_signature,
            "assumptions": list(self.assumptions),
            "validity_conditions": list(self.validity_conditions),
            "invalidity_conditions": list(self.invalidity_conditions),
            "tolerance_policy": dict(self.tolerance_policy),
            "severity_on_violation": self.severity_on_violation,
            "evaluation_role": self.evaluation_role,
            "feature_role": self.feature_role,
            "model_role": self.model_role,
            "claim_impact": self.claim_impact,
            "references": list(self.references),
            "version": self.version,
            "status": self.status,
        }
