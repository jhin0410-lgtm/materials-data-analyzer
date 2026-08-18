from __future__ import annotations

from materials_data_analyzer.research_loop.autonomous_decision_integration import (
    build_autonomous_decision_report,
)
from materials_data_analyzer.research_loop.autonomous_episode_step import (
    decision_report_to_episode_step,
)
from materials_data_analyzer.research_loop.persistent_autonomous_episode import (
    apply_persistent_step,
    open_or_create_episode,
)


def _plan(*, stop: bool = False) -> dict:
    action = {
        "action_id": "gap:search",
        "action_class": "external_evidence_search",
        "execution_mode": "explicit_authorization_required",
        "cost_units": 2.0,
        "utility_score": 0.5,
        "physical_experiment_execution_authorized": False,
    }
    return {
        "planning_budget": {"budget_units": 8.0, "minimum_utility": 0.01},
        "ranked_actions": [action],
        "selected_next_action": None if stop else action,
        "stop_decision": {
            "stop": stop,
            "reason": "mission_scope_exhausted" if stop else "informative_action_available",
        },
    }


def test_decision_step_persists_exact_report_binding_without_charging_execution_cost(tmp_path) -> None:
    plan = _plan()
    report = build_autonomous_decision_report(plan)
    step = decision_report_to_episode_step(
        plan=plan,
        decision_report=report,
        evidence_refs=["evidence:real-source-1"],
        unresolved_gaps=["sample_lineage_pending"],
        review_queue=["review:semantic-contract"],
        blockers=["human_review_required"],
    )
    checkpoint = tmp_path / "episode.json"
    state = open_or_create_episode(
        checkpoint,
        episode_id="episode-real-1",
        research_question="Can the acquired evidence resolve the declared gap?",
        mission_id="mission-1",
        objectives=["Resolve evidence gap without scientific over-promotion"],
        max_iterations=4,
        cost_budget=8.0,
    )
    updated = apply_persistent_step(checkpoint, state, step)
    assert updated["iteration"] == 1
    assert updated["status"] == "blocked"
    assert updated["budgets"]["cost_consumed"] == 0.0
    assert updated["evidence_refs"] == ["evidence:real-source-1"]
    assert updated["review_queue"] == ["review:semantic-contract"]
    assert updated["action_history"][0]["artifact_refs"] == [
        f"decision-report-sha256:{report['report_sha256']}"
    ]


def test_upstream_stop_becomes_terminal_bounded_stop_without_scientific_promotion() -> None:
    plan = _plan(stop=True)
    report = build_autonomous_decision_report(plan)
    step = decision_report_to_episode_step(plan=plan, decision_report=report)
    assert step["episode_status"] == "stopped"
    assert step["conclusion"]["kind"] == "bounded_stop_without_scientific_promotion"
    assert step["conclusion"]["scientific_status_changed"] is False
    assert step["cost_units"] == 0.0
