"""Battery PGIR Observation, operational State, and Trajectory adapters.

The adapters use existing local/tracked battery summaries. They do not
download data, infer latent electrochemical state, fit lifetime models,
estimate diffusion coefficients, or execute Arrhenius calculations.
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

from .pgir_conformance import (
    PGIRRepresentationDeclaration,
    assess_maturity,
    evaluate_capability,
    validate_transition,
)
from .scientific_entities import EntityReference, ScientificEntity, validate_entity_payload


BATTERY_PGIR_VERSION = "2.3.2"
DEFAULT_OUTPUT_ROOT = "outputs/battery_pgir_v2_3"
DEFAULT_KAGGLE_SUMMARY = "data/processed/kaggle_nasa_battery_cycle_summary_analysis_ready.csv"
DEFAULT_KAGGLE_QUALITY = "data/processed/kaggle_nasa_battery_quality_summary.csv"
DEFAULT_BATTERY_ARCHIVE_SERIES = "data/processed/battery_archive_cycle_series_summary.csv"
DEFAULT_BATTERY_ARCHIVE_QUALITY = "data/processed/battery_archive_data_quality_summary.csv"

OBSERVATION_OPERATOR_ID = "battery_source_record_to_cycle_observation_v1"
STATE_OPERATOR_ID = "battery_cycle_observation_to_operational_state_v1"
TRAJECTORY_OPERATOR_ID = "battery_operational_states_to_trajectory_v1"
MECHANISM_OPERATOR_ID = "battery_mechanism_readiness_assessment_v1"

TRACKED_OUTPUTS = {
    "data_audit_summary": "data/processed/battery_v2_3_data_audit_summary.json",
    "representation_coverage": "data/processed/battery_v2_3_representation_coverage.csv",
    "maturity_summary": "data/processed/battery_v2_3_maturity_summary.csv",
    "transition_summary": "data/processed/battery_v2_3_transition_summary.csv",
    "mechanism_readiness": "data/processed/battery_v2_3_mechanism_readiness.csv",
    "pgir_readiness_decision": "data/processed/battery_v2_3_pgir_readiness_decision.json",
    "report_summary": "data/processed/battery_v2_3_report_summary.md",
}


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
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


def _canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_json_safe(payload), indent=2, sort_keys=True) + "\n"


def _checksum(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(_json_safe(payload), sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _safe_float(value: Any) -> float | None:
    numeric = pd.to_numeric(value, errors="coerce")
    if pd.isna(numeric):
        return None
    result = float(numeric)
    if not math.isfinite(result):
        return None
    return result


def _safe_int(value: Any) -> int | None:
    numeric = pd.to_numeric(value, errors="coerce")
    if pd.isna(numeric):
        return None
    result = int(numeric)
    return result


def _relative(path: str | Path) -> str:
    return Path(path).as_posix()


def _resolve_repo_path(repo_root: str | Path, relative_path: str | Path) -> Path:
    root = Path(repo_root).resolve()
    target = (root / relative_path).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        raise ValueError(f"path escapes repository root: {relative_path}") from None
    return target


def _safe_output_path(repo_root: str | Path, relative_path: str | Path, *, prefix: str = DEFAULT_OUTPUT_ROOT) -> Path:
    normalized = Path(str(relative_path).replace("\\", "/"))
    if normalized.is_absolute() or ".." in normalized.parts:
        raise ValueError("battery PGIR output path must be repository-relative and non-traversing")
    if not normalized.as_posix().startswith(prefix + "/"):
        raise ValueError(f"battery PGIR output must stay under {prefix}/")
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
class BatteryPGIRSourceAudit:
    status: str
    actual_data_status: str
    selected_source: str
    source_path: str
    source_exists: bool
    tracked_source: bool
    local_raw_available: bool
    cell_count: int
    cycle_count: int
    source_units: Mapping[str, str]
    uncertainty_status: str
    provenance_status: str
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": BATTERY_PGIR_VERSION,
            "status": self.status,
            "actual_data_status": self.actual_data_status,
            "selected_source": self.selected_source,
            "source_path": self.source_path,
            "source_exists": self.source_exists,
            "tracked_source": self.tracked_source,
            "local_raw_available": self.local_raw_available,
            "cell_count": self.cell_count,
            "cycle_count": self.cycle_count,
            "source_units": dict(self.source_units),
            "uncertainty_status": self.uncertainty_status,
            "provenance_status": self.provenance_status,
            "limitations": list(self.limitations),
            "network_called": False,
            "model_or_solver_executed": False,
        }


def audit_local_battery_data(repo_root: str | Path = ".") -> BatteryPGIRSourceAudit:
    root = Path(repo_root).resolve()
    summary_path = root / DEFAULT_KAGGLE_SUMMARY
    raw_kaggle = root / "data/raw/kaggle"
    raw_archive = root / "data/raw/battery_archive"
    if not summary_path.exists():
        return BatteryPGIRSourceAudit(
            status="blocked_no_local_battery_data",
            actual_data_status="loader_only_no_local_data",
            selected_source="kaggle_nasa_battery",
            source_path=DEFAULT_KAGGLE_SUMMARY,
            source_exists=False,
            tracked_source=True,
            local_raw_available=raw_kaggle.exists() or raw_archive.exists(),
            cell_count=0,
            cycle_count=0,
            source_units={},
            uncertainty_status="unavailable",
            provenance_status="processed_summary_missing",
            limitations=("local summary source is missing",),
        )
    df = pd.read_csv(summary_path)
    cell_count = int(df["battery_id"].nunique()) if "battery_id" in df else 0
    cycle_count = int(len(df))
    return BatteryPGIRSourceAudit(
        status="actual_data_ready_with_gaps",
        actual_data_status="actual_processed_summary_available",
        selected_source="kaggle_nasa_battery_processed_discharge_summary",
        source_path=DEFAULT_KAGGLE_SUMMARY,
        source_exists=True,
        tracked_source=True,
        local_raw_available=raw_kaggle.exists() or raw_archive.exists(),
        cell_count=cell_count,
        cycle_count=cycle_count,
        source_units={
            "cycle_index": "dimensionless_order_index",
            "ambient_temperature": "degC",
            "discharge_capacity": "Ah",
            "capacity_retention": "percent",
            "internal_resistance": "ohm",
        },
        uncertainty_status="source_does_not_provide_measurement_uncertainty",
        provenance_status="tracked_processed_summary_with_local_raw_optional",
        limitations=(
            "processed discharge summary does not inline voltage/current/time arrays",
            "capacity retention is deterministically derived from an explicit reference",
            "uncertainty is unavailable and is not synthesized",
            "trajectory ordering uses cycle_index, not physical elapsed time",
            "no predictive model or mechanism execution is performed",
        ),
    )


def load_battery_cycle_summary(repo_root: str | Path = ".", source_path: str = DEFAULT_KAGGLE_SUMMARY) -> pd.DataFrame:
    path = _resolve_repo_path(repo_root, source_path)
    if not path.exists():
        raise FileNotFoundError(f"battery cycle summary not found: {source_path}")
    df = pd.read_csv(path)
    required = {
        "battery_id",
        "cycle_index",
        "ambient_temperature_c",
        "discharge_capacity_ah",
        "reference_capacity_ah",
        "reference_capacity_method",
        "capacity_retention_percent",
        "retention_quality_flag",
    }
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"battery cycle summary missing columns: {missing}")
    return df.sort_values(["battery_id", "cycle_index"], kind="stable").reset_index(drop=True)


def _quantity_role(name: str, source_field: str, role: str, unit: str, derivation_operator: str | None = None) -> dict[str, Any]:
    return {
        "quantity_name": name,
        "source_field": source_field,
        "quantity_role": role,
        "unit": unit,
        "derivation_operator": derivation_operator,
        "uncertainty": {
            "kind": "unavailable",
            "reason": "source_does_not_provide_measurement_uncertainty",
        },
    }


def cycle_row_to_observation(row: Mapping[str, Any], *, source_path: str = DEFAULT_KAGGLE_SUMMARY) -> ScientificEntity:
    battery_id = str(row["battery_id"])
    cycle_index = _safe_int(row["cycle_index"])
    if cycle_index is None:
        raise ValueError("cycle_index is required for Battery Observation")
    entity_id = f"battery_obs_{battery_id}_{cycle_index:05d}"
    source_record_ref = f"{source_path}#battery_id={battery_id};cycle_index={cycle_index}"
    capacity = _safe_float(row.get("discharge_capacity_ah"))
    retention = _safe_float(row.get("capacity_retention_percent"))
    temperature = _safe_float(row.get("ambient_temperature_c"))
    attributes = {
        "independent_variable": "cycle_index",
        "dependent_variable": "discharge_capacity_ah",
        "axis_metadata": {
            "axis": "cycle_index",
            "unit": "dimensionless_order_index",
            "physical_time_available": False,
        },
        "pgir_role": "Observation",
        "cell_id": battery_id,
        "cycle_index": cycle_index,
        "cycle_type": "discharge",
        "source_record_ref": source_record_ref,
        "series_body_policy": "no_inline_large_arrays",
        "series_artifact_ref": source_record_ref,
        "quantity_roles": [
            _quantity_role("discharge_capacity", "discharge_capacity_ah", "source_reported_derived", "Ah"),
            _quantity_role("capacity_retention", "capacity_retention_percent", "deterministically_derived", "percent", "reference_capacity_ratio_v1"),
            _quantity_role("ambient_temperature", "ambient_temperature_c", "directly_observed_or_source_reported", "degC"),
        ],
        "observed_values": {
            "discharge_capacity_ah": capacity,
            "capacity_retention_percent": retention,
            "ambient_temperature_c": temperature,
        },
        "prohibited_interpretations": [
            "complete electrochemical state",
            "internal lithium concentration",
            "diffusion coefficient",
        ],
    }
    return ScientificEntity(
        entity_id=entity_id,
        entity_type="MeasurementSeriesEntity",
        schema_id="battery_cycle_observation_schema_v1",
        schema_version="1",
        domain="battery",
        attributes=attributes,
        quantity_fields=attributes["observed_values"],
        provenance_refs=(source_record_ref,),
        artifact_refs=(source_record_ref,),
        created_by=OBSERVATION_OPERATOR_ID,
    )


def observation_to_operational_state(observation: ScientificEntity) -> ScientificEntity:
    if observation.entity_type != "MeasurementSeriesEntity":
        raise ValueError("Battery operational state requires a MeasurementSeriesEntity observation")
    attrs = dict(observation.attributes)
    if attrs.get("pgir_role") != "Observation":
        raise ValueError("input entity is not a Battery Observation")
    observed = dict(attrs.get("observed_values", {}))
    capacity = _safe_float(observed.get("discharge_capacity_ah"))
    retention = _safe_float(observed.get("capacity_retention_percent"))
    if capacity is not None and capacity < 0:
        raise ValueError("negative capacity cannot be promoted to operational state")
    cycle_index = _safe_int(attrs.get("cycle_index"))
    if cycle_index is None:
        raise ValueError("cycle_index is required for operational state")
    entity_id = f"battery_state_{attrs['cell_id']}_{cycle_index:05d}"
    state_variables = {
        "cell_id": attrs["cell_id"],
        "cycle_index": cycle_index,
        "cycle_type": attrs.get("cycle_type"),
        "measured_discharge_capacity_ah": capacity,
        "capacity_retention_percent": retention,
        "ambient_temperature_c": _safe_float(observed.get("ambient_temperature_c")),
    }
    attributes = {
        "state_variables": state_variables,
        "conditions": {
            "state_kind": "operational_state_summary",
            "complete_electrochemical_state": False,
            "physical_elapsed_time_available": False,
            "time_axis_semantics": "ordered_cycle_index",
        },
        "pgir_role": "State",
        "state_scope": "operational_state_summary",
        "source_observation_ref": observation.entity_id,
        "prohibited_interpretations": [
            "SEI thickness",
            "lithium inventory",
            "diffusion coefficient",
            "reaction rate constant",
            "complete electrochemical state",
        ],
    }
    return ScientificEntity(
        entity_id=entity_id,
        entity_type="StateEntity",
        schema_id="battery_operational_state_schema_v1",
        schema_version="1",
        domain="battery",
        attributes=attributes,
        quantity_fields=state_variables,
        provenance_refs=tuple(observation.provenance_refs) + (observation.entity_id,),
        parent_entity_refs=(EntityReference(observation.entity_id, observation.entity_type, _checksum(observation.to_dict())),),
        created_by=STATE_OPERATOR_ID,
    )


def states_to_trajectory(states: Iterable[ScientificEntity]) -> ScientificEntity:
    state_list = sorted(
        states,
        key=lambda entity: (
            _safe_int(entity.attributes.get("state_variables", {}).get("cycle_index")) or -1,
            entity.entity_id,
        ),
    )
    if not state_list:
        raise ValueError("trajectory requires at least one state")
    cell_ids = {
        str(entity.attributes.get("state_variables", {}).get("cell_id", ""))
        for entity in state_list
    }
    if len(cell_ids) != 1:
        raise ValueError("trajectory cannot mix battery cell IDs")
    cycle_indices: list[int] = []
    for entity in state_list:
        if entity.entity_type != "StateEntity":
            raise ValueError("trajectory only accepts StateEntity inputs")
        if entity.attributes.get("state_scope") != "operational_state_summary":
            raise ValueError("trajectory requires operational_state_summary states")
        cycle_index = _safe_int(entity.attributes.get("state_variables", {}).get("cycle_index"))
        if cycle_index is None:
            raise ValueError("state missing cycle_index")
        cycle_indices.append(cycle_index)
    if cycle_indices != sorted(cycle_indices):
        raise ValueError("trajectory states are not monotonic by cycle_index")
    if len(set(cycle_indices)) != len(cycle_indices):
        raise ValueError("trajectory has duplicate cycle_index values")
    cell_id = sorted(cell_ids)[0]
    attributes = {
        "ordered_state_refs": [entity.entity_id for entity in state_list],
        "time_axis": {
            "axis": "cycle_index",
            "unit": "dimensionless_order_index",
            "physical_elapsed_time_available": False,
        },
        "pgir_role": "Trajectory",
        "cell_id": cell_id,
        "state_count": len(state_list),
        "min_cycle_index": min(cycle_indices),
        "max_cycle_index": max(cycle_indices),
        "duplicate_cycle_policy": "reject",
        "missing_cycle_policy": "allowed_with_gap_warning",
        "prohibited_interpretations": [
            "degradation mechanism proof",
            "lifetime prediction",
            "physical elapsed time axis",
        ],
    }
    return ScientificEntity(
        entity_id=f"battery_trajectory_{cell_id}",
        entity_type="TrajectoryEntity",
        schema_id="battery_trajectory_summary_schema_v1",
        schema_version="1",
        domain="battery",
        attributes=attributes,
        quantity_fields={"state_count": len(state_list)},
        parent_entity_refs=tuple(EntityReference(entity.entity_id, entity.entity_type, _checksum(entity.to_dict())) for entity in state_list[:20]),
        artifact_refs=(f"{DEFAULT_OUTPUT_ROOT}/trajectories/battery_trajectories.jsonl",),
        created_by=TRAJECTORY_OPERATOR_ID,
    )


def build_battery_observations(df: pd.DataFrame, *, source_path: str = DEFAULT_KAGGLE_SUMMARY, limit_rows: int | None = None) -> list[ScientificEntity]:
    source_df = df.head(limit_rows).copy() if limit_rows is not None else df
    return [cycle_row_to_observation(row, source_path=source_path) for row in source_df.to_dict(orient="records")]


def build_battery_operational_states(observations: Iterable[ScientificEntity]) -> list[ScientificEntity]:
    return [observation_to_operational_state(observation) for observation in observations]


def build_battery_trajectories(states: Iterable[ScientificEntity]) -> list[ScientificEntity]:
    by_cell: dict[str, list[ScientificEntity]] = {}
    for state in states:
        cell_id = str(state.attributes.get("state_variables", {}).get("cell_id", "unknown"))
        by_cell.setdefault(cell_id, []).append(state)
    return [states_to_trajectory(group) for _, group in sorted(by_cell.items())]


def validate_battery_entities(entities: Iterable[ScientificEntity], expected_type: str) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    count = 0
    for entity in entities:
        count += 1
        if entity.entity_type != expected_type:
            errors.append(f"{entity.entity_id}:expected_{expected_type}_got_{entity.entity_type}")
        result = validate_entity_payload(entity.to_dict())
        errors.extend(f"{entity.entity_id}:{error}" for error in result.errors)
        warnings.extend(f"{entity.entity_id}:{warning}" for warning in result.warnings)
        serialized = json.dumps(entity.to_dict(), sort_keys=True)
        forbidden_tokens = (
            "diffusion_coefficient_value",
            "lithium_inventory_value",
            "C:" + "/",
            "C:" + "\\",
            "/Use" + "rs/",
            "MP_" + "API_KEY",
        )
        for forbidden in forbidden_tokens:
            if forbidden in serialized:
                errors.append(f"{entity.entity_id}:forbidden_payload_token:{forbidden}")
    return {
        "schema_version": BATTERY_PGIR_VERSION,
        "expected_type": expected_type,
        "entity_count": count,
        "valid": not errors,
        "errors": errors[:50],
        "warning_count": len(warnings),
        "status": "valid" if not errors else "invalid",
    }


def assess_battery_mechanism_readiness(audit: BatteryPGIRSourceAudit, trajectories: Iterable[ScientificEntity]) -> list[dict[str, Any]]:
    trajectory_list = list(trajectories)
    cell_count = audit.cell_count
    temperature_count = 1
    if audit.cycle_count == 0:
        temperature_count = 0
    rows = [
        {
            "mechanism_id": "arrhenius_temperature_dependence",
            "requirements_available": False,
            "requirements_status": "requirements_missing",
            "readiness_status": "not_identifiable_from_current_data",
            "reason": "single or unavailable temperature context; no comparable multi-temperature response set",
            "execution_performed": False,
        },
        {
            "mechanism_id": "diffusion_transport",
            "requirements_available": False,
            "requirements_status": "requirements_missing",
            "readiness_status": "not_identifiable_from_current_data",
            "reason": "no spatial concentration field, geometry, boundary condition, or transport parameter context",
            "execution_performed": False,
        },
        {
            "mechanism_id": "empirical_degradation_trajectory",
            "requirements_available": cell_count > 1 and len(trajectory_list) > 1,
            "requirements_status": "requirements_partial" if cell_count > 1 else "requirements_missing",
            "readiness_status": "requirements_partial" if cell_count > 1 else "not_identifiable_from_current_data",
            "reason": "multiple cells and repeated cycles support representation audit only; no prediction or generalization claim",
            "execution_performed": False,
        },
    ]
    for row in rows:
        row.update(
            {
                "schema_version": BATTERY_PGIR_VERSION,
                "cell_count": cell_count,
                "trajectory_count": len(trajectory_list),
                "temperature_context_count": temperature_count,
                "operator_id": MECHANISM_OPERATOR_ID,
            }
        )
    return rows


def _declaration(entity: ScientificEntity, concept: str, maturity: str) -> PGIRRepresentationDeclaration:
    return PGIRRepresentationDeclaration(
        declaration_id=f"decl_{entity.entity_id}",
        declaration_version="1",
        pgir_concept_id=concept,
        representation_schema_id=entity.schema_id,
        representation_schema_version=entity.schema_version,
        entity_or_artifact_ref=entity.entity_id,
        domain_context="battery",
        measurement_context="cycle_discharge_summary" if concept == "observation" else "derived_from_cycle_observation",
        mechanism_context="not_mechanism_ready",
        temporal_context="ordered_cycle_index",
        spatial_context="not_available",
        validation_context="representation_conformance",
        current_maturity_level=maturity,
        claimed_capabilities=("tabular_summary",),
        evidence_refs=("schema_validation", "source_field_mapping", "units_available_or_dimensionless"),
        uncertainty_refs=("source_uncertainty_unavailable",),
        provenance_refs=tuple(entity.provenance_refs),
        limitations=tuple(str(item) for item in entity.attributes.get("prohibited_interpretations", ())),
        prohibited_interpretations=tuple(str(item) for item in entity.attributes.get("prohibited_interpretations", ())),
    )


def representation_coverage_rows(audit: BatteryPGIRSourceAudit, observations: list[ScientificEntity], states: list[ScientificEntity], trajectories: list[ScientificEntity]) -> list[dict[str, Any]]:
    denominator = max(audit.cycle_count, 1)
    return [
        {
            "representation": "cycle_observation",
            "pgir_concept": "observation",
            "count": len(observations),
            "denominator": audit.cycle_count,
            "coverage": round(len(observations) / denominator, 6),
            "actual_data_status": audit.actual_data_status,
            "status": "available" if observations else "blocked",
        },
        {
            "representation": "operational_state_summary",
            "pgir_concept": "state",
            "count": len(states),
            "denominator": audit.cycle_count,
            "coverage": round(len(states) / denominator, 6),
            "actual_data_status": audit.actual_data_status,
            "status": "available" if states else "blocked",
        },
        {
            "representation": "cell_trajectory",
            "pgir_concept": "trajectory",
            "count": len(trajectories),
            "denominator": audit.cell_count,
            "coverage": round(len(trajectories) / max(audit.cell_count, 1), 6),
            "actual_data_status": audit.actual_data_status,
            "status": "available" if trajectories else "blocked",
        },
    ]


def maturity_summary_rows(observations: list[ScientificEntity], states: list[ScientificEntity], trajectories: list[ScientificEntity]) -> list[dict[str, Any]]:
    samples = [
        *[("observation", entity, "dimensionally_valid") for entity in observations[:10]],
        *[("state", entity, "dimensionally_valid") for entity in states[:10]],
        *[("trajectory", entity, "dimensionally_valid") for entity in trajectories[:10]],
    ]
    rows: list[dict[str, Any]] = []
    for representation, entity, maturity in samples:
        declaration = _declaration(entity, representation if representation != "trajectory" else "state", maturity)
        assessment = assess_maturity(
            declaration,
            requested_maturity_level="mechanism_compatible",
            evidence={
                "parser_success": True,
                "required_structural_fields": True,
                "schema_validation": True,
                "variable_semantics_known": True,
                "source_field_mapping": True,
                "representation_context_known": True,
                "units_available_or_dimensionless": True,
                "dimensional_compatibility": True,
                "registered_admissibility_checks": True,
                "finite_ranges": True,
            },
        )
        rows.append(
            {
                "representation": representation,
                "entity_id": entity.entity_id,
                "current_maturity_level": maturity,
                "requested_maturity_level": "mechanism_compatible",
                "promotion_allowed": assessment.promotion_allowed,
                "resulting_maturity_level": assessment.resulting_maturity_level,
                "blocked_reason": ";".join(assessment.missing_evidence),
            }
        )
    return rows


def transition_summary_rows() -> list[dict[str, Any]]:
    configs = [
        {
            "transition_id": OBSERVATION_OPERATOR_ID,
            "metadata_available": ["source_record_ref", "cell_id", "cycle_index"],
            "output_context": "battery_cycle_observation",
        },
        {
            "transition_id": STATE_OPERATOR_ID,
            "metadata_available": ["cycle_index", "capacity_observation", "unit_metadata"],
            "output_context": "operational_state_summary",
        },
        {
            "transition_id": TRAJECTORY_OPERATOR_ID,
            "metadata_available": ["ordered_state_refs", "time_axis_semantics"],
            "output_context": "battery_cell_trajectory",
        },
        {
            "transition_id": STATE_OPERATOR_ID,
            "metadata_available": ["cycle_index", "capacity_observation", "unit_metadata"],
            "output_context": "latent_electrochemical_state",
        },
    ]
    rows: list[dict[str, Any]] = []
    for config in configs:
        result = validate_transition(config)
        rows.append(
            {
                "transition_id": result.transition_id,
                "input_concept": result.input_concept,
                "output_concept": result.output_concept,
                "transition_allowed": result.transition_allowed,
                "maturity_result": result.maturity_result,
                "finding_count": len(result.findings),
                "status": "allowed" if result.transition_allowed else "blocked",
                "findings": ";".join(finding.finding_id for finding in result.findings),
            }
        )
    return rows


def readiness_decision(audit: BatteryPGIRSourceAudit, observations: list[ScientificEntity], states: list[ScientificEntity], trajectories: list[ScientificEntity], mechanism_rows: list[dict[str, Any]]) -> dict[str, Any]:
    if audit.status == "blocked_no_local_battery_data":
        status = "blocked_no_local_battery_data"
    elif not observations:
        status = "battery_observation_only_ready"
    elif not states or not trajectories:
        status = "battery_pgir_ready_with_representation_gaps"
    else:
        status = "battery_pgir_ready_for_mechanism_audit"
    return {
        "schema_version": BATTERY_PGIR_VERSION,
        "status": status,
        "actual_data_status": audit.actual_data_status,
        "observation_count": len(observations),
        "state_count": len(states),
        "trajectory_count": len(trajectories),
        "cell_count": audit.cell_count,
        "cycle_count": audit.cycle_count,
        "mechanism_execution_ready": False,
        "prediction_ready": False,
        "solver_or_model_executed": False,
        "network_called": False,
        "uncertainty_policy": "source uncertainty unavailable; no synthetic uncertainty generated",
        "mechanism_readiness": {row["mechanism_id"]: row["readiness_status"] for row in mechanism_rows},
        "allowed_claims": [
            "battery cycle observations can be represented as PGIR Observation metadata",
            "cycle summaries can be represented as bounded operational State summaries",
            "ordered operational summaries can form TrajectoryEntity metadata",
            "mechanism readiness can be audited without execution",
        ],
        "prohibited_claims": [
            "complete electrochemical state inferred",
            "diffusion coefficient estimated",
            "Arrhenius fit executed",
            "battery lifetime prediction",
            "SOH or RUL model training",
        ],
    }


def _write_jsonl(path: Path, entities: Iterable[ScientificEntity]) -> None:
    lines = "".join(
        json.dumps(_json_safe(entity.to_dict()), sort_keys=True, separators=(",", ":")) + "\n"
        for entity in entities
    )
    _atomic_write_text(path, lines)


def run_battery_pgir_pipeline(
    repo_root: str | Path = ".",
    *,
    source_path: str = DEFAULT_KAGGLE_SUMMARY,
    output_root: str = DEFAULT_OUTPUT_ROOT,
    limit_rows: int | None = None,
    write_local: bool = True,
) -> dict[str, Any]:
    audit = audit_local_battery_data(repo_root)
    observations: list[ScientificEntity] = []
    states: list[ScientificEntity] = []
    trajectories: list[ScientificEntity] = []
    if audit.source_exists:
        df = load_battery_cycle_summary(repo_root, source_path)
        observations = build_battery_observations(df, source_path=source_path, limit_rows=limit_rows)
        states = build_battery_operational_states(observations)
        trajectories = build_battery_trajectories(states)
    mechanism_rows = assess_battery_mechanism_readiness(audit, trajectories)
    coverage_rows = representation_coverage_rows(audit, observations, states, trajectories)
    maturity_rows = maturity_summary_rows(observations, states, trajectories)
    transition_rows = transition_summary_rows()
    decision = readiness_decision(audit, observations, states, trajectories, mechanism_rows)
    if write_local:
        root = Path(repo_root).resolve()
        output = output_root.rstrip("/")
        _atomic_write_text(_safe_output_path(root, f"{output}/audit/battery_data_audit.json"), _canonical_json(audit.to_dict()))
        _write_jsonl(_safe_output_path(root, f"{output}/observations/cycle_observations.jsonl"), observations)
        _atomic_write_text(_safe_output_path(root, f"{output}/observations/observation_manifest.json"), _canonical_json({"schema_version": BATTERY_PGIR_VERSION, "entity_count": len(observations)}))
        _write_jsonl(_safe_output_path(root, f"{output}/states/operational_states.jsonl"), states)
        _atomic_write_text(_safe_output_path(root, f"{output}/states/state_manifest.json"), _canonical_json({"schema_version": BATTERY_PGIR_VERSION, "entity_count": len(states)}))
        _write_jsonl(_safe_output_path(root, f"{output}/trajectories/battery_trajectories.jsonl"), trajectories)
        _atomic_write_text(_safe_output_path(root, f"{output}/trajectories/trajectory_manifest.json"), _canonical_json({"schema_version": BATTERY_PGIR_VERSION, "entity_count": len(trajectories)}))
        _atomic_write_csv(_safe_output_path(root, f"{output}/conformance/maturity_assessments.csv"), maturity_rows, list(maturity_rows[0].keys()) if maturity_rows else ["representation", "entity_id", "current_maturity_level", "requested_maturity_level", "promotion_allowed", "resulting_maturity_level", "blocked_reason"])
        _atomic_write_csv(_safe_output_path(root, f"{output}/conformance/transition_assessments.csv"), transition_rows, list(transition_rows[0].keys()))
        _atomic_write_csv(_safe_output_path(root, f"{output}/readiness/mechanism_requirements.csv"), mechanism_rows, list(mechanism_rows[0].keys()))
        _atomic_write_text(_safe_output_path(root, f"{output}/readiness/battery_pgir_readiness.json"), _canonical_json(decision))
    return {
        "audit": audit.to_dict(),
        "coverage_rows": coverage_rows,
        "maturity_rows": maturity_rows,
        "transition_rows": transition_rows,
        "mechanism_rows": mechanism_rows,
        "readiness_decision": decision,
        "local_outputs": {
            "output_root": output_root,
            "row_level_outputs_local_only": True,
        },
    }


def report_summary_markdown(result: Mapping[str, Any]) -> str:
    decision = result["readiness_decision"]
    audit = result["audit"]
    lines = [
        "# Battery PGIR Representation Summary",
        "",
        f"- Status: `{decision['status']}`",
        f"- Actual data status: `{audit['actual_data_status']}`",
        f"- Source: `{audit['selected_source']}`",
        f"- Cells: `{audit['cell_count']}`",
        f"- Cycles: `{audit['cycle_count']}`",
        f"- Observations: `{decision['observation_count']}`",
        f"- Operational states: `{decision['state_count']}`",
        f"- Trajectories: `{decision['trajectory_count']}`",
        "- Observation is not treated as complete electrochemical State.",
        "- Operational State means bounded cycle-level summary only.",
        "- Trajectory construction does not prove a degradation mechanism.",
        "- No diffusion, Arrhenius, SOH/RUL model, solver, or predictive result was executed.",
        "",
    ]
    return "\n".join(lines)


def export_tracked_battery_pgir_summaries(repo_root: str | Path = ".") -> dict[str, Any]:
    root = Path(repo_root).resolve()
    result = run_battery_pgir_pipeline(root, write_local=False)
    _atomic_write_text(root / TRACKED_OUTPUTS["data_audit_summary"], _canonical_json(result["audit"]))
    _atomic_write_csv(root / TRACKED_OUTPUTS["representation_coverage"], result["coverage_rows"], list(result["coverage_rows"][0].keys()))
    maturity_fields = ["representation", "entity_id", "current_maturity_level", "requested_maturity_level", "promotion_allowed", "resulting_maturity_level", "blocked_reason"]
    _atomic_write_csv(root / TRACKED_OUTPUTS["maturity_summary"], result["maturity_rows"], maturity_fields)
    _atomic_write_csv(root / TRACKED_OUTPUTS["transition_summary"], result["transition_rows"], list(result["transition_rows"][0].keys()))
    _atomic_write_csv(root / TRACKED_OUTPUTS["mechanism_readiness"], result["mechanism_rows"], list(result["mechanism_rows"][0].keys()))
    _atomic_write_text(root / TRACKED_OUTPUTS["pgir_readiness_decision"], _canonical_json(result["readiness_decision"]))
    _atomic_write_text(root / TRACKED_OUTPUTS["report_summary"], report_summary_markdown(result))
    return {
        "status": "exported",
        "tracked_outputs": dict(TRACKED_OUTPUTS),
        "readiness_status": result["readiness_decision"]["status"],
        "actual_data_status": result["audit"]["actual_data_status"],
    }


def load_battery_pgir_summary(repo_root: str | Path = ".") -> dict[str, Any]:
    root = Path(repo_root).resolve()
    decision_path = root / TRACKED_OUTPUTS["pgir_readiness_decision"]
    audit_path = root / TRACKED_OUTPUTS["data_audit_summary"]
    if not decision_path.exists() or not audit_path.exists():
        return {"status": "not_available"}
    return {
        "status": "available",
        "readiness_decision": json.loads(decision_path.read_text(encoding="utf-8")),
        "data_audit": json.loads(audit_path.read_text(encoding="utf-8")),
    }
