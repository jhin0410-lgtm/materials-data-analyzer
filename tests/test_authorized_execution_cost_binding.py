from __future__ import annotations

import pytest

import materials_data_analyzer.research_loop.authorized_execution as execution


def test_dispatch_cost_uses_code_bound_version_when_authorization_repeats_no_cost() -> None:
    key = (execution.PROTOCOL_ACTION_TYPE, "1.0")
    assert execution._dispatch_cost_units(key, {}) == 5


def test_dispatch_cost_rejects_registry_authorization_cost_drift() -> None:
    key = (execution.PROTOCOL_ACTION_TYPE, "1.0")
    with pytest.raises(
        execution.AuthorizedExecutionError,
        match="does not match the hardcoded action version",
    ):
        execution._dispatch_cost_units(key, {"cost_units": 4})


def test_dispatch_cost_rejects_malformed_cost() -> None:
    key = (execution.PROTOCOL_ACTION_TYPE, "1.0")
    with pytest.raises(
        execution.AuthorizedExecutionError,
        match="cost binding is malformed",
    ):
        execution._dispatch_cost_units(key, {"cost_units": True})
