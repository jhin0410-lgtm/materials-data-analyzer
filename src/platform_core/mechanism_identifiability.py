"""Battery mechanism sufficiency and identifiability audit.

This module audits whether the current Battery PGIR representation can support
bounded dynamic mechanism evaluators. It reads compact processed battery
summaries, records evidence gaps, and exports deterministic compact artifacts.
It does not fit parameters, solve equations, train models, infer hidden state,
or call external services.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

import pandas as pd


BATTERY_MECHANISM_AUDIT_VERSION = "2.3.3"
DEFAULT_SOURCE_PATH = "data/processed/kaggle_nasa_battery_analysis_ready_with_features.csv"
FALLBACK_SOURCE_PATH = "data/processed/kaggle_nasa_battery_cycle_summary_analysis_ready.csv"
LOCAL_OUTPUT_ROOT = "outputs/battery_mechanism_audit_v2_3"

TRACKED_OUTPUTS = {
    "condition_coverage": "data/processed/battery_v2_3_3_condition_coverage_summary.csv",
    "protocol_comparability": "data/processed/battery_v2_3_3_protocol_comparability_summary.csv",
    "mechanism_candidate": "data/processed/battery_v2_3_3_mechanism_candidate_summary.csv",
    "identifiability": "data/processed/battery_v2_3_3_identifiability_summary.csv",
    "evidence_gap": "data/processed/battery_v2_3_3_evidence_gap_summary.csv",
    "operator_selection": "data/processed/battery_v2_3_3_operator_selection_decision.json",
    "report_summary": "data/processed/battery_v2_3_3_report_summary.md",
}


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    return str(value)


def canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_json_safe(payload), indent=2, sort_keys=True) + "\n"


def _checksum_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _checksum_mapping(payload: Mapping[str, Any]) -> str:
    return _checksum_bytes(json.dumps(_json_safe(payload), sort_keys=True, separators=(",", ":")).encode("utf-8"))


def _safe_int(value: Any) -> int:
    if value is None:
        return 0
    numeric = pd.to_numeric(value, errors="coerce")
    if pd.isna(numeric):
        return 0
    return int(numeric)


def _safe_float(value: Any) -> float | None:
    numeric = pd.to_numeric(value, errors="coerce")
    if pd.isna(numeric):
        return None
    result = float(numeric)
    return result if math.isfinite(result) else None


def _bool_text(value: bool) -> str:
    return "true" if value else "false"


def _resolve_repo_path(repo_root: str | Path, relative_path: str | Path) -> Path:
    root = Path(repo_root).resolve()
    normalized = Path(str(relative_path).replace("\\", "/"))
    if normalized.is_absolute() or ".." in normalized.parts:
        raise ValueError("path must be repository-relative and non-traversing")
    target = (root / normalized).resolve()
    if root != target and root not in target.parents:
        raise ValueError(f"path escapes repository root: {relative_path}")
    return target


def _safe_local_output(repo_root: str | Path, relative_path: str | Path) -> Path:
    normalized = str(relative_path).replace("\\", "/")
    if not normalized.startswith(LOCAL_OUTPUT_ROOT + "/"):
        raise ValueError(f"local audit output must stay under {LOCAL_OUTPUT_ROOT}/")
    return _resolve_repo_path(repo_root, normalized)


def _atomic_write_text(path: Path, content: str, *, overwrite: bool = True) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"refusing to overwrite existing file: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="", delete=False, dir=path.parent, prefix=f".{path.name}.", suffix=".tmp") as handle:
        temp = Path(handle.name)
        handle.write(content)
    try:
        temp.replace(path)
    except Exception:
        temp.unlink(missing_ok=True)
        raise


def _atomic_write_csv(path: Path, rows: Iterable[Mapping[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="", delete=False, dir=path.parent, prefix=f".{path.name}.", suffix=".tmp") as handle:
        temp = Path(handle.name)
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _json_safe(row.get(field)) for field in fieldnames})
    try:
        temp.replace(path)
    except Exception:
        temp.unlink(missing_ok=True)
        raise


@dataclass(frozen=True)
class MechanismRequirement:
    requirement_id: str
    mechanism_id: str
    requirement_type: str
    required_concept: str
    required_evidence: str
    minimum_status: str
    required_for_execution: bool
    prohibited_substitute: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "requirement_id": self.requirement_id,
            "mechanism_id": self.mechanism_id,
            "requirement_type": self.requirement_type,
            "required_concept": self.required_concept,
            "required_evidence": self.required_evidence,
            "minimum_status": self.minimum_status,
            "required_for_execution": self.required_for_execution,
            "prohibited_substitute": self.prohibited_substitute,
        }


@dataclass(frozen=True)
class MechanismCandidate:
    mechanism_id: str
    mechanism_family: str
    scientific_meaning: str
    required_pgir_concepts: tuple[str, ...]
    possible_operator_role: str
    current_implementation_status: str
    requirements: tuple[MechanismRequirement, ...]
    prohibited_interpretations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "mechanism_id": self.mechanism_id,
            "mechanism_family": self.mechanism_family,
            "scientific_meaning": self.scientific_meaning,
            "required_pgir_concepts": list(self.required_pgir_concepts),
            "possible_operator_role": self.possible_operator_role,
            "current_implementation_status": self.current_implementation_status,
            "requirements": [requirement.to_dict() for requirement in self.requirements],
            "prohibited_interpretations": list(self.prohibited_interpretations),
        }


@dataclass(frozen=True)
class EvidenceBinding:
    mechanism_id: str
    requirement_id: str
    evidence_status: str
    evidence_ref: str
    maturity_level: str
    context: str
    completeness: str
    uncertainty: str
    limitation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "mechanism_id": self.mechanism_id,
            "requirement_id": self.requirement_id,
            "evidence_status": self.evidence_status,
            "evidence_ref": self.evidence_ref,
            "maturity_level": self.maturity_level,
            "context": self.context,
            "completeness": self.completeness,
            "uncertainty": self.uncertainty,
            "limitation": self.limitation,
        }


@dataclass(frozen=True)
class IdentifiabilityAssessment:
    mechanism_id: str
    structural_status: str
    practical_status: str
    contextual_status: str
    overall_status: str
    blocking_reasons: tuple[str, ...]
    supported_role: str
    prohibited_promotions: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "mechanism_id": self.mechanism_id,
            "structural_status": self.structural_status,
            "practical_status": self.practical_status,
            "contextual_status": self.contextual_status,
            "overall_status": self.overall_status,
            "blocking_reasons": list(self.blocking_reasons),
            "supported_role": self.supported_role,
            "prohibited_promotions": list(self.prohibited_promotions),
        }


@dataclass(frozen=True)
class ConfoundingAssessment:
    mechanism_id: str
    likely_confounders: tuple[str, ...]
    observed_confounders: tuple[str, ...]
    unobserved_confounders: tuple[str, ...]
    controllability: str
    stratification_feasibility: str
    residual_confounding_risk: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "mechanism_id": self.mechanism_id,
            "likely_confounders": list(self.likely_confounders),
            "observed_confounders": list(self.observed_confounders),
            "unobserved_confounders": list(self.unobserved_confounders),
            "controllability": self.controllability,
            "stratification_feasibility": self.stratification_feasibility,
            "residual_confounding_risk": self.residual_confounding_risk,
        }


@dataclass(frozen=True)
class EvidenceGapRecommendation:
    gap_id: str
    mechanism_id: str
    missing_concept: str
    missing_variable: str
    required_unit: str
    required_context: str
    acquisition_method_candidate: str
    external_data_required: bool
    current_source_can_be_enriched: bool
    scientific_impact: str
    priority: str
    prohibited_workaround: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "gap_id": self.gap_id,
            "mechanism_id": self.mechanism_id,
            "missing_concept": self.missing_concept,
            "missing_variable": self.missing_variable,
            "required_unit": self.required_unit,
            "required_context": self.required_context,
            "acquisition_method_candidate": self.acquisition_method_candidate,
            "external_data_required": self.external_data_required,
            "current_source_can_be_enriched": self.current_source_can_be_enriched,
            "scientific_impact": self.scientific_impact,
            "priority": self.priority,
            "prohibited_workaround": self.prohibited_workaround,
        }


@dataclass(frozen=True)
class MechanismSelectionDecision:
    status: str
    selected_evaluator_id: str | None
    selected_mechanism_id: str | None
    selected_operator_role: str
    rationale: tuple[str, ...]
    rejected_mechanisms: tuple[dict[str, Any], ...]
    allowed_claims: tuple[str, ...]
    prohibited_claims: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": BATTERY_MECHANISM_AUDIT_VERSION,
            "status": self.status,
            "selected_evaluator_id": self.selected_evaluator_id,
            "selected_mechanism_id": self.selected_mechanism_id,
            "selected_operator_role": self.selected_operator_role,
            "rationale": list(self.rationale),
            "rejected_mechanisms": list(self.rejected_mechanisms),
            "allowed_claims": list(self.allowed_claims),
            "prohibited_claims": list(self.prohibited_claims),
            "network_called": False,
            "model_or_solver_executed": False,
            "parameter_fitting_performed": False,
        }


def _req(
    mechanism_id: str,
    suffix: str,
    requirement_type: str,
    required_concept: str,
    required_evidence: str,
    prohibited_substitute: str,
    *,
    minimum_status: str = "explicit_observed",
    required_for_execution: bool = True,
) -> MechanismRequirement:
    return MechanismRequirement(
        requirement_id=f"{mechanism_id}.{suffix}",
        mechanism_id=mechanism_id,
        requirement_type=requirement_type,
        required_concept=required_concept,
        required_evidence=required_evidence,
        minimum_status=minimum_status,
        required_for_execution=required_for_execution,
        prohibited_substitute=prohibited_substitute,
    )


def build_default_mechanism_candidates() -> tuple[MechanismCandidate, ...]:
    """Return deterministic metadata-only Battery mechanism candidates."""

    candidate_specs: list[MechanismCandidate] = []
    candidate_specs.append(
        MechanismCandidate(
            mechanism_id="arrhenius_temperature_dependence",
            mechanism_family="temperature_dependent_rate_relation",
            scientific_meaning="Rate-like response varies with reciprocal absolute temperature under comparable protocol conditions.",
            required_pgir_concepts=("observation", "state", "parameter", "context", "uncertainty"),
            possible_operator_role="Evaluator",
            current_implementation_status="requirements_audit_only",
            requirements=(
                _req("arrhenius_temperature_dependence", "controlled_temperature_groups", "condition_diversity", "context", "multiple controlled temperature groups with comparable cells", "using transient measured cell temperature as controlled ambient condition"),
                _req("arrhenius_temperature_dependence", "rate_like_response", "response_definition", "result", "explicit rate-like response denominator and semantics", "treating capacity value itself as rate constant"),
                _req("arrhenius_temperature_dependence", "protocol_comparability", "protocol", "context", "same or explicitly comparable protocol across temperature groups", "assuming comparable protocols from missing metadata"),
                _req("arrhenius_temperature_dependence", "replicates", "replication", "observation", "repeated cells or observations per temperature condition", "treating adjacent cycles as independent replicate cells"),
                _req("arrhenius_temperature_dependence", "uncertainty", "uncertainty", "uncertainty", "variability or measurement uncertainty policy", "using zero uncertainty when source uncertainty is unavailable", required_for_execution=False),
            ),
            prohibited_interpretations=("activation energy estimated", "Arrhenius behavior proven", "causal temperature effect"),
        )
    )
    candidate_specs.append(
        MechanismCandidate(
            mechanism_id="diffusion_transport",
            mechanism_family="transport_relation",
            scientific_meaning="Internal transported quantity evolves over physical time and geometry with defined initial and boundary conditions.",
            required_pgir_concepts=("state", "field", "parameter", "context", "operator"),
            possible_operator_role="Evaluator",
            current_implementation_status="requirements_audit_only",
            requirements=(
                _req("diffusion_transport", "transported_quantity", "state_definition", "field", "concentration-linked state or observation model", "treating terminal voltage as concentration field"),
                _req("diffusion_transport", "geometry", "geometry", "physical_entity", "electrode geometry or characteristic length scale", "using arbitrary default particle radius"),
                _req("diffusion_transport", "initial_conditions", "initial_condition", "state", "initial state definition at transient start", "backfilling initial concentration from cycle index"),
                _req("diffusion_transport", "boundary_conditions", "boundary_condition", "context", "boundary condition and driving force", "assuming boundary conditions from generic charge/discharge labels"),
                _req("diffusion_transport", "transient_time_axis", "time_axis", "observation", "physical elapsed transient time", "using ordered cycle index as diffusion time"),
                _req("diffusion_transport", "transport_protocol", "protocol", "context", "GITT/PITT/EIS or equivalent transport-identifying protocol", "calling general discharge summaries GITT or PITT"),
            ),
            prohibited_interpretations=("diffusion coefficient inferred", "transport mechanism confirmed", "internal concentration reconstructed"),
        )
    )
    candidate_specs.append(
        MechanismCandidate(
            mechanism_id="capacity_fade_trajectory",
            mechanism_family="empirical_degradation_trajectory",
            scientific_meaning="Observed discharge capacity changes along ordered cycle trajectories.",
            required_pgir_concepts=("observation", "state", "trajectory", "context"),
            possible_operator_role="Evaluator",
            current_implementation_status="bounded_descriptive_candidate",
            requirements=(
                _req("capacity_fade_trajectory", "capacity_definition", "observable", "observation", "explicit discharge capacity values and units", "using hidden SOH as direct measurement"),
                _req("capacity_fade_trajectory", "reference_policy", "normalization", "context", "reference capacity policy", "silently changing baseline after audit"),
                _req("capacity_fade_trajectory", "cycle_order", "time_axis", "trajectory", "ordered cycle index with duplicate policy", "treating cycle index as physical elapsed time"),
                _req("capacity_fade_trajectory", "censoring", "context", "context", "end-of-life/censoring policy", "assuming unobserved future failure-free behavior"),
            ),
            prohibited_interpretations=("SEI mechanism proven", "lifetime prediction", "physical law confirmed"),
        )
    )
    candidate_specs.append(
        MechanismCandidate(
            mechanism_id="resistance_growth_trajectory",
            mechanism_family="empirical_resistance_relation",
            scientific_meaning="Observed resistance or impedance-derived scalar changes along cycle trajectories.",
            required_pgir_concepts=("observation", "trajectory", "context"),
            possible_operator_role="Evaluator",
            current_implementation_status="requirements_audit_only",
            requirements=(
                _req("resistance_growth_trajectory", "resistance_field", "observable", "observation", "direct resistance or impedance-derived scalar with definition", "using missing internal resistance as zero"),
                _req("resistance_growth_trajectory", "measurement_protocol", "protocol", "context", "resistance measurement or EIS protocol definition", "calling scalar resistance charge-transfer resistance"),
                _req("resistance_growth_trajectory", "frequency_axis", "protocol", "observation", "frequency axis for impedance claims", "inferring EIS from one scalar field", required_for_execution=False),
            ),
            prohibited_interpretations=("charge-transfer resistance estimated", "diffusion impedance estimated", "equivalent-circuit parameter fitted"),
        )
    )
    for mechanism_id, family, meaning, requirements in (
        (
            "temperature_capacity_coupling",
            "observational_coupling",
            "Capacity observations are summarized against observed ambient or operating temperature metadata.",
            (
                _req("temperature_capacity_coupling", "temperature_metadata", "condition", "context", "temperature field with source semantics", "treating response temperature as controlled condition"),
                _req("temperature_capacity_coupling", "capacity_definition", "observable", "observation", "capacity value and unit", "using derived SOH as direct capacity"),
                _req("temperature_capacity_coupling", "confounders", "context", "context", "cycle age and protocol confounder audit", "promoting correlation to causality"),
            ),
        ),
        (
            "cycle_duration_capacity_coupling",
            "observational_coupling",
            "Capacity observations are summarized against discharge duration when available.",
            (
                _req("cycle_duration_capacity_coupling", "duration_metadata", "time_axis", "observation", "discharge duration field and unit", "treating duration as calendar age"),
                _req("cycle_duration_capacity_coupling", "capacity_definition", "observable", "observation", "capacity value and unit", "using lifetime target as capacity"),
                _req("cycle_duration_capacity_coupling", "protocol_context", "protocol", "context", "protocol/cutoff comparability audit", "assuming duration changes are mechanism evidence"),
            ),
        ),
        (
            "charge_discharge_efficiency_relation",
            "observable_balance_relation",
            "Charge/discharge capacity or energy balance can be audited only when both sides are observed.",
            (
                _req("charge_discharge_efficiency_relation", "charge_capacity", "observable", "observation", "charge capacity or charge energy", "reconstructing charge capacity from discharge only"),
                _req("charge_discharge_efficiency_relation", "discharge_capacity", "observable", "observation", "discharge capacity or discharge energy", "using capacity retention as energy efficiency"),
            ),
        ),
        (
            "empirical_monotonic_degradation",
            "empirical_trajectory_shape",
            "Trajectory monotonicity or local reversals can be audited descriptively without a physical mechanism claim.",
            (
                _req("empirical_monotonic_degradation", "cycle_order", "time_axis", "trajectory", "ordered cycle index with duplicate policy", "using unordered rows"),
                _req("empirical_monotonic_degradation", "capacity_definition", "observable", "observation", "capacity value and unit", "using hidden degradation state"),
            ),
        ),
        (
            "change_point_or_regime_transition",
            "empirical_trajectory_shape",
            "Potential regime transitions can be flagged descriptively when enough ordered observations exist.",
            (
                _req("change_point_or_regime_transition", "trajectory_length", "support", "trajectory", "sufficient ordered observations per cell", "using one or two cycles as regime evidence"),
                _req("change_point_or_regime_transition", "context_stability", "context", "context", "protocol/condition stability audit", "interpreting protocol change as mechanism transition"),
            ),
        ),
        (
            "observation_consistency_only",
            "representation_quality",
            "Observation, State, and Trajectory records can be checked for consistency without mechanism execution.",
            (
                _req("observation_consistency_only", "source_fields", "representation", "observation", "required source fields and units", "inventing missing latent state"),
                _req("observation_consistency_only", "trajectory_order", "representation", "trajectory", "deterministic ordering and duplicate policy", "using row order without cycle metadata"),
            ),
        ),
    ):
        candidate_specs.append(
            MechanismCandidate(
                mechanism_id=mechanism_id,
                mechanism_family=family,
                scientific_meaning=meaning,
                required_pgir_concepts=("observation", "state", "trajectory", "context"),
                possible_operator_role="Evaluator",
                current_implementation_status="requirements_audit_only",
                requirements=requirements,
                prohibited_interpretations=("mechanism confirmed", "causal relation proven", "production decision supported"),
            )
        )
    return tuple(sorted(candidate_specs, key=lambda item: item.mechanism_id))


def mechanism_candidate_registry_payload() -> dict[str, Any]:
    return {
        "schema_version": BATTERY_MECHANISM_AUDIT_VERSION,
        "status": "accepted_for_v2_3",
        "description": "Metadata-only Battery mechanism candidates and requirements for v2.3.3.",
        "candidates": [candidate.to_dict() for candidate in build_default_mechanism_candidates()],
        "execution_boundary": {
            "network_called": False,
            "model_or_solver_executed": False,
            "parameter_fitting_performed": False,
            "row_level_payload_in_registry": False,
        },
    }


def build_evidence_gap_registry() -> tuple[EvidenceGapRecommendation, ...]:
    return (
        EvidenceGapRecommendation("gap_controlled_temperature_groups", "arrhenius_temperature_dependence", "context", "controlled temperature condition", "K", "multiple comparable controlled-temperature groups", "temperature-controlled replicate cycling", True, False, "blocks Arrhenius applicability", "high", "using transient measured cell temperature as controlled condition"),
        EvidenceGapRecommendation("gap_rate_like_response", "arrhenius_temperature_dependence", "result", "rate-like response", "context-specific rate unit", "explicit denominator and response semantics", "protocol-level response definition", True, False, "blocks activation-energy interpretation", "high", "treating capacity itself as a rate constant"),
        EvidenceGapRecommendation("gap_protocol_comparability", "arrhenius_temperature_dependence", "context", "charge/discharge protocol metadata", "not_applicable", "same or explicitly comparable protocol groups", "protocol/cutoff/current metadata enrichment", True, True, "prevents mechanism comparison across cells", "high", "assuming missing protocol metadata implies equality"),
        EvidenceGapRecommendation("gap_electrode_geometry", "diffusion_transport", "physical_entity", "electrode or particle length scale", "m", "geometry and characteristic diffusion length", "cell/electrode metadata acquisition", True, False, "prevents transport-parameter semantics", "high", "using arbitrary default geometry"),
        EvidenceGapRecommendation("gap_concentration_field", "diffusion_transport", "field", "internal concentration field", "mol/m^3", "state or observation model linked to concentration", "GITT/PITT/EIS or physics observation model", True, False, "prevents diffusion state inference", "high", "using terminal voltage as concentration field"),
        EvidenceGapRecommendation("gap_boundary_conditions", "diffusion_transport", "context", "boundary conditions", "not_applicable", "defined transient boundary and driving force", "transport-identifying protocol metadata", True, False, "blocks diffusion execution", "high", "assuming boundary conditions from general discharge summaries"),
        EvidenceGapRecommendation("gap_physical_elapsed_time", "diffusion_transport", "observation", "transient physical time axis", "s", "fine-grained elapsed time within transport transient", "raw time-series protocol audit", True, True, "cycle index cannot parameterize diffusion time", "medium", "using cycle index as seconds or hours"),
        EvidenceGapRecommendation("gap_resistance_definition", "resistance_growth_trajectory", "observation", "resistance measurement definition", "ohm", "explicit measurement method and context", "resistance/EIS metadata enrichment", True, True, "blocks impedance interpretation", "medium", "treating missing resistance as zero"),
        EvidenceGapRecommendation("gap_frequency_axis", "resistance_growth_trajectory", "observation", "EIS frequency axis", "Hz", "frequency-resolved impedance spectra for EIS claims", "EIS source acquisition", True, False, "blocks equivalent-circuit interpretation", "medium", "inferring frequency-dependent impedance from one scalar"),
        EvidenceGapRecommendation("gap_uncertainty_records", "capacity_fade_trajectory", "uncertainty", "measurement uncertainty", "source-specific", "measurement variability or calibration records", "source calibration metadata", False, True, "limits practical identifiability and confidence intervals", "medium", "using zero uncertainty when source does not provide it"),
    )


def evidence_gap_registry_payload() -> dict[str, Any]:
    return {
        "schema_version": BATTERY_MECHANISM_AUDIT_VERSION,
        "status": "accepted_for_v2_3",
        "description": "Evidence gaps and prohibited workarounds for Battery mechanism candidates.",
        "evidence_gaps": [gap.to_dict() for gap in build_evidence_gap_registry()],
        "execution_boundary": {
            "network_called": False,
            "model_or_solver_executed": False,
            "recommendations_only": True,
        },
    }


def load_battery_evidence_frame(repo_root: str | Path = ".", source_path: str | None = None) -> pd.DataFrame:
    root = Path(repo_root).resolve()
    candidates = [source_path] if source_path else [DEFAULT_SOURCE_PATH, FALLBACK_SOURCE_PATH]
    for relative in candidates:
        if relative is None:
            continue
        target = _resolve_repo_path(root, relative)
        if target.exists():
            df = pd.read_csv(target)
            if "battery_id" not in df or "cycle_index" not in df or "discharge_capacity_ah" not in df:
                raise ValueError("Battery evidence source missing required battery_id/cycle_index/discharge_capacity_ah columns")
            return df
    raise FileNotFoundError("no Battery evidence source found")


def audit_battery_evidence_inventory(repo_root: str | Path = ".", source_path: str | None = None) -> dict[str, Any]:
    df = load_battery_evidence_frame(repo_root, source_path)
    cell_count = int(df["battery_id"].nunique())
    cycle_count = int(len(df))
    temp_unique = int(df["ambient_temperature_c"].nunique(dropna=True)) if "ambient_temperature_c" in df else 0
    temp_min = _safe_float(df["ambient_temperature_c"].min()) if "ambient_temperature_c" in df else None
    temp_max = _safe_float(df["ambient_temperature_c"].max()) if "ambient_temperature_c" in df else None
    cycles_per_cell = df.groupby("battery_id").size() if "battery_id" in df else pd.Series(dtype=int)
    resistance_non_null = int(df["internal_resistance_ohm"].notna().sum()) if "internal_resistance_ohm" in df else 0
    duration_non_null = int(df["discharge_duration_s"].notna().sum()) if "discharge_duration_s" in df else 0
    voltage_non_null = int(df["voltage_mean_v"].notna().sum()) if "voltage_mean_v" in df else 0
    current_non_null = int(df["current_mean_a"].notna().sum()) if "current_mean_a" in df else 0
    measured_temp_non_null = int(df["temperature_mean_c"].notna().sum()) if "temperature_mean_c" in df else 0
    source_path_used = DEFAULT_SOURCE_PATH if (Path(repo_root) / DEFAULT_SOURCE_PATH).exists() else FALLBACK_SOURCE_PATH
    return {
        "schema_version": BATTERY_MECHANISM_AUDIT_VERSION,
        "status": "actual_data_inventory_available",
        "source_path": source_path or source_path_used,
        "source_checksum": _checksum_bytes(_resolve_repo_path(repo_root, source_path or source_path_used).read_bytes()),
        "cell_count": cell_count,
        "cycle_count": cycle_count,
        "ambient_temperature_unique_count": temp_unique,
        "ambient_temperature_min_c": temp_min,
        "ambient_temperature_max_c": temp_max,
        "temperature_condition_status": "observed_ambient_temperature_metadata_not_confirmed_controlled",
        "cycle_index_available": "cycle_index" in df,
        "physical_elapsed_time_available": "elapsed_time" in df or "timestamp" in df,
        "discharge_duration_available_rows": duration_non_null,
        "voltage_summary_available_rows": voltage_non_null,
        "current_summary_available_rows": current_non_null,
        "measured_temperature_summary_available_rows": measured_temp_non_null,
        "capacity_available_rows": int(df["discharge_capacity_ah"].notna().sum()),
        "internal_resistance_available_rows": resistance_non_null,
        "charge_capacity_available_rows": int(df["charge_capacity_ah"].notna().sum()) if "charge_capacity_ah" in df else 0,
        "cycle_type_available": "cycle_type" in df,
        "explicit_protocol_identifier_available": "protocol_id" in df or "protocol_label" in df,
        "c_rate_available": "c_rate" in df or "charge_c_rate" in df or "discharge_c_rate" in df,
        "cutoff_metadata_available": "cutoff_voltage" in df or "voltage_min_v" in df and "voltage_max_v" in df,
        "uncertainty_status": "source_does_not_provide_measurement_uncertainty",
        "cycles_per_cell_min": _safe_int(cycles_per_cell.min()) if not cycles_per_cell.empty else 0,
        "cycles_per_cell_median": float(cycles_per_cell.median()) if not cycles_per_cell.empty else 0.0,
        "cycles_per_cell_max": _safe_int(cycles_per_cell.max()) if not cycles_per_cell.empty else 0,
        "network_called": False,
        "model_or_solver_executed": False,
    }


def condition_coverage_rows(df: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if "ambient_temperature_c" not in df:
        return [
            {
                "condition_field": "ambient_temperature_c",
                "condition_value": "unavailable",
                "cell_count": 0,
                "cycle_count": 0,
                "status": "missing_condition_field",
                "condition_semantics": "unavailable",
            }
        ]
    for value, group in df.groupby("ambient_temperature_c", dropna=False):
        rows.append(
            {
                "condition_field": "ambient_temperature_c",
                "condition_value": _json_safe(value),
                "cell_count": int(group["battery_id"].nunique()) if "battery_id" in group else 0,
                "cycle_count": int(len(group)),
                "capacity_rows": int(group["discharge_capacity_ah"].notna().sum()) if "discharge_capacity_ah" in group else 0,
                "duration_rows": int(group["discharge_duration_s"].notna().sum()) if "discharge_duration_s" in group else 0,
                "measured_temperature_rows": int(group["temperature_mean_c"].notna().sum()) if "temperature_mean_c" in group else 0,
                "status": "condition_observed",
                "condition_semantics": "ambient_metadata_not_confirmed_controlled",
            }
        )
    return sorted(rows, key=lambda row: str(row["condition_value"]))


def condition_coverage_summary(repo_root: str | Path = ".", source_path: str | None = None) -> list[dict[str, Any]]:
    return condition_coverage_rows(load_battery_evidence_frame(repo_root, source_path))


def protocol_comparability_summary(repo_root: str | Path = ".", source_path: str | None = None) -> list[dict[str, Any]]:
    df = load_battery_evidence_frame(repo_root, source_path)
    available = {
        "cycle_type": "cycle_type" in df,
        "source_filename": "source_filename" in df,
        "test_id": "test_id" in df,
        "voltage_window_summary": "voltage_min_v" in df and "voltage_max_v" in df,
        "current_summary": "current_mean_a" in df and "current_min_a" in df and "current_max_a" in df,
        "duration_summary": "discharge_duration_s" in df,
        "c_rate": "c_rate" in df or "charge_c_rate" in df or "discharge_c_rate" in df,
        "cutoff_voltage": "cutoff_voltage" in df,
        "rest_period": "rest_period_s" in df,
        "protocol_identifier": "protocol_id" in df or "protocol_label" in df,
    }
    comparable_status = "insufficient_protocol_metadata"
    if available["protocol_identifier"] and available["c_rate"] and available["cutoff_voltage"]:
        comparable_status = "comparable_with_known_differences"
    rows = [
        {
            "protocol_field": key,
            "available": _bool_text(value),
            "coverage_rows": int(df[key].notna().sum()) if key in df else 0,
            "status": "available" if value else "missing",
            "comparability_impact": "required_for_mechanism_comparison" if key in {"protocol_identifier", "c_rate", "cutoff_voltage", "rest_period"} else "supporting_metadata",
        }
        for key, value in sorted(available.items())
    ]
    rows.append(
        {
            "protocol_field": "overall_protocol_comparability",
            "available": "false",
            "coverage_rows": int(len(df)),
            "status": comparable_status,
            "comparability_impact": "blocks Arrhenius and mechanism comparison when exact protocol equality is required",
        }
    )
    return rows


def time_axis_inventory(repo_root: str | Path = ".", source_path: str | None = None) -> list[dict[str, Any]]:
    df = load_battery_evidence_frame(repo_root, source_path)
    rows = []
    for axis_id, field, status, semantics in (
        ("ordered_cycle_index", "cycle_index", "available" if "cycle_index" in df else "missing", "ordered cycle progression, not physical elapsed time"),
        ("discharge_duration", "discharge_duration_s", "available" if "discharge_duration_s" in df else "missing", "per-cycle discharge segment duration"),
        ("physical_elapsed_time", "elapsed_time", "missing" if "elapsed_time" not in df else "available", "physical elapsed time required for kinetic/transient mechanisms"),
        ("calendar_timestamp", "timestamp", "missing" if "timestamp" not in df else "available", "calendar time required for calendar aging"),
    ):
        rows.append(
            {
                "time_axis_id": axis_id,
                "source_field": field,
                "status": status,
                "coverage_rows": int(df[field].notna().sum()) if field in df else 0,
                "semantics": semantics,
                "prohibited_interpretation": "cycle index is not seconds or hours" if axis_id == "ordered_cycle_index" else "",
            }
        )
    return rows


def _evidence_status_for_requirement(requirement: MechanismRequirement, inventory: Mapping[str, Any]) -> EvidenceBinding:
    rid = requirement.requirement_id
    status = "missing"
    completeness = "none"
    ref = "battery_v2_3_3_condition_coverage_summary"
    limitation = "requirement not satisfied by current compact evidence"
    maturity = "semantically_mapped"
    context = "battery_v2_3_3_actual_audit"
    uncertainty = "source_uncertainty_unavailable"

    if "controlled_temperature_groups" in rid:
        has_diversity = _safe_int(inventory.get("ambient_temperature_unique_count")) >= 2
        status = "observed_but_contextually_insufficient" if has_diversity else "missing_condition_variation"
        completeness = "partial" if has_diversity else "none"
        limitation = "ambient temperature groups exist but are not sufficient as controlled Arrhenius conditions without comparable protocol and rate response"
    elif "rate_like_response" in rid:
        status = "missing_response_definition"
        limitation = "capacity and retention are observations, not rate constants"
    elif "protocol_comparability" in rid or "measurement_protocol" in rid or "protocol_context" in rid:
        status = "insufficient_protocol_metadata"
        ref = "battery_v2_3_3_protocol_comparability_summary"
        limitation = "explicit C-rate, cutoff, rest, and protocol identity are incomplete"
    elif "replicates" in rid:
        status = "observed_with_dependence"
        completeness = "partial"
        limitation = "cells and cycles exist, but adjacent cycles are repeated origins rather than independent replicate cells"
    elif "uncertainty" in rid:
        status = "unavailable"
        limitation = "source uncertainty is unavailable; zero uncertainty is prohibited"
    elif "transported_quantity" in rid:
        status = "missing_internal_state"
        limitation = "terminal voltage and capacity summaries are not concentration fields"
    elif "geometry" in rid:
        status = "missing_geometry"
        limitation = "electrode geometry and diffusion length scale are unavailable"
    elif "initial_conditions" in rid:
        status = "missing_initial_conditions"
        limitation = "initial internal concentration state is unavailable"
    elif "boundary_conditions" in rid:
        status = "missing_boundary_conditions"
        limitation = "transport boundary conditions and driving force are unavailable"
    elif "transient_time_axis" in rid:
        status = "insufficient_time_resolution"
        ref = "battery_v2_3_3_condition_coverage_summary"
        limitation = "cycle index is not diffusion time; per-cycle duration is not a full transport transient context"
    elif "transport_protocol" in rid:
        status = "blocked_protocol_not_transport_identifying"
        limitation = "general discharge summaries are not explicitly GITT/PITT/EIS"
    elif "capacity_definition" in rid or "discharge_capacity" in rid:
        rows = _safe_int(inventory.get("capacity_available_rows"))
        status = "available" if rows > 0 else "missing"
        completeness = "complete" if rows == _safe_int(inventory.get("cycle_count")) else "partial"
        limitation = "supports observed capacity trajectory only, not a physical mechanism by itself"
    elif "reference_policy" in rid:
        status = "available"
        completeness = "tracked"
        limitation = "baseline policy is tracked as processed metadata; no silent replacement allowed"
    elif "cycle_order" in rid or "trajectory_order" in rid:
        status = "available"
        completeness = "tracked"
        limitation = "ordered cycle index supports trajectory ordering but not physical elapsed time"
    elif "censoring" in rid:
        status = "partially_available"
        completeness = "partial"
        limitation = "failure/end-of-life is processed as a label, but future lifetime extrapolation is not authorized"
    elif "resistance_field" in rid:
        rows = _safe_int(inventory.get("internal_resistance_available_rows"))
        status = "available" if rows > 0 else "unavailable"
        completeness = "none" if rows == 0 else "partial"
        limitation = "current analysis-ready source has no non-null internal resistance scalar"
    elif "frequency_axis" in rid:
        status = "missing_frequency_axis"
        limitation = "EIS frequency-resolved spectra are unavailable"
    elif "temperature_metadata" in rid:
        status = "available_with_semantic_warning"
        completeness = "partial"
        limitation = "ambient and measured temperature summaries do not prove a controlled temperature intervention"
    elif "duration_metadata" in rid:
        status = "available"
        completeness = "complete" if _safe_int(inventory.get("discharge_duration_available_rows")) == _safe_int(inventory.get("cycle_count")) else "partial"
        limitation = "duration is per-cycle discharge segment metadata, not calendar aging"
    elif "confounders" in rid or "context_stability" in rid:
        status = "confounding_recorded_not_controlled"
        completeness = "partial"
        limitation = "cycle age, cell identity, temperature, and protocol confounding remain"
    elif "charge_capacity" in rid:
        status = "missing_charge_side"
        limitation = "charge capacity or charge energy is unavailable in the current compact source"
    elif "trajectory_length" in rid:
        status = "available_with_short_trajectory_warning"
        completeness = "partial"
        limitation = "trajectory length varies by cell; short trajectories limit regime-transition evidence"
    elif "source_fields" in rid:
        status = "available"
        completeness = "tracked"
        limitation = "supports representation consistency only"

    return EvidenceBinding(
        mechanism_id=requirement.mechanism_id,
        requirement_id=requirement.requirement_id,
        evidence_status=status,
        evidence_ref=ref,
        maturity_level=maturity,
        context=context,
        completeness=completeness,
        uncertainty=uncertainty,
        limitation=limitation,
    )


def bind_mechanism_requirements(
    candidates: Iterable[MechanismCandidate] | None = None,
    inventory: Mapping[str, Any] | None = None,
    repo_root: str | Path = ".",
) -> list[EvidenceBinding]:
    candidates = tuple(candidates or build_default_mechanism_candidates())
    inventory = dict(inventory or audit_battery_evidence_inventory(repo_root))
    bindings: list[EvidenceBinding] = []
    for candidate in candidates:
        for requirement in candidate.requirements:
            bindings.append(_evidence_status_for_requirement(requirement, inventory))
    return sorted(bindings, key=lambda item: (item.mechanism_id, item.requirement_id))


def _bindings_by_mechanism(bindings: Iterable[EvidenceBinding]) -> dict[str, list[EvidenceBinding]]:
    grouped: dict[str, list[EvidenceBinding]] = {}
    for binding in bindings:
        grouped.setdefault(binding.mechanism_id, []).append(binding)
    return grouped


BLOCKING_STATUSES = {
    "missing",
    "missing_condition_variation",
    "missing_response_definition",
    "insufficient_protocol_metadata",
    "missing_internal_state",
    "missing_geometry",
    "missing_initial_conditions",
    "missing_boundary_conditions",
    "insufficient_time_resolution",
    "blocked_protocol_not_transport_identifying",
    "unavailable",
    "missing_frequency_axis",
    "missing_charge_side",
}


def assess_identifiability(
    candidates: Iterable[MechanismCandidate] | None = None,
    bindings: Iterable[EvidenceBinding] | None = None,
    repo_root: str | Path = ".",
) -> list[IdentifiabilityAssessment]:
    candidate_list = tuple(candidates or build_default_mechanism_candidates())
    binding_list = list(bindings or bind_mechanism_requirements(candidate_list, repo_root=repo_root))
    grouped = _bindings_by_mechanism(binding_list)
    assessments: list[IdentifiabilityAssessment] = []
    for candidate in candidate_list:
        candidate_bindings = grouped.get(candidate.mechanism_id, [])
        blocking = tuple(
            binding.evidence_status for binding in candidate_bindings if binding.evidence_status in BLOCKING_STATUSES
        )
        if candidate.mechanism_id in {"capacity_fade_trajectory", "empirical_monotonic_degradation", "observation_consistency_only"}:
            structural = "not_a_physical_mechanism_identifier" if candidate.mechanism_id != "observation_consistency_only" else "representation_only"
            practical = "descriptive_evaluator_possible"
            contextual = "bounded_to_observed_cycle_summary"
            overall = "bounded_empirical_evaluator_candidate" if candidate.mechanism_id == "capacity_fade_trajectory" else "descriptive_only"
            supported_role = "descriptive_evaluator"
            reasons = ("mechanism_not_identified", "no_parameter_fitting_authorized")
        elif candidate.mechanism_id == "arrhenius_temperature_dependence":
            structural = "not_identifiable_from_current_data"
            practical = "blocked_response_definition"
            contextual = "blocked_protocol_confounding"
            overall = "not_identifiable_from_current_data"
            supported_role = "readiness_audit_only"
            reasons = tuple(dict.fromkeys(blocking + ("capacity_is_not_rate_constant", "temperature_correlation_is_not_arrhenius_evidence")))
        elif candidate.mechanism_id == "diffusion_transport":
            structural = "missing_state_observation"
            practical = "blocked_missing_geometry"
            contextual = "blocked_missing_boundary_conditions"
            overall = "not_identifiable_from_current_data"
            supported_role = "readiness_audit_only"
            reasons = tuple(dict.fromkeys(blocking + ("voltage_is_not_concentration_field", "cycle_index_is_not_diffusion_time")))
        elif candidate.mechanism_id == "resistance_growth_trajectory":
            structural = "not_identifiable_from_current_data"
            practical = "blocked_unknown_measurement_definition"
            contextual = "blocked_missing_frequency_axis"
            overall = "not_identifiable_from_current_data"
            supported_role = "readiness_audit_only"
            reasons = tuple(dict.fromkeys(blocking + ("equivalent_circuit_fitting_not_authorized",)))
        else:
            structural = "observational_relation_only"
            practical = "confounded_by_cycle_age"
            contextual = "confounded_by_protocol"
            overall = "descriptive_only"
            supported_role = "readiness_audit_only"
            reasons = tuple(dict.fromkeys(blocking + ("correlation_not_causality",)))
        assessments.append(
            IdentifiabilityAssessment(
                mechanism_id=candidate.mechanism_id,
                structural_status=structural,
                practical_status=practical,
                contextual_status=contextual,
                overall_status=overall,
                blocking_reasons=reasons,
                supported_role=supported_role,
                prohibited_promotions=("mechanism confirmed", "parameter estimated", "predictive model evidence"),
            )
        )
    return sorted(assessments, key=lambda item: item.mechanism_id)


def assess_confounding(candidates: Iterable[MechanismCandidate] | None = None) -> list[ConfoundingAssessment]:
    rows: list[ConfoundingAssessment] = []
    for candidate in candidates or build_default_mechanism_candidates():
        if candidate.mechanism_id == "arrhenius_temperature_dependence":
            likely = ("cycle_age", "cell_identity", "protocol", "ambient_temperature", "measured_operating_temperature", "current_profile")
            observed = ("cell_identity", "cycle_age", "ambient_temperature", "measured_operating_temperature")
            unobserved = ("controlled_protocol_identity", "C_rate", "cutoff_conditions", "rest_period", "batch")
            controllability = "not_controlled_in_current_processed_source"
            strat = "limited_by_protocol_metadata"
            risk = "high"
        elif candidate.mechanism_id == "diffusion_transport":
            likely = ("geometry", "boundary_conditions", "SOC", "current_profile", "temperature", "chemistry")
            observed = ("cycle_age", "ambient_temperature", "current_summary", "voltage_summary")
            unobserved = ("internal_concentration", "particle_radius", "electrode_thickness", "boundary_conditions", "SOC")
            controllability = "not_controllable_from_current_summary"
            strat = "not_ready"
            risk = "high"
        elif candidate.mechanism_id in {"capacity_fade_trajectory", "empirical_monotonic_degradation"}:
            likely = ("cell_identity", "cycle_age", "temperature", "protocol", "initial_capacity")
            observed = ("cell_identity", "cycle_age", "ambient_temperature", "initial_reference_capacity")
            unobserved = ("exact_protocol", "calendar_time", "manufacturing_batch")
            controllability = "descriptive_stratification_only"
            strat = "partially_feasible"
            risk = "medium"
        else:
            likely = ("cell_identity", "cycle_age", "temperature", "protocol", "missingness_pattern")
            observed = ("cell_identity", "cycle_age", "ambient_temperature")
            unobserved = ("full_protocol", "calendar_time", "batch")
            controllability = "not_controlled"
            strat = "limited"
            risk = "medium"
        rows.append(
            ConfoundingAssessment(
                mechanism_id=candidate.mechanism_id,
                likely_confounders=likely,
                observed_confounders=observed,
                unobserved_confounders=unobserved,
                controllability=controllability,
                stratification_feasibility=strat,
                residual_confounding_risk=risk,
            )
        )
    return sorted(rows, key=lambda item: item.mechanism_id)


def select_bounded_evaluator(
    assessments: Iterable[IdentifiabilityAssessment] | None = None,
) -> MechanismSelectionDecision:
    assessments = tuple(assessments or assess_identifiability())
    by_id = {item.mechanism_id: item for item in assessments}
    rejected = []
    for mechanism_id, reason in (
        ("arrhenius_temperature_dependence", "missing rate-like response, comparable protocol, and controlled-temperature semantics"),
        ("diffusion_transport", "missing internal state, geometry, boundary conditions, and transport-identifying protocol"),
        ("resistance_growth_trajectory", "internal resistance/EIS measurement definition unavailable"),
        ("temperature_capacity_coupling", "observational coupling only with uncontrolled confounding"),
    ):
        rejected.append({"mechanism_id": mechanism_id, "reason": reason})

    capacity_ready = by_id.get("capacity_fade_trajectory")
    if capacity_ready and capacity_ready.overall_status == "bounded_empirical_evaluator_candidate":
        return MechanismSelectionDecision(
            status="descriptive_evaluator_only",
            selected_evaluator_id="battery_capacity_trajectory_consistency_evaluator_v1",
            selected_mechanism_id="capacity_fade_trajectory",
            selected_operator_role="Evaluator",
            rationale=(
                "capacity trajectories have explicit observed capacity values and cycle ordering",
                "selection is descriptive and does not identify a degradation mechanism",
                "no Arrhenius, diffusion, resistance, SOH, RUL, or production prediction claim is supported",
            ),
            rejected_mechanisms=tuple(rejected),
            allowed_claims=(
                "capacity trajectory consistency can be audited descriptively",
                "mechanism requirements and evidence gaps were recorded",
                "protocol and condition comparability limitations were identified",
            ),
            prohibited_claims=(
                "degradation mechanism identified",
                "Arrhenius behavior proven",
                "activation energy estimated",
                "diffusion coefficient inferred",
                "SOH or RUL model validated",
                "causal temperature effect established",
            ),
        )
    return MechanismSelectionDecision(
        status="no_mechanism_ready_from_current_data",
        selected_evaluator_id=None,
        selected_mechanism_id=None,
        selected_operator_role="none",
        rationale=("all mechanism candidates require missing state, condition, protocol, or response evidence",),
        rejected_mechanisms=tuple(rejected),
        allowed_claims=("no mechanism-ready result is a scientifically valid outcome",),
        prohibited_claims=("mechanism confirmed", "parameter estimated", "predictive model evidence"),
    )


def mechanism_candidate_summary_rows(
    candidates: Iterable[MechanismCandidate],
    assessments: Iterable[IdentifiabilityAssessment],
) -> list[dict[str, Any]]:
    by_id = {item.mechanism_id: item for item in assessments}
    rows = []
    for candidate in candidates:
        assessment = by_id[candidate.mechanism_id]
        rows.append(
            {
                "mechanism_id": candidate.mechanism_id,
                "mechanism_family": candidate.mechanism_family,
                "possible_operator_role": candidate.possible_operator_role,
                "current_implementation_status": candidate.current_implementation_status,
                "requirement_count": len(candidate.requirements),
                "overall_identifiability_status": assessment.overall_status,
                "supported_role": assessment.supported_role,
                "model_or_solver_executed": "false",
                "parameter_fitting_performed": "false",
                "claim_boundary": "; ".join(candidate.prohibited_interpretations),
            }
        )
    return rows


def identifiability_summary_rows(assessments: Iterable[IdentifiabilityAssessment]) -> list[dict[str, Any]]:
    return [
        {
            "mechanism_id": item.mechanism_id,
            "structural_status": item.structural_status,
            "practical_status": item.practical_status,
            "contextual_status": item.contextual_status,
            "overall_status": item.overall_status,
            "blocking_reasons": "; ".join(item.blocking_reasons),
            "supported_role": item.supported_role,
            "prohibited_promotions": "; ".join(item.prohibited_promotions),
        }
        for item in sorted(assessments, key=lambda row: row.mechanism_id)
    ]


def evidence_gap_summary_rows(gaps: Iterable[EvidenceGapRecommendation] | None = None) -> list[dict[str, Any]]:
    return [gap.to_dict() for gap in sorted(gaps or build_evidence_gap_registry(), key=lambda item: item.gap_id)]


def _report_markdown(summary: Mapping[str, Any], decision: MechanismSelectionDecision) -> str:
    lines = [
        "# Battery Mechanism Data Sufficiency Audit",
        "",
        f"- schema_version: `{BATTERY_MECHANISM_AUDIT_VERSION}`",
        f"- source_status: `{summary['status']}`",
        f"- cells: `{summary['cell_count']}`",
        f"- cycles: `{summary['cycle_count']}`",
        f"- ambient_temperature_groups: `{summary['ambient_temperature_unique_count']}`",
        f"- selected_evaluator_status: `{decision.status}`",
        f"- selected_evaluator: `{decision.selected_evaluator_id or 'none'}`",
        "",
        "This audit records mechanism requirements, evidence gaps, and identifiability limits only.",
        "It does not estimate activation energy, diffusion coefficients, SOH, RUL, or causal effects.",
    ]
    return "\n".join(lines) + "\n"


def export_battery_mechanism_audit_summary(repo_root: str | Path = ".", *, write_local: bool = True) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    df = load_battery_evidence_frame(root)
    inventory = audit_battery_evidence_inventory(root)
    candidates = build_default_mechanism_candidates()
    bindings = bind_mechanism_requirements(candidates, inventory, root)
    assessments = assess_identifiability(candidates, bindings, root)
    confounding = assess_confounding(candidates)
    decision = select_bounded_evaluator(assessments)
    condition_rows = condition_coverage_rows(df)
    protocol_rows = protocol_comparability_summary(root)
    gaps = build_evidence_gap_registry()

    _atomic_write_csv(
        root / TRACKED_OUTPUTS["condition_coverage"],
        condition_rows,
        [
            "condition_field",
            "condition_value",
            "cell_count",
            "cycle_count",
            "capacity_rows",
            "duration_rows",
            "measured_temperature_rows",
            "status",
            "condition_semantics",
        ],
    )
    _atomic_write_csv(
        root / TRACKED_OUTPUTS["protocol_comparability"],
        protocol_rows,
        ["protocol_field", "available", "coverage_rows", "status", "comparability_impact"],
    )
    _atomic_write_csv(
        root / TRACKED_OUTPUTS["mechanism_candidate"],
        mechanism_candidate_summary_rows(candidates, assessments),
        [
            "mechanism_id",
            "mechanism_family",
            "possible_operator_role",
            "current_implementation_status",
            "requirement_count",
            "overall_identifiability_status",
            "supported_role",
            "model_or_solver_executed",
            "parameter_fitting_performed",
            "claim_boundary",
        ],
    )
    _atomic_write_csv(
        root / TRACKED_OUTPUTS["identifiability"],
        identifiability_summary_rows(assessments),
        [
            "mechanism_id",
            "structural_status",
            "practical_status",
            "contextual_status",
            "overall_status",
            "blocking_reasons",
            "supported_role",
            "prohibited_promotions",
        ],
    )
    _atomic_write_csv(
        root / TRACKED_OUTPUTS["evidence_gap"],
        evidence_gap_summary_rows(gaps),
        [
            "gap_id",
            "mechanism_id",
            "missing_concept",
            "missing_variable",
            "required_unit",
            "required_context",
            "acquisition_method_candidate",
            "external_data_required",
            "current_source_can_be_enriched",
            "scientific_impact",
            "priority",
            "prohibited_workaround",
        ],
    )
    decision_payload = {
        **decision.to_dict(),
        "source_inventory": {
            "cell_count": inventory["cell_count"],
            "cycle_count": inventory["cycle_count"],
            "ambient_temperature_unique_count": inventory["ambient_temperature_unique_count"],
            "internal_resistance_available_rows": inventory["internal_resistance_available_rows"],
            "physical_elapsed_time_available": inventory["physical_elapsed_time_available"],
        },
        "actual_data_status": inventory["status"],
        "tracked_outputs": dict(TRACKED_OUTPUTS),
        "source_checksum": inventory["source_checksum"],
        "result_checksum": _checksum_mapping(decision.to_dict()),
    }
    _atomic_write_text(root / TRACKED_OUTPUTS["operator_selection"], canonical_json(decision_payload))
    _atomic_write_text(root / TRACKED_OUTPUTS["report_summary"], _report_markdown(inventory, decision))

    local_outputs: dict[str, str] = {}
    if write_local:
        local_specs = [
            ("inventory/cell_condition_inventory.csv", condition_rows, list(condition_rows[0].keys()) if condition_rows else ["status"]),
            ("inventory/protocol_inventory.csv", protocol_rows, list(protocol_rows[0].keys()) if protocol_rows else ["status"]),
            ("inventory/variable_coverage.csv", _variable_coverage_rows(df), ["variable", "available", "coverage_rows", "coverage_ratio", "role", "mechanism_relevance"]),
            ("inventory/time_axis_inventory.csv", time_axis_inventory(root), ["time_axis_id", "source_field", "status", "coverage_rows", "semantics", "prohibited_interpretation"]),
            ("candidates/mechanism_requirements.csv", [req.to_dict() for candidate in candidates for req in candidate.requirements], ["requirement_id", "mechanism_id", "requirement_type", "required_concept", "required_evidence", "minimum_status", "required_for_execution", "prohibited_substitute"]),
            ("candidates/evidence_bindings.csv", [binding.to_dict() for binding in bindings], ["mechanism_id", "requirement_id", "evidence_status", "evidence_ref", "maturity_level", "context", "completeness", "uncertainty", "limitation"]),
            ("candidates/identifiability_assessments.csv", identifiability_summary_rows(assessments), ["mechanism_id", "structural_status", "practical_status", "contextual_status", "overall_status", "blocking_reasons", "supported_role", "prohibited_promotions"]),
            ("candidates/confounding_assessments.csv", [item.to_dict() for item in confounding], ["mechanism_id", "likely_confounders", "observed_confounders", "unobserved_confounders", "controllability", "stratification_feasibility", "residual_confounding_risk"]),
            ("decisions/evidence_gaps.csv", evidence_gap_summary_rows(gaps), ["gap_id", "mechanism_id", "missing_concept", "missing_variable", "required_unit", "required_context", "acquisition_method_candidate", "external_data_required", "current_source_can_be_enriched", "scientific_impact", "priority", "prohibited_workaround"]),
        ]
        for relative, rows, fields in local_specs:
            target = _safe_local_output(root, f"{LOCAL_OUTPUT_ROOT}/{relative}")
            _atomic_write_csv(target, rows, fields)
            local_outputs[relative] = f"{LOCAL_OUTPUT_ROOT}/{relative}"
        _atomic_write_text(_safe_local_output(root, f"{LOCAL_OUTPUT_ROOT}/decisions/candidate_decisions.json"), canonical_json({"decisions": [item.to_dict() for item in assessments]}))
        _atomic_write_text(_safe_local_output(root, f"{LOCAL_OUTPUT_ROOT}/decisions/operator_selection.json"), canonical_json(decision_payload))
        _atomic_write_text(_safe_local_output(root, f"{LOCAL_OUTPUT_ROOT}/reports/battery_mechanism_audit.md"), _report_markdown(inventory, decision))
        local_outputs["decisions/candidate_decisions.json"] = f"{LOCAL_OUTPUT_ROOT}/decisions/candidate_decisions.json"
        local_outputs["decisions/operator_selection.json"] = f"{LOCAL_OUTPUT_ROOT}/decisions/operator_selection.json"
        local_outputs["reports/battery_mechanism_audit.md"] = f"{LOCAL_OUTPUT_ROOT}/reports/battery_mechanism_audit.md"

    return {
        "schema_version": BATTERY_MECHANISM_AUDIT_VERSION,
        "status": "exported",
        "decision_status": decision.status,
        "selected_evaluator_id": decision.selected_evaluator_id,
        "candidate_count": len(candidates),
        "evidence_binding_count": len(bindings),
        "evidence_gap_count": len(gaps),
        "tracked_outputs": dict(TRACKED_OUTPUTS),
        "local_outputs": local_outputs,
        "network_called": False,
        "model_or_solver_executed": False,
        "parameter_fitting_performed": False,
    }


def _variable_coverage_rows(df: pd.DataFrame) -> list[dict[str, Any]]:
    variables = {
        "battery_id": ("identity", "cell identity for grouping, not feature identity claim"),
        "cycle_index": ("time_axis", "ordered cycle progression, not physical time"),
        "ambient_temperature_c": ("condition", "temperature metadata with controlled-condition warning"),
        "discharge_capacity_ah": ("observable", "capacity trajectory descriptor"),
        "capacity_retention_percent": ("derived_observable", "normalized retention descriptor"),
        "internal_resistance_ohm": ("observable", "resistance relation if defined and non-null"),
        "discharge_duration_s": ("time_axis", "per-cycle discharge duration"),
        "voltage_mean_v": ("observable_summary", "terminal voltage summary, not concentration field"),
        "current_mean_a": ("observable_summary", "current summary, not full protocol"),
        "temperature_mean_c": ("response_summary", "operating temperature response, not controlled ambient condition"),
        "failed": ("label", "end-of-life indicator, not a mechanism parameter"),
    }
    rows = []
    total = max(len(df), 1)
    for variable, (role, relevance) in variables.items():
        available = variable in df
        coverage = int(df[variable].notna().sum()) if available else 0
        rows.append(
            {
                "variable": variable,
                "available": _bool_text(available),
                "coverage_rows": coverage,
                "coverage_ratio": round(coverage / total, 6),
                "role": role,
                "mechanism_relevance": relevance,
            }
        )
    return rows


def load_battery_mechanism_summary(repo_root: str | Path = ".") -> dict[str, Any]:
    root = Path(repo_root).resolve()
    decision_path = root / TRACKED_OUTPUTS["operator_selection"]
    if not decision_path.exists():
        return {"status": "not_available", "schema_version": BATTERY_MECHANISM_AUDIT_VERSION}
    with decision_path.open("r", encoding="utf-8") as handle:
        decision = json.load(handle)
    for key, relative in TRACKED_OUTPUTS.items():
        if not (root / relative).exists():
            return {"status": "not_available", "missing_output": relative, "schema_version": BATTERY_MECHANISM_AUDIT_VERSION}
    return {
        "schema_version": BATTERY_MECHANISM_AUDIT_VERSION,
        "status": "available",
        "decision": decision,
        "tracked_outputs": dict(TRACKED_OUTPUTS),
        "model_or_solver_executed": False,
        "network_called": False,
        "parameter_fitting_performed": False,
    }


def validate_battery_mechanism_audit_path(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    if not target.exists():
        return {"schema_version": BATTERY_MECHANISM_AUDIT_VERSION, "status": "invalid", "valid": False, "error": "path does not exist"}
    if target.suffix.lower() == ".json":
        payload = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("JSON audit artifact must contain an object")
        if "schema_version" in payload and payload["schema_version"] != BATTERY_MECHANISM_AUDIT_VERSION:
            raise ValueError("unsupported audit schema_version")
        return {"schema_version": BATTERY_MECHANISM_AUDIT_VERSION, "status": "valid", "valid": True, "artifact_type": "json"}
    if target.suffix.lower() == ".csv":
        with target.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        return {"schema_version": BATTERY_MECHANISM_AUDIT_VERSION, "status": "valid", "valid": True, "artifact_type": "csv", "row_count": len(rows)}
    raise ValueError("battery mechanism audit artifact must be JSON or CSV")
