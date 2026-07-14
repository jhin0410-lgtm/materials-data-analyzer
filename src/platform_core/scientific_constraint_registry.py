"""Explicit scientific constraint registry."""

from __future__ import annotations

from dataclasses import dataclass, field

from .scientific_constraints import (
    EXECUTABLE_EVALUATION_ROLES,
    SCIENTIFIC_CONSTRAINT_STATUSES,
    ScientificConstraint,
    VariableRequirement,
)
from .scientific_evaluators import ScientificEvaluatorRegistry, build_default_evaluator_registry
from .units import UnitRegistry, build_default_unit_registry


@dataclass
class ScientificConstraintRegistry:
    evaluator_registry: ScientificEvaluatorRegistry
    unit_registry: UnitRegistry
    _constraints: dict[str, ScientificConstraint] = field(default_factory=dict)

    def register(self, constraint: ScientificConstraint) -> None:
        if constraint.constraint_id in self._constraints:
            raise ValueError(f"duplicate constraint_id: {constraint.constraint_id}")
        if constraint.status not in SCIENTIFIC_CONSTRAINT_STATUSES:
            raise ValueError(f"unsupported constraint status: {constraint.status}")
        if constraint.evaluation_role not in EXECUTABLE_EVALUATION_ROLES and constraint.status == "validation_ready":
            raise ValueError(f"role {constraint.evaluation_role} is not executable in v2.1.3")
        if constraint.evaluator_id is not None:
            self.evaluator_registry.get(constraint.evaluator_id)
        for variable, unit_id in constraint.expected_units.items():
            self.unit_registry.get(unit_id)
            if variable not in {item.name for item in constraint.required_variables + constraint.optional_variables}:
                raise ValueError(f"expected unit declared for unknown variable {variable}")
        if constraint.output_unit:
            self.unit_registry.get(constraint.output_unit)
        self._constraints[constraint.constraint_id] = constraint

    def get(self, constraint_id: str) -> ScientificConstraint:
        try:
            return self._constraints[constraint_id]
        except KeyError as exc:
            raise KeyError(f"unknown constraint_id: {constraint_id}") from exc

    def list_constraints(self, domain: str | None = None, category: str | None = None) -> list[ScientificConstraint]:
        constraints = self._constraints.values()
        if domain is not None:
            constraints = [constraint for constraint in constraints if constraint.domain == domain]
        if category is not None:
            constraints = [constraint for constraint in constraints if constraint.category == category]
        return [self._constraints[key] for key in sorted(constraint.constraint_id for constraint in constraints)]

    def snapshot(self, domain: str | None = None, category: str | None = None) -> list[dict[str, object]]:
        return [constraint.to_dict() for constraint in self.list_constraints(domain, category)]


def _var(name: str, unit: str | None = None, dimension: str | None = None, description: str = "", required: bool = True) -> VariableRequirement:
    return VariableRequirement(name=name, expected_unit=unit, dimension=dimension, description=description, required=required)


def _constraint(
    constraint_id: str,
    name: str,
    domain: str,
    category: str,
    description: str,
    *,
    evaluator_id: str | None,
    required_variables: tuple[VariableRequirement, ...],
    optional_variables: tuple[VariableRequirement, ...] = (),
    expected_units: dict[str, str] | None = None,
    equation_display: str | None = None,
    tolerance_policy: dict[str, object] | None = None,
    assumptions: tuple[str, ...] = (),
    validity_conditions: tuple[str, ...] = (),
    invalidity_conditions: tuple[str, ...] = (),
    severity_on_violation: str = "warning",
    evaluation_role: str = "range_check",
    feature_role: str = "none",
    model_role: str = "none",
    claim_impact: str = "narrow_claim",
    references: tuple[str, ...] = (),
    status: str = "validation_ready",
) -> ScientificConstraint:
    return ScientificConstraint(
        constraint_id=constraint_id,
        name=name,
        domain=domain,
        category=category,
        description=description,
        equation_display=equation_display,
        evaluator_id=evaluator_id,
        required_variables=required_variables,
        optional_variables=optional_variables,
        expected_units=expected_units or {},
        tolerance_policy=tolerance_policy or {},
        assumptions=assumptions,
        validity_conditions=validity_conditions,
        invalidity_conditions=invalidity_conditions,
        severity_on_violation=severity_on_violation,
        evaluation_role=evaluation_role,
        feature_role=feature_role,
        model_role=model_role,
        claim_impact=claim_impact,
        references=references,
        status=status,
    )


