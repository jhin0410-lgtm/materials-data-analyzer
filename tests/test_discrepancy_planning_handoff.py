from __future__ import annotations

import copy

import pytest

import materials_data_analyzer.research_loop.discrepancy_planning_handoff as handoff_module
from materials_data_analyzer.research_loop.discrepancy_planning_handoff import (
    DiscrepancyPlanningHandoffError,
    build_discrepancy_planning_handoff,
    validate_discrepancy_planning_handoff,
)


REPORT_SHA = "1" * 64
PREVIOUS_SHA = "2" * 64


def _verified(*, diagnosis_types: list[str] | None = None) -> dict:
    return {
        "report_sha256": REPORT_SHA,
        "target_node_id": "h1",
        "iteration_index": 2,
        "diagnosis_types": diagnosis_types or ["empirical_model_discrepancy"],
        "artifact_bindings_reverified": True,
        "scientific_status_changed": False,
        "automatic_execution_authorized": False,
    }


def _report(
    *,
    diagnosis_types: list[str] | None = None,
    portfolio_state: str | None = None,
) -> dict:
    types = diagnosis_types or ["empirical_model_discrepancy"]
    proposals = [
        {
            "proposal_id": "model-evidence:discriminate-model-vs-hypothesis",
            "action_class": "discriminating_analysis",
            "description": "Separate model-form failure from hypothesis-scope failure.",
            "rationale": "The fully admissible residual discrepancy remains unresolved.",
            "information_gain_priority": "highest",
            "information_gain_is_calibrated_probability": False,
            "execution_mode": "plan_only",
            "availability_asserted": False,
            "automatic_execution_authorized": False,
            "rank": 1,
        },
        {
            "proposal_id": "model-evidence:independent-matched-replication",
            "action_class": "replication",
            "description": "Seek a provenance-disjoint matched-condition replication.",
            "rationale": "Replication tests whether the residual is reproducible.",
            "information_gain_priority": "high",
            "information_gain_is_calibrated_probability": False,
            "execution_mode": "explicit_authorization_required",
            "availability_asserted": False,
            "automatic_execution_authorized": False,
            "rank": 2,
        },
    ]
    if types == ["numerical_invalidity"]:
        proposals = [
            {
                "proposal_id": "model-evidence:validate-or-refine-numerics",
                "action_class": "numerical_validation",
                "description": "Validate or refine numerical behavior first.",
                "rationale": "Numerical invalidity blocks physical interpretation.",
                "information_gain_priority": "highest",
                "information_gain_is_calibrated_probability": False,
                "execution_mode": "plan_only",
                "availability_asserted": False,
                "automatic_execution_authorized": False,
                "rank": 1,
            }
        ]
    if portfolio_state == "retired_falsified_within_verified_scope":
        proposals.insert(
            0,
            {
                "proposal_id": "model-evidence:preserve-falsified-status",
                "action_class": "hypothesis_reframe",
                "description": "Preserve falsification and create a new hypothesis identity.",
                "rationale": "A discrepancy report cannot reactivate a falsified hypothesis.",
                "information_gain_priority": "highest",
                "information_gain_is_calibrated_probability": False,
                "execution_mode": "plan_only",
                "availability_asserted": False,
                "automatic_execution_authorized": False,
                "rank": 1,
            },
        )
        for index, item in enumerate(proposals, start=1):
            item["rank"] = index
    gates = {
        "numerical_validity": {"passed": "numerical_invalidity" not in types},
        "model_domain": {"passed": True},
        "property_authority": {"passed": True},
        "comparability": {"passed": True},
        "empirical_sufficiency": {"passed": True},
    }
    return {
        "schema_version": "1.0",
        "policy_version": "1.0",
        "target": {
            "graph_id": "graph-1",
            "node_id": "h1",
            "node_type": "hypothesis",
            "statement": "Bounded model/evidence target.",
        },
        "hypothesis_portfolio_state": (
            {
                "hypothesis_id": "h1",
                "portfolio_state": portfolio_state,
                "epistemic_status": "falsified_within_verified_scope",
                "research_directive": "do_not_repeat_without_new_hypothesis_identity",
                "verified_support_edges": [],
                "verified_contradiction_edges": [],
                "verified_falsification_edges": ["f1"],
            }
            if portfolio_state is not None
            else None
        ),
        "gates": gates,
        "ranked_next_actions": proposals,
        "stop_recommendation": {
            "recommendation": "continue_discriminating_research",
            "rationale": "A bounded discrepancy remains unresolved.",
            "automatic_stop_authorized": False,
            "positive_scientific_closeout_granted": False,
        },
        "ancestry": {
            "previous_report_sha256": PREVIOUS_SHA,
            "prior_diagnosis_types": ["insufficient_empirical_evidence"],
            "current_diagnosis_types": types,
        },
        "autonomy_boundary": {
            "scientific_status_changed": False,
            "automatic_execution_authorized": False,
        },
    }


def _patch_verified(monkeypatch: pytest.MonkeyPatch, *, diagnosis_types: list[str]) -> None:
    monkeypatch.setattr(
        handoff_module,
        "validate_model_evidence_discrepancy_report",
        lambda *args, **kwargs: _verified(diagnosis_types=diagnosis_types),
    )


