from __future__ import annotations

import hashlib
import json

from materials_data_analyzer.research_loop.autonomous_decision_integration import (
    build_autonomous_decision_report,
)
from materials_data_analyzer.research_loop.autonomous_episode_step import (
    decision_report_to_episode_step,
)
from materials_data_analyzer.research_loop.hypothesis_portfolio import (
    build_hypothesis_portfolio,
)
from materials_data_analyzer.research_loop.persistent_autonomous_episode import (
    apply_persistent_step,
    open_or_create_episode,
)


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _plan(*, stop: bool = False, bind_sha: bool = False) -> dict:
    action = {
        "action_id": "gap:search",
        "action_class": "external_evidence_search",
        "execution_mode": "explicit_authorization_required",
        "cost_units": 2.0,
        "utility_score": 0.5,
        "physical_experiment_execution_authorized": False,
    }
    plan = {
        "planning_budget": {"budget_units": 8.0, "minimum_utility": 0.01},
        "ranked_actions": [action],
        "selected_next_action": None if stop else action,
        "stop_decision": {
            "stop": stop,
            "reason": "mission_scope_exhausted" if stop else "informative_action_available",
        },
    }
    if bind_sha:
        plan["plan_sha256"] = _canonical_sha256(plan)
    return plan


def _portfolio(plan: dict, status: str) -> dict:
    support = ["support-1"] if status == "provisionally_supported" else []
    falsification = ["falsifier-1"] if status == "falsified_within_verified_scope" else []
    graph = {
        "schema_version": "1.0",
        "graph_policy_version": "1.0",
        "graph_id": "episode-portfolio-graph",
        "research_scope": "persistent episode hypothesis state",
        "nodes": [
            {
                "node_id": "h1",
                "node_type": "hypothesis",
                "statement": "The target relation survives the bounded test.",
            }
        ],
        "edges": [],
        "assessments": [
            {
                "node_id": "h1",
                "node_type": "hypothesis",
                "status": status,
                "verified_support_edges": support,
                "verified_contradiction_edges": [],
                "verified_falsification_edges": falsification,
                "diagnostic_relation_edges": [],
                "final_positive_support_granted": False,
                "domain_closeout_required_for_positive_conclusion": status
                == "provisionally_supported",
                "confidence_score": None,
            }
        ],
        "conflict_count": 0,
        "falsified_count": int(status == "falsified_within_verified_scope"),
        "autonomy_boundary": {
            "proposal_relations_affect_status": False,
            "diagnostic_relations_affect_verified_status": False,
            "domain_verified_relations_require_checksum_bound_verifier_artifacts": True,
            "final_positive_support_is_automatic": False,
            "numeric_confidence_invented": False,
        },
    }
    return build_hypothesis_portfolio(graph, plan=plan)


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


def test_portfolio_sha_is_persisted_beside_decision_report_sha() -> None:
    plan = _plan(bind_sha=True)
    portfolio = _portfolio(plan, "inconclusive")
    report = build_autonomous_decision_report(plan, hypothesis_portfolio=portfolio)
    step = decision_report_to_episode_step(plan=plan, decision_report=report)

    assert step["artifact_refs"] == [
        f"decision-report-sha256:{report['report_sha256']}",
        f"hypothesis-portfolio-sha256:{portfolio['portfolio_sha256']}",
    ]
    assert step["episode_status"] == "active"
    assert step["iteration_status"] == "decision_recorded"


def test_provisional_support_becomes_episode_blocked_for_domain_closeout() -> None:
    plan = _plan(bind_sha=True)
    portfolio = _portfolio(plan, "provisionally_supported")
    report = build_autonomous_decision_report(plan, hypothesis_portfolio=portfolio)
    step = decision_report_to_episode_step(plan=plan, decision_report=report)

    assert report["selected_action"] is None
    assert step["episode_status"] == "blocked"
    assert step["iteration_status"] == "decision_blocked_pending_domain_closeout"
    assert step["conclusion"] is None


def test_all_falsified_hypotheses_become_bounded_episode_stop() -> None:
    plan = _plan(bind_sha=True)
    portfolio = _portfolio(plan, "falsified_within_verified_scope")
    report = build_autonomous_decision_report(plan, hypothesis_portfolio=portfolio)
    step = decision_report_to_episode_step(plan=plan, decision_report=report)

    assert report["selected_action"] is None
    assert step["episode_status"] == "stopped"
    assert step["iteration_status"] == "bounded_stop_all_hypotheses_retired"
    assert step["conclusion"]["kind"] == "bounded_stop_without_scientific_promotion"
    assert step["conclusion"]["reason"] == (
        "all_graph_hypotheses_falsified_within_verified_scope"
    )
    assert step["conclusion"]["scientific_status_changed"] is False
