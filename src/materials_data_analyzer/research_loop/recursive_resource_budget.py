"""Deterministic resource bounds for validated recursive research cycles.

The resource controller runs after the private discrepancy/planner checkpoint is built
and before a validated checkpoint is published.  It counts *planning cycles* and
*authorization action slots*, not executed actions: execution truth remains owned by the
independent typed-execution / immutable-ledger evidence chain.

Limits are immutable across one recursive ancestry.  Successor usage is accepted only
from a deterministically reconstructed predecessor budget whose SHA is embedded in the
predecessor checkpoint.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

from .kernel import ResearchLoopError

RECURSIVE_RESOURCE_BUDGET_SCHEMA_VERSION = "1.0"
RECURSIVE_RESOURCE_BUDGET_POLICY_VERSION = "1.0"
DEFAULT_RECURSIVE_LIMITS: dict[str, int | float] = {
    "max_cycles": 8,
    "max_action_slots": 8,
    "max_planned_cost_units": 64.0,
}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class RecursiveResourceBudgetError(ResearchLoopError):
    """Raised when recursive resource limits or cumulative usage cannot be trusted."""


def _canonical_sha256(value: object) -> str:
    try:
        payload = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise RecursiveResourceBudgetError(
            "recursive resource state must be canonical-JSON serializable"
        ) from exc
    return hashlib.sha256(payload).hexdigest()


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise RecursiveResourceBudgetError(f"{field} must be an integer >= 1")
    return value


def _nonnegative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise RecursiveResourceBudgetError(f"{field} must be an integer >= 0")
    return value


def _positive_decimal(value: object, field: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise RecursiveResourceBudgetError(f"{field} must be a finite number > 0")
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise RecursiveResourceBudgetError(f"{field} must be a finite number > 0") from exc
    if not result.is_finite() or result <= 0:
        raise RecursiveResourceBudgetError(f"{field} must be a finite number > 0")
    return result


def _nonnegative_decimal(value: object, field: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise RecursiveResourceBudgetError(f"{field} must be a finite number >= 0")
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise RecursiveResourceBudgetError(f"{field} must be a finite number >= 0") from exc
    if not result.is_finite() or result < 0:
        raise RecursiveResourceBudgetError(f"{field} must be a finite number >= 0")
    return result


def normalize_recursive_limits(value: Mapping[str, Any] | None) -> dict[str, int | float]:
    """Normalize one explicit recursive limit contract."""
    raw: Mapping[str, Any] = DEFAULT_RECURSIVE_LIMITS if value is None else value
    if set(raw) != {"max_cycles", "max_action_slots", "max_planned_cost_units"}:
        raise RecursiveResourceBudgetError(
            "recursive_limits must contain exactly max_cycles, max_action_slots, "
            "and max_planned_cost_units"
        )
    max_cost = _positive_decimal(
        raw["max_planned_cost_units"], "recursive_limits.max_planned_cost_units"
    )
    return {
        "max_cycles": _positive_int(raw["max_cycles"], "recursive_limits.max_cycles"),
        "max_action_slots": _positive_int(
            raw["max_action_slots"], "recursive_limits.max_action_slots"
        ),
        "max_planned_cost_units": float(max_cost),
    }


def _verify_previous_budget(
    previous_budget: Mapping[str, Any],
    *,
    previous_checkpoint: Mapping[str, Any],
    limits: Mapping[str, int | float],
    expected_previous_cycles: int,
) -> tuple[int, Decimal]:
    if previous_budget.get("schema_version") != RECURSIVE_RESOURCE_BUDGET_SCHEMA_VERSION:
        raise RecursiveResourceBudgetError("previous recursive resource budget schema_version drifted")
    if previous_budget.get("policy_version") != RECURSIVE_RESOURCE_BUDGET_POLICY_VERSION:
        raise RecursiveResourceBudgetError("previous recursive resource budget policy_version drifted")
    supplied = dict(previous_budget)
    digest = supplied.pop("budget_sha256", None)
    if not isinstance(digest, str) or _SHA256.fullmatch(digest) is None:
        raise RecursiveResourceBudgetError("previous recursive resource budget SHA-256 is malformed")
    if _canonical_sha256(supplied) != digest:
        raise RecursiveResourceBudgetError("previous recursive resource budget SHA-256 does not match content")
    if previous_checkpoint.get("recursive_resource_budget_sha256") != digest:
        raise RecursiveResourceBudgetError(
            "previous checkpoint is not bound to the reconstructed recursive resource budget"
        )
    if previous_budget.get("limits") != dict(limits):
        raise RecursiveResourceBudgetError(
            "recursive resource limits cannot change within one recursive ancestry"
        )
    usage = previous_budget.get("usage_after")
    if not isinstance(usage, Mapping):
        raise RecursiveResourceBudgetError("previous recursive resource usage_after must be an object")
    cycles = _nonnegative_int(usage.get("planning_cycles"), "previous usage_after.planning_cycles")
    if cycles != expected_previous_cycles:
        raise RecursiveResourceBudgetError(
            "previous recursive planning-cycle usage disagrees with checkpoint ancestry"
        )
    slots = _nonnegative_int(
        usage.get("planned_action_slots"), "previous usage_after.planned_action_slots"
    )
    cost = _nonnegative_decimal(
        usage.get("cumulative_planned_cost_units"),
        "previous usage_after.cumulative_planned_cost_units",
    )
    return slots, cost


def apply_recursive_resource_budget(
    *,
    checkpoint: Mapping[str, Any],
    fresh_plan: Mapping[str, Any],
    previous_checkpoint: Mapping[str, Any] | None = None,
    previous_budget: Mapping[str, Any] | None = None,
    recursive_limits: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Bind cumulative limits to a checkpoint and fail closed before authorization."""
    limits = normalize_recursive_limits(recursive_limits)
    current = dict(checkpoint)
    cycle_index = _positive_int(current.get("cycle_index"), "checkpoint.cycle_index")
    base_checkpoint_sha = current.get("checkpoint_sha256")
    if not isinstance(base_checkpoint_sha, str) or _SHA256.fullmatch(base_checkpoint_sha) is None:
        raise RecursiveResourceBudgetError("checkpoint.checkpoint_sha256 is malformed")

    if cycle_index == 1:
        if previous_checkpoint is not None or previous_budget is not None:
            raise RecursiveResourceBudgetError(
                "cycle-one recursive resource state cannot carry predecessor usage"
            )
        prior_slots = 0
        prior_cost = Decimal("0")
    else:
        if previous_checkpoint is None or previous_budget is None:
            raise RecursiveResourceBudgetError(
                "successor recursive resource state requires reconstructed predecessor checkpoint and budget"
            )
        prior_slots, prior_cost = _verify_previous_budget(
            previous_budget,
            previous_checkpoint=previous_checkpoint,
            limits=limits,
            expected_previous_cycles=cycle_index - 1,
        )

    selected = fresh_plan.get("selected_next_action")
    selected_id: str | None = None
    selected_cost = Decimal("0")
    if isinstance(selected, Mapping):
        action_id = selected.get("action_id")
        if not isinstance(action_id, str) or not action_id.strip():
            raise RecursiveResourceBudgetError("selected action_id must be non-empty text")
        selected_id = action_id
        selected_cost = _nonnegative_decimal(
            selected.get("cost_units"), "selected_next_action.cost_units"
        )

    base_authorization_open = current.get("checkpoint_status") == "explicit_authorization_required"
    resource_stop_reason: str | None = None
    if cycle_index > int(limits["max_cycles"]):
        resource_stop_reason = "configured_max_cycles_exhausted"
    elif base_authorization_open and prior_slots >= int(limits["max_action_slots"]):
        resource_stop_reason = "configured_max_action_slots_exhausted"
    elif base_authorization_open and prior_cost + selected_cost > Decimal(
        str(limits["max_planned_cost_units"])
    ):
        resource_stop_reason = "configured_max_planned_cost_units_exhausted"

    slot_consumed = base_authorization_open and resource_stop_reason is None
    cost_consumed = selected_cost if slot_consumed else Decimal("0")
    usage_after = {
        "planning_cycles": cycle_index,
        "planned_action_slots": prior_slots + (1 if slot_consumed else 0),
        "cumulative_planned_cost_units": float(prior_cost + cost_consumed),
    }
    budget: dict[str, Any] = {
        "schema_version": RECURSIVE_RESOURCE_BUDGET_SCHEMA_VERSION,
        "policy_version": RECURSIVE_RESOURCE_BUDGET_POLICY_VERSION,
        "limits": dict(limits),
        "base_checkpoint_sha256": base_checkpoint_sha,
        "usage_before": {
            "planning_cycles": cycle_index - 1,
            "planned_action_slots": prior_slots,
            "cumulative_planned_cost_units": float(prior_cost),
        },
        "current_cycle": {
            "cycle_index": cycle_index,
            "selected_action_id": selected_id,
            "selected_action_cost_units": float(selected_cost),
            "authorization_slot_consumed": slot_consumed,
            "planned_cost_consumed": float(cost_consumed),
        },
        "usage_after": usage_after,
        "limit_decision": {
            "stop": resource_stop_reason is not None,
            "reason": resource_stop_reason,
            "semantics": (
                "configured_recursive_resource_limit_before_authorization"
                if resource_stop_reason is not None
                else "within_configured_recursive_resource_limits"
            ),
        },
        "execution_count_claimed": False,
        "actual_execution_cost_claimed": False,
    }
    budget["budget_sha256"] = _canonical_sha256(budget)

    current.pop("checkpoint_sha256", None)
    current["recursive_resource_budget_sha256"] = budget["budget_sha256"]
    if resource_stop_reason is not None:
        current["checkpoint_status"] = "bounded_stop_recursive_resource_limit"
        authorization = dict(current.get("authorization_handoff", {}))
        authorization["required"] = False
        current["authorization_handoff"] = authorization
        current["bounded_stop"] = {
            "stopped": True,
            "reason": resource_stop_reason,
            "reopen_condition": (
                "Start a new explicitly configured recursive ancestry; limits are immutable "
                "within the current ancestry."
            ),
        }
    current["checkpoint_sha256"] = _canonical_sha256(current)
    return current, budget


__all__ = [
    "DEFAULT_RECURSIVE_LIMITS",
    "RECURSIVE_RESOURCE_BUDGET_POLICY_VERSION",
    "RECURSIVE_RESOURCE_BUDGET_SCHEMA_VERSION",
    "RecursiveResourceBudgetError",
    "apply_recursive_resource_budget",
    "normalize_recursive_limits",
]
