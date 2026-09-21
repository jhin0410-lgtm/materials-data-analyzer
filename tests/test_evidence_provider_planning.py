from __future__ import annotations

import copy

import pytest

from materials_data_analyzer.research_loop.autonomous_inquiry import (
    build_autonomous_inquiry_plan,
)
from materials_data_analyzer.research_loop.evidence_packet import canonical_sha256
from materials_data_analyzer.research_loop.evidence_provider_contract import (
    AuthenticatedProviderStateInput,
    finalize_provider_state,
)
from materials_data_analyzer.research_loop.evidence_provider_planning import (
    EvidenceProviderPlanningError,
    apply_provider_state_transition,
    build_provider_planner_program_state,
    build_provider_state_transition,
    build_provider_successor_planner_program_state,
    deserialize_authenticated_provider_inputs,
    serialize_authenticated_provider_inputs,
    validate_provider_input_successor,
    validate_provider_planner_program_state,
    validate_provider_state_transition,
    validate_provider_successor_planner_program_state,
)


def _provider_state(
    provider_id: str,
    *,
    requirement_id: str | None,
    description: str = "Acquire missing evidence.",
    action_class: str = "evidence_acquisition",
    source_sha: str = "a" * 64,
) -> dict:
    requirements = []
    if requirement_id is not None:
        requirements.append(
            {
                "requirement_id": requirement_id,
                "requirement_class": action_class,
                "action_class": action_class,
                "description": description,
                "status": "unresolved",
                "source_binding_ids": ["source-1"],
                "automatic_execution_authorized": False,
                "scientific_status_promoted": False,
            }
        )
    return finalize_provider_state(
        {
            "schema_version": "1.0",
            "policy_version": "1.0",
            "provider_state_type": "evidence_provider_state",
            "provider": {
                "provider_id": provider_id,
                "contract_version": "1.0",
                "schema_version": "1.0",
                "adapter_id": f"{provider_id}-adapter-v1",
            },
            "domain": f"{provider_id}-domain",
            "modality": "test-modality",
            "subject_scope": "bounded test subject",
            "source_bindings": [
                {
                    "binding_id": "source-1",
                    "role": "verified_source",
                    "sha256": source_sha,
                    "binding_kind": "artifact_sha256",
                    "locator": None,
                }
            ],
            "readiness": {
                "status": "blocked" if requirements else "ready",
                "maturity_label": None,
                "maturity_index": None,
                "first_blocker": requirement_id,
            },
            "unresolved_requirements": requirements,
            "authority_boundary": {
                "planning_metadata_only": True,
                "empirical_evidence_created": False,
                "scientific_status_promoted": False,
                "downstream_use_authorized": False,
                "execution_authorized": False,
            },
        }
    )


def _auth(state: dict) -> AuthenticatedProviderStateInput:
    return AuthenticatedProviderStateInput(
        state=state,
        trusted_provider_state_sha256=state["provider_state_sha256"],
    )


def _base_program() -> dict:
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
                "goal_id": "existing:goal",
                "workstream_id": "existing",
                "research_question": "Can the existing bounded analysis reduce uncertainty?",
                "goal_statement": "Run only the already available bounded analysis.",
                "status": "active",
                "priority": "high",
                "evidence_requirements": ["bounded analysis result"],
                "claim_boundary": {"scientific_status": "unchanged"},
                "action_frontier": [
                    {
                        "action_id": "existing:analysis",
                        "action_class": "existing_data_reanalysis",
                        "description": "Run the existing bounded analysis.",
                        "rationale": "Resolve an already verified analysis gap.",
                        "execution_mode": "plan_only",
                        "expected_information_score": 0.8,
                        "hypothesis_discrimination_score": 0.8,
                        "feasibility_score": 0.9,
                        "cost_units": 1.0,
                        "risk_penalty": 0.0,
                    }
                ],
            }
        ],
    }


def _rehash_transition(value: dict) -> dict:
    result = copy.deepcopy(value)
    result.pop("transition_sha256", None)
    result["transition_sha256"] = canonical_sha256(result)
    return result


