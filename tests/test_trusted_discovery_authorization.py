from __future__ import annotations

from pathlib import Path

import pytest

from materials_data_analyzer.research_loop.self_directed_research import (
    build_self_directed_research_plan,
)
from materials_data_analyzer.research_loop.trusted_discovery_authorization import (
    TrustedDiscoveryAuthorizationError,
    authorize_mission_pinned_trusted_discovery,
    compile_trusted_discovery_handoff,
)

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "configs" / "research" / "trusted_source_discovery_policy.v1.json"
POLICY_SHA = "494757ff5a3924b364da11d5364afed22cc45c1c70a59fa35669000050f70ec8"


def _program(*, pinned: bool = True, provider_gap: str = "Independent raw source dataset with checksum"):
    mission = {
        "autonomy_policy": {
            "goal_generation": "bounded_autonomous",
            "reasoning_proposals": "schema_validated",
            "typed_computational_actions": "explicit_request",
            "network_evidence_search": "explicit_authorization",
            "physical_experiment_execution": "external_only",
        }
    }
    if pinned:
        mission["source_trust_policy_pins"] = [
            {"policy_id": "trusted-source-discovery-v1", "sha256": POLICY_SHA}
        ]
    return {
        "mission": mission,
        "generated_goals": [
            {
                "goal_id": "mission:external-source",
                "workstream_id": "materials-project-external-source",
                "research_question": "What external evidence resolves the current gap?",
                "goal_statement": "Resolve the external evidence gap.",
                "status": "active",
                "priority": 85,
                "evidence_requirements": [provider_gap],
                "claim_boundary": {"scientific_status": "inconclusive"},
                "action_frontier": [],
            }
        ],
    }


def test_exact_mission_pin_satisfies_existing_explicit_authorization_gate():
    policy_bytes = POLICY_PATH.read_bytes()
    program = _program()
    plan = build_self_directed_research_plan(program)
    assert plan["selected_next_action"]["action_class"] == "external_evidence_search"
    assert plan["selected_next_action"]["execution_mode"] == "explicit_authorization_required"

    handoff = compile_trusted_discovery_handoff(
        program,
        plan,
        trusted_policy_bytes=policy_bytes,
    )

    assert handoff["authorization"]["human_approval_required"] is False
    assert handoff["planner_gate_bypassed"] is False
    assert handoff["planner_gate_satisfied_by_pinned_policy"] is True
    assert handoff["authorization"]["scientific_status_upgrade_authorized"] is False


def test_tampered_policy_bytes_do_not_satisfy_standing_authorization():
    tampered = POLICY_PATH.read_bytes().replace(b"exception_only", b"exception-only")
    with pytest.raises(TrustedDiscoveryAuthorizationError, match="exact mission pin"):
        authorize_mission_pinned_trusted_discovery(
            _program(),
            trusted_policy_bytes=tampered,
        )


def test_missing_mission_pin_requires_real_authorization_instead_of_auto():
    with pytest.raises(TrustedDiscoveryAuthorizationError, match="pin"):
        authorize_mission_pinned_trusted_discovery(
            _program(pinned=False),
            trusted_policy_bytes=POLICY_PATH.read_bytes(),
        )


def test_unknown_provider_never_inherits_standing_nist_authorization():
    with pytest.raises(TrustedDiscoveryAuthorizationError, match="provider"):
        authorize_mission_pinned_trusted_discovery(
            _program(),
            trusted_policy_bytes=POLICY_PATH.read_bytes(),
            provider="arbitrary_web",
        )


def test_non_search_selected_action_cannot_be_routed_through_discovery_policy():
    program = _program("Predeclared sensitivity and residual robustness analysis")
    plan = build_self_directed_research_plan(program)
    assert plan["selected_next_action"]["action_class"] == "sensitivity_analysis"
    with pytest.raises(TrustedDiscoveryAuthorizationError, match="only external_evidence_search"):
        compile_trusted_discovery_handoff(
            program,
            plan,
            trusted_policy_bytes=POLICY_PATH.read_bytes(),
        )


def test_disabled_network_policy_cannot_be_overridden_by_policy_pin():
    program = _program()
    program["mission"]["autonomy_policy"]["network_evidence_search"] = "disabled"
    with pytest.raises(TrustedDiscoveryAuthorizationError, match="does not require"):
        authorize_mission_pinned_trusted_discovery(
            program,
            trusted_policy_bytes=POLICY_PATH.read_bytes(),
        )
