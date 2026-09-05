from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop import (
    autonomous_production_exact_head_p2_round4 as round4,
)
from materials_data_analyzer.research_loop import (
    autonomous_production_exact_head_p2_round5 as round5,
)
from materials_data_analyzer.research_loop import (
    calibration_protocol_bridge_capability as bridge,
)
from materials_data_analyzer.research_loop import (
    capability_expansion,
    capability_registry,
    capability_resolver,
    capability_verifier,
)
from materials_data_analyzer.research_loop import (
    nist_ammt_calibration_source_discovery as discovery,
)


ROOT = Path(__file__).resolve().parents[1]
MISSION = ROOT / "configs/research/autonomous_in625_production_mission.v1.json"
MISSION_SHA = "7de1c78d1411805623a4687a6d1956517edc009abe5790a0870e89ab6ccb4e88"


def _spec(action_class: str = bridge.ACTION_CLASS) -> dict[str, object]:
    gap = capability_expansion.build_capability_gap(
        requested_action={
            "action_class": action_class,
            "objective": "Acquire exact evidence.",
            "eligible_evidence_lanes": ["paper_and_supplementary_material"],
        },
        predecessor_report={"report_sha256_without_self_field": "a" * 64},
        available_action_classes=[],
    )
    return capability_expansion.build_capability_specification(gap)


def test_resolver_discovers_only_finite_bridge_factory() -> None:
    registry = capability_registry.build_initial_capability_registry(
        verified_action_classes=[]
    )
    result = capability_resolver.resolve_or_discover_capability(
        registry=registry,
        capability_specification=_spec(),
        available_verified_primitives=bridge.REQUIRED_VERIFIED_PRIMITIVES,
    )
    assert result["resolution_status"] == "bounded_candidate_discovered"
    assert result["factory_id"] == bridge.FACTORY_ID
    assert result["candidate"]["state"] == "candidate"
    assert result["candidate"]["implementation_id"] == bridge.IMPLEMENTATION_ID
    assert result["factory_catalogue_size"] == 5
    assert result["unrestricted_discovery_performed"] is False
    assert result["arbitrary_code_generation_performed"] is False


def test_resolver_discovers_finite_nist_index_factory_only_with_required_primitives() -> None:
    registry = capability_registry.build_initial_capability_registry(
        verified_action_classes=[]
    )
    spec = _spec(discovery.ACTION_CLASS)
    result = capability_resolver.resolve_or_discover_capability(
        registry=registry,
        capability_specification=spec,
        available_verified_primitives=discovery.REQUIRED_VERIFIED_PRIMITIVES,
    )
    assert result["resolution_status"] == "bounded_candidate_discovered"
    assert result["factory_id"] == discovery.FACTORY_ID
    assert result["factory_catalogue_size"] == 5
    assert result["candidate"]["implementation_id"] == discovery.IMPLEMENTATION_ID
    assert result["candidate"]["mechanism"] == "generate_declarative_adapter_instance"
    assert result["candidate"]["network_authority_granted"] is False
    assert result["candidate"]["execution_authority_granted"] is False

    missing = capability_resolver.resolve_or_discover_capability(
        registry=registry,
        capability_specification=spec,
        available_verified_primitives=discovery.REQUIRED_VERIFIED_PRIMITIVES[:-1],
    )
    assert missing["resolution_status"] == "no_bounded_candidate_available"
    assert missing["candidate"] is None


def test_resolver_does_not_invent_candidate_for_unknown_action() -> None:
    registry = capability_registry.build_initial_capability_registry(
        verified_action_classes=[]
    )
    result = capability_resolver.resolve_or_discover_capability(
        registry=registry,
        capability_specification=_spec("unseen_untrusted_action"),
        available_verified_primitives=bridge.REQUIRED_VERIFIED_PRIMITIVES,
    )
    assert result["resolution_status"] == "no_bounded_candidate_available"
    assert result["candidate"] is None
    assert result["factory_catalogue_size"] == 5
    assert result["arbitrary_code_generation_performed"] is False


def test_missing_verified_primitive_prevents_candidate_discovery() -> None:
    registry = capability_registry.build_initial_capability_registry(
        verified_action_classes=[]
    )
    result = capability_resolver.resolve_or_discover_capability(
        registry=registry,
        capability_specification=_spec(),
        available_verified_primitives=bridge.REQUIRED_VERIFIED_PRIMITIVES[:-1],
    )
    assert result["resolution_status"] == "no_bounded_candidate_available"


