from __future__ import annotations

import copy

import pytest

import materials_data_analyzer.research_loop.public_recursive_planning as public_planning
from materials_data_analyzer.research_loop.autonomous_inquiry import (
    build_autonomous_inquiry_plan,
)
from materials_data_analyzer.research_loop.evidence_provider_contract import (
    AuthenticatedProviderStateInput,
    finalize_provider_state,
)
from materials_data_analyzer.research_loop.evidence_provider_planning import (
    build_provider_planner_program_state,
    build_provider_state_transition,
)
from materials_data_analyzer.research_loop.public_recursive_planning import (
    PublicRecursivePlanningError,
    build_public_candidate_match_record,
    build_public_recursive_planning_checkpoint,
    build_public_recursive_planning_context,
    validate_public_recursive_planning_context,
)


def _provider_state(
    provider_id: str,
    *,
    requirement_id: str,
    description: str,
    source_sha: str,
) -> dict:
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
            "domain": "test-domain",
            "modality": "test-modality",
            "subject_scope": "bounded subject",
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
                "status": "blocked",
                "maturity_label": None,
                "maturity_index": None,
                "first_blocker": requirement_id,
            },
            "unresolved_requirements": [
                {
                    "requirement_id": requirement_id,
                    "requirement_class": "analysis",
                    "action_class": "analysis",
                    "description": description,
                    "status": "unresolved",
                    "source_binding_ids": ["source-1"],
                    "automatic_execution_authorized": False,
                    "scientific_status_promoted": False,
                }
            ],
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


def _handoff() -> dict:
    value = {
        "schema_version": "1.0",
        "policy_version": "1.0",
        "source_discrepancy_report_sha256": "a" * 64,
        "target": {
            "graph_id": "g-1",
            "node_id": "h-1",
            "node_type": "hypothesis",
            "statement": "Bounded target statement.",
        },
        "diagnosis_context": {
            "diagnosis_types": ["parameter_or_property_uncertainty"],
            "passed_gates": ["numerical_validity"],
            "failed_gates": ["property_authority"],
            "stop_recommendation": "replan_to_resolve_upstream_comparison_gates",
            "stop_rationale": "Property authority remains unresolved.",
            "hypothesis_portfolio_directive": None,
        },
        "source_ancestry": {
            "previous_discrepancy_report_sha256": None,
            "prior_diagnosis_types": [],
            "current_diagnosis_types": ["parameter_or_property_uncertainty"],
        },
        "research_objectives": [
            {
                "objective_id": "planning-objective:property-sensitivity",
                "source_proposal_id": "property-sensitivity",
                "source_rank": 1,
                "research_action_class": "sensitivity_analysis",
                "rationale": "Resolve bounded property uncertainty.",
                "source_execution_mode": "plan_only",
                "planner_candidate_required": True,
                "availability_asserted": False,
                "automatic_execution_authorized": False,
            }
        ],
        "planner_boundary": {
            "current_planner_frontier_modified": False,
            "current_selected_action_modified": False,
            "executable_candidate_created": False,
            "candidate_availability_verified": False,
            "candidate_registry_binding_created": False,
            "fresh_planner_candidate_matching_required": True,
            "action_authorization_granted": False,
            "automatic_execution_authorized": False,
            "scientific_status_changed": False,
        },
    }
    from materials_data_analyzer.research_loop.evidence_packet import canonical_sha256

    value["handoff_sha256"] = canonical_sha256(value)
    return value


def _successor_handoff(previous: dict) -> dict:
    value = copy.deepcopy(previous)
    value.pop("handoff_sha256", None)
    value["source_discrepancy_report_sha256"] = "d" * 64
    value["target"]["graph_id"] = "g-2"
    value["source_ancestry"]["previous_discrepancy_report_sha256"] = previous[
        "source_discrepancy_report_sha256"
    ]
    value["source_ancestry"]["prior_diagnosis_types"] = list(
        previous["source_ancestry"]["current_diagnosis_types"]
    )
    value["research_objectives"][0]["objective_id"] = (
        "planning-objective:property-sensitivity-successor"
    )
    value["research_objectives"][0]["source_proposal_id"] = (
        "property-sensitivity-successor"
    )
    from materials_data_analyzer.research_loop.evidence_packet import canonical_sha256

    value["handoff_sha256"] = canonical_sha256(value)
    return value


