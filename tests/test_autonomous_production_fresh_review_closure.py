from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop import (
    autonomous_production_multisource_reviewed_witness as multisource_witness,
)
from materials_data_analyzer.research_loop import (
    autonomous_production_trusted_replay_artifact_binding as trusted_binding,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


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


def _reviewed_multisource_report() -> dict[str, object]:
    witness = json.loads(
        (
            _REPOSITORY_ROOT
            / "configs/research/in625_geometry_condition_multisource_reviewed_witness.v1.json"
        ).read_text(encoding="utf-8")
    )
    registry = json.loads(
        (
            _REPOSITORY_ROOT
            / "configs/research/in625_geometry_condition_source_reconnaissance.v1.json"
        ).read_text(encoding="utf-8")
    )
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
            "application/pdf;charset=UTF-8"
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


def test_multisource_reviewed_witness_accepts_exact_source_and_claim_projection() -> None:
    report = _reviewed_multisource_report()
    multisource_witness.verify_multisource_acquisition_against_reviewed_witness(report)


@pytest.mark.parametrize("mutation", ["source_digest", "claim_match"])
def test_multisource_reviewed_witness_rejects_fabricated_rehashed_semantics(
    mutation: str,
) -> None:
    report = _reviewed_multisource_report()
    sources = report["sources"]
    assert isinstance(sources, list) and isinstance(sources[0], dict)
    if mutation == "source_digest":
        sources[0]["source_sha256"] = "f" * 64
    else:
        claims = sources[0]["claims"]
        assert isinstance(claims, list) and isinstance(claims[0], dict)
        matches = claims[0]["matches"]
        assert isinstance(matches, list) and isinstance(matches[0], dict)
        matches[0]["matched_text_sha256"] = "e" * 64

    with pytest.raises(
        multisource_witness.AutonomousProductionMultisourceReviewedWitnessError,
        match="source/claim authority projection drifted",
    ):
        multisource_witness.verify_multisource_acquisition_against_reviewed_witness(
            report
        )


def test_historical_replay_pypdf_dependency_is_exactly_pinned() -> None:
    pyproject = (_REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '"pypdf==6.18.1"' in pyproject
    assert '"pypdf>=5,<7"' not in pyproject
