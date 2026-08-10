"""Read-only adapters for a common bounded research-planning surface.

The adapters in this module do not execute actions, search the network, acquire
new data, fit models, or upgrade scientific evidence. They translate existing,
domain-specific scientific state into one stable planning-decision shape while
leaving each domain's actual scientific rules in its existing implementation.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
from pathlib import Path
from typing import Any, Mapping

from .external_evidence_contract import (
    ExternalEvidenceContractError,
    evaluate_external_source_candidate,
)
from .kernel import ResearchLoopError, load_research_state
from .nasa_action_policy import plan_nasa_next_action

PLANNING_DECISION_SCHEMA_VERSION = "1.0"
PLANNING_ADAPTER_VERSION = "1.3"

_NASA_ADAPTER = "nasa-battery"
_MATERIALS_PROJECT_ADAPTER = "materials-project-external-source"
_TM_FE_SI_ADAPTER = "tm-fe-si-descriptive"
_NIST_AMBENCH_ADAPTER = "nist-ambench-process-characterization"
_ADAPTER_IDS = (
    _NASA_ADAPTER,
    _MATERIALS_PROJECT_ADAPTER,
    _TM_FE_SI_ADAPTER,
    _NIST_AMBENCH_ADAPTER,
)
_NASA_EVIDENCE_LEVELS = {"Unsupported", "Inconclusive", "Diagnostic"}
_NIST_EXPECTED_TRACES: dict[int, tuple[str, float, float]] = {
    1: ("amb2018-02-C", 297.0, 800.0),
    2: ("amb2018-02-C", 297.0, 800.0),
    3: ("amb2018-02-C", 297.0, 800.0),
    4: ("amb2018-02-C", 297.0, 800.0),
    5: ("amb2018-02-A", 195.0, 800.0),
    6: ("amb2018-02-A", 195.0, 800.0),
    7: ("amb2018-02-A", 195.0, 800.0),
    8: ("amb2018-02-B", 195.0, 1200.0),
    9: ("amb2018-02-B", 195.0, 1200.0),
    10: ("amb2018-02-B", 195.0, 1200.0),
}

_MP_REQUIREMENT_CONFIG = Path(
    "configs/research/materials_project_external_evidence_requirement.v1.json"
)
_MP_CANDIDATE_REGISTRY = Path(
    "configs/research/materials_project_external_source_candidates.v1.json"
)
_MP_PLANNING_CLOSEOUT = Path(
    "configs/research/materials_project_external_source_search_planning_closeout.v1.json"
)
_TM_FE_SI_READINESS = Path(
    "configs/research/tm_fe_si_characterization_consumer_readiness.v1.json"
)
_NIST_AMBENCH_READINESS = Path(
    "configs/research/nist_ambench_2018_02_planning_readiness.v1.json"
)


class PlanningAdapterError(ResearchLoopError):
    """Raised when a domain adapter cannot produce a defensible planning decision."""


def available_planning_adapters() -> tuple[str, ...]:
    """Return stable adapter identifiers accepted by the common planning surface."""
    return _ADAPTER_IDS


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PlanningAdapterError(f"duplicate JSON key is not allowed: {key}")
        result[key] = value
    return result


def _nonempty_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PlanningAdapterError(f"{field} must be a non-empty string")
    return value.strip()


def _finite_float(
    value: object,
    field: str,
    *,
    positive: bool = False,
    nonnegative: bool = False,
) -> float:
    text = _nonempty_text(value, field)
    try:
        number = float(text)
    except ValueError as exc:
        raise PlanningAdapterError(f"{field} must be numeric") from exc
    if not math.isfinite(number):
        raise PlanningAdapterError(f"{field} must be finite")
    if positive and number <= 0:
        raise PlanningAdapterError(f"{field} must be positive")
    if nonnegative and number < 0:
        raise PlanningAdapterError(f"{field} must be non-negative")
    return number


def _canonical_positive_int(value: object, field: str) -> int:
    text = _nonempty_text(value, field)
    try:
        parsed = int(text)
    except ValueError as exc:
        raise PlanningAdapterError(f"{field} must be an integer") from exc
    if parsed <= 0 or text != str(parsed):
        raise PlanningAdapterError(f"{field} must be a canonical positive integer")
    return parsed


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_text_snapshot(path: Path) -> tuple[str, str]:
    data = path.read_bytes()
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PlanningAdapterError(f"planning evidence must be UTF-8: {path}") from exc
    return text, _sha256_bytes(data)


def _load_json_snapshot(path: Path) -> tuple[dict[str, Any], str]:
    text, digest = _read_text_snapshot(path)
    try:
        payload = json.loads(text, object_pairs_hook=_reject_duplicate_pairs)
    except json.JSONDecodeError as exc:
        raise PlanningAdapterError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise PlanningAdapterError(f"JSON root must be an object: {path}")
    return payload, digest


def _load_csv_snapshot(path: Path) -> tuple[list[dict[str, str]], list[str], str]:
    text, digest = _read_text_snapshot(path)
    reader = csv.DictReader(io.StringIO(text))
    fieldnames = reader.fieldnames
    if not isinstance(fieldnames, list) or not fieldnames:
        raise PlanningAdapterError(f"CSV header is missing: {path}")
    if any(not isinstance(field, str) or not field.strip() for field in fieldnames):
        raise PlanningAdapterError(f"CSV contains an empty header field: {path}")
    if len(fieldnames) != len(set(fieldnames)):
        raise PlanningAdapterError(f"CSV contains duplicate header fields: {path}")
    rows = [dict(row) for row in reader]
    if not rows:
        raise PlanningAdapterError(f"CSV contains no data rows: {path}")
    return rows, fieldnames, digest


def _resolve_tracked_file(repository_root: Path, relative_path: Path) -> Path:
    root = repository_root.expanduser().resolve(strict=True)
    path = (root / relative_path).resolve(strict=True)
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise PlanningAdapterError(
            f"planning evidence escapes repository root: {relative_path}"
        ) from exc
    if not path.is_file():
        raise PlanningAdapterError(f"planning evidence is not a file: {path}")
    return path


def _binding(
    role: str,
    path: Path,
    repository_root: Path,
    *,
    snapshot_sha256: str | None = None,
) -> dict[str, str]:
    root = repository_root.expanduser().resolve(strict=True)
    resolved = path.resolve(strict=True)
    try:
        relative = resolved.relative_to(root).as_posix()
    except ValueError:
        relative = str(resolved)
    digest = snapshot_sha256
    if digest is None:
        digest = _sha256_bytes(resolved.read_bytes())
    return {"role": role, "path": relative, "sha256": digest}


def _decision(
    *,
    adapter_id: str,
    domain: str,
    selection_status: str,
    selected_action: object,
    candidates: list[dict[str, Any]],
    reason: str,
    evidence_level: str | None,
    maximum_allowed_use: str | None,
    evidence_bindings: list[dict[str, str]],
    delegated_policy_version: str | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": PLANNING_DECISION_SCHEMA_VERSION,
        "adapter_id": adapter_id,
        "adapter_version": PLANNING_ADAPTER_VERSION,
        "domain": domain,
        "selection_status": selection_status,
        "selected_action": selected_action,
        "candidates": candidates,
        "reason": reason,
        "evidence_level": evidence_level,
        "maximum_allowed_use": maximum_allowed_use,
        "evidence_bindings": evidence_bindings,
        "network_access_performed": False,
        "action_executed": False,
        "model_fit_performed": False,
        "scientific_evidence_upgraded": False,
        "delegated_policy_version": delegated_policy_version,
    }


def _plan_nasa(
    *,
    repository_root: Path,
    research_run: Path | None,
    action_registry_path: Path | None,
) -> dict[str, Any]:
    if research_run is None or action_registry_path is None:
        raise PlanningAdapterError(
            "nasa-battery planning requires both research_run and action_registry_path"
        )
    run_path = Path(research_run).expanduser().resolve(strict=True)
    state_before = load_research_state(run_path)
    ledger_sha_before = _nonempty_text(
        state_before.get("ledger_sha256"), "NASA research ledger SHA-256"
    )
    delegated = plan_nasa_next_action(
        run_path,
        action_registry_path,
        repository_root,
    )
    state_after = load_research_state(run_path)
    ledger_sha_after = _nonempty_text(
        state_after.get("ledger_sha256"), "NASA post-planning research ledger SHA-256"
    )
    if ledger_sha_after != ledger_sha_before:
        raise PlanningAdapterError(
            "NASA research ledger changed while the planning decision was being built"
        )
    if not isinstance(delegated, Mapping):
        raise PlanningAdapterError("NASA planner returned a non-object decision")
    status = delegated.get("selection_status")
    reason = delegated.get("reason")
    candidates = delegated.get("candidates")
    if not isinstance(status, str) or not status:
        raise PlanningAdapterError("NASA planner omitted selection_status")
    if not isinstance(reason, str) or not reason:
        raise PlanningAdapterError("NASA planner omitted reason")
    if not isinstance(candidates, list):
        raise PlanningAdapterError("NASA planner candidates must be a list")
    raw_evidence_level = delegated.get("latest_evidence_level")
    evidence_level = None
    if raw_evidence_level is not None:
        evidence_level = _nonempty_text(
            raw_evidence_level,
            "NASA planner latest_evidence_level",
        )
        if evidence_level not in _NASA_EVIDENCE_LEVELS:
            raise PlanningAdapterError(
                f"NASA planner returned unsupported evidence level: {evidence_level!r}"
            )
    selected_action = delegated.get("selected_action")
    registry_path = Path(action_registry_path).expanduser().resolve(strict=True)
    bindings = [_binding("action_registry", registry_path, repository_root)]
    state_path = run_path / "research_state.json"
    if state_path.is_file():
        bindings.append(_binding("research_state", state_path, repository_root))
    ledger_path = run_path / "research_ledger.jsonl"
    if ledger_path.is_file():
        bindings.append(
            _binding(
                "research_ledger",
                ledger_path,
                repository_root,
                snapshot_sha256=ledger_sha_before,
            )
        )
    objective_path = run_path / "research_objective.json"
    if objective_path.is_file():
        bindings.append(_binding("research_objective", objective_path, repository_root))
    return _decision(
        adapter_id=_NASA_ADAPTER,
        domain="battery_degradation",
        selection_status=status,
        selected_action=selected_action,
        candidates=[dict(item) for item in candidates if isinstance(item, Mapping)],
        reason=reason,
        evidence_level=evidence_level,
        maximum_allowed_use=None,
        evidence_bindings=bindings,
        delegated_policy_version=(
            str(delegated["policy_version"])
            if delegated.get("policy_version") is not None
            else None
        ),
    )


def _build_mp_screening_requirement(
    config: Mapping[str, Any], config_sha256: str
) -> dict[str, Any]:
    required = {
        "schema_version",
        "requirement_id",
        "domain",
        "objective",
        "scientific_evidence_level",
        "prohibited_source_systems",
        "required_metadata_checks",
        "required_semantic_checks",
        "domain_requirements",
        "scientific_boundary",
    }
    missing = sorted(required - set(config))
    if missing:
        raise PlanningAdapterError(
            f"Materials Project requirement config is missing fields: {missing}"
        )
    return {
        "schema_version": config["schema_version"],
        "requirement_id": config["requirement_id"],
        "domain": config["domain"],
        "objective": config["objective"],
        "scientific_evidence_level": config["scientific_evidence_level"],
        "source_independence_required": True,
        "prohibited_source_systems": config["prohibited_source_systems"],
        "required_metadata_checks": config["required_metadata_checks"],
        "required_semantic_checks": config["required_semantic_checks"],
        "domain_requirements": config["domain_requirements"],
        "automatic_acquisition_authorized": False,
        "model_fit_authorized": False,
        "external_validation_claim_authorized": False,
        "source_binding": {
            "planning_source": _MP_REQUIREMENT_CONFIG.as_posix(),
            "planning_source_sha256": config_sha256,
            "read_only_revalidation": True,
        },
        "scientific_boundary": config["scientific_boundary"],
    }


def _plan_materials_project(*, repository_root: Path) -> dict[str, Any]:
    requirement_path = _resolve_tracked_file(repository_root, _MP_REQUIREMENT_CONFIG)
    registry_path = _resolve_tracked_file(repository_root, _MP_CANDIDATE_REGISTRY)
    closeout_path = _resolve_tracked_file(repository_root, _MP_PLANNING_CLOSEOUT)
    requirement_config, requirement_sha = _load_json_snapshot(requirement_path)
    registry, registry_sha = _load_json_snapshot(registry_path)
    closeout, closeout_sha = _load_json_snapshot(closeout_path)

    if (
        closeout.get("schema_version") != "1.0"
        or closeout.get("closed_for_current_scope") is not True
    ):
        raise PlanningAdapterError("Materials Project planning closeout is not frozen closed")
    if closeout.get("evidence_level") != "Diagnostic":
        raise PlanningAdapterError("Materials Project frozen evidence level drifted")
    if closeout.get("requirement_id") != requirement_config.get("requirement_id"):
        raise PlanningAdapterError("Materials Project closeout requirement_id mismatch")
    if closeout.get("registry_id") != registry.get("registry_id"):
        raise PlanningAdapterError("Materials Project closeout registry_id mismatch")
    raw_candidates = registry.get("candidates")
    if not isinstance(raw_candidates, list) or not raw_candidates:
        raise PlanningAdapterError("Materials Project candidate registry is empty or malformed")

    candidate_ids: set[str] = set()
    screening_requirement = _build_mp_screening_requirement(
        requirement_config,
        requirement_sha,
    )
    assessments: list[dict[str, Any]] = []
    for raw_candidate in raw_candidates:
        if not isinstance(raw_candidate, Mapping):
            raise PlanningAdapterError("Materials Project candidate must be an object")
        candidate_id = _nonempty_text(
            raw_candidate.get("candidate_id"),
            "Materials Project candidate_id",
        )
        if candidate_id in candidate_ids:
            raise PlanningAdapterError(
                f"Materials Project candidate_id is duplicated: {candidate_id}"
            )
        candidate_ids.add(candidate_id)
        try:
            assessment = evaluate_external_source_candidate(
                screening_requirement,
                raw_candidate,
            )
        except ExternalEvidenceContractError as exc:
            raise PlanningAdapterError(
                f"Materials Project candidate contract revalidation failed: {exc}"
            ) from exc
        assessments.append(assessment.to_dict())

    disposition_counts: dict[str, int] = {}
    for assessment in assessments:
        disposition = str(assessment["disposition"])
        disposition_counts[disposition] = disposition_counts.get(disposition, 0) + 1
    eligible_count = sum(
        1 for assessment in assessments if assessment["eligible_for_requirement"]
    )
    expected_counts = closeout.get("expected_disposition_counts")
    if not isinstance(expected_counts, Mapping):
        raise PlanningAdapterError("Materials Project closeout lacks disposition counts")
    if eligible_count != closeout.get("expected_eligible_candidate_count"):
        raise PlanningAdapterError("Materials Project eligible-candidate count drifted")
    if dict(sorted(disposition_counts.items())) != dict(sorted(expected_counts.items())):
        raise PlanningAdapterError("Materials Project candidate dispositions drifted")
    if eligible_count != 0:
        raise PlanningAdapterError(
            "Materials Project now has an eligible candidate; frozen search closeout must be reviewed"
        )
    restart_criteria = closeout.get("restart_criteria")
    if not isinstance(restart_criteria, list) or not restart_criteria:
        raise PlanningAdapterError("Materials Project closeout lacks restart criteria")

    return _decision(
        adapter_id=_MATERIALS_PROJECT_ADAPTER,
        domain="materials_phase_stability",
        selection_status="no_positive_value_action",
        selected_action=None,
        candidates=[],
        reason=(
            f"The frozen source-disjoint search remains closed: all {len(raw_candidates)} tracked "
            "high-priority candidates revalidate as ineligible or diagnostic-only. Reopen only "
            "when genuinely new evidence directly addresses a recorded provenance or "
            "thermodynamic-semantics blocker."
        ),
        evidence_level="Diagnostic",
        maximum_allowed_use=None,
        evidence_bindings=[
            _binding(
                "external_evidence_requirement_config",
                requirement_path,
                repository_root,
                snapshot_sha256=requirement_sha,
            ),
            _binding(
                "external_source_candidate_registry",
                registry_path,
                repository_root,
                snapshot_sha256=registry_sha,
            ),
            _binding(
                "planning_closeout",
                closeout_path,
                repository_root,
                snapshot_sha256=closeout_sha,
            ),
        ],
    )


def _plan_tm_fe_si(*, repository_root: Path) -> dict[str, Any]:
    readiness_path = _resolve_tracked_file(repository_root, _TM_FE_SI_READINESS)
    payload, readiness_sha = _load_json_snapshot(readiness_path)
    if payload.get("schema_version") != "1.0":
        raise PlanningAdapterError("TM-Fe-Si readiness schema_version mismatch")
    if payload.get("case_id") != "tm_fe_si_characterization_consumer_readiness":
        raise PlanningAdapterError("TM-Fe-Si readiness case_id mismatch")
    producer = payload.get("producer")
    readiness = payload.get("readiness")
    closeout = payload.get("closeout")
    intent = payload.get("consumer_intent")
    if not all(
        isinstance(item, Mapping)
        for item in (producer, readiness, closeout, intent)
    ):
        raise PlanningAdapterError("TM-Fe-Si readiness sections are malformed")
    assert isinstance(producer, Mapping)
    assert isinstance(readiness, Mapping)
    assert isinstance(closeout, Mapping)
    assert isinstance(intent, Mapping)
    real_replay = producer.get("real_source_replay")
    if not isinstance(real_replay, Mapping):
        raise PlanningAdapterError("TM-Fe-Si producer real_source_replay is malformed")
    if real_replay.get("evidence_level") != "Diagnostic":
        raise PlanningAdapterError("TM-Fe-Si producer evidence level drifted")
    producer_maximum_use = real_replay.get("maximum_allowed_use")
    if producer_maximum_use != "descriptive":
        raise PlanningAdapterError("TM-Fe-Si producer maximum allowed use drifted")
    if readiness.get("cross_modal_descriptive_case_ready") is not True:
        raise PlanningAdapterError("TM-Fe-Si descriptive case is no longer ready")
    if readiness.get("predictive_negative_control_passed") is not True:
        raise PlanningAdapterError("TM-Fe-Si predictive negative control is not preserved")
    for field in (
        "predictive_case_ready",
        "causal_case_ready",
        "engineering_decision_ready",
    ):
        if readiness.get(field) is not False:
            raise PlanningAdapterError(f"TM-Fe-Si stronger-use boundary drifted: {field}")
    if closeout.get("evidence_level") != "Diagnostic":
        raise PlanningAdapterError("TM-Fe-Si evidence level drifted")
    if closeout.get("result") != "real_cross_repository_descriptive_case_complete":
        raise PlanningAdapterError("TM-Fe-Si closeout result drifted")
    if intent.get("requested_use") != "descriptive":
        raise PlanningAdapterError("TM-Fe-Si frozen requested use is not descriptive")
    if intent.get("descriptive_authorized") is not True:
        raise PlanningAdapterError("TM-Fe-Si descriptive use is no longer authorized")
    for field in (
        "association_authorized",
        "predictive_authorized",
        "causal_authorized",
        "engineering_authorized",
    ):
        if intent.get(field) is not False:
            raise PlanningAdapterError(f"TM-Fe-Si use boundary drifted: {field}")

    return _decision(
        adapter_id=_TM_FE_SI_ADAPTER,
        domain="cross_modal_materials_characterization",
        selection_status="no_positive_value_action",
        selected_action=None,
        candidates=[],
        reason=(
            "The real cross-repository descriptive case is complete at Diagnostic evidence. "
            "No additional TM-Fe-Si analysis is justified merely to expand scope; stronger use "
            "requires new independent evidence with exact lineage and hypothesis-relevant truth."
        ),
        evidence_level="Diagnostic",
        maximum_allowed_use=producer_maximum_use,
        evidence_bindings=[
            _binding(
                "consumer_readiness",
                readiness_path,
                repository_root,
                snapshot_sha256=readiness_sha,
            )
        ],
    )


def _required_csv_fields(
    fieldnames: list[str],
    required: set[str],
    *,
    label: str,
) -> None:
    missing = sorted(required - set(fieldnames))
    if missing:
        raise PlanningAdapterError(f"{label} CSV is missing fields: {missing}")


def _unique_sample_ids(rows: list[dict[str, str]], *, label: str) -> list[str]:
    sample_ids: list[str] = []
    seen: set[str] = set()
    for row in rows:
        sample_id = _nonempty_text(row.get("sample_id"), f"{label}.sample_id")
        if sample_id in seen:
            raise PlanningAdapterError(f"{label} contains duplicate sample_id: {sample_id}")
        seen.add(sample_id)
        sample_ids.append(sample_id)
    return sample_ids


def _validate_nist_case_tables(
    process_path: Path,
    measurement_path: Path,
    tracked: Mapping[str, Any],
) -> tuple[str, str]:
    process_rows, process_fields, process_sha = _load_csv_snapshot(process_path)
    measurement_rows, measurement_fields, measurement_sha = _load_csv_snapshot(
        measurement_path
    )
    _required_csv_fields(
        process_fields,
        {
            "sample_id",
            "case_id",
            "trace_number",
            "actual_laser_power_w",
            "scan_speed_mm_s",
            "system",
            "material",
        },
        label="NIST AM-Bench process",
    )
    _required_csv_fields(
        measurement_fields,
        {
            "sample_id",
            "case_id",
            "trace_number",
            "width_mean_um",
            "width_std_um",
            "depth_mean_um",
            "depth_std_um",
        },
        label="NIST AM-Bench measurement",
    )

    expected_trace_count = tracked.get("trace_count")
    if isinstance(expected_trace_count, bool) or not isinstance(expected_trace_count, int):
        raise PlanningAdapterError("NIST AM-Bench tracked trace_count is malformed")
    if expected_trace_count != 10:
        raise PlanningAdapterError("NIST AM-Bench frozen trace_count drifted")
    if len(process_rows) != expected_trace_count or len(measurement_rows) != expected_trace_count:
        raise PlanningAdapterError(
            "NIST AM-Bench actual table row counts do not match the frozen trace_count"
        )

    process_ids = _unique_sample_ids(process_rows, label="NIST AM-Bench process table")
    measurement_ids = _unique_sample_ids(
        measurement_rows,
        label="NIST AM-Bench measurement table",
    )
    if set(process_ids) != set(measurement_ids):
        raise PlanningAdapterError(
            "NIST AM-Bench process and measurement tables do not join one-to-one by sample_id"
        )

    expected_system = _nonempty_text(tracked.get("system"), "NIST AM-Bench tracked system")
    expected_material = _nonempty_text(
        tracked.get("material"),
        "NIST AM-Bench tracked material",
    )
    process_by_id: dict[str, dict[str, str]] = {}
    seen_traces: set[int] = set()
    conditions: set[tuple[float, float]] = set()
    for row in process_rows:
        sample_id = _nonempty_text(row.get("sample_id"), "NIST AM-Bench process sample_id")
        trace = _canonical_positive_int(
            row.get("trace_number"), "NIST AM-Bench process trace_number"
        )
        if trace in seen_traces or trace not in _NIST_EXPECTED_TRACES:
            raise PlanningAdapterError(
                f"NIST AM-Bench process trace identity drifted: {trace}"
            )
        seen_traces.add(trace)
        expected_case, expected_power, expected_speed = _NIST_EXPECTED_TRACES[trace]
        expected_sample_id = f"amb2018_02_ammt_trace_{trace:02d}"
        if sample_id != expected_sample_id or row.get("case_id") != expected_case:
            raise PlanningAdapterError(
                f"NIST AM-Bench frozen trace/case/sample identity drifted for trace {trace}"
            )
        if row.get("system") != expected_system or row.get("material") != expected_material:
            raise PlanningAdapterError(
                "NIST AM-Bench process table material/system drifted from the frozen case"
            )
        power = _finite_float(
            row.get("actual_laser_power_w"),
            "NIST AM-Bench actual_laser_power_w",
            positive=True,
        )
        speed = _finite_float(
            row.get("scan_speed_mm_s"),
            "NIST AM-Bench scan_speed_mm_s",
            positive=True,
        )
        if not math.isclose(power, expected_power, rel_tol=0.0, abs_tol=1e-9) or not math.isclose(
            speed, expected_speed, rel_tol=0.0, abs_tol=1e-9
        ):
            raise PlanningAdapterError(
                f"NIST AM-Bench frozen process condition drifted for trace {trace}"
            )
        conditions.add((power, speed))
        process_by_id[sample_id] = row

    if seen_traces != set(_NIST_EXPECTED_TRACES):
        raise PlanningAdapterError("NIST AM-Bench frozen trace sequence is incomplete")

    for row in measurement_rows:
        sample_id = _nonempty_text(
            row.get("sample_id"), "NIST AM-Bench measurement sample_id"
        )
        process_row = process_by_id.get(sample_id)
        if process_row is None:
            raise PlanningAdapterError(
                "NIST AM-Bench measurement row has no process-table identity match"
            )
        trace = _canonical_positive_int(
            row.get("trace_number"), "NIST AM-Bench measurement trace_number"
        )
        if str(trace) != process_row.get("trace_number") or row.get("case_id") != process_row.get(
            "case_id"
        ):
            raise PlanningAdapterError(
                "NIST AM-Bench process/measurement identity fields disagree for "
                f"sample_id={sample_id}"
            )
        _finite_float(
            row.get("width_mean_um"),
            "NIST AM-Bench width_mean_um",
            positive=True,
        )
        _finite_float(
            row.get("depth_mean_um"),
            "NIST AM-Bench depth_mean_um",
            positive=True,
        )
        _finite_float(
            row.get("width_std_um"),
            "NIST AM-Bench width_std_um",
            nonnegative=True,
        )
        _finite_float(
            row.get("depth_std_um"),
            "NIST AM-Bench depth_std_um",
            nonnegative=True,
        )

    expected_condition_count = tracked.get("unique_process_condition_count")
    if (
        isinstance(expected_condition_count, bool)
        or not isinstance(expected_condition_count, int)
        or expected_condition_count != 3
    ):
        raise PlanningAdapterError(
            "NIST AM-Bench frozen unique_process_condition_count drifted"
        )
    if len(conditions) != expected_condition_count:
        raise PlanningAdapterError(
            "NIST AM-Bench actual process-condition count does not match the frozen case"
        )
    return process_sha, measurement_sha


def _plan_nist_ambench(*, repository_root: Path) -> dict[str, Any]:
    readiness_path = _resolve_tracked_file(repository_root, _NIST_AMBENCH_READINESS)
    payload, readiness_sha = _load_json_snapshot(readiness_path)
    if payload.get("schema_version") != "1.0":
        raise PlanningAdapterError("NIST AM-Bench planning readiness schema_version mismatch")
    if payload.get("case_id") != "nist-ambench-2018-02-planning-readiness-v1":
        raise PlanningAdapterError("NIST AM-Bench planning readiness case_id mismatch")
    scope = payload.get("current_scope")
    tracked = payload.get("tracked_case")
    blocker = payload.get("current_blocker")
    requirements = payload.get("required_new_evidence")
    reopen = payload.get("reopen_conditions")
    if not all(isinstance(item, Mapping) for item in (scope, tracked, blocker)):
        raise PlanningAdapterError("NIST AM-Bench readiness sections are malformed")
    assert isinstance(scope, Mapping)
    assert isinstance(tracked, Mapping)
    assert isinstance(blocker, Mapping)
    blocker_summary = _nonempty_text(
        blocker.get("summary"),
        "NIST AM-Bench current_blocker.summary",
    )
    if scope.get("evidence_level") != "Diagnostic":
        raise PlanningAdapterError("NIST AM-Bench evidence level drifted")
    if scope.get("maximum_allowed_use") != "descriptive":
        raise PlanningAdapterError("NIST AM-Bench maximum use drifted")
    if scope.get("descriptive_case_complete") is not True:
        raise PlanningAdapterError("NIST AM-Bench descriptive closeout is no longer complete")
    for field in (
        "predictive_use_authorized",
        "causal_use_authorized",
        "engineering_use_authorized",
    ):
        if scope.get(field) is not False:
            raise PlanningAdapterError(f"NIST AM-Bench stronger-use boundary drifted: {field}")
    if tracked.get("trace_count") != 10 or tracked.get("unique_process_condition_count") != 3:
        raise PlanningAdapterError("NIST AM-Bench frozen case dimensions drifted")
    if not isinstance(requirements, list) or not requirements:
        raise PlanningAdapterError("NIST AM-Bench evidence requirements are missing")
    if not isinstance(reopen, list) or not reopen:
        raise PlanningAdapterError("NIST AM-Bench reopen conditions are missing")
    for field in (
        "automatic_acquisition_authorized",
        "automatic_experiment_control_authorized",
        "model_fit_authorized",
        "automatic_reopen_authorized",
        "scientific_evidence_upgrade_authorized",
    ):
        if payload.get(field) is not False:
            raise PlanningAdapterError(f"NIST AM-Bench safety boundary drifted: {field}")

    process_path = _resolve_tracked_file(repository_root, Path(str(tracked["process_table"])))
    measurement_path = _resolve_tracked_file(
        repository_root, Path(str(tracked["measurement_table"]))
    )
    readme_path = _resolve_tracked_file(repository_root, Path(str(tracked["case_readme"])))
    process_sha, measurement_sha = _validate_nist_case_tables(
        process_path,
        measurement_path,
        tracked,
    )
    return _decision(
        adapter_id=_NIST_AMBENCH_ADAPTER,
        domain=_nonempty_text(payload.get("domain"), "NIST AM-Bench domain"),
        selection_status="no_positive_value_action",
        selected_action=None,
        candidates=[],
        reason=blocker_summary,
        evidence_level="Diagnostic",
        maximum_allowed_use="descriptive",
        evidence_bindings=[
            _binding(
                "planning_readiness",
                readiness_path,
                repository_root,
                snapshot_sha256=readiness_sha,
            ),
            _binding(
                "source_process_conditions",
                process_path,
                repository_root,
                snapshot_sha256=process_sha,
            ),
            _binding(
                "source_melt_pool_measurements",
                measurement_path,
                repository_root,
                snapshot_sha256=measurement_sha,
            ),
            _binding("case_documentation", readme_path, repository_root),
        ],
    )


def plan_research_next_action(
    adapter_id: str,
    *,
    repository_root: str | Path,
    research_run: str | Path | None = None,
    action_registry_path: str | Path | None = None,
) -> dict[str, Any]:
    """Produce one read-only planning decision through a stable cross-domain interface."""
    if adapter_id not in _ADAPTER_IDS:
        raise PlanningAdapterError(
            f"unknown planning adapter {adapter_id!r}; expected one of {list(_ADAPTER_IDS)}"
        )
    root = Path(repository_root).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise PlanningAdapterError(f"repository_root is not a directory: {root}")
    if adapter_id == _NASA_ADAPTER:
        return _plan_nasa(
            repository_root=root,
            research_run=Path(research_run) if research_run is not None else None,
            action_registry_path=(
                Path(action_registry_path) if action_registry_path is not None else None
            ),
        )
    if research_run is not None or action_registry_path is not None:
        raise PlanningAdapterError(
            f"{adapter_id} uses tracked scientific closeout state and does not accept run/registry arguments"
        )
    if adapter_id == _MATERIALS_PROJECT_ADAPTER:
        return _plan_materials_project(repository_root=root)
    if adapter_id == _TM_FE_SI_ADAPTER:
        return _plan_tm_fe_si(repository_root=root)
    return _plan_nist_ambench(repository_root=root)


__all__ = [
    "PLANNING_ADAPTER_VERSION",
    "PLANNING_DECISION_SCHEMA_VERSION",
    "PlanningAdapterError",
    "available_planning_adapters",
    "plan_research_next_action",
]