def _base_program(handoff: dict) -> dict:
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
                "goal_id": "existing:property-sensitivity",
                "workstream_id": "existing",
                "research_question": "Does property uncertainty affect the bounded result?",
                "goal_statement": "Run the already available sensitivity analysis.",
                "status": "active",
                "priority": "high",
                "evidence_requirements": ["bounded property sensitivity result"],
                "claim_boundary": {"scientific_status": "computational_only"},
                "action_frontier": [
                    {
                        "action_id": "existing:sensitivity",
                        "action_class": "sensitivity_analysis",
                        "description": "Run bounded property sensitivity analysis.",
                        "rationale": "Resolve bounded property uncertainty.",
                        "execution_mode": "plan_only",
                        "expected_information_score": 0.8,
                        "hypothesis_discrimination_score": 0.8,
                        "feasibility_score": 0.9,
                        "cost_units": 1.5,
                        "risk_penalty": 0.0,
                    }
                ],
            }
        ],
        "public_recursive_planner_binding": {
            "handoff_sha256": handoff["handoff_sha256"],
            "source_discrepancy_report_sha256": handoff[
                "source_discrepancy_report_sha256"
            ],
        },
    }


def _patch_handoff_validation(monkeypatch, handoff: dict | None = None) -> None:
    def fake_validator(value, **kwargs):
        if handoff is not None:
            assert value == handoff
        return {
            "handoff_sha256": value["handoff_sha256"],
            "source_discrepancy_report_sha256": value[
                "source_discrepancy_report_sha256"
            ],
            "source_discrepancy_hardening_verified": True,
            "source_discrepancy_physics_hardening_verified": True,
        }

    monkeypatch.setattr(
        public_planning,
        "validate_public_recursive_discrepancy_planning_handoff",
        fake_validator,
    )


def _build(monkeypatch, provider_input: AuthenticatedProviderStateInput):
    handoff = _handoff()
    _patch_handoff_validation(monkeypatch)
    program = build_provider_planner_program_state(
        _base_program(handoff),
        [provider_input],
    )
    plan = build_autonomous_inquiry_plan(program)
    match = build_public_candidate_match_record(
        planning_handoff=handoff,
        fresh_plan=plan,
    )
    source_report = {"report_sha256": "a" * 64}
    graph = {"graph_id": "g-1"}
    checkpoint = build_public_recursive_planning_checkpoint(
        planning_handoff=handoff,
        source_discrepancy_report=source_report,
        source_evaluated_graph=graph,
        fresh_plan=plan,
        planner_program_state=program,
        candidate_match=match,
        provider_state_inputs=[provider_input],
    )
    return {
        "handoff": handoff,
        "program": program,
        "plan": plan,
        "match": match,
        "source_report": source_report,
        "graph": graph,
        "checkpoint": checkpoint,
    }


def test_recursive_checkpoint_persists_authenticated_provider_requirements(monkeypatch) -> None:
    provider = _provider_state(
        "characterization-provider",
        requirement_id="l5-gap",
        description="Acquire direct target-material validation evidence.",
        source_sha="b" * 64,
    )
    built = _build(monkeypatch, _auth(provider))
    checkpoint = built["checkpoint"]
    persistent = checkpoint["recursive_checkpoint"]["persistent_research_state"]
    provider_state = persistent["evidence_provider_state"]

    assert checkpoint["planner_verification"]["selected_candidate_id"] == "existing:sensitivity"
    assert {item["action_id"] for item in built["plan"]["ranked_actions"]} == {
        "existing:sensitivity"
    }
    assert provider_state["provider_requirement_aggregate"]["requirements"][0][
        "provider_id"
    ] == "characterization-provider"
    assert provider_state["planner_overlay_verification"][
        "provider_candidates_created"
    ] is False
    assert len(
        provider_state["planner_overlay_verification"]["verification_sha256"]
    ) == 64
    assert checkpoint["autonomy_boundary"]["provider_requirements_authenticated"] is True
    assert checkpoint["autonomy_boundary"]["provider_candidates_created"] is False
    assert checkpoint["autonomy_boundary"]["authorization_granted"] is False


def test_recursive_checkpoint_rejects_provider_inputs_that_do_not_match_planner_overlay(
    monkeypatch,
) -> None:
    first = _provider_state(
        "provider-a",
        requirement_id="gap-a",
        description="Resolve provider A.",
        source_sha="b" * 64,
    )
    second = _provider_state(
        "provider-b",
        requirement_id="gap-b",
        description="Resolve provider B.",
        source_sha="c" * 64,
    )
    handoff = _handoff()
    _patch_handoff_validation(monkeypatch, handoff)
    program = build_provider_planner_program_state(
        _base_program(handoff),
        [_auth(first)],
    )
    plan = build_autonomous_inquiry_plan(program)
    match = build_public_candidate_match_record(
        planning_handoff=handoff,
        fresh_plan=plan,
    )

    with pytest.raises(
        PublicRecursivePlanningError,
        match="provider planning state failed authenticated provider reconstruction",
    ):
        build_public_recursive_planning_checkpoint(
            planning_handoff=handoff,
            source_discrepancy_report={"report_sha256": "a" * 64},
            source_evaluated_graph={"graph_id": "g-1"},
            fresh_plan=plan,
            planner_program_state=program,
            candidate_match=match,
            provider_state_inputs=[_auth(second)],
        )


