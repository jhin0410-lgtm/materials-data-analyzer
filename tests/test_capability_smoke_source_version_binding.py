from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest

from materials_data_analyzer.research_loop import (
    autonomous_production_exact_head_p2_round8 as round8,
)
from materials_data_analyzer.research_loop import capability_smoke_replay_evidence
from materials_data_analyzer.research_loop import (
    nist_ammt_calibration_candidate_acquisition as candidate_acquisition,
)
from materials_data_analyzer.research_loop import (
    nist_ammt_candidate_acquisition_policy as candidate_policy,
)
from materials_data_analyzer.research_loop import (
    nist_ammt_calibration_source_discovery as source_discovery,
)
from materials_data_analyzer.research_loop.in625_geometry_condition_source_acquisition import (
    FetchResult,
)

ROOT = Path(__file__).resolve().parents[1]


def _self_consistent_replay_evidence(
    *,
    action_class: str,
    witnesses: tuple[Any, ...],
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


def _visible_binding(text: str) -> tuple[str, int]:
    raw = text.encode("utf-8")
    return hashlib.sha256(raw).hexdigest(), len(raw)


def _discovery_fixture(script_token: str, *, target: str = "test") -> bytes:
    return (
        "<html><body>AMMT<ul><li>Laser calibration "
        f'<a href="https://www.nist.gov/publications/{target}">Laser calibration</a>'
        "</li></ul>"
        f"<script>volatile_cloudflare_token={script_token}</script>"
        "</body></html>"
    ).encode()


def _candidate_fixture(script_token: str) -> bytes:
    return (
        "<html><body>Published Author(s) Download Paper "
        '<a href="https://tsapps.nist.gov/publication/get_pdf.cfm?pub_id=935350">'
        f"{candidate_policy.FULL_TEXT_LINK_LABEL}</a>"
        f"<script>volatile_runtime_token={script_token}</script>"
        "</body></html>"
    ).encode()


def test_promotion_two_ignores_non_authority_runtime_bytes_but_binds_semantics() -> None:
    reviewed_body = _discovery_fixture("reviewed")
    replay_body = _discovery_fixture("new-request")
    assert hashlib.sha256(reviewed_body).digest() != hashlib.sha256(replay_body).digest()

    reviewed_candidates, reviewed_text = source_discovery._candidate_records(reviewed_body)
    text_sha, text_size = _visible_binding(reviewed_text)
    witness = round8.SemanticHtmlWitness(
        requested_url="https://www.nist.gov/el/ammt/relevant-publications",
        allowed_hosts=("www.nist.gov",),
        max_bytes=2_097_152,
        timeout_seconds=60,
        final_url="https://www.nist.gov/el/ammt/relevant-publications",
        visible_text_sha256=text_sha,
        visible_text_utf8_bytes=text_size,
    )
    expected_candidates_sha = source_discovery._canonical_sha(reviewed_candidates)
    evidence, specification_sha, candidate_sha, mission_sha = _self_consistent_replay_evidence(
        action_class="experiment_specific_calibration_record_source_discovery",
        witnesses=(witness,),
        bodies=(replay_body,),
    )

    round8.verify_discovery_semantic_witness(
        evidence,
        action_class="experiment_specific_calibration_record_source_discovery",
        capability_specification_sha256=specification_sha,
        capability_candidate_sha256=candidate_sha,
        mission_sha256=mission_sha,
        witness=witness,
        expected_candidates_sha256=expected_candidates_sha,
    )


def test_promotion_two_candidate_authority_drift_fails_even_when_visible_text_is_same() -> None:
    reviewed_body = _discovery_fixture("reviewed", target="test")
    forged_body = _discovery_fixture("forged", target="other")
    reviewed_candidates, reviewed_text = source_discovery._candidate_records(reviewed_body)
    _forged_candidates, forged_text = source_discovery._candidate_records(forged_body)
    assert reviewed_text == forged_text

    text_sha, text_size = _visible_binding(reviewed_text)
    witness = round8.SemanticHtmlWitness(
        requested_url="https://www.nist.gov/el/ammt/relevant-publications",
        allowed_hosts=("www.nist.gov",),
        max_bytes=2_097_152,
        timeout_seconds=60,
        final_url="https://www.nist.gov/el/ammt/relevant-publications",
        visible_text_sha256=text_sha,
        visible_text_utf8_bytes=text_size,
    )
    evidence, specification_sha, candidate_sha, mission_sha = _self_consistent_replay_evidence(
        action_class="experiment_specific_calibration_record_source_discovery",
        witnesses=(witness,),
        bodies=(forged_body,),
    )

    with pytest.raises(
        round8.AutonomousProductionExactHeadRound8Error,
        match="ranked discovery candidate projection drifted",
    ):
        round8.verify_discovery_semantic_witness(
            evidence,
            action_class="experiment_specific_calibration_record_source_discovery",
            capability_specification_sha256=specification_sha,
            capability_candidate_sha256=candidate_sha,
            mission_sha256=mission_sha,
            witness=witness,
            expected_candidates_sha256=source_discovery._canonical_sha(reviewed_candidates),
        )


def test_promotion_three_allows_runtime_html_drift_but_exactly_binds_primary_pdf() -> None:
    reviewed_page = _candidate_fixture("reviewed")
    replay_page = _candidate_fixture("new-request")
    reviewed_text, derived_url = candidate_acquisition._parse_candidate_page(
        reviewed_page,
        "https://www.nist.gov/publications/laser-calibration-powder-bed-fusion-additive-manufacturing-process",
    )
    text_sha, text_size = _visible_binding(reviewed_text)
    html_witness = round8.SemanticHtmlWitness(
        requested_url="https://www.nist.gov/publications/laser-calibration-powder-bed-fusion-additive-manufacturing-process",
        allowed_hosts=("www.nist.gov",),
        max_bytes=2_097_152,
        timeout_seconds=90,
        final_url="https://www.nist.gov/publications/laser-calibration-powder-bed-fusion-additive-manufacturing-process",
        visible_text_sha256=text_sha,
        visible_text_utf8_bytes=text_size,
    )
    pdf_body = b"%PDF-synthetic-reviewed-primary"
    pdf_witness = round8.ExactSourceWitness(
        requested_url=derived_url,
        allowed_hosts=("tsapps.nist.gov",),
        max_bytes=16_777_216,
        timeout_seconds=90,
        final_url=derived_url,
        source_sha256=hashlib.sha256(pdf_body).hexdigest(),
        source_size_bytes=len(pdf_body),
    )
    evidence, specification_sha, candidate_sha, mission_sha = _self_consistent_replay_evidence(
        action_class="experiment_specific_calibration_record_candidate_acquisition",
        witnesses=(html_witness, pdf_witness),
        bodies=(replay_page, pdf_body),
    )

    round8.verify_candidate_semantic_and_static_witness(
        evidence,
        action_class="experiment_specific_calibration_record_candidate_acquisition",
        capability_specification_sha256=specification_sha,
        capability_candidate_sha256=candidate_sha,
        mission_sha256=mission_sha,
        html_witness=html_witness,
        pdf_witness=pdf_witness,
    )


def test_promotion_three_same_size_rehashed_primary_pdf_fails_external_witness() -> None:
    page = _candidate_fixture("runtime")
    visible_text, derived_url = candidate_acquisition._parse_candidate_page(
        page,
        "https://www.nist.gov/publications/laser-calibration-powder-bed-fusion-additive-manufacturing-process",
    )
    text_sha, text_size = _visible_binding(visible_text)
    html_witness = round8.SemanticHtmlWitness(
        requested_url="https://www.nist.gov/publications/laser-calibration-powder-bed-fusion-additive-manufacturing-process",
        allowed_hosts=("www.nist.gov",),
        max_bytes=2_097_152,
        timeout_seconds=90,
        final_url="https://www.nist.gov/publications/laser-calibration-powder-bed-fusion-additive-manufacturing-process",
        visible_text_sha256=text_sha,
        visible_text_utf8_bytes=text_size,
    )
    reviewed_pdf = b"%PDF-reviewed"
    forged_pdf = b"%PDF-forged!!"
    assert len(reviewed_pdf) == len(forged_pdf)
    pdf_witness = round8.ExactSourceWitness(
        requested_url=derived_url,
        allowed_hosts=("tsapps.nist.gov",),
        max_bytes=16_777_216,
        timeout_seconds=90,
        final_url=derived_url,
        source_sha256=hashlib.sha256(reviewed_pdf).hexdigest(),
        source_size_bytes=len(reviewed_pdf),
    )
    evidence, specification_sha, candidate_sha, mission_sha = _self_consistent_replay_evidence(
        action_class="experiment_specific_calibration_record_candidate_acquisition",
        witnesses=(html_witness, pdf_witness),
        bodies=(page, forged_pdf),
    )

    with pytest.raises(
        round8.AutonomousProductionExactHeadRound8Error,
        match="primary PDF SHA-256 drifted",
    ):
        round8.verify_candidate_semantic_and_static_witness(
            evidence,
            action_class="experiment_specific_calibration_record_candidate_acquisition",
            capability_specification_sha256=specification_sha,
            capability_candidate_sha256=candidate_sha,
            mission_sha256=mission_sha,
            html_witness=html_witness,
            pdf_witness=pdf_witness,
        )


def test_round8_witnesses_match_reviewed_7e734c7_authority_projection() -> None:
    assert round8.WITNESS_ORIGIN_RUN_ID == 34_430_156_288
    assert round8.WITNESS_ORIGIN_ARTIFACT_ID == 10_134_264_310
    assert round8.WITNESS_ORIGIN_ARTIFACT_DIGEST == (
        "sha256:b895422a03bf1eedb3009695fa177e3fceae61f15d722970515a7ff383df0a9b"
    )

    assert round8.DISCOVERY_HTML_WITNESS.visible_text_sha256 == (
        "f6c5ebe90021efaae19146480b48e40ec8c41de2c5e0aab01cae648a0a786ed7"
    )
    assert round8.DISCOVERY_HTML_WITNESS.visible_text_utf8_bytes == 15_535
    assert round8.DISCOVERY_CANDIDATES_SHA256 == (
        "f915580b047dbd95e5bd47b44aeeefc2e706b439d0e016ff3ce64bbadb0845f8"
    )
    assert round8.CANDIDATE_HTML_WITNESS.visible_text_sha256 == (
        "29652d89ebe37d973d351015a3d0ba2b29f3f974dc39cc678e5f9a9205bafddb"
    )
    assert round8.CANDIDATE_HTML_WITNESS.visible_text_utf8_bytes == 4_625
    assert round8.CANDIDATE_FULL_TEXT_WITNESS.source_size_bytes == 2_264_822
    assert round8.CANDIDATE_FULL_TEXT_WITNESS.source_sha256 == (
        "76a95c1ce41240db355752cd537cca66467999e20b260e263a4e83af19f1b8d7"
    )


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