def test_provider_overlay_adds_planning_gaps_without_creating_candidates() -> None:
    simulation_provider = _provider_state(
        "simulation-provider",
        requirement_id="sim-gap",
        description="Run a bounded simulation only if an independently matched candidate exists.",
        action_class="simulation",
    )
    program = build_provider_planner_program_state(
        _base_program(),
        [_auth(simulation_provider)],
    )
    provider_goals = [
        item
        for item in program["generated_goals"]
        if item.get("provider_requirement_overlay") is True
    ]
    assert len(provider_goals) == 1
    assert provider_goals[0]["action_frontier"] == []
    assert (
        provider_goals[0]["claim_boundary"]["requested_action_semantics"]
        == "simulation"
    )

    plan = build_autonomous_inquiry_plan(program)
    assert plan["selected_next_action"]["action_id"] == "existing:analysis"
    assert {item["action_id"] for item in plan["ranked_actions"]} == {
        "existing:analysis"
    }
    assert any(
        "independently matched candidate" in item["requirement"]
        for item in plan["evidence_gaps"]
    )
    assert program["evidence_provider_binding"][
        "requirements_projected_as_candidate_actions"
    ] is False
    assert program["evidence_provider_binding"][
        "exact_candidate_matching_required"
    ] is True


def test_provider_overlay_without_existing_candidates_stops_instead_of_inventing_action() -> None:
    provider = _provider_state(
        "acquisition-provider",
        requirement_id="source-gap",
        action_class="evidence_acquisition",
    )
    base = _base_program()
    base["generated_goals"][0]["action_frontier"] = []
    program = build_provider_planner_program_state(base, [_auth(provider)])
    plan = build_autonomous_inquiry_plan(program)

    assert plan["ranked_actions"] == []
    assert plan["selected_next_action"] is None
    assert plan["stop_decision"]["stop"] is True
    assert plan["stop_decision"]["reason"] == "no_affordable_informative_action"


def test_provider_overlay_verifier_rejects_provider_goal_candidate_injection() -> None:
    provider = _provider_state("characterization-provider", requirement_id="l5-gap")
    program = build_provider_planner_program_state(
        _base_program(),
        [_auth(provider)],
    )
    forged = copy.deepcopy(program)
    provider_goal = next(
        item
        for item in forged["generated_goals"]
        if item.get("provider_requirement_overlay") is True
    )
    provider_goal["action_frontier"] = [
        {
            "action_id": "forged:auto",
            "action_class": "external_evidence_search",
        }
    ]

    with pytest.raises(
        EvidenceProviderPlanningError,
        match="provider goals differ|may not create planner action candidates",
    ):
        validate_provider_planner_program_state(
            forged,
            [_auth(provider)],
        )


def test_provider_namespace_cannot_be_used_by_unbound_goal() -> None:
    provider = _provider_state("characterization-provider", requirement_id="l5-gap")
    program = build_provider_planner_program_state(
        _base_program(),
        [_auth(provider)],
    )
    forged = copy.deepcopy(program)
    forged["generated_goals"].append(
        {
            "goal_id": "provider:forged:goal",
            "workstream_id": "provider:forged",
            "research_question": "forged",
            "goal_statement": "forged",
            "status": "active",
            "priority": "high",
            "evidence_requirements": ["forged"],
            "claim_boundary": {},
            "action_frontier": [],
        }
    )
    with pytest.raises(
        EvidenceProviderPlanningError,
        match="provider namespace goal",
    ):
        validate_provider_planner_program_state(
            forged,
            [_auth(provider)],
        )


def test_provider_binding_rejects_bool_int_alias() -> None:
    provider = _provider_state("characterization-provider", requirement_id="l5-gap")
    program = build_provider_planner_program_state(
        _base_program(),
        [_auth(provider)],
    )
    assert program["evidence_provider_binding"]["provider_requirement_count"] == 1
    forged = copy.deepcopy(program)
    forged["evidence_provider_binding"]["provider_requirement_count"] = True

    with pytest.raises(
        EvidenceProviderPlanningError,
        match="provider binding differs",
    ):
        validate_provider_planner_program_state(
            forged,
            [_auth(provider)],
        )


