from __future__ import annotations

import copy
import hashlib
import json

import pytest

from materials_data_analyzer.research_loop.recursive_resource_budget import (
    RecursiveResourceBudgetError,
    apply_recursive_resource_budget,
)


def _sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _checkpoint(
    cycle_index: int,
    *,
    status: str = "explicit_authorization_required",
    previous_sha: str | None = None,
) -> dict:
    value = {
        "schema_version": "1.0",
        "policy_version": "1.0",
        "cycle_id": f"recursive:g-{cycle_index}:h-1",
        "cycle_index": cycle_index,
        "checkpoint_status": status,
        "target": {
            "graph_id": f"g-{cycle_index}",
            "node_id": "h-1",
            "node_type": "hypothesis",
            "statement": "H",
        },
        "ancestry": {
            "previous_checkpoint_sha256": previous_sha,
            "source_discrepancy_report_sha256": "a" * 64,
            "planning_handoff_sha256": "b" * 64,
            "fresh_plan_sha256": "c" * 64,
        },
        "authorization_handoff": {
            "required": status == "explicit_authorization_required",
            "destination": "existing_independent_action_authorization_and_typed_executor_chain",
            "authorization_granted": False,
            "request_compiled": False,
            "execution_performed": False,
        },
        "bounded_stop": {
            "stopped": status.startswith("bounded_stop_"),
            "reason": "already_stopped" if status.startswith("bounded_stop_") else None,
            "reopen_condition": None,
        },
        "autonomy_boundary": {
            "authorization_granted": False,
            "execution_performed": False,
            "scientific_status_changed": False,
        },
    }
    value["checkpoint_sha256"] = _sha(value)
    return value


def _plan(action_id: str, cost: float) -> dict:
    return {
        "selected_next_action": {
            "action_id": action_id,
            "cost_units": cost,
        }
    }


def _limits(*, cycles: int = 8, actions: int = 8, cost: float = 64.0) -> dict:
    return {
        "max_cycles": cycles,
        "max_action_slots": actions,
        "max_planned_cost_units": cost,
    }


def test_first_cycle_binds_budget_without_claiming_execution() -> None:
    checkpoint, budget = apply_recursive_resource_budget(
        checkpoint=_checkpoint(1),
        fresh_plan=_plan("a-1", 1.5),
        recursive_limits=_limits(cycles=2, actions=2, cost=3.0),
    )

    assert checkpoint["checkpoint_status"] == "explicit_authorization_required"
    assert checkpoint["recursive_resource_budget_sha256"] == budget["budget_sha256"]
    assert budget["usage_before"] == {
        "planning_cycles": 0,
        "planned_action_slots": 0,
        "cumulative_planned_cost_units": 0.0,
    }
    assert budget["usage_after"] == {
        "planning_cycles": 1,
        "planned_action_slots": 1,
        "cumulative_planned_cost_units": 1.5,
    }
    assert budget["execution_count_claimed"] is False
    assert budget["actual_execution_cost_claimed"] is False


def test_successor_stops_when_configured_cycle_limit_is_exhausted() -> None:
    first, first_budget = apply_recursive_resource_budget(
        checkpoint=_checkpoint(1),
        fresh_plan=_plan("a-1", 1.0),
        recursive_limits=_limits(cycles=1),
    )
    second_base = _checkpoint(2, previous_sha=first["checkpoint_sha256"])
    second, budget = apply_recursive_resource_budget(
        checkpoint=second_base,
        fresh_plan=_plan("a-2", 1.0),
        previous_checkpoint=first,
        previous_budget=first_budget,
        recursive_limits=_limits(cycles=1),
    )

    assert second["checkpoint_status"] == "bounded_stop_recursive_resource_limit"
    assert second["authorization_handoff"]["required"] is False
    assert second["bounded_stop"]["reason"] == "configured_max_cycles_exhausted"
    assert budget["usage_after"]["planned_action_slots"] == 1
    assert budget["usage_after"]["cumulative_planned_cost_units"] == 1.0


