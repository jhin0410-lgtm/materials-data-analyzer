"""Read-only adapters for a common bounded research-planning surface.

The adapters in this module do not execute actions, search the network, acquire
new data, fit models, or upgrade scientific evidence. They translate existing,
domain-specific scientific state into one stable planning-decision shape while
leaving each domain's actual scientific rules in its existing implementation.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .external_evidence_contract import (
    ExternalEvidenceContractError,
    evaluate_external_source_candidate,
)
from .kernel import ResearchLoopError
from .nasa_action_policy import plan_nasa_next_action

PLANNING_DECISION_SCHEMA_VERSION = "1.0"
PLANNING_ADAPTER_VERSION = "1.1"

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


def _load_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle, object_pairs_hook=_reject_duplicate_pairs)
    except json.JSONDecodeError as exc:
        raise PlanningAdapterError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise PlanningAdapterError(f"JSON root must be an object: {path}")
    return payload


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def _binding(role: str, path: Path, repository_root: Path) -> dict[str, str]:
    root = repository_root.expanduser().resolve(strict=True)
    resolved = path.resolve(strict=True)
    try:
        relative = resolved.relative_to(root).as_posix()
    except ValueError:
        relative = str(resolved)
    return {"role": role, "path": relative, "sha256": _sha256_file(resolved)}


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
    delegated = plan_nasa_next_action(
        research_run,
        action_registry_path,
        repository_root,
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
    selected_action = delegated.get("selected_action")
    run_path = Path(research_run).expanduser().resolve(strict=True)
    registry_path = Path(action_registry_path).expanduser().resolve(strict=True)
    bindings = [_binding("action_registry", registry_path, repository_root)]
    for role, path in (
        ("research_state", run_path / "research_state.json"),
        ("research_ledger", run_path / "research_ledger.jsonl"),
        ("research_objective", run_path / "research_objective.json"),
    ):
        if path.is_file():
            bindings.append(_binding(role, path, repository_root))
    return _decision(
        adapter_id=_NASA_ADAPTER,
        domain="battery_degradation",
        selection_status=status,
        selected_action=selected_action,
        candidates=[dict(item) for item in candidates if isinstance(item, Mapping)],
        reason=reason,
        evidence_level=None,
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
    requirement_config = _load_json(requirement_path)
    registry = _load_json(registry_path)
    closeout = _load_json(closeout_path)

    if (
        closeout.get("schema_version") != "1.0"
        or closeout.get("closed_for_current_scope") is not True
    ):
        raise PlanningAdapterError("Materials Project planning closeout is not frozen closed")
    if closeout.get("requirement_id") != requirement_config.get("requirement_id"):
        raise PlanningAdapterError("Materials Project closeout requirement_id mismatch")
    if closeout.get("registry_id") != registry.get("registry_id"):
        raise PlanningAdapterError("Materials Project closeout registry_id mismatch")
    raw_candidates = registry.get("candidates")
    if not isinstance(raw_candidates, list) or not raw_candidates:
        raise PlanningAdapterError("Materials Project candidate registry is empty or malformed")

    screening_requirement = _build_mp_screening_requirement(
        requirement_config,
        _sha256_file(requirement_path),
    )
    assessments: list[dict[str, Any]] = []
    for raw_candidate in raw_candidates:
        if not isinstance(raw_candidate, Mapping):
            raise PlanningAdapterError("Materials Project candidate must be an object")
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
            "The frozen source-disjoint search remains closed: all four tracked high-priority "
            "candidates revalidate as ineligible or diagnostic-only. Reopen only when genuinely "
            "new evidence directly addresses a recorded provenance or thermodynamic-semantics blocker."
        ),
        evidence_level=str(closeout.get("evidence_level", "Diagnostic")),
        maximum_allowed_use=None,
        evidence_bindings=[
            _binding(
                "external_evidence_requirement_config",
                requirement_path,
                repository_root,
            ),
            _binding("external_source_candidate_registry", registry_path, repository_root),
            _binding("planning_closeout", closeout_path, repository_root),
        ],
    )


def _plan_tm_fe_si(*, repository_root: Path) -> dict[str, Any]:
    readiness_path = _resolve_tracked_file(repository_root, _TM_FE_SI_READINESS)
    payload = _load_json(readiness_path)
    if payload.get("schema_version") != "1.0":
        raise PlanningAdapterError("TM-Fe-Si readiness schema_version mismatch")
    if payload.get("case_id") != "tm_fe_si_characterization_consumer_readiness":
        raise PlanningAdapterError("TM-Fe-Si readiness case_id mismatch")
    readiness = payload.get("readiness")
    closeout = payload.get("closeout")
    intent = payload.get("consumer_intent")
    if not all(isinstance(item, Mapping) for item in (readiness, closeout, intent)):
        raise PlanningAdapterError("TM-Fe-Si readiness sections are malformed")
    assert isinstance(readiness, Mapping)
    assert isinstance(closeout, Mapping)
    assert isinstance(intent, Mapping)
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
        maximum_allowed_use="descriptive",
        evidence_bindings=[_binding("consumer_readiness", readiness_path, repository_root)],
    )


def _plan_nist_ambench(*, repository_root: Path) -> dict[str, Any]:
    readiness_path = _resolve_tracked_file(repository_root, _NIST_AMBENCH_READINESS)
    payload = _load_json(readiness_path)
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
    return _decision(
        adapter_id=_NIST_AMBENCH_ADAPTER,
        domain=str(payload.get("domain")),
        selection_status="no_positive_value_action",
        selected_action=None,
        candidates=[],
        reason=str(blocker.get("summary")),
        evidence_level="Diagnostic",
        maximum_allowed_use="descriptive",
        evidence_bindings=[
            _binding("planning_readiness", readiness_path, repository_root),
            _binding("source_process_conditions", process_path, repository_root),
            _binding("source_melt_pool_measurements", measurement_path, repository_root),
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
