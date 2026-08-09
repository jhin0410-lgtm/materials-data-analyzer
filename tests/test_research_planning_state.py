from __future__ import annotations

from pathlib import Path

import pytest

import materials_data_analyzer.research_loop.planning_state as planning_state


ROOT = Path(__file__).resolve().parents[1]


def test_materials_project_state_preserves_closed_evidence_gap() -> None:
    state = planning_state.build_research_planning_state(
        "materials-project-external-source",
        repository_root=ROOT,
    )

    assert state["domain"] == "materials_phase_stability"
    assert state["stop_state"]["status"] == "terminal_for_current_scope"
    assert state["current_blocker"]["code"] == (
        "independence_and_target_semantics_not_jointly_satisfied"
    )
    assert state["evidence_gap"]["status"] == "unsatisfied_external_evidence_requirement"
    assert state["evidence_gap"]["requirements"]
    assert state["stop_state"]["reopen_conditions"] == state["evidence_gap"]["requirements"]
    assert state["action_frontier"] == []
    assert state["network_access_performed"] is False
    assert state["action_executed"] is False
    assert state["model_fit_performed"] is False


def test_tm_fe_si_state_stops_current_scope_without_promoting_use() -> None:
    state = planning_state.build_research_planning_state(
        "tm-fe-si-descriptive",
        repository_root=ROOT,
    )

    assert state["claim_boundary"] == {
        "evidence_level": "Diagnostic",
        "maximum_allowed_use": "descriptive",
    }
    assert state["stop_state"]["status"] == "terminal_for_current_scope"
    assert state["current_blocker"]["kind"] == "stronger_claim_evidence_limit"
    assert state["evidence_gap"]["status"] == (
        "current_descriptive_scope_complete_stronger_use_unsatisfied"
    )
    assert state["stop_state"]["reopen_conditions"]
    assert state["scientific_evidence_upgraded"] is False


def test_nasa_state_projects_verified_question_budget_and_action_without_fake_information_gain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = tmp_path / "run"
    run.mkdir()

    monkeypatch.setattr(
        planning_state,
        "plan_research_next_action",
        lambda *args, **kwargs: {
            "adapter_id": "nasa-battery",
            "domain": "battery_degradation",
            "selection_status": "ready_to_execute",
            "selected_action": {
                "action_type": "protocol_stratification",
                "availability": "available",
                "cost_units": 5,
                "score": 110,
                "trigger": "pooled_error_instability_detected",
                "rationale": "Test protocol heterogeneity.",
            },
            "candidates": [
                {
                    "action_type": "protocol_stratification",
                    "availability": "available",
                    "cost_units": 5,
                    "score": 110,
                    "trigger": "pooled_error_instability_detected",
                    "rationale": "Test protocol heterogeneity.",
                }
            ],
            "reason": "Test protocol heterogeneity.",
            "evidence_level": None,
            "maximum_allowed_use": None,
            "evidence_bindings": [],
        },
    )
    monkeypatch.setattr(
        planning_state,
        "load_research_state",
        lambda path: {
            "question": "Can protocol structure explain concentrated error?",
            "constraints": ["battery_disjoint_validation"],
            "stop_rules": ["no_positive_value_action"],
            "budget": {
                "maximum_actions": 12,
                "actions_used": 2,
                "actions_remaining": 10,
                "maximum_cost_units": 100,
                "cost_units_used": 8,
                "cost_units_remaining": 92,
            },
            "stop": None,
        },
    )

    state = planning_state.build_research_planning_state(
        "nasa-battery",
        repository_root=tmp_path,
        research_run=run,
        action_registry_path=tmp_path / "unused.json",
    )

    assert state["research_question"] == "Can protocol structure explain concentrated error?"
    assert state["budget"]["actions_remaining"] == 10
    assert state["selected_action"]["priority_score"] == 110
    assert state["selected_action"]["expected_information_gain"]["status"] == "not_quantified"
    assert state["selected_action"]["expected_information_gain"]["value"] is None
    assert state["stop_state"]["status"] == "continue"


def test_nasa_external_requirement_action_becomes_explicit_evidence_gap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = tmp_path / "run"
    run.mkdir()
    monkeypatch.setattr(
        planning_state,
        "plan_research_next_action",
        lambda *args, **kwargs: {
            "adapter_id": "nasa-battery",
            "domain": "battery_degradation",
            "selection_status": "ready_to_execute",
            "selected_action": {
                "action_type": "external_data_requirement_generation",
                "availability": "available",
                "cost_units": 1,
                "score": 140,
                "trigger": "required_reference_metadata_missing",
                "rationale": "Specify missing reference metadata.",
            },
            "candidates": [],
            "reason": "Specify missing reference metadata.",
            "evidence_level": None,
            "maximum_allowed_use": None,
            "evidence_bindings": [],
        },
    )
    monkeypatch.setattr(
        planning_state,
        "load_research_state",
        lambda path: {
            "question": "What evidence is missing?",
            "constraints": [],
            "stop_rules": ["external_evidence_required"],
            "budget": {},
            "stop": None,
        },
    )

    state = planning_state.build_research_planning_state(
        "nasa-battery",
        repository_root=tmp_path,
        research_run=run,
        action_registry_path=tmp_path / "unused.json",
    )
    assert state["evidence_gap"]["status"] == "requirement_definition_needed"
    assert state["evidence_gap"]["requirements"]


def test_unknown_planning_state_adapter_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        planning_state,
        "plan_research_next_action",
        lambda *args, **kwargs: {
            "adapter_id": "unknown",
            "domain": "unknown",
            "selection_status": "no_positive_value_action",
            "selected_action": None,
            "candidates": [],
            "reason": "none",
            "evidence_level": None,
            "maximum_allowed_use": None,
            "evidence_bindings": [],
        },
    )
    with pytest.raises(planning_state.PlanningStateError, match="unsupported planning-state adapter"):
        planning_state.build_research_planning_state(
            "unknown",
            repository_root=tmp_path,
        )
