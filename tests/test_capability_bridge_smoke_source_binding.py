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
            content_type="text/html",
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


def test_bridge_smoke_witness_is_the_exact_f0da_live_source_version() -> None:
    assert bridge.SMOKE_SOURCE_ID == "nist-official-amb2018-02-description"
    assert bridge.SMOKE_SOURCE_URL == "https://www.nist.gov/ambench/amb2018-02-description"
    assert bridge.SMOKE_SOURCE_SHA256 == (
        "9c7fd41e9f82b5412097448a40892e3dbf80c6e237075fbe9294ab69224d55da"
    )
    assert bridge.SMOKE_SOURCE_SIZE_BYTES == 104_348
