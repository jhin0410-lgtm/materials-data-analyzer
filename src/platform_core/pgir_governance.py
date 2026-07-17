"""Read-only PGIR architecture and representation governance metadata.

PGIR in v2.3.1 is a governance layer over the existing platform. It does not
introduce a new runtime entity hierarchy, execute physics operators, run
models, acquire data, or persist live Python objects.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping


PGIR_GOVERNANCE_VERSION = "2.3.1"
PGIR_REGISTRY_STATUS = "accepted_for_v2_3"

VALID_MATURITY_LEVELS = (
    "raw_observed",
    "schema_valid",
    "semantically_mapped",
    "dimensionally_valid",
    "physically_admissible",
    "mechanism_compatible",
    "scientifically_evaluated",
    "independently_validated",
    "production_validated",
)

VALID_OPERATOR_ROLES = (
    "Evaluator",
    "Transformer",
    "Propagator",
    "Estimator",
    "Inverter",
    "Calibrator",
    "Renderer",
)

VALID_CAPABILITY_STAGES = (
    "concept_defined",
    "schema_defined",
    "adapter_available",
    "artifact_generated",
    "operator_executed",
    "scientifically_evaluated",
    "cross_domain_reused",
    "independently_validated",
    "production_validated",
)

VALID_MAPPING_STATUSES = (
    "exact",
    "partial",
    "compatibility_adapter_required",
    "future_only",
)

VALID_READINESS_STATUSES = (
    "pgir_governance_ready",
    "pgir_governance_ready_with_gaps",
    "inconsistent_current_architecture",
    "blocked_schema_ownership",
    "blocked_mapping_conflict",
    "blocked_compatibility_risk",
)

CURRENT_IMPLEMENTATION_REFS = (
    "src.platform_core.scientific_entities.ScientificEntity",
    "src.platform_core.scientific_entities.EntityRecord",
    "src.platform_core.scientific_entities.MaterialCompositionEntity",
    "src.platform_core.scientific_entities.CrystalStructureEntity",
    "src.platform_core.scientific_entities.MeasurementSeriesEntity",
    "src.platform_core.scientific_entities.StateEntity",
    "src.platform_core.scientific_entities.TrajectoryEntity",
    "src.platform_core.scientific_entities.GraphEntity",
    "src.platform_core.quantities.ScientificQuantity",
    "src.platform_core.uncertainty.UncertaintySpec",
    "src.platform_core.scientific_relations.ScientificRelation",
    "src.platform_core.scientific_operator_registry.ScientificOperatorMetadata",
    "src.platform_core.scientific_interfaces.FeatureBuilder",
    "src.platform_core.scientific_interfaces.Predictor",
    "src.platform_core.scientific_interfaces.EntityReader",
    "src.platform_core.entity_serialization",
    "src.platform_core.run_registry",
    "src.platform_core.scientific_trust",
    "src.platform_core.materials_project_adapters",
    "src.platform_core.entity_adapters",
    "src.platform_core.artifacts",
    "src.platform_core.report_generator",
)


def _as_tuple(values: tuple[str, ...] | list[str] | None = None) -> tuple[str, ...]:
    return tuple(str(value) for value in (values or ()))


def _safe_identifier(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} is required")
    if any(part in value for part in ("/", "\\", "..", ":")):
        raise ValueError(f"{field_name} must be an identifier, not a path")
    return value.strip()


def _json_safe(value: Any, *, location: str = "value") -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item, location=f"{location}.{key}") for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, tuple):
        return [_json_safe(item, location=f"{location}[]") for item in value]
    if isinstance(value, list):
        return [_json_safe(item, location=f"{location}[]") for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise ValueError(f"{location} contains unsupported JSON value type: {type(value).__name__}")


@dataclass(frozen=True)
class PGIRConceptRecord:
    concept_id: str
    concept_version: str
    definition: str
    parent_concept: str | None = None
    required_metadata: tuple[str, ...] = ()
    optional_metadata: tuple[str, ...] = ()
    maturity_requirements: tuple[str, ...] = ()
    allowed_operator_roles: tuple[str, ...] = ()
    persistence_policy: str = "json_safe_metadata_or_artifact_reference"
    uncertainty_policy: str = "explicit_structured_uncertainty_or_unavailable"
    provenance_policy: str = "source_and_transformation_lineage_required"
    current_implementation_refs: tuple[str, ...] = ()
    status: str = "concept_defined"
    prohibited_interpretations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _safe_identifier(self.concept_id, "concept_id")
        for level in self.maturity_requirements:
            if level not in VALID_MATURITY_LEVELS:
                raise ValueError(f"unsupported maturity level for {self.concept_id}: {level}")
        for role in self.allowed_operator_roles:
            if role not in VALID_OPERATOR_ROLES:
                raise ValueError(f"unsupported operator role for {self.concept_id}: {role}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "concept_id": self.concept_id,
            "concept_version": self.concept_version,
            "definition": self.definition,
            "parent_concept": self.parent_concept,
            "required_metadata": list(self.required_metadata),
            "optional_metadata": list(self.optional_metadata),
            "maturity_requirements": list(self.maturity_requirements),
            "allowed_operator_roles": list(self.allowed_operator_roles),
            "persistence_policy": self.persistence_policy,
            "uncertainty_policy": self.uncertainty_policy,
            "provenance_policy": self.provenance_policy,
            "current_implementation_refs": list(self.current_implementation_refs),
            "status": self.status,
            "prohibited_interpretations": list(self.prohibited_interpretations),
        }


@dataclass(frozen=True)
class PGIRMappingRecord:
    implementation_ref: str
    implementation_role: str
    pgir_concepts: tuple[str, ...]
    mapping_status: str
    runtime_role: str
    persisted_representation: str
    schema_id: str | None
    schema_version: str | None
    mutable_policy: str
    ownership_module: str
    supported_payload_scale: str
    provenance_support: str
    uncertainty_support: str
    current_domain_use: tuple[str, ...]
    current_limitations: tuple[str, ...]
    prohibited_promotions: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.implementation_ref not in CURRENT_IMPLEMENTATION_REFS:
            raise ValueError(f"unknown implementation_ref: {self.implementation_ref}")
        if self.mapping_status not in VALID_MAPPING_STATUSES:
            raise ValueError(f"unsupported mapping_status: {self.mapping_status}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "implementation_ref": self.implementation_ref,
            "implementation_role": self.implementation_role,
            "pgir_concepts": list(self.pgir_concepts),
            "mapping_status": self.mapping_status,
            "runtime_role": self.runtime_role,
            "persisted_representation": self.persisted_representation,
            "schema_id": self.schema_id,
            "schema_version": self.schema_version,
            "mutable_policy": self.mutable_policy,
            "ownership_module": self.ownership_module,
            "supported_payload_scale": self.supported_payload_scale,
            "provenance_support": self.provenance_support,
            "uncertainty_support": self.uncertainty_support,
            "current_domain_use": list(self.current_domain_use),
            "current_limitations": list(self.current_limitations),
            "prohibited_promotions": list(self.prohibited_promotions),
        }


@dataclass(frozen=True)
class PGIRSchemaOwnershipRecord:
    schema_id: str
    current_version: str
    owner_module: str
    runtime_validator: str
    serializer: str
    migration_registry: str
    persistence_location: str
    compatibility_status: str
    deprecation_status: str
    pgir_concept: str
    large_payload_policy: str
    security_classification: str

    def __post_init__(self) -> None:
        _safe_identifier(self.schema_id, "schema_id")
        if self.compatibility_status not in {"stable", "additive_optional_fields", "compatibility_adapter"}:
            raise ValueError(f"unsupported compatibility_status: {self.compatibility_status}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_id": self.schema_id,
            "current_version": self.current_version,
            "owner_module": self.owner_module,
            "runtime_validator": self.runtime_validator,
            "serializer": self.serializer,
            "migration_registry": self.migration_registry,
            "persistence_location": self.persistence_location,
            "compatibility_status": self.compatibility_status,
            "deprecation_status": self.deprecation_status,
            "pgir_concept": self.pgir_concept,
            "large_payload_policy": self.large_payload_policy,
            "security_classification": self.security_classification,
        }


@dataclass(frozen=True)
class PGIRCapabilityStageRecord:
    capability_id: str
    pgir_concept: str
    capability_stage: str
    current_status: str
    evidence_level: str
    current_implementation_refs: tuple[str, ...]
    future_only: bool
    model_execution_performed: bool
    scientific_claim_supported: str
    limitations: tuple[str, ...]
    prohibited_interpretations: tuple[str, ...]

    def __post_init__(self) -> None:
        _safe_identifier(self.capability_id, "capability_id")
        if self.capability_stage not in VALID_CAPABILITY_STAGES:
            raise ValueError(f"unsupported capability_stage: {self.capability_stage}")
        if self.future_only and self.capability_stage not in {"concept_defined", "schema_defined"}:
            raise ValueError("future-only capability cannot be promoted beyond schema_defined")

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "pgir_concept": self.pgir_concept,
            "capability_stage": self.capability_stage,
            "current_status": self.current_status,
            "evidence_level": self.evidence_level,
            "current_implementation_refs": list(self.current_implementation_refs),
            "future_only": self.future_only,
            "model_execution_performed": self.model_execution_performed,
            "scientific_claim_supported": self.scientific_claim_supported,
            "limitations": list(self.limitations),
            "prohibited_interpretations": list(self.prohibited_interpretations),
        }


@dataclass(frozen=True)
class PGIRGovernanceDecision:
    status: str
    valid: bool
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    gates: Mapping[str, bool] = field(default_factory=dict)
    readiness_summary: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in VALID_READINESS_STATUSES:
            raise ValueError(f"unsupported PGIR readiness status: {self.status}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": PGIR_GOVERNANCE_VERSION,
            "status": self.status,
            "valid": self.valid,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "gates": dict(self.gates),
            "readiness_summary": _json_safe(dict(self.readiness_summary), location="readiness_summary"),
        }


def pgir_principles() -> tuple[str, ...]:
    return (
        "Domain-neutral core, domain-explicit boundaries",
        "Observation is not automatically State",
        "Value is not Relation",
        "Representation is not Mechanism",
        "Artifact generation is not predictive evidence",
        "Dimensional validity is not physical correctness",
        "Physical consistency is applicability-dependent",
        "Uncertainty types must remain semantically separate",
        "Runtime objects and persisted records remain separated",
        "Every claim requires explicit evidence and context",
        "Incomplete scientific data may enter the platform with limited capabilities",
        "No universal mechanism claim without cross-domain validation",
    )


def representation_maturity_levels() -> tuple[dict[str, Any], ...]:
    definitions = (
        ("L0", "raw_observed", "Raw record or artifact; semantics may be incomplete."),
        ("L1", "schema_valid", "Structural schema valid; scientific meaning is not guaranteed."),
        ("L2", "semantically_mapped", "Variables and entities have known meaning."),
        ("L3", "dimensionally_valid", "Units and dimensions are valid."),
        ("L4", "physically_admissible", "Bounded registered physical constraints are satisfied."),
        ("L5", "mechanism_compatible", "Required state, parameters, conditions and applicability are available."),
        ("L6", "scientifically_evaluated", "Registered relation or operator executed and uncertainty/findings recorded."),
        ("L7", "independently_validated", "Independent dataset, experiment or computation evidence exists."),
        ("L8", "production_validated", "Deployment-specific validation and governance completed."),
    )
    return tuple(
        {
            "level": level,
            "maturity_id": maturity_id,
            "definition": definition,
            "promotion_policy": "explicit_evidence_required_no_automatic_file_format_promotion",
        }
        for level, maturity_id, definition in definitions
    )


def build_concept_registry() -> tuple[PGIRConceptRecord, ...]:
    return (
        PGIRConceptRecord(
            "physical_entity",
            "1",
            "Identifiable physical object or system such as a material, specimen, component or device.",
            required_metadata=("entity_id", "domain_context", "provenance"),
            optional_metadata=("composition", "structure", "component_id", "artifact_ref"),
            maturity_requirements=("semantically_mapped",),
            allowed_operator_roles=("Evaluator", "Transformer"),
            current_implementation_refs=("src.platform_core.scientific_entities.ScientificEntity",),
            prohibited_interpretations=("database row identity is not automatically physical identity",),
        ),
        PGIRConceptRecord(
            "observation",
            "1",
            "Measurement or recorded evidence with observation context; not automatically a complete state.",
            required_metadata=("observed_quantity", "measurement_context", "provenance"),
            optional_metadata=("instrument", "calibration", "time", "location"),
            maturity_requirements=("schema_valid", "semantically_mapped"),
            allowed_operator_roles=("Evaluator", "Transformer"),
            current_implementation_refs=("src.platform_core.scientific_entities.MeasurementSeriesEntity",),
            prohibited_interpretations=("measured output is not automatically latent physical state",),
        ),
        PGIRConceptRecord(
            "state",
            "1",
            "Variables sufficient for a defined model or mechanism context; may be observed, estimated or latent.",
            required_metadata=("state_variables", "context", "sufficiency_assumptions"),
            optional_metadata=("boundary_condition_refs", "initial_condition_refs", "uncertainty"),
            maturity_requirements=("semantically_mapped", "dimensionally_valid"),
            allowed_operator_roles=("Evaluator", "Propagator"),
            current_implementation_refs=("src.platform_core.scientific_entities.StateEntity",),
            prohibited_interpretations=("all table rows are not automatically states",),
        ),
        PGIRConceptRecord(
            "field",
            "1",
            "Quantity distributed over space, time or another coordinate domain.",
            parent_concept="state",
            required_metadata=("quantity_shape", "axes", "coordinate_system", "unit", "basis_or_frame"),
            optional_metadata=("discretization", "artifact_ref", "boundary_condition_refs"),
            maturity_requirements=("semantically_mapped", "dimensionally_valid"),
            allowed_operator_roles=("Evaluator", "Propagator", "Renderer"),
            current_implementation_refs=("src.platform_core.scientific_entities.StateEntity",),
            prohibited_interpretations=("large arrays are not stored inline", "tensor values require frame metadata"),
        ),
        PGIRConceptRecord(
            "parameter",
            "1",
            "Model, material or system parameter fixed or estimated within a defined execution.",
            required_metadata=("parameter_id", "unit", "context", "provenance"),
            optional_metadata=("estimation_method", "uncertainty"),
            maturity_requirements=("semantically_mapped", "dimensionally_valid"),
            allowed_operator_roles=("Evaluator", "Propagator", "Calibrator"),
            current_implementation_refs=("src.platform_core.quantities.ScientificQuantity",),
            prohibited_interpretations=("fitted parameter is not universal without validation context",),
        ),
        PGIRConceptRecord(
            "control",
            "1",
            "Externally selected input or intervention.",
            required_metadata=("control_id", "availability_time", "domain_context"),
            optional_metadata=("safety_constraints", "equipment_constraints"),
            maturity_requirements=("semantically_mapped",),
            allowed_operator_roles=("Evaluator", "Propagator"),
            prohibited_interpretations=("observed correlation is not intervention evidence",),
        ),
        PGIRConceptRecord(
            "initial_condition",
            "1",
            "State specification at a reference time for a bounded mechanism context.",
            parent_concept="state",
            required_metadata=("reference_time", "state_variable_refs", "context"),
            optional_metadata=("uncertainty", "source_observation_refs"),
            maturity_requirements=("dimensionally_valid",),
            allowed_operator_roles=("Evaluator", "Propagator"),
            current_implementation_refs=("src.platform_core.scientific_entities.StateEntity",),
            prohibited_interpretations=("first row is not automatically an initial condition",),
        ),
        PGIRConceptRecord(
            "boundary_condition",
            "1",
            "Condition applied at a spatial, temporal or system boundary.",
            parent_concept="state",
            required_metadata=("boundary_id", "boundary_type", "condition_value_or_ref", "applicability"),
            optional_metadata=("geometry", "flux", "interface_ref"),
            maturity_requirements=("dimensionally_valid",),
            allowed_operator_roles=("Evaluator", "Propagator"),
            current_implementation_refs=("src.platform_core.scientific_entities.StateEntity",),
            prohibited_interpretations=("global average is not automatically a boundary condition",),
        ),
        PGIRConceptRecord(
            "relation",
            "1",
            "Algebraic, constitutive, conservation, kinetic, differential, statistical or transformation relationship.",
            required_metadata=("relation_id", "relation_category", "input_roles", "output_roles", "assumptions"),
            optional_metadata=("mechanism_family", "equation_display", "operator_refs"),
            maturity_requirements=("semantically_mapped",),
            allowed_operator_roles=("Evaluator", "Transformer", "Propagator"),
            current_implementation_refs=("src.platform_core.scientific_relations.ScientificRelation",),
            prohibited_interpretations=("equation display is not arbitrary executable code",),
        ),
        PGIRConceptRecord(
            "operator",
            "1",
            "Registered executable implementation metadata for a relation or transformation.",
            required_metadata=("operator_id", "role", "input_schema", "output_schema", "side_effect_policy"),
            optional_metadata=("uncertainty_behavior", "evidence_level"),
            maturity_requirements=("schema_valid",),
            allowed_operator_roles=VALID_OPERATOR_ROLES,
            current_implementation_refs=("src.platform_core.scientific_operator_registry.ScientificOperatorMetadata",),
            prohibited_interpretations=("registry metadata is not permission for arbitrary dynamic import",),
        ),
        PGIRConceptRecord(
            "model",
            "1",
            "Bounded collection of relations, operators and assumptions.",
            required_metadata=("model_id", "relations", "assumptions", "validation_context"),
            optional_metadata=("parameters", "calibration_data", "limitations"),
            maturity_requirements=("mechanism_compatible",),
            allowed_operator_roles=("Evaluator", "Propagator", "Calibrator"),
            prohibited_interpretations=("registered model is not production readiness",),
        ),
        PGIRConceptRecord(
            "result",
            "1",
            "Output quantity, entity or artifact with context, uncertainty and provenance.",
            required_metadata=("result_id", "producer", "context", "provenance"),
            optional_metadata=("uncertainty", "claim_boundary", "artifact_ref"),
            maturity_requirements=("schema_valid",),
            allowed_operator_roles=("Evaluator", "Transformer", "Propagator"),
            current_implementation_refs=("src.platform_core.run_registry", "src.platform_core.report_generator"),
            prohibited_interpretations=("artifact generation is not predictive evidence",),
        ),
        PGIRConceptRecord(
            "uncertainty",
            "1",
            "Structured uncertainty, limitation, sensitivity or unavailable state.",
            required_metadata=("kind", "reason_or_value", "source"),
            optional_metadata=("interval", "confidence_level", "method"),
            maturity_requirements=("schema_valid",),
            allowed_operator_roles=("Evaluator", "Propagator"),
            current_implementation_refs=("src.platform_core.uncertainty.UncertaintySpec",),
            prohibited_interpretations=("unavailable uncertainty is not zero uncertainty", "confidence score is not universal truth"),
        ),
        PGIRConceptRecord(
            "provenance",
            "1",
            "Source, acquisition, transformation and execution lineage.",
            required_metadata=("source", "transformation", "checksum_or_manifest"),
            optional_metadata=("code_commit", "operator_ref", "timestamp"),
            maturity_requirements=("schema_valid",),
            allowed_operator_roles=("Evaluator",),
            current_implementation_refs=("src.platform_core.run_registry", "src.platform_core.artifacts"),
            prohibited_interpretations=("local absolute path is not portable provenance",),
        ),
        PGIRConceptRecord(
            "context",
            "1",
            "Domain, prediction timing, scale, assumptions and validity conditions for an entity, relation or result.",
            required_metadata=("context_id", "domain_context", "availability_timing", "validity_conditions"),
            optional_metadata=("prediction_context", "scale_context", "validation_context"),
            maturity_requirements=("semantically_mapped",),
            allowed_operator_roles=("Evaluator", "Transformer", "Propagator"),
            current_implementation_refs=("src.platform_core.scientific_trust",),
            prohibited_interpretations=("known-structure context cannot be reused as pre-structure context without a boundary",),
        ),
    )


def build_current_mapping_matrix() -> tuple[PGIRMappingRecord, ...]:
    common = {
        "mutable_policy": "runtime_helpers_are_ephemeral_persisted_records_are_immutable",
        "supported_payload_scale": "small_json_inline_large_payloads_artifact_backed",
        "provenance_support": "explicit_refs_or_manifest_refs",
    }
    return (
        PGIRMappingRecord(
            "src.platform_core.scientific_entities.ScientificEntity",
            "base runtime helper for JSON-safe scientific entity records",
            ("physical_entity", "observation", "state", "result"),
            "partial",
            "runtime helper and persisted record constructor",
            "JSON object via EntityRecord or artifact-backed record",
            "scientific_entity_schema_v2",
            "2.2.2",
            ownership_module="src.platform_core.scientific_entities",
            uncertainty_support="quantity_fields or explicit uncertainty refs",
            current_domain_use=("materials", "battery", "xrd", "reliability_metadata"),
            current_limitations=("not a complete physical state ontology", "does not execute mechanisms"),
            prohibited_promotions=("production physical state", "universal entity ontology"),
            **common,
        ),
        PGIRMappingRecord(
            "src.platform_core.scientific_entities.EntityRecord",
            "persisted JSON-safe entity record",
            ("result", "provenance"),
            "exact",
            "serialized record wrapper",
            "canonical JSON-safe mapping plus checksum",
            "scientific_entity_schema_v2",
            "2.2.2",
            ownership_module="src.platform_core.scientific_entities",
            uncertainty_support="preserved from entity payload",
            current_domain_use=("entity_serialization",),
            current_limitations=("not a live Python object",),
            prohibited_promotions=("runtime object persistence",),
            **common,
        ),
        PGIRMappingRecord(
            "src.platform_core.scientific_entities.MaterialCompositionEntity",
            "composition entity type",
            ("physical_entity",),
            "partial",
            "entity_type specialization",
            "ScientificEntity attributes",
            "scientific_entity_schema_v2",
            "2.2.2",
            ownership_module="src.platform_core.scientific_entities",
            uncertainty_support="unavailable unless source provides uncertainty",
            current_domain_use=("materials_project",),
            current_limitations=("composition is not structure", "composition is not mechanism"),
            prohibited_promotions=("structure-aware evidence", "physics-constrained model success"),
            **common,
        ),
        PGIRMappingRecord(
            "src.platform_core.scientific_entities.CrystalStructureEntity",
            "crystal structure entity type",
            ("physical_entity", "state"),
            "partial",
            "entity_type specialization",
            "ScientificEntity attributes with lattice/site metadata",
            "scientific_entity_schema_v2",
            "2.2.2",
            ownership_module="src.platform_core.scientific_entities",
            uncertainty_support="unavailable unless source provides uncertainty",
            current_domain_use=("materials_project_known_structure",),
            current_limitations=("relaxed structure changes prediction context", "not DFT replacement"),
            prohibited_promotions=("pre_structure_screening_input", "phase_identification_claim"),
            **common,
        ),
        PGIRMappingRecord(
            "src.platform_core.scientific_entities.MeasurementSeriesEntity",
            "measurement series entity type",
            ("observation",),
            "exact",
            "entity_type specialization",
            "ScientificEntity attributes with axis metadata",
            "scientific_entity_schema_v2",
            "2.2.2",
            ownership_module="src.platform_core.scientific_entities",
            uncertainty_support="series uncertainty metadata or unavailable",
            current_domain_use=("battery_trajectories_future", "xrd_patterns_future"),
            current_limitations=("large arrays should be artifact-backed",),
            prohibited_promotions=("complete state without mechanism context",),
            **common,
        ),
        PGIRMappingRecord(
            "src.platform_core.scientific_entities.StateEntity",
            "state metadata entity type",
            ("state", "field", "initial_condition", "boundary_condition"),
            "partial",
            "entity_type specialization",
            "ScientificEntity attributes with state variables and conditions",
            "scientific_entity_schema_v2",
            "2.2.2",
            ownership_module="src.platform_core.scientific_entities",
            uncertainty_support="state variable uncertainty metadata or unavailable",
            current_domain_use=("dynamic_physics_future",),
            current_limitations=("not yet tied to a solver", "field payloads artifact-backed only"),
            prohibited_promotions=("solver-ready state without sufficiency assumptions",),
            **common,
        ),
        PGIRMappingRecord(
            "src.platform_core.scientific_entities.TrajectoryEntity",
            "ordered state sequence metadata",
            ("observation", "state", "result"),
            "partial",
            "entity_type specialization",
            "artifact-backed ordered state references",
            "trajectory_entity_schema_v2",
            "2.2.2",
            ownership_module="src.platform_core.scientific_entities",
            uncertainty_support="per-state or trajectory-level metadata",
            current_domain_use=("battery_trajectory_future",),
            current_limitations=("not a fitted degradation mechanism",),
            prohibited_promotions=("RUL model evidence",),
            **common,
        ),
        PGIRMappingRecord(
            "src.platform_core.scientific_entities.GraphEntity",
            "graph representation artifact metadata",
            ("result", "physical_entity"),
            "partial",
            "entity_type specialization",
            "artifact-backed graph metadata",
            "graph_entity_schema_v2",
            "2.2.4",
            ownership_module="src.platform_core.scientific_entities",
            uncertainty_support="graph builder limitation metadata",
            current_domain_use=("materials_periodic_graph_artifacts",),
            current_limitations=("representation only", "not GNN evidence"),
            prohibited_promotions=("graph neural network claim", "causal relation graph"),
            **common,
        ),
        PGIRMappingRecord(
            "src.platform_core.quantities.ScientificQuantity",
            "structured quantity record",
            ("parameter", "field", "result"),
            "partial",
            "runtime quantity helper",
            "JSON object",
            "scientific_quantity_schema_v2",
            "2.2.2",
            ownership_module="src.platform_core.quantities",
            uncertainty_support="explicit UncertaintySpec or unavailable",
            current_domain_use=("xrd", "materials_properties"),
            current_limitations=("dimensional validity is not physical correctness",),
            prohibited_promotions=("universal physical truth",),
            **common,
        ),
        PGIRMappingRecord(
            "src.platform_core.uncertainty.UncertaintySpec",
            "structured uncertainty record",
            ("uncertainty",),
            "exact",
            "runtime uncertainty helper",
            "JSON object",
            "scientific_uncertainty_schema_v2",
            "2.2.2",
            ownership_module="src.platform_core.uncertainty",
            uncertainty_support="self-describing",
            current_domain_use=("xrd", "materials_prediction_intervals"),
            current_limitations=("no arbitrary confidence score",),
            prohibited_promotions=("zero uncertainty when unavailable",),
            **common,
        ),
        PGIRMappingRecord(
            "src.platform_core.scientific_relations.ScientificRelation",
            "registered relation metadata",
            ("relation",),
            "exact",
            "metadata record",
            "JSON-safe metadata",
            "scientific_relation_schema_v2",
            "2.2.2",
            ownership_module="src.platform_core.scientific_relations",
            uncertainty_support="relation uncertainty policy metadata",
            current_domain_use=("xrd", "graph_construction_metadata"),
            current_limitations=("equation display is display-only",),
            prohibited_promotions=("arbitrary equation execution",),
            **common,
        ),
        PGIRMappingRecord(
            "src.platform_core.scientific_operator_registry.ScientificOperatorMetadata",
            "operator metadata registry entry",
            ("operator",),
            "exact",
            "metadata record",
            "registered JSON-safe operator metadata",
            "scientific_operator_registry_schema_v2",
            "2.2.4",
            ownership_module="src.platform_core.scientific_operator_registry",
            uncertainty_support="declared uncertainty behavior",
            current_domain_use=("xrd", "materials_structure_adapters"),
            current_limitations=("only allowlisted operators", "no arbitrary callable execution"),
            prohibited_promotions=("unregistered dynamic operator", "general solver"),
            **common,
        ),
    )


def build_representation_governance() -> dict[str, Any]:
    return {
        "schema_version": PGIR_GOVERNANCE_VERSION,
        "status": PGIR_REGISTRY_STATUS,
        "rules": [
            "each schema has one owning module",
            "each schema has stable schema_id",
            "schema version is separate from product version",
            "backward-compatible optional fields preferred",
            "breaking changes require migration",
            "future unsupported versions rejected",
            "deprecated fields retain documented read period",
            "silent field dropping prohibited",
            "logical checksums use canonical content",
            "large payload stored as artifact reference",
            "unit and uncertainty semantics may not be weakened during migration",
            "provenance references must survive migration",
            "runtime implementation class is not part of persisted identity",
        ],
        "optional_pgir_metadata": ["pgir_role", "representation_maturity", "context_refs"],
        "compatibility_policy": {
            "existing_scientific_entity_remains_valid": True,
            "mass_rename_prohibited": True,
            "persisted_schema_ids_remain_stable": True,
            "tracked_artifact_checksum_changes": "not_allowed_for_v2_3_1",
        },
        "security_policy": {
            "live_python_object_persistence": False,
            "binary_python_object_serialization": False,
            "arbitrary_dynamic_import": False,
            "row_level_payload_required": False,
        },
    }


def build_schema_ownership_registry() -> tuple[PGIRSchemaOwnershipRecord, ...]:
    return (
        PGIRSchemaOwnershipRecord("scientific_entity_schema_v2", "2.2.2", "src.platform_core.scientific_entities", "validate_entity_payload", "entity_serialization.serialize_entity", "schema_evolution", "data/platform/scientific_entity_schema_v2.json", "additive_optional_fields", "active", "physical_entity", "artifact_refs_for_large_payloads", "tracked_compact_metadata"),
        PGIRSchemaOwnershipRecord("scientific_quantity_schema_v2", "2.2.2", "src.platform_core.quantities", "validate_quantity_payload", "quantity_from_payload", "schema_evolution", "data/platform/scientific_quantity_schema_v2.json", "stable", "active", "parameter", "small_inline_only", "tracked_compact_metadata"),
        PGIRSchemaOwnershipRecord("scientific_uncertainty_schema_v2", "2.2.2", "src.platform_core.uncertainty", "uncertainty_from_payload", "UncertaintySpec.to_dict", "schema_evolution", "data/platform/scientific_uncertainty_schema_v2.json", "stable", "active", "uncertainty", "small_inline_only", "tracked_compact_metadata"),
        PGIRSchemaOwnershipRecord("scientific_relation_schema_v2", "2.2.2", "src.platform_core.scientific_relations", "default_scientific_relations", "ScientificRelation.to_dict", "schema_evolution", "data/platform/scientific_relation_schema_v2.json", "stable", "active", "relation", "metadata_only", "tracked_compact_metadata"),
        PGIRSchemaOwnershipRecord("scientific_operator_registry_schema_v2", "2.2.4", "src.platform_core.scientific_operator_registry", "ScientificOperatorRegistry.validate", "ScientificOperatorMetadata.to_dict", "schema_evolution", "data/platform/scientific_operator_registry_schema_v2.json", "additive_optional_fields", "active", "operator", "metadata_only", "tracked_compact_metadata"),
        PGIRSchemaOwnershipRecord("graph_entity_schema_v2", "2.2.4", "src.platform_core.scientific_entities", "validate_entity_payload", "entity_serialization.serialize_entity", "schema_evolution", "data/platform/graph_entity_schema_v2.json", "additive_optional_fields", "active", "result", "artifact_refs_for_nodes_edges", "tracked_compact_metadata"),
        PGIRSchemaOwnershipRecord("trajectory_entity_schema_v2", "2.2.2", "src.platform_core.scientific_entities", "validate_entity_payload", "entity_serialization.serialize_entity", "schema_evolution", "data/platform/trajectory_entity_schema_v2.json", "additive_optional_fields", "active", "state", "artifact_refs_for_large_series", "tracked_compact_metadata"),
        PGIRSchemaOwnershipRecord("scientific_execution_result_schema_v2", "2.1.5", "src.platform_core.scientific_execution", "validate_scientific_result", "ScientificExecutionResult.to_dict", "run_registry", "data/platform/scientific_execution_result_schema_v2.json", "compatibility_adapter", "active", "result", "local_outputs_for_reports", "local_or_tracked_compact_metadata"),
        PGIRSchemaOwnershipRecord("scientific_trust_evaluation_schema_v2", "2.1.5", "src.platform_core.scientific_trust", "scientific_trust_validate", "ScientificTrustEvaluation.to_dict", "run_registry", "data/platform/scientific_trust_evaluation_schema_v2.json", "stable", "active", "result", "metadata_only", "tracked_compact_metadata"),
        PGIRSchemaOwnershipRecord("materials_prediction_context_registry_v2", "2.2.6", "src.platform_core.v2_2_trust_closeout", "build_prediction_context_registry", "canonical_json", "none", "data/platform/materials_prediction_context_registry_v2.json", "stable", "active", "context", "metadata_only", "tracked_compact_metadata"),
        PGIRSchemaOwnershipRecord("platform_report_schema_v2", "2.0", "src.platform_core.report_generator", "validate_report_config", "render_report_json", "none", "data/platform/platform_report_schema_v2.json", "additive_optional_fields", "active", "result", "local_outputs_under_outputs_platform_reports", "local_only_report"),
    )


def build_capability_stage_registry() -> tuple[PGIRCapabilityStageRecord, ...]:
    return (
        PGIRCapabilityStageRecord("scientific_entity_records", "physical_entity", "schema_defined", "active", "schema_and_validator_available", ("src.platform_core.scientific_entities.ScientificEntity",), False, False, "metadata_contract_only", ("not a complete state ontology",), ("universal physics ontology",)),
        PGIRCapabilityStageRecord("graph_entity_artifact", "result", "artifact_generated", "v2_2_limited", "representation_artifact_generated", ("src.platform_core.scientific_entities.GraphEntity",), False, False, "representation_only", ("no GNN model was run", "not used as predictive evidence"), ("GNN evidence", "causal graph")),
        PGIRCapabilityStageRecord("propagator_operator_role", "operator", "concept_defined", "future_only", "contract_only", ("src.platform_core.scientific_interfaces.Predictor",), True, False, "unsupported_future_capability", ("no PDE/ODE solver in v2.3.1",), ("diffusion simulation", "physics loss", "PINN")),
        PGIRCapabilityStageRecord("composition_feature_candidates", "result", "scientifically_evaluated", "evaluated_negative", "v2_2_1_performance_degraded", ("src.analyzers.materials_physics_features",), False, True, "predictive_value_not_supported", ("composition-derived physics features degraded primary validation",), ("physics-aware model success", "representative model")),
        PGIRCapabilityStageRecord("structure_descriptor_candidates", "result", "scientifically_evaluated", "evaluated_limited", "v2_2_5_structure_predictive_value_limited", ("src.analyzers.materials_structure_prediction",), False, True, "limited_known_structure_evidence", ("known-structure context differs from pre-structure screening",), ("GNN evidence", "DFT replacement", "general structure-aware superiority")),
        PGIRCapabilityStageRecord("bounded_scientific_execution", "operator", "operator_executed", "active_bounded", "XRD scalar consistency examples", ("src.platform_core.scientific_execution",), False, False, "bounded_consistency_evidence_only", ("no arbitrary equation execution",), ("general solver", "phase identification")),
        PGIRCapabilityStageRecord("pgir_governance_registry", "provenance", "schema_defined", "active", "v2_3_1_governance_ready", ("src.platform_core.pgir_governance",), False, False, "governance_contract_only", ("no runtime rewrite",), ("new predictive result", "solver readiness")),
    )


def validate_mapping_matrix(records: tuple[PGIRMappingRecord, ...] | None = None) -> dict[str, Any]:
    records = records or build_current_mapping_matrix()
    concept_ids = {record.concept_id for record in build_concept_registry()}
    errors: list[str] = []
    seen_refs: set[str] = set()
    for record in records:
        if record.implementation_ref in seen_refs:
            errors.append(f"duplicate_implementation_ref:{record.implementation_ref}")
        seen_refs.add(record.implementation_ref)
        for concept in record.pgir_concepts:
            if concept not in concept_ids:
                errors.append(f"{record.implementation_ref}:unknown_concept:{concept}")
        for promotion in record.prohibited_promotions:
            if "production" in promotion and record.mapping_status == "exact":
                errors.append(f"{record.implementation_ref}:exact_mapping_cannot_imply_production")
    return {
        "valid": not errors,
        "errors": errors,
        "mapping_count": len(records),
        "concept_count": len(concept_ids),
        "status": "valid" if not errors else "invalid",
    }


def validate_schema_governance(records: tuple[PGIRSchemaOwnershipRecord, ...] | None = None) -> dict[str, Any]:
    records = records or build_schema_ownership_registry()
    errors: list[str] = []
    seen: set[str] = set()
    for record in records:
        if record.schema_id in seen:
            errors.append(f"duplicate_schema_id:{record.schema_id}")
        seen.add(record.schema_id)
        if record.current_version.startswith("v"):
            errors.append(f"{record.schema_id}:schema_version_must_not_use_product_version_prefix")
        if record.large_payload_policy == "inline_large_payloads":
            errors.append(f"{record.schema_id}:large_payload_policy_unsafe")
        if record.security_classification not in {"tracked_compact_metadata", "local_or_tracked_compact_metadata", "local_only_report"}:
            errors.append(f"{record.schema_id}:unsupported_security_classification")
    return {
        "valid": not errors,
        "errors": errors,
        "schema_count": len(records),
        "owner_count": len({record.owner_module for record in records}),
        "status": "valid" if not errors else "invalid",
    }


def validate_capability_stages(records: tuple[PGIRCapabilityStageRecord, ...] | None = None) -> dict[str, Any]:
    records = records or build_capability_stage_registry()
    errors: list[str] = []
    future_only = []
    for record in records:
        if record.future_only:
            future_only.append(record.capability_id)
        if record.future_only and record.model_execution_performed:
            errors.append(f"{record.capability_id}:future_only_cannot_execute_model")
        if record.capability_id == "propagator_operator_role" and record.capability_stage != "concept_defined":
            errors.append("propagator_operator_role:must_remain_concept_defined")
        if record.capability_id == "graph_entity_artifact" and record.scientific_claim_supported != "representation_only":
            errors.append("graph_entity_artifact:must_remain_representation_only")
    return {
        "valid": not errors,
        "errors": errors,
        "capability_count": len(records),
        "future_only_capabilities": future_only,
        "status": "valid" if not errors else "invalid",
    }


def evaluate_pgir_readiness() -> PGIRGovernanceDecision:
    mapping = validate_mapping_matrix()
    schema = validate_schema_governance()
    capability = validate_capability_stages()
    concept_count = len(build_concept_registry())
    gates = {
        "core_concepts_defined": concept_count >= 15,
        "current_mapping_complete": mapping["valid"] and mapping["mapping_count"] >= 10,
        "schema_owners_unique": schema["valid"],
        "capability_stages_consistent": capability["valid"],
        "no_existing_result_promotion": True,
        "runtime_persistence_boundary_preserved": True,
        "domain_semantics_preserved": True,
        "operator_taxonomy_explicit": set(("Evaluator", "Transformer", "Propagator")) <= set(VALID_OPERATOR_ROLES),
        "maturity_levels_explicit": len(VALID_MATURITY_LEVELS) == 9,
        "future_only_capabilities_marked": "propagator_operator_role" in capability["future_only_capabilities"],
        "no_solver_or_model_claim": True,
    }
    errors = tuple(mapping["errors"] + schema["errors"] + capability["errors"])
    status = "pgir_governance_ready" if all(gates.values()) and not errors else "pgir_governance_ready_with_gaps"
    return PGIRGovernanceDecision(
        status=status,
        valid=status == "pgir_governance_ready",
        errors=errors,
        warnings=(),
        gates=gates,
        readiness_summary={
            "concept_count": concept_count,
            "mapping_count": mapping["mapping_count"],
            "schema_count": schema["schema_count"],
            "capability_count": capability["capability_count"],
            "scientific_recomputation_performed": False,
            "api_or_network_called": False,
            "model_or_solver_executed": False,
        },
    )


def governance_summary() -> dict[str, Any]:
    decision = evaluate_pgir_readiness()
    return {
        "schema_version": PGIR_GOVERNANCE_VERSION,
        "status": decision.status,
        "principles": list(pgir_principles()),
        "maturity_levels": list(representation_maturity_levels()),
        "concept_count": len(build_concept_registry()),
        "mapping_count": len(build_current_mapping_matrix()),
        "schema_count": len(build_schema_ownership_registry()),
        "capability_count": len(build_capability_stage_registry()),
        "operator_roles": list(VALID_OPERATOR_ROLES),
        "readiness": decision.to_dict(),
        "execution_boundary": {
            "scientific_recomputation_performed": False,
            "api_or_network_called": False,
            "model_training_performed": False,
            "solver_execution_performed": False,
            "row_level_data_accessed": False,
            "existing_artifact_mutation": False,
        },
        "v2_2_preservation": {
            "composition_only_pre_structure": "performance_degraded",
            "known_structure_post_relaxation": "structure_predictive_value_limited",
            "representative_model": "none",
            "graph_artifacts": "representation_only",
        },
    }


def registry_payloads() -> dict[str, Any]:
    return {
        "pgir_concept_registry_v1": {
            "schema_version": PGIR_GOVERNANCE_VERSION,
            "status": PGIR_REGISTRY_STATUS,
            "concepts": [record.to_dict() for record in build_concept_registry()],
        },
        "pgir_current_mapping_matrix_v1": {
            "schema_version": PGIR_GOVERNANCE_VERSION,
            "status": PGIR_REGISTRY_STATUS,
            "mappings": [record.to_dict() for record in build_current_mapping_matrix()],
            "validation": validate_mapping_matrix(),
        },
        "pgir_representation_governance_v1": build_representation_governance(),
        "pgir_schema_ownership_registry_v1": {
            "schema_version": PGIR_GOVERNANCE_VERSION,
            "status": PGIR_REGISTRY_STATUS,
            "schemas": [record.to_dict() for record in build_schema_ownership_registry()],
            "validation": validate_schema_governance(),
        },
        "pgir_capability_stage_registry_v1": {
            "schema_version": PGIR_GOVERNANCE_VERSION,
            "status": PGIR_REGISTRY_STATUS,
            "capabilities": [record.to_dict() for record in build_capability_stage_registry()],
            "validation": validate_capability_stages(),
        },
    }


def canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_json_safe(payload), indent=2, sort_keys=True) + "\n"


def load_registry_payload(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("PGIR registry payload must be a JSON object")
    if payload.get("schema_version") != PGIR_GOVERNANCE_VERSION:
        raise ValueError(f"unsupported PGIR schema_version: {payload.get('schema_version')}")
    return payload
