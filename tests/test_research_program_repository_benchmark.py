from __future__ import annotations

from pathlib import Path

from materials_data_analyzer.research_loop import build_research_program


def test_tracked_autonomous_mission_projects_real_repository_workstreams() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    mission = (
        repository_root
        / "configs"
        / "research"
        / "autonomous_materials_research_mission.v1.json"
    )

    program = build_research_program(
        mission,
        repository_root=repository_root,
    )

    assert program["schema_version"] == "1.0"
    assert program["program_policy_version"] == "1.0"
    assert program["mission"]["mission_id"] == "autonomous-materials-research-v1"
    assert program["autonomy_boundary"] == {
        "goal_generation_performed": True,
        "scientific_hypotheses_invented": False,
        "reasoning_proposals_may_be_schema_validated": True,
        "typed_action_execution_performed": False,
        "network_access_performed": False,
        "physical_experiment_execution_available": False,
        "scientific_evidence_upgraded": False,
    }

    states = {item["workstream_id"]: item for item in program["workstreams"]}
    assert set(states) == {
        "nist-ambench",
        "nasa-battery",
        "tm-fe-si-characterization",
        "materials-project-external-source",
    }
    assert states["nasa-battery"]["status"] == "runtime_context_required"
    assert states["nasa-battery"]["planning_state"] is None
    assert states["nist-ambench"]["status"] == "verified"
    assert states["tm-fe-si-characterization"]["status"] == "verified"
    assert states["materials-project-external-source"]["status"] == "verified"

    goals = {item["workstream_id"]: item for item in program["generated_goals"]}
    assert goals["nasa-battery"]["status"] == "runtime_context_required"
    assert goals["nasa-battery"]["scientific_hypothesis_generation_status"] == (
        "blocked_by_missing_runtime_context"
    )
    assert goals["nist-ambench"]["expected_information_gain"]["status"] == (
        "not_quantified"
    )
    assert all(goal["epistemic_hypothesis"]["scientific_mechanism_claim"] is False for goal in goals.values())

    next_step = program["next_program_step"]
    assert next_step["workstream_id"] == "nist-ambench"
    assert next_step["automatic_execution_authorized"] is False
