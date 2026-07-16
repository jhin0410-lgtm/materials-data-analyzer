"""Scientific relation and registered-operator metadata contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


RELATION_CATEGORIES = (
    "algebraic",
    "constitutive",
    "conservation",
    "differential",
    "statistical",
    "transformation",
    "transition",
    "graph_construction",
)
EXECUTION_STATUSES = ("metadata_only", "registered_operator_required", "executable_disabled", "not_implemented")


@dataclass(frozen=True)
class RelationInput:
    name: str
    entity_type: str
    quantity_id: str | None = None
    required: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "entity_type": self.entity_type,
            "quantity_id": self.quantity_id,
            "required": self.required,
        }


@dataclass(frozen=True)
class RelationOutput:
    name: str
    entity_type: str | None = None
    quantity_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "entity_type": self.entity_type,
            "quantity_id": self.quantity_id,
        }


@dataclass(frozen=True)
class RelationApplicability:
    assumptions: tuple[str, ...] = ()
    validity_conditions: tuple[str, ...] = ()
    prohibited_claims: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "assumptions": list(self.assumptions),
            "validity_conditions": list(self.validity_conditions),
            "prohibited_claims": list(self.prohibited_claims),
        }


@dataclass(frozen=True)
class RelationExecutionReference:
    operator_id: str
    execution_status: str = "metadata_only"
    module_path: str | None = None
    callable_name: str | None = None

    def __post_init__(self) -> None:
        if self.execution_status not in EXECUTION_STATUSES:
            raise ValueError(f"unsupported execution_status: {self.execution_status}")
        if self.module_path or self.callable_name:
            raise ValueError("relation execution cannot store arbitrary module_path or callable_name")

    def to_dict(self) -> dict[str, Any]:
        return {
            "operator_id": self.operator_id,
            "execution_status": self.execution_status,
        }


@dataclass(frozen=True)
class ScientificRelation:
    relation_id: str
    relation_version: str
    category: str
    input_entity_types: tuple[str, ...]
    output_entity_types: tuple[str, ...]
    required_quantities: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    validity_conditions: tuple[str, ...] = ()
    operator_id: str | None = None
    execution_status: str = "metadata_only"
    uncertainty_policy: str = "unavailable_unless_declared"
    provenance_refs: tuple[str, ...] = ()
    equation_display: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.category not in RELATION_CATEGORIES:
            raise ValueError(f"unsupported relation category: {self.category}")
        if self.execution_status not in EXECUTION_STATUSES:
            raise ValueError(f"unsupported execution_status: {self.execution_status}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "relation_id": self.relation_id,
            "relation_version": self.relation_version,
            "category": self.category,
            "input_entity_types": list(self.input_entity_types),
            "output_entity_types": list(self.output_entity_types),
            "required_quantities": list(self.required_quantities),
            "assumptions": list(self.assumptions),
            "validity_conditions": list(self.validity_conditions),
            "operator_id": self.operator_id,
            "execution_status": self.execution_status,
            "uncertainty_policy": self.uncertainty_policy,
            "provenance_refs": list(self.provenance_refs),
            "equation_display": self.equation_display,
            "metadata": dict(self.metadata),
        }


def default_scientific_relations() -> tuple[ScientificRelation, ...]:
    return (
        ScientificRelation(
            relation_id="materials.composition.physics_feature_builder",
            relation_version="2.2.2",
            category="transformation",
            input_entity_types=("MaterialCompositionEntity",),
            output_entity_types=("MeasurementSeriesEntity",),
            required_quantities=("atomic_fractions",),
            assumptions=("composition fractions are normalized", "element property source is documented"),
            validity_conditions=("composition-only descriptors",),
            operator_id="materials_physics_feature_builder_v2_2",
            execution_status="registered_operator_required",
            uncertainty_policy="not_propagated_in_v2_2_1",
            equation_display="weighted composition descriptors",
        ),
        ScientificRelation(
            relation_id="xrd.bragg.d_spacing",
            relation_version="2.2.2",
            category="algebraic",
            input_entity_types=("MeasurementSeriesEntity",),
            output_entity_types=("MeasurementSeriesEntity",),
            required_quantities=("wavelength", "two_theta", "diffraction_order"),
            assumptions=("first-order independent uncertainty when supplied",),
            validity_conditions=("0 < two_theta < pi radians", "positive wavelength", "positive diffraction order"),
            operator_id="xrd_bragg_uncertainty_v2_2",
            execution_status="registered_operator_required",
            uncertainty_policy="first_order_independent",
            equation_display="d = n*lambda / (2*sin(theta))",
        ),
        ScientificRelation(
            relation_id="structure.graph.metadata_contract",
            relation_version="2.2.2",
            category="graph_construction",
            input_entity_types=("CrystalStructureEntity",),
            output_entity_types=("GraphEntity",),
            required_quantities=(),
            assumptions=("periodic-edge metadata must be explicit",),
            validity_conditions=("schema readiness only; no tensor generation or GNN execution",),
            operator_id="graph_metadata_contract_v2_2",
            execution_status="metadata_only",
            uncertainty_policy="not_applicable",
        ),
    )
