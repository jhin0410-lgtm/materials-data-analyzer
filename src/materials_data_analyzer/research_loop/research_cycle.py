"""Single-step orchestration for the bounded materials research loop.

A cycle plans, projects state, classifies the transition, checks authorization,
and optionally executes exactly one explicit typed action before rebuilding state
and replanning once. It never loops automatically and never creates an execution
request on behalf of the caller.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .action_authorization import assess_action_authorization
from .authorized_execution import execute_authorized_action
from .kernel import ResearchLoopError
from .planning_state import build_research_planning_state
from .planning_transition import determine_research_transition

CYCLE_SCHEMA_VERSION = "1.0"
CYCLE_POLICY_VERSION = "1.0"


class ResearchCycleError(ResearchLoopError):
    """Raised when a bounded research cycle violates its one-step contract."""


def _base_result(
    *,
    adapter_id: str,
    before_state: Mapping[str, Any],
    before_transition: Mapping[str, Any],
    request_supplied: bool,
) -> dict[str, Any]:
    return {
        "schema_version": CYCLE_SCHEMA_VERSION,
        "cycle_policy_version": CYCLE_POLICY_VERSION,
        "adapter_id": adapter_id,
        "cycle_status": None,
        "before_planning_state": dict(before_state),
        "before_transition": dict(before_transition),
        "authorization": None,
        "execution": None,
        "after_planning_state": None,
        "after_transition": None,
        "request_supplied": request_supplied,
        "request_unused": False,
        "actions_executed": 0,
        "maximum_actions_executed_per_cycle": 1,
        "automatic_looping_available": False,
        "automatic_request_generation_available": False,
        "generic_command_execution_available": False,
        "network_access_initiated_by_cycle_orchestrator": False,
        "model_fit_initiated_by_cycle_orchestrator": False,
        "scientific_evidence_upgraded_by_cycle_orchestrator": False,
    }


def run_research_cycle(
    adapter_id: str,
    *,
    repository_root: str | Path,
    research_run: str | Path | None = None,
    action_registry_path: str | Path | None = None,
    request_path: str | Path | None = None,
) -> dict[str, Any]:
    """Run at most one explicit typed action and then replan exactly once."""
    root = Path(repository_root).expanduser().resolve(strict=True)
    before_state = build_research_planning_state(
        adapter_id,
        repository_root=root,
        research_run=research_run,
        action_registry_path=action_registry_path,
    )
    before_transition = determine_research_transition(before_state)
    result = _base_result(
        adapter_id=adapter_id,
        before_state=before_state,
        before_transition=before_transition,
        request_supplied=request_path is not None,
    )

    transition_type = before_transition.get("transition_type")
    if transition_type == "stop_current_scope":
        result["cycle_status"] = "stopped_current_scope"
        result["request_unused"] = request_path is not None
        return result
    if transition_type == "manual_review_required":
        result["cycle_status"] = "manual_review_required"
        result["request_unused"] = request_path is not None
        return result
    if transition_type == "blocked":
        result["cycle_status"] = "blocked"
        result["request_unused"] = request_path is not None
        return result
    if transition_type not in {
        "action_pending_authorization",
        "evidence_requirement_pending_authorization",
    }:
        raise ResearchCycleError(
            f"unsupported authorizable transition type: {transition_type!r}"
        )

    authorization = assess_action_authorization(
        before_state,
        repository_root=root,
    )
    result["authorization"] = authorization
    if authorization.get("authorization_status") != (
        "ready_for_explicit_execution_request"
    ):
        result["cycle_status"] = "authorization_denied"
        result["request_unused"] = request_path is not None
        return result

    if request_path is None:
        result["cycle_status"] = "explicit_request_required"
        return result
    if research_run is None or action_registry_path is None:
        raise ResearchCycleError(
            "authorized execution requires research_run and action_registry_path"
        )

    execution = execute_authorized_action(
        adapter_id,
        repository_root=root,
        research_run=research_run,
        action_registry_path=action_registry_path,
        request_path=request_path,
    )
    if not isinstance(execution, Mapping):
        raise ResearchCycleError("authorized executor returned a malformed result")
    result["execution"] = dict(execution)
    result["actions_executed"] = 1

    after_state = build_research_planning_state(
        adapter_id,
        repository_root=root,
        research_run=research_run,
        action_registry_path=action_registry_path,
    )
    after_transition = determine_research_transition(after_state)
    result["after_planning_state"] = after_state
    result["after_transition"] = after_transition
    result["cycle_status"] = "one_action_executed"
    return result


__all__ = [
    "CYCLE_POLICY_VERSION",
    "CYCLE_SCHEMA_VERSION",
    "ResearchCycleError",
    "run_research_cycle",
]
