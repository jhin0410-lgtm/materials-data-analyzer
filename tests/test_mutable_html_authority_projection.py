from __future__ import annotations

import hashlib
from typing import Any

import pytest

from materials_data_analyzer.research_loop import (
    autonomous_production_exact_head_p2_round8 as round8,
)
from materials_data_analyzer.research_loop import capability_smoke_replay_evidence as replay
from materials_data_analyzer.research_loop import (
    nist_ammt_calibration_candidate_acquisition as candidate_acquisition,
)
from materials_data_analyzer.research_loop import (
    nist_ammt_calibration_source_discovery as source_discovery,
)
from materials_data_analyzer.research_loop import (
    nist_ammt_candidate_acquisition_policy as candidate_policy,
)
from materials_data_analyzer.research_loop.in625_geometry_condition_source_acquisition import (
    FetchResult,
)


def _replay_evidence(
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

    recorder = replay.RecordingFetcher(delegate)
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
    evidence = replay.build_smoke_replay_evidence(
        action_class=action_class,
        capability_specification_sha256=specification_sha,
        capability_candidate_sha256=candidate_sha,
        mission_sha256=mission_sha,
        verification_context=None,
        fetch_records=recorder.records,
    )
    return evidence, specification_sha, candidate_sha, mission_sha


def _binding(text: str) -> tuple[str, int]:
    raw = text.encode("utf-8")
    return hashlib.sha256(raw).hexdigest(), len(raw)


def _discovery_page(*, footer: str) -> bytes:
    return (
        "<html><body>AMMT<ul><li>Laser calibration "
        '<a href="https://www.nist.gov/publications/test">Laser calibration</a>'
        "</li></ul>"
        f"<footer>{footer}</footer>"
        "</body></html>"
    ).encode()


def _candidate_page(*, footer: str, pdf_url: str) -> bytes:
    return (
        "<html><body>Published Author(s) Download Paper "
        f'<a href="{pdf_url}">{candidate_policy.FULL_TEXT_LINK_LABEL}</a>'
        f"<footer>{footer}</footer>"
        "</body></html>"
    ).encode()


def test_discovery_visible_text_drift_is_not_authority_when_ranked_candidates_match() -> None:
    reviewed = _discovery_page(footer="historical CMS footer")
    replayed = _discovery_page(footer="new mutable CMS footer text")
    reviewed_candidates, reviewed_text = source_discovery._candidate_records(reviewed)
    replayed_candidates, replayed_text = source_discovery._candidate_records(replayed)
    assert reviewed_text != replayed_text
    assert reviewed_candidates == replayed_candidates
    visible_sha, visible_size = _binding(reviewed_text)
    witness = round8.SemanticHtmlWitness(
        requested_url="https://www.nist.gov/el/ammt/relevant-publications",
        allowed_hosts=("www.nist.gov",),
        max_bytes=2_097_152,
        timeout_seconds=60,
        final_url="https://www.nist.gov/el/ammt/relevant-publications",
        visible_text_sha256=visible_sha,
        visible_text_utf8_bytes=visible_size,
    )
    evidence, specification_sha, candidate_sha, mission_sha = _replay_evidence(
        action_class="experiment_specific_calibration_record_source_discovery",
        witnesses=(witness,),
        bodies=(replayed,),
    )

    round8.verify_discovery_semantic_witness(
        evidence,
        action_class="experiment_specific_calibration_record_source_discovery",
        capability_specification_sha256=specification_sha,
        capability_candidate_sha256=candidate_sha,
        mission_sha256=mission_sha,
        witness=witness,
        expected_candidates_sha256=round8._canonical_sha(reviewed_candidates),
    )


def test_candidate_page_visible_text_drift_is_not_authority_when_pdf_route_and_bytes_match() -> None:
    pdf_url = "https://tsapps.nist.gov/publication/get_pdf.cfm?pub_id=935350"
    reviewed = _candidate_page(footer="historical CMS footer", pdf_url=pdf_url)
    replayed = _candidate_page(footer="new mutable CMS footer text", pdf_url=pdf_url)
    reviewed_text, reviewed_url = candidate_acquisition._parse_candidate_page(
        reviewed,
        "https://www.nist.gov/publications/test",
    )
    replayed_text, replayed_url = candidate_acquisition._parse_candidate_page(
        replayed,
        "https://www.nist.gov/publications/test",
    )
    assert reviewed_text != replayed_text
    assert reviewed_url == replayed_url == pdf_url
    visible_sha, visible_size = _binding(reviewed_text)
    html_witness = round8.SemanticHtmlWitness(
        requested_url="https://www.nist.gov/publications/test",
        allowed_hosts=("www.nist.gov",),
        max_bytes=2_097_152,
        timeout_seconds=90,
        final_url="https://www.nist.gov/publications/test",
        visible_text_sha256=visible_sha,
        visible_text_utf8_bytes=visible_size,
    )
    pdf_body = b"%PDF-static-authority-witness"
    pdf_witness = round8.ExactSourceWitness(
        requested_url=pdf_url,
        allowed_hosts=("tsapps.nist.gov",),
        max_bytes=16_777_216,
        timeout_seconds=90,
        final_url=pdf_url,
        source_sha256=hashlib.sha256(pdf_body).hexdigest(),
        source_size_bytes=len(pdf_body),
    )
    evidence, specification_sha, candidate_sha, mission_sha = _replay_evidence(
        action_class="experiment_specific_calibration_record_candidate_acquisition",
        witnesses=(html_witness, pdf_witness),
        bodies=(replayed, pdf_body),
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


def test_candidate_page_derived_pdf_route_drift_remains_authority_failure() -> None:
    trusted_pdf_url = "https://tsapps.nist.gov/publication/get_pdf.cfm?pub_id=935350"
    drifted_pdf_url = "https://tsapps.nist.gov/publication/get_pdf.cfm?pub_id=935351"
    page = _candidate_page(footer="mutable text", pdf_url=drifted_pdf_url)
    parsed_text, _ = candidate_acquisition._parse_candidate_page(
        page,
        "https://www.nist.gov/publications/test",
    )
    visible_sha, visible_size = _binding(parsed_text)
    html_witness = round8.SemanticHtmlWitness(
        requested_url="https://www.nist.gov/publications/test",
        allowed_hosts=("www.nist.gov",),
        max_bytes=2_097_152,
        timeout_seconds=90,
        final_url="https://www.nist.gov/publications/test",
        visible_text_sha256=visible_sha,
        visible_text_utf8_bytes=visible_size,
    )
    pdf_body = b"%PDF-static-authority-witness"
    pdf_witness = round8.ExactSourceWitness(
        requested_url=trusted_pdf_url,
        allowed_hosts=("tsapps.nist.gov",),
        max_bytes=16_777_216,
        timeout_seconds=90,
        final_url=trusted_pdf_url,
        source_sha256=hashlib.sha256(pdf_body).hexdigest(),
        source_size_bytes=len(pdf_body),
    )
    evidence, specification_sha, candidate_sha, mission_sha = _replay_evidence(
        action_class="experiment_specific_calibration_record_candidate_acquisition",
        witnesses=(html_witness, pdf_witness),
        bodies=(page, pdf_body),
    )

    with pytest.raises(
        round8.AutonomousProductionExactHeadRound8Error,
        match="derived full-text URL drifted",
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
