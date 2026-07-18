"""Deterministic Battery capacity-trajectory consistency evaluation.

This module evaluates observed cycle-index capacity trajectories. It does not
fit physical parameters, identify degradation mechanisms, predict lifetime,
train a model, or treat cycle index as physical elapsed time.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import statistics
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import pandas as pd


BATTERY_TRAJECTORY_EVALUATOR_VERSION = "2.3.4"
EVALUATOR_ID = "battery_capacity_trajectory_consistency_evaluator_v1"
DEFAULT_SOURCE_PATH = "data/processed/kaggle_nasa_battery_cycle_summary_analysis_ready.csv"
DEFAULT_TRAJECTORY_PATH = "outputs/battery_pgir_v2_3/trajectories/battery_trajectories.jsonl"
DEFAULT_STATE_PATH = "outputs/battery_pgir_v2_3/states/operational_states.jsonl"
DEFAULT_OUTPUT_ROOT = "outputs/battery_trajectory_evaluator_v2_3"

TRACKED_OUTPUTS = {
    "execution_summary": "data/processed/battery_v2_3_4_evaluator_execution_summary.json",
    "eligibility_summary": "data/processed/battery_v2_3_4_eligibility_summary.csv",
    "finding_summary": "data/processed/battery_v2_3_4_finding_summary.csv",
    "trust_summary": "data/processed/battery_v2_3_4_trust_summary.csv",
    "decision": "data/processed/battery_v2_3_4_evaluator_decision.json",
    "claim_evidence": "data/processed/battery_v2_3_4_claim_evidence.json",
    "report_summary": "data/processed/battery_v2_3_4_report_summary.md",
}

LOCAL_OUTPUTS = {
    "input_manifest": f"{DEFAULT_OUTPUT_ROOT}/inputs/trajectory_evaluation_manifest.json",
    "trajectory_results": f"{DEFAULT_OUTPUT_ROOT}/results/trajectory_results.jsonl",
    "trajectory_findings": f"{DEFAULT_OUTPUT_ROOT}/results/trajectory_findings.jsonl",
    "trajectory_summary": f"{DEFAULT_OUTPUT_ROOT}/results/trajectory_summary.csv",
    "trust_assessments": f"{DEFAULT_OUTPUT_ROOT}/trust/trajectory_trust_assessments.csv",
    "execution_summary": f"{DEFAULT_OUTPUT_ROOT}/trust/evaluator_execution_summary.json",
    "report": f"{DEFAULT_OUTPUT_ROOT}/reports/battery_trajectory_evaluator_report.md",
}

FINDING_CATEGORIES = (
    "trajectory_validity",
    "missing_cycle_gap",
    "duplicate_cycle_candidate",
    "non_monotonic_increase_candidate",
    "abrupt_capacity_drop_candidate",
    "abrupt_capacity_rise_candidate",
    "plateau_candidate",
    "accelerated_fade_candidate",
    "decelerated_fade_candidate",
    "high_variability_candidate",
    "terminal_low_retention_observation",
    "protocol_context_change_candidate",
)

PROHIBITED_INTERPRETATIONS = (
    "degradation mechanism identified",
    "knee point physically confirmed",
    "lithium plating detected",
    "SEI growth detected",
    "internal short detected",
    "activation energy estimated",
    "diffusion coefficient estimated",
    "RUL predicted",
    "SOH model validated",
    "lifetime predicted",
    "causal temperature effect",
    "production battery decision",
)

ALLOWED_CLAIMS = (
    "battery capacity trajectory evaluator registered",
    "battery capacity trajectory evaluator executed",
    "battery trajectory consistency findings generated",
    "deterministic threshold policy recorded",
    "PGIR conformance checked before execution",
    "evaluator trust assessed",
    "descriptive trajectory patterns summarized",
)


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _json_safe(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_json_safe(payload), indent=2, sort_keys=True) + "\n"


def canonical_checksum(payload: Any) -> str:
    text = json.dumps(_json_safe(payload), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _file_checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _resolve_repo_path(repo_root: str | Path, relative_path: str | Path) -> Path:
    root = Path(repo_root).resolve()
    candidate = Path(str(relative_path).replace("\\", "/"))
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError("paths must be repository-relative and non-traversing")
    target = (root / candidate).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        raise ValueError("path escapes repository root") from None
    return target


def _safe_local_path(repo_root: str | Path, relative_path: str | Path) -> Path:
    normalized = Path(str(relative_path).replace("\\", "/")).as_posix()
    if not normalized.startswith(DEFAULT_OUTPUT_ROOT + "/"):
        raise ValueError(f"local evaluator outputs must stay under {DEFAULT_OUTPUT_ROOT}/")
    return _resolve_repo_path(repo_root, normalized)


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        newline="",
        delete=False,
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    ) as handle:
        temp_path = Path(handle.name)
        handle.write(content)
    try:
        temp_path.replace(path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def _atomic_write_csv(
    path: Path,
    rows: Iterable[Mapping[str, Any]],
    fieldnames: Sequence[str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        newline="",
        delete=False,
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    ) as handle:
        temp_path = Path(handle.name)
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames))
        writer.writeheader()
        for row in rows:
            writer.writerow({name: _json_safe(row.get(name)) for name in fieldnames})
    try:
        temp_path.replace(path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    content = "".join(
        json.dumps(_json_safe(row), sort_keys=True, separators=(",", ":")) + "\n"
        for row in rows
    )
    _atomic_write_text(path, content)


def _safe_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _safe_int(value: Any) -> int | None:
    numeric = _safe_float(value)
    if numeric is None or not numeric.is_integer():
        return None
    return int(numeric)


def _median(values: Sequence[float]) -> float:
    return float(statistics.median(values))


def _robust_scale(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    center = _median(values)
    mad = _median([abs(value - center) for value in values])
    return 1.4826 * mad


@dataclass(frozen=True)
class CapacityTrajectoryEvaluatorConfig:
    evaluator_id: str = EVALUATOR_ID
    evaluator_version: str = "1"
    minimum_valid_observations: int = 5
    reference_capacity_policy: str = "source_recorded_first_n_median_window_5"
    reference_window: int = 5
    absolute_detection_floor: float = 0.005
    robust_scale_multiplier: float = 6.0
    window_size: int = 5
    minimum_window_support: int = 5
    gap_exclusion_threshold: int = 1
    plateau_threshold: float = 0.01
    accelerated_fade_threshold: float = 0.0025
    high_variability_scale_threshold: float = 0.01
    terminal_retention_boundary: float = 0.8
    numerical_tolerance: float = 1e-12
    maximum_states_per_trajectory: int = 10000

    def __post_init__(self) -> None:
        if self.evaluator_id != EVALUATOR_ID:
            raise ValueError(f"only {EVALUATOR_ID} may be executed in v2.3.4")
        if self.minimum_valid_observations < 2:
            raise ValueError("minimum_valid_observations must be at least 2")
        if self.reference_capacity_policy not in {
            "source_recorded_first_n_median_window_5",
            "first_n_median_first_5",
            "first_valid_discharge_capacity",
            "first_valid_capacity_after_formation",
            "source_nominal_capacity",
        }:
            raise ValueError("unsupported reference_capacity_policy")
        if self.reference_window < 1:
            raise ValueError("reference_window must be positive")
        if self.reference_capacity_policy == "first_n_median_first_5" and self.reference_window != 5:
            raise ValueError("first_n_median_first_5 requires reference_window=5")
        if self.absolute_detection_floor <= 0 or self.robust_scale_multiplier <= 0:
            raise ValueError("detection thresholds must be positive")
        if self.window_size < 2 or self.minimum_window_support < 2:
            raise ValueError("window sizes must be at least 2")
        if self.gap_exclusion_threshold < 1:
            raise ValueError("gap_exclusion_threshold must be at least 1")
        if not 0 < self.terminal_retention_boundary < 2:
            raise ValueError("terminal_retention_boundary must be a dimensionless ratio")
        if self.maximum_states_per_trajectory < self.minimum_valid_observations:
            raise ValueError("maximum_states_per_trajectory is too small")

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "CapacityTrajectoryEvaluatorConfig":
        threshold = dict(payload.get("threshold_policy", {}))
        window = dict(payload.get("window_policy", {}))
        reference = dict(payload.get("reference_capacity", {}))
        resource = dict(payload.get("resource_policy", {}))
        return cls(
            evaluator_id=str(payload.get("evaluator_id", EVALUATOR_ID)),
            evaluator_version=str(payload.get("evaluator_version", "1")),
            minimum_valid_observations=int(payload.get("minimum_valid_observations", 5)),
            reference_capacity_policy=str(reference.get("policy_id", payload.get("reference_capacity_policy", "source_recorded_first_n_median_window_5"))),
            reference_window=int(reference.get("window", payload.get("reference_window", 5))),
            absolute_detection_floor=float(threshold.get("absolute_detection_floor", 0.005)),
            robust_scale_multiplier=float(threshold.get("robust_scale_multiplier", 6.0)),
            window_size=int(window.get("window_size", 5)),
            minimum_window_support=int(window.get("minimum_window_support", 5)),
            gap_exclusion_threshold=int(threshold.get("gap_exclusion_threshold", 1)),
            plateau_threshold=float(threshold.get("plateau_threshold", 0.01)),
            accelerated_fade_threshold=float(threshold.get("accelerated_fade_threshold", 0.0025)),
            high_variability_scale_threshold=float(threshold.get("high_variability_scale_threshold", 0.01)),
            terminal_retention_boundary=float(threshold.get("terminal_retention_boundary", 0.8)),
            numerical_tolerance=float(threshold.get("numerical_tolerance", 1e-12)),
            maximum_states_per_trajectory=int(resource.get("maximum_states_per_trajectory", 10000)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": BATTERY_TRAJECTORY_EVALUATOR_VERSION,
            "evaluator_id": self.evaluator_id,
            "evaluator_version": self.evaluator_version,
            "minimum_valid_observations": self.minimum_valid_observations,
            "reference_capacity": {
                "policy_id": self.reference_capacity_policy,
                "window": self.reference_window,
                "selection_scope": "earliest_valid_discharge_capacity_observations_only",
                "post_hoc_maximum_prohibited": True,
            },
            "threshold_policy": {
                "absolute_detection_floor": self.absolute_detection_floor,
                "robust_scale_multiplier": self.robust_scale_multiplier,
                "gap_exclusion_threshold": self.gap_exclusion_threshold,
                "plateau_threshold": self.plateau_threshold,
                "accelerated_fade_threshold": self.accelerated_fade_threshold,
                "high_variability_scale_threshold": self.high_variability_scale_threshold,
                "terminal_retention_boundary": self.terminal_retention_boundary,
                "numerical_tolerance": self.numerical_tolerance,
                "semantics": "algorithmic_detection_policy_not_measurement_uncertainty",
                "post_hoc_optimization_prohibited": True,
            },
            "window_policy": {
                "window_size": self.window_size,
                "minimum_window_support": self.minimum_window_support,
                "overlap_policy": "merge_adjacent_candidate_windows",
            },
            "resource_policy": {
                "maximum_states_per_trajectory": self.maximum_states_per_trajectory,
                "bounded_computation": True,
            },
        }


@dataclass(frozen=True)
class CapacityTrajectoryInput:
    trajectory_id: str
    cell_id: str
    cycle_indices: tuple[int, ...]
    capacities: tuple[float | None, ...]
    capacity_units: tuple[str, ...]
    ordered_state_refs: tuple[str, ...]
    reference_capacity_method: str
    recorded_reference_capacity: float | None
    representation_maturity: str = "dimensionally_valid"
    lineage_valid: bool = True
    trajectory_schema_id: str = "battery_trajectory_summary_schema_v1"
    protocol_signatures: tuple[str | None, ...] = ()
    temperature_context_available: bool = True
    timestamp_available: bool = False
    physical_elapsed_time_available: bool = False
    source_uncertainty_status: str = "unavailable"

    def __post_init__(self) -> None:
        lengths = {
            len(self.cycle_indices),
            len(self.capacities),
            len(self.capacity_units),
            len(self.ordered_state_refs),
        }
        if len(lengths) != 1:
            raise ValueError("trajectory input arrays must have equal length")
        if self.protocol_signatures and len(self.protocol_signatures) != len(self.cycle_indices):
            raise ValueError("protocol_signatures must align with trajectory observations")


@dataclass(frozen=True)
class CapacityTrajectoryFinding:
    finding_id: str
    trajectory_id: str
    finding_category: str
    finding_status: str
    start_cycle_index: int | None
    end_cycle_index: int | None
    cycle_gap: int | None
    normalized_magnitude: float | None
    absolute_capacity_magnitude: float | None
    threshold_used: float | None
    threshold_id: str
    threshold_semantics: str
    protocol_context_available: bool
    temperature_context_available: bool
    interpretation: str
    prohibited_interpretations: tuple[str, ...] = PROHIBITED_INTERPRETATIONS

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": BATTERY_TRAJECTORY_EVALUATOR_VERSION,
            "finding_id": self.finding_id,
            "trajectory_id": self.trajectory_id,
            "finding_category": self.finding_category,
            "finding_status": self.finding_status,
            "start_cycle_index": self.start_cycle_index,
            "end_cycle_index": self.end_cycle_index,
            "cycle_gap": self.cycle_gap,
            "normalized_magnitude": self.normalized_magnitude,
            "absolute_capacity_magnitude": self.absolute_capacity_magnitude,
            "threshold_used": self.threshold_used,
            "threshold_id": self.threshold_id,
            "threshold_semantics": self.threshold_semantics,
            "protocol_context_available": self.protocol_context_available,
            "temperature_context_available": self.temperature_context_available,
            "interpretation": self.interpretation,
            "prohibited_interpretations": list(self.prohibited_interpretations),
        }


@dataclass(frozen=True)
class CapacityTrajectoryResult:
    trajectory_id: str
    cell_id: str
    eligibility_status: str
    trust_status: str
    total_state_count: int
    valid_capacity_count: int
    evaluable_transition_count: int
    first_capacity: float | None
    last_capacity: float | None
    reference_capacity: float | None
    reference_cycle_index: int | None
    reference_policy_id: str
    reference_selection_evidence: str
    excluded_early_cycle_policy: str
    reference_unit: str
    first_retention: float | None
    last_retention: float | None
    observed_retention_range: float | None
    robust_difference_scale: float | None
    event_threshold: float | None
    finding_counts: Mapping[str, int]
    gap_aware_exclusion_count: int
    uncertainty_status: str
    physical_elapsed_time_available: bool
    limitations: tuple[str, ...]
    findings: tuple[CapacityTrajectoryFinding, ...] = field(repr=False)

    def to_dict(self, *, include_identity: bool = True, include_findings: bool = False) -> dict[str, Any]:
        payload = {
            "schema_version": BATTERY_TRAJECTORY_EVALUATOR_VERSION,
            "evaluator_id": EVALUATOR_ID,
            "eligibility_status": self.eligibility_status,
            "trust_status": self.trust_status,
            "total_state_count": self.total_state_count,
            "valid_capacity_count": self.valid_capacity_count,
            "evaluable_transition_count": self.evaluable_transition_count,
            "first_capacity": self.first_capacity,
            "last_capacity": self.last_capacity,
            "reference_capacity": self.reference_capacity,
            "reference_cycle_index": self.reference_cycle_index,
            "reference_policy_id": self.reference_policy_id,
            "reference_selection_evidence": self.reference_selection_evidence,
            "excluded_early_cycle_policy": self.excluded_early_cycle_policy,
            "reference_unit": self.reference_unit,
            "first_retention": self.first_retention,
            "last_retention": self.last_retention,
            "observed_retention_range": self.observed_retention_range,
            "robust_difference_scale": self.robust_difference_scale,
            "event_threshold": self.event_threshold,
            "finding_counts": dict(sorted(self.finding_counts.items())),
            "gap_aware_exclusion_count": self.gap_aware_exclusion_count,
            "uncertainty_status": self.uncertainty_status,
            "physical_elapsed_time_available": self.physical_elapsed_time_available,
            "limitations": list(self.limitations),
            "model_or_solver_executed": False,
            "parameter_fitting_performed": False,
        }
        if include_identity:
            payload["trajectory_id"] = self.trajectory_id
            payload["cell_id"] = self.cell_id
        if include_findings:
            payload["findings"] = [finding.to_dict() for finding in self.findings]
        payload["result_checksum"] = canonical_checksum(payload)
        return payload


@dataclass(frozen=True)
class CapacityTrajectoryAggregate:
    requested_trajectories: int
    eligible_trajectories: int
    eligible_with_warnings: int
    blocked_trajectories: int
    evaluated_trajectories: int
    total_states: int
    valid_capacity_observations: int
    finding_counts: Mapping[str, int]
    trajectories_with_findings: Mapping[str, int]
    valid_cycle_count_min: int | None
    valid_cycle_count_median: float | None
    valid_cycle_count_max: int | None
    final_retention_min: float | None
    final_retention_median: float | None
    final_retention_max: float | None
    protocol_context_available_trajectories: int
    timestamp_available_trajectories: int
    physical_time_available_trajectories: int
    source_uncertainty_available_trajectories: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "requested_trajectories": self.requested_trajectories,
            "eligible_trajectories": self.eligible_trajectories,
            "eligible_with_warnings": self.eligible_with_warnings,
            "blocked_trajectories": self.blocked_trajectories,
            "evaluated_trajectories": self.evaluated_trajectories,
            "total_states": self.total_states,
            "valid_capacity_observations": self.valid_capacity_observations,
            "finding_counts": dict(sorted(self.finding_counts.items())),
            "trajectories_with_findings": dict(sorted(self.trajectories_with_findings.items())),
            "valid_cycle_count_min": self.valid_cycle_count_min,
            "valid_cycle_count_median": self.valid_cycle_count_median,
            "valid_cycle_count_max": self.valid_cycle_count_max,
            "final_retention_min": self.final_retention_min,
            "final_retention_median": self.final_retention_median,
            "final_retention_max": self.final_retention_max,
            "protocol_context_available_trajectories": self.protocol_context_available_trajectories,
            "timestamp_available_trajectories": self.timestamp_available_trajectories,
            "physical_time_available_trajectories": self.physical_time_available_trajectories,
            "source_uncertainty_available_trajectories": self.source_uncertainty_available_trajectories,
        }


@dataclass(frozen=True)
class CapacityTrajectoryTrustAssessment:
    trust_dimension: str
    status: str
    evidence: tuple[str, ...]
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "trust_dimension": self.trust_dimension,
            "status": self.status,
            "evidence": ";".join(self.evidence),
            "limitations": ";".join(self.limitations),
        }


@dataclass(frozen=True)
class CapacityTrajectoryEvaluationDecision:
    status: str
    evaluator_id: str
    evaluator_executed: bool
    deterministic_rerun_match: bool
    representative_mechanism: str
    allowed_claims: tuple[str, ...]
    prohibited_claims: tuple[str, ...]
    restrictions: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "schema_version": BATTERY_TRAJECTORY_EVALUATOR_VERSION,
            "status": self.status,
            "evaluator_id": self.evaluator_id,
            "evaluator_role": "Evaluator",
            "evaluator_executed": self.evaluator_executed,
            "deterministic_rerun_match": self.deterministic_rerun_match,
            "representative_mechanism": self.representative_mechanism,
            "allowed_claims": list(self.allowed_claims),
            "prohibited_claims": list(self.prohibited_claims),
            "restrictions": list(self.restrictions),
            "degradation_mechanism_identified": False,
            "predictive_model_validated": False,
            "lifetime_estimation_supported": False,
            "physical_parameter_estimated": False,
            "causal_effect_identified": False,
            "production_decision_supported": False,
            "model_or_solver_executed": False,
            "parameter_fitting_performed": False,
            "network_called": False,
        }
        payload["result_checksum"] = canonical_checksum(payload)
        return payload


def load_evaluator_config(path: str | Path) -> tuple[CapacityTrajectoryEvaluatorConfig, dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != BATTERY_TRAJECTORY_EVALUATOR_VERSION:
        raise ValueError(f"config schema_version must be {BATTERY_TRAJECTORY_EVALUATOR_VERSION}")
    credential = dict(payload.get("credential_policy", {}))
    if credential.get("store_credentials") is not False or credential.get("network_access_required") is not False:
        raise ValueError("Battery trajectory evaluator requires no credentials and no network")
    execution = dict(payload.get("execution_policy", {}))
    if any(execution.get(key) is not False for key in ("model_training_enabled", "solver_enabled", "parameter_fitting_enabled")):
        raise ValueError("model training, solver execution, and parameter fitting must be disabled")
    fixed_paths = {
        "source_path": DEFAULT_SOURCE_PATH,
        "trajectory_path": DEFAULT_TRAJECTORY_PATH,
        "state_path": DEFAULT_STATE_PATH,
        "output_root": DEFAULT_OUTPUT_ROOT,
    }
    for field_name, expected in fixed_paths.items():
        value = str(payload.get(field_name, expected)).replace("\\", "/")
        candidate = Path(value)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise ValueError(f"{field_name} must be repository-relative and non-traversing")
        if value != expected:
            raise ValueError(f"v2.3.4 {field_name} must remain {expected}")
    return CapacityTrajectoryEvaluatorConfig.from_mapping(payload), payload


def evaluator_contract(config: CapacityTrajectoryEvaluatorConfig | None = None) -> dict[str, Any]:
    config = config or CapacityTrajectoryEvaluatorConfig()
    return {
        **config.to_dict(),
        "operator_role": "Evaluator",
        "mechanism_classification": "damage_and_degradation_descriptive_trajectory_evaluation",
        "input_schema": "battery_trajectory_summary_schema_v1",
        "output_schemas": [
            "battery_capacity_trajectory_finding_schema_v1",
            "battery_capacity_trajectory_result_schema_v1",
            "battery_capacity_trajectory_trust_schema_v1",
        ],
        "required_maturity": "dimensionally_valid",
        "side_effect_policy": "local_row_level_outputs_and_compact_tracked_aggregates",
        "network_policy": "no_network",
        "target_access_policy": "observed_capacity_only_no_predictive_target",
        "uncertainty_policy": "source_uncertainty_unavailable_not_zero",
        "provenance_policy": "record_source_and_input_artifact_checksums",
        "capability_stage": "operator_executed_descriptive_only",
        "prohibited_interpretations": list(PROHIBITED_INTERPRETATIONS),
    }


def _reference_capacity(
    trajectory: CapacityTrajectoryInput,
    config: CapacityTrajectoryEvaluatorConfig,
) -> tuple[float | None, int | None, str]:
    valid = [
        (cycle, float(capacity))
        for cycle, capacity in zip(trajectory.cycle_indices, trajectory.capacities)
        if capacity is not None and math.isfinite(float(capacity)) and float(capacity) > 0
    ]
    if not valid:
        return None, None, "no_positive_capacity_observation"
    policy = config.reference_capacity_policy
    if policy == "source_recorded_first_n_median_window_5":
        if trajectory.reference_capacity_method != "first_n_median":
            return None, None, "source_reference_method_is_not_first_n_median"
        if trajectory.recorded_reference_capacity is None or trajectory.recorded_reference_capacity <= 0:
            return None, None, "source_recorded_reference_capacity_unavailable"
        reference = float(trajectory.recorded_reference_capacity)
        matching = [
            cycle
            for cycle, capacity in valid
            if abs(capacity - reference) <= max(config.numerical_tolerance, abs(reference) * 1e-9)
        ]
        return (
            reference,
            matching[0] if matching else None,
            "upstream_first_five_positive_discharge_capacity_median_before_quality_filter",
        )
    if policy == "first_n_median_first_5":
        selected = valid[: config.reference_window]
        if len(selected) < config.reference_window:
            return None, None, "fewer_than_five_valid_reference_observations"
        value = _median([capacity for _, capacity in selected])
        cycle = min(selected, key=lambda item: (abs(item[1] - value), item[0]))[0]
        return value, cycle, "median_of_earliest_five_positive_discharge_capacities"
    if policy == "first_valid_discharge_capacity":
        return valid[0][1], valid[0][0], "earliest_positive_discharge_capacity"
    if policy == "first_valid_capacity_after_formation":
        return None, None, "formation_exclusion_metadata_unavailable"
    if trajectory.recorded_reference_capacity is None or trajectory.recorded_reference_capacity <= 0:
        return None, None, "source_nominal_capacity_unavailable"
    return float(trajectory.recorded_reference_capacity), None, "source_provided_nominal_capacity"


def _finding(
    trajectory: CapacityTrajectoryInput,
    category: str,
    ordinal: int,
    *,
    start_cycle: int | None,
    end_cycle: int | None,
    cycle_gap: int | None = None,
    normalized_magnitude: float | None = None,
    absolute_magnitude: float | None = None,
    threshold: float | None = None,
    interpretation: str,
) -> CapacityTrajectoryFinding:
    identity = {
        "trajectory_id": trajectory.trajectory_id,
        "category": category,
        "ordinal": ordinal,
        "start_cycle": start_cycle,
        "end_cycle": end_cycle,
    }
    return CapacityTrajectoryFinding(
        finding_id=f"battery_finding_{canonical_checksum(identity)[:16]}",
        trajectory_id=trajectory.trajectory_id,
        finding_category=category,
        finding_status="algorithmic_candidate",
        start_cycle_index=start_cycle,
        end_cycle_index=end_cycle,
        cycle_gap=cycle_gap,
        normalized_magnitude=normalized_magnitude,
        absolute_capacity_magnitude=absolute_magnitude,
        threshold_used=threshold,
        threshold_id="battery_capacity_detection_threshold_v1",
        threshold_semantics="algorithmic_detection_policy_not_measurement_uncertainty",
        protocol_context_available=bool(trajectory.protocol_signatures),
        temperature_context_available=trajectory.temperature_context_available,
        interpretation=interpretation,
    )


def _merge_window_candidates(
    trajectory: CapacityTrajectoryInput,
    category: str,
    candidates: Sequence[tuple[int, int, float]],
    threshold: float,
    interpretation: str,
) -> list[CapacityTrajectoryFinding]:
    if not candidates:
        return []
    ordered = sorted(candidates)
    groups: list[list[tuple[int, int, float]]] = [[ordered[0]]]
    for item in ordered[1:]:
        if item[0] <= groups[-1][-1][1] + 1:
            groups[-1].append(item)
        else:
            groups.append([item])
    findings = []
    for ordinal, group in enumerate(groups, start=1):
        findings.append(
            _finding(
                trajectory,
                category,
                ordinal,
                start_cycle=group[0][0],
                end_cycle=max(item[1] for item in group),
                normalized_magnitude=max(group, key=lambda item: abs(item[2]))[2],
                threshold=threshold,
                interpretation=interpretation,
            )
        )
    return findings


def _blocked_result(
    trajectory: CapacityTrajectoryInput,
    status: str,
    limitations: Sequence[str],
    findings: Sequence[CapacityTrajectoryFinding] = (),
) -> CapacityTrajectoryResult:
    counts = {category: 0 for category in FINDING_CATEGORIES}
    for finding in findings:
        counts[finding.finding_category] += 1
    return CapacityTrajectoryResult(
        trajectory_id=trajectory.trajectory_id,
        cell_id=trajectory.cell_id,
        eligibility_status=status,
        trust_status="blocked_invalid_representation",
        total_state_count=len(trajectory.cycle_indices),
        valid_capacity_count=sum(value is not None and _safe_float(value) is not None and float(value) >= 0 for value in trajectory.capacities),
        evaluable_transition_count=0,
        first_capacity=None,
        last_capacity=None,
        reference_capacity=None,
        reference_cycle_index=None,
        reference_policy_id="unresolved",
        reference_selection_evidence="unavailable",
        excluded_early_cycle_policy="none_without_explicit_formation_metadata",
        reference_unit="Ah",
        first_retention=None,
        last_retention=None,
        observed_retention_range=None,
        robust_difference_scale=None,
        event_threshold=None,
        finding_counts=counts,
        gap_aware_exclusion_count=0,
        uncertainty_status=trajectory.source_uncertainty_status,
        physical_elapsed_time_available=trajectory.physical_elapsed_time_available,
        limitations=tuple(limitations),
        findings=tuple(findings),
    )


def evaluate_capacity_trajectory(
    trajectory: CapacityTrajectoryInput,
    config: CapacityTrajectoryEvaluatorConfig | None = None,
) -> CapacityTrajectoryResult:
    config = config or CapacityTrajectoryEvaluatorConfig()
    if len(trajectory.cycle_indices) > config.maximum_states_per_trajectory:
        return _blocked_result(trajectory, "unsupported_schema", ("trajectory exceeds bounded state count",))
    if trajectory.trajectory_schema_id != "battery_trajectory_summary_schema_v1":
        return _blocked_result(trajectory, "unsupported_schema", ("unsupported trajectory schema",))
    if trajectory.representation_maturity not in {
        "dimensionally_valid",
        "physically_admissible",
        "mechanism_compatible",
        "scientifically_evaluated",
        "independently_validated",
        "production_validated",
    }:
        return _blocked_result(trajectory, "blocked_lineage", ("PGIR dimensionally_valid maturity gate not satisfied",))
    if not trajectory.lineage_valid:
        return _blocked_result(trajectory, "blocked_lineage", ("source-to-state-to-trajectory lineage validation failed",))
    if any(not ref.startswith(f"battery_state_{trajectory.cell_id}_") for ref in trajectory.ordered_state_refs):
        return _blocked_result(trajectory, "blocked_mixed_cell", ("ordered state references contain a mixed cell identity",))
    duplicate_cycles = sorted({cycle for cycle in trajectory.cycle_indices if trajectory.cycle_indices.count(cycle) > 1})
    duplicate_refs = sorted({ref for ref in trajectory.ordered_state_refs if trajectory.ordered_state_refs.count(ref) > 1})
    duplicate_findings: list[CapacityTrajectoryFinding] = []
    for ordinal, cycle in enumerate(duplicate_cycles, start=1):
        duplicate_findings.append(
            _finding(
                trajectory,
                "duplicate_cycle_candidate",
                ordinal,
                start_cycle=cycle,
                end_cycle=cycle,
                interpretation="duplicate cycle index prevents ordered trajectory evaluation",
            )
        )
    if duplicate_cycles or duplicate_refs or list(trajectory.cycle_indices) != sorted(trajectory.cycle_indices):
        return _blocked_result(
            trajectory,
            "blocked_invalid_ordering",
            ("cycle indices must be strictly increasing and state references unique",),
            duplicate_findings,
        )
    units = {unit for unit in trajectory.capacity_units if unit}
    if units != {"Ah"}:
        return _blocked_result(trajectory, "blocked_unit_inconsistency", ("all capacity observations must use Ah",))
    if any(
        capacity is not None
        and _safe_float(capacity) is not None
        and float(capacity) < 0
        for capacity in trajectory.capacities
    ):
        return _blocked_result(
            trajectory,
            "blocked_insufficient_capacity_data",
            ("negative capacity is not eligible for descriptive trajectory evaluation",),
        )
    valid_pairs = [
        (cycle, float(capacity))
        for cycle, capacity in zip(trajectory.cycle_indices, trajectory.capacities)
        if capacity is not None and _safe_float(capacity) is not None and float(capacity) >= 0
    ]
    if len(valid_pairs) < config.minimum_valid_observations:
        return _blocked_result(
            trajectory,
            "blocked_insufficient_capacity_data",
            (f"requires at least {config.minimum_valid_observations} finite nonnegative capacity observations",),
        )
    reference, reference_cycle, reference_evidence = _reference_capacity(trajectory, config)
    if reference is None or reference <= 0:
        return _blocked_result(trajectory, "blocked_reference_capacity", (reference_evidence,))
    if (
        trajectory.recorded_reference_capacity is not None
        and config.reference_capacity_policy != "source_recorded_first_n_median_window_5"
    ):
        tolerance = max(config.numerical_tolerance, abs(reference) * 1e-9)
        if abs(float(trajectory.recorded_reference_capacity) - reference) > tolerance:
            return _blocked_result(
                trajectory,
                "blocked_reference_capacity",
                ("recorded reference capacity conflicts with deterministic reference policy",),
            )

    cycles = [item[0] for item in valid_pairs]
    capacities = [item[1] for item in valid_pairs]
    retention = [capacity / reference for capacity in capacities]
    transitions = [
        {
            "start": cycles[index - 1],
            "end": cycles[index],
            "gap": cycles[index] - cycles[index - 1],
            "dq": capacities[index] - capacities[index - 1],
            "dr": retention[index] - retention[index - 1],
        }
        for index in range(1, len(cycles))
    ]
    evaluable = [item for item in transitions if item["gap"] <= config.gap_exclusion_threshold]
    robust_scale = _robust_scale([item["dr"] for item in evaluable])
    event_threshold = max(config.absolute_detection_floor, config.robust_scale_multiplier * robust_scale)
    findings: list[CapacityTrajectoryFinding] = []

    for ordinal, item in enumerate((row for row in transitions if row["gap"] > 1), start=1):
        findings.append(
            _finding(
                trajectory,
                "missing_cycle_gap",
                ordinal,
                start_cycle=item["start"],
                end_cycle=item["end"],
                cycle_gap=item["gap"],
                normalized_magnitude=item["dr"],
                absolute_magnitude=item["dq"],
                interpretation="cycle-index discontinuity; not interpreted as a physical-time gap",
            )
        )

    rises = [item for item in evaluable if item["dr"] > event_threshold]
    for ordinal, item in enumerate(rises, start=1):
        findings.append(
            _finding(
                trajectory,
                "non_monotonic_increase_candidate",
                ordinal,
                start_cycle=item["start"],
                end_cycle=item["end"],
                cycle_gap=item["gap"],
                normalized_magnitude=item["dr"],
                absolute_magnitude=item["dq"],
                threshold=event_threshold,
                interpretation="observed positive retention change above the algorithmic tolerance; cause unresolved",
            )
        )
    abrupt_drop = [item for item in evaluable if item["dr"] < -event_threshold]
    for category, rows, interpretation in (
        ("abrupt_capacity_drop_candidate", abrupt_drop, "local decline exceeds the deterministic descriptive threshold"),
        ("abrupt_capacity_rise_candidate", rises, "local rise exceeds the deterministic descriptive threshold"),
    ):
        for ordinal, item in enumerate(rows, start=1):
            findings.append(
                _finding(
                    trajectory,
                    category,
                    ordinal,
                    start_cycle=item["start"],
                    end_cycle=item["end"],
                    cycle_gap=item["gap"],
                    normalized_magnitude=item["dr"],
                    absolute_magnitude=item["dq"],
                    threshold=event_threshold,
                    interpretation=interpretation,
                )
            )

    plateau_candidates: list[tuple[int, int, float]] = []
    size = config.window_size
    for start in range(0, len(cycles) - size + 1):
        window_cycles = cycles[start : start + size]
        window_retention = retention[start : start + size]
        if len(window_cycles) < config.minimum_window_support:
            continue
        if any(window_cycles[index] - window_cycles[index - 1] > config.gap_exclusion_threshold for index in range(1, len(window_cycles))):
            continue
        observed_range = max(window_retention) - min(window_retention)
        if observed_range <= config.plateau_threshold:
            plateau_candidates.append((window_cycles[0], window_cycles[-1], observed_range))
    findings.extend(
        _merge_window_candidates(
            trajectory,
            "plateau_candidate",
            plateau_candidates,
            config.plateau_threshold,
            "bounded low-change interval candidate; not evidence that degradation stopped",
        )
    )

    acceleration: list[tuple[int, int, float]] = []
    deceleration: list[tuple[int, int, float]] = []
    dr = [item["dr"] for item in evaluable]
    transition_cycles = [(item["start"], item["end"]) for item in evaluable]
    if len(dr) >= 2 * size:
        for split in range(size, len(dr) - size + 1):
            before = dr[split - size : split]
            after = dr[split : split + size]
            if len(before) < config.minimum_window_support or len(after) < config.minimum_window_support:
                continue
            shift = _median(after) - _median(before)
            start_cycle = transition_cycles[split - size][0]
            end_cycle = transition_cycles[split + size - 1][1]
            if shift <= -config.accelerated_fade_threshold:
                acceleration.append((start_cycle, end_cycle, shift))
            elif shift >= config.accelerated_fade_threshold:
                deceleration.append((start_cycle, end_cycle, shift))
    findings.extend(
        _merge_window_candidates(
            trajectory,
            "accelerated_fade_candidate",
            acceleration,
            config.accelerated_fade_threshold,
            "later cycle-index window has a more negative robust local slope; no physical regime is assigned",
        )
    )
    findings.extend(
        _merge_window_candidates(
            trajectory,
            "decelerated_fade_candidate",
            deceleration,
            config.accelerated_fade_threshold,
            "later cycle-index window has a less negative robust local slope; no physical regime is assigned",
        )
    )
    if robust_scale >= config.high_variability_scale_threshold:
        findings.append(
            _finding(
                trajectory,
                "high_variability_candidate",
                1,
                start_cycle=cycles[0],
                end_cycle=cycles[-1],
                normalized_magnitude=robust_scale,
                threshold=config.high_variability_scale_threshold,
                interpretation="robust adjacent-difference dispersion exceeds the configured descriptive threshold",
            )
        )
    if retention[-1] < config.terminal_retention_boundary:
        findings.append(
            _finding(
                trajectory,
                "terminal_low_retention_observation",
                1,
                start_cycle=cycles[-1],
                end_cycle=cycles[-1],
                normalized_magnitude=retention[-1],
                threshold=config.terminal_retention_boundary,
                interpretation="last observed retention is below the descriptive boundary; not an end-of-life determination",
            )
        )
    signatures = [value for value in trajectory.protocol_signatures if value]
    if len(set(signatures)) > 1:
        findings.append(
            _finding(
                trajectory,
                "protocol_context_change_candidate",
                1,
                start_cycle=cycles[0],
                end_cycle=cycles[-1],
                interpretation="available protocol signature changes within the trajectory; causal interpretation prohibited",
            )
        )

    counts = {category: 0 for category in FINDING_CATEGORIES}
    for finding in findings:
        counts[finding.finding_category] += 1
    warnings = []
    if counts["missing_cycle_gap"]:
        warnings.append("cycle gaps were excluded from local abrupt-change and window-rate interpretation")
    if not trajectory.physical_elapsed_time_available:
        warnings.append("cycle index is not physical elapsed time")
    if trajectory.source_uncertainty_status == "unavailable":
        warnings.append("source measurement uncertainty unavailable; thresholds are algorithmic only")
    if not trajectory.protocol_signatures:
        warnings.append("protocol signature unavailable")
    status = "eligible_with_warnings" if warnings else "eligible"
    trust = "trusted_with_representation_warnings" if warnings else "trusted_for_bounded_descriptive_audit"
    return CapacityTrajectoryResult(
        trajectory_id=trajectory.trajectory_id,
        cell_id=trajectory.cell_id,
        eligibility_status=status,
        trust_status=trust,
        total_state_count=len(trajectory.cycle_indices),
        valid_capacity_count=len(valid_pairs),
        evaluable_transition_count=len(evaluable),
        first_capacity=capacities[0],
        last_capacity=capacities[-1],
        reference_capacity=reference,
        reference_cycle_index=reference_cycle,
        reference_policy_id=config.reference_capacity_policy,
        reference_selection_evidence=reference_evidence,
        excluded_early_cycle_policy="upstream_quality_filter_preserved_no_post_hoc_evaluator_exclusion",
        reference_unit="Ah",
        first_retention=retention[0],
        last_retention=retention[-1],
        observed_retention_range=max(retention) - min(retention),
        robust_difference_scale=robust_scale,
        event_threshold=event_threshold,
        finding_counts=counts,
        gap_aware_exclusion_count=len(transitions) - len(evaluable),
        uncertainty_status=trajectory.source_uncertainty_status,
        physical_elapsed_time_available=trajectory.physical_elapsed_time_available,
        limitations=tuple(warnings),
        findings=tuple(sorted(findings, key=lambda item: (item.finding_category, item.start_cycle_index or -1, item.finding_id))),
    )


def aggregate_results(
    results: Sequence[CapacityTrajectoryResult],
    inputs: Sequence[CapacityTrajectoryInput] | None = None,
) -> CapacityTrajectoryAggregate:
    finding_counts = {category: 0 for category in FINDING_CATEGORIES}
    trajectories_with = {category: 0 for category in FINDING_CATEGORIES}
    for result in results:
        for category in FINDING_CATEGORIES:
            count = int(result.finding_counts.get(category, 0))
            finding_counts[category] += count
            trajectories_with[category] += int(count > 0)
    evaluated = [result for result in results if result.eligibility_status in {"eligible", "eligible_with_warnings"}]
    valid_counts = [result.valid_capacity_count for result in evaluated]
    final_retention = [result.last_retention for result in evaluated if result.last_retention is not None]
    inputs = inputs or ()
    return CapacityTrajectoryAggregate(
        requested_trajectories=len(results),
        eligible_trajectories=sum(result.eligibility_status == "eligible" for result in results),
        eligible_with_warnings=sum(result.eligibility_status == "eligible_with_warnings" for result in results),
        blocked_trajectories=len(results) - len(evaluated),
        evaluated_trajectories=len(evaluated),
        total_states=sum(result.total_state_count for result in results),
        valid_capacity_observations=sum(result.valid_capacity_count for result in results),
        finding_counts=finding_counts,
        trajectories_with_findings=trajectories_with,
        valid_cycle_count_min=min(valid_counts) if valid_counts else None,
        valid_cycle_count_median=_median(valid_counts) if valid_counts else None,
        valid_cycle_count_max=max(valid_counts) if valid_counts else None,
        final_retention_min=min(final_retention) if final_retention else None,
        final_retention_median=_median(final_retention) if final_retention else None,
        final_retention_max=max(final_retention) if final_retention else None,
        protocol_context_available_trajectories=sum(bool(item.protocol_signatures) for item in inputs),
        timestamp_available_trajectories=sum(item.timestamp_available for item in inputs),
        physical_time_available_trajectories=sum(item.physical_elapsed_time_available for item in inputs),
        source_uncertainty_available_trajectories=sum(item.source_uncertainty_status != "unavailable" for item in inputs),
    )


def assess_evaluator_trust(
    aggregate: CapacityTrajectoryAggregate,
    *,
    deterministic_rerun_match: bool,
) -> tuple[CapacityTrajectoryTrustAssessment, ...]:
    representation = (
        "trusted_with_representation_warnings"
        if aggregate.blocked_trajectories or aggregate.finding_counts["missing_cycle_gap"]
        else "trusted_for_bounded_descriptive_audit"
    )
    execution = (
        "trusted_for_bounded_descriptive_audit"
        if deterministic_rerun_match
        else "blocked_nondeterministic_result"
    )
    return (
        CapacityTrajectoryTrustAssessment(
            "representation_trust",
            representation,
            ("schema, Ah unit, strict ordering, lineage, and reference policy checked",),
            ("cycle gaps and blocked short trajectories remain explicit",),
        ),
        CapacityTrajectoryTrustAssessment(
            "execution_trust",
            execution,
            ("fixed config, canonical serialization, and repeated checksum comparison",),
            ("algorithmic thresholds are not measurement uncertainty",),
        ),
        CapacityTrajectoryTrustAssessment(
            "scientific_interpretation_trust",
            "execution_valid_but_interpretation_restricted",
            ("observed capacity and cycle-index findings only",),
            ("no mechanism attribution, physical-time rate, parameter estimate, prediction, or extrapolation",),
        ),
        CapacityTrajectoryTrustAssessment(
            "external_validity",
            "not_independently_validated",
            ("current 34-cell source context only",),
            ("no external or production validation",),
        ),
        CapacityTrajectoryTrustAssessment(
            "production_validity",
            "not_production_validated",
            ("no production evidence was evaluated",),
            ("production decision support is prohibited",),
        ),
    )


def evaluation_decision(
    aggregate: CapacityTrajectoryAggregate,
    *,
    deterministic_rerun_match: bool,
) -> CapacityTrajectoryEvaluationDecision:
    if not deterministic_rerun_match:
        status = "blocked_nondeterminism"
    elif aggregate.evaluated_trajectories == 0:
        status = "blocked_trajectory_integrity"
    else:
        status = "descriptive_evaluator_executed_with_restrictions"
    return CapacityTrajectoryEvaluationDecision(
        status=status,
        evaluator_id=EVALUATOR_ID,
        evaluator_executed=aggregate.evaluated_trajectories > 0,
        deterministic_rerun_match=deterministic_rerun_match,
        representative_mechanism="none",
        allowed_claims=ALLOWED_CLAIMS,
        prohibited_claims=PROHIBITED_INTERPRETATIONS,
        restrictions=(
            "findings are deterministic descriptive candidates, not physical mechanisms",
            "evaluation uses cycle index and does not estimate physical-time degradation rates",
            "source measurement uncertainty is unavailable",
            "results apply only to the current 34-cell source context",
            "no external or production validation was performed",
        ),
    )


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise ValueError(f"JSONL row {line_number} must be an object")
            rows.append(payload)
    return rows


def load_local_battery_trajectory_inputs(
    repo_root: str | Path = ".",
    *,
    source_path: str = DEFAULT_SOURCE_PATH,
    trajectory_path: str = DEFAULT_TRAJECTORY_PATH,
    state_path: str = DEFAULT_STATE_PATH,
) -> tuple[list[CapacityTrajectoryInput], dict[str, Any]]:
    root = Path(repo_root).resolve()
    source = _resolve_repo_path(root, source_path)
    trajectory_file = _resolve_repo_path(root, trajectory_path)
    state_file = _resolve_repo_path(root, state_path)
    for path, label in ((source, "source"), (trajectory_file, "trajectory"), (state_file, "state")):
        if not path.exists():
            raise FileNotFoundError(f"{label} artifact not found: {path.relative_to(root).as_posix()}")
    selection = json.loads(
        _resolve_repo_path(root, "data/processed/battery_v2_3_3_operator_selection_decision.json").read_text(encoding="utf-8")
    )
    if selection.get("selected_evaluator_id") != EVALUATOR_ID or selection.get("status") != "descriptive_evaluator_only":
        raise ValueError("v2.3.3 did not select the bounded capacity trajectory evaluator")
    readiness = json.loads(
        _resolve_repo_path(root, "data/processed/battery_v2_3_pgir_readiness_decision.json").read_text(encoding="utf-8")
    )
    if readiness.get("status") != "battery_pgir_ready_for_mechanism_audit":
        raise ValueError("Battery PGIR readiness gate is not satisfied")

    frame = pd.read_csv(source)
    required = {
        "battery_id",
        "cycle_index",
        "discharge_capacity_ah",
        "reference_capacity_ah",
        "reference_capacity_method",
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"source summary missing columns: {missing}")
    states = {row["entity_id"]: row for row in _load_jsonl(state_file)}
    trajectories = sorted(_load_jsonl(trajectory_file), key=lambda row: row["entity_id"])
    inputs: list[CapacityTrajectoryInput] = []
    for trajectory in trajectories:
        attrs = dict(trajectory.get("attributes", {}))
        cell_id = str(attrs.get("cell_id", ""))
        refs = tuple(str(ref) for ref in attrs.get("ordered_state_refs", []))
        source_group = frame.loc[frame["battery_id"].astype(str) == cell_id].copy()
        source_group["cycle_index"] = pd.to_numeric(source_group["cycle_index"], errors="coerce")
        source_group = source_group.sort_values("cycle_index", kind="stable")
        source_by_cycle = {
            int(row["cycle_index"]): row
            for row in source_group.to_dict(orient="records")
            if _safe_int(row.get("cycle_index")) is not None
        }
        cycles: list[int] = []
        capacities: list[float | None] = []
        lineage_valid = True
        for ref in refs:
            state = states.get(ref)
            if state is None:
                lineage_valid = False
                continue
            variables = dict(state.get("attributes", {}).get("state_variables", {}))
            cycle = _safe_int(variables.get("cycle_index"))
            state_cell = str(variables.get("cell_id", ""))
            capacity = _safe_float(variables.get("measured_discharge_capacity_ah"))
            if cycle is None or state_cell != cell_id or cycle not in source_by_cycle:
                lineage_valid = False
                continue
            source_capacity = _safe_float(source_by_cycle[cycle].get("discharge_capacity_ah"))
            if source_capacity is None or capacity is None or abs(source_capacity - capacity) > 1e-12:
                lineage_valid = False
            cycles.append(cycle)
            capacities.append(capacity)
        methods = sorted(set(source_group["reference_capacity_method"].dropna().astype(str)))
        references = sorted(set(pd.to_numeric(source_group["reference_capacity_ah"], errors="coerce").dropna().astype(float)))
        if len(methods) != 1 or len(references) != 1:
            lineage_valid = False
        inputs.append(
            CapacityTrajectoryInput(
                trajectory_id=str(trajectory["entity_id"]),
                cell_id=cell_id,
                cycle_indices=tuple(cycles),
                capacities=tuple(capacities),
                capacity_units=tuple("Ah" for _ in cycles),
                ordered_state_refs=refs,
                reference_capacity_method=methods[0] if len(methods) == 1 else "unresolved",
                recorded_reference_capacity=references[0] if len(references) == 1 else None,
                representation_maturity="dimensionally_valid",
                lineage_valid=lineage_valid and len(cycles) == len(refs),
                trajectory_schema_id=str(trajectory.get("schema_id", "")),
                temperature_context_available="ambient_temperature_c" in source_group.columns,
                source_uncertainty_status="unavailable",
            )
        )
    metadata = {
        "schema_version": BATTERY_TRAJECTORY_EVALUATOR_VERSION,
        "source_path": source_path,
        "source_checksum_sha256": _file_checksum(source),
        "trajectory_path": trajectory_path,
        "trajectory_checksum_sha256": _file_checksum(trajectory_file),
        "state_path": state_path,
        "state_checksum_sha256": _file_checksum(state_file),
        "trajectory_count": len(inputs),
        "state_count": len(states),
        "selection_decision_checksum": canonical_checksum(selection),
        "pgir_readiness_checksum": canonical_checksum(readiness),
        "network_called": False,
        "model_or_solver_executed": False,
    }
    return inputs, metadata


def run_battery_capacity_evaluator(
    repo_root: str | Path = ".",
    *,
    config: CapacityTrajectoryEvaluatorConfig | None = None,
    write_local: bool = True,
    write_plots: bool = True,
) -> dict[str, Any]:
    config = config or CapacityTrajectoryEvaluatorConfig()
    inputs, source_metadata = load_local_battery_trajectory_inputs(repo_root)
    results = [evaluate_capacity_trajectory(item, config) for item in inputs]
    repeated = [evaluate_capacity_trajectory(item, config) for item in inputs]
    first_checksum = canonical_checksum([result.to_dict(include_identity=True) for result in results])
    second_checksum = canonical_checksum([result.to_dict(include_identity=True) for result in repeated])
    deterministic = first_checksum == second_checksum
    aggregate = aggregate_results(results, inputs)
    trust = assess_evaluator_trust(aggregate, deterministic_rerun_match=deterministic)
    decision = evaluation_decision(aggregate, deterministic_rerun_match=deterministic)
    payload = {
        "schema_version": BATTERY_TRAJECTORY_EVALUATOR_VERSION,
        "operator": evaluator_contract(config),
        "source_metadata": source_metadata,
        "aggregate": aggregate.to_dict(),
        "trust": [item.to_dict() for item in trust],
        "decision": decision.to_dict(),
        "trajectory_results": results,
        "deterministic_result_checksum": first_checksum,
        "deterministic_rerun_checksum": second_checksum,
        "deterministic_rerun_match": deterministic,
    }
    if write_local:
        _write_local_outputs(repo_root, payload, inputs, write_plots=write_plots)
    return payload


def _trajectory_summary_rows(results: Sequence[CapacityTrajectoryResult]) -> list[dict[str, Any]]:
    rows = []
    for result in sorted(results, key=lambda item: item.trajectory_id):
        rows.append(
            {
                "trajectory_id": result.trajectory_id,
                "cell_id": result.cell_id,
                "eligibility_status": result.eligibility_status,
                "trust_status": result.trust_status,
                "total_state_count": result.total_state_count,
                "valid_capacity_count": result.valid_capacity_count,
                "evaluable_transition_count": result.evaluable_transition_count,
                "first_capacity_ah": result.first_capacity,
                "last_capacity_ah": result.last_capacity,
                "first_retention": result.first_retention,
                "last_retention": result.last_retention,
                "robust_difference_scale": result.robust_difference_scale,
                "event_threshold": result.event_threshold,
                "missing_cycle_gap_count": result.finding_counts.get("missing_cycle_gap", 0),
                "non_monotonic_increase_count": result.finding_counts.get("non_monotonic_increase_candidate", 0),
                "abrupt_drop_count": result.finding_counts.get("abrupt_capacity_drop_candidate", 0),
                "abrupt_rise_count": result.finding_counts.get("abrupt_capacity_rise_candidate", 0),
                "plateau_count": result.finding_counts.get("plateau_candidate", 0),
                "accelerated_fade_count": result.finding_counts.get("accelerated_fade_candidate", 0),
                "decelerated_fade_count": result.finding_counts.get("decelerated_fade_candidate", 0),
                "limitations": ";".join(result.limitations),
            }
        )
    return rows


def _report_markdown(payload: Mapping[str, Any], *, compact: bool = False) -> str:
    aggregate = payload["aggregate"]
    decision = payload["decision"]
    findings = aggregate["finding_counts"]
    lines = [
        "# Battery Capacity-Trajectory Evaluator Summary",
        "",
        f"Status: `{decision['status']}`",
        "",
        f"Evaluator: `{EVALUATOR_ID}`",
        "",
        "This is a deterministic cycle-index descriptive audit. It is not a mechanism solver, predictive model, parameter estimator, or physical-time degradation-rate analysis.",
        "",
        "## Coverage",
        "",
        f"- Requested trajectories: {aggregate['requested_trajectories']}",
        f"- Evaluated trajectories: {aggregate['evaluated_trajectories']}",
        f"- Eligible with warnings: {aggregate['eligible_with_warnings']}",
        f"- Blocked trajectories: {aggregate['blocked_trajectories']}",
        f"- Valid capacity observations: {aggregate['valid_capacity_observations']}",
        "",
        "## Aggregate Findings",
        "",
    ]
    for category in FINDING_CATEGORIES:
        lines.append(f"- `{category}`: {findings[category]}")
    lines.extend(
        [
            "",
            "## Threshold And Uncertainty Boundary",
            "",
            "Thresholds are fixed algorithmic detection rules. They are not measurement uncertainty, confidence intervals, learned change points, or fitted physical parameters.",
            "",
            "## Interpretation Boundary",
            "",
            "Findings are descriptive candidates in the observed cycle-index domain. They do not confirm a degradation mechanism, knee point, lifetime, SOH/RUL, causal effect, or production decision.",
        ]
    )
    if not compact:
        lines.extend(
            [
                "",
                "## Determinism",
                "",
                f"- First checksum: `{payload['deterministic_result_checksum']}`",
                f"- Repeated checksum: `{payload['deterministic_rerun_checksum']}`",
                f"- Match: `{payload['deterministic_rerun_match']}`",
            ]
        )
    return "\n".join(lines) + "\n"


def _write_local_outputs(
    repo_root: str | Path,
    payload: Mapping[str, Any],
    inputs: Sequence[CapacityTrajectoryInput],
    *,
    write_plots: bool,
) -> None:
    results: Sequence[CapacityTrajectoryResult] = payload["trajectory_results"]
    manifest = {
        "schema_version": BATTERY_TRAJECTORY_EVALUATOR_VERSION,
        "evaluator_id": EVALUATOR_ID,
        "source_metadata": payload["source_metadata"],
        "config": payload["operator"],
        "trajectory_count": len(inputs),
        "local_only": True,
        "row_level_tracking_prohibited": True,
    }
    _atomic_write_text(_safe_local_path(repo_root, LOCAL_OUTPUTS["input_manifest"]), canonical_json(manifest))
    _write_jsonl(
        _safe_local_path(repo_root, LOCAL_OUTPUTS["trajectory_results"]),
        [result.to_dict(include_identity=True, include_findings=False) for result in results],
    )
    findings = [finding.to_dict() for result in results for finding in result.findings]
    _write_jsonl(_safe_local_path(repo_root, LOCAL_OUTPUTS["trajectory_findings"]), findings)
    summary_rows = _trajectory_summary_rows(results)
    _atomic_write_csv(
        _safe_local_path(repo_root, LOCAL_OUTPUTS["trajectory_summary"]),
        summary_rows,
        list(summary_rows[0].keys()) if summary_rows else ["trajectory_id", "eligibility_status"],
    )
    _atomic_write_csv(
        _safe_local_path(repo_root, LOCAL_OUTPUTS["trust_assessments"]),
        payload["trust"],
        ["trust_dimension", "status", "evidence", "limitations"],
    )
    compact_execution = {
        key: value
        for key, value in payload.items()
        if key not in {"trajectory_results"}
    }
    _atomic_write_text(
        _safe_local_path(repo_root, LOCAL_OUTPUTS["execution_summary"]),
        canonical_json(compact_execution),
    )
    _atomic_write_text(
        _safe_local_path(repo_root, LOCAL_OUTPUTS["report"]),
        _report_markdown(payload),
    )
    if write_plots:
        _write_local_plots(repo_root, inputs, results)


def _atomic_save_figure(figure: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "wb",
        delete=False,
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".png",
    ) as handle:
        temp_path = Path(handle.name)
    try:
        figure.savefig(temp_path, format="png", dpi=140, bbox_inches="tight")
        temp_path.replace(path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def _write_local_plots(
    repo_root: str | Path,
    inputs: Sequence[CapacityTrajectoryInput],
    results: Sequence[CapacityTrajectoryResult],
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plot_root = _safe_local_path(repo_root, f"{DEFAULT_OUTPUT_ROOT}/reports/plots")
    eligible = [result for result in results if result.last_retention is not None]
    input_by_id = {item.trajectory_id: item for item in inputs}
    examples = sorted(eligible, key=lambda item: (-item.valid_capacity_count, item.trajectory_id))[:4]

    figure, axis = plt.subplots(figsize=(8, 4.5))
    for result in examples:
        item = input_by_id[result.trajectory_id]
        valid = [(cycle, capacity) for cycle, capacity in zip(item.cycle_indices, item.capacities) if capacity is not None]
        axis.plot([cycle for cycle, _ in valid], [capacity / result.reference_capacity for _, capacity in valid], label=result.trajectory_id)
    axis.set_xlabel("Cycle index")
    axis.set_ylabel("Capacity retention (ratio)")
    axis.set_title("Deterministically selected longest trajectory examples")
    axis.legend(fontsize=7)
    _atomic_save_figure(figure, plot_root / "retention_trajectory_examples.png")
    plt.close(figure)

    aggregate = aggregate_results(results, inputs)
    categories = [category for category in FINDING_CATEGORIES if aggregate.finding_counts[category] > 0]
    figure, axis = plt.subplots(figsize=(9, 4.5))
    axis.bar(categories, [aggregate.finding_counts[category] for category in categories])
    axis.tick_params(axis="x", rotation=70)
    axis.set_ylabel("Finding count")
    axis.set_title("Descriptive candidate findings")
    _atomic_save_figure(figure, plot_root / "finding_type_counts.png")
    plt.close(figure)

    figure, axis = plt.subplots(figsize=(7, 4.5))
    axis.hist([result.last_retention for result in eligible], bins=min(12, max(4, len(eligible) // 2)))
    axis.set_xlabel("Final observed retention (ratio)")
    axis.set_ylabel("Trajectory count")
    axis.set_title("Final observed retention distribution")
    _atomic_save_figure(figure, plot_root / "final_retention_distribution.png")
    plt.close(figure)

    differences = []
    for result in eligible:
        item = input_by_id[result.trajectory_id]
        valid = [(cycle, capacity / result.reference_capacity) for cycle, capacity in zip(item.cycle_indices, item.capacities) if capacity is not None]
        differences.extend(valid[index][1] - valid[index - 1][1] for index in range(1, len(valid)) if valid[index][0] - valid[index - 1][0] == 1)
    figure, axis = plt.subplots(figsize=(7, 4.5))
    axis.hist(differences, bins=40)
    axis.set_xlabel("Adjacent retention difference")
    axis.set_ylabel("Transition count")
    axis.set_title("Gap-excluded cycle-index transition differences")
    _atomic_save_figure(figure, plot_root / "transition_difference_distribution.png")
    plt.close(figure)


def _eligibility_summary_rows(results: Sequence[CapacityTrajectoryResult]) -> list[dict[str, Any]]:
    statuses = sorted({result.eligibility_status for result in results})
    return [
        {
            "eligibility_status": status,
            "trajectory_count": sum(result.eligibility_status == status for result in results),
            "evaluation_scope": "34_cell_current_source_cycle_index_domain",
            "row_level_identity_included": False,
        }
        for status in statuses
    ]


def _finding_summary_rows(aggregate: CapacityTrajectoryAggregate) -> list[dict[str, Any]]:
    return [
        {
            "finding_category": category,
            "finding_count": aggregate.finding_counts[category],
            "trajectory_count": aggregate.trajectories_with_findings[category],
            "finding_status": "algorithmic_candidate" if aggregate.finding_counts[category] else "not_observed",
            "evaluation_axis": "cycle_index",
            "physical_time_interpretation": "prohibited",
            "mechanism_interpretation": "prohibited",
        }
        for category in FINDING_CATEGORIES
    ]


def claim_evidence_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    decision = payload["decision"]
    aggregate = payload["aggregate"]
    claims = []
    for claim in ALLOWED_CLAIMS:
        claims.append(
            {
                "claim": claim,
                "status": "supported_for_bounded_descriptive_audit",
                "evidence_refs": [
                    TRACKED_OUTPUTS["execution_summary"],
                    TRACKED_OUTPUTS["finding_summary"],
                    TRACKED_OUTPUTS["trust_summary"],
                ],
                "scope": "current_34_cell_source_context",
            }
        )
    for claim in PROHIBITED_INTERPRETATIONS:
        claims.append(
            {
                "claim": claim,
                "status": "prohibited",
                "evidence_refs": [TRACKED_OUTPUTS["decision"]],
                "scope": "unsupported",
            }
        )
    result = {
        "schema_version": BATTERY_TRAJECTORY_EVALUATOR_VERSION,
        "evaluator_id": EVALUATOR_ID,
        "decision_status": decision["status"],
        "evaluated_trajectory_count": aggregate["evaluated_trajectories"],
        "claims": claims,
        "row_level_data_included": False,
        "mechanism_labels_included": False,
    }
    result["result_checksum"] = canonical_checksum(result)
    return result


def export_battery_capacity_evaluator_summary(
    repo_root: str | Path = ".",
    *,
    config: CapacityTrajectoryEvaluatorConfig | None = None,
    write_local: bool = True,
    write_plots: bool = True,
) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    payload = run_battery_capacity_evaluator(
        root,
        config=config,
        write_local=write_local,
        write_plots=write_plots,
    )
    aggregate = payload["aggregate"]
    results: Sequence[CapacityTrajectoryResult] = payload["trajectory_results"]
    execution = {
        "schema_version": BATTERY_TRAJECTORY_EVALUATOR_VERSION,
        "evaluator_id": EVALUATOR_ID,
        "execution_status": payload["decision"]["status"],
        "source_metadata": payload["source_metadata"],
        "config_checksum": canonical_checksum(payload["operator"]),
        "requested_trajectories": aggregate["requested_trajectories"],
        "evaluated_trajectories": aggregate["evaluated_trajectories"],
        "total_states": aggregate["total_states"],
        "valid_capacity_observations": aggregate["valid_capacity_observations"],
        "deterministic_result_checksum": payload["deterministic_result_checksum"],
        "deterministic_rerun_checksum": payload["deterministic_rerun_checksum"],
        "deterministic_rerun_match": payload["deterministic_rerun_match"],
        "row_level_data_included": False,
        "network_called": False,
        "model_or_solver_executed": False,
        "parameter_fitting_performed": False,
        "tracked_outputs": dict(TRACKED_OUTPUTS),
        "local_outputs": dict(LOCAL_OUTPUTS),
    }
    execution["result_checksum"] = canonical_checksum(execution)
    _atomic_write_text(root / TRACKED_OUTPUTS["execution_summary"], canonical_json(execution))
    eligibility_rows = _eligibility_summary_rows(results)
    _atomic_write_csv(root / TRACKED_OUTPUTS["eligibility_summary"], eligibility_rows, list(eligibility_rows[0].keys()))
    finding_rows = _finding_summary_rows(aggregate_results(results))
    _atomic_write_csv(root / TRACKED_OUTPUTS["finding_summary"], finding_rows, list(finding_rows[0].keys()))
    trust_rows = payload["trust"]
    _atomic_write_csv(root / TRACKED_OUTPUTS["trust_summary"], trust_rows, ["trust_dimension", "status", "evidence", "limitations"])
    _atomic_write_text(root / TRACKED_OUTPUTS["decision"], canonical_json(payload["decision"]))
    claims = claim_evidence_payload(payload)
    _atomic_write_text(root / TRACKED_OUTPUTS["claim_evidence"], canonical_json(claims))
    _atomic_write_text(root / TRACKED_OUTPUTS["report_summary"], _report_markdown(payload, compact=True))
    return {
        "status": "exported",
        "decision_status": payload["decision"]["status"],
        "aggregate": aggregate,
        "tracked_outputs": dict(TRACKED_OUTPUTS),
        "local_outputs": dict(LOCAL_OUTPUTS) if write_local else {},
        "deterministic_rerun_match": payload["deterministic_rerun_match"],
    }


def load_battery_capacity_evaluator_summary(repo_root: str | Path = ".") -> dict[str, Any]:
    root = Path(repo_root).resolve()
    decision_path = root / TRACKED_OUTPUTS["decision"]
    execution_path = root / TRACKED_OUTPUTS["execution_summary"]
    if not decision_path.exists() or not execution_path.exists():
        return {"status": "not_available"}
    return {
        "status": "available",
        "schema_version": BATTERY_TRAJECTORY_EVALUATOR_VERSION,
        "decision": json.loads(decision_path.read_text(encoding="utf-8")),
        "execution": json.loads(execution_path.read_text(encoding="utf-8")),
        "tracked_outputs": dict(TRACKED_OUTPUTS),
    }


def validate_battery_capacity_evaluator_result(path: str | Path) -> dict[str, Any]:
    candidate = Path(path)
    errors: list[str] = []
    row_count = 0
    if not candidate.exists():
        return {"valid": False, "status": "missing", "errors": ["result path does not exist"]}
    try:
        if candidate.suffix == ".json":
            payload = json.loads(candidate.read_text(encoding="utf-8"))
            row_count = 1
            if payload.get("schema_version") != BATTERY_TRAJECTORY_EVALUATOR_VERSION:
                errors.append("unexpected schema_version")
        elif candidate.suffix == ".jsonl":
            rows = _load_jsonl(candidate)
            row_count = len(rows)
            if any(row.get("schema_version") != BATTERY_TRAJECTORY_EVALUATOR_VERSION for row in rows):
                errors.append("unexpected JSONL schema_version")
        elif candidate.suffix == ".csv":
            frame = pd.read_csv(candidate)
            row_count = len(frame)
            if len(frame.columns) != len(set(frame.columns)):
                errors.append("duplicate CSV header")
        else:
            errors.append("unsupported result format")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors.append(str(exc))
    text = candidate.read_text(encoding="utf-8", errors="ignore")
    if ":/" in text or ":\\" in text:
        errors.append("absolute path detected")
    for credential in ("API_KEY", "KAGGLE_KEY", "PASSWORD=", "TOKEN="):
        if credential in text.upper():
            errors.append("credential-like content detected")
    return {
        "valid": not errors,
        "status": "valid" if not errors else "invalid",
        "errors": errors,
        "row_count": row_count,
    }


def preview_battery_capacity_evaluation(
    repo_root: str | Path = ".",
    *,
    config: CapacityTrajectoryEvaluatorConfig | None = None,
) -> dict[str, Any]:
    config = config or CapacityTrajectoryEvaluatorConfig()
    inputs, source_metadata = load_local_battery_trajectory_inputs(repo_root)
    return {
        "schema_version": BATTERY_TRAJECTORY_EVALUATOR_VERSION,
        "status": "ready_for_bounded_descriptive_evaluation",
        "expected_trajectories": len(inputs),
        "expected_states": source_metadata["state_count"],
        "operator": evaluator_contract(config),
        "required_metadata": [
            "cycle_index",
            "discharge_capacity_ah",
            "capacity_unit",
            "reference_capacity_policy",
            "state_lineage",
        ],
        "local_outputs": dict(LOCAL_OUTPUTS),
        "tracked_outputs": dict(TRACKED_OUTPUTS),
        "prohibited_claims": list(PROHIBITED_INTERPRETATIONS),
        "result_mutation_performed": False,
        "network_called": False,
        "model_or_solver_executed": False,
    }
