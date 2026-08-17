from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from materials_data_analyzer.characterization_use_contract import CharacterizationUseEligibility
from materials_data_analyzer.research_loop.cross_source_scientific_reasoning import (
    AnalysisTraits,
    ComparabilityContext,
    CrossSourceReasoningError,
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
    CandidateResearchAction,
    ScientificSimulationRegistry,
    ScientificSimulationRegistryError,
    SimulationRequest,
    SolverSpec,
    callable_module_sha256,
    finite_difference_sensitivity,
    select_information_gain_action,
)


ARTIFACT_SHA = hashlib.sha256(b"source-artifact").hexdigest()


def _provenance(locator: str = "row:1") -> ProvenanceLocator:
    return ProvenanceLocator("fixture-source", ARTIFACT_SHA, locator)


def _material() -> MaterialComposition:
    return MaterialComposition(
        "IN625 fixture",
        "mass_percent",
        {"Ni": 60.0, "Cr": 22.0, "Mo": 9.0, "Nb": 3.5},
    )


def _measurement() -> NormalizedMeasurement:
    return NormalizedMeasurement(
        material=_material(),
        sample_id="sample-001",
        property_name="yield_strength",
        value=810.0,
        unit="MPa",
        method="tensile_test",
        instrument_model="fixture-frame",
        calibration_id="cal-001",
        process_signature="lpbf:p1",
        standard_uncertainty=5.0,
        provenance=_provenance(),
    )


def _program_state() -> dict[str, object]:
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


def _eligibility(*, allowed: bool = True, review_status: str = "reviewed") -> CharacterizationUseEligibility:
    return CharacterizationUseEligibility(
        requested_use="descriptive",
        allowed=allowed,
        maximum_allowed_use="descriptive",
        policy_source="fixture",
        evidence_level="Supported",
        feature_stage="observable",
        review_status=review_status,
        independence_group_field=None,
        split_group_field=None,
        measurement_timing="unknown",
        reasons=(),
        warnings=(),
        limitations=(),
    )


def _linear_backend(values: dict[str, float]) -> tuple[float, float, float]:
    return 2.0 * values["temperature"], 0.5, 0.2


def _simulation_graph(evidence_node: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "graph_id": "fixture-graph",
        "research_scope": "acceptance test only",
        "nodes": [
            evidence_node,
            {
                "node_id": "claim:fixture",
                "node_type": "claim",
                "statement": "Fixture claim under test.",
            },
        ],
        "edges": [],
    }


def test_phase_b_normalization_requires_explicit_composition_basis_and_emits_existing_graph_node(tmp_path: Path) -> None:
    measurement = _measurement()
    node = build_epistemic_evidence_node(
        measurement,
        workstream_id="in625",
        evidence_role="external_raw",
        evidence_quality="supported",
    )
    graph = {
        "schema_version": "1.0",
        "graph_id": "phase-b",
        "research_scope": "normalization acceptance",
        "nodes": [node],
        "edges": [],
    }
    validated = validate_epistemic_graph(
        graph, program_state=_program_state(), artifact_root=tmp_path
    )
    assert validated["nodes"][0]["metadata"]["semantic_inference_performed"] is False
    assert validated["nodes"][0]["metadata"]["material"]["basis"] == "mass_percent"

    with pytest.raises(ScientificEvidenceNormalizationError, match="basis"):
        MaterialComposition("bad", "unknown", {"Ni": 1.0})
    with pytest.raises(ScientificEvidenceNormalizationError, match="exceeds"):
        MaterialComposition("bad", "mass_fraction", {"Ni": 1.1})


def test_phase_c_comparability_is_fail_closed_and_contradiction_requires_independence() -> None:
    left_context = ComparabilityContext(
        _material().material_id,
        "effect",
        "MPa",
        "lpbf:p1",
        "frame-a",
        "cal-a",
        "source-a",
        "independent-a",
    )
    right_context = ComparabilityContext(
        _material().material_id,
        "effect",
        "GPa",
        "lpbf:p1",
        "frame-b",
        "cal-b",
        "source-b",
        "independent-b",
    )
    assert assess_comparability(left_context, right_context).comparable is False
    left = EffectEstimate(left_context, 10.0, 1.0)
    right = EffectEstimate(right_context, -0.010, 0.001)
    contradiction, decision = detect_verified_directional_contradiction(
        left,
        right,
        explicit_unit_conversions={("GPa", "MPa"): 1000.0},
    )
    assert decision.comparable is True
    assert contradiction is True

    same_group = ComparabilityContext(
        _material().material_id,
        "effect",
        "MPa",
        "lpbf:p1",
        None,
        None,
        "source-b",
        "independent-a",
    )
    contradiction, decision = detect_verified_directional_contradiction(
        left, EffectEstimate(same_group, -10.0, 1.0)
    )
    assert contradiction is False
    assert "independence_not_demonstrated" in decision.reasons


