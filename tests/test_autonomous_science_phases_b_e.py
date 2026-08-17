from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from materials_data_analyzer.characterization_use_contract import CharacterizationUseEligibility
from materials_data_analyzer.research_loop.cross_source_scientific_reasoning import (
    AnalysisTraits,
    ComparabilityContext,
    EffectEstimate,
    UncertaintyComponent,
    assess_comparability,
    combine_uncertainty,
    detect_verified_directional_contradiction,
    select_next_analysis,
)
from materials_data_analyzer.research_loop.epistemic_graph import validate_epistemic_graph
from materials_data_analyzer.research_loop.sample_identity_binding import (
    SampleBinding,
    SampleIdentityBindingError,
    SampleIdentityRegistry,
    normalize_characterization_measurement,
)
from materials_data_analyzer.research_loop.scientific_evidence_normalization import (
    MaterialComposition,
    NormalizedMeasurement,
    ProvenanceLocator,
    ScientificEvidenceNormalizationError,
    build_epistemic_evidence_node,
)
from materials_data_analyzer.research_loop.scientific_simulation_registry import (
    SimulationPlanningRequest,
    SolverContractRegistry,
    StructuralDesignCandidate,
    compile_simulation_action_candidate,
    repository_design_simulation_contract,
    select_structural_design_candidate,
    structural_design_sensitivity,
)
from materials_data_analyzer.research_loop.design_simulation import simulate_design_structure


ARTIFACT_SHA = hashlib.sha256(b"source-artifact").hexdigest()


def provenance(locator: str = "row:1") -> ProvenanceLocator:
    return ProvenanceLocator("fixture-source", ARTIFACT_SHA, locator)


def material() -> MaterialComposition:
    return MaterialComposition(
        "IN625 fixture",
        "mass_percent",
        {"Ni": 60.0, "Cr": 22.0, "Mo": 9.0, "Nb": 3.5},
    )


def measurement() -> NormalizedMeasurement:
    return NormalizedMeasurement(
        material=material(),
        sample_id="sample-001",
        property_name="yield_strength",
        value=810.0,
        unit="MPa",
        method="tensile_test",
        instrument_model="fixture-frame",
        calibration_id="cal-001",
        process_signature="lpbf:p1",
        standard_uncertainty=5.0,
        provenance=provenance(),
    )


def evidence_node() -> dict[str, object]:
    return build_epistemic_evidence_node(
        measurement(),
        workstream_id="in625",
        evidence_role="external_raw",
        evidence_quality="supported",
    )


def program_state() -> dict[str, object]:
    return {
        "workstreams": [
            {
                "workstream_id": "in625",
                "planning_state": {
                    "evidence_bindings": [
                        {"role": "external_raw", "sha256": ARTIFACT_SHA}
                    ]
                },
            }
        ]
    }


def eligibility(*, allowed: bool = True) -> CharacterizationUseEligibility:
    return CharacterizationUseEligibility(
        requested_use="descriptive",
        allowed=allowed,
        maximum_allowed_use="descriptive",
        policy_source="fixture",
        evidence_level="Supported",
        feature_stage="observable",
        review_status="reviewed",
        independence_group_field=None,
        split_group_field=None,
        measurement_timing="unknown",
        reasons=(),
        warnings=(),
        limitations=(),
    )


def test_phase_b_normalization_emits_existing_epistemic_evidence_node(tmp_path: Path) -> None:
    node = evidence_node()
    graph = {
        "schema_version": "1.0",
        "graph_id": "phase-b",
        "research_scope": "normalization acceptance",
        "nodes": [node],
        "edges": [],
    }
    validated = validate_epistemic_graph(
        graph, program_state=program_state(), artifact_root=tmp_path
    )
    metadata = validated["nodes"][0]["metadata"]
    assert metadata["semantic_inference_performed"] is False
    assert metadata["material"]["basis"] == "mass_percent"
    with pytest.raises(ScientificEvidenceNormalizationError, match="basis"):
        MaterialComposition("bad", "unknown", {"Ni": 1.0})
    with pytest.raises(ScientificEvidenceNormalizationError, match="exceeds"):
        MaterialComposition("bad", "mass_fraction", {"Ni": 1.1})


def test_phase_c_contradiction_requires_comparability_independence_and_explicit_units() -> None:
    left_context = ComparabilityContext(
        material().material_id, "effect", "MPa", "lpbf:p1", "a", "ca", "src-a", "g-a"
    )
    right_context = ComparabilityContext(
        material().material_id, "effect", "GPa", "lpbf:p1", "b", "cb", "src-b", "g-b"
    )
    assert not assess_comparability(left_context, right_context).comparable
    contradiction, decision = detect_verified_directional_contradiction(
        EffectEstimate(left_context, 10.0, 1.0),
        EffectEstimate(right_context, -0.010, 0.001),
        explicit_unit_conversions={("GPa", "MPa"): 1000.0},
    )
    assert decision.comparable and contradiction
    same_group = ComparabilityContext(
        material().material_id, "effect", "MPa", "lpbf:p1", None, None, "src-b", "g-a"
    )
    contradiction, decision = detect_verified_directional_contradiction(
        EffectEstimate(left_context, 10.0, 1.0), EffectEstimate(same_group, -10.0, 1.0)
    )
    assert not contradiction
    assert "independence_not_demonstrated" in decision.reasons


