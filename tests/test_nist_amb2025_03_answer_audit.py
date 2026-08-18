from __future__ import annotations

import json

import pytest

from materials_data_analyzer.research_loop.nist_amb2025_03_answer_audit import (
    NistAmb202503AnswerAuditError,
    audit_amb2025_03_answer_metadata,
)


DESCRIPTION = (
    "Specimens from one build of laser powder bed fusion (PBF-L) titanium alloy (Ti-6Al-4V) "
    "were split equally into two heat treatment conditions. The first condition will be referred "
    "to as 800HIP. The second condition will be referred to as 800VAC. Approximately 25 specimens "
    "per condition were tested in high-cycle fully reversed 4-point rotating bending fatigue "
    "(RBF, R = -1) according to ISO 1143. All fatigue data (S-N curve) for the 800HIP condition "
    "will also be given as calibration data."
)


def _metadata(*, checksum: object = None, url: str | None = None) -> bytes:
    component = {
        "@type": ["nrdp:DataFile", "nrdp:DownloadableFile"],
        "filepath": "answers_data/fatigue_both_conditions.xlsx",
        "downloadURL": url
        or "https://data.nist.gov/od/ds/ark:/88434/mds2-3734/answers_data/fatigue_both_conditions.xlsx",
        "size": 25018,
    }
    if checksum is not None:
        component["checksum"] = checksum
    return (
        json.dumps(
            {
                "@id": "ark:/88434/mds2-3734",
                "ediid": "ark:/88434/mds2-3734",
                "doi": "doi:10.18434/mds2-3734",
                "accessLevel": "public",
                "version": "1.1.1",
                "description": [DESCRIPTION],
                "components": [component],
            },
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def test_missing_source_checksum_keeps_both_condition_answer_review_gated() -> None:
    report = audit_amb2025_03_answer_metadata(_metadata())
    artifact = report["answer_artifact"]
    assert artifact["public_datafile_discovered"] is True
    assert artifact["size_bytes"] == 25018
    assert artifact["source_checksum"] is None
    assert artifact["source_sha256_bound"] is False
    assert report["automatic_acquisition_eligible"] is False
    assert report["automatic_acquisition_decision"] == "REVIEW_REQUIRED_SOURCE_INTEGRITY"
    assert report["new_blocker"] == "authoritative_answer_datafile_missing_source_sha256_checksum"
    assert report["bounded_stop"] is True
    assert report["model_training_authorized"] is False
    assert report["treatment_effect_claim_authorized"] is False
    assert report["scientific_status_changed"] is False


def test_explicit_source_sha256_would_remove_integrity_blocker_without_promoting_science() -> None:
    report = audit_amb2025_03_answer_metadata(
        _metadata(
            checksum={
                "hash": "a" * 64,
                "algorithm": {"tag": "sha256"},
            }
        )
    )
    assert report["answer_artifact"]["source_sha256_bound"] is True
    assert report["automatic_acquisition_eligible"] is True
    assert report["automatic_acquisition_decision"] == "AUTO"
    assert report["new_blocker"] is None
    assert report["bounded_stop"] is False
    assert report["treatment_effect_claim_authorized"] is False
    assert report["scientific_status_changed"] is False


def test_answer_file_must_remain_on_exact_nist_https() -> None:
    with pytest.raises(NistAmb202503AnswerAuditError, match="outside exact NIST HTTPS"):
        audit_amb2025_03_answer_metadata(
            _metadata(url="https://example.org/fatigue_both_conditions.xlsx")
        )