def test_authenticated_provider_inputs_round_trip_and_reject_trust_substitution() -> None:
    state = _provider_state("provider-a", requirement_id="gap-a")
    serialized = serialize_authenticated_provider_inputs([_auth(state)])
    restored = deserialize_authenticated_provider_inputs(serialized)
    assert restored[0].trusted_provider_state_sha256 == state["provider_state_sha256"]

    forged = copy.deepcopy(serialized)
    forged[0]["trusted_provider_state_sha256"] = "f" * 64
    with pytest.raises(
        EvidenceProviderPlanningError,
        match="external trust root mismatch",
    ):
        deserialize_authenticated_provider_inputs(forged)


def test_provider_transition_changes_exactly_one_provider_and_preserves_other_sha() -> None:
    first = _provider_state("provider-a", requirement_id="gap-a", source_sha="a" * 64)
    second = _provider_state("provider-b", requirement_id="gap-b", source_sha="b" * 64)
    replacement = _provider_state(
        "provider-a",
        requirement_id="gap-a2",
        description="Acquire newly identified calibration evidence.",
        source_sha="c" * 64,
    )
    transition = build_provider_state_transition(
        [_auth(first), _auth(second)],
        _auth(replacement),
    )

    assert transition["provider_id"] == "provider-a"
    assert transition["state_changed"] is True
    assert transition["next_planning_cycle_required"] is True
    assert transition["stop_reason"] is None
    assert transition["unchanged_provider_state_sha256s"] == [
        {
            "provider_id": "provider-b",
            "provider_state_sha256": second["provider_state_sha256"],
        }
    ]
    assert transition["authority_boundary"]["execution_authorized"] is False


def test_same_provider_state_transition_is_no_new_information_stop() -> None:
    first = _provider_state("provider-a", requirement_id="gap-a")
    second = _provider_state("provider-b", requirement_id="gap-b", source_sha="b" * 64)
    transition = build_provider_state_transition(
        [_auth(first), _auth(second)],
        _auth(first),
    )

    assert transition["state_changed"] is False
    assert transition["next_planning_cycle_required"] is False
    assert transition["stop_reason"] == "no_new_provider_information"
    assert (
        transition["previous_aggregate_sha256"]
        == transition["current_aggregate_sha256"]
    )


def test_recursive_provider_successor_rejects_multiple_provider_changes() -> None:
    first_a = _provider_state("provider-a", requirement_id="gap-a", source_sha="a" * 64)
    first_b = _provider_state("provider-b", requirement_id="gap-b", source_sha="b" * 64)
    second_a = _provider_state("provider-a", requirement_id="gap-a2", source_sha="c" * 64)
    second_b = _provider_state("provider-b", requirement_id="gap-b2", source_sha="d" * 64)

    with pytest.raises(
        EvidenceProviderPlanningError,
        match="at most one provider state",
    ):
        validate_provider_input_successor(
            [_auth(first_a), _auth(first_b)],
            [_auth(second_a), _auth(second_b)],
        )


def test_recursive_provider_successor_requires_transition_for_changed_provider() -> None:
    first = _provider_state("provider-a", requirement_id="gap-a")
    replacement = _provider_state(
        "provider-a",
        requirement_id="gap-a2",
        source_sha="c" * 64,
    )
    with pytest.raises(
        EvidenceProviderPlanningError,
        match="requires an authenticated single-provider transition",
    ):
        validate_provider_input_successor(
            [_auth(first)],
            [_auth(replacement)],
        )


def test_recursive_provider_successor_validates_exact_single_provider_transition() -> None:
    first_a = _provider_state("provider-a", requirement_id="gap-a", source_sha="a" * 64)
    first_b = _provider_state("provider-b", requirement_id="gap-b", source_sha="b" * 64)
    replacement = _provider_state(
        "provider-a",
        requirement_id="gap-a2",
        source_sha="c" * 64,
    )
    transition = build_provider_state_transition(
        [_auth(first_a), _auth(first_b)],
        _auth(replacement),
    )
    verified = validate_provider_input_successor(
        [_auth(first_a), _auth(first_b)],
        [_auth(replacement), _auth(first_b)],
        transition=transition,
    )

    assert verified["changed_provider_count"] == 1
    assert verified["changed_provider_id"] == "provider-a"
    assert verified["state_changed"] is True
    assert verified["multiple_provider_changes_accepted"] is False
    assert len(verified["successor_verification_sha256"]) == 64


