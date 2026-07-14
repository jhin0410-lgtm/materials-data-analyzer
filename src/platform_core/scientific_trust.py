"""Scientific trust-boundary and feature-eligibility evaluation.

This module reads existing scientific execution records and registry metadata.
It does not run scientific evaluators, compute feature values, read raw data, or
train models.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Mapping

from .run_registry import canonical_json_sha256
from .scientific_constraints import ScientificConstraint
from .scientific_feature_candidates import ScientificFeatureCandidate
from .scientific_feature_registry import ScientificFeatureRegistry, build_default_scientific_feature_registry


SCIENTIFIC_TRUST_SCHEMA_VERSION = "2.1.5"
SCIENTIFIC_TRUST_RULE_VERSION = "scientific_trust_rules_v2_1_5"
SCIENTIFIC_FEATURE_REGISTRY_VERSION = "scientific_feature_registry_v2_1_5"

SCIENTIFIC_EVIDENCE_LEVELS = (
    "metadata_registered",
    "applicability_checked",
    "consistency_checked",
    "bounded_quantity_estimated",
    "feature_candidate",
    "model_constraint_candidate",
    "independently_validated",
    "production_validated",
)

CONSTRAINT_ROLES = (
    "validation_only",
    "diagnostic_only",
    "derived_feature_candidate",
    "model_constraint_candidate",
    "post_prediction_check",
    "documentation_only",
    "bounded_quantity_estimated",
    "unavailable",
)

CLAIM_BOUNDARY_IDS = (
    "physically_consistent_input",
    "dimensionally_consistent",
    "bounded_quantity_estimated",
    "lattice_spacing_estimated",
    "crystallite_size_estimated",
    "physics_informed_feature_available",
    "physics_informed_feature_used",
    "physics_constrained_model",
    "hybrid_physics_ml",
    "thermodynamic_consistency",
    "degradation_mechanism_supported",
    "phase_identification_supported",
    "particle_size_estimated",
    "production_scientific_decision",
)

MODEL_CONSTRAINT_STATUSES = (
    "candidate_with_limits",
    "diagnostic_only",
    "blocked_invalid_assumption",
    "blocked_overclaim",
    "unavailable_missing_variable",
    "unavailable",
)


@dataclass(frozen=True)
class ConstraintEligibility:
    constraint_id: str
    role: str
    eligibility_status: str
    reason_codes: tuple[str, ...] = ()
    remediation_codes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "constraint_id": self.constraint_id,
            "role": self.role,
            "eligibility_status": self.eligibility_status,
            "reason_codes": list(self.reason_codes),
            "remediation_codes": list(self.remediation_codes),
        }


@dataclass(frozen=True)
class FeatureEligibility:
    feature_id: str
    eligibility_status: str
    prediction_time_available: bool
    leakage_status: str
    assumption_status: str
    reason_codes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_id": self.feature_id,
            "eligibility_status": self.eligibility_status,
            "prediction_time_available": self.prediction_time_available,
            "leakage_status": self.leakage_status,
            "assumption_status": self.assumption_status,
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True)
class ScientificClaimBoundary:
    claim_id: str
    status: str
    support_refs: tuple[str, ...] = ()
    conflict_refs: tuple[str, ...] = ()
    reason_code: str = "boundary_not_evaluated"

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "status": self.status,
            "support_refs": list(self.support_refs),
            "conflict_refs": list(self.conflict_refs),
            "reason_code": self.reason_code,
        }


@dataclass(frozen=True)
class ScientificTrustEvaluation:
    evaluation_id: str
    execution_id: str
    knowledge_pack_id: str
    constraint_id: str | None
    evaluator_id: str | None
    applicability_status: str
    execution_status: str
    evidence_level: str
    unit_status: str
    assumption_status: str
    validity_status: str
    uncertainty_status: str
    reproducibility_status: str
    feature_eligibility: tuple[FeatureEligibility, ...]
    model_constraint_eligibility: str
    allowed_claims: tuple[str, ...]
    prohibited_claims: tuple[str, ...]
    rejection_reasons: tuple[str, ...]
    remediation_codes: tuple[str, ...]
    source_refs: tuple[str, ...]
    constraint_eligibility: tuple[ConstraintEligibility, ...] = ()
    claim_boundaries: tuple[ScientificClaimBoundary, ...] = ()
    evidence_graph: Mapping[str, Any] = field(default_factory=dict)
    source_execution_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCIENTIFIC_TRUST_SCHEMA_VERSION,
            "trust_policy_version": SCIENTIFIC_TRUST_RULE_VERSION,
            "evaluation_id": self.evaluation_id,
            "execution_id": self.execution_id,
            "knowledge_pack_id": self.knowledge_pack_id,
            "constraint_id": self.constraint_id,
            "evaluator_id": self.evaluator_id,
            "applicability_status": self.applicability_status,
            "execution_status": self.execution_status,
            "evidence_level": self.evidence_level,
            "unit_status": self.unit_status,
            "assumption_status": self.assumption_status,
            "validity_status": self.validity_status,
            "uncertainty_status": self.uncertainty_status,
            "reproducibility_status": self.reproducibility_status,
            "feature_eligibility": [item.to_dict() for item in self.feature_eligibility],
            "model_constraint_eligibility": self.model_constraint_eligibility,
            "allowed_claims": list(self.allowed_claims),
            "prohibited_claims": list(self.prohibited_claims),
            "rejection_reasons": list(self.rejection_reasons),
            "remediation_codes": list(self.remediation_codes),
            "source_refs": list(self.source_refs),
            "constraint_eligibility": [item.to_dict() for item in self.constraint_eligibility],
            "claim_boundaries": [item.to_dict() for item in self.claim_boundaries],
            "evidence_graph": dict(self.evidence_graph),
            "source_execution_hash": self.source_execution_hash,
        }


@dataclass(frozen=True)
class ScientificCloseoutConclusion:
    status: str
    release_readiness: str
    summary: str
    allowed_claims: tuple[str, ...]
    prohibited_claims: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "release_readiness": self.release_readiness,
            "summary": self.summary,
            "allowed_claims": list(self.allowed_claims),
            "prohibited_claims": list(self.prohibited_claims),
        }


def _json_field(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def _constraint_roles(constraint: ScientificConstraint) -> tuple[str, ...]:
    cid = constraint.constraint_id
    if cid == "xrd.bragg.geometry":
        return ("validation_only", "bounded_quantity_estimated", "derived_feature_candidate")
    if cid == "xrd.scherrer.preconditions":
        return ("bounded_quantity_estimated", "derived_feature_candidate")
    if cid == "xrd.crystallite_size.positive":
        return ("validation_only", "post_prediction_check")
    if cid == "materials.composition_fraction.sum_to_one":
        return ("validation_only", "post_prediction_check")
    if cid == "materials.energy_above_hull.non_negative_tolerance":
        return ("validation_only", "diagnostic_only")
    if cid == "battery.temperature.arrhenius_domain":
        return ("documentation_only", "model_constraint_candidate")
    if cid == "battery.cycle_index.non_decreasing":
        return ("validation_only",)
    if cid == "reliability.post_event.feature_prohibition":
        return ("validation_only", "post_prediction_check")
    if constraint.status == "metadata_only":
        return ("documentation_only",)
    if constraint.feature_role in {"derived_feature_candidate", "diagnostic"}:
        return ("diagnostic_only", "derived_feature_candidate")
    if constraint.evaluation_role in {"range_check", "consistency_check", "unit_check"}:
        return ("validation_only",)
    if constraint.evaluation_role == "model_constraint":
        return ("model_constraint_candidate",)
    if constraint.evaluation_role == "post_prediction_check":
        return ("post_prediction_check",)
    return ("documentation_only",)


def classify_constraint_roles(constraint: ScientificConstraint) -> tuple[ConstraintEligibility, ...]:
    records: list[ConstraintEligibility] = []
    for role in _constraint_roles(constraint):
        status = "eligible_metadata"
        reasons: tuple[str, ...] = ()
        remediation: tuple[str, ...] = ()
        if role == "model_constraint_candidate":
            status = "candidate_with_limits"
            if constraint.constraint_id in {
                "battery.temperature.arrhenius_domain",
                "battery.cycle_index.non_decreasing",
            }:
                status = "blocked_invalid_assumption"
                reasons = ("mechanism_or_monotonicity_not_universal",)
                remediation = ("document_mechanism_and_exception_scope",)
        elif role == "derived_feature_candidate":
            status = "metadata_candidate"
        elif role == "bounded_quantity_estimated":
            status = "requires_execution_evidence"
        elif role == "documentation_only":
            status = "metadata_only"
        records.append(
            ConstraintEligibility(
                constraint_id=constraint.constraint_id,
                role=role,
                eligibility_status=status,
                reason_codes=reasons,
                remediation_codes=remediation,
            )
        )
    return tuple(records)


def constraint_role_snapshot(registry) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for constraint in registry.list_constraints():
        for item in classify_constraint_roles(constraint):
            payload = item.to_dict()
            payload["domain"] = constraint.domain
            payload["category"] = constraint.category
            payload["constraint_status"] = constraint.status
            rows.append(payload)
    return sorted(rows, key=lambda row: (row["constraint_id"], row["role"]))


def _execution_variables(execution_payload: Mapping[str, Any]) -> tuple[set[str], set[str], dict[str, Any]]:
    variables: set[str] = set()
    variables_with_units: set[str] = set()
    values: dict[str, Any] = {}
    for row in execution_payload.get("unit_conversions", []):
        variable_id = str(row.get("variable_id", ""))
        if not variable_id:
            continue
        variables.add(variable_id)
        if row.get("conversion_status") not in {"missing_unit", "incompatible_unit"}:
            variables_with_units.add(variable_id)
        normalized_value = _json_field(row.get("normalized_value"), None)
        if normalized_value is not None:
            values[variable_id] = normalized_value
    for finding in execution_payload.get("findings", []):
        normalized = _json_field(finding.get("normalized_values_json"), {})
        if isinstance(normalized, dict):
            for key, value in normalized.items():
                variables.add(str(key))
                values[str(key)] = value
    return variables, variables_with_units, values


def evaluate_feature_candidate_against_execution(
    candidate: ScientificFeatureCandidate,
    execution_payload: Mapping[str, Any] | None = None,
) -> FeatureEligibility:
    reasons: list[str] = []
    variables: set[str] = set()
    variables_with_units: set[str] = set()
    if execution_payload is not None:
        variables, variables_with_units, _ = _execution_variables(execution_payload)
    missing_variables = sorted(set(candidate.required_variables) - variables) if execution_payload is not None else []
    missing_units = sorted(
        variable for variable in candidate.required_units if variable in variables and variable not in variables_with_units
    ) if execution_payload is not None else []
    status = candidate.eligibility_status
    if candidate.leakage_risk == "blocked_leakage_risk":
        status = "blocked_leakage_risk"
        reasons.append("feature_has_declared_leakage_risk")
    elif not candidate.prediction_time_available:
        status = "blocked_leakage_risk"
        reasons.append("not_prediction_time_available")
    elif missing_variables:
        status = "unavailable_missing_variable"
        reasons.extend(f"missing_variable:{item}" for item in missing_variables)
    elif missing_units:
        status = "unavailable_missing_unit"
        reasons.extend(f"missing_unit:{item}" for item in missing_units)
    elif any("invalid" in text.lower() for text in candidate.assumptions):
        status = "blocked_invalid_assumption"
        reasons.append("invalid_assumption_declared")
    elif candidate.validation_status == "bounded_builder_candidate":
        status = "eligible_bounded"
    elif status == "eligible_with_metadata_requirement" and candidate.applicability_requirements:
        reasons.append("metadata_requirement_remains")
    leakage_status = "requires_prediction_cutoff" if candidate.leakage_risk == "requires_prediction_cutoff" else candidate.leakage_risk
    assumption_status = "metadata_required" if candidate.assumptions else "not_required"
    return FeatureEligibility(
        feature_id=candidate.feature_id,
        eligibility_status=status,
        prediction_time_available=candidate.prediction_time_available,
        leakage_status=leakage_status,
        assumption_status=assumption_status,
        reason_codes=tuple(sorted(set(reasons))),
    )


def _evidence_level(execution_payload: Mapping[str, Any]) -> str:
    findings = execution_payload.get("findings", [])
    claims = execution_payload.get("claim_evaluations", [])
    evidence_refs: set[str] = set()
    for finding in findings:
        evidence_refs.update(str(item) for item in _json_field(finding.get("evidence_refs_json"), []))
    for claim in claims:
        evidence_refs.update(str(item) for item in _json_field(claim.get("support_refs_json"), []))
    if any("crystallite_size_estimated" in item or "lattice_spacing_estimated" in item for item in evidence_refs):
        return "bounded_quantity_estimated"
    if any(row.get("status") in {"consistent", "conditionally_consistent"} for row in findings):
        return "consistency_checked"
    if execution_payload.get("execution", {}).get("status") in {"applicable", "conditionally_consistent", "consistent"}:
        return "applicability_checked"
    return "metadata_registered"


def _unit_status(execution_payload: Mapping[str, Any]) -> str:
    conversions = execution_payload.get("unit_conversions", [])
    statuses = {row.get("conversion_status") for row in conversions}
    if not conversions:
        return "unit_metadata_unavailable"
    if {"missing_unit", "incompatible_unit"} & statuses:
        return "unit_issue"
    return "unit_consistent"


def _assumption_status(execution_payload: Mapping[str, Any]) -> str:
    for finding in execution_payload.get("findings", []):
        assumptions = _json_field(finding.get("assumptions_json"), [])
        if any(isinstance(item, dict) and item.get("status") == "invalid" for item in assumptions):
            return "invalid_assumption"
    return "assumptions_recorded"


def _claim_boundary(
    execution_payload: Mapping[str, Any],
    feature_eligibility: tuple[FeatureEligibility, ...],
) -> tuple[ScientificClaimBoundary, ...]:
    persisted = {
        row.get("claim_id"): row
        for row in execution_payload.get("claim_evaluations", [])
        if row.get("claim_id")
    }
    evidence_refs: set[str] = set()
    for finding in execution_payload.get("findings", []):
        evidence_refs.update(str(item) for item in _json_field(finding.get("evidence_refs_json"), []))
    feature_available = any(item.eligibility_status in {"eligible_bounded", "eligible_with_metadata_requirement"} for item in feature_eligibility)
    boundaries: list[ScientificClaimBoundary] = []
    for claim_id in CLAIM_BOUNDARY_IDS:
        if claim_id in persisted:
            row = persisted[claim_id]
            status = row.get("status", "unsupported")
            support = tuple(_json_field(row.get("support_refs_json"), []))
            conflict = tuple(_json_field(row.get("conflict_refs_json"), []))
            reason = row.get("reason_code", "persisted_claim_evaluation")
        elif claim_id == "bounded_quantity_estimated" and any(
            item in evidence_refs
            for item in {
                "scientific_evidence:lattice_spacing_estimated",
                "scientific_evidence:crystallite_size_estimated",
            }
        ):
            status = "supported_with_limits"
            support = tuple(sorted(evidence_refs))
            conflict = ()
            reason = "bounded_registered_quantity_was_estimated"
        elif claim_id == "lattice_spacing_estimated" and "scientific_evidence:lattice_spacing_estimated" in evidence_refs:
            status = "supported_with_limits"
            support = ("scientific_evidence:lattice_spacing_estimated",)
            conflict = ()
            reason = "bragg_d_spacing_estimated_with_supplied_metadata"
        elif claim_id == "crystallite_size_estimated" and "scientific_evidence:crystallite_size_estimated" in evidence_refs:
            status = "supported_with_limits"
            support = ("scientific_evidence:crystallite_size_estimated",)
            conflict = ("scherrer_limitations_apply",)
            reason = "scherrer_crystallite_size_estimated_with_limits"
        elif claim_id == "physics_informed_feature_available" and feature_available:
            status = "supported_with_limits"
            support = ("feature_eligibility:metadata_candidate",)
            conflict = ()
            reason = "eligible_feature_definition_available_not_used"
        elif claim_id in {
            "physics_informed_feature_used",
            "physics_constrained_model",
            "hybrid_physics_ml",
            "phase_identification_supported",
            "particle_size_estimated",
            "production_scientific_decision",
            "degradation_mechanism_supported",
        }:
            status = "prohibited"
            support = ()
            conflict = (f"missing:{claim_id}:execution_evidence",)
            reason = "claim_overreach"
        elif claim_id == "thermodynamic_consistency":
            status = "unsupported"
            support = ()
            conflict = ("composition_or_scalar_checks_do_not_prove_thermodynamic_consistency",)
            reason = "insufficient_evidence"
        else:
            status = "unsupported"
            support = ()
            conflict = (f"missing:{claim_id}:evidence",)
            reason = "evidence_not_available"
        boundaries.append(ScientificClaimBoundary(claim_id, status, support, conflict, reason))
    return tuple(boundaries)


def _model_constraint_status(constraint_eligibility: tuple[ConstraintEligibility, ...]) -> str:
    statuses = {item.eligibility_status for item in constraint_eligibility if item.role == "model_constraint_candidate"}
    if "blocked_invalid_assumption" in statuses:
        return "blocked_invalid_assumption"
    if "candidate_with_limits" in statuses:
        return "candidate_with_limits"
    return "unavailable"


def evaluate_scientific_trust(
    execution_payload: Mapping[str, Any],
    *,
    feature_registry: ScientificFeatureRegistry | None = None,
) -> ScientificTrustEvaluation:
    feature_registry = feature_registry or build_default_scientific_feature_registry()
    execution = execution_payload["execution"]
    execution_id = str(execution["execution_id"])
    source_hash = canonical_json_sha256(json.loads(json.dumps(execution_payload, sort_keys=True, default=str)))
    pack_id = str(execution["knowledge_pack_id"])
    constraints = feature_registry.constraint_registry
    constraint_ids = sorted({row["constraint_id"] for row in execution_payload.get("findings", []) if row.get("constraint_id")})
    constraint_eligibility: list[ConstraintEligibility] = []
    evaluator_id = None
    for constraint_id in constraint_ids:
        try:
            constraint = constraints.get(constraint_id)
        except KeyError:
            constraint_eligibility.append(
                ConstraintEligibility(
                    constraint_id=constraint_id,
                    role="unavailable",
                    eligibility_status="unavailable",
                    reason_codes=("constraint_not_registered",),
                    remediation_codes=("register_constraint_metadata",),
                )
            )
            continue
        evaluator_id = evaluator_id or constraint.evaluator_id
        constraint_eligibility.extend(classify_constraint_roles(constraint))
    feature_records = tuple(
        evaluate_feature_candidate_against_execution(feature, execution_payload)
        for feature in feature_registry.list_features()
        if feature.knowledge_pack_id == pack_id
    )
    claim_boundaries = _claim_boundary(execution_payload, feature_records)
    prohibited_claims = tuple(sorted(item.claim_id for item in claim_boundaries if item.status == "prohibited"))
    allowed_claims = tuple(sorted(item.claim_id for item in claim_boundaries if item.status in {"supported", "supported_with_limits"}))
    blockers = [row for row in execution_payload.get("findings", []) if row.get("severity") == "blocker"]
    rejection_reasons = []
    if blockers:
        rejection_reasons.append("blocker_findings_present")
    if any(item.status == "prohibited" for item in claim_boundaries):
        rejection_reasons.append("unsupported_claims_are_prohibited")
    evidence_level = _evidence_level(execution_payload)
    evaluation_id = "scientific_trust_" + canonical_json_sha256(
        {
            "execution_id": execution_id,
            "source_hash": source_hash,
            "trust_rule_version": SCIENTIFIC_TRUST_RULE_VERSION,
            "feature_registry_version": SCIENTIFIC_FEATURE_REGISTRY_VERSION,
        }
    )[:20]
    from .evidence_graph import build_scientific_trust_evidence_graph

    graph = build_scientific_trust_evidence_graph(
        trust_evaluation_id=evaluation_id,
        execution_id=execution_id,
        feature_eligibility=[item.to_dict() for item in feature_records],
        claim_boundaries=[item.to_dict() for item in claim_boundaries],
        constraint_eligibility=[item.to_dict() for item in constraint_eligibility],
    )
    return ScientificTrustEvaluation(
        evaluation_id=evaluation_id,
        execution_id=execution_id,
        knowledge_pack_id=pack_id,
        constraint_id=constraint_ids[0] if len(constraint_ids) == 1 else None,
        evaluator_id=evaluator_id,
        applicability_status="applicability_checked",
        execution_status=str(execution["status"]),
        evidence_level=evidence_level,
        unit_status=_unit_status(execution_payload),
        assumption_status=_assumption_status(execution_payload),
        validity_status="bounded_validity_only",
        uncertainty_status="limited_or_unavailable",
        reproducibility_status="metadata_reproducible",
        feature_eligibility=feature_records,
        model_constraint_eligibility=_model_constraint_status(tuple(constraint_eligibility)),
        allowed_claims=allowed_claims,
        prohibited_claims=prohibited_claims,
        rejection_reasons=tuple(sorted(set(rejection_reasons))),
        remediation_codes=("do_not_overclaim_scientific_correctness",),
        source_refs=(f"scientific_execution:{execution_id}",),
        constraint_eligibility=tuple(constraint_eligibility),
        claim_boundaries=claim_boundaries,
        evidence_graph=graph,
        source_execution_hash=source_hash,
    )


def closeout_conclusion() -> ScientificCloseoutConclusion:
    return ScientificCloseoutConclusion(
        status="feature_complete_pending_release_audit",
        release_readiness="release_ready_after_ci",
        summary=(
            "v2.1 scientific execution is bounded to explicit registry-based checks; "
            "feature candidates and model constraints remain metadata eligibility records until v2.2."
        ),
        allowed_claims=(
            "bounded scalar/list consistency checks",
            "d-spacing or crystallite-size estimates when inputs and assumptions are supplied",
            "physics-aware feature candidates as metadata only",
        ),
        prohibited_claims=(
            "independent scientific validation",
            "phase identification",
            "particle-size inference from Scherrer alone",
            "physics-informed feature used in predictive models",
            "physics-constrained model",
            "production scientific decision",
        ),
    )