def test_phase_c_uncertainty_and_analysis_selection_are_bounded() -> None:
    parts = (
        UncertaintyComponent("measurement", 3.0, "instrument"),
        UncertaintyComponent("model", 4.0, "validation"),
    )
    assert combine_uncertainty(parts, independence_explicitly_established=True) == 5.0
    assert combine_uncertainty(parts, independence_explicitly_established=False) == 7.0
    assert select_next_analysis(AnalysisTraits(20, 2, "continuous")).analysis_type == "bounded_regression"
    assert not select_next_analysis(AnalysisTraits(2, 1, "continuous")).executable


def test_phase_d_characterization_respects_policy_and_sample_identity() -> None:
    identities = SampleIdentityRegistry()
    identities.bind(SampleBinding("specimen-1", "fov-1", "field_of_view", provenance("binding")))
    normalized = normalize_characterization_measurement(
        modality="xrd",
        sample_id="fov-1",
        property_name="peak_position",
        value=44.5,
        unit="deg",
        material=material(),
        instrument_model="fixture-diffractometer",
        calibration_id="cal-xrd",
        process_signature="lpbf:p1",
        standard_uncertainty=0.02,
        provenance=provenance("xrd:peak:1"),
        eligibility=eligibility(),
        identity_registry=identities,
    )
    assert normalized.sample_id == "specimen-1"
    with pytest.raises(SampleIdentityBindingError, match="ambiguous"):
        identities.bind(SampleBinding("specimen-2", "fov-1", "field_of_view", provenance("other")))
    with pytest.raises(SampleIdentityBindingError, match="blocks"):
        normalize_characterization_measurement(
            modality="xrd", sample_id="fov-1", property_name="peak_position",
            value=44.5, unit="deg", material=material(), instrument_model="fixture",
            calibration_id=None, process_signature=None, standard_uncertainty=None,
            provenance=provenance(), eligibility=eligibility(allowed=False),
            identity_registry=identities,
        )


def design_config(*, proposed: list[dict[str, object]]) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "simulation_id": "fixture-design",
        "research_question": "Which predeclared cells improve structural estimability?",
        "factors": [{"name": "power", "unit": "W"}, {"name": "speed", "unit": "mm/s"}],
        "observed_cells": [
            {"cell_id": "o1", "factor_values": {"power": 0.0, "speed": 0.0}, "replicates": 1},
            {"cell_id": "o2", "factor_values": {"power": 1.0, "speed": 0.0}, "replicates": 1},
        ],
        "proposed_cells": proposed,
        "models": ["main_effects"],
        "scientific_boundary": {
            "response_values_allowed": False,
            "coefficient_estimation_allowed": False,
            "effect_size_estimation_allowed": False,
            "predictive_modeling_allowed": False,
            "causal_inference_allowed": False,
            "optimization_allowed": False,
            "engineering_decision_allowed": False,
        },
    }


def test_phase_e_reuses_existing_simulator_and_does_not_create_second_executor() -> None:
    registry = SolverContractRegistry()
    contract = repository_design_simulation_contract()
    registry.register_attested(contract, implementation=simulate_design_structure)
    assert not hasattr(registry, "execute")
    node = evidence_node()
    graph = {
        "nodes": [node, {"node_id": "claim:fixture", "node_type": "claim", "statement": "fixture"}]
    }
    action = compile_simulation_action_candidate(
        registry,
        SimulationPlanningRequest(
            "sim-plan-1", contract.solver_id, (str(node["node_id"]),), "claim:fixture"
        ),
        graph,
    )
    assert action["execution_performed"] is False
    assert action["second_executor_introduced"] is False
    assert action["execution_mode"] == "explicit_authorization_required"
    assert action["scientific_status_upgrade_authorized"] is False


def test_phase_e_structural_sensitivity_and_priority_do_not_fabricate_eig() -> None:
    new_cell = StructuralDesignCandidate(
        "new-cell",
        design_config(proposed=[
            {"cell_id": "p1", "factor_values": {"power": 0.0, "speed": 1.0}, "replicates": 1}
        ]),
        1.0,
    )
    replicate = StructuralDesignCandidate(
        "replicate",
        design_config(proposed=[
            {"cell_id": "p2", "factor_values": {"power": 0.0, "speed": 0.0}, "replicates": 1}
        ]),
        1.0,
    )
    assessments = structural_design_sensitivity((new_cell, replicate))
    assert assessments[0].rank_gain > assessments[1].rank_gain
    selected = select_structural_design_candidate((new_cell, replicate), remaining_budget=2.0)
    assert selected["selected_candidate_id"] == "new-cell"
    assert selected["expected_information_gain"] == {"status": "not_quantified", "value": None}
    assert selected["physical_experiment_execution_authorized"] is False
    assert selected["scientific_status_upgrade_authorized"] is False