def test_recursive_provider_successor_rejects_provider_add_remove() -> None:
    first = _provider_state("provider-a", requirement_id="gap-a")
    added = _provider_state("provider-b", requirement_id="gap-b", source_sha="b" * 64)
    with pytest.raises(
        EvidenceProviderPlanningError,
        match="may not add or remove provider identities",
    ):
        validate_provider_input_successor(
            [_auth(first)],
            [_auth(first), _auth(added)],
        )


def test_provider_successor_planner_is_not_built_without_new_provider_information() -> None:
    first = _provider_state("provider-a", requirement_id="gap-a")
    result = build_provider_successor_planner_program_state(
        _base_program(),
        [_auth(first)],
        _auth(first),
    )

    assert result["next_planning_cycle_required"] is False
    assert result["stop_reason"] == "no_new_provider_information"
    assert result["successor_planner_program_state"] is None
    assert result["authority_boundary"]["execution_authorized"] is False


def test_provider_successor_replaces_verified_prior_overlay_in_place() -> None:
    first = _provider_state("provider-a", requirement_id="gap-a")
    replacement = _provider_state(
        "provider-a",
        requirement_id="gap-a2",
        description="Acquire replacement evidence.",
        source_sha="c" * 64,
    )
    previous_program = build_provider_planner_program_state(
        _base_program(),
        [_auth(first)],
    )

    result = build_provider_successor_planner_program_state(
        previous_program,
        [_auth(first)],
        _auth(replacement),
    )

    successor = result["successor_planner_program_state"]
    assert successor is not None
    non_provider = [
        item
        for item in successor["generated_goals"]
        if item.get("provider_requirement_overlay") is not True
    ]
    assert [item["goal_id"] for item in non_provider] == ["existing:goal"]
    provider_goals = [
        item
        for item in successor["generated_goals"]
        if item.get("provider_requirement_overlay") is True
    ]
    assert len(provider_goals) == 1
    assert provider_goals[0]["claim_boundary"]["requirement_id"] == "gap-a2"
    assert "gap-a" not in provider_goals[0]["goal_statement"]


def test_provider_successor_rejects_tampered_prior_overlay_before_replacement() -> None:
    first = _provider_state("provider-a", requirement_id="gap-a")
    replacement = _provider_state(
        "provider-a",
        requirement_id="gap-a2",
        source_sha="c" * 64,
    )
    previous_program = build_provider_planner_program_state(
        _base_program(),
        [_auth(first)],
    )
    forged = copy.deepcopy(previous_program)
    provider_goal = next(
        item
        for item in forged["generated_goals"]
        if item.get("provider_requirement_overlay") is True
    )
    provider_goal["goal_statement"] = "forged prior provider requirement"

    with pytest.raises(
        EvidenceProviderPlanningError,
        match="provider goals differ",
    ):
        build_provider_successor_planner_program_state(
            forged,
            [_auth(first)],
            _auth(replacement),
        )


def test_provider_successor_planner_binds_changed_provider_transition() -> None:
    first = _provider_state("provider-a", requirement_id="gap-a")
    replacement = _provider_state(
        "provider-a",
        requirement_id="gap-a2",
        description="Acquire new calibration evidence.",
        source_sha="c" * 64,
    )
    result = build_provider_successor_planner_program_state(
        _base_program(),
        [_auth(first)],
        _auth(replacement),
    )

    assert result["next_planning_cycle_required"] is True
    successor = result["successor_planner_program_state"]
    assert successor is not None
    assert "evidence_provider_transition_binding" not in successor
    assert len(result["transition"]["transition_sha256"]) == 64
    assert (
        result["transition"]["current_provider_state_sha256"]
        == replacement["provider_state_sha256"]
    )
    provider_goal = next(
        item
        for item in successor["generated_goals"]
        if item.get("provider_requirement_overlay") is True
    )
    assert provider_goal["action_frontier"] == []