def test_phase_c_uncertainty_and_single_analysis_selection_are_explicit() -> None:
    parts = (
        UncertaintyComponent("measurement", 3.0, "instrument"),
        UncertaintyComponent("model", 4.0, "validation"),
    )
    assert combine_uncertainty(parts, independence_explicitly_established=True) == 5.0
    assert combine_uncertainty(parts, independence_explicitly_established=False) == 7.0
    selected = select_next_analysis(AnalysisTraits(20, 2, "continuous"))
    assert selected.analysis_type == "bounded_regression"
    assert selected.executable is True
    assert select_next_analysis(AnalysisTraits(2, 1, "continuous")).executable is False
    with pytest.raises(CrossSourceReasoningError):
        select_next_analysis(AnalysisTraits(-1, 1, "continuous"))


def test_phase_d_characterization_respects_existing_policy_and_physical_sample_binding() -> None:
    registry = SampleIdentityRegistry()
    registry.bind(SampleBinding("specimen-1", "fov-1", "field_of_view", _provenance("binding")))
    measurement = normalize_characterization_measurement(
        modality="xrd",
        sample_id="fov-1",
        property_name="peak_position",
        value=44.5,
        unit="deg",
        material=_material(),
        instrument_model="fixture-diffractometer",
        calibration_id="cal-xrd",
        process_signature="lpbf:p1",
        standard_uncertainty=0.02,
        provenance=_provenance("xrd:peak:1"),
        eligibility=_eligibility(),
        identity_registry=registry,
    )
    assert measurement.sample_id == "specimen-1"
    assert measurement.method == "xrd"

    with pytest.raises(SampleIdentityBindingError, match="ambiguous"):
        registry.bind(SampleBinding("specimen-2", "fov-1", "field_of_view", _provenance("other")))
    with pytest.raises(SampleIdentityBindingError, match="blocks"):
        normalize_characterization_measurement(
            modality="xrd",
            sample_id="fov-1",
            property_name="peak_position",
            value=44.5,
            unit="deg",
            material=_material(),
            instrument_model="fixture",
            calibration_id=None,
            process_signature=None,
            standard_uncertainty=None,
            provenance=_provenance(),
            eligibility=_eligibility(allowed=False),
            identity_registry=registry,
        )


def test_phase_e_solver_is_source_attested_bounded_and_never_auto_supports_claim(tmp_path: Path) -> None:
    evidence_node = build_epistemic_evidence_node(
        _measurement(),
        workstream_id="in625",
        evidence_role="external_raw",
        evidence_quality="supported",
    )
    graph = _simulation_graph(evidence_node)
    registry = ScientificSimulationRegistry()
    spec = SolverSpec(
        solver_id="fixture-linear",
        version="1.0",
        backend_qualname=_linear_backend.__qualname__,
        module_sha256=callable_module_sha256(_linear_backend),
        input_units={"temperature": "K"},
        output_name="response",
        output_unit="arb",
        validity_ranges={"temperature": (250.0, 2000.0)},
        assumptions=("fixture acceptance-test relation only",),
    )
    registry.register(spec, _linear_backend)
    request = SimulationRequest(
        "sim-001",
        "fixture-linear",
        {"temperature": (500.0, "K")},
        (evidence_node["node_id"],),
        "claim:fixture",
    )
    package = registry.execute_to_epistemic_artifact(
        request, graph, output_path=tmp_path / "simulation.json"
    )
    assert package["result"]["scientific_boundary"]["physical_evidence_sufficiency_changed"] is False
    assert package["edges"][0]["relation"] == "tests"
    assert all(edge["relation"] != "supports" for edge in package["edges"])
    assert package["edges"][1]["source_node_id"] == package["node"]["node_id"]
    assert package["edges"][1]["target_node_id"] == evidence_node["node_id"]

    integrated = dict(graph)
    integrated["nodes"] = [*graph["nodes"], package["node"]]
    integrated["edges"] = package["edges"]
    validated = validate_epistemic_graph(
        integrated, program_state=_program_state(), artifact_root=tmp_path
    )
    assert any(node["node_type"] == "simulation" for node in validated["nodes"])

    sensitivity = finite_difference_sensitivity(
        registry, request, graph, variable="temperature"
    )
    assert sensitivity.derivative == pytest.approx(2.0)
    assert sensitivity.normalized_sensitivity == pytest.approx(1.0)

    with pytest.raises(ScientificSimulationRegistryError, match="validity range"):
        registry.evaluate(
            SimulationRequest(
                "bad",
                "fixture-linear",
                {"temperature": (5000.0, "K")},
                (evidence_node["node_id"],),
                "claim:fixture",
            ),
            graph,
        )


def test_phase_e_active_learning_keeps_physical_experiment_recommendation_only() -> None:
    physical = CandidateResearchAction("physical", "physical_experiment", 1.0, 1.0, 0.1)
    simulation = CandidateResearchAction("simulation", "simulation", 0.8, 0.8, 1.0)
    decision = select_information_gain_action(
        (simulation, physical), remaining_budget=2.0
    )
    assert decision.selected == physical
    assert decision.execution_mode == "human_authorization_required"
