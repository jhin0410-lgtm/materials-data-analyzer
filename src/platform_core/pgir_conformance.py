"""PGIR conformance gates for representation-producing code.

This module turns the v2.3.1 PGIR governance registries into explicit gates.
It does not create a new entity hierarchy, import user-provided classes,
execute solvers, train models, or mutate registry files.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from .pgir_governance import (
    VALID_MATURITY_LEVELS,
    build_concept_registry,
    build_schema_ownership_registry,
)


PGIR_CONFORMANCE_VERSION = "2.3.2"

MATURITY_ORDER = {level: index for index, level in enumerate(VALID_MATURITY_LEVELS)}
MATURITY_ALIASES = {
    f"L{index + 1}": level for index, level in enumerate(VALID_MATURITY_LEVELS)
}
MATURITY_ALIASES.update({key.lower(): value for key, value in MATURITY_ALIASES.items()})


def _normalize_maturity_level(level: str) -> str:
    normalized = MATURITY_ALIASES.get(str(level), str(level))
    if normalized not in MATURITY_ORDER:
        raise ValueError(f"unsupported maturity level: {level}")
    return normalized

PROMOTION_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "schema_valid": (
        "parser_success",
        "required_structural_fields",
        "schema_validation",
    ),
    "semantically_mapped": (
        "variable_semantics_known",
        "source_field_mapping",
        "representation_context_known",
    ),
    "dimensionally_valid": (
        "units_available_or_dimensionless",
        "dimensional_compatibility",
    ),
    "physically_admissible": (
        "registered_admissibility_checks",
        "finite_ranges",
    ),
    "mechanism_compatible": (
        "mechanism_requirements_metadata",
        "applicability_evaluated",
    ),
    "scientifically_evaluated": (
        "registered_operator_executed",
        "results_recorded",
        "uncertainty_recorded",
    ),
    "independently_validated": ("independent_validation_evidence",),
    "production_validated": (
        "deployment_validation_evidence",
        "operational_governance_evidence",
    ),
}

CAPABILITY_REQUIREMENTS: dict[str, dict[str, Any]] = {
    "tabular_summary": {"minimum_maturity": "schema_valid"},
    "dimensional_comparison": {"minimum_maturity": "dimensionally_valid"},
    "bounded_physical_validation": {"minimum_maturity": "physically_admissible"},
    "bounded_physical_propagation": {
        "minimum_maturity": "physically_admissible",
        "required_context": ("registered_model_contract", "registered_operator", "bounded_execution_policy"),
    },
    "mechanism_applicability_assessment": {
        "minimum_maturity": "physically_admissible",
        "required_context": ("mechanism_requirements_metadata",),
    },
    "mechanism_execution": {"minimum_maturity": "mechanism_compatible"},
    "predictive_model_input": {
        "minimum_maturity": "semantically_mapped",
        "required_context": ("feature_provenance", "leakage_policy"),
    },
    "production_decision": {"minimum_maturity": "production_validated"},
}

REGISTERED_TRANSITIONS: dict[str, dict[str, Any]] = {
    "mp_structure_to_crystal_entity_v1": {
        "input_concept": "result",
        "output_concept": "physical_entity",
        "required_metadata": ("material_id", "structure", "source_record_checksum"),
        "deterministic": True,
        "information_loss": "runtime_materials_objects_are_converted_to_json_safe_entity_records",
        "maturity_result": "semantically_mapped",
    },
    "crystal_structure_integrity_check_v1": {
        "input_concept": "physical_entity",
        "output_concept": "result",
        "required_metadata": ("lattice", "sites", "integrity_status"),
        "deterministic": True,
        "information_loss": "evaluator_result_summarizes_integrity_without_replacing_structure_body",
        "maturity_result": "physically_admissible",
    },
    "composition_structure_consistency_check_v1": {
        "input_concept": "physical_entity",
        "output_concept": "result",
        "required_metadata": ("summary_composition", "structure_derived_composition", "consistency_status"),
        "deterministic": True,
        "information_loss": "comparison_status_does_not_assert_phase_or_experimental_validity",
        "maturity_result": "physically_admissible",
    },
    "crystal_structure_to_descriptor_summary_v1": {
        "input_concept": "physical_entity",
        "output_concept": "result",
        "required_metadata": ("descriptor_registry", "prediction_context", "target_access_policy"),
        "deterministic": True,
        "information_loss": "descriptors_are_bounded_transformed_representations",
        "maturity_result": "semantically_mapped",
    },
    "crystal_structure_to_radius_graph_v1": {
        "input_concept": "physical_entity",
        "output_concept": "result",
        "required_metadata": ("graph_builder", "cutoff_policy", "target_access_policy"),
        "deterministic": True,
        "information_loss": "graph_is_a_representation_artifact_not_physical_or_predictive_evidence",
        "maturity_result": "semantically_mapped",
    },
    "battery_source_record_to_cycle_observation_v1": {
        "input_concept": "result",
        "output_concept": "observation",
        "required_metadata": ("source_record_ref", "cell_id", "cycle_index"),
        "deterministic": True,
        "information_loss": "raw_time_series_body_stays_local_artifact_ref",
        "maturity_result": "semantically_mapped",
    },
    "battery_cycle_observation_to_operational_state_v1": {
        "input_concept": "observation",
        "output_concept": "state",
        "required_metadata": ("cycle_index", "capacity_observation", "unit_metadata"),
        "deterministic": True,
        "information_loss": "operational_summary_only_no_latent_state",
        "maturity_result": "dimensionally_valid",
    },
    "battery_operational_states_to_trajectory_v1": {
        "input_concept": "state",
        "output_concept": "trajectory",
        "required_metadata": ("ordered_state_refs", "time_axis_semantics"),
        "deterministic": True,
        "information_loss": "row_level_states_referenced_not_inlined",
        "maturity_result": "dimensionally_valid",
    },
    "one_dimensional_diffusion_exact_propagator_v1": {
        "input_concept": "model",
        "output_concept": "field",
        "required_metadata": ("model_contract_id", "input_checksum", "exact_result_checksum"),
        "deterministic": True,
        "information_loss": "field arrays remain local-only while compact lineage is tracked",
        "maturity_result": "scientifically_evaluated",
    },
    "one_dimensional_diffusion_ftcs_propagator_v1": {
        "input_concept": "model",
        "output_concept": "field",
        "required_metadata": ("model_contract_id", "stability_ratio", "numerical_result_checksum"),
        "deterministic": True,
        "information_loss": "field arrays remain local-only while compact lineage is tracked",
        "maturity_result": "scientifically_evaluated",
    },
    "one_dimensional_diffusion_benchmark_evaluator_v1": {
        "input_concept": "field",
        "output_concept": "result",
        "required_metadata": ("exact_result_checksum", "numerical_result_checksum", "evaluation_metrics"),
        "deterministic": True,
        "information_loss": "compact error evidence summarizes local exact and numerical fields",
        "maturity_result": "scientifically_evaluated",
    },
}


def _safe_identifier(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} is required")
    if any(part in value for part in ("/", "\\", "..", ":")):
        raise ValueError(f"{field_name} must be an identifier, not a path")
    return value.strip()


def _json_safe(value: Any, *, location: str = "value") -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _json_safe(item, location=f"{location}.{key}")
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, tuple):
        return [_json_safe(item, location=f"{location}[]") for item in value]
    if isinstance(value, list):
        return [_json_safe(item, location=f"{location}[]") for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise ValueError(f"{location} contains unsupported JSON value type: {type(value).__name__}")


def _as_tuple(values: Any) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, str):
        return (values,)
    return tuple(str(item) for item in values)


@dataclass(frozen=True)
class PGIRRepresentationDeclaration:
    declaration_id: str
    declaration_version: str
    pgir_concept_id: str
    representation_schema_id: str
    representation_schema_version: str
    entity_or_artifact_ref: str
    domain_context: str
    measurement_context: str = "unavailable"
    mechanism_context: str = "not_applicable"
    temporal_context: str = "unavailable"
    spatial_context: str = "unavailable"
    validation_context: str = "not_evaluated"
    current_maturity_level: str = "raw_observed"
    claimed_capabilities: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    uncertainty_refs: tuple[str, ...] = ()
    provenance_refs: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    prohibited_interpretations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _safe_identifier(self.declaration_id, "declaration_id")
        if _normalize_maturity_level(self.current_maturity_level) not in MATURITY_ORDER:
            raise ValueError(f"unsupported current_maturity_level: {self.current_maturity_level}")
        for capability in self.claimed_capabilities:
            _safe_identifier(capability, "claimed_capability")
        for reference in (self.entity_or_artifact_ref, *self.evidence_refs, *self.uncertainty_refs, *self.provenance_refs):
            if str(reference).startswith("/") or ":/" in str(reference) or ":\\" in str(reference) or ".." in str(reference).split("/"):
                raise ValueError("PGIR declaration references must be relative identifiers or relative paths")

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "PGIRRepresentationDeclaration":
        return cls(
            declaration_id=str(payload["declaration_id"]),
            declaration_version=str(payload.get("declaration_version", "1")),
            pgir_concept_id=str(payload["pgir_concept_id"]),
            representation_schema_id=str(payload["representation_schema_id"]),
            representation_schema_version=str(payload["representation_schema_version"]),
            entity_or_artifact_ref=str(payload["entity_or_artifact_ref"]),
            domain_context=str(payload.get("domain_context", "unavailable")),
            measurement_context=str(payload.get("measurement_context", "unavailable")),
            mechanism_context=str(payload.get("mechanism_context", "not_applicable")),
            temporal_context=str(payload.get("temporal_context", "unavailable")),
            spatial_context=str(payload.get("spatial_context", "unavailable")),
            validation_context=str(payload.get("validation_context", "not_evaluated")),
            current_maturity_level=_normalize_maturity_level(str(payload.get("current_maturity_level", "raw_observed"))),
            claimed_capabilities=_as_tuple(payload.get("claimed_capabilities")),
            evidence_refs=_as_tuple(payload.get("evidence_refs")),
            uncertainty_refs=_as_tuple(payload.get("uncertainty_refs")),
            provenance_refs=_as_tuple(payload.get("provenance_refs")),
            limitations=_as_tuple(payload.get("limitations")),
            prohibited_interpretations=_as_tuple(payload.get("prohibited_interpretations")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "declaration_id": self.declaration_id,
            "declaration_version": self.declaration_version,
            "pgir_concept_id": self.pgir_concept_id,
            "representation_schema_id": self.representation_schema_id,
            "representation_schema_version": self.representation_schema_version,
            "entity_or_artifact_ref": self.entity_or_artifact_ref,
            "domain_context": self.domain_context,
            "measurement_context": self.measurement_context,
            "mechanism_context": self.mechanism_context,
            "temporal_context": self.temporal_context,
            "spatial_context": self.spatial_context,
            "validation_context": self.validation_context,
            "current_maturity_level": self.current_maturity_level,
            "claimed_capabilities": list(self.claimed_capabilities),
            "evidence_refs": list(self.evidence_refs),
            "uncertainty_refs": list(self.uncertainty_refs),
            "provenance_refs": list(self.provenance_refs),
            "limitations": list(self.limitations),
            "prohibited_interpretations": list(self.prohibited_interpretations),
        }


@dataclass(frozen=True)
class PGIRConformanceFinding:
    finding_id: str
    severity: str
    message: str
    gate: str

    def to_dict(self) -> dict[str, str]:
        return {
            "finding_id": self.finding_id,
            "severity": self.severity,
            "message": self.message,
            "gate": self.gate,
        }


@dataclass(frozen=True)
class PGIRMaturityAssessment:
    declaration_id: str
    current_maturity_level: str
    requested_maturity_level: str
    resulting_maturity_level: str
    promotion_allowed: bool
    missing_evidence: tuple[str, ...] = ()
    findings: tuple[PGIRConformanceFinding, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "declaration_id": self.declaration_id,
            "current_maturity_level": self.current_maturity_level,
            "requested_maturity_level": self.requested_maturity_level,
            "resulting_maturity_level": self.resulting_maturity_level,
            "promotion_allowed": self.promotion_allowed,
            "missing_evidence": list(self.missing_evidence),
            "findings": [finding.to_dict() for finding in self.findings],
        }


@dataclass(frozen=True)
class PGIRContextCompatibilityResult:
    status: str
    source_context: str
    requested_context: str
    findings: tuple[PGIRConformanceFinding, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "source_context": self.source_context,
            "requested_context": self.requested_context,
            "findings": [finding.to_dict() for finding in self.findings],
        }


@dataclass(frozen=True)
class PGIRTransitionAssessment:
    transition_id: str
    input_concept: str
    output_concept: str
    transition_allowed: bool
    maturity_result: str
    findings: tuple[PGIRConformanceFinding, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "transition_id": self.transition_id,
            "input_concept": self.input_concept,
            "output_concept": self.output_concept,
            "transition_allowed": self.transition_allowed,
            "maturity_result": self.maturity_result,
            "findings": [finding.to_dict() for finding in self.findings],
        }


@dataclass(frozen=True)
class PGIROperatorEligibilityResult:
    capability_id: str
    status: str
    minimum_maturity: str
    current_maturity: str
    findings: tuple[PGIRConformanceFinding, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "status": self.status,
            "minimum_maturity": self.minimum_maturity,
            "current_maturity": self.current_maturity,
            "findings": [finding.to_dict() for finding in self.findings],
        }


@dataclass(frozen=True)
class PGIRConformanceSummary:
    status: str
    valid: bool
    declaration_count: int
    blocked_promotion_count: int
    incompatible_context_count: int
    transition_count: int
    capability_count: int
    findings: tuple[PGIRConformanceFinding, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": PGIR_CONFORMANCE_VERSION,
            "status": self.status,
            "valid": self.valid,
            "declaration_count": self.declaration_count,
            "blocked_promotion_count": self.blocked_promotion_count,
            "incompatible_context_count": self.incompatible_context_count,
            "transition_count": self.transition_count,
            "capability_count": self.capability_count,
            "findings": [finding.to_dict() for finding in self.findings],
            "execution_boundary": {
                "network_called": False,
                "model_or_solver_executed": False,
                "registry_files_mutated": False,
                "runtime_object_persisted": False,
            },
        }


def validate_declaration(declaration: PGIRRepresentationDeclaration) -> tuple[PGIRConformanceFinding, ...]:
    concepts = {record.concept_id for record in build_concept_registry()}
    schemas = {record.schema_id for record in build_schema_ownership_registry()}
    findings: list[PGIRConformanceFinding] = []
    if declaration.pgir_concept_id not in concepts:
        findings.append(PGIRConformanceFinding("unknown_concept", "error", f"Unknown PGIR concept: {declaration.pgir_concept_id}", "declaration"))
    if declaration.representation_schema_id not in schemas:
        findings.append(PGIRConformanceFinding("unknown_schema", "error", f"Unknown schema: {declaration.representation_schema_id}", "schema"))
    if declaration.domain_context in {"", "unavailable"}:
        findings.append(PGIRConformanceFinding("missing_domain_context", "error", "Domain context is required.", "context"))
    if declaration.pgir_concept_id == "observation" and declaration.measurement_context in {"", "unavailable"}:
        findings.append(PGIRConformanceFinding("missing_measurement_context", "error", "Observation declarations require measurement context.", "context"))
    if any("confidence" in item.lower() for item in declaration.evidence_refs):
        findings.append(PGIRConformanceFinding("global_confidence_score_rejected", "error", "Global confidence scores are not PGIR maturity evidence.", "maturity"))
    return tuple(findings)


def assess_maturity(
    declaration: PGIRRepresentationDeclaration,
    requested_maturity_level: str | None = None,
    evidence: Mapping[str, Any] | None = None,
) -> PGIRMaturityAssessment:
    requested = _normalize_maturity_level(requested_maturity_level or declaration.current_maturity_level)
    evidence_keys = set(str(key) for key, value in (evidence or {}).items() if bool(value))
    current_index = MATURITY_ORDER[declaration.current_maturity_level]
    requested_index = MATURITY_ORDER[requested]
    missing: list[str] = []
    findings = list(validate_declaration(declaration))
    if requested_index > current_index:
        for level in VALID_MATURITY_LEVELS[current_index + 1 : requested_index + 1]:
            missing.extend(item for item in PROMOTION_REQUIREMENTS.get(level, ()) if item not in evidence_keys)
    if missing:
        findings.append(PGIRConformanceFinding("missing_promotion_evidence", "error", "Maturity promotion requires explicit evidence.", "maturity"))
    allowed = not missing and not any(finding.severity == "error" for finding in findings)
    return PGIRMaturityAssessment(
        declaration_id=declaration.declaration_id,
        current_maturity_level=declaration.current_maturity_level,
        requested_maturity_level=requested,
        resulting_maturity_level=requested if allowed else declaration.current_maturity_level,
        promotion_allowed=allowed,
        missing_evidence=tuple(sorted(set(missing))),
        findings=tuple(findings),
    )


def check_context_compatibility(
    declaration: PGIRRepresentationDeclaration,
    requested_context: Mapping[str, Any],
) -> PGIRContextCompatibilityResult:
    requested_label = str(requested_context.get("context_id", requested_context.get("target_context", "unspecified")))
    requested_concept = str(requested_context.get("requested_concept", declaration.pgir_concept_id))
    requested_mechanism = str(requested_context.get("mechanism_context", "not_applicable"))
    findings: list[PGIRConformanceFinding] = []
    status = "compatible"
    if declaration.pgir_concept_id == "observation" and requested_concept in {"state", "field"}:
        status = "prohibited_reuse"
        findings.append(PGIRConformanceFinding("observation_not_state", "error", "Observation cannot be reused directly as State or Field.", "context"))
    if "internal_concentration" in requested_label or requested_mechanism in {"diffusion_execution", "particle_diffusion"}:
        status = "prohibited_reuse"
        findings.append(PGIRConformanceFinding("terminal_measurement_not_internal_field", "error", "Terminal battery measurements are not internal concentration fields.", "context"))
    if declaration.temporal_context == "post_test" and requested_context.get("prediction_timing") == "pre_test":
        status = "prohibited_reuse"
        findings.append(PGIRConformanceFinding("post_test_pre_test_leakage", "error", "Post-test representation cannot be reused for pre-test prediction context.", "context"))
    if declaration.domain_context == "unavailable":
        status = "insufficient_context"
        findings.append(PGIRConformanceFinding("insufficient_domain_context", "error", "Domain context is unavailable.", "context"))
    return PGIRContextCompatibilityResult(
        status=status,
        source_context=declaration.domain_context,
        requested_context=requested_label,
        findings=tuple(findings),
    )


def validate_transition(config: Mapping[str, Any]) -> PGIRTransitionAssessment:
    transition_id = str(config.get("transition_id", ""))
    if transition_id not in REGISTERED_TRANSITIONS:
        return PGIRTransitionAssessment(
            transition_id=transition_id or "unregistered",
            input_concept=str(config.get("input_concept", "unknown")),
            output_concept=str(config.get("output_concept", "unknown")),
            transition_allowed=False,
            maturity_result="raw_observed",
            findings=(PGIRConformanceFinding("unregistered_transition", "error", "Transition requires a registered operator.", "transition"),),
        )
    spec = REGISTERED_TRANSITIONS[transition_id]
    metadata = set(_as_tuple(config.get("metadata_available")))
    missing = sorted(set(spec["required_metadata"]) - metadata)
    findings: list[PGIRConformanceFinding] = []
    if missing:
        findings.append(PGIRConformanceFinding("missing_transition_metadata", "error", f"Missing transition metadata: {missing}", "transition"))
    output_context = str(config.get("output_context", ""))
    if transition_id == "battery_cycle_observation_to_operational_state_v1" and output_context not in {"operational_state_summary", "battery_operational_state_summary"}:
        findings.append(PGIRConformanceFinding("latent_state_transition_rejected", "error", "Battery Observation may only become an operational state summary in v2.3.2.", "transition"))
    return PGIRTransitionAssessment(
        transition_id=transition_id,
        input_concept=str(spec["input_concept"]),
        output_concept=str(spec["output_concept"]),
        transition_allowed=not findings,
        maturity_result=str(spec["maturity_result"]) if not findings else "raw_observed",
        findings=tuple(findings),
    )


def evaluate_capability(
    declaration: PGIRRepresentationDeclaration,
    capability_id: str,
    context: Mapping[str, Any] | None = None,
) -> PGIROperatorEligibilityResult:
    rule = CAPABILITY_REQUIREMENTS.get(capability_id)
    if rule is None:
        return PGIROperatorEligibilityResult(
            capability_id=capability_id,
            status="blocked_unknown_capability",
            minimum_maturity="unavailable",
            current_maturity=declaration.current_maturity_level,
            findings=(PGIRConformanceFinding("unknown_capability", "error", f"Unknown capability: {capability_id}", "capability"),),
        )
    minimum = str(rule["minimum_maturity"])
    findings: list[PGIRConformanceFinding] = []
    status = "eligible"
    if MATURITY_ORDER[declaration.current_maturity_level] < MATURITY_ORDER[minimum]:
        status = "blocked_low_maturity"
        findings.append(PGIRConformanceFinding("maturity_below_capability_requirement", "error", f"{capability_id} requires {minimum}.", "capability"))
    context_keys = set((context or {}).keys())
    missing_context = sorted(set(rule.get("required_context", ())) - context_keys)
    if missing_context:
        status = "blocked_missing_context"
        findings.append(PGIRConformanceFinding("missing_capability_context", "error", f"Missing capability context: {missing_context}", "capability"))
    return PGIROperatorEligibilityResult(
        capability_id=capability_id,
        status=status,
        minimum_maturity=minimum,
        current_maturity=declaration.current_maturity_level,
        findings=tuple(findings),
    )


def conformance_summary(
    declarations: tuple[PGIRRepresentationDeclaration, ...],
    maturity_assessments: tuple[PGIRMaturityAssessment, ...] = (),
    transitions: tuple[PGIRTransitionAssessment, ...] = (),
    capability_results: tuple[PGIROperatorEligibilityResult, ...] = (),
    context_results: tuple[PGIRContextCompatibilityResult, ...] = (),
) -> PGIRConformanceSummary:
    findings: list[PGIRConformanceFinding] = []
    for declaration in declarations:
        findings.extend(validate_declaration(declaration))
    for item in maturity_assessments:
        findings.extend(item.findings)
    for item in transitions:
        findings.extend(item.findings)
    for item in capability_results:
        findings.extend(item.findings)
    for item in context_results:
        findings.extend(item.findings)
    blocked_promotions = sum(not item.promotion_allowed for item in maturity_assessments)
    incompatible_contexts = sum(item.status in {"incompatible", "prohibited_reuse", "insufficient_context"} for item in context_results)
    valid = not any(finding.severity == "error" for finding in findings)
    return PGIRConformanceSummary(
        status="valid" if valid else "blocked",
        valid=valid,
        declaration_count=len(declarations),
        blocked_promotion_count=blocked_promotions,
        incompatible_context_count=incompatible_contexts,
        transition_count=len(transitions),
        capability_count=len(capability_results),
        findings=tuple(findings),
    )


def load_declaration(path: str | Path) -> PGIRRepresentationDeclaration:
    with Path(path).open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("PGIR representation declaration must be a JSON object")
    return PGIRRepresentationDeclaration.from_mapping(payload)


def canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_json_safe(payload), indent=2, sort_keys=True) + "\n"
