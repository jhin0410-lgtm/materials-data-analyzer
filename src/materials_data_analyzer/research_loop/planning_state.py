"""Domain-general read-only research planning-state projection.

This module projects verified domain decisions and existing tracked evidence into
one bounded research-state shape. It does not execute actions, search the network,
acquire data, fit models, quantify information gain, or upgrade scientific
evidence.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .kernel import ResearchLoopError, load_research_state
from .planning_adapter import plan_research_next_action

PLANNING_STATE_SCHEMA_VERSION = "1.0"
PLANNING_STATE_VERSION = "1.1"

_NASA_ADAPTER = "nasa-battery"
_MATERIALS_PROJECT_ADAPTER = "materials-project-external-source"
_TM_FE_SI_ADAPTER = "tm-fe-si-descriptive"

_MP_REQUIREMENT_CONFIG = Path(
    "configs/research/materials_project_external_evidence_requirement.v1.json"
)
_MP_PLANNING_CLOSEOUT = Path(
    "configs/research/materials_project_external_source_search_planning_closeout.v1.json"
)
_TM_FE_SI_READINESS = Path(
    "configs/research/tm_fe_si_characterization_consumer_readiness.v1.json"
)


class PlanningStateError(ResearchLoopError):
    """Raised when a verified planning decision cannot form a defensible state."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PlanningStateError(f"duplicate JSON key is not allowed: {key}")
        result[key] = value
    return result


def _load_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle, object_pairs_hook=_reject_duplicate_pairs)
    except json.JSONDecodeError as exc:
        raise PlanningStateError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise PlanningStateError(f"JSON root must be an object: {path}")
    return payload


def _resolve_repository_file(repository_root: Path, relative_path: Path) -> Path:
    root = repository_root.expanduser().resolve(strict=True)
    path = (root / relative_path).resolve(strict=True)
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise PlanningStateError(
            f"planning-state evidence escapes repository root: {relative_path}"
        ) from exc
    if not path.is_file():
        raise PlanningStateError(f"planning-state evidence is not a file: {path}")
    return path


def _nonempty_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PlanningStateError(f"{field} must be a non-empty string")
    return value.strip()


def _optional_text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _string_list(value: object, field: str, *, allow_empty: bool = True) -> list[str]:
    if not isinstance(value, list):
        raise PlanningStateError(f"{field} must be a list")
    if not allow_empty and not value:
        raise PlanningStateError(f"{field} must not be empty")
    result: list[str] = []
    for item in value:
        text = _nonempty_text(item, f"{field} item")
        if text in result:
            raise PlanningStateError(f"{field} must not contain duplicates")
        result.append(text)
    return result


def _normalize_action(candidate: Mapping[str, Any]) -> dict[str, Any]:
    action_type = _nonempty_text(candidate.get("action_type"), "candidate.action_type")
    availability = candidate.get("availability")
    cost_units = candidate.get("cost_units")
    priority_score = candidate.get("score")
    trigger = candidate.get("trigger")
    rationale = candidate.get("rationale")
    if not isinstance(availability, str) or not availability:
        availability = "unknown"
    if isinstance(cost_units, bool) or not isinstance(cost_units, int):
        cost_units = None
    if isinstance(priority_score, bool) or not isinstance(priority_score, int):
        priority_score = None
    return {
        "action_type": action_type,
        "action_version": _optional_text(candidate.get("action_version")),
        "availability": availability,
        "cost_units": cost_units,
        "priority_score": priority_score,
        "trigger": trigger if isinstance(trigger, str) and trigger else None,
        "rationale": rationale if isinstance(rationale, str) and rationale else None,
        "execution_registry_id": _optional_text(candidate.get("execution_registry_id")),
        "execution_registry_sha256": _optional_text(
            candidate.get("execution_registry_sha256")
        ),
        "execution_registry_path": _optional_text(candidate.get("execution_registry_path")),
        "expected_information_gain": {
            "status": "not_quantified",
            "value": None,
            "unit": None,
            "boundary": (
                "Policy priority scores are not information-gain estimates and must not be "
                "relabelled as expected scientific value."
            ),
        },
    }


def _stop_state(selection_status: str, reason: str) -> dict[str, Any]:
    if selection_status in {"no_positive_value_action", "research_stopped"}:
        status = "terminal_for_current_scope"
    elif selection_status == "manual_review_required":
        status = "manual_review_gate"
    elif selection_status in {"blocked_by_budget", "blocked_unimplemented_action"}:
        status = "operationally_blocked"
    else:
        status = "continue"
    return {
        "status": status,
        "selection_status": selection_status,
        "reason": reason,
        "reopen_conditions": [],
    }


