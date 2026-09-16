from __future__ import annotations

import base64
import copy
import hashlib
import zlib
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop import (
    autonomous_production_fresh_review_round9 as round9,
)
from materials_data_analyzer.research_loop import capability_smoke_replay_evidence as smoke

ROOT = Path(__file__).resolve().parents[1]


def _discovery_report() -> dict[str, object]:
    return {
        "source_index": {
            "source_sha256": "a" * 64,
            "source_size_bytes": 123,
            "http_content_type": "text/html; charset=UTF-8",
            "visible_text_sha256": "b" * 64,
            "visible_text_utf8_bytes": 100,
        }
    }


@pytest.mark.parametrize("field", round9._DISCOVERY_FINGERPRINT_FIELDS)
def test_discovery_mutable_fingerprint_must_exist_before_projection(field: str) -> None:
    report = _discovery_report()
    source = report["source_index"]
    assert isinstance(source, dict)
    source.pop(field)
    with pytest.raises(
        round9.AutonomousProductionFreshReviewRound9Error,
        match="mutable fingerprint is missing",
    ):
        round9._validate_discovery_fingerprints(report, label="test discovery")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_sha256", "not-a-sha"),
        ("visible_text_sha256", "A" * 64),
        ("source_size_bytes", 1.0),
        ("visible_text_utf8_bytes", False),
        ("http_content_type", ""),
    ],
)
def test_discovery_mutable_fingerprint_must_be_typed(field: str, value: object) -> None:
    report = _discovery_report()
    source = report["source_index"]
    assert isinstance(source, dict)
    source[field] = value
    with pytest.raises(
        round9.AutonomousProductionFreshReviewRound9Error,
        match="mutable fingerprint is malformed",
    ):
        round9._validate_discovery_fingerprints(report, label="test discovery")


def _multisource_report() -> dict[str, object]:
    return {
        "pdf_extractor": {"package": "pypdf", "version": "6.18.1", "strict": False},
        "network_requests_performed": 8,
        "network_request_budget": 8,
        "source_bytes_persisted": True,
        "retained_source_bytes_count": 8,
        "unrestricted_network_search_performed": False,
        "caller_authored_url_used": False,
        "arbitrary_url_fetch_performed": False,
        "network_failure_interpreted_as_negative_scientific_evidence": False,
    }


def test_multisource_report_requires_exact_pinned_pdf_extractor_version() -> None:
    report = _multisource_report()
    extractor = report["pdf_extractor"]
    assert isinstance(extractor, dict)
    extractor["version"] = "6.18.0"
    with pytest.raises(
        round9.AutonomousProductionFreshReviewRound9Error,
        match="PDF extractor environment drifted",
    ):
        round9._validate_multisource_report_boundaries(report)


@pytest.mark.parametrize("field", round9._NETWORK_FALSE_FIELDS)
def test_multisource_report_rejects_rehashed_network_history_promotion(field: str) -> None:
    report = _multisource_report()
    report[field] = True
    with pytest.raises(
        round9.AutonomousProductionFreshReviewRound9Error,
        match="widened network/scientific execution boundary",
    ):
        round9._validate_multisource_report_boundaries(report)


def test_qualification_equality_is_json_type_sensitive(tmp_path: Path) -> None:
    persisted = {"network_access_performed": 0, "max_requests": 1}
    expected = {"network_access_performed": False, "max_requests": 1}
    (tmp_path / "qualification.json").write_text(
        '{"max_requests":1,"network_access_performed":0}', encoding="utf-8"
    )
    with pytest.raises(
        round9.AutonomousProductionFreshReviewRound9Error,
        match="trusted checkout reconstruction",
    ):
        round9._require_exact_qualification(
            root=tmp_path,
            filename="qualification.json",
            expected=expected,
            label="test qualification",
        )
    assert persisted != expected or type(persisted["network_access_performed"]) is not type(
        expected["network_access_performed"]
    )


def _encoded_bytes(raw: bytes, *, declared_size: int | None = None) -> dict[str, object]:
    compressed = zlib.compress(raw, level=9)
    return {
        smoke._BYTES_MARKER: base64.b64encode(compressed).decode("ascii"),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size_bytes": len(raw) if declared_size is None else declared_size,
        "compression": "zlib-9",
    }


def test_context_decoder_rejects_declared_size_over_contract_before_decompression() -> None:
    value = _encoded_bytes(
        b"x",
        declared_size=smoke._MAX_VERIFICATION_CONTEXT_TOTAL_BYTES + 1,
    )
    with pytest.raises(
        smoke.CapabilitySmokeReplayEvidenceError,
        match="per-value verification-context byte budget",
    ):
        smoke.decode_context({"nerdm_metadata_bytes": value})


def test_context_decoder_rejects_absurd_size_without_overflow() -> None:
    value = _encoded_bytes(b"x", declared_size=2**63)
    with pytest.raises(smoke.CapabilitySmokeReplayEvidenceError):
        smoke.decode_context({"nerdm_metadata_bytes": value})


def test_context_decoder_enforces_cumulative_budget_before_second_decompression(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(smoke, "_MAX_VERIFICATION_CONTEXT_VALUE_BYTES", 8)
    monkeypatch.setattr(smoke, "_MAX_VERIFICATION_CONTEXT_TOTAL_BYTES", 8)
    value = {
        "first": _encoded_bytes(b"12345"),
        "second": _encoded_bytes(b"6789"),
    }
    with pytest.raises(
        smoke.CapabilitySmokeReplayEvidenceError,
        match="cumulative verification-context byte budget",
    ):
        smoke.decode_context(value)


def test_context_decoder_valid_round_trip() -> None:
    raw = b"trusted-metadata"
    encoded = smoke.encode_context({"nerdm_metadata_bytes": raw})
    assert smoke.decode_context(encoded) == {"nerdm_metadata_bytes": raw}


def test_live_workflow_tracks_zenodo_normalizer_and_round9_regressions() -> None:
    workflow = (ROOT / ".github/workflows/autonomous-production-live.yml").read_text(
        encoding="utf-8"
    )
    dependency = (
        '"src/materials_data_analyzer/research_loop/zenodo_evidence_acquisition.py"'
    )
    assert workflow.count(dependency) == 2
    assert "tests/test_autonomous_production_fresh_review_round9.py" in workflow
