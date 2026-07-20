"""Versioned PGIR model contract for the bounded 1D diffusion benchmark.

This module is deliberately not a symbolic equation engine. Relations,
conditions, and operators are selected from explicit registries, and persisted
records contain JSON-safe metadata only.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import MISSING, asdict, dataclass, fields
from typing import Any, ClassVar, Mapping, TypeVar

from .scientific_relations import default_scientific_relations
from .unit_backend import BuiltinUnitBackend


PGIR_MODEL_CONTRACT_SCHEMA_VERSION = "1"
DIFFUSION_MODEL_CONTRACT_ID = "one_dimensional_diffusion_zero_dirichlet_v1"
DIFFUSION_RELATION_ID = "pgir.diffusion_1d.homogeneous_zero_dirichlet"
EXACT_OPERATOR_ID = "one_dimensional_diffusion_exact_propagator_v1"
FTCS_OPERATOR_ID = "one_dimensional_diffusion_ftcs_propagator_v1"
EVALUATOR_OPERATOR_ID = "one_dimensional_diffusion_benchmark_evaluator_v1"

ALLOWED_INITIAL_CONDITIONS = ("single_sine_mode_zero_dirichlet_v1",)
ALLOWED_BOUNDARY_TYPES = ("homogeneous_dirichlet",)
ALLOWED_MODEL_CONTRACT_STATUSES = ("registered_bounded_benchmark",)
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_WINDOWS_ABSOLUTE = re.compile(r"^[A-Za-z]:[\\/]")


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def canonical_json_sha256(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{field_name} must be a stable identifier")


def _json_safe(value: Any, location: str = "record") -> Any:
    if isinstance(value, Mapping):
        blocked = {"module_path", "callable_name", "python_expression", "api_key", "authorization", "secret"}
        for key, item in value.items():
            if str(key).lower() in blocked:
                raise ValueError(f"{location}.{key} is prohibited")
            _json_safe(item, f"{location}.{key}")
        return value
    if isinstance(value, (tuple, list)):
        for index, item in enumerate(value):
            _json_safe(item, f"{location}[{index}]")
        return value
    if isinstance(value, str):
        normalized = value.replace("\\", "/")
        if normalized.startswith(("/", "//")) or _WINDOWS_ABSOLUTE.match(value):
            raise ValueError(f"{location} contains an absolute path")
        return value
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{location} must be finite")
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    raise ValueError(f"{location} contains unsupported JSON type: {type(value).__name__}")


T = TypeVar("T", bound="StrictModelRecord")


@dataclass(frozen=True)
class StrictModelRecord:
    TUPLE_FIELDS: ClassVar[tuple[str, ...]] = ()

    @classmethod
    def from_mapping(cls: type[T], payload: Mapping[str, Any]) -> T:
        allowed = {item.name for item in fields(cls)}
        unknown = sorted(set(payload) - allowed)
        if unknown:
            raise ValueError(f"{cls.__name__} contains unknown fields: {unknown}")
        required = {
            item.name
            for item in fields(cls)
            if item.default is MISSING and item.default_factory is MISSING
        }
        missing = sorted(required - set(payload))
        if missing:
            raise ValueError(f"{cls.__name__} is missing required fields: {missing}")
        values = dict(payload)
        for name in cls.TUPLE_FIELDS:
            if name in values:
                raw = values[name]
                values[name] = (raw,) if isinstance(raw, str) else tuple(raw or ())
        return cls(**values)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        _json_safe(payload)
        return payload


@dataclass(frozen=True)
class ScalarField1DDeclaration(StrictModelRecord):
    field_id: str
    symbol: str
    quantity_semantics: str
    unit: str
    dimension: str
    coordinate_ids: tuple[str, ...]
    positive_benchmark_input: bool
    persistence_policy: str

    TUPLE_FIELDS: ClassVar[tuple[str, ...]] = ("coordinate_ids",)

    def __post_init__(self) -> None:
        _identifier(self.field_id, "field_id")
        if self.persistence_policy != "large_arrays_local_only_compact_metadata_tracked":
            raise ValueError("scalar field arrays must remain local-only")
        _json_safe(self.to_dict())


@dataclass(frozen=True)
class SpatialDomain1D(StrictModelRecord):
    coordinate_id: str
    symbol: str
    lower_bound: float
    upper_bound_parameter_id: str
    unit: str
    dimension: str
    topology: str
    minimum_grid_points: int

    def __post_init__(self) -> None:
        _identifier(self.coordinate_id, "coordinate_id")
        _identifier(self.upper_bound_parameter_id, "upper_bound_parameter_id")
        if self.lower_bound != 0.0 or self.topology != "closed_interval":
            raise ValueError("the bounded benchmark requires x in [0, L]")
        if self.minimum_grid_points < 3:
            raise ValueError("minimum_grid_points must be at least three")


@dataclass(frozen=True)
class TimeDomain(StrictModelRecord):
    coordinate_id: str
    symbol: str
    start: float
    end_execution_parameter_id: str
    unit: str
    dimension: str
    minimum_grid_points: int

    def __post_init__(self) -> None:
        _identifier(self.coordinate_id, "coordinate_id")
        _identifier(self.end_execution_parameter_id, "end_execution_parameter_id")
        if self.start != 0.0 or self.minimum_grid_points < 2:
            raise ValueError("time grid must start at zero and contain at least two points")


@dataclass(frozen=True)
class ParameterDeclaration(StrictModelRecord):
    parameter_id: str
    symbol: str
    quantity_semantics: str
    unit: str
    dimension: str
    constraints: tuple[str, ...]
    provenance: str
    uncertainty_policy: str

    TUPLE_FIELDS: ClassVar[tuple[str, ...]] = ("constraints",)

    def __post_init__(self) -> None:
        _identifier(self.parameter_id, "parameter_id")
        if self.uncertainty_policy != "synthetic_value_no_empirical_uncertainty":
            raise ValueError("benchmark parameters must not invent empirical uncertainty")


@dataclass(frozen=True)
class InitialConditionDeclaration(StrictModelRecord):
    condition_id: str
    expression_id: str
    field_id: str
    reference_time: float
    parameter_refs: tuple[str, ...]
    compatibility_requirements: tuple[str, ...]

    TUPLE_FIELDS: ClassVar[tuple[str, ...]] = ("parameter_refs", "compatibility_requirements")

    def __post_init__(self) -> None:
        _identifier(self.condition_id, "condition_id")
        if self.expression_id not in ALLOWED_INITIAL_CONDITIONS:
            raise ValueError(f"unsupported initial condition: {self.expression_id}")
        if self.reference_time != 0.0:
            raise ValueError("initial condition reference time must be zero")


@dataclass(frozen=True)
class BoundaryConditionDeclaration(StrictModelRecord):
    condition_id: str
    boundary_type: str
    field_id: str
    coordinate_id: str
    location: str
    value: float
    value_unit: str
    applies_for: str

    def __post_init__(self) -> None:
        _identifier(self.condition_id, "condition_id")
        if self.boundary_type not in ALLOWED_BOUNDARY_TYPES or self.value != 0.0:
            raise ValueError("benchmark boundaries must be homogeneous zero Dirichlet")
        if self.location not in {"lower_bound", "upper_bound"}:
            raise ValueError("boundary location must be lower_bound or upper_bound")


@dataclass(frozen=True)
class SolverRequirement(StrictModelRecord):
    operator_id: str
    operator_role: str
    backend_id: str
    deterministic_required: bool
    uniform_spatial_grid_required: bool
    uniform_time_grid_required: bool
    stability_condition: str
    maximum_spatial_points: int
    maximum_time_steps: int

    def __post_init__(self) -> None:
        _identifier(self.operator_id, "operator_id")
        if self.operator_role not in {"Propagator", "Evaluator"}:
            raise ValueError("unsupported operator role")
        if not self.deterministic_required:
            raise ValueError("benchmark operators must be deterministic")
        if self.maximum_spatial_points > 1001 or self.maximum_time_steps > 100000:
            raise ValueError("solver requirement exceeds bounded benchmark limits")


@dataclass(frozen=True)
class ModelValidationCriterion(StrictModelRecord):
    criterion_id: str
    metric: str
    requirement: str
    threshold: float | None
    failure_status: str

    def __post_init__(self) -> None:
        _identifier(self.criterion_id, "criterion_id")
        if self.threshold is not None and (not math.isfinite(self.threshold) or self.threshold < 0):
            raise ValueError("validation threshold must be finite and non-negative")


@dataclass(frozen=True)
class PGIRModelContract(StrictModelRecord):
    model_contract_id: str
    model_contract_version: str
    schema_version: str
    status: str
    scientific_question: str
    domain_context: str
    governing_relation_id: str
    governing_equation_display: str
    scalar_field: ScalarField1DDeclaration
    spatial_domain: SpatialDomain1D
    time_domain: TimeDomain
    parameters: tuple[ParameterDeclaration, ...]
    initial_condition: InitialConditionDeclaration
    boundary_conditions: tuple[BoundaryConditionDeclaration, ...]
    applicability_conditions: tuple[str, ...]
    input_maturity_requirements: tuple[str, ...]
    operator_requirements: tuple[SolverRequirement, ...]
    analytical_reference_available: bool
    expected_result_schema_ids: tuple[str, ...]
    validation_criteria: tuple[ModelValidationCriterion, ...]
    uncertainty_policy: str
    provenance: tuple[str, ...]
    allowed_claims: tuple[str, ...]
    prohibited_claims: tuple[str, ...]

    TUPLE_FIELDS: ClassVar[tuple[str, ...]] = (
        "parameters",
        "boundary_conditions",
        "applicability_conditions",
        "input_maturity_requirements",
        "operator_requirements",
        "expected_result_schema_ids",
        "validation_criteria",
        "provenance",
        "allowed_claims",
        "prohibited_claims",
    )

    def __post_init__(self) -> None:
        _identifier(self.model_contract_id, "model_contract_id")
        if self.schema_version != PGIR_MODEL_CONTRACT_SCHEMA_VERSION:
            raise ValueError(f"unsupported model contract schema_version: {self.schema_version}")
        if self.status not in ALLOWED_MODEL_CONTRACT_STATUSES:
            raise ValueError(f"unsupported model contract status: {self.status}")
        if self.governing_relation_id != DIFFUSION_RELATION_ID:
            raise ValueError("unregistered governing relation")
        if not self.analytical_reference_available:
            raise ValueError("this benchmark requires an analytical reference")
        if len(self.boundary_conditions) != 2:
            raise ValueError("two endpoint boundary conditions are required")
        object.__setattr__(self, "parameters", tuple(
            item if isinstance(item, ParameterDeclaration) else ParameterDeclaration.from_mapping(item)
            for item in self.parameters
        ))
        object.__setattr__(self, "boundary_conditions", tuple(
            item if isinstance(item, BoundaryConditionDeclaration) else BoundaryConditionDeclaration.from_mapping(item)
            for item in self.boundary_conditions
        ))
        object.__setattr__(self, "operator_requirements", tuple(
            item if isinstance(item, SolverRequirement) else SolverRequirement.from_mapping(item)
            for item in self.operator_requirements
        ))
        object.__setattr__(self, "validation_criteria", tuple(
            item if isinstance(item, ModelValidationCriterion) else ModelValidationCriterion.from_mapping(item)
            for item in self.validation_criteria
        ))
        _json_safe(self.to_dict())

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "PGIRModelContract":
        values = dict(payload)
        values["scalar_field"] = ScalarField1DDeclaration.from_mapping(payload["scalar_field"])
        values["spatial_domain"] = SpatialDomain1D.from_mapping(payload["spatial_domain"])
        values["time_domain"] = TimeDomain.from_mapping(payload["time_domain"])
        values["parameters"] = tuple(ParameterDeclaration.from_mapping(item) for item in payload["parameters"])
        values["initial_condition"] = InitialConditionDeclaration.from_mapping(payload["initial_condition"])
        values["boundary_conditions"] = tuple(
            BoundaryConditionDeclaration.from_mapping(item) for item in payload["boundary_conditions"]
        )
        values["operator_requirements"] = tuple(
            SolverRequirement.from_mapping(item) for item in payload["operator_requirements"]
        )
        values["validation_criteria"] = tuple(
            ModelValidationCriterion.from_mapping(item) for item in payload["validation_criteria"]
        )
        return super().from_mapping(values)


@dataclass(frozen=True)
class ModelExecutionDeclaration(StrictModelRecord):
    execution_id: str
    model_contract_id: str
    model_contract_checksum: str
    operator_ids: tuple[str, ...]
    input_checksum: str
    exact_result_checksum: str | None
    numerical_result_checksum: str | None
    evaluator_result_checksum: str | None
    execution_status: str
    deterministic: bool
    network_called: bool
    model_fitting_performed: bool
    lineage_refs: tuple[str, ...]

    TUPLE_FIELDS: ClassVar[tuple[str, ...]] = ("operator_ids", "lineage_refs")

    def __post_init__(self) -> None:
        _identifier(self.execution_id, "execution_id")
        if self.network_called or self.model_fitting_performed:
            raise ValueError("benchmark execution cannot use network access or fitting")
        _json_safe(self.to_dict())


def build_diffusion_model_contract() -> PGIRModelContract:
    return PGIRModelContract(
        model_contract_id=DIFFUSION_MODEL_CONTRACT_ID,
        model_contract_version="1",
        schema_version="1",
        status="registered_bounded_benchmark",
        scientific_question="Can PGIR execute and validate a deterministic bounded scalar diffusion benchmark against an exact solution?",
        domain_context="synthetic_scalar_diffusion_software_benchmark",
        governing_relation_id=DIFFUSION_RELATION_ID,
        governing_equation_display="dc/dt = D d2c/dx2 on x in [0,L]",
        scalar_field=ScalarField1DDeclaration(
            field_id="scalar_field_c",
            symbol="c",
            quantity_semantics="abstract_dimensionless_scalar_field",
            unit="unitless",
            dimension="dimensionless",
            coordinate_ids=("x", "t"),
            positive_benchmark_input=True,
            persistence_policy="large_arrays_local_only_compact_metadata_tracked",
        ),
        spatial_domain=SpatialDomain1D("x", "x", 0.0, "length", "m", "length", "closed_interval", 3),
        time_domain=TimeDomain("t", "t", 0.0, "final_time", "s", "time", 2),
        parameters=(
            ParameterDeclaration("length", "L", "domain_length", "m", "length", ("value > 0",), "synthetic_config", "synthetic_value_no_empirical_uncertainty"),
            ParameterDeclaration("diffusivity", "D", "abstract_diffusivity", "m^2/s", "diffusivity", ("value > 0",), "synthetic_config", "synthetic_value_no_empirical_uncertainty"),
            ParameterDeclaration("amplitude", "A", "initial_field_amplitude", "unitless", "dimensionless", ("finite", "value >= 0 for positive benchmark"), "synthetic_config", "synthetic_value_no_empirical_uncertainty"),
        ),
        initial_condition=InitialConditionDeclaration(
            "initial_single_sine_mode",
            "single_sine_mode_zero_dirichlet_v1",
            "scalar_field_c",
            0.0,
            ("amplitude", "length"),
            ("c(0,0)=0", "c(L,0)=0"),
        ),
        boundary_conditions=(
            BoundaryConditionDeclaration("left_zero_dirichlet", "homogeneous_dirichlet", "scalar_field_c", "x", "lower_bound", 0.0, "unitless", "t >= 0"),
            BoundaryConditionDeclaration("right_zero_dirichlet", "homogeneous_dirichlet", "scalar_field_c", "x", "upper_bound", 0.0, "unitless", "t >= 0"),
        ),
        applicability_conditions=(
            "constant positive diffusivity",
            "one-dimensional uniform domain",
            "homogeneous zero Dirichlet boundaries",
            "single sine-mode initial condition",
            "synthetic benchmark parameters",
        ),
        input_maturity_requirements=("schema_valid", "semantically_mapped", "dimensionally_valid"),
        operator_requirements=(
            SolverRequirement(EXACT_OPERATOR_ID, "Propagator", "closed_form_single_mode_v1", True, False, False, "not_applicable", 1001, 100000),
            SolverRequirement(FTCS_OPERATOR_ID, "Propagator", "explicit_ftcs_v1", True, True, True, "0 < D*dt/dx^2 <= 0.5", 1001, 100000),
            SolverRequirement(EVALUATOR_OPERATOR_ID, "Evaluator", "analytical_numerical_comparison_v1", True, False, False, "not_applicable", 1001, 100000),
        ),
        analytical_reference_available=True,
        expected_result_schema_ids=(
            "scalar_field_1d_result_schema_v1",
            "physical_propagator_execution_schema_v1",
            "analytical_numerical_benchmark_schema_v1",
        ),
        validation_criteria=(
            ModelValidationCriterion("finite_field_values", "finite_value_check", "all values finite", 0.0, "blocked_nonfinite_result"),
            ModelValidationCriterion("zero_boundary_residual", "boundary_residual", "maximum residual <= tolerance", 1e-12, "blocked_artifact_mismatch"),
            ModelValidationCriterion("initial_condition_residual", "initial_condition_residual", "maximum residual <= tolerance", 1e-12, "blocked_artifact_mismatch"),
            ModelValidationCriterion("refinement_error_decrease", "l2_error", "fine error lower than coarse error", None, "blocked_artifact_mismatch"),
        ),
        uncertainty_policy="source_uncertainty_unavailable_report_numerical_discretization_error_only",
        provenance=("synthetic_config", "analytical_single_mode_solution", "deterministic_ftcs_implementation"),
        allowed_claims=(
            "bounded PGIR model-contract execution",
            "analytical and deterministic numerical propagator comparison",
            "software-level refinement evidence for this synthetic benchmark",
        ),
        prohibited_claims=(
            "Battery diffusion mechanism",
            "real-material diffusivity",
            "fitted physical mechanism",
            "validated industrial solver",
            "cross-domain physical-operator reuse",
            "independent validation",
            "production validation",
        ),
    )


def validate_pgir_model_contract(contract: PGIRModelContract | Mapping[str, Any]) -> dict[str, Any]:
    try:
        record = contract if isinstance(contract, PGIRModelContract) else PGIRModelContract.from_mapping(contract)
        relation_ids = {item.relation_id for item in default_scientific_relations()}
        from .scientific_operator_registry import build_default_scientific_operator_registry

        operator_ids = {item.operator_id for item in build_default_scientific_operator_registry().list_operators()}
        required_operators = {item.operator_id for item in record.operator_requirements}
        errors = []
        if record.governing_relation_id not in relation_ids:
            errors.append("unregistered_governing_relation")
        missing_operators = sorted(required_operators - operator_ids)
        if missing_operators:
            errors.append(f"unregistered_operators:{','.join(missing_operators)}")
        backend = BuiltinUnitBackend()
        expected_dimensions = {
            record.spatial_domain.unit: "length",
            record.time_domain.unit: "time",
            record.scalar_field.unit: record.scalar_field.dimension,
        }
        expected_dimensions.update({item.unit: item.dimension for item in record.parameters})
        for unit, dimension in expected_dimensions.items():
            if backend.dimensionality(unit) != dimension:
                errors.append(f"dimension_mismatch:{unit}:{dimension}")
        if {item.location for item in record.boundary_conditions} != {"lower_bound", "upper_bound"}:
            errors.append("boundary_endpoint_coverage_invalid")
        if any(item.value_unit != record.scalar_field.unit for item in record.boundary_conditions):
            errors.append("boundary_field_unit_mismatch")
        return {
            "status": "valid" if not errors else "blocked_invalid_model_contract",
            "valid": not errors,
            "errors": errors,
            "model_contract_id": record.model_contract_id,
            "model_contract_checksum": canonical_json_sha256(record.to_dict()),
        }
    except (KeyError, TypeError, ValueError) as exc:
        return {
            "status": "blocked_invalid_model_contract",
            "valid": False,
            "errors": [str(exc)],
            "model_contract_id": None,
            "model_contract_checksum": None,
        }