def test_discovery_fixture_excludes_untrusted_host_and_never_authorizes_acquisition() -> None:
    fixture = b"""
    <html><body><h1>AMMT Relevant Publications</h1><ul>
      <li><a href='/publications/laser-calibration-powder-bed-fusion-additive-manufacturing-process'>Laser Calibration for Powder Bed Fusion Additive Manufacturing Process</a></li>
      <li><a href='https://evil.example/calibration'>laser power calibration</a></li>
    </ul></body></html>
    """
    candidates, _ = discovery._candidate_records(fixture)
    assert len(candidates) == 1
    assert candidates[0]["link_host"] == "www.nist.gov"
    assert candidates[0]["candidate_url_followed"] is False
    assert candidates[0]["acquisition_authorized"] is False
    assert candidates[0]["row_level_measurement_authority"] is False


def test_independent_verifier_requires_real_source_smoke_for_network_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec = _spec()
    candidate = capability_registry.build_capability_candidate(
        capability_specification=spec,
        factory_id=bridge.FACTORY_ID,
        implementation_id=bridge.IMPLEMENTATION_ID,
        mechanism="compose_verified_primitives",
        required_verified_primitives=bridge.REQUIRED_VERIFIED_PRIMITIVES,
    )
    receipt = capability_verifier.verify_bounded_capability_candidate(
        capability_specification=spec,
        candidate=candidate,
        available_verified_primitives=bridge.REQUIRED_VERIFIED_PRIMITIVES,
        repository_root=ROOT,
        mission_path=MISSION,
        expected_mission_sha256=MISSION_SHA,
        perform_real_source_smoke=False,
    )
    assert receipt["verification_results"][
        "real_source_smoke_test_when_network_evidence_is_required"
    ] is False
    assert receipt["promotion_eligible"] is False

    fake_smoke = {
        "schema_version": "1.0",
        "smoke_status": "exact_authorized_source_retrieved",
        "policy_sha256": "b" * 64,
        "registry_git_blob_sha1": "c" * 40,
        "source_id": "nist-official-amb2018-02-description",
        "requested_url": "https://www.nist.gov/ambench/amb2018-02-description",
        "final_url": "https://www.nist.gov/ambench/amb2018-02-description",
        "source_sha256": "d" * 64,
        "source_size_bytes": 1,
        "network_requests_performed": 1,
        "unrestricted_search_performed": False,
        "arbitrary_url_fetch_performed": False,
        "scientific_status_changed": False,
        "smoke_receipt_sha256_without_self_field": "e" * 64,
    }
    monkeypatch.setattr(bridge, "smoke_exact_source_authority", lambda **kwargs: fake_smoke)
    receipt = capability_verifier.verify_bounded_capability_candidate(
        capability_specification=spec,
        candidate=candidate,
        available_verified_primitives=bridge.REQUIRED_VERIFIED_PRIMITIVES,
        repository_root=ROOT,
        mission_path=MISSION,
        expected_mission_sha256=MISSION_SHA,
        perform_real_source_smoke=True,
    )
    assert receipt["all_required_checks_passed"] is True
    assert receipt["promotion_eligible"] is True
    assert len(receipt["implementation_sha256"]) == 64
    assert len(receipt["verifier_sha256"]) == 64


def test_verified_registry_is_preferred_over_candidate_discovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec = _spec()
    candidate = capability_registry.build_capability_candidate(
        capability_specification=spec,
        factory_id=bridge.FACTORY_ID,
        implementation_id=bridge.IMPLEMENTATION_ID,
        mechanism="compose_verified_primitives",
        required_verified_primitives=bridge.REQUIRED_VERIFIED_PRIMITIVES,
    )
    fake_smoke = {
        "schema_version": "1.0",
        "smoke_status": "exact_authorized_source_retrieved",
        "network_requests_performed": 1,
        "unrestricted_search_performed": False,
        "arbitrary_url_fetch_performed": False,
        "scientific_status_changed": False,
        "smoke_receipt_sha256_without_self_field": "e" * 64,
    }
    monkeypatch.setattr(bridge, "smoke_exact_source_authority", lambda **kwargs: fake_smoke)
    receipt = capability_verifier.verify_bounded_capability_candidate(
        capability_specification=spec,
        candidate=candidate,
        available_verified_primitives=bridge.REQUIRED_VERIFIED_PRIMITIVES,
        repository_root=ROOT,
        mission_path=MISSION,
        expected_mission_sha256=MISSION_SHA,
        perform_real_source_smoke=True,
    )
    registry = capability_registry.promote_verified_capability(
        registry=capability_registry.build_initial_capability_registry(
            verified_action_classes=[]
        ),
        candidate=candidate,
        verification_receipt=receipt,
    )
    result = capability_resolver.resolve_or_discover_capability(
        registry=registry,
        capability_specification=spec,
        available_verified_primitives=[],
    )
    assert result["resolution_status"] == "verified_capability_resolved"
    assert result["implementation_id"] == bridge.IMPLEMENTATION_ID
    assert result["candidate"] is None