def test_recursive_planning_context_serializes_and_replays_provider_inputs(monkeypatch) -> None:
    provider = _provider_state(
        "characterization-provider",
        requirement_id="l5-gap",
        description="Acquire direct target-material validation evidence.",
        source_sha="b" * 64,
    )
    provider_input = _auth(provider)
    built = _build(monkeypatch, provider_input)

    context = build_public_recursive_planning_context(
        validated_planning_artifact=built["checkpoint"],
        planning_handoff=built["handoff"],
        source_discrepancy_report=built["source_report"],
        source_evaluated_graph=built["graph"],
        fresh_plan=built["plan"],
        planner_program_state=built["program"],
        candidate_match=built["match"],
        provider_state_inputs=[provider_input],
    )
    verified = validate_public_recursive_planning_context(context)

    assert context["validation_inputs"]["provider_state_inputs"][0][
        "trusted_provider_state_sha256"
    ] == provider["provider_state_sha256"]
    expected_aggregate = built["checkpoint"]["recursive_checkpoint"][
        "persistent_research_state"
    ]["evidence_provider_state"]["provider_requirement_aggregate"]["aggregate_sha256"]
    assert context["bindings"]["evidence_provider_aggregate_sha256"] == expected_aggregate
    assert verified["evidence_provider_aggregate_sha256"] == expected_aggregate
    assert verified["provider_requirements_authenticated"] is True


def test_recursive_context_rejects_rehashed_provider_input_substitution(monkeypatch) -> None:
    provider = _provider_state(
        "characterization-provider",
        requirement_id="l5-gap",
        description="Acquire direct target-material validation evidence.",
        source_sha="b" * 64,
    )
    provider_input = _auth(provider)
    built = _build(monkeypatch, provider_input)
    context = build_public_recursive_planning_context(
        validated_planning_artifact=built["checkpoint"],
        planning_handoff=built["handoff"],
        source_discrepancy_report=built["source_report"],
        source_evaluated_graph=built["graph"],
        fresh_plan=built["plan"],
        planner_program_state=built["program"],
        candidate_match=built["match"],
        provider_state_inputs=[provider_input],
    )

    forged = copy.deepcopy(context)
    serialized = forged["validation_inputs"]["provider_state_inputs"][0]
    serialized["trusted_provider_state_sha256"] = "f" * 64
    forged.pop("context_sha256")
    from materials_data_analyzer.research_loop.evidence_packet import canonical_sha256

    forged["context_sha256"] = canonical_sha256(forged)

    with pytest.raises(
        PublicRecursivePlanningError,
        match="provider-state inputs failed reconstruction",
    ):
        validate_public_recursive_planning_context(forged)


