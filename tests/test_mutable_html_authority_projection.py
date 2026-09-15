from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

import pytest

from materials_data_analyzer.research_loop import (
    autonomous_production_exact_head_p2_round8 as round8,
)
from materials_data_analyzer.research_loop import (
    autonomous_production_trusted_replay_artifact_binding as trusted_binding,
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


def _rehash_report(value: dict[str, object]) -> dict[str, object]:
    report = copy.deepcopy(value)
    report.pop("report_sha256_without_self_field", None)
    report["report_sha256_without_self_field"] = hashlib.sha256(
        trusted_binding._canonical_bytes(report)
    ).hexdigest()
    return report


def _trusted_candidate_acquisition_fixture() -> dict[str, object]:
    acquisition: dict[str, object] = {
        "schema_version": "1.0",
        "action_class": "experiment_specific_calibration_record_candidate_acquisition",
        "acquisition_status": "derived_nist_calibration_candidate_and_full_text_acquired",
        "candidate_page": {
            "requested_url": "https://www.nist.gov/publications/calibration",
            "final_url": "https://www.nist.gov/publications/calibration",
            "source_sha256": "1" * 64,
            "source_size_bytes": 100,
            "http_content_type": "text/html",
            "visible_text_sha256": "2" * 64,
            "visible_text_utf8_bytes": 80,
            "raw_bytes_persisted": False,
        },
        "full_text": {
            "url_derived_from_candidate_page": True,
            "requested_url": "https://tsapps.nist.gov/publication/get_pdf.cfm?pub_id=935350",
            "final_url": "https://tsapps.nist.gov/publication/get_pdf.cfm?pub_id=935350",
            "source_sha256": "3" * 64,
            "source_size_bytes": 2_264_822,
            "page_count": 7,
            "page_text_sha256": ["4" * 64, "5" * 64],
            "raw_bytes_persisted": False,
            "full_text_persisted": False,
        },
        "claim_receipts": [
            {
                "claim_id": "digital_camera_in_situ_calibration_methodology",
                "matched": True,
                "matched_span_sha256": "6" * 64,
                "page_index": 2,
            }
        ],
        "network_requests_performed": 2,
        "candidate_url_derived_from_discovery": True,
        "full_text_url_derived_from_candidate_page": True,
        "caller_authored_url_used": False,
        "unrestricted_search_performed": False,
        "literature_promoted_to_row_level_measurement_authority": False,
        "acquisition_success_establishes_calibration_bridge": False,
        "global_evidence_unavailability_claimed": False,
        "scientific_status_changed": False,
    }
    return _rehash_report(acquisition)


def _write_candidate_binding_fixture(tmp_path, persisted: dict[str, object]) -> None:
    trusted_acquisition = _trusted_candidate_acquisition_fixture()
    trusted_smoke = _rehash_report(
        {
            "schema_version": "1.0",
            "smoke_status": "derived_candidate_lineage_and_acquisition_verified",
            "acquisition_receipt": trusted_acquisition,
            "network_requests_performed": 2,
            "scientific_status_changed": False,
        }
    )
    suffix = trusted_binding._round6._PROMOTIONS[2][0]
    verification_path = tmp_path / trusted_binding._round6._name(
        "capability-verification", suffix
    )
    verification_path.write_text(
        json.dumps({"real_source_smoke_receipt": trusted_smoke}),
        encoding="utf-8",
    )
    (tmp_path / "nist-ammt-calibration-candidate-acquisition.json").write_text(
        json.dumps(persisted),
        encoding="utf-8",
    )


def test_persisted_candidate_acquisition_allows_only_mutable_page_fingerprint_drift(
    tmp_path,
) -> None:
    persisted = _trusted_candidate_acquisition_fixture()
    candidate_page = persisted["candidate_page"]
    assert isinstance(candidate_page, dict)
    candidate_page["source_sha256"] = "a" * 64
    candidate_page["source_size_bytes"] = 999
    candidate_page["http_content_type"] = "text/html; charset=UTF-8"
    candidate_page["visible_text_sha256"] = "b" * 64
    candidate_page["visible_text_utf8_bytes"] = 777
    persisted = _rehash_report(persisted)
    _write_candidate_binding_fixture(tmp_path, persisted)

    trusted_binding._bind_persisted_candidate_acquisition_to_trusted_replay(tmp_path)


@pytest.mark.parametrize(
    "mutation",
    [
        "static_pdf_sha",
        "page_text_sha",
        "claim_receipt",
        "scientific_authority",
    ],
)
def test_persisted_candidate_acquisition_rejects_rehashed_authority_drift(
    tmp_path,
    mutation: str,
) -> None:
    persisted = _trusted_candidate_acquisition_fixture()
    full_text = persisted["full_text"]
    claims = persisted["claim_receipts"]
    assert isinstance(full_text, dict)
    assert isinstance(claims, list) and isinstance(claims[0], dict)
    if mutation == "static_pdf_sha":
        full_text["source_sha256"] = "f" * 64
    elif mutation == "page_text_sha":
        full_text["page_text_sha256"] = ["e" * 64]
    elif mutation == "claim_receipt":
        claims[0]["matched_span_sha256"] = "d" * 64
    else:
        persisted["literature_promoted_to_row_level_measurement_authority"] = True
    persisted = _rehash_report(persisted)
    _write_candidate_binding_fixture(tmp_path, persisted)

    with pytest.raises(
        trusted_binding.AutonomousProductionTrustedReplayArtifactBindingError,
        match="candidate acquisition authority projection drifted",
    ):
        trusted_binding._bind_persisted_candidate_acquisition_to_trusted_replay(tmp_path)