def _base_state(decision: Mapping[str, Any]) -> dict[str, Any]:
    adapter_id = _nonempty_text(decision.get("adapter_id"), "decision.adapter_id")
    domain = _nonempty_text(decision.get("domain"), "decision.domain")
    selection_status = _nonempty_text(
        decision.get("selection_status"), "decision.selection_status"
    )
    reason = _nonempty_text(decision.get("reason"), "decision.reason")
    raw_candidates = decision.get("candidates")
    if not isinstance(raw_candidates, list):
        raise PlanningStateError("decision.candidates must be a list")
    actions: list[dict[str, Any]] = []
    for candidate in raw_candidates:
        if not isinstance(candidate, Mapping):
            raise PlanningStateError("decision candidate must be an object")
        actions.append(_normalize_action(candidate))
    selected = decision.get("selected_action")
    normalized_selected = None
    if selected is not None:
        if not isinstance(selected, Mapping):
            raise PlanningStateError("decision.selected_action must be an object or null")
        normalized_selected = _normalize_action(selected)
    evidence_bindings = decision.get("evidence_bindings")
    if not isinstance(evidence_bindings, list):
        raise PlanningStateError("decision.evidence_bindings must be a list")
    return {
        "schema_version": PLANNING_STATE_SCHEMA_VERSION,
        "planning_state_version": PLANNING_STATE_VERSION,
        "adapter_id": adapter_id,
        "domain": domain,
        "research_question": None,
        "claim_boundary": {
            "evidence_level": decision.get("evidence_level"),
            "maximum_allowed_use": decision.get("maximum_allowed_use"),
        },
        "current_blocker": {
            "kind": "not_classified",
            "code": selection_status,
            "summary": reason,
        },
        "evidence_gap": {
            "status": "not_classified",
            "requirements": [],
        },
        "action_frontier": actions,
        "selected_action": normalized_selected,
        "budget": None,
        "constraints": [],
        "stop_rules": [],
        "stop_state": _stop_state(selection_status, reason),
        "evidence_bindings": evidence_bindings,
        "network_access_performed": False,
        "action_executed": False,
        "model_fit_performed": False,
        "scientific_evidence_upgraded": False,
    }


def _project_nasa(
    state: dict[str, Any],
    *,
    research_run: Path,
) -> None:
    research = load_research_state(research_run)
    state["research_question"] = _nonempty_text(research.get("question"), "research.question")
    constraints = research.get("constraints")
    stop_rules = research.get("stop_rules")
    budget = research.get("budget")
    if not isinstance(constraints, list) or not isinstance(stop_rules, list):
        raise PlanningStateError("NASA research constraints/stop_rules are malformed")
    if not isinstance(budget, Mapping):
        raise PlanningStateError("NASA research budget is malformed")
    state["constraints"] = _string_list(constraints, "research.constraints")
    state["stop_rules"] = _string_list(stop_rules, "research.stop_rules")
    state["budget"] = dict(budget)

    selection_status = str(state["stop_state"]["selection_status"])
    selected = state["selected_action"]
    if selection_status == "ready_to_execute" and isinstance(selected, Mapping):
        state["current_blocker"] = {
            "kind": "scientific_or_evidence_blocker",
            "code": selected.get("trigger") or "selected_action_ready",
            "summary": selected.get("rationale") or state["stop_state"]["reason"],
        }
        if selected.get("action_type") == "external_data_requirement_generation":
            state["evidence_gap"] = {
                "status": "requirement_definition_needed",
                "requirements": [
                    "Define the minimum missing external evidence before any source search or acquisition."
                ],
            }
        else:
            state["evidence_gap"] = {
                "status": "action_expected_to_reduce_uncertainty",
                "requirements": [],
            }
    elif selection_status == "manual_review_required":
        state["current_blocker"]["kind"] = "semantic_or_failed_action_review"
        state["evidence_gap"] = {
            "status": "manual_review_required",
            "requirements": [],
        }
    elif selection_status == "blocked_by_budget":
        state["current_blocker"]["kind"] = "budget"
        state["evidence_gap"] = {"status": "not_applicable", "requirements": []}
    elif selection_status == "blocked_unimplemented_action":
        state["current_blocker"]["kind"] = "implementation"
        state["evidence_gap"] = {"status": "implementation_required", "requirements": []}
    elif selection_status in {"no_positive_value_action", "research_stopped"}:
        state["current_blocker"]["kind"] = "terminal_scope"
        state["evidence_gap"] = {"status": "no_current_positive_value_gap", "requirements": []}
        if research.get("stop"):
            state["stop_state"]["reopen_conditions"] = [
                "Open a new versioned research objective if materially new evidence changes the stopped scope."
            ]
    else:
        state["evidence_gap"] = {"status": "undetermined", "requirements": []}


