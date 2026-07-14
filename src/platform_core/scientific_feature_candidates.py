"""Scientific feature-candidate metadata.

Feature candidates are registry records only. They do not compute feature
values, create feature datasets, or imply predictive usefulness.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


FEATURE_ELIGIBILITY_STATUSES = (
    "eligible_bounded",
    "eligible_with_metadata_requirement",
    "diagnostic_only",
    "unavailable_missing_variable",
    "unavailable_missing_unit",
    "blocked_leakage_risk",
    "blocked_invalid_assumption",
    "blocked_unstable_definition",
    "blocked_claim_overreach",
)

FEATURE_REGISTRY_STATUSES = (
    "metadata_only",
    "bounded_builder_candidate",
    "validation_required",
    "blocked",
    "deprecated_candidate",
)

LEAKAGE_STATUSES = (
    "none",
    "low",
    "metadata_required",
    "requires_prediction_cutoff",
    "blocked_leakage_risk",
)


@dataclass(frozen=True)
class ScientificFeatureCandidate:
    feature_id: str
    name: str
    domain: str
    knowledge_pack_id: str
    source_constraint_ids: tuple[str, ...]
    required_variables: tuple[str, ...]
    required_units: dict[str, str] = field(default_factory=dict)
    output_unit: str | None = None
    definition_summary: str = ""
    evaluator_or_builder_id: str | None = None
    prediction_time_available: bool = True
    leakage_risk: str = "none"
    applicability_requirements: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    validity_conditions: tuple[str, ...] = ()
    expected_claim: str = "physics_informed_feature_available"
    eligibility_status: str = "eligible_with_metadata_requirement"
    validation_status: str = "metadata_only"
    feature_version: str = "1"

    def __post_init__(self) -> None:
        if not self.feature_id:
            raise ValueError("feature_id is required")
        if self.eligibility_status not in FEATURE_ELIGIBILITY_STATUSES:
            raise ValueError(f"unsupported feature eligibility_status: {self.eligibility_status}")
        if self.validation_status not in FEATURE_REGISTRY_STATUSES:
            raise ValueError(f"unsupported feature validation_status: {self.validation_status}")
        if self.leakage_risk not in LEAKAGE_STATUSES:
            raise ValueError(f"unsupported leakage_risk: {self.leakage_risk}")
        if not self.knowledge_pack_id:
            raise ValueError("knowledge_pack_id is required")

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_id": self.feature_id,
            "name": self.name,
            "domain": self.domain,
            "knowledge_pack_id": self.knowledge_pack_id,
            "source_constraint_ids": list(self.source_constraint_ids),
            "required_variables": list(self.required_variables),
            "required_units": dict(self.required_units),
            "output_unit": self.output_unit,
            "definition_summary": self.definition_summary,
            "evaluator_or_builder_id": self.evaluator_or_builder_id,
            "prediction_time_available": self.prediction_time_available,
            "leakage_risk": self.leakage_risk,
            "applicability_requirements": list(self.applicability_requirements),
            "assumptions": list(self.assumptions),
            "validity_conditions": list(self.validity_conditions),
            "expected_claim": self.expected_claim,
            "eligibility_status": self.eligibility_status,
            "validation_status": self.validation_status,
            "feature_version": self.feature_version,
        }


def _candidate(
    feature_id: str,
    name: str,
    domain: str,
    knowledge_pack_id: str,
    source_constraint_ids: tuple[str, ...],
    required_variables: tuple[str, ...],
    *,
    required_units: dict[str, str] | None = None,
    output_unit: str | None = None,
    definition_summary: str,
    evaluator_or_builder_id: str | None = None,
    prediction_time_available: bool = True,
    leakage_risk: str = "none",
    applicability_requirements: tuple[str, ...] = (),
    assumptions: tuple[str, ...] = (),
    validity_conditions: tuple[str, ...] = (),
    expected_claim: str = "physics_informed_feature_available",
    eligibility_status: str = "eligible_with_metadata_requirement",
    validation_status: str = "metadata_only",
) -> ScientificFeatureCandidate:
    return ScientificFeatureCandidate(
        feature_id=feature_id,
        name=name,
        domain=domain,
        knowledge_pack_id=knowledge_pack_id,
        source_constraint_ids=source_constraint_ids,
        required_variables=required_variables,
        required_units=required_units or {},
        output_unit=output_unit,
        definition_summary=definition_summary,
        evaluator_or_builder_id=evaluator_or_builder_id,
        prediction_time_available=prediction_time_available,
        leakage_risk=leakage_risk,
        applicability_requirements=applicability_requirements,
        assumptions=assumptions,
        validity_conditions=validity_conditions,
        expected_claim=expected_claim,
        eligibility_status=eligibility_status,
        validation_status=validation_status,
    )


def default_scientific_feature_candidates() -> tuple[ScientificFeatureCandidate, ...]:
    """Return deterministic metadata-only candidate records."""

    materials_constraints = (
        "materials.composition_fraction.non_negative",
        "materials.composition_fraction.sum_to_one",
    )
    return (
        _candidate(
            "materials.composition_weighted_mean",
            "Composition-weighted property mean",
            "materials",
            "materials_basic_v1",
            materials_constraints,
            ("composition_fraction", "element_property"),
            required_units={"composition_fraction": "fraction"},
            definition_summary="Weighted average of a vetted element property over composition fractions.",
            applicability_requirements=("element property source and provenance are required",),
            assumptions=("composition fractions are prediction-time available and normalized",),
            validity_conditions=("element property values are finite",),
        ),
        _candidate(
            "materials.composition_weighted_variance",
            "Composition-weighted property variance",
            "materials",
            "materials_basic_v1",
            materials_constraints,
            ("composition_fraction", "element_property"),
            required_units={"composition_fraction": "fraction"},
            definition_summary="Weighted variance of a vetted element property over composition fractions.",
            applicability_requirements=("element property source and provenance are required",),
            assumptions=("not a thermodynamic stability claim",),
        ),
        _candidate(
            "materials.atomic_radius_mismatch",
            "Atomic-radius mismatch candidate",
            "materials",
            "materials_basic_v1",
            materials_constraints,
            ("composition_fraction", "atomic_radius"),
            required_units={"composition_fraction": "fraction", "atomic_radius": "angstrom"},
            output_unit="angstrom",
            definition_summary="Composition-weighted radius mismatch descriptor candidate.",
            assumptions=("atomic-radius table is fixed and documented",),
        ),
        _candidate(
            "materials.electronegativity_mismatch",
            "Electronegativity mismatch candidate",
            "materials",
            "materials_basic_v1",
            materials_constraints,
            ("composition_fraction", "electronegativity"),
            required_units={"composition_fraction": "fraction"},
            definition_summary="Composition-based electronegativity spread descriptor candidate.",
            assumptions=("electronegativity scale is fixed and documented",),
        ),
        _candidate(
            "materials.configurational_mixing_entropy",
            "Configurational mixing entropy candidate",
            "materials",
            "materials_basic_v1",
            materials_constraints,
            ("composition_fraction",),
            required_units={"composition_fraction": "fraction"},
            definition_summary="Ideal configurational entropy candidate from composition fractions.",
            assumptions=("ideal mixing approximation only",),
            validity_conditions=("all fractions are non-negative and sum to one",),
        ),
        _candidate(
            "battery.capacity_retention",
            "Capacity-retention candidate",
            "battery",
            "battery_degradation_basic_v1",
            ("battery.capacity.non_negative",),
            ("capacity", "baseline_capacity"),
            required_units={"capacity": "Ah", "baseline_capacity": "Ah"},
            definition_summary="Capacity divided by a predeclared or train-derived baseline.",
            assumptions=("baseline is defined without future/test leakage",),
            validity_conditions=("baseline is positive",),
            validation_status="bounded_builder_candidate",
        ),
        _candidate(
            "battery.coulombic_efficiency_deviation",
            "Coulombic-efficiency deviation candidate",
            "battery",
            "battery_degradation_basic_v1",
            ("battery.coulombic_efficiency.bounds",),
            ("coulombic_efficiency",),
            required_units={"coulombic_efficiency": "fraction"},
            definition_summary="Deviation of coulombic efficiency from a documented reference value.",
            assumptions=("integration method is consistent",),
        ),
        _candidate(
            "battery.resistance_growth_rate",
            "Resistance-growth-rate candidate",
            "battery",
            "battery_degradation_basic_v1",
            ("battery.cycle_index.non_decreasing",),
            ("resistance", "cycle_index"),
            definition_summary="Prior-window resistance slope candidate when resistance semantics are available.",
            leakage_risk="requires_prediction_cutoff",
            assumptions=("uses only observations up to prediction origin",),
        ),
        _candidate(
            "battery.temperature_exposure_summary",
            "Temperature-exposure summary candidate",
            "battery",
            "battery_degradation_basic_v1",
            ("battery.temperature.arrhenius_domain",),
            ("temperature",),
            required_units={"temperature": "K"},
            definition_summary="Temperature exposure metadata candidate, not an Arrhenius mechanism proof.",
            eligibility_status="diagnostic_only",
            assumptions=("mechanism evidence is unavailable by default",),
        ),
        _candidate(
            "xrd.bragg_d_spacing",
            "Bragg d-spacing candidate",
            "xrd",
            "xrd_crystallography_basic_v1",
            ("xrd.bragg.geometry",),
            ("two_theta", "wavelength"),
            required_units={"two_theta": "degree", "wavelength": "angstrom"},
            output_unit="angstrom",
            definition_summary="d-spacing estimate from Bragg relation for supplied peak metadata.",
            evaluator_or_builder_id="check_bragg_geometry",
            validation_status="bounded_builder_candidate",
            assumptions=("input is two-theta, not theta", "order is supplied or n=1 default is accepted"),
        ),
        _candidate(
            "xrd.scherrer_crystallite_size",
            "Scherrer crystallite-size candidate",
            "xrd",
            "xrd_crystallography_basic_v1",
            ("xrd.scherrer.preconditions",),
            ("two_theta", "wavelength", "fwhm"),
            required_units={"two_theta": "degree", "wavelength": "angstrom", "fwhm": "rad"},
            output_unit="nm",
            definition_summary="Bounded crystallite-size estimate; not particle size.",
            evaluator_or_builder_id="check_scherrer_preconditions",
            validation_status="bounded_builder_candidate",
            assumptions=("instrumental and strain broadening limitations are documented",),
            validity_conditions=("FWHM is positive and in radians",),
        ),
        _candidate(
            "manufacturing.process_window_distance",
            "Process-window distance candidate",
            "manufacturing",
            "manufacturing_process_basic_v1",
            ("manufacturing.process_window.closed_interval",),
            ("process_value", "equipment_range"),
            definition_summary="Distance to a known equipment/process-window boundary when semantics are explicit.",
            eligibility_status="diagnostic_only",
            applicability_requirements=("sensor semantics and equipment limits are required",),
        ),
        _candidate(
            "manufacturing.mass_balance_residual_candidate",
            "Mass-balance residual candidate",
            "manufacturing",
            "manufacturing_process_basic_v1",
            ("manufacturing.flow.non_negative",),
            ("flow_rate",),
            definition_summary="Mass-balance residual candidate when in/out flow topology and units are known.",
            eligibility_status="unavailable_missing_variable",
            applicability_requirements=("process topology and semantic flow variables are required",),
            validation_status="validation_required",
        ),
        _candidate(
            "reliability.cumulative_exposure",
            "Cumulative-exposure candidate",
            "reliability",
            "reliability_degradation_basic_v1",
            ("reliability.cumulative_exposure.non_decreasing",),
            ("cumulative_exposure",),
            definition_summary="Prior-known cumulative exposure or age feature candidate.",
            leakage_risk="requires_prediction_cutoff",
            assumptions=("does not use final lifetime or future observation end",),
        ),
        _candidate(
            "reliability.degradation_slope",
            "Degradation-slope candidate",
            "reliability",
            "reliability_degradation_basic_v1",
            ("reliability.degradation_indicator.non_negative",),
            ("degradation_indicator", "observation_timestamp"),
            definition_summary="Prior-window degradation slope candidate with explicit indicator semantics.",
            leakage_risk="requires_prediction_cutoff",
            assumptions=("rolling window uses only past observations",),
            validation_status="validation_required",
        ),
    )
