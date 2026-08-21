from __future__ import annotations

import hashlib
import json

import pytest

from materials_data_analyzer.research_loop.hypothesis_portfolio import (
    HypothesisPortfolioError,
    build_hypothesis_portfolio,
    validate_hypothesis_portfolio_for_plan,
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


def _plan() -> dict:
    plan = {
        "schema_version": "1.0",
        "iteration_index": 1,
        "planning_budget": {"budget_units": 8.0, "minimum_utility": 0.01},
        "ranked_actions": [],
        "selected_next_action": None,
        "stop_decision": {"stop": False, "reason": "informative_action_available"},
    }
    plan["plan_sha256"] = _canonical_sha256(plan)
    return plan


def _assessment(
    status: str,
    *,
    support: tuple[str, ...] = (),
    contradiction: tuple[str, ...] = (),
    falsification: tuple[str, ...] = (),
) -> dict:
    return {
        "node_id": "h1",
        "node_type": "hypothesis",
        "status": status,
        "verified_support_edges": list(support),
        "verified_contradiction_edges": list(contradiction),
        "verified_falsification_edges": list(falsification),
        "diagnostic_relation_edges": [],
        "final_positive_support_granted": False,
        "domain_closeout_required_for_positive_conclusion": status
        == "provisionally_supported",
        "confidence_score": None,
    }


def _graph(assessment: dict, *, hypothesis_id: str = "h1") -> dict:
    item = dict(assessment)
    item["node_id"] = hypothesis_id
    return {
        "schema_version": "1.0",
        "graph_policy_version": "1.0",
        "graph_id": "graph-1",
        "research_scope": "bounded post-MVP hypothesis tracking",
        "nodes": [
            {
                "node_id": hypothesis_id,
                "node_type": "hypothesis",
                "statement": "The target relation survives the declared discrimination test.",
            }
        ],
        "edges": [],
        "assessments": [item],
        "conflict_count": int(item["status"] == "contested"),
        "falsified_count": int(item["status"] == "falsified_within_verified_scope"),
        "autonomy_boundary": {
            "proposal_relations_affect_status": False,
            "diagnostic_relations_affect_verified_status": False,
            "domain_verified_relations_require_checksum_bound_verifier_artifacts": True,
            "final_positive_support_is_automatic": False,
            "numeric_confidence_invented": False,
        },
    }


@pytest.mark.parametrize(
    ("assessment", "state", "directive"),
    [
        (
            _assessment("inconclusive"),
            "active_discrimination_required",
            "continue_bounded_discrimination",
        ),
        (
            _assessment("provisionally_supported", support=("support-1",)),
            "positive_closeout_required",
            "domain_closeout_required",
        ),
        (
            _assessment(
                "contested",
                support=("support-1",),
                contradiction=("contradiction-1",),
            ),
            "contested_discrimination_required",
            "prioritize_discrimination",
        ),
        (
            _assessment(
                "contradicted_within_verified_scope",
                contradiction=("contradiction-1",),
            ),
            "challenge_or_retirement_review",
            "continue_bounded_discrimination",
        ),
        (
            _assessment(
                "falsified_within_verified_scope",
                falsification=("falsifier-1",),
            ),
            "retired_falsified_within_verified_scope",
            "bounded_stop_all_hypotheses_retired",
        ),
    ],
)
def test_epistemic_status_maps_to_bounded_portfolio_state(
    assessment: dict,
    state: str,
    directive: str,
) -> None:
    portfolio = build_hypothesis_portfolio(_graph(assessment), plan=_plan())

    assert portfolio["hypothesis_count"] == 1
    assert portfolio["hypotheses"][0]["portfolio_state"] == state
    assert portfolio["portfolio_directive"] == directive
    assert portfolio["hypotheses"][0]["final_positive_support_granted"] is False
    assert portfolio["hypotheses"][0]["confidence_score"] is None
    assert portfolio["autonomy_boundary"]["scientific_status_changed"] is False
    assert portfolio["autonomy_boundary"]["execution_authorized"] is False


def test_new_verified_edges_advance_portfolio_state_with_exact_ancestry() -> None:
    plan1 = _plan()
    prior = build_hypothesis_portfolio(
        _graph(_assessment("inconclusive")),
        plan=plan1,
    )
    plan2 = _plan()
    plan2["iteration_index"] = 2
    plan2.pop("plan_sha256")
    plan2["plan_sha256"] = _canonical_sha256(plan2)
    current = build_hypothesis_portfolio(
        _graph(
            _assessment(
                "contested",
                support=("support-1",),
                contradiction=("contradiction-1",),
            )
        ),
        plan=plan2,
        previous_portfolio=prior,
    )

    assert current["previous_portfolio_sha256"] == prior["portfolio_sha256"]
    assert current["hypotheses"][0]["transition"] == (
        "advanced_by_new_verified_epistemic_evidence"
    )
    assert current["portfolio_directive"] == "prioritize_discrimination"


def test_previous_portfolio_tampering_fails_closed() -> None:
    prior = build_hypothesis_portfolio(
        _graph(_assessment("inconclusive")),
        plan=_plan(),
    )
    prior["hypotheses"][0]["statement"] = "tampered"

    with pytest.raises(HypothesisPortfolioError, match="canonical SHA-256"):
        build_hypothesis_portfolio(
            _graph(_assessment("inconclusive")),
            plan=_plan(),
            previous_portfolio=prior,
        )


def test_verified_edge_removal_is_not_treated_as_hypothesis_recovery() -> None:
    prior = build_hypothesis_portfolio(
        _graph(_assessment("provisionally_supported", support=("support-1",))),
        plan=_plan(),
    )

    with pytest.raises(HypothesisPortfolioError, match="verified epistemic edges were removed"):
        build_hypothesis_portfolio(
            _graph(_assessment("inconclusive")),
            plan=_plan(),
            previous_portfolio=prior,
        )


def test_falsified_hypothesis_cannot_silently_reactivate() -> None:
    prior = build_hypothesis_portfolio(
        _graph(
            _assessment(
                "falsified_within_verified_scope",
                falsification=("falsifier-1",),
            )
        ),
        plan=_plan(),
    )
    inconsistent_current = _assessment(
        "inconclusive",
        falsification=("falsifier-1",),
    )

    with pytest.raises(HypothesisPortfolioError, match="cannot silently reactivate"):
        build_hypothesis_portfolio(
            _graph(inconsistent_current),
            plan=_plan(),
            previous_portfolio=prior,
        )


def test_previous_hypothesis_node_cannot_disappear_silently() -> None:
    prior = build_hypothesis_portfolio(
        _graph(_assessment("inconclusive")),
        plan=_plan(),
    )

    with pytest.raises(HypothesisPortfolioError, match="cannot disappear"):
        build_hypothesis_portfolio(
            _graph(_assessment("inconclusive"), hypothesis_id="h2"),
            plan=_plan(),
            previous_portfolio=prior,
        )


def test_plan_sha_binding_detects_planning_cycle_mutation() -> None:
    plan = _plan()
    plan["iteration_index"] = 99

    with pytest.raises(HypothesisPortfolioError, match="plan.plan_sha256 mismatch"):
        build_hypothesis_portfolio(
            _graph(_assessment("inconclusive")),
            plan=plan,
        )


def test_portfolio_validation_requires_the_exact_current_plan() -> None:
    plan = _plan()
    portfolio = build_hypothesis_portfolio(
        _graph(_assessment("inconclusive")),
        plan=plan,
    )
    binding = validate_hypothesis_portfolio_for_plan(portfolio, plan=plan)
    assert binding["portfolio_sha256"] == portfolio["portfolio_sha256"]
    assert binding["portfolio_directive"] == "continue_bounded_discrimination"

    other_plan = _plan()
    other_plan["iteration_index"] = 2
    other_plan.pop("plan_sha256")
    other_plan["plan_sha256"] = _canonical_sha256(other_plan)
    with pytest.raises(HypothesisPortfolioError, match="current planning cycle"):
        validate_hypothesis_portfolio_for_plan(portfolio, plan=other_plan)
