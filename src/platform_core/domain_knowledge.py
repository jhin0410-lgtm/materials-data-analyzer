"""Domain-knowledge pack metadata for the platform scaffold."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DomainVariableDefinition:
    variable_id: str
    description: str
    dimension: str | None = None
    canonical_unit: str | None = None
    availability: str = "preferred"

    def to_dict(self) -> dict[str, object]:
        return {
            "variable_id": self.variable_id,
            "description": self.description,
            "dimension": self.dimension,
            "canonical_unit": self.canonical_unit,
            "availability": self.availability,
        }


@dataclass(frozen=True)
class DomainAssumption:
    assumption_id: str
    description: str
    claim_boundary: str

    def to_dict(self) -> dict[str, object]:
        return {
            "assumption_id": self.assumption_id,
            "description": self.description,
            "claim_boundary": self.claim_boundary,
        }


@dataclass(frozen=True)
class DomainMechanism:
    mechanism_id: str
    description: str
    evidence_required: tuple[str, ...] = ()
    status: str = "metadata_candidate"

    def to_dict(self) -> dict[str, object]:
        return {
            "mechanism_id": self.mechanism_id,
            "description": self.description,
            "evidence_required": list(self.evidence_required),
            "status": self.status,
        }


@dataclass(frozen=True)
class DomainFeatureDefinition:
    feature_id: str
    description: str
    source_variables: tuple[str, ...]
    status: str = "feature_candidate"
    cautions: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "feature_id": self.feature_id,
            "description": self.description,
            "source_variables": list(self.source_variables),
            "status": self.status,
            "cautions": list(self.cautions),
        }


@dataclass(frozen=True)
class DomainKnowledgePack:
    pack_id: str
    domain: str
    name: str
    description: str
    constraint_ids: tuple[str, ...]
    variables: tuple[DomainVariableDefinition, ...] = ()
    assumptions: tuple[DomainAssumption, ...] = ()
    mechanisms: tuple[DomainMechanism, ...] = ()
    feature_definitions: tuple[DomainFeatureDefinition, ...] = ()
    cautions: tuple[str, ...] = ()
    status: str = "metadata_only"
    version: str = "1"

    def to_dict(self) -> dict[str, object]:
        return {
            "pack_id": self.pack_id,
            "domain": self.domain,
            "name": self.name,
            "description": self.description,
            "constraint_ids": list(self.constraint_ids),
            "variables": [item.to_dict() for item in self.variables],
            "assumptions": [item.to_dict() for item in self.assumptions],
            "mechanisms": [item.to_dict() for item in self.mechanisms],
            "feature_definitions": [item.to_dict() for item in self.feature_definitions],
            "cautions": list(self.cautions),
            "status": self.status,
            "version": self.version,
        }


@dataclass
class DomainKnowledgeRegistry:
    _packs: dict[str, DomainKnowledgePack] = field(default_factory=dict)

    def register(self, pack: DomainKnowledgePack) -> None:
        if pack.pack_id in self._packs:
            raise ValueError(f"duplicate knowledge pack_id: {pack.pack_id}")
        self._packs[pack.pack_id] = pack

    def get(self, pack_id: str) -> DomainKnowledgePack:
        try:
            return self._packs[pack_id]
        except KeyError as exc:
            raise KeyError(f"unknown knowledge pack_id: {pack_id}") from exc

    def list_packs(self, domain: str | None = None) -> list[DomainKnowledgePack]:
        packs = self._packs.values()
        if domain is not None:
            packs = [pack for pack in packs if pack.domain == domain]
        return [self._packs[key] for key in sorted(pack.pack_id for pack in packs)]

    def snapshot(self, domain: str | None = None) -> list[dict[str, object]]:
        return [pack.to_dict() for pack in self.list_packs(domain)]


def _var(variable_id: str, description: str, dimension: str | None = None, unit: str | None = None, availability: str = "preferred") -> DomainVariableDefinition:
    return DomainVariableDefinition(variable_id, description, dimension, unit, availability)


def build_default_domain_knowledge_registry() -> DomainKnowledgeRegistry:
    registry = DomainKnowledgeRegistry()
    registry.register(
        DomainKnowledgePack(
            pack_id="materials_basic_v1",
            domain="materials",
            name="Materials composition and calculated-property basics",
            description="Metadata pack for composition fractions, calculated energies, and conservative feature candidates.",
            constraint_ids=(
                "materials.composition_fraction.non_negative",
                "materials.composition_fraction.sum_to_one",
                "materials.energy_above_hull.non_negative_tolerance",
                "materials.oxidation_state.charge_balance_metadata",
            ),
            variables=(
                _var("composition_fraction", "Atomic or composition fraction.", "dimensionless", "fraction", "required"),
                _var("atomic_radius", "Element-level atomic radius for descriptor candidates.", "length", "angstrom"),
                _var("electronegativity", "Element electronegativity descriptor candidate.", "dimensionless"),
                _var("valence_electron_count", "Element valence-electron descriptor candidate.", "dimensionless"),
                _var("oxidation_state", "Explicit oxidation-state metadata.", "dimensionless", None, "optional"),
                _var("formation_energy", "Calculated formation energy.", "energy", "eV"),
                _var("energy_above_hull_ev_atom", "Calculated energy above hull per atom.", "energy", "eV"),
                _var("density", "Material density metadata.", None, None, "optional"),
                _var("crystal_system", "Crystal system label.", None, None, "optional"),
                _var("lattice_parameter", "Lattice parameter metadata.", "length", "angstrom", "optional"),
            ),
            feature_definitions=(
                DomainFeatureDefinition("weighted_property_mean", "Composition-weighted element property mean.", ("composition_fraction",), cautions=("Descriptor only; not a DFT replacement.",)),
                DomainFeatureDefinition("radius_mismatch_candidate", "Composition-based atomic-radius mismatch candidate.", ("composition_fraction", "atomic_radius")),
                DomainFeatureDefinition("electronegativity_mismatch_candidate", "Composition-based electronegativity mismatch candidate.", ("composition_fraction", "electronegativity")),
            ),
            cautions=(
                "Small negative energy-above-hull values can be numerical tolerance, not a hard physical violation.",
                "Thermodynamic stability is not a synthesizability guarantee.",
                "Oxidation-state metadata failure does not prove a material is impossible.",
            ),
        )
    )
    registry.register(
        DomainKnowledgePack(
            pack_id="battery_degradation_basic_v1",
            domain="battery",
            name="Battery degradation metadata basics",
            description="Metadata pack for cycle-level battery aging variables and conservative derived features.",
            constraint_ids=(
                "battery.capacity.non_negative",
                "battery.coulombic_efficiency.bounds",
                "battery.cycle_index.non_decreasing",
                "battery.temperature.arrhenius_domain",
            ),
            variables=(
                _var("capacity", "Charge or discharge capacity.", "capacity", "Ah", "required"),
                _var("voltage", "Cell voltage.", "voltage", "V"),
                _var("current", "Cell current.", "current", "A"),
                _var("resistance", "Internal resistance metadata.", "resistance", "ohm", "optional"),
                _var("temperature", "Cell or ambient temperature.", "temperature", "K"),
                _var("cycle_index", "Cycle counter.", "dimensionless", None, "required"),
                _var("c_rate", "Charge/discharge C-rate metadata.", "dimensionless", None, "optional"),
                _var("soc", "State of charge.", "dimensionless", "fraction", "optional"),
                _var("dod", "Depth of discharge.", "dimensionless", "fraction", "optional"),
            ),
            feature_definitions=(
                DomainFeatureDefinition("capacity_retention", "Capacity divided by train-defined or series-defined baseline.", ("capacity",)),
                DomainFeatureDefinition("resistance_growth", "Resistance change over available prior observations.", ("resistance",)),
                DomainFeatureDefinition("dq_dv_candidate", "dQ/dV candidate when high-resolution voltage/capacity data exists.", ("capacity", "voltage"), "future_feature_candidate"),
            ),
            mechanisms=(
                DomainMechanism("calendar_aging", "Time-dependent aging mechanism requiring storage-time and temperature evidence.", ("temperature", "storage_time")),
                DomainMechanism("cycle_aging", "Cycle-dependent aging mechanism requiring cycle and usage evidence.", ("cycle_index", "current")),
            ),
            cautions=(
                "Do not force monotonic capacity decrease; recovery and measurement artifacts can occur.",
                "Arrhenius reasoning is limited to justified temperature/mechanism ranges.",
            ),
        )
    )
    registry.register(
        DomainKnowledgePack(
            pack_id="manufacturing_process_basic_v1",
            domain="manufacturing",
            name="Manufacturing process metadata basics",
            description="Metadata pack for process ranges, sensor semantics, and process-window diagnostics.",
            constraint_ids=("manufacturing.flow.non_negative", "manufacturing.process_window.closed_interval"),
            variables=(
                _var("temperature", "Process temperature.", "temperature", "K"),
                _var("pressure", "Process pressure.", "pressure", "Pa"),
                _var("flow_rate", "Material or gas flow rate.", None, None),
                _var("power", "Process power metadata.", None, None),
                _var("recipe_setpoint", "Recipe target or setpoint.", None, None),
                _var("equipment_range", "Equipment operating range metadata.", None, None),
                _var("residence_time", "Cycle or residence time.", "time", "s"),
            ),
            feature_definitions=(
                DomainFeatureDefinition("setpoint_deviation", "Difference between observed value and known recipe setpoint.", ("process_value", "recipe_setpoint")),
                DomainFeatureDefinition("process_window_distance", "Distance to equipment/process-window boundary.", ("process_value", "equipment_range")),
                DomainFeatureDefinition("mass_balance_residual_candidate", "Mass balance residual candidate when in/out flow semantics are known.", ("flow_rate",), "future_feature_candidate"),
            ),
            cautions=(
                "Anonymous UCI SECOM features cannot be assigned physical constraints without semantic metadata.",
                "Mass or energy balance residuals require known process topology and units.",
            ),
        )
    )
    registry.register(
        DomainKnowledgePack(
            pack_id="reliability_degradation_basic_v1",
            domain="reliability",
            name="Reliability degradation metadata basics",
            description="Metadata pack for asset history, event chronology, degradation trajectory, and censoring boundaries.",
            constraint_ids=(
                "reliability.cumulative_exposure.non_decreasing",
                "reliability.degradation_indicator.non_negative",
                "reliability.post_event.feature_prohibition",
            ),
            variables=(
                _var("asset_age", "Age or time since first observation.", "time", "day"),
                _var("load", "Operating load or stress metadata.", None, None, "optional"),
                _var("temperature", "Operating temperature.", "temperature", "K", "optional"),
                _var("stress_amplitude", "Stress amplitude for fatigue law candidates.", None, None, "optional"),
                _var("cycle_count", "Cumulative cycle count.", "dimensionless"),
                _var("degradation_indicator", "Health or wear indicator with known semantics.", None, None),
                _var("failure", "Observed event indicator.", "dimensionless"),
                _var("maintenance", "Maintenance action metadata.", None, None, "optional"),
            ),
            feature_definitions=(
                DomainFeatureDefinition("degradation_slope_candidate", "Prior-window degradation slope candidate.", ("degradation_indicator", "asset_age")),
                DomainFeatureDefinition("arrhenius_acceleration_candidate", "Temperature acceleration candidate when mechanism evidence exists.", ("temperature",), "future_feature_candidate"),
                DomainFeatureDefinition("miner_rule_metadata_candidate", "Miner damage accumulation metadata candidate when stress cycles exist.", ("stress_amplitude", "cycle_count"), "future_feature_candidate"),
            ),
            cautions=(
                "Backblaze SMART variables have limited physical mechanism semantics.",
                "A failure flag is an observed event candidate, not a confirmed physical mechanism.",
                "Hazard monotonicity is not universal.",
            ),
        )
    )
    registry.register(
        DomainKnowledgePack(
            pack_id="xrd_crystallography_basic_v1",
            domain="xrd",
            name="XRD crystallography metadata basics",
            description="Metadata pack for Bragg geometry and Scherrer crystallite-size precondition checks.",
            constraint_ids=(
                "xrd.two_theta.valid_range",
                "xrd.wavelength.positive",
                "xrd.bragg.geometry",
                "xrd.scherrer.preconditions",
                "xrd.crystallite_size.positive",
            ),
            variables=(
                _var("two_theta", "Diffraction peak position as two-theta.", "angle", "degree", "required"),
                _var("wavelength", "X-ray wavelength.", "length", "angstrom", "required"),
                _var("fwhm", "Peak full width at half maximum, beta, in radians for Scherrer.", "angle", "rad"),
                _var("shape_factor", "Scherrer shape factor K.", "dimensionless", None, "optional"),
                _var("instrumental_broadening", "Instrumental broadening metadata.", "angle", "rad", "optional"),
                _var("lattice_spacing", "d-spacing estimate.", "length", "angstrom", "optional"),
                _var("crystallite_size", "Scherrer crystallite-size estimate.", "length", "nm", "optional"),
                _var("miller_indices", "Miller index metadata.", None, None, "optional"),
                _var("lattice_parameter", "Lattice parameter metadata.", "length", "angstrom", "optional"),
            ),
            feature_definitions=(
                DomainFeatureDefinition("bragg_d_spacing_candidate", "d-spacing candidate from Bragg relation when metadata is sufficient.", ("two_theta", "wavelength"), "future_feature_candidate"),
                DomainFeatureDefinition("scherrer_crystallite_size_candidate", "Crystallite-size estimate, not particle size.", ("two_theta", "wavelength", "fwhm"), "future_feature_candidate", ("Requires instrumental broadening/strain limitations.",)),
            ),
            cautions=(
                "Bragg metadata checks do not identify phase.",
                "Scherrer estimates crystallite size, not particle size.",
                "FWHM beta must be in radians and instrument broadening must be documented.",
            ),
        )
    )
    return registry
