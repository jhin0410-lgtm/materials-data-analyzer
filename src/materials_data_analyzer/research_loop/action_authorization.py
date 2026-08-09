"""Fail-closed authorization checks for planner-selected typed research actions.

Authorization verifies the selected action against its tracked execution registry
and remaining research budget. It never executes the action. A successful result
means only that an explicit typed execution request may be considered next.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .action_registry import describe_action, load_action_registry
from .kernel import ResearchLoopError
from .planning_state import build_research_planning_state
from .planning_transition import determine_research_transition

AUTHORIZATION_SCHEMA_VERSION = "1.0"
AUTHORIZATION_POLICY_VERSION = "1.0"
_EXECUTABLE_BINDING_KINDS = {"installed_command", "source_script"}
_AUTHORIZABLE_TRANSITIONS = {
    "action_pending_authorization",
    "evidence_requirement_pending_authorization",
}


class ActionAuthorizationError(ResearchLoopError):
    """Raised when a selected action or execution registry binding has drifted."""


def _nonempty_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ActionAuthorizationError(f"{field} must be a non-empty string")
    return value.strip()


def _nonnegative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ActionAuthorizationError(f"{field} must be a non-negative integer")
    return value


def _resolve_registry_path(raw: object, repository_root: Path) -> Path:
    text = _nonempty_text(raw, "selected_action.execution_registry_path")
    path = Path(text).expanduser()
    if not path.is_absolute():
        path = repository_root / path
    resolved = path.resolve(strict=True)
    try:
        resolved.relative_to(repository_root)
    except ValueError as exc:
        raise ActionAuthorizationError(
            "selected execution registry escapes repository root"
        ) from exc
    if not resolved.is_file():
        raise ActionAuthorizationError(
            f"selected execution registry is not a file: {resolved}"
        )
    return resolved


def _base_result(state: Mapping[str, Any], transition: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": AUTHORIZATION_SCHEMA_VERSION,
        "authorization_policy_version": AUTHORIZATION_POLICY_VERSION,
        "adapter_id": _nonempty_text(state.get("adapter_id"), "planning_state.adapter_id"),
        "domain": _nonempty_text(state.get("domain"), "planning_state.domain"),
        "transition_type": transition.get("transition_type"),
        "authorization_status": None,
        "selected_action": state.get("selected_action"),
        "execution_registry_verified": False,
        "selected_action_binding_verified": False,
        "budget_verified": False,
        "explicit_execution_request_required": True,
        "automatic_execution_authorized": False,
        "action_executed": False,
        "network_access_performed": False,
        "model_fit_performed": False,
        "scientific_evidence_upgraded": False,
    }


def assess_action_authorization(
    state: Mapping[str, Any],
    *,
    repository_root: str | Path,
) -> dict[str, Any]:
    """Verify one planner-selected action without executing it."""
    root = Path(repository_root).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ActionAuthorizationError(f"repository_root is not a directory: {root}")
    transition = determine_research_transition(state)
    result = _base_result(state, transition)
    transition_type = transition.get("transition_type")
    if transition_type not in _AUTHORIZABLE_TRANSITIONS:
        result["authorization_status"] = "not_authorizable_current_state"
        result["reason"] = (
            "The current research transition does not permit a typed execution request."
        )
        return result

    selected = state.get("selected_action")
    if not isinstance(selected, Mapping):
        raise ActionAuthorizationError(
            "authorizable transition must contain one selected action"
        )
    action_type = _nonempty_text(selected.get("action_type"), "selected_action.action_type")
    action_version = _nonempty_text(
        selected.get("action_version"), "selected_action.action_version"
    )
    selected_availability = _nonempty_text(
        selected.get("availability"), "selected_action.availability"
    )
    selected_cost = _nonnegative_int(
        selected.get("cost_units"), "selected_action.cost_units"
    )
    expected_registry_id = _nonempty_text(
        selected.get("execution_registry_id"),
        "selected_action.execution_registry_id",
    )
    expected_registry_sha = _nonempty_text(
        selected.get("execution_registry_sha256"),
        "selected_action.execution_registry_sha256",
    )
    if len(expected_registry_sha) != 64 or any(
        char not in "0123456789abcdef" for char in expected_registry_sha
    ):
        raise ActionAuthorizationError(
            "selected_action.execution_registry_sha256 must be lowercase SHA-256 hex"
        )
    registry_path = _resolve_registry_path(
        selected.get("execution_registry_path"), root
    )
    registry = load_action_registry(registry_path, repository_root=root)
    if registry["registry_id"] != expected_registry_id:
        raise ActionAuthorizationError(
            "selected action execution registry_id no longer matches tracked registry"
        )
    if registry["registry_sha256"] != expected_registry_sha:
        raise ActionAuthorizationError(
            "selected action execution registry SHA-256 no longer matches tracked registry"
        )
    contract = describe_action(registry, action_type)
    if contract["version"] != action_version:
        raise ActionAuthorizationError(
            "selected action version no longer matches execution registry"
        )
    if contract["availability"] != selected_availability:
        raise ActionAuthorizationError(
            "selected action availability no longer matches execution registry"
        )
    if contract["cost_units"] != selected_cost:
        raise ActionAuthorizationError(
            "selected action cost no longer matches execution registry"
        )
    if selected_availability != "available":
        result["authorization_status"] = "denied_action_not_available"
        result["reason"] = "The selected action is not marked available for execution."
        return result
    binding = contract.get("binding")
    if not isinstance(binding, Mapping):
        raise ActionAuthorizationError("execution registry action binding is malformed")
    binding_kind = binding.get("kind")
    if binding_kind not in _EXECUTABLE_BINDING_KINDS:
        result["authorization_status"] = "denied_non_executable_binding"
        result["reason"] = (
            "The selected action does not bind a registered installed command or source script."
        )
        return result
    verifier_checks = contract.get("verifier_checks")
    if not isinstance(verifier_checks, list) or not verifier_checks:
        raise ActionAuthorizationError(
            "available execution contract must retain independent verifier checks"
        )

    result["execution_registry_verified"] = True
    result["selected_action_binding_verified"] = True
    result["execution_contract"] = {
        "registry_id": registry["registry_id"],
        "registry_sha256": registry["registry_sha256"],
        "registry_path": registry["registry_path"],
        "action_type": action_type,
        "action_version": contract["version"],
        "category": contract["category"],
        "cost_units": contract["cost_units"],
        "binding": dict(binding),
        "verifier_checks": list(verifier_checks),
        "prohibited_effects": list(contract["prohibited_effects"]),
    }

    budget = state.get("budget")
    if not isinstance(budget, Mapping):
        raise ActionAuthorizationError(
            "authorizable action requires a verified research budget"
        )
    actions_remaining = _nonnegative_int(
        budget.get("actions_remaining"), "planning_state.budget.actions_remaining"
    )
    cost_units_remaining = _nonnegative_int(
        budget.get("cost_units_remaining"),
        "planning_state.budget.cost_units_remaining",
    )
    if actions_remaining <= 0:
        result["authorization_status"] = "denied_action_budget_exhausted"
        result["reason"] = "No research actions remain in the verified budget."
        return result
    if selected_cost > cost_units_remaining:
        result["authorization_status"] = "denied_cost_budget_exceeded"
        result["reason"] = (
            "The selected typed action would exceed the verified remaining cost budget."
        )
        return result

    result["budget_verified"] = True
    result["authorization_status"] = "ready_for_explicit_execution_request"
    result["reason"] = (
        "The planner-selected typed action, execution registry, verifier contract, and budget "
        "match. Execution still requires a separate explicit typed request and is not automatic."
    )
    return result


def assess_current_action_authorization(
    adapter_id: str,
    *,
    repository_root: str | Path,
    research_run: str | Path | None = None,
    action_registry_path: str | Path | None = None,
) -> dict[str, Any]:
    """Build current planning state and assess typed action authorization."""
    state = build_research_planning_state(
        adapter_id,
        repository_root=repository_root,
        research_run=research_run,
        action_registry_path=action_registry_path,
    )
    return assess_action_authorization(state, repository_root=repository_root)


__all__ = [
    "AUTHORIZATION_POLICY_VERSION",
    "AUTHORIZATION_SCHEMA_VERSION",
    "ActionAuthorizationError",
    "assess_action_authorization",
    "assess_current_action_authorization",
]
