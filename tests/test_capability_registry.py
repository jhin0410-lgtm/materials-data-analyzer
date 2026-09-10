from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop import (
    autonomous_production_exact_head_p2_round5 as round5,
)
from materials_data_analyzer.research_loop import (
    autonomous_production_exact_head_p2_round6 as round6,
)
from materials_data_analyzer.research_loop import (
    capability_expansion,
    capability_registry,
    capability_resolver,
)


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


def _write_json(root: Path, name: str, value: object) -> None:
    (root / name).write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _capability_name(stem: str, suffix: str) -> str:
    return f"{stem}{suffix}.json"


def test_full_registry_promotion_lineage_rejects_fabricated_verified_record(
    tmp_path: Path,
) -> None:
    initial_actions = list(round6._INITIAL_VERIFIED_ACTIONS)
    registry = capability_registry.build_initial_capability_registry(
        verified_action_classes=initial_actions
    )
    _write_json(tmp_path, "capability-registry-initial.json", registry)

    available_actions = list(initial_actions)
    promoted_registries: list[dict[str, object]] = []
    for step, (
        suffix,
        action_class,
        implementation_id,
        _cycle_index,
        _manifest_field,
    ) in enumerate(round6._PROMOTIONS, start=1):
        gap = capability_expansion.build_capability_gap(
            requested_action={
                "action_class": action_class,
                "objective": f"Execute audited capability promotion {step}.",
                "eligible_evidence_lanes": [],
            },
            predecessor_report={"report_sha256_without_self_field": "a" * 64},
            available_action_classes=available_actions,
        )
        specification = capability_expansion.build_capability_specification(gap)
        candidate = capability_registry.build_capability_candidate(
            capability_specification=specification,
            factory_id=f"synthetic-audited-factory-{step}",
            implementation_id=implementation_id,
            mechanism="compose_verified_primitives",
            required_verified_primitives=[],
        )
        verification = capability_registry.build_capability_verification_receipt(
            capability_specification=specification,
            candidate=candidate,
            available_verified_primitives=[],
            verification_results=_passing_results(specification),
        )
        registry = capability_registry.promote_verified_capability(
            registry=registry,
            candidate=candidate,
            verification_receipt=verification,
        )
        resolution = capability_resolver.resolve_or_discover_capability(
            registry=registry,
            capability_specification=specification,
            available_verified_primitives=[],
        )
        _write_json(
            tmp_path,
            _capability_name("capability-specification", suffix),
            specification,
        )
        _write_json(
            tmp_path,
            _capability_name("capability-candidate", suffix),
            candidate,
        )
        _write_json(
            tmp_path,
            _capability_name("capability-verification", suffix),
            verification,
        )
        _write_json(
            tmp_path,
            _capability_name("capability-registry-promoted", suffix),
            registry,
        )
        _write_json(
            tmp_path,
            _capability_name("capability-post-promotion-resolution", suffix),
            resolution,
        )
        promoted_registries.append(copy.deepcopy(registry))
        available_actions.append(action_class)

    terminal_action = {
        "action_class": "weaver_2021_spot_size_full_text_derived_acquisition",
        "objective": "Acquire exact Weaver primary full text.",
        "eligible_evidence_lanes": ["paper_and_supplementary_material"],
        "automatic_acquisition_authorized": False,
        "caller_authored_url_authorized": False,
        "unrestricted_search_authorized": False,
    }
    reference_graph: dict[str, object] = {
        "schema_version": "1.0",
        "next_action": terminal_action,
        "scientific_status_changed": False,
    }
    reference_graph["report_sha256_without_self_field"] = (
        capability_registry._canonical_sha(reference_graph)
    )
    _write_json(
        tmp_path,
        "mds2-2923-experiment-identity-reference-chain.json",
        reference_graph,
    )

    cycles: list[dict[str, object]] = [
        {"cycle_index": index} for index in range(1, 13)
    ]
    for registry_value, promotion in zip(
        promoted_registries,
        round6._PROMOTIONS,
        strict=True,
    ):
        cycle_index = promotion[3]
        cycles[cycle_index - 1]["promoted_registry_sha256"] = registry_value[
            "capability_registry_sha256_without_self_field"
        ]
    cycles[11].update(
        {
            "reference_graph_sha256": reference_graph[
                "report_sha256_without_self_field"
            ],
            "output_next_action_class": terminal_action["action_class"],
        }
    )
    manifest: dict[str, object] = {"cycles": cycles}
    for registry_value, promotion in zip(
        promoted_registries,
        round6._PROMOTIONS,
        strict=True,
    ):
        manifest_field = promotion[4]
        if manifest_field is not None:
            manifest[manifest_field] = registry_value[
                "capability_registry_sha256_without_self_field"
            ]
    _write_json(tmp_path, "autonomous-production-manifest.json", manifest)

    registry4 = promoted_registries[-1]
    gap5 = capability_expansion.build_capability_gap(
        requested_action=terminal_action,
        predecessor_report=reference_graph,
        available_action_classes=sorted(
            record["action_class"]
            for record in registry4["records"]  # type: ignore[index]
            if record["state"] == "verified"
        ),
    )
    spec5 = capability_expansion.build_capability_specification(gap5)
    resolution5 = capability_resolver.resolve_or_discover_capability(
        registry=registry4,
        capability_specification=spec5,
        available_verified_primitives=[],
    )
    _write_json(tmp_path, "capability-gap-5.json", gap5)
    _write_json(tmp_path, "capability-specification-5.json", spec5)
    _write_json(tmp_path, "capability-resolution-5.json", resolution5)

    round6.verify_exact_head_round6_boundaries(tmp_path)
    round5.verify_exact_head_round5_boundaries(tmp_path)

    forged_registry4 = copy.deepcopy(registry4)
    forged_registry4["records"].append(  # type: ignore[index,union-attr]
        {
            "action_class": "fabricated_verified_analysis_capability",
            "state": "verified",
            "origin": "independently_verified_capability_expansion",
            "candidate_sha256": "c" * 64,
            "verification_sha256": "d" * 64,
            "implementation_id": "fabricated-analysis-v1",
        }
    )
    unsigned_registry = dict(forged_registry4)
    unsigned_registry.pop("capability_registry_sha256_without_self_field")
    forged_registry4["capability_registry_sha256_without_self_field"] = (
        capability_registry._canonical_sha(unsigned_registry)
    )
    _write_json(tmp_path, "capability-registry-promoted-4.json", forged_registry4)

    forged_registry_sha = forged_registry4[
        "capability_registry_sha256_without_self_field"
    ]
    cycles[11]["promoted_registry_sha256"] = forged_registry_sha
    manifest["cycles"] = cycles
    _write_json(tmp_path, "autonomous-production-manifest.json", manifest)

    forged_gap5 = capability_expansion.build_capability_gap(
        requested_action=terminal_action,
        predecessor_report=reference_graph,
        available_action_classes=sorted(
            record["action_class"]
            for record in forged_registry4["records"]  # type: ignore[index]
            if record["state"] == "verified"
        ),
    )
    forged_spec5 = capability_expansion.build_capability_specification(forged_gap5)
    forged_resolution5 = capability_resolver.resolve_or_discover_capability(
        registry=forged_registry4,
        capability_specification=forged_spec5,
        available_verified_primitives=[],
    )
    _write_json(tmp_path, "capability-gap-5.json", forged_gap5)
    _write_json(tmp_path, "capability-specification-5.json", forged_spec5)
    _write_json(tmp_path, "capability-resolution-5.json", forged_resolution5)

    # Round 5 treats the self-hashed promoted registry as an authenticated input, so the
    # fabricated unrelated verified capability survives if all terminal derivatives are
    # consistently rebuilt around that forged registry.
    round5.verify_exact_head_round5_boundaries(tmp_path)

    with pytest.raises(
        round6.AutonomousProductionExactHeadRound6Error,
        match="capability promotion 4 registry drifted from canonical successor",
    ):
        round6.verify_exact_head_round6_boundaries(tmp_path)
