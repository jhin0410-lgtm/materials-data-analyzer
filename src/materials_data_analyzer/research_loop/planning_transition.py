"""Fail-closed transitions derived from domain-general research planning state.

Transitions classify what kind of continuation is justified by the current state.
They never execute actions or automatically reopen a terminal scientific scope.
Reopen evidence is checksum-bound to a frozen condition and routed to manual
semantic review only.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any, Mapping

from .kernel import ResearchLoopError
from .planning_state import build_research_planning_state

TRANSITION_SCHEMA_VERSION = "1.0"
TRANSITION_POLICY_VERSION = "1.1"


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


def _evidence_bindings(value: object) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise PlanningTransitionError("planning_state.evidence_bindings must be a list")
    bindings: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise PlanningTransitionError(
                f"planning_state.evidence_bindings[{index}] must be an object"
            )
        bindings.append(dict(item))
    return bindings


def _stable_file_snapshot(path: Path) -> tuple[bytes, os.stat_result]:
    """Read one stable file snapshot and reject metadata changes during the read."""
    try:
        with path.open("rb") as handle:
            before = os.fstat(handle.fileno())
            data = handle.read()
            after = os.fstat(handle.fileno())
    except OSError as exc:
        raise PlanningTransitionError(f"failed to read reopen evidence: {path}") from exc
    try:
        path_after = path.stat()
    except OSError as exc:
        raise PlanningTransitionError(
            "reopen evidence changed or disappeared while it was being bound"
        ) from exc
    stable_fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns")
    if any(getattr(before, field) != getattr(after, field) for field in stable_fields):
        raise PlanningTransitionError(
            "reopen evidence metadata changed while the file was being read"
        )
    if any(getattr(after, field) != getattr(path_after, field) for field in stable_fields):
        raise PlanningTransitionError(
            "reopen evidence path changed after the file snapshot was read"
        )
    if len(data) != after.st_size:
        raise PlanningTransitionError(
            "reopen evidence size does not match the bytes read from the stable snapshot"
        )
    return data, after


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
    bindings = _evidence_bindings(state.get("evidence_bindings"))
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
        "planning_evidence_bindings": bindings,
        "reason": reason,
        "automatic_execution_authorized": False,
        "automatic_reopen_authorized": False,
        "network_access_performed": False,
        "action_executed": False,
        "model_fit_performed": False,
        "scientific_evidence_upgraded": False,
    }


def _selected_action_is_bounded(selected_action: object) -> bool:
    if not isinstance(selected_action, Mapping):
        return False
    action_type = selected_action.get("action_type")
    return isinstance(action_type, str) and bool(action_type.strip())


def determine_research_transition(state: Mapping[str, Any]) -> dict[str, Any]:
    """Classify the next control transition without executing or reopening anything."""
    result = _transition_base(state)
    stop_status = result["planning_stop_status"]
    selected_action = state.get("selected_action")
    evidence_gap = _mapping(state.get("evidence_gap"), "planning_state.evidence_gap")

    if stop_status == "continue":
        if not _selected_action_is_bounded(selected_action):
            result["transition_type"] = "manual_review_required"
            result["selected_action"] = None
            result["reason"] = (
                "Planning state is active but has no valid bounded selected action; fail closed "
                "to manual review instead of inventing or partially accepting an action."
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
    data, snapshot_stat = _stable_file_snapshot(path)
    if not data:
        raise PlanningTransitionError("reopen evidence file must not be empty")

    return {
        "schema_version": TRANSITION_SCHEMA_VERSION,
        "transition_policy_version": TRANSITION_POLICY_VERSION,
        "adapter_id": _nonempty_text(state.get("adapter_id"), "planning_state.adapter_id"),
        "domain": _nonempty_text(state.get("domain"), "planning_state.domain"),
        "planning_evidence_bindings": _evidence_bindings(state.get("evidence_bindings")),
        "review_status": "manual_semantic_review_required",
        "requested_transition": "reopen_current_scope",
        "condition_index": condition_index,
        "reopen_condition": condition,
        "evidence_binding": {
            "path": str(path),
            "sha256": hashlib.sha256(data).hexdigest(),
            "size_bytes": len(data),
            "mtime_ns": snapshot_stat.st_mtime_ns,
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