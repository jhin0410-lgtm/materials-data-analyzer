from __future__ import annotations

from pathlib import Path

from materials_data_analyzer.research_loop import (
    build_current_research_transition,
    build_research_planning_state,
    run_research_cycle,
)


ROOT = Path(__file__).resolve().parents[1]
ADAPTER = "nist-ambench-process-characterization"


def test_nist_planning_state_exposes_exact_physical_evidence_gap() -> None:
    state = build_research_planning_state(ADAPTER, repository_root=ROOT)

    assert state["claim_boundary"] == {
        "evidence_level": "Diagnostic",
        "maximum_allowed_use": "descriptive",
    }
    assert state["current_blocker"]["kind"] == (
        "physical_evidence_and_validation_design_limit"
    )
    assert state["evidence_gap"]["status"] == (
        "physical_evidence_required_for_stronger_use"
    )
    requirements = state["evidence_gap"]["requirements"]
    assert len(requirements) == 5
    assert any("additional physical AMMT trace evidence" in item for item in requirements)
    assert any("independence/split grouping" in item for item in requirements)
    assert any("measurement timing" in item for item in requirements)
    assert state["selected_action"] is None
    assert state["action_frontier"] == []
    assert state["stop_state"]["status"] == "terminal_for_current_scope"
    assert len(state["stop_state"]["reopen_conditions"]) == 2
    assert state["network_access_performed"] is False
    assert state["action_executed"] is False
    assert state["model_fit_performed"] is False
    assert state["scientific_evidence_upgraded"] is False


def test_nist_transition_stops_current_scope_without_inventing_action() -> None:
    transition = build_current_research_transition(ADAPTER, repository_root=ROOT)

    assert transition["transition_type"] == "stop_current_scope"
    assert transition["selected_action"] is None
    assert transition["automatic_execution_authorized"] is False
    assert transition["automatic_reopen_authorized"] is False
    assert transition["network_access_performed"] is False
    assert transition["model_fit_performed"] is False
    assert transition["scientific_evidence_upgraded"] is False


def test_nist_one_step_cycle_stops_without_request_or_execution() -> None:
    result = run_research_cycle(ADAPTER, repository_root=ROOT)

    assert result["cycle_status"] == "stopped_current_scope"
    assert result["actions_executed"] == 0
    assert result["authorization"] is None
    assert result["execution"] is None
    assert result["after_planning_state"] is None
    assert result["after_transition"] is None
    assert result["automatic_looping_available"] is False
    assert result["automatic_request_generation_available"] is False
    assert result["generic_command_execution_available"] is False
    assert result["network_access_initiated_by_cycle_orchestrator"] is False
    assert result["model_fit_initiated_by_cycle_orchestrator"] is False
    assert result["scientific_evidence_upgraded_by_cycle_orchestrator"] is False