def test_recursive_second_cycle_requires_transition_when_provider_state_changes(
    monkeypatch,
) -> None:
    _patch_handoff_validation(monkeypatch)
    first_provider = _provider_state(
        "characterization-provider",
        requirement_id="l5-gap",
        description="Acquire first target-material evidence.",
        source_sha="b" * 64,
    )
    first_input = _auth(first_provider)
    first = _build(monkeypatch, first_input)
    context1 = build_public_recursive_planning_context(
        validated_planning_artifact=first["checkpoint"],
        planning_handoff=first["handoff"],
        source_discrepancy_report=first["source_report"],
        source_evaluated_graph=first["graph"],
        fresh_plan=first["plan"],
        planner_program_state=first["program"],
        candidate_match=first["match"],
        provider_state_inputs=[first_input],
    )

    replacement = _provider_state(
        "characterization-provider",
        requirement_id="l6-gap",
        description="Acquire independent external validation evidence.",
        source_sha="c" * 64,
    )
    replacement_input = _auth(replacement)
    handoff2 = _successor_handoff(first["handoff"])
    program2 = build_provider_planner_program_state(
        _base_program(handoff2),
        [replacement_input],
    )
    plan2 = build_autonomous_inquiry_plan(program2)
    match2 = build_public_candidate_match_record(
        planning_handoff=handoff2,
        fresh_plan=plan2,
    )

    with pytest.raises(
        PublicRecursivePlanningError,
        match="single-provider transition validation",
    ):
        build_public_recursive_planning_checkpoint(
            planning_handoff=handoff2,
            source_discrepancy_report={"report_sha256": "d" * 64},
            source_evaluated_graph={"graph_id": "g-2"},
            fresh_plan=plan2,
            planner_program_state=program2,
            previous_discrepancy_report={"report_sha256": "a" * 64},
            candidate_match=match2,
            previous_validated_planning_context=context1,
            provider_state_inputs=[replacement_input],
        )

    transition = build_provider_state_transition(
        [first_input],
        replacement_input,
    )
    checkpoint2 = build_public_recursive_planning_checkpoint(
        planning_handoff=handoff2,
        source_discrepancy_report={"report_sha256": "d" * 64},
        source_evaluated_graph={"graph_id": "g-2"},
        fresh_plan=plan2,
        planner_program_state=program2,
        previous_discrepancy_report={"report_sha256": "a" * 64},
        candidate_match=match2,
        previous_validated_planning_context=context1,
        provider_state_inputs=[replacement_input],
        provider_state_transition=transition,
    )

    successor = checkpoint2["evidence_provider_successor_verification"]
    assert successor["changed_provider_count"] == 1
    assert successor["changed_provider_id"] == "characterization-provider"
    assert successor["state_changed"] is True
    assert checkpoint2["recursive_checkpoint"]["cycle_index"] == 2
    assert checkpoint2["autonomy_boundary"]["provider_candidates_created"] is False

    context2 = build_public_recursive_planning_context(
        validated_planning_artifact=checkpoint2,
        planning_handoff=handoff2,
        source_discrepancy_report={"report_sha256": "d" * 64},
        source_evaluated_graph={"graph_id": "g-2"},
        fresh_plan=plan2,
        planner_program_state=program2,
        previous_discrepancy_report={"report_sha256": "a" * 64},
        candidate_match=match2,
        previous_validated_planning_context=context1,
        provider_state_inputs=[replacement_input],
        provider_state_transition=transition,
    )
    assert context2["bindings"]["evidence_provider_transition_sha256"] == transition[
        "transition_sha256"
    ]
    replayed2 = validate_public_recursive_planning_context(context2)
    assert replayed2["recursive_checkpoint"]["cycle_index"] == 2


def test_recursive_second_cycle_can_inherit_unchanged_provider_when_other_information_changes(
    monkeypatch,
) -> None:
    _patch_handoff_validation(monkeypatch)
    provider = _provider_state(
        "characterization-provider",
        requirement_id="l5-gap",
        description="Acquire target-material evidence.",
        source_sha="b" * 64,
    )
    provider_input = _auth(provider)
    first = _build(monkeypatch, provider_input)
    context1 = build_public_recursive_planning_context(
        validated_planning_artifact=first["checkpoint"],
        planning_handoff=first["handoff"],
        source_discrepancy_report=first["source_report"],
        source_evaluated_graph=first["graph"],
        fresh_plan=first["plan"],
        planner_program_state=first["program"],
        candidate_match=first["match"],
        provider_state_inputs=[provider_input],
    )

    handoff2 = _successor_handoff(first["handoff"])
    # The provider state is inherited; only the independent discrepancy/planner binding changes.
    program2 = copy.deepcopy(first["program"])
    program2["public_recursive_planner_binding"] = {
        "handoff_sha256": handoff2["handoff_sha256"],
        "source_discrepancy_report_sha256": handoff2[
            "source_discrepancy_report_sha256"
        ],
    }
    plan2 = build_autonomous_inquiry_plan(program2)
    assert plan2["plan_sha256"] != first["plan"]["plan_sha256"]
    match2 = build_public_candidate_match_record(
        planning_handoff=handoff2,
        fresh_plan=plan2,
    )

    checkpoint2 = build_public_recursive_planning_checkpoint(
        planning_handoff=handoff2,
        source_discrepancy_report={"report_sha256": "d" * 64},
        source_evaluated_graph={"graph_id": "g-2"},
        fresh_plan=plan2,
        planner_program_state=program2,
        previous_discrepancy_report={"report_sha256": "a" * 64},
        candidate_match=match2,
        previous_validated_planning_context=context1,
        # provider_state_inputs intentionally omitted: exact predecessor state is inherited.
    )

    successor = checkpoint2["evidence_provider_successor_verification"]
    assert successor["changed_provider_count"] == 0
    assert successor["state_changed"] is False
    assert successor["changed_provider_id"] is None
    assert checkpoint2["recursive_checkpoint"]["cycle_index"] == 2
    assert checkpoint2["planner_verification"]["plan_sha256"] == plan2["plan_sha256"]
