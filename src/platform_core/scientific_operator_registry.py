"""Explicit selected scientific operator registry.

Operators are metadata records only. The registry stores no arbitrary callable,
does not import user-supplied modules, and does not scan the filesystem.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


OPERATOR_REGISTRY_VERSION = "2.4.2"
ALLOWED_OPERATOR_STATUSES = ("registered", "metadata_only", "adapter_available", "validation_ready")


@dataclass(frozen=True)
class ScientificOperatorMetadata:
    operator_id: str
    operator_version: str
    input_entity_types: tuple[str, ...]
    output_types: tuple[str, ...]
    required_fields: tuple[str, ...]
    side_effect_policy: str
    network_policy: str
    uncertainty_policy: str
    provenance_policy: str
    deterministic: bool
    bounded_input_policy: str
    status: str = "registered"
    description: str = ""
    operator_role: str = "unspecified"
    mechanism_family: str = "unspecified"
    target_access_policy: str = "no_target_access"
    claim_boundary: tuple[str, ...] = ()
    capability_stage: str = "registered"

    def __post_init__(self) -> None:
        if "/" in self.operator_id or "\\" in self.operator_id or ".." in self.operator_id:
            raise ValueError("operator_id must be an identifier, not a path")
        if self.status not in ALLOWED_OPERATOR_STATUSES:
            raise ValueError(f"unsupported operator status: {self.status}")
        blocked = (self.side_effect_policy, self.network_policy)
        if any("arbitrary" in item for item in blocked):
            raise ValueError("arbitrary execution policies are not allowed")

    def to_dict(self) -> dict[str, Any]:
        return {
            "operator_id": self.operator_id,
            "operator_version": self.operator_version,
            "input_entity_types": list(self.input_entity_types),
            "output_types": list(self.output_types),
            "required_fields": list(self.required_fields),
            "side_effect_policy": self.side_effect_policy,
            "network_policy": self.network_policy,
            "uncertainty_policy": self.uncertainty_policy,
            "provenance_policy": self.provenance_policy,
            "deterministic": self.deterministic,
            "bounded_input_policy": self.bounded_input_policy,
            "status": self.status,
            "description": self.description,
            "operator_role": self.operator_role,
            "mechanism_family": self.mechanism_family,
            "target_access_policy": self.target_access_policy,
            "claim_boundary": list(self.claim_boundary),
            "capability_stage": self.capability_stage,
        }


@dataclass
class ScientificOperatorRegistry:
    _operators: dict[str, ScientificOperatorMetadata] = field(default_factory=dict)

    def register(self, operator: ScientificOperatorMetadata) -> None:
        if operator.operator_id in self._operators:
            raise ValueError(f"duplicate scientific operator_id: {operator.operator_id}")
        self._operators[operator.operator_id] = operator

    def get(self, operator_id: str) -> ScientificOperatorMetadata:
        try:
            return self._operators[operator_id]
        except KeyError as exc:
            raise KeyError(f"unknown scientific operator_id: {operator_id}") from exc

    def list_operators(self) -> list[ScientificOperatorMetadata]:
        return [self._operators[key] for key in sorted(self._operators)]

    def snapshot(self) -> list[dict[str, Any]]:
        return [operator.to_dict() for operator in self.list_operators()]

    def validate(self) -> dict[str, Any]:
        errors: list[str] = []
        for operator in self.list_operators():
            if operator.network_policy == "network_allowed":
                errors.append(f"{operator.operator_id}: network_allowed is not valid in v2.2.3")
            if operator.side_effect_policy not in {"none", "local_output_only", "metadata_only"}:
                errors.append(f"{operator.operator_id}: unsupported side_effect_policy")
        return {
            "valid": not errors,
            "errors": errors,
            "operator_count": len(self._operators),
            "registry_version": OPERATOR_REGISTRY_VERSION,
        }


def _op(
    operator_id: str,
    input_entity_types: tuple[str, ...],
    output_types: tuple[str, ...],
    required_fields: tuple[str, ...],
    description: str,
    *,
    status: str = "registered",
    uncertainty_policy: str = "unavailable_if_source_not_provided",
    side_effect_policy: str = "none",
    operator_role: str = "unspecified",
    mechanism_family: str = "unspecified",
    target_access_policy: str = "no_target_access",
    claim_boundary: tuple[str, ...] = (),
    capability_stage: str = "registered",
) -> ScientificOperatorMetadata:
    return ScientificOperatorMetadata(
        operator_id=operator_id,
        operator_version="1",
        input_entity_types=input_entity_types,
        output_types=output_types,
        required_fields=required_fields,
        side_effect_policy=side_effect_policy,
        network_policy="no_network",
        uncertainty_policy=uncertainty_policy,
        provenance_policy="record_input_checksums_and_schema_versions",
        deterministic=True,
        bounded_input_policy="small_inline_or_artifact_backed_json_safe_records",
        status=status,
        description=description,
        operator_role=operator_role,
        mechanism_family=mechanism_family,
        target_access_policy=target_access_policy,
        claim_boundary=claim_boundary,
        capability_stage=capability_stage,
    )


def build_default_scientific_operator_registry() -> ScientificOperatorRegistry:
    registry = ScientificOperatorRegistry()
    for operator in (
        _op(
            "mp_summary_to_composition_entity_v1",
            ("MaterialsProjectSummaryDoc",),
            ("MaterialCompositionEntity",),
            ("material_id", "formula_pretty", "composition_reduced"),
            "Convert Materials Project summary metadata into a JSON-safe composition entity.",
            status="adapter_available",
        ),
        _op(
            "mp_structure_to_crystal_entity_v1",
            ("MaterialsProjectStructureDoc",),
            ("CrystalStructureEntity",),
            ("material_id", "structure.lattice", "structure.sites"),
            "Convert a runtime MP/pymatgen structure into a JSON-safe crystal structure entity.",
            status="adapter_available",
        ),
        _op(
            "mp_target_to_quantity_v1",
            ("MaterialsProjectSummaryDoc",),
            ("ScientificQuantity",),
            ("material_id", "energy_above_hull"),
            "Convert the current target property into a scientific quantity with unavailable uncertainty.",
            status="adapter_available",
        ),
        _op(
            "crystal_structure_integrity_check_v1",
            ("CrystalStructureEntity",),
            ("IntegrityFinding",),
            ("lattice.matrix", "sites"),
            "Validate basic crystal structure payload shape, finite values, species, and occupancy metadata.",
            status="validation_ready",
        ),
        _op(
            "composition_structure_consistency_check_v1",
            ("MaterialCompositionEntity", "CrystalStructureEntity"),
            ("ConsistencyFinding",),
            ("stoichiometric_amounts", "structure_derived_composition"),
            "Compare summary composition and structure-derived composition without making phase claims.",
            status="validation_ready",
        ),
        _op(
            "crystal_basic_geometry_summary_v1",
            ("CrystalStructureEntity",),
            ("GeometrySummary",),
            ("lattice.matrix", "sites"),
            "Compute descriptive lattice geometry summary; not a predictive feature artifact.",
            status="validation_ready",
        ),
        _op(
            "crystal_structure_to_descriptor_summary_v1",
            ("CrystalStructureEntity",),
            ("StructureDescriptorSummary",),
            ("lattice.matrix", "sites", "symmetry"),
            "Build deterministic Tier-1 structure descriptor candidates without target access.",
            status="validation_ready",
        ),
        _op(
            "crystal_structure_to_radius_graph_v1",
            ("CrystalStructureEntity",),
            ("GraphEntity",),
            ("lattice.matrix", "sites.fractional_coordinates", "sites.species"),
            "Build a deterministic periodic radius graph artifact; not a GNN execution.",
            status="validation_ready",
        ),
        _op(
            "structure_snapshot_alignment_check_v1",
            ("MaterialsProjectSummaryDoc", "MaterialsProjectStructureDoc"),
            ("SnapshotAlignmentFinding",),
            ("material_id", "energy_above_hull"),
            "Compare original v1.3 target with current API value without overwriting the original target.",
            status="validation_ready",
        ),
        _op(
            "battery_source_record_to_cycle_observation_v1",
            ("BatteryCycleSourceRecord",),
            ("MeasurementSeriesEntity",),
            ("battery_id", "cycle_index", "discharge_capacity_ah"),
            "Map an existing battery cycle source row to a PGIR Observation without inlining large series.",
            status="adapter_available",
        ),
        _op(
            "battery_cycle_observation_to_operational_state_v1",
            ("MeasurementSeriesEntity",),
            ("StateEntity",),
            ("cycle_index", "capacity_observation", "unit_metadata"),
            "Transform a Battery Observation into a bounded operational State summary, not a latent electrochemical state.",
            status="adapter_available",
        ),
        _op(
            "battery_operational_states_to_trajectory_v1",
            ("StateEntity",),
            ("TrajectoryEntity",),
            ("ordered_state_refs", "time_axis_semantics"),
            "Build a deterministic per-cell trajectory from ordered battery operational State summaries.",
            status="adapter_available",
        ),
        _op(
            "battery_cycle_observation_integrity_check_v1",
            ("MeasurementSeriesEntity",),
            ("IntegrityFinding",),
            ("cycle_index", "quantity_roles", "unit_metadata"),
            "Validate Battery Observation metadata, units, and direct/derived quantity roles.",
            status="validation_ready",
        ),
        _op(
            "battery_trajectory_integrity_check_v1",
            ("TrajectoryEntity",),
            ("IntegrityFinding",),
            ("ordered_state_refs", "time_axis"),
            "Validate cycle ordering, duplicate policy, and mixed-cell rejection for Battery trajectories.",
            status="validation_ready",
        ),
        _op(
            "battery_mechanism_readiness_assessment_v1",
            ("TrajectoryEntity",),
            ("MechanismReadinessSummary",),
            ("trajectory_count", "temperature_context", "boundary_condition_context"),
            "Audit readiness for Arrhenius, diffusion, and empirical degradation mechanisms without executing them.",
            status="validation_ready",
        ),
        _op(
            "battery_capacity_trajectory_consistency_evaluator_v1",
            ("TrajectoryEntity",),
            ("CapacityTrajectoryResult", "CapacityTrajectoryFinding", "CapacityTrajectoryTrustAssessment"),
            ("cycle_order", "discharge_capacity_ah", "reference_capacity_policy"),
            "Evaluate observed capacity trajectory consistency descriptively without mechanism confirmation or prediction.",
            status="adapter_available",
            side_effect_policy="local_output_only",
            operator_role="Evaluator",
            mechanism_family="damage_and_degradation_descriptive_trajectory_evaluation",
            target_access_policy="observed_capacity_only_no_predictive_target",
            claim_boundary=(
                "descriptive trajectory candidates only",
                "no mechanism attribution",
                "no parameter estimation",
                "no prediction or extrapolation",
            ),
            capability_stage="scientifically_evaluated_as_descriptive_evaluator",
        ),
        _op(
            "battery_protocol_comparability_evaluator_v1",
            ("MeasurementSeriesEntity", "TrajectoryEntity"),
            ("ProtocolComparabilityFinding",),
            ("cycle_type", "current_profile", "voltage_window", "temperature_context"),
            "Audit protocol comparability metadata for mechanism candidates without treating missing metadata as equality.",
            status="validation_ready",
        ),
        _op(
            "battery_arrhenius_readiness_evaluator_v1",
            ("TrajectoryEntity",),
            ("MechanismReadinessSummary",),
            ("temperature_groups", "rate_like_response", "protocol_comparability"),
            "Audit Arrhenius sufficiency and block activation-energy claims when current evidence is insufficient.",
            status="validation_ready",
        ),
        _op(
            "battery_diffusion_readiness_evaluator_v1",
            ("TrajectoryEntity",),
            ("MechanismReadinessSummary",),
            ("internal_state", "geometry", "boundary_conditions", "transient_time_axis"),
            "Audit diffusion sufficiency and block diffusion-coefficient claims when state, geometry, or boundary evidence is missing.",
            status="validation_ready",
        ),
        _op(
            "battery_resistance_capacity_relation_applicability_v1",
            ("MeasurementSeriesEntity", "TrajectoryEntity"),
            ("MechanismReadinessSummary",),
            ("resistance_definition", "capacity_definition", "protocol_context"),
            "Audit resistance/capacity relation applicability without equivalent-circuit or impedance fitting.",
            status="validation_ready",
        ),
        _op(
            "one_dimensional_diffusion_exact_propagator_v1",
            ("Model", "Field", "Parameter", "InitialCondition", "BoundaryCondition"),
            ("ScalarField1DResult", "PhysicalPropagatorExecution"),
            ("length", "diffusivity", "amplitude", "x_grid", "time_grid"),
            "Evaluate the registered single-mode 1D diffusion analytical solution.",
            status="validation_ready",
            operator_role="Propagator",
            mechanism_family="synthetic_scalar_diffusion_benchmark",
            target_access_policy="no_target_or_empirical_data_access",
            claim_boundary=(
                "bounded synthetic analytical reference only",
                "not a Battery or real-material diffusion mechanism",
            ),
            capability_stage="operator_executed_for_bounded_benchmark",
        ),
        _op(
            "one_dimensional_diffusion_ftcs_propagator_v1",
            ("Model", "Field", "Parameter", "InitialCondition", "BoundaryCondition"),
            ("ScalarField1DResult", "PhysicalPropagatorExecution"),
            ("length", "diffusivity", "amplitude", "uniform_x_grid", "uniform_time_grid"),
            "Execute deterministic FTCS for the registered bounded 1D diffusion benchmark.",
            status="validation_ready",
            operator_role="Propagator",
            mechanism_family="synthetic_scalar_diffusion_benchmark",
            target_access_policy="no_target_or_empirical_data_access",
            claim_boundary=(
                "requires 0 < D*dt/dx^2 <= 0.5 without silent adjustment",
                "not a general PDE solver or material mechanism",
            ),
            capability_stage="operator_executed_for_bounded_benchmark",
        ),
        _op(
            "one_dimensional_diffusion_benchmark_evaluator_v1",
            ("ScalarField1DResult",),
            ("AnalyticalNumericalBenchmarkResult",),
            ("exact_field_checksum", "numerical_field_checksum", "grid_metadata"),
            "Compare exact and FTCS scalar fields and record bounded numerical evidence.",
            status="validation_ready",
            operator_role="Evaluator",
            mechanism_family="synthetic_scalar_diffusion_benchmark",
            target_access_policy="analytical_reference_only_no_empirical_target",
            claim_boundary=(
                "software and numerical benchmark evidence only",
                "no independent or production validation",
            ),
            capability_stage="scientifically_evaluated_for_bounded_benchmark",
        ),
    ):
        registry.register(operator)
    return registry