def test_rehashed_provider_successor_bundle_tamper_fails_recomputation() -> None:
    first = _provider_state("provider-a", requirement_id="gap-a")
    replacement = _provider_state(
        "provider-a",
        requirement_id="gap-a2",
        source_sha="c" * 64,
    )
    bundle = build_provider_successor_planner_program_state(
        _base_program(),
        [_auth(first)],
        _auth(replacement),
    )
    forged = copy.deepcopy(bundle)
    forged["successor_planner_program_state"]["generated_goals"][0][
        "goal_statement"
    ] = "forged non-provider planner content"
    forged.pop("successor_bundle_sha256")
    forged["successor_bundle_sha256"] = canonical_sha256(forged)

    with pytest.raises(
        EvidenceProviderPlanningError,
        match="authenticated recomputation",
    ):
        validate_provider_successor_planner_program_state(
            forged,
            _base_program(),
            [_auth(first)],
            _auth(replacement),
        )


def test_provider_transition_cannot_replace_unknown_provider() -> None:
    first = _provider_state("provider-a", requirement_id="gap-a")
    unknown = _provider_state("provider-x", requirement_id="gap-x")
    with pytest.raises(
        EvidenceProviderPlanningError,
        match="replace only an existing provider",
    ):
        build_provider_state_transition([_auth(first)], _auth(unknown))


def test_rehashed_provider_transition_tamper_fails_authenticated_recomputation() -> None:
    first = _provider_state("provider-a", requirement_id="gap-a")
    replacement = _provider_state("provider-a", requirement_id="gap-a2", source_sha="c" * 64)
    transition = build_provider_state_transition(
        [_auth(first)],
        _auth(replacement),
    )
    forged = copy.deepcopy(transition)
    forged["next_planning_cycle_required"] = False
    forged["stop_reason"] = "no_new_provider_information"
    forged = _rehash_transition(forged)

    with pytest.raises(
        EvidenceProviderPlanningError,
        match="authenticated recomputation",
    ):
        validate_provider_state_transition(
            forged,
            [_auth(first)],
            _auth(replacement),
        )


def test_provider_transition_replay_rejects_bool_int_aliases() -> None:
    first = _provider_state("provider-a", requirement_id="gap-a")
    replacement = _provider_state(
        "provider-a",
        requirement_id="gap-a2",
        source_sha="c" * 64,
    )
    transition = build_provider_state_transition(
        [_auth(first)],
        _auth(replacement),
    )
    forged = copy.deepcopy(transition)
    forged["state_changed"] = 1
    forged["next_planning_cycle_required"] = 1
    forged.pop("transition_sha256")
    forged["transition_sha256"] = canonical_sha256(forged)

    with pytest.raises(
        EvidenceProviderPlanningError,
        match="authenticated recomputation",
    ):
        validate_provider_state_transition(
            forged,
            [_auth(first)],
            _auth(replacement),
        )


def test_transition_application_returns_replayable_updated_provider_set() -> None:
    first = _provider_state("provider-a", requirement_id="gap-a")
    second = _provider_state("provider-b", requirement_id="gap-b", source_sha="b" * 64)
    replacement = _provider_state(
        "provider-a",
        requirement_id="gap-a2",
        source_sha="c" * 64,
    )
    applied = apply_provider_state_transition(
        [_auth(first), _auth(second)],
        _auth(replacement),
    )
    restored = deserialize_authenticated_provider_inputs(
        applied["provider_state_inputs"]
    )
    assert {item.state["provider"]["provider_id"] for item in restored} == {
        "provider-a",
        "provider-b",
    }
    assert {
        item.state["provider_state_sha256"] for item in restored
    } == {
        replacement["provider_state_sha256"],
        second["provider_state_sha256"],
    }
    assert applied["provider_requirement_aggregate"]["aggregate_sha256"] == applied[
        "transition"
    ]["current_aggregate_sha256"]
    assert applied["authority_boundary"]["scientific_status_promoted"] is False
