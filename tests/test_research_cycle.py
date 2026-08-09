from __future__ import annotations

from pathlib import Path

import pytest

import materials_data_analyzer.research_loop.research_cycle as cycle


ROOT = Path(__file__).resolve().parents[1]


def _state(
    *,
    stop_status: str,
    selection_status: str,
    selected_action: object = None,
    evidence_gap_status: str = "action_expected_to_reduce_uncertainty",
) -> dict[str, object]:
    return {
        "adapter_id": "nasa-battery",
        "domain": "battery_degradation",
        "selected_action": selected_action,
        "evidence_gap": {"status": evidence_gap_status, "requirements": []},
        "stop_state": {
            "status": stop_status,
            "selection_status": selection_status,
            "reason": "test reason",
            "reopen_conditions": [],
        },
        "budget": {"actions_remaining": 2, "cost_units_remaining": 10},
    }


def _ready_action() -> dict[str, object]:
    return {
        "action_type": "protocol_stratification",
        "action_version": "1.0",
        "availability": "available",
        "cost_units": 2,
        "execution_registry_id": "test-registry",
        "execution_registry_sha256": "a" * 64,
        "execution_registry_path": "registry.json",
    }


def _ready_authorization() -> dict[str, object]:
    return {
        "authorization_status": "ready_for_explicit_execution_request",
        "selected_action": _ready_action(),
    }


def test_current_materials_project_cycle_stops_without_execution() -> None:
    result = cycle.run_research_cycle(
        "materials-project-external-source",
        repository_root=ROOT,
    )

    assert result["cycle_status"] == "stopped_current_scope"
    assert result["actions_executed"] == 0
    assert result["authorization"] is None
    assert result["execution"] is None
    assert result["automatic_looping_available"] is False


def test_current_tm_fe_si_cycle_stops_without_execution() -> None:
    result = cycle.run_research_cycle(
        "tm-fe-si-descriptive",
        repository_root=ROOT,
    )

    assert result["cycle_status"] == "stopped_current_scope"
    assert result["actions_executed"] == 0
    assert result["scientific_evidence_upgraded_by_cycle_orchestrator"] is False


@pytest.mark.parametrize(
    ("stop_status", "selection_status", "expected"),
    [
        ("manual_review_gate", "manual_review_required", "manual_review_required"),
        ("operationally_blocked", "blocked_by_budget", "blocked"),
    ],
)
def test_nonexecuting_control_states_do_not_authorize(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stop_status: str,
    selection_status: str,
    expected: str,
) -> None:
    state = _state(stop_status=stop_status, selection_status=selection_status)
    monkeypatch.setattr(cycle, "build_research_planning_state", lambda *a, **k: state)
    authorization_called = False

    def forbidden_authorization(*args: object, **kwargs: object) -> dict[str, object]:
        nonlocal authorization_called
        authorization_called = True
        return {}

    monkeypatch.setattr(cycle, "assess_action_authorization", forbidden_authorization)

    result = cycle.run_research_cycle("nasa-battery", repository_root=tmp_path)

    assert result["cycle_status"] == expected
    assert result["actions_executed"] == 0
    assert authorization_called is False


