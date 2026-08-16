from __future__ import annotations

from materials_data_analyzer.research_loop.self_directed_research import (
    build_self_directed_research_plan,
)


def _program(requirement: str = "At least two independent samples and acquisitions") -> dict[str, object]:
    return {
        "mission": {
            "autonomy_policy": {
                "goal_generation": "bounded_autonomous",
                "reasoning_proposals": "schema_validated",
                "typed_computational_actions": "explicit_request",
                "network_evidence_search": "explicit_authorization",
                "physical_experiment_execution": "external_only",
            }
        },
        "generated_goals": [
            {
                "goal_id": "mission:workstream:resolve-current-blocker",
                "workstream_id": "workstream",
                "research_question": "What evidence is needed next?",
                "goal_statement": "Resolve the current evidence gap.",
                "status": "active",
                "priority": 80,
                "evidence_requirements": [requirement],
                "claim_boundary": {"scientific_status": "inconclusive"},
                "action_frontier": [],
            }
        ],
    }


def test_empirical_gap_generates_search_and_experiment_design_without_execution() -> None:
    plan = build_self_directed_research_plan(_program())

    classes = {item["action_class"] for item in plan["self_generated_gap_actions"]}
    assert classes == {"external_evidence_search", "physical_experiment_design"}
    assert plan["selected_next_action"]["action_class"] == "external_evidence_search"
    assert plan["selected_next_action"]["execution_mode"] == "explicit_authorization_required"
    assert plan["handoff"]["execution_performed"] is False
    assert plan["autonomy_boundary"]["second_executor_introduced"] is False
    experiment = next(
        item
        for item in plan["self_generated_gap_actions"]
        if item["action_class"] == "physical_experiment_design"
    )
    assert experiment["execution_mode"] == "plan_only"
    assert experiment["physical_experiment_execution_authorized"] is False


def test_analysis_gap_generates_bounded_reanalysis_design() -> None:
    plan = build_self_directed_research_plan(
        _program("Predeclared sensitivity and residual robustness analysis")
    )

    assert plan["self_generated_gap_actions"][0]["action_class"] == "sensitivity_analysis"
    assert plan["self_generated_gap_actions"][0]["execution_mode"] == "plan_only"
    assert plan["autonomy_boundary"]["automatic_execution_authorized"] is False


def test_simulation_gap_generates_solver_bounded_plan_only_candidate() -> None:
    plan = build_self_directed_research_plan(
        _program("Thermodynamic simulation with traceable solver inputs and outputs")
    )

    simulation = next(
        item for item in plan["self_generated_gap_actions"] if item["action_class"] == "simulation"
    )
    assert simulation["execution_mode"] == "plan_only"
    assert plan["autonomy_boundary"]["unregistered_solver_executed"] is False


def test_unknown_gap_fails_safe_to_manual_discrimination_design() -> None:
    plan = build_self_directed_research_plan(_program("Resolve the unresolved epistemic ambiguity"))

    assert len(plan["self_generated_gap_actions"]) == 1
    action = plan["self_generated_gap_actions"][0]
    assert action["action_class"] == "manual_review"
    assert action["execution_mode"] == "plan_only"


def test_same_program_and_selected_action_stops_repeated_iteration_as_stagnation() -> None:
    first = build_self_directed_research_plan(_program())
    second = build_self_directed_research_plan(_program(), previous_plan=first)

    assert second["iteration_index"] == 2
    assert second["selected_next_action"] is None
    assert second["stop_decision"] == {
        "stop": True,
        "reason": "stagnation_no_new_verified_evidence",
        "next_mode": "seek_new_evidence_path_or_revise_objective",
    }
    assert second["objective_revision"]["mission_mutation_performed"] is False


def test_changed_verified_program_binding_allows_second_iteration() -> None:
    first = build_self_directed_research_plan(_program())
    changed = _program("Raw or demonstrably lossless source representation with checksum")
    second = build_self_directed_research_plan(changed, previous_plan=first)

    assert second["iteration_index"] == 2
    assert second["stop_decision"]["stop"] is False
    assert second["selected_next_action"] is not None


def test_max_iteration_guard_prevents_unbounded_research_loop() -> None:
    first = build_self_directed_research_plan(_program(), max_iterations=1)
    changed = _program("Raw source dataset and checksum")
    second = build_self_directed_research_plan(
        changed,
        previous_plan=first,
        max_iterations=1,
    )

    assert second["iteration_index"] == 2
    assert second["selected_next_action"] is None
    assert second["stop_decision"]["reason"] == "maximum_iteration_guard_reached"
    assert second["handoff"]["required_for_selected_action"] is False
