from __future__ import annotations

import copy

import pytest

import materials_data_analyzer.research_loop.discrepancy_planning_handoff as structural_module
import materials_data_analyzer.research_loop.discrepancy_planning_handoff_policy as policy_module
from materials_data_analyzer.research_loop.discrepancy_planning_handoff import (
    DiscrepancyPlanningHandoffError,
    build_discrepancy_planning_handoff as build_structural_handoff,
)
from materials_data_analyzer.research_loop.discrepancy_planning_handoff_policy import (
    SEMANTIC_ACTION_CLASS_TRANSLATION_POLICY_VERSION,
    build_policy_hardened_discrepancy_planning_handoff,
    validate_policy_hardened_discrepancy_planning_handoff,
)


REPORT_SHA = "1" * 64


def _report(*, diagnosis: str = "numerical_invalidity", failed_gate: bool = True) -> dict:
    return {
        "schema_version": "1.0",
        "policy_version": "1.0",
        "target": {
            "graph_id": "graph-heat-1",
            "node_id": "heat-model-node",
            "node_type": "model_output",
            "statement": "Reference heat-conduction result requires numerical validation.",
        },
        "hypothesis_portfolio_state": None,
        "gates": {
            "numerical_validity": {"passed": not failed_gate},
            "model_domain": {"passed": True},
            "property_authority": {"passed": True},
            "comparability": {"passed": True},
            "empirical_sufficiency": {"passed": True},
        },
        "ranked_next_actions": [
            {
                "proposal_id": "model-evidence:validate-or-refine-numerics",
                "action_class": "numerical_validation",
                "description": "Validate or refine numerical behavior first.",
                "rationale": "Numerical invalidity blocks physical interpretation.",
                "information_gain_priority": "highest",
                "information_gain_is_calibrated_probability": False,
                "execution_mode": "explicit_authorization_required",
                "availability_asserted": False,
                "automatic_execution_authorized": False,
                "rank": 1,
            }
        ],
        "stop_recommendation": {
            "recommendation": "continue_discriminating_research",
            "rationale": "Numerical validity remains unresolved.",
            "automatic_stop_authorized": False,
            "positive_scientific_closeout_granted": False,
        },
        "ancestry": {
            "previous_report_sha256": None,
            "prior_diagnosis_types": [],
            "current_diagnosis_types": [diagnosis],
        },
        "autonomy_boundary": {
            "scientific_status_changed": False,
            "automatic_execution_authorized": False,
        },
    }


def _patch_validation(
    monkeypatch: pytest.MonkeyPatch,
    *,
    diagnosis: str = "numerical_invalidity",
) -> None:
    verified = {
        "report_sha256": REPORT_SHA,
        "target_node_id": "heat-model-node",
        "iteration_index": 1,
        "diagnosis_types": [diagnosis],
        "artifact_bindings_reverified": True,
        "scientific_status_changed": False,
        "automatic_execution_authorized": False,
    }
    monkeypatch.setattr(
        structural_module,
        "validate_model_evidence_discrepancy_report",
        lambda *args, **kwargs: verified,
    )
    monkeypatch.setattr(
        policy_module,
        "validate_physics_hardened_model_evidence_discrepancy_report",
        lambda *args, **kwargs: verified,
    )


def test_policy_bridge_preserves_diagnostic_class_and_projects_planner_simulation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_validation(monkeypatch)
    report = _report()

    structural = build_structural_handoff(report, evaluated_graph={})
    assert structural["research_objectives"][0]["research_action_class"] == (
        "numerical_validation"
    )
    assert "planner_semantic_bridge" not in structural

    handoff = build_policy_hardened_discrepancy_planning_handoff(
        report,
        evaluated_graph={},
    )
    objective = handoff["research_objectives"][0]
    translation = objective["semantic_action_class_translation"]

    assert objective["source_research_action_class"] == "numerical_validation"
    assert objective["research_action_class"] == "simulation"
    assert translation["source_diagnostic_action_class"] == "numerical_validation"
    assert translation["planner_action_class"] == "simulation"
    assert translation["required_diagnosis"] == "numerical_invalidity"
    assert translation["required_failed_gate"] == "numerical_validity"
    assert translation["diagnostic_semantics_preserved"] is True
    assert translation["candidate_availability_asserted"] is False
    assert translation["registry_binding_created"] is False
    assert translation["action_authorization_granted"] is False
    assert handoff["planner_semantic_bridge"]["translation_count"] == 1
    assert handoff["planner_boundary"]["automatic_execution_authorized"] is False

    verified = validate_policy_hardened_discrepancy_planning_handoff(
        handoff,
        discrepancy_report=report,
        evaluated_graph={},
    )
    assert verified["semantic_action_class_translation_count"] == 1
    assert verified["semantic_action_class_translation_policy_version"] == (
        SEMANTIC_ACTION_CLASS_TRANSLATION_POLICY_VERSION
    )
    assert verified["semantic_translation_created_execution_authority"] is False


def test_policy_bridge_requires_exact_numerical_invalidity_diagnosis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_validation(monkeypatch, diagnosis="empirical_model_discrepancy")
    report = _report(diagnosis="empirical_model_discrepancy")

    with pytest.raises(
        DiscrepancyPlanningHandoffError,
        match="required discrepancy diagnosis",
    ):
        build_policy_hardened_discrepancy_planning_handoff(
            report,
            evaluated_graph={},
        )


def test_policy_bridge_requires_exact_failed_numerical_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_validation(monkeypatch)
    report = _report(failed_gate=False)

    with pytest.raises(
        DiscrepancyPlanningHandoffError,
        match="required failed discrepancy gate",
    ):
        build_policy_hardened_discrepancy_planning_handoff(
            report,
            evaluated_graph={},
        )


def test_policy_bridge_tamper_fails_deterministic_reconstruction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_validation(monkeypatch)
    report = _report()
    handoff = build_policy_hardened_discrepancy_planning_handoff(
        report,
        evaluated_graph={},
    )

    tampered = copy.deepcopy(handoff)
    tampered["research_objectives"][0]["research_action_class"] = "sensitivity_analysis"
    with pytest.raises(
        DiscrepancyPlanningHandoffError,
        match="canonical SHA-256",
    ):
        validate_policy_hardened_discrepancy_planning_handoff(
            tampered,
            discrepancy_report=report,
            evaluated_graph={},
        )


def test_unmapped_classes_remain_structurally_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_validation(monkeypatch, diagnosis="empirical_model_discrepancy")
    report = _report(diagnosis="empirical_model_discrepancy")
    report["ranked_next_actions"][0]["action_class"] = "replication"
    report["ranked_next_actions"][0]["proposal_id"] = "model-evidence:replicate"
    report["gates"]["numerical_validity"]["passed"] = True

    structural = build_structural_handoff(report, evaluated_graph={})
    hardened = build_policy_hardened_discrepancy_planning_handoff(
        report,
        evaluated_graph={},
    )

    assert hardened == structural
    assert "planner_semantic_bridge" not in hardened
