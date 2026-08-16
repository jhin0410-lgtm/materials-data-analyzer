from __future__ import annotations

from materials_data_analyzer.research_loop.critic_inquiry_adapter import (
    adapt_scientific_critic_report,
)
from materials_data_analyzer.research_loop.research_agent import (
    build_research_agent_iteration,
)


def _program() -> dict[str, object]:
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
                "goal_id": "mission:test:resolve-current-blocker",
                "workstream_id": "test",
                "research_question": "Is the claim robust?",
                "goal_statement": "Resolve raw independent source evidence gap.",
                "status": "active",
                "priority": 90,
                "evidence_requirements": ["Raw independent source dataset with checksum"],
                "claim_boundary": {"scientific_status": "inconclusive"},
                "action_frontier": [],
            }
        ],
    }


def _critic() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "critic_policy_version": "1.0",
        "critic_hardening_policy_version": "1.9",
        "target_reports": [
            {
                "target_node_id": "h1",
                "critic_findings": [
                    {
                        "finding_id": "critic:h1:counterevidence-gap",
                        "code": "NO_DOMAIN_VERIFIED_COUNTEREVIDENCE",
                    }
                ],
                "methodological_alternatives": [
                    {
                        "alternative_id": "critic:h1:artifact-or-selection",
                        "alternative_type": "methodological_not_domain_mechanism",
                        "statement": "The apparent support may be an artifact.",
                        "falsification_criteria": ["Independent evidence reproduces the effect."],
                        "discriminating_evidence": ["Independent evidence"],
                        "proposal_status": "proposed_not_evidence_upgraded",
                        "scientific_mechanism_claim": False,
                    }
                ],
                "discriminating_actions": [
                    {
                        "action_id": "critic:h1:robustness-sensitivity",
                        "action_class": "sensitivity_analysis",
                        "description": "Plan robustness sensitivity checks.",
                        "rationale": "Test an artifact alternative.",
                        "execution_mode": "plan_only",
                        "information_gain_priority": "high",
                        "information_gain_is_calibrated_probability": False,
                        "expected_discrimination": "Tests robustness.",
                        "automatic_execution_authorized": False,
                        "availability_asserted": False,
                    }
                ],
                "stop_recommendation": {
                    "recommendation": "continue_discriminating_research",
                    "automatic_stop_authorized": False,
                },
            }
        ],
    }


def test_adapter_consumes_current_target_reports_contract() -> None:
    adapted = adapt_scientific_critic_report(_critic())

    assert adapted["targets"][0]["target_node_id"] == "h1"
    assert adapted["targets"][0]["alternatives"][0]["alternative_id"] == (
        "critic:h1:artifact-or-selection"
    )
    action = adapted["targets"][0]["proposed_actions"][0]
    assert action["action_id"] == "critic:h1:robustness-sensitivity"
    assert action["availability_asserted"] is False
    assert action["feasibility_score"] == 0.0
    assert adapted["projection_boundary"]["critic_action_availability_inferred"] is False


def test_research_agent_includes_critic_alternative_but_does_not_select_unavailable_action() -> None:
    plan = build_research_agent_iteration(_program(), scientific_critic_report=_critic())

    ids = {
        item.get("alternative_id") or item.get("hypothesis_id")
        for item in plan["candidate_hypotheses"]
    }
    assert "critic:h1:artifact-or-selection" in ids
    critic_action = next(
        item
        for item in plan["ranked_actions"]
        if item["action_id"] == "critic:h1:robustness-sensitivity"
    )
    assert critic_action["utility_score"] == 0.0
    assert plan["selected_next_action"]["origin"] == "self_generated_from_evidence_gap"
    assert plan["scientific_critic_adapter"]["current_public_critic_contract_consumed"] is True
    assert plan["autonomy_boundary"]["scientific_status_changed"] is False