def test_ready_action_without_request_stops_at_explicit_request_required(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _state(
        stop_status="continue",
        selection_status="ready_to_execute",
        selected_action=_ready_action(),
    )
    monkeypatch.setattr(cycle, "build_research_planning_state", lambda *a, **k: state)
    monkeypatch.setattr(cycle, "assess_action_authorization", lambda *a, **k: _ready_authorization())
    executed = False

    def forbidden_executor(*args: object, **kwargs: object) -> dict[str, object]:
        nonlocal executed
        executed = True
        return {}

    monkeypatch.setattr(cycle, "execute_authorized_action", forbidden_executor)

    result = cycle.run_research_cycle("nasa-battery", repository_root=tmp_path)

    assert result["cycle_status"] == "explicit_request_required"
    assert result["actions_executed"] == 0
    assert executed is False
    assert result["automatic_request_generation_available"] is False


def test_authorization_denial_never_executes_even_when_request_supplied(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _state(
        stop_status="continue",
        selection_status="ready_to_execute",
        selected_action=_ready_action(),
    )
    request = tmp_path / "request.json"
    request.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(cycle, "build_research_planning_state", lambda *a, **k: state)
    monkeypatch.setattr(
        cycle,
        "assess_action_authorization",
        lambda *a, **k: {"authorization_status": "denied_cost_budget_exceeded"},
    )
    executed = False

    def forbidden_executor(*args: object, **kwargs: object) -> dict[str, object]:
        nonlocal executed
        executed = True
        return {}

    monkeypatch.setattr(cycle, "execute_authorized_action", forbidden_executor)

    result = cycle.run_research_cycle(
        "nasa-battery",
        repository_root=tmp_path,
        request_path=request,
    )

    assert result["cycle_status"] == "authorization_denied"
    assert result["request_unused"] is True
    assert result["actions_executed"] == 0
    assert executed is False


def test_one_explicit_action_executes_once_then_replans_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = _state(
        stop_status="continue",
        selection_status="ready_to_execute",
        selected_action=_ready_action(),
    )
    after = _state(
        stop_status="continue",
        selection_status="ready_to_execute",
        selected_action={
            **_ready_action(),
            "action_type": "target_reference_sensitivity",
        },
    )
    request = tmp_path / "request.json"
    request.write_text("{}", encoding="utf-8")
    run = tmp_path / "run"
    run.mkdir()
    planning = tmp_path / "planning.json"
    planning.write_text("{}", encoding="utf-8")

    states = iter([before, after])
    state_calls = 0

    def fake_state(*args: object, **kwargs: object) -> dict[str, object]:
        nonlocal state_calls
        state_calls += 1
        return next(states)

    executor_calls = 0

    def fake_executor(*args: object, **kwargs: object) -> dict[str, object]:
        nonlocal executor_calls
        executor_calls += 1
        return {
            "execution_status": "completed",
            "action_type": "protocol_stratification",
            "maximum_actions_executed_per_invocation": 1,
        }

    monkeypatch.setattr(cycle, "build_research_planning_state", fake_state)
    monkeypatch.setattr(cycle, "assess_action_authorization", lambda *a, **k: _ready_authorization())
    monkeypatch.setattr(cycle, "execute_authorized_action", fake_executor)

    result = cycle.run_research_cycle(
        "nasa-battery",
        repository_root=tmp_path,
        research_run=run,
        action_registry_path=planning,
        request_path=request,
    )

    assert result["cycle_status"] == "one_action_executed"
    assert result["actions_executed"] == 1
    assert executor_calls == 1
    assert state_calls == 2
    assert result["after_planning_state"]["selected_action"]["action_type"] == (
        "target_reference_sensitivity"
    )
    assert result["after_transition"]["transition_type"] == "action_pending_authorization"
    assert result["maximum_actions_executed_per_cycle"] == 1
    assert result["automatic_looping_available"] is False


def test_terminal_cycle_with_supplied_request_never_consumes_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _state(
        stop_status="terminal_for_current_scope",
        selection_status="no_positive_value_action",
    )
    request = tmp_path / "request.json"
    request.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(cycle, "build_research_planning_state", lambda *a, **k: state)

    result = cycle.run_research_cycle(
        "nasa-battery",
        repository_root=tmp_path,
        request_path=request,
    )

    assert result["cycle_status"] == "stopped_current_scope"
    assert result["request_unused"] is True
    assert result["actions_executed"] == 0


def test_execution_requires_run_and_registry_even_after_authorization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _state(
        stop_status="continue",
        selection_status="ready_to_execute",
        selected_action=_ready_action(),
    )
    request = tmp_path / "request.json"
    request.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(cycle, "build_research_planning_state", lambda *a, **k: state)
    monkeypatch.setattr(cycle, "assess_action_authorization", lambda *a, **k: _ready_authorization())

    with pytest.raises(cycle.ResearchCycleError, match="requires research_run"):
        cycle.run_research_cycle(
            "nasa-battery",
            repository_root=tmp_path,
            request_path=request,
        )