def test_successor_stops_before_consuming_second_action_slot() -> None:
    limits = _limits(cycles=4, actions=1, cost=10.0)
    first, first_budget = apply_recursive_resource_budget(
        checkpoint=_checkpoint(1),
        fresh_plan=_plan("a-1", 1.0),
        recursive_limits=limits,
    )
    second, budget = apply_recursive_resource_budget(
        checkpoint=_checkpoint(2, previous_sha=first["checkpoint_sha256"]),
        fresh_plan=_plan("a-2", 1.0),
        previous_checkpoint=first,
        previous_budget=first_budget,
        recursive_limits=limits,
    )

    assert second["bounded_stop"]["reason"] == "configured_max_action_slots_exhausted"
    assert budget["current_cycle"]["authorization_slot_consumed"] is False
    assert budget["usage_after"]["planned_action_slots"] == 1


def test_successor_stops_before_exceeding_cumulative_planned_cost() -> None:
    limits = _limits(cycles=4, actions=4, cost=2.0)
    first, first_budget = apply_recursive_resource_budget(
        checkpoint=_checkpoint(1),
        fresh_plan=_plan("a-1", 1.5),
        recursive_limits=limits,
    )
    second, budget = apply_recursive_resource_budget(
        checkpoint=_checkpoint(2, previous_sha=first["checkpoint_sha256"]),
        fresh_plan=_plan("a-2", 0.6),
        previous_checkpoint=first,
        previous_budget=first_budget,
        recursive_limits=limits,
    )

    assert second["bounded_stop"]["reason"] == (
        "configured_max_planned_cost_units_exhausted"
    )
    assert budget["current_cycle"]["planned_cost_consumed"] == 0.0
    assert budget["usage_after"]["cumulative_planned_cost_units"] == 1.5
    assert budget["usage_after"]["planned_action_slots"] == 1


def test_recursive_limits_cannot_be_raised_inside_existing_ancestry() -> None:
    first, first_budget = apply_recursive_resource_budget(
        checkpoint=_checkpoint(1),
        fresh_plan=_plan("a-1", 1.0),
        recursive_limits=_limits(cycles=2, actions=2, cost=2.0),
    )
    with pytest.raises(RecursiveResourceBudgetError, match="cannot change"):
        apply_recursive_resource_budget(
            checkpoint=_checkpoint(2, previous_sha=first["checkpoint_sha256"]),
            fresh_plan=_plan("a-2", 1.0),
            previous_checkpoint=first,
            previous_budget=first_budget,
            recursive_limits=_limits(cycles=20, actions=20, cost=200.0),
        )


def test_tampered_predecessor_budget_fails_closed() -> None:
    limits = _limits(cycles=2, actions=2, cost=2.0)
    first, first_budget = apply_recursive_resource_budget(
        checkpoint=_checkpoint(1),
        fresh_plan=_plan("a-1", 1.0),
        recursive_limits=limits,
    )
    tampered = copy.deepcopy(first_budget)
    tampered["usage_after"]["planned_action_slots"] = 0

    with pytest.raises(RecursiveResourceBudgetError, match="SHA-256 does not match"):
        apply_recursive_resource_budget(
            checkpoint=_checkpoint(2, previous_sha=first["checkpoint_sha256"]),
            fresh_plan=_plan("a-2", 1.0),
            previous_checkpoint=first,
            previous_budget=tampered,
            recursive_limits=limits,
        )


def test_existing_bounded_stop_does_not_consume_action_or_cost() -> None:
    checkpoint, budget = apply_recursive_resource_budget(
        checkpoint=_checkpoint(1, status="bounded_stop_no_matching_candidate"),
        fresh_plan=_plan("a-1", 7.0),
        recursive_limits=_limits(cycles=2, actions=2, cost=10.0),
    )

    assert checkpoint["checkpoint_status"] == "bounded_stop_no_matching_candidate"
    assert budget["usage_after"]["planned_action_slots"] == 0
    assert budget["usage_after"]["cumulative_planned_cost_units"] == 0.0
    assert budget["limit_decision"]["stop"] is False