def build_default_scientific_constraint_registry(
    evaluator_registry: ScientificEvaluatorRegistry | None = None,
    unit_registry: UnitRegistry | None = None,
) -> ScientificConstraintRegistry:
    evaluator_registry = evaluator_registry or build_default_evaluator_registry()
    unit_registry = unit_registry or build_default_unit_registry()
    registry = ScientificConstraintRegistry(evaluator_registry, unit_registry)

    constraints = [
        _constraint(
            "materials.composition_fraction.non_negative",
            "Composition fractions are non-negative",
            "materials",
            "domain_constraint",
            "Composition fractions should not be negative.",
            evaluator_id="check_fraction_bounds",
            required_variables=(_var("composition_fraction", "fraction", "dimensionless"),),
            expected_units={"composition_fraction": "fraction"},
            tolerance_policy={"min": 0.0, "max": 1.0, "tolerance": 1e-9},
            feature_role="input_validation",
        ),
        _constraint(
            "materials.composition_fraction.sum_to_one",
            "Composition fractions sum to one",
            "materials",
            "conservation_constraint",
            "Atomic or composition fractions should sum to one within tolerance.",
            evaluator_id="check_sum_to_target",
            required_variables=(_var("composition_fraction", "fraction", "dimensionless"),),
            expected_units={"composition_fraction": "fraction"},
            tolerance_policy={"target": 1.0, "tolerance": 1e-6},
            feature_role="input_validation",
        ),
        _constraint(
            "materials.energy_above_hull.non_negative_tolerance",
            "Energy above hull non-negative tolerance",
            "materials",
            "thermodynamic_constraint",
            "Calculated energy above hull is normally non-negative, with small numerical tolerance.",
            evaluator_id="check_non_negative",
            required_variables=(_var("energy_above_hull_ev_atom", "eV", "energy"),),
            expected_units={"energy_above_hull_ev_atom": "eV"},
            tolerance_policy={"lower_tolerance": 1e-6},
            assumptions=("DFT-calculated thermodynamic metric; not a synthesizability guarantee.",),
            feature_role="diagnostic",
        ),
        _constraint(
            "materials.oxidation_state.charge_balance_metadata",
            "Oxidation-state metadata for charge-balance checks",
            "materials",
            "domain_constraint",
            "Charge balance requires oxidation-state metadata and should not be inferred from formula alone.",
            evaluator_id="check_charge_balance_metadata",
            required_variables=(),
            evaluation_role="consistency_check",
            status="metadata_only",
            assumptions=("Oxidation states are explicitly supplied by a trusted source.",),
        ),
        _constraint(
            "battery.capacity.non_negative",
            "Battery capacity is non-negative",
            "battery",
            "domain_constraint",
            "Capacity-like quantities should be non-negative.",
            evaluator_id="check_non_negative",
            required_variables=(_var("capacity", "Ah", "capacity"),),
            expected_units={"capacity": "Ah"},
        ),
        _constraint(
            "battery.coulombic_efficiency.bounds",
            "Coulombic efficiency conservative bounds",
            "battery",
            "measurement_constraint",
            "Coulombic efficiency is checked as a bounded ratio with measurement tolerance.",
            evaluator_id="check_ratio_range",
            required_variables=(_var("coulombic_efficiency", "fraction", "dimensionless"),),
            expected_units={"coulombic_efficiency": "fraction"},
            tolerance_policy={"min": 0.0, "max": 1.05, "tolerance": 1e-9},
            assumptions=("Values above one can occur from measurement/integration artifacts and require review.",),
        ),
        _constraint(
            "battery.cycle_index.non_decreasing",
            "Cycle index is non-decreasing",
            "battery",
            "monotonic_constraint",
            "Cycle index should be non-decreasing within a single ordered series.",
            evaluator_id="check_monotonic_non_decreasing",
            required_variables=(_var("cycle_index", None, "dimensionless"),),
        ),
        _constraint(
            "battery.temperature.arrhenius_domain",
            "Arrhenius temperature domain metadata",
            "battery",
            "kinetic_constraint",
            "Arrhenius-style reasoning requires physically positive temperatures and mechanism assumptions.",
            evaluator_id="check_arrhenius_temperature_domain",
            required_variables=(_var("temperature", "K", "temperature"),),
            expected_units={"temperature": "K"},
            assumptions=("Single dominant activation process is justified.", "Temperature is available before prediction origin."),
            validity_conditions=("Temperature can be converted to Kelvin.",),
            invalidity_conditions=("Mechanism changes across operating range.",),
            feature_role="diagnostic",
        ),
        _constraint(
            "manufacturing.flow.non_negative",
            "Process flow is non-negative",
            "manufacturing",
            "domain_constraint",
            "Flow-like process variables should be non-negative when semantic metadata identifies them as flow.",
            evaluator_id="check_non_negative",
            required_variables=(_var("flow_rate", None, None),),
            validity_conditions=("Variable semantic meaning is known.",),
            assumptions=("Sensor sign convention is standard non-negative flow.",),
        ),
        _constraint(
            "manufacturing.process_window.closed_interval",
            "Process window range check",
            "manufacturing",
            "domain_constraint",
            "Known process setpoints or equipment ranges can define a safe metadata-only interval.",
            evaluator_id="check_closed_interval",
            required_variables=(_var("process_value", None, None),),
            tolerance_policy={"min": 0.0, "max": 1.0, "tolerance": 0.0},
            status="metadata_only",
            assumptions=("Valid equipment limits are supplied separately.",),
        ),
        _constraint(
            "reliability.cumulative_exposure.non_decreasing",
            "Cumulative exposure is non-decreasing",
            "reliability",
            "monotonic_constraint",
            "Cumulative exposure, age, or cycle count should not decrease for an asset history.",
            evaluator_id="check_monotonic_non_decreasing",
            required_variables=(_var("cumulative_exposure", None, "time"),),
        ),
        _constraint(
            "reliability.degradation_indicator.non_negative",
            "Degradation indicator non-negative",
            "reliability",
            "domain_constraint",
            "Wear or cumulative degradation indicators are checked as non-negative only when semantics are explicit.",
            evaluator_id="check_non_negative",
            required_variables=(_var("degradation_indicator", None, None),),
            validity_conditions=("The indicator has a known non-negative convention.",),
        ),
        _constraint(
            "reliability.post_event.feature_prohibition",
            "Post-event feature prohibition",
            "reliability",
            "measurement_constraint",
            "Measurements after a terminal event are metadata/diagnostic only and cannot be prediction features.",
            evaluator_id=None,
            required_variables=(),
            evaluation_role="metadata_only",
            status="metadata_only",
            claim_impact="prohibit_claim",
        ),
        _constraint(
            "xrd.two_theta.valid_range",
            "XRD two-theta range",
            "xrd",
            "measurement_constraint",
            "two_theta must lie inside the open 0-180 degree range for the simple XRD geometry checks.",
            evaluator_id="check_closed_interval",
            required_variables=(_var("two_theta", "degree", "angle"),),
            expected_units={"two_theta": "degree"},
            tolerance_policy={"min": 0.0, "max": 180.0, "tolerance": 0.0},
            assumptions=("Input is two-theta, not theta.",),
        ),
        _constraint(
            "xrd.wavelength.positive",
            "XRD wavelength positive",
            "xrd",
            "measurement_constraint",
            "X-ray wavelength must be positive.",
            evaluator_id="check_positive",
            required_variables=(_var("wavelength", "angstrom", "length"),),
            expected_units={"wavelength": "angstrom"},
        ),
        _constraint(
            "xrd.bragg.geometry",
            "Bragg geometry metadata check",
            "xrd",
            "geometric_structural_constraint",
            "Bragg geometry checks metadata ranges only; it does not perform phase identification.",
            evaluator_id="check_bragg_geometry",
            required_variables=(_var("two_theta", "degree", "angle"), _var("wavelength", "angstrom", "length")),
            expected_units={"two_theta": "degree", "wavelength": "angstrom"},
            equation_display="n lambda = 2 d sin(theta)",
            assumptions=("n=1 unless explicitly supplied.", "Peak position is measured before derived-feature use."),
            validity_conditions=("0 < two_theta < 180 degrees.", "wavelength > 0."),
            feature_role="diagnostic",
        ),
        _constraint(
            "xrd.scherrer.preconditions",
            "Scherrer crystallite-size preconditions",
            "xrd",
            "empirical_engineering_law",
            "Scherrer metadata checks require positive FWHM in radians and instrumental-broadening context.",
            evaluator_id="check_scherrer_preconditions",
            required_variables=(
                _var("two_theta", "degree", "angle"),
                _var("wavelength", "angstrom", "length"),
                _var("fwhm", "rad", "angle"),
            ),
            optional_variables=(_var("shape_factor", None, "dimensionless", required=False),),
            expected_units={"two_theta": "degree", "wavelength": "angstrom", "fwhm": "rad"},
            equation_display="D = K lambda / (beta cos(theta))",
            assumptions=("Peak broadening is size-dominated or limitations are documented.", "Instrumental broadening is handled separately."),
            validity_conditions=("FWHM beta is in radians.", "theta is not near 90 degrees.", "crystallite estimate is not particle size."),
            invalidity_conditions=("Strain/size broadening is not separable.", "Instrumental broadening is unknown."),
            feature_role="derived_feature_candidate",
            claim_impact="narrow_claim",
        ),
        _constraint(
            "xrd.crystallite_size.positive",
            "Crystallite-size estimate positive",
            "xrd",
            "domain_constraint",
            "Derived crystallite-size estimates must be positive and should not be called particle size.",
            evaluator_id="check_positive",
            required_variables=(_var("crystallite_size", "nm", "length"),),
            expected_units={"crystallite_size": "nm"},
            feature_role="post_derivation_check",
            claim_impact="narrow_claim",
        ),
    ]
    for constraint in constraints:
        registry.register(constraint)
    return registry