def _project_materials_project(state: dict[str, Any], repository_root: Path) -> None:
    requirement = _load_json(
        _resolve_repository_file(repository_root, _MP_REQUIREMENT_CONFIG)
    )
    closeout = _load_json(_resolve_repository_file(repository_root, _MP_PLANNING_CLOSEOUT))
    state["research_question"] = _nonempty_text(
        requirement.get("objective"), "materials_project.objective"
    )
    state["current_blocker"] = {
        "kind": "external_evidence_compatibility",
        "code": "independence_and_target_semantics_not_jointly_satisfied",
        "summary": (
            "No tracked high-priority source simultaneously satisfies source independence and "
            "the frozen Materials Project thermodynamic target semantics."
        ),
    }
    restart = _string_list(
        closeout.get("restart_criteria"),
        "materials_project.restart_criteria",
        allow_empty=False,
    )
    state["evidence_gap"] = {
        "status": "unsatisfied_external_evidence_requirement",
        "requirements": restart,
    }
    state["stop_state"]["reopen_conditions"] = restart


def _project_tm_fe_si(state: dict[str, Any], repository_root: Path) -> None:
    payload = _load_json(_resolve_repository_file(repository_root, _TM_FE_SI_READINESS))
    closeout = payload.get("closeout")
    if not isinstance(closeout, Mapping):
        raise PlanningStateError("TM-Fe-Si closeout is malformed")
    next_requirements = _string_list(
        payload.get("next_requirements"),
        "tm_fe_si.next_requirements",
        allow_empty=False,
    )
    state["research_question"] = (
        "Can checksum-bound XRD characterization evidence and public 300 K M-H traces be "
        "joined and consumed defensibly for the frozen TM-Fe-Si descriptive cross-modal case?"
    )
    state["current_blocker"] = {
        "kind": "stronger_claim_evidence_limit",
        "code": "descriptive_case_complete_stronger_use_not_supported",
        "summary": _nonempty_text(closeout.get("primary_limitation"), "tm_fe_si.primary_limitation"),
    }
    stronger_requirements = [
        item
        for item in next_requirements
        if "stronger scientific claim" in item.lower()
        or "predictive" in item.lower()
        or "exact" in item.lower()
    ]
    if not stronger_requirements:
        stronger_requirements = next_requirements
    state["evidence_gap"] = {
        "status": "current_descriptive_scope_complete_stronger_use_unsatisfied",
        "requirements": stronger_requirements,
    }
    state["stop_state"]["reopen_conditions"] = stronger_requirements


def build_research_planning_state(
    adapter_id: str,
    *,
    repository_root: str | Path,
    research_run: str | Path | None = None,
    action_registry_path: str | Path | None = None,
) -> dict[str, Any]:
    """Build a read-only domain-general planning state from verified current evidence."""
    root = Path(repository_root).expanduser().resolve(strict=True)
    decision = plan_research_next_action(
        adapter_id,
        repository_root=root,
        research_run=research_run,
        action_registry_path=action_registry_path,
    )
    state = _base_state(decision)
    if adapter_id == _NASA_ADAPTER:
        if research_run is None:
            raise PlanningStateError("nasa-battery planning state requires research_run")
        _project_nasa(state, research_run=Path(research_run).expanduser().resolve(strict=True))
    elif adapter_id == _MATERIALS_PROJECT_ADAPTER:
        _project_materials_project(state, root)
    elif adapter_id == _TM_FE_SI_ADAPTER:
        _project_tm_fe_si(state, root)
    else:
        raise PlanningStateError(f"unsupported planning-state adapter: {adapter_id!r}")
    return state


__all__ = [
    "PLANNING_STATE_SCHEMA_VERSION",
    "PLANNING_STATE_VERSION",
    "PlanningStateError",
    "build_research_planning_state",
]
