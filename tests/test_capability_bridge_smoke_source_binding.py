from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop import (
    autonomous_production_exact_head_p2_round6 as round6,
)
from materials_data_analyzer.research_loop import calibration_protocol_bridge_capability as bridge
from materials_data_analyzer.research_loop import capability_expansion
from materials_data_analyzer.research_loop import capability_registry
from materials_data_analyzer.research_loop import capability_resolver
from materials_data_analyzer.research_loop import capability_smoke_replay_evidence
from materials_data_analyzer.research_loop import capability_verifier
from materials_data_analyzer.research_loop import in625_geometry_condition_multisource_policy as policy
from materials_data_analyzer.research_loop.in625_geometry_condition_source_acquisition import (
    FetchResult,
)

ROOT = Path(__file__).resolve().parents[1]
MISSION = ROOT / "configs/research/autonomous_in625_production_mission.v1.json"
MISSION_SHA = hashlib.sha256(MISSION.read_bytes()).hexdigest()
REGISTRY = ROOT / "configs/research/in625_geometry_condition_source_reconnaissance.v1.json"


def _canonical_sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _canonical_bridge_candidate() -> tuple[dict[str, object], dict[str, object]]:
    next_action = {
        "action_class": bridge.ACTION_CLASS,
        "objective": "Reacquire the exact mission-authorized bridge source set.",
        "eligible_evidence_lanes": ["official_calibration_or_metrology_documentation"],
        "automatic_unrestricted_search_authorized": False,
        "caller_authored_arbitrary_urls_authorized": False,
    }
    predecessor = {
        "schema_version": "bridge-smoke-binding-test-1.0",
        "next_action": next_action,
        "scientific_status_changed": False,
    }
    predecessor["report_sha256_without_self_field"] = _canonical_sha(predecessor)
    registry = capability_registry.build_initial_capability_registry(
        verified_action_classes=round6._INITIAL_VERIFIED_ACTIONS,
    )
    gap = capability_expansion.build_capability_gap(
        requested_action=next_action,
        predecessor_report=predecessor,
        available_action_classes=round6._INITIAL_VERIFIED_ACTIONS,
    )
    specification = capability_expansion.build_capability_specification(gap)
    resolution = capability_resolver.resolve_or_discover_capability(
        registry=registry,
        capability_specification=specification,
        available_verified_primitives=bridge.REQUIRED_VERIFIED_PRIMITIVES,
    )
    candidate = resolution["candidate"]
    assert isinstance(candidate, dict)
    return specification, candidate


def _self_consistently_hashed_forged_replay_evidence(
    *,
    specification: dict[str, object],
    candidate: dict[str, object],
) -> dict[str, object]:
    forged_body = b"x" * bridge.SMOKE_SOURCE_SIZE_BYTES
    assert hashlib.sha256(forged_body).hexdigest() != bridge.SMOKE_SOURCE_SHA256

    def forged_delegate(
        url: str,
        *,
        allowed_hosts: tuple[str, ...],
        max_bytes: int,
        timeout_seconds: int,
    ) -> FetchResult:
        assert url == bridge.SMOKE_SOURCE_URL
        assert allowed_hosts == policy.ALLOWED_HOSTS
        assert max_bytes == policy.MAX_SOURCE_BYTES
        assert timeout_seconds == policy.TIMEOUT_SECONDS
        return FetchResult(
            body=forged_body,
            final_url=bridge.SMOKE_SOURCE_URL,
            status_code=200,
            content_type="application/pdf;charset=UTF-8",
        )

    recorder = capability_smoke_replay_evidence.RecordingFetcher(forged_delegate)
    recorder(
        bridge.SMOKE_SOURCE_URL,
        allowed_hosts=policy.ALLOWED_HOSTS,
        max_bytes=policy.MAX_SOURCE_BYTES,
        timeout_seconds=policy.TIMEOUT_SECONDS,
    )
    spec_sha = specification["capability_specification_sha256_without_self_field"]
    candidate_sha = candidate["capability_candidate_sha256_without_self_field"]
    assert isinstance(spec_sha, str)
    assert isinstance(candidate_sha, str)
    return capability_smoke_replay_evidence.build_smoke_replay_evidence(
        action_class=bridge.ACTION_CLASS,
        capability_specification_sha256=spec_sha,
        capability_candidate_sha256=candidate_sha,
        mission_sha256=MISSION_SHA,
        verification_context=None,
        fetch_records=recorder.records,
    )


def test_self_consistently_rehashed_bridge_smoke_body_cannot_regenerate_passing_receipt() -> None:
    specification, candidate = _canonical_bridge_candidate()
    replay_evidence = _self_consistently_hashed_forged_replay_evidence(
        specification=specification,
        candidate=candidate,
    )

    # The packet, byte record, request/response contract, and every local self-hash are valid.
    # Verification must still fail because the body digest is independently pinned by the exact
    # implementation bytes, which are themselves bound into capability verification receipts.
    with pytest.raises(
        bridge.CalibrationProtocolBridgeCapabilityError,
        match="body SHA-256 drifted from pinned historical source",
    ):
        capability_verifier.verify_bounded_capability_candidate(
            capability_specification=specification,
            candidate=candidate,
            available_verified_primitives=bridge.REQUIRED_VERIFIED_PRIMITIVES,
            repository_root=ROOT,
            mission_path=MISSION,
            expected_mission_sha256=MISSION_SHA,
            perform_real_source_smoke=False,
            verification_context=None,
            retained_smoke_replay_evidence=replay_evidence,
        )


def test_bridge_smoke_witness_is_exact_stable_primary_pdf_source() -> None:
    assert bridge.SMOKE_SOURCE_ID == "lane-2020-melt-pool-geometry"
    assert bridge.SMOKE_SOURCE_URL == (
        "https://tsapps.nist.gov/publication/get_pdf.cfm?pub_id=927485"
    )
    assert bridge.SMOKE_SOURCE_SHA256 == (
        "39de5e6987461c3cf607e544d202cfdc3f28dffd2e0ec298175df63803b99640"
    )
    assert bridge.SMOKE_SOURCE_SIZE_BYTES == 1_874_330

    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    matches = [
        item
        for item in registry["sources"]
        if item.get("source_id") == bridge.SMOKE_SOURCE_ID
    ]
    assert len(matches) == 1
    assert matches[0]["url"] == bridge.SMOKE_SOURCE_URL
    assert matches[0]["media_type"] == "pdf"
    claim_ids = {
        claim["claim_id"] for claim in matches[0]["claims_under_review"]
    }
    assert {
        "lane-ammt-corrected-cases",
        "lane-ammt-cbm-spot-diameters",
        "lane-cross-section-uncertainty-exists",
    } <= claim_ids
