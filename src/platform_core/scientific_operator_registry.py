"""Explicit selected scientific operator registry.

Operators are metadata records only. The registry stores no arbitrary callable,
does not import user-supplied modules, and does not scan the filesystem.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


OPERATOR_REGISTRY_VERSION = "2.2.4"
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
    ):
        registry.register(operator)
    return registry
