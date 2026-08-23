from __future__ import annotations

import copy

import pytest

from materials_data_analyzer.research_loop import capability_expansion, capability_registry


ACTION_CLASS = "ammt_mds2_2923_calibration_protocol_bridge_evidence_acquisition"
PRIMITIVES = [
    "exact_multisource_policy_authentication",
    "exact_allowlisted_source_acquisition",
    "provenance_bound_bridge_frontier_evaluation",
]


def _spec() -> dict[str, object]:
    gap = capability_expansion.build_capability_gap(
        requested_action={
            "action_class": ACTION_CLASS,
            "objective": "Acquire calibration/protocol bridge evidence.",
            "eligible_evidence_lanes": ["paper_and_supplementary_material"],
        },
        predecessor_report={"report_sha256_without_self_field": "a" * 64},
        available_action_classes=[],
    )
    return capability_expansion.build_capability_specification(gap)


def _candidate() -> dict[str, object]:
    return capability_registry.build_capability_candidate(
        capability_specification=_spec(),
        factory_id="existing-authorized-source-reacquisition-v1",
        implementation_id="ammt-calibration-bridge-existing-source-adapter-v1",
        mechanism="compose_verified_primitives",
        required_verified_primitives=PRIMITIVES,
    )


def _passing_results(spec: dict[str, object]) -> dict[str, bool]:
    return {item: True for item in spec["verification_requirements"]}  # type: ignore[index]


def test_candidate_is_not_resolvable_before_independent_verification() -> None:
    registry = capability_registry.build_initial_capability_registry(
        verified_action_classes=["reviewed_geometry_condition_mapping_assessment"]
    )
    result = capability_registry.resolve_verified_capability(
        registry=registry,
        action_class=ACTION_CLASS,
    )
    assert result["resolved"] is False
    assert result["implementation_id"] is None


def test_verified_candidate_promotes_into_immutable_successor_registry() -> None:
    spec = _spec()
    candidate = capability_registry.build_capability_candidate(
        capability_specification=spec,
        factory_id="existing-authorized-source-reacquisition-v1",
        implementation_id="ammt-calibration-bridge-existing-source-adapter-v1",
        mechanism="compose_verified_primitives",
        required_verified_primitives=PRIMITIVES,
    )
    receipt = capability_registry.build_capability_verification_receipt(
        capability_specification=spec,
        candidate=candidate,
        available_verified_primitives=PRIMITIVES,
        verification_results=_passing_results(spec),
    )
    assert receipt["promotion_eligible"] is True
    registry = capability_registry.build_initial_capability_registry(
        verified_action_classes=["reviewed_geometry_condition_mapping_assessment"]
    )
    successor = capability_registry.promote_verified_capability(
        registry=registry,
        candidate=candidate,
        verification_receipt=receipt,
    )
    assert successor["predecessor_registry_sha256"] == registry[
        "capability_registry_sha256_without_self_field"
    ]
    assert len(registry["records"]) == 1
    assert len(successor["records"]) == 2
    resolution = capability_registry.resolve_verified_capability(
        registry=successor,
        action_class=ACTION_CLASS,
    )
    assert resolution["resolved"] is True
    assert resolution["implementation_id"] == (
        "ammt-calibration-bridge-existing-source-adapter-v1"
    )


def test_failed_verifier_check_cannot_promote_candidate() -> None:
    spec = _spec()
    candidate = _candidate()
    results = _passing_results(spec)
    results["epistemic_boundary_test"] = False
    receipt = capability_registry.build_capability_verification_receipt(
        capability_specification=spec,
        candidate=candidate,
        available_verified_primitives=PRIMITIVES,
        verification_results=results,
    )
    assert receipt["promotion_eligible"] is False
    with pytest.raises(
        capability_registry.CapabilityRegistryError,
        match="did not pass independent promotion gate",
    ):
        capability_registry.promote_verified_capability(
            registry=capability_registry.build_initial_capability_registry(
                verified_action_classes=[]
            ),
            candidate=candidate,
            verification_receipt=receipt,
        )


def test_unverified_primitive_blocks_verification() -> None:
    spec = _spec()
    candidate = _candidate()
    with pytest.raises(
        capability_registry.CapabilityRegistryError,
        match="unverified primitive",
    ):
        capability_registry.build_capability_verification_receipt(
            capability_specification=spec,
            candidate=candidate,
            available_verified_primitives=PRIMITIVES[:-1],
            verification_results=_passing_results(spec),
        )


def test_candidate_cannot_self_authorize_even_if_repinned() -> None:
    spec = _spec()
    candidate = _candidate()
    tampered = copy.deepcopy(candidate)
    tampered["self_promotion_requested"] = True
    unsigned = dict(tampered)
    unsigned.pop("capability_candidate_sha256_without_self_field")
    tampered["capability_candidate_sha256_without_self_field"] = (
        capability_registry._canonical_sha(unsigned)
    )
    with pytest.raises(
        capability_registry.CapabilityRegistryError,
        match="pre-authorize itself",
    ):
        capability_registry.build_capability_verification_receipt(
            capability_specification=spec,
            candidate=tampered,
            available_verified_primitives=PRIMITIVES,
            verification_results=_passing_results(spec),
        )


def test_candidate_specification_substitution_is_rejected() -> None:
    spec = _spec()
    candidate = _candidate()
    other_spec = copy.deepcopy(spec)
    other_spec["gap_class"] = "missing_executor"
    unsigned = dict(other_spec)
    unsigned.pop("capability_specification_sha256_without_self_field")
    other_spec["capability_specification_sha256_without_self_field"] = (
        capability_registry._canonical_sha(unsigned)
    )
    with pytest.raises(
        capability_registry.CapabilityRegistryError,
        match="specification binding drifted",
    ):
        capability_registry.build_capability_verification_receipt(
            capability_specification=other_spec,
            candidate=candidate,
            available_verified_primitives=PRIMITIVES,
            verification_results=_passing_results(other_spec),
        )
