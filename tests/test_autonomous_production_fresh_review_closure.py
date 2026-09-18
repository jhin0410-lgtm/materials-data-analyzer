from __future__ import annotations

import base64
import copy
import hashlib
import json
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop import (
    autonomous_production_multisource_extension as multisource_extension,
)
from materials_data_analyzer.research_loop import (
    autonomous_production_multisource_reviewed_witness as multisource_witness,
)
from materials_data_analyzer.research_loop import (
    autonomous_production_round3_preflight_scope as bounded_preflight,
)
from materials_data_analyzer.research_loop import (
    autonomous_production_trusted_replay_artifact_binding as trusted_binding,
)
from materials_data_analyzer.research_loop import (
    in625_geometry_condition_source_acquisition as source_acquisition,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_WITNESS_PATH = (
    _REPOSITORY_ROOT
    / "configs/research/in625_geometry_condition_multisource_reviewed_witness.v1.json"
)
_REGISTRY_PATH = (
    _REPOSITORY_ROOT
    / "configs/research/in625_geometry_condition_source_reconnaissance.v1.json"
)


def _candidate_report() -> dict[str, object]:
    return {
        "candidate_page": {
            "requested_url": "https://www.nist.gov/publications/calibration",
            "final_url": "https://www.nist.gov/publications/calibration",
            "source_sha256": "1" * 64,
            "source_size_bytes": 100,
            "http_content_type": "text/html; charset=UTF-8",
            "visible_text_sha256": "2" * 64,
            "visible_text_utf8_bytes": 80,
            "raw_bytes_persisted": False,
        },
        "full_text": {
            "source_sha256": "3" * 64,
            "source_size_bytes": 200,
        },
        "scientific_status_changed": False,
    }


@pytest.mark.parametrize(
    "field",
    trusted_binding._MUTABLE_PAGE_FINGERPRINT_FIELDS,
)
def test_mutable_candidate_page_fingerprint_must_exist_before_projection(
    field: str,
) -> None:
    report = _candidate_report()
    candidate_page = report["candidate_page"]
    assert isinstance(candidate_page, dict)
    candidate_page.pop(field)

    with pytest.raises(
        trusted_binding.AutonomousProductionTrustedReplayArtifactBindingError,
        match="mutable fingerprint is missing",
    ):
        trusted_binding._candidate_acquisition_authority_projection(
            report,
            label="persisted acquisition",
        )


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
def test_mutable_candidate_page_fingerprint_must_be_structurally_valid(
    field: str,
    value: object,
) -> None:
    report = _candidate_report()
    candidate_page = report["candidate_page"]
    assert isinstance(candidate_page, dict)
    candidate_page[field] = value

    with pytest.raises(
        trusted_binding.AutonomousProductionTrustedReplayArtifactBindingError,
        match="mutable fingerprint is malformed",
    ):
        trusted_binding._candidate_acquisition_authority_projection(
            report,
            label="persisted acquisition",
        )


def _load_witness() -> dict[str, object]:
    value = json.loads(_WITNESS_PATH.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _reviewed_multisource_report() -> dict[str, object]:
    witness = _load_witness()
    registry = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
    witness_sources = witness["sources"]
    registry_sources = registry["sources"]
    assert isinstance(witness_sources, list) and isinstance(registry_sources, list)
    assert len(witness_sources) == len(registry_sources) == 8

    sources: list[dict[str, object]] = []
    metadata_keys = (
        "source_id",
        "source_class",
        "authority",
        "title",
        "authors",
        "publication_date",
        "document_date_status",
        "doi",
    )
    for reviewed, registered in zip(witness_sources, registry_sources, strict=True):
        assert isinstance(reviewed, dict) and isinstance(registered, dict)
        source = copy.deepcopy(reviewed)
        for key in metadata_keys:
            source[key] = registered.get(key)
        source["http_content_type"] = (
            "application/pdf"
            if source["media_type"] == "pdf"
            else "text/html; charset=UTF-8"
        )
        sources.append(source)

    return {
        "policy_id": witness["policy_id"],
        "policy_sha256": witness["policy_sha256"],
        "registry_git_blob_sha1": witness["registry_git_blob_sha1"],
        "pdf_extractor": {
            "package": witness["pdf_extractor"]["package"],
            "version": "6.18.1",
            "strict": witness["pdf_extractor"]["strict"],
        },
        "sources": sources,
    }


def test_historical_projection_allows_mutable_html_raw_fingerprint_drift() -> None:
    report = _reviewed_multisource_report()
    witness = _load_witness()
    sources = report["sources"]
    assert isinstance(sources, list)
    html_source = next(
        source
        for source in sources
        if isinstance(source, dict) and source.get("media_type") == "html"
    )
    html_source["source_sha256"] = "f" * 64
    html_source["source_size_bytes"] = 999_999

    multisource_witness._verify_historical_projection(report, witness)


def test_historical_projection_keeps_static_pdf_exact_byte_binding() -> None:
    report = _reviewed_multisource_report()
    witness = _load_witness()
    sources = report["sources"]
    assert isinstance(sources, list)
    pdf_source = next(
        source
        for source in sources
        if isinstance(source, dict) and source.get("media_type") == "pdf"
    )
    pdf_source["source_sha256"] = "f" * 64

    with pytest.raises(
        multisource_witness.AutonomousProductionMultisourceReviewedWitnessError,
        match="source/claim authority projection drifted",
    ):
        multisource_witness._verify_historical_projection(report, witness)


def test_historical_projection_rejects_claim_semantic_drift_on_mutable_html() -> None:
    report = _reviewed_multisource_report()
    witness = _load_witness()
    sources = report["sources"]
    assert isinstance(sources, list)
    html_source = next(
        source
        for source in sources
        if isinstance(source, dict) and source.get("media_type") == "html"
    )
    claims = html_source["claims"]
    assert isinstance(claims, list) and isinstance(claims[0], dict)
    matches = claims[0]["matches"]
    assert isinstance(matches, list) and isinstance(matches[0], dict)
    matches[0]["matched_text_sha256"] = "e" * 64

    with pytest.raises(
        multisource_witness.AutonomousProductionMultisourceReviewedWitnessError,
        match="source/claim authority projection drifted",
    ):
        multisource_witness._verify_historical_projection(report, witness)


def _synthetic_html_replay_fixture() -> tuple[dict[str, object], dict[str, object], bytes]:
    body = (
        b"<html><body>trusted calibration evidence 137.9 W then 179.2 W</body></html>"
    )
    registered: dict[str, object] = {
        "media_type": "html",
        "claims_under_review": [
            {
                "claim_id": "synthetic-calibration-claim",
                "anchor_regex": r"137\.9\s*W.*179\.2\s*W",
                "scope": "synthetic retained-byte replay",
            }
        ],
    }
    pages = source_acquisition._html_pages(body)
    claim = source_acquisition._claim_receipt(
        registered["claims_under_review"][0],  # type: ignore[index,arg-type]
        pages,
        is_pdf=False,
    )
    observed: dict[str, object] = {
        "source_id": "synthetic-html",
        "media_type": "html",
        "http_content_type": "text/html",
        "source_sha256": hashlib.sha256(body).hexdigest(),
        "source_size_bytes": len(body),
        "source_bytes_b64": base64.b64encode(body).decode("ascii"),
        "source_bytes_persisted": True,
        "pdf_page_count": None,
        "claims": [claim],
    }
    return observed, registered, body


def test_retained_html_bytes_replay_recomputes_claim_receipt() -> None:
    observed, registered, body = _synthetic_html_replay_fixture()
    assert (
        multisource_witness._replay_retained_source(
            observed,
            registered,
            label="synthetic source",
        )
        == len(body)
    )


def test_retained_html_bytes_replay_rejects_rehashed_claim_fabrication() -> None:
    observed, registered, _ = _synthetic_html_replay_fixture()
    claims = observed["claims"]
    assert isinstance(claims, list) and isinstance(claims[0], dict)
    matches = claims[0]["matches"]
    assert isinstance(matches, list) and isinstance(matches[0], dict)
    matches[0]["matched_text_sha256"] = "d" * 64

    with pytest.raises(
        multisource_witness.AutonomousProductionMultisourceReviewedWitnessError,
        match="claim receipts do not replay from retained source bytes",
    ):
        multisource_witness._replay_retained_source(
            observed,
            registered,
            label="synthetic source",
        )


def test_retained_html_bytes_replay_rejects_digest_fabrication() -> None:
    observed, registered, _ = _synthetic_html_replay_fixture()
    observed["source_sha256"] = "c" * 64

    with pytest.raises(
        multisource_witness.AutonomousProductionMultisourceReviewedWitnessError,
        match="retained source SHA-256 drifted",
    ):
        multisource_witness._replay_retained_source(
            observed,
            registered,
            label="synthetic source",
        )


def test_cycle4_producer_retains_all_first_fetch_bytes_before_self_hashing() -> None:
    captured = {
        f"https://example.invalid/source-{index}": f"body-{index}".encode()
        for index in range(1, 9)
    }
    sources: list[dict[str, object]] = []
    for url, body in captured.items():
        sources.append(
            {
                "requested_url": url,
                "source_sha256": hashlib.sha256(body).hexdigest(),
                "source_size_bytes": len(body),
                "source_bytes_persisted": False,
            }
        )
    evidence: dict[str, object] = {
        "sources": sources,
        "source_bytes_persisted": False,
        "report_sha256_without_self_field": "0" * 64,
    }

    multisource_extension._attach_retained_source_bytes(evidence, captured)

    assert evidence["source_bytes_persisted"] is True
    assert evidence["retained_source_bytes_count"] == 8
    assert isinstance(evidence["report_sha256_without_self_field"], str)
    for source in sources:
        assert source["source_bytes_persisted"] is True
        encoded = source["source_bytes_b64"]
        assert isinstance(encoded, str)
        assert base64.b64decode(encoded, validate=True) == captured[source["requested_url"]]


def test_historical_replay_pypdf_dependency_is_exactly_pinned() -> None:
    pyproject = (_REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '"pypdf==6.18.1"' in pyproject
    assert '"pypdf>=5,<7"' not in pyproject


def test_untrusted_provenance_json_preflight_is_bounded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(bounded_preflight, "_MAX_PERSISTED_JSON_BYTES", 64)
    oversized = tmp_path / "oversized.json"
    oversized.write_bytes(b'{"padding":"' + b"x" * 80 + b'"}')

    with pytest.raises(
        bounded_preflight.AutonomousProductionExactHeadRound3Error,
        match="exceeds bounded verifier budget",
    ):
        bounded_preflight.verify_round3_duplicate_key_preflight(tmp_path)
