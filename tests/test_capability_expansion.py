from __future__ import annotations

import copy

import pytest

from materials_data_analyzer.research_loop import capability_expansion


ACTION_CLASS = "ammt_mds2_2923_calibration_protocol_bridge_evidence_acquisition"


def _action() -> dict[str, object]:
    return {
        "action_class": ACTION_CLASS,
        "objective": "Acquire experiment-specific AMMT calibration and protocol bridge evidence.",
        "eligible_evidence_lanes": [
            "official_calibration_or_metrology_documentation",
            "paper_and_supplementary_material",
            "authoritative_repository_or_dataset",
            "characterization_evidence",
        ],
    }


def _predecessor() -> dict[str, object]:
    return {
        "report_sha256_without_self_field": "a" * 64,
        "gate_decision": {
            "directly_comparable_mds2_rows": 0,
            "issue_76_exact_target_cells_satisfied": 0,
        },
    }


def test_missing_bridge_action_becomes_source_adapter_gap_not_evidence_absence() -> None:
    gap = capability_expansion.build_capability_gap(
        requested_action=_action(),
        predecessor_report=_predecessor(),
        available_action_classes=[
            "external_evidence_search",
            "reviewed_geometry_condition_mapping_assessment",
        ],
    )
    assert gap["gap_class"] == "missing_source_adapter"
    assert gap["requested_action_class"] == ACTION_CLASS
    assert gap["predecessor_research_state_sha256"] == "a" * 64
    assert gap["evidence_absence_claimed"] is False
    assert gap["global_evidence_unavailability_claimed"] is False
    assert gap["execution_authority_granted"] is False
    assert gap["network_authority_granted"] is False
    assert gap["arbitrary_code_execution_granted"] is False
    assert gap["requires_capability_expansion"] is True
    assert gap["requires_external_authorization"] is False


def test_gap_rejected_for_action_already_available() -> None:
    with pytest.raises(
        capability_expansion.CapabilityExpansionError,
        match="already available",
    ):
        capability_expansion.build_capability_gap(
            requested_action=_action(),
            predecessor_report=_predecessor(),
            available_action_classes=[ACTION_CLASS],
        )


@pytest.mark.parametrize(
    ("action_class", "expected"),
    [
        ("new_dataset_evidence_acquisition", "missing_source_adapter"),
        ("new_parser", "missing_parser"),
        ("reviewed_model_assessment", "missing_analysis_executor"),
        ("thermal_simulation", "missing_simulation_executor"),
        ("physical_experiment_execution", "unavailable_physical_interface"),
        ("custom_action", "missing_executor"),
    ],
)
def test_gap_classification_is_deterministic(action_class: str, expected: str) -> None:
    assert capability_expansion.classify_capability_gap(action_class) == expected


def test_policy_forbidden_gap_requires_external_authorization() -> None:
    action = _action()
    gap = capability_expansion.build_capability_gap(
        requested_action=action,
        predecessor_report=_predecessor(),
        available_action_classes=[],
        policy_forbidden=True,
    )
    assert gap["gap_class"] == "policy_forbidden"
    assert gap["requires_capability_expansion"] is False
    assert gap["requires_external_authorization"] is True


def test_bridge_spec_preserves_scientific_boundaries_and_no_self_promotion() -> None:
    gap = capability_expansion.build_capability_gap(
        requested_action=_action(),
        predecessor_report=_predecessor(),
        available_action_classes=[],
    )
    spec = capability_expansion.build_capability_specification(gap)
    assert spec["requested_action_class"] == ACTION_CLASS
    assert "experiment_specific_machine_setting_to_calibrated_power_relation_or_explicit_absence" in spec[
        "required_outputs"
    ]
    assert "generate_declarative_adapter_instance" in spec[
        "allowed_implementation_mechanisms"
    ]
    assert "arbitrary_python_eval_or_exec" in spec[
        "forbidden_implementation_mechanisms"
    ]
    assert spec["promotion_policy"]["candidate_may_self_promote"] is False
    assert spec["promotion_policy"]["independent_verifier_required"] is True
    assert spec["authority_policy"]["may_synthesize_new_network_hosts"] is False
    assert spec["authority_policy"]["may_execute_physical_instrument"] is False
    assert spec["authority_policy"]["may_promote_literature_to_row_level_measurement"] is False
    assert any("Issue #76 remains 0/3" in item for item in spec["scientific_acceptance"])


def test_tampered_gap_cannot_compile_into_capability_specification() -> None:
    gap = capability_expansion.build_capability_gap(
        requested_action=_action(),
        predecessor_report=_predecessor(),
        available_action_classes=[],
    )
    tampered = copy.deepcopy(gap)
    tampered["network_authority_granted"] = True
    with pytest.raises(
        capability_expansion.CapabilityExpansionError,
        match="self binding is invalid",
    ):
        capability_expansion.build_capability_specification(tampered)


def test_repinned_gap_still_cannot_pre_authorize_network_or_execution() -> None:
    gap = capability_expansion.build_capability_gap(
        requested_action=_action(),
        predecessor_report=_predecessor(),
        available_action_classes=[],
    )
    tampered = copy.deepcopy(gap)
    tampered["network_authority_granted"] = True
    unsigned = dict(tampered)
    unsigned.pop("capability_gap_sha256_without_self_field")
    tampered["capability_gap_sha256_without_self_field"] = capability_expansion._canonical_sha(
        unsigned
    )
    with pytest.raises(
        capability_expansion.CapabilityExpansionError,
        match="cannot pre-authorize",
    ):
        capability_expansion.build_capability_specification(tampered)
