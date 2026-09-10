from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop import (
    autonomous_production_exact_head_p2_round8 as round8,
)
from materials_data_analyzer.research_loop import capability_smoke_replay_evidence
from materials_data_analyzer.research_loop.in625_geometry_condition_source_acquisition import (
    FetchResult,
)

ROOT = Path(__file__).resolve().parents[1]


def _self_consistent_replay_evidence(
    *,
    action_class: str,
    witnesses: tuple[round8.SourceVersionWitness, ...],
    bodies: tuple[bytes, ...],
) -> tuple[dict[str, object], str, str, str]:
    assert len(witnesses) == len(bodies)
    index = 0

    def delegate(
        url: str,
        *,
        allowed_hosts: tuple[str, ...],
        max_bytes: int,
        timeout_seconds: int,
    ) -> FetchResult:
        nonlocal index
        witness = witnesses[index]
        body = bodies[index]
        assert url == witness.requested_url
        assert allowed_hosts == witness.allowed_hosts
        assert max_bytes == witness.max_bytes
        assert timeout_seconds == witness.timeout_seconds
        index += 1
        return FetchResult(
            body=body,
            final_url=witness.final_url,
            status_code=200,
            content_type="application/octet-stream",
        )

    recorder = capability_smoke_replay_evidence.RecordingFetcher(delegate)
    for witness in witnesses:
        recorder(
            witness.requested_url,
            allowed_hosts=witness.allowed_hosts,
            max_bytes=witness.max_bytes,
            timeout_seconds=witness.timeout_seconds,
        )
    specification_sha = "a" * 64
    candidate_sha = "b" * 64
    mission_sha = "c" * 64
    evidence = capability_smoke_replay_evidence.build_smoke_replay_evidence(
        action_class=action_class,
        capability_specification_sha256=specification_sha,
        capability_candidate_sha256=candidate_sha,
        mission_sha256=mission_sha,
        verification_context=None,
        fetch_records=recorder.records,
    )
    return evidence, specification_sha, candidate_sha, mission_sha


def test_promotion_two_self_consistently_rehashed_source_body_fails_external_witness() -> None:
    witness = round8.DISCOVERY_SOURCE_WITNESSES[0]
    forged_body = b"x" * witness.source_size_bytes
    assert hashlib.sha256(forged_body).hexdigest() != witness.source_sha256
    evidence, specification_sha, candidate_sha, mission_sha = _self_consistent_replay_evidence(
        action_class="experiment_specific_calibration_record_source_discovery",
        witnesses=round8.DISCOVERY_SOURCE_WITNESSES,
        bodies=(forged_body,),
    )

    with pytest.raises(
        round8.AutonomousProductionExactHeadRound8Error,
        match="source 1 SHA-256 drifted from pinned live witness",
    ):
        round8.verify_retained_source_witness(
            evidence,
            action_class="experiment_specific_calibration_record_source_discovery",
            capability_specification_sha256=specification_sha,
            capability_candidate_sha256=candidate_sha,
            mission_sha256=mission_sha,
            expected_records=round8.DISCOVERY_SOURCE_WITNESSES,
            label="capability promotion 2",
        )


def test_promotion_three_second_source_cannot_be_rehashed_behind_valid_first_witness() -> None:
    page_witness, pdf_witness = round8.CANDIDATE_SOURCE_WITNESSES
    synthetic_page = b"p" * page_witness.source_size_bytes
    forged_pdf = b"q" * pdf_witness.source_size_bytes
    first_record_test_witness = page_witness._replace(
        source_sha256=hashlib.sha256(synthetic_page).hexdigest()
    )
    test_witnesses = (first_record_test_witness, pdf_witness)
    evidence, specification_sha, candidate_sha, mission_sha = _self_consistent_replay_evidence(
        action_class="experiment_specific_calibration_record_candidate_acquisition",
        witnesses=test_witnesses,
        bodies=(synthetic_page, forged_pdf),
    )

    with pytest.raises(
        round8.AutonomousProductionExactHeadRound8Error,
        match="source 2 SHA-256 drifted from pinned live witness",
    ):
        round8.verify_retained_source_witness(
            evidence,
            action_class="experiment_specific_calibration_record_candidate_acquisition",
            capability_specification_sha256=specification_sha,
            capability_candidate_sha256=candidate_sha,
            mission_sha256=mission_sha,
            expected_records=test_witnesses,
            label="capability promotion 3",
        )


def test_round8_witnesses_match_exact_7e734c7_live_artifact_source_versions() -> None:
    assert round8.WITNESS_ORIGIN_RUN_ID == 34_430_156_288
    assert round8.WITNESS_ORIGIN_ARTIFACT_ID == 10_134_264_310
    assert round8.WITNESS_ORIGIN_ARTIFACT_DIGEST == (
        "sha256:b895422a03bf1eedb3009695fa177e3fceae61f15d722970515a7ff383df0a9b"
    )

    discovery = round8.DISCOVERY_SOURCE_WITNESSES
    assert len(discovery) == 1
    assert discovery[0].source_size_bytes == 98_790
    assert discovery[0].source_sha256 == (
        "179235d723ea91905d8f6e6ce573545cfcf1f92be4a3ea4d9358c8feac46be4c"
    )

    candidate = round8.CANDIDATE_SOURCE_WITNESSES
    assert [item.source_size_bytes for item in candidate] == [82_335, 2_264_822]
    assert [item.source_sha256 for item in candidate] == [
        "4443eebf40ebcb03c32f3af9ae031165141fe4bf19d9214a474acc88cc1584f9",
        "76a95c1ce41240db355752cd537cca66467999e20b260e263a4e83af19f1b8d7",
    ]


def test_round8_witness_gate_is_wired_after_round7_and_before_registry_lineage() -> None:
    verifier = (
        ROOT
        / "src/materials_data_analyzer/research_loop/autonomous_production_live_verifier.py"
    ).read_text(encoding="utf-8")
    assert "verify_exact_head_round8_boundaries" in verifier
    assert verifier.index("verify_exact_head_round7_boundaries(output_root)") < verifier.index(
        "verify_exact_head_round8_boundaries(output_root)"
    )
    assert verifier.index("verify_exact_head_round8_boundaries(output_root)") < verifier.index(
        "verify_exact_head_round6_boundaries(output_root)"
    )
