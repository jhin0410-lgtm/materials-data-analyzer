"""Fail-closed transitions derived from domain-general research planning state.

Transitions classify what kind of continuation is justified by the current state.
They never execute actions or automatically reopen a terminal scientific scope.
Reopen evidence is checksum-bound to a frozen condition and routed to manual
semantic review only.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping

from .kernel import ResearchLoopError
from .planning_state import build_research_planning_state

TRANSITION_SCHEMA_VERSION = "1.0"
TRANSITION_POLICY_VERSION = "1.0"


class PlanningTransitionError(ResearchLoopError):
    """Raised when planning state cannot support a defensible transition."""


def _nonempty_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PlanningTransitionError(f"{field} must be a non-empty string")
    return value.strip()


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PlanningTransitionError(f"{field} must be an object")
    return value


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _transition_base(state: Mapping[str, Any]) -> dict[str, Any]:
    stop_state = _mapping(state.get("stop_state"), "planning_state.stop_state")
    evidence_gap = _mapping(state.get("evidence_gap"), "planning_state.evidence_gap")
    stop_status = _nonempty_text(stop_state.get("status"), "planning_state.stop_state.status")
    selection_status = _nonempty_text(
        stop_state.get("selection_status"), "planning_state.stop_state.selection_status"
    )
    reason = _nonempty_text(stop_state.get("reason"), "planning_state.stop_state.reason")
    adapter_id = _nonempty_text(state.get("adapter_id"), "planning_state.adapter_id")
    domain = _nonempty_text(state.get("domain"), "planning_state.domain")
    return {
        "schema_version": TRANSITION_SCHEMA_VERSION,
        "transition_policy_version": TRANSITION_POLICY_VERSION,
        "adapter_id": adapter_id,
        "domain": domain,
        "planning_stop_status": stop_status,
        "planning_selection_status": selection_status,
        "evidence_gap_status": evidence_gap.get("status"),
        "transition_type": None,
        "selected_action": state.get("selected_action"),
        "reason": reason,
        "automatic_execution_authorized": False,
        "automatic_reopen_authorized": False,
        "network_access_performed": False,
        "action_executed": False,
        "model_fit_performed": False,
        "scientific_evidence_upgraded": False,
    }


def determine_research_transition(state: Mapping[str, Any]) -> dict[str, Any]:
    """Classify the next control transition without executing or reopening anything."""
    result = _transition_base(state)
    stop_status = result["planning_stop_status"]
    selected_action = state.get("selected_action")
    evidence_gap = _mapping(state.get("evidence_gap"), "planning_state.evidence_gap")

    if stop_status == "continue":
        if not isinstance(selected_action, Mapping):
            result["transition_type"] = "manual_review_required"
            result["reason"] = (
                "Planning state is active but has no bounded selected action; fail closed to "
                "manual review instead of inventing an action."
            )
        elif evidence_gap.get("status") == "requirement_definition_needed":
            result["transition_type"] = "evidence_requirement_pending_authorization"
        else:
            result["transition_type"] = "action_pending_authorization"
    elif stop_status == "manual_review_gate":
        result["transition_type"] = "manual_review_required"
    elif stop_status == "operationally_blocked":
        result["transition_type"] = "blocked"
    elif stop_status == "terminal_for_current_scope":
        result["transition_type"] = "stop_current_scope"
        result["selected_action"] = None
    else:
        raise PlanningTransitionError(f"unsupported planning stop status: {stop_status!r}")
    return result


def build_current_research_transition(
    adapter_id: str,
    *,
    repository_root: str | Path,
    research_run: str | Path | None = None,
    action_registry_path: str | Path | None = None,
) -> dict[str, Any]:
    """Build current planning state and derive its fail-closed transition."""
    state = build_research_planning_state(
        adapter_id,
        repository_root=repository_root,
        research_run=research_run,
        action_registry_path=action_registry_path,
    )
    return determine_research_transition(state)


def prepare_reopen_evidence_review(
    state: Mapping[str, Any],
    *,
    condition_index: int,
    evidence_path: str | Path,
) -> dict[str, Any]:
    """Bind new evidence to one frozen reopen condition without claiming it satisfies it."""
    stop_state = _mapping(state.get("stop_state"), "planning_state.stop_state")
    if stop_state.get("status") != "terminal_for_current_scope":
        raise PlanningTransitionError(
            "reopen evidence review is only valid for terminal_for_current_scope state"
        )
    conditions = stop_state.get("reopen_conditions")
    if not isinstance(conditions, list) or not conditions:
        raise PlanningTransitionError("terminal planning state has no reopen conditions")
    if isinstance(condition_index, bool) or not isinstance(condition_index, int):
        raise PlanningTransitionError("condition_index must be an integer")
    if condition_index < 0 or condition_index >= len(conditions):
        raise PlanningTransitionError(
            f"condition_index out of range: {condition_index}; available=0..{len(conditions) - 1}"
        )
    condition = _nonempty_text(conditions[condition_index], "reopen condition")
    path = Path(evidence_path).expanduser().resolve(strict=True)
    if not path.is_file():
        raise PlanningTransitionError(f"reopen evidence must be a file: {path}")
    if path.stat().st_size <= 0:
        raise PlanningTransitionError("reopen evidence file must not be empty")

    return {
        "schema_version": TRANSITION_SCHEMA_VERSION,
        "transition_policy_version": TRANSITION_POLICY_VERSION,
        "adapter_id": _nonempty_text(state.get("adapter_id"), "planning_state.adapter_id"),
        "domain": _nonempty_text(state.get("domain"), "planning_state.domain"),
        "review_status": "manual_semantic_review_required",
        "requested_transition": "reopen_current_scope",
        "condition_index": condition_index,
        "reopen_condition": condition,
        "evidence_binding": {
            "path": str(path),
            "sha256": _sha256_file(path),
            "size_bytes": path.stat().st_size,
        },
        "condition_satisfaction_established": False,
        "scientific_comparability_established": False,
        "automatic_reopen_authorized": False,
        "automatic_execution_authorized": False,
        "network_access_performed": False,
        "model_fit_performed": False,
        "scientific_evidence_upgraded": False,
        "next_transition": "manual_review_required",
        "scientific_boundary": (
            "Checksum binding proves only which file was submitted against which frozen reopen "
            "condition. It does not establish semantic relevance, provenance adequacy, source "
            "independence, comparability, scientific validity, or satisfaction of the condition."
        ),
    }


def build_reopen_evidence_review(
    adapter_id: str,
    *,
    repository_root: str | Path,
    condition_index: int,
    evidence_path: str | Path,
    research_run: str | Path | None = None,
    action_registry_path: str | Path | None = None,
) -> dict[str, Any]:
    """Build current planning state and bind evidence for a manual reopen review."""
    state = build_research_planning_state(
        adapter_id,
        repository_root=repository_root,
        research_run=research_run,
        action_registry_path=action_registry_path,
    )
    return prepare_reopen_evidence_review(
        state,
        condition_index=condition_index,
        evidence_path=evidence_path,
    )


__all__ = [
    "TRANSITION_POLICY_VERSION",
    "TRANSITION_SCHEMA_VERSION",
    "PlanningTransitionError",
    "build_current_research_transition",
    "build_reopen_evidence_review",
    "determine_research_transition",
    "prepare_reopen_evidence_review",
]