def test_discrepancy_proposals_become_future_objectives_not_executable_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_verified(monkeypatch, diagnosis_types=["empirical_model_discrepancy"])
    report = _report()
    handoff = build_discrepancy_planning_handoff(report, evaluated_graph={})

    assert handoff["planning_handoff_state"] == "fresh_planner_candidate_generation_required"
    assert handoff["next_planning_cycle_required"] is True
    assert [item["research_action_class"] for item in handoff["research_objectives"]] == [
        "discriminating_analysis",
        "replication",
    ]
    assert all(item["planner_candidate_required"] is True for item in handoff["research_objectives"])
    assert all(item["action_type"] is None for item in handoff["research_objectives"])
    assert all(item["action_version"] is None for item in handoff["research_objectives"])
    assert all(item["availability_asserted"] is False for item in handoff["research_objectives"])
    assert handoff["planner_boundary"] == {
        "current_planner_frontier_modified": False,
        "current_selected_action_modified": False,
        "executable_candidate_created": False,
        "candidate_availability_verified": False,
        "candidate_registry_binding_created": False,
        "fresh_planner_candidate_matching_required": True,
        "action_authorization_granted": False,
        "automatic_execution_authorized": False,
        "scientific_status_changed": False,
    }

    verified = validate_discrepancy_planning_handoff(
        handoff,
        discrepancy_report=report,
        evaluated_graph={},
    )
    assert verified["handoff_sha256"] == handoff["handoff_sha256"]
    assert verified["current_planner_frontier_modified"] is False
    assert verified["action_authorization_granted"] is False


def test_numerical_invalidity_handoff_prioritizes_numerical_validation_without_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_verified(monkeypatch, diagnosis_types=["numerical_invalidity"])
    report = _report(diagnosis_types=["numerical_invalidity"])
    handoff = build_discrepancy_planning_handoff(report, evaluated_graph={})

    assert handoff["diagnosis_context"]["failed_gates"] == ["numerical_validity"]
    assert handoff["research_objectives"][0]["research_action_class"] == "numerical_validation"
    assert handoff["research_objectives"][0]["action_type"] is None
    assert handoff["planner_boundary"]["automatic_execution_authorized"] is False


def test_falsified_hypothesis_reframe_remains_first_planning_objective(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_verified(monkeypatch, diagnosis_types=["agreement_within_declared_tolerance"])
    report = _report(
        diagnosis_types=["agreement_within_declared_tolerance"],
        portfolio_state="retired_falsified_within_verified_scope",
    )
    handoff = build_discrepancy_planning_handoff(
        report,
        evaluated_graph={},
        hypothesis_portfolio={},
    )

    assert handoff["research_objectives"][0]["research_action_class"] == "hypothesis_reframe"
    assert (
        handoff["diagnosis_context"]["hypothesis_portfolio_directive"]
        == "do_not_repeat_without_new_hypothesis_identity"
    )
    assert handoff["planner_boundary"]["scientific_status_changed"] is False


def test_proposal_cannot_smuggle_availability_or_execution_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_verified(monkeypatch, diagnosis_types=["empirical_model_discrepancy"])
    report = _report()
    report["ranked_next_actions"][0]["availability_asserted"] = True
    with pytest.raises(
        DiscrepancyPlanningHandoffError,
        match="cannot assert action availability",
    ):
        build_discrepancy_planning_handoff(report, evaluated_graph={})

    report = _report()
    report["ranked_next_actions"][0]["automatic_execution_authorized"] = True
    with pytest.raises(
        DiscrepancyPlanningHandoffError,
        match="cannot authorize execution",
    ):
        build_discrepancy_planning_handoff(report, evaluated_graph={})


def test_handoff_tamper_or_source_drift_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_verified(monkeypatch, diagnosis_types=["empirical_model_discrepancy"])
    report = _report()
    handoff = build_discrepancy_planning_handoff(report, evaluated_graph={})

    tampered = copy.deepcopy(handoff)
    tampered["research_objectives"][0]["action_type"] = "invented_direct_action"
    with pytest.raises(
        DiscrepancyPlanningHandoffError,
        match="canonical SHA-256",
    ):
        validate_discrepancy_planning_handoff(
            tampered,
            discrepancy_report=report,
            evaluated_graph={},
        )

    # Even if a caller recomputes its own handoff checksum, rebuilding from the validated
    # discrepancy context catches semantic source drift.
    changed_report = copy.deepcopy(report)
    changed_report["ranked_next_actions"][0]["description"] = "changed source proposal"
    with pytest.raises(
        DiscrepancyPlanningHandoffError,
        match="differs from current validated discrepancy context",
    ):
        validate_discrepancy_planning_handoff(
            handoff,
            discrepancy_report=changed_report,
            evaluated_graph={},
        )


def test_recursive_discrepancy_ancestry_is_forwarded_without_becoming_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_verified(monkeypatch, diagnosis_types=["empirical_model_discrepancy"])
    report = _report()
    handoff = build_discrepancy_planning_handoff(report, evaluated_graph={})

    assert handoff["source_iteration_index"] == 2
    assert handoff["source_ancestry"]["previous_discrepancy_report_sha256"] == PREVIOUS_SHA
    assert handoff["source_ancestry"]["prior_diagnosis_types"] == [
        "insufficient_empirical_evidence"
    ]
    assert handoff["source_ancestry"]["current_diagnosis_types"] == [
        "empirical_model_discrepancy"
    ]
    assert handoff["planner_boundary"]["candidate_registry_binding_created"] is False