def test_terminal_capability_lineage_rejects_jointly_rehashed_action_substitution(
    tmp_path: Path,
) -> None:
    def canonical_sha(value: object) -> str:
        return hashlib.sha256(
            json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()

    def write_json(name: str, value: object) -> None:
        (tmp_path / name).write_text(
            json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    requested_action = {
        "action_class": "weaver_2021_spot_size_full_text_derived_acquisition",
        "objective": "Acquire the exact Weaver primary full text.",
        "candidate": {
            "doi": "10.1016/j.jmapro.2021.10.053",
            "acquisition_authorized": False,
        },
        "caller_authored_url_authorized": False,
        "automatic_acquisition_authorized": False,
        "unrestricted_search_authorized": False,
    }
    reference = {
        "schema_version": "1.0",
        "next_action": requested_action,
        "scientific_status_changed": False,
    }
    reference["report_sha256_without_self_field"] = canonical_sha(reference)

    registry = capability_registry.build_initial_capability_registry(
        verified_action_classes=["external_evidence_search"]
    )
    verified_actions = ["external_evidence_search"]
    gap = capability_expansion.build_capability_gap(
        requested_action=requested_action,
        predecessor_report=reference,
        available_action_classes=verified_actions,
    )
    specification = capability_expansion.build_capability_specification(gap)
    resolution = capability_resolver.resolve_or_discover_capability(
        registry=registry,
        capability_specification=specification,
        available_verified_primitives=[],
    )
    cycles = [{"cycle_index": index} for index in range(1, 13)]
    cycles[11].update(
        {
            "output_next_action_class": requested_action["action_class"],
            "reference_graph_sha256": reference[
                "report_sha256_without_self_field"
            ],
            "promoted_registry_sha256": registry[
                "capability_registry_sha256_without_self_field"
            ],
        }
    )

    write_json("autonomous-production-manifest.json", {"cycles": cycles})
    write_json(
        "mds2-2923-experiment-identity-reference-chain.json",
        reference,
    )
    write_json("capability-registry-promoted-4.json", registry)
    write_json("capability-gap-5.json", gap)
    write_json("capability-specification-5.json", specification)
    write_json("capability-resolution-5.json", resolution)

    round5.verify_exact_head_round5_boundaries(tmp_path)

    forged_action = dict(requested_action)
    forged_action["action_class"] = "untrusted_weaver_full_text_acquisition"
    forged_action["objective"] = "Substitute a different terminal acquisition action."
    forged_gap = capability_expansion.build_capability_gap(
        requested_action=forged_action,
        predecessor_report=reference,
        available_action_classes=verified_actions,
    )
    forged_specification = capability_expansion.build_capability_specification(forged_gap)
    forged_resolution = capability_resolver.resolve_or_discover_capability(
        registry=registry,
        capability_specification=forged_specification,
        available_verified_primitives=[],
    )
    write_json("capability-gap-5.json", forged_gap)
    write_json("capability-specification-5.json", forged_specification)
    write_json("capability-resolution-5.json", forged_resolution)

    # Round 4 authenticates this internally consistent forged terminal trio but does not
    # bind the gap's requested action back to the cycle-12 reference graph.
    round4._verify_terminal_capability_resolution(tmp_path, cycles)

    with pytest.raises(
        round5.AutonomousProductionExactHeadRound5Error,
        match="terminal capability gap drifted from the authenticated reference action",
    ):
        round5.verify_exact_head_round5_boundaries(tmp_path)
