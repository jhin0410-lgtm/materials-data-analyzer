from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop.public_data_acquisition import FetchResult
from materials_data_analyzer.research_loop.zenodo_evidence_acquisition import (
    AUTO,
    REVIEW_REQUIRED,
    ZenodoEvidenceAcquisitionError,
    acquire_zenodo_files,
    normalize_zenodo_record_metadata,
    plan_zenodo_file_acquisition,
    zenodo_record_url,
)


def _metadata(
    *,
    body: bytes,
    license_id: str = "cc-by-4.0",
    access_record: str = "public",
    access_files: str = "public",
    checksum_algorithm: str = "md5",
) -> bytes:
    if checksum_algorithm == "md5":
        digest = hashlib.md5(body, usedforsecurity=False).hexdigest()
    elif checksum_algorithm == "sha256":
        digest = hashlib.sha256(body).hexdigest()
    else:
        digest = "a" * 40
    payload = {
        "id": 20503603,
        "doi": "10.5281/zenodo.20503603",
        "metadata": {
            "title": "IN625 publication dataset",
            "license": {"id": license_id},
        },
        "access": {"record": access_record, "files": access_files},
        "files": {
            "entries": {
                "data.csv": {
                    "key": "data.csv",
                    "size": len(body),
                    "checksum": f"{checksum_algorithm}:{digest}",
                    "links": {
                        "content": (
                            "https://zenodo.org/api/records/20503603/files/data.csv/content"
                        )
                    },
                }
            }
        },
    }
    return json.dumps(payload, sort_keys=True).encode("utf-8")


def test_public_cc_by_record_is_auto_eligible_but_not_scientific_evidence() -> None:
    body = b"x,y\n1,2\n"
    metadata = _metadata(body=body)
    record = normalize_zenodo_record_metadata(
        metadata_bytes=metadata,
        request_url=zenodo_record_url(20503603),
        expected_record_id=20503603,
        expected_doi="10.5281/zenodo.20503603",
    )
    assert record["record_decision"] == AUTO
    assert record["source_license_ids"] == ["cc-by-4.0"]
    assert record["license_ids"] == ["cc-by-4.0"]
    assert record["scientific_status_changed"] is False
    assert record["download_success_is_scientific_validation"] is False
    assert record["files"][0]["source_checksum_algorithm"] == "md5"


def test_legacy_cc_zero_is_canonicalized_without_erasing_source_vocabulary() -> None:
    body = b"x,y\n1,2\n"
    record = normalize_zenodo_record_metadata(
        metadata_bytes=_metadata(body=body, license_id="cc-zero"),
        request_url=zenodo_record_url(20503603),
    )
    assert record["source_license_ids"] == ["cc-zero"]
    assert record["license_ids"] == ["cc0-1.0"]
    assert record["record_decision"] == AUTO
    assert record["record_reason_codes"] == []
    assert record["scientific_status_changed"] is False


def test_noncommercial_license_routes_to_review() -> None:
    body = b"x,y\n1,2\n"
    metadata = _metadata(body=body, license_id="cc-by-nc-4.0")
    record = normalize_zenodo_record_metadata(
        metadata_bytes=metadata,
        request_url=zenodo_record_url(20503603),
    )
    assert record["record_decision"] == REVIEW_REQUIRED
    assert "license_has_use_or_derivative_restriction" in record["record_reason_codes"]


def test_unknown_license_routes_to_review() -> None:
    body = b"x,y\n1,2\n"
    payload = json.loads(_metadata(body=body).decode("utf-8"))
    payload["metadata"].pop("license")
    metadata = json.dumps(payload, sort_keys=True).encode("utf-8")
    record = normalize_zenodo_record_metadata(
        metadata_bytes=metadata,
        request_url=zenodo_record_url(20503603),
    )
    assert record["record_decision"] == REVIEW_REQUIRED
    assert "license_not_explicit_in_record_metadata" in record["record_reason_codes"]


def test_nonpublic_files_are_not_auto_acquired() -> None:
    body = b"x,y\n1,2\n"
    metadata = _metadata(body=body, access_files="restricted")
    record = normalize_zenodo_record_metadata(
        metadata_bytes=metadata,
        request_url=zenodo_record_url(20503603),
    )
    assert record["record_decision"] != AUTO


def test_unsupported_source_checksum_never_becomes_auto() -> None:
    body = b"x,y\n1,2\n"
    metadata = _metadata(body=body, checksum_algorithm="sha1")
    record = normalize_zenodo_record_metadata(
        metadata_bytes=metadata,
        request_url=zenodo_record_url(20503603),
    )
    plan = plan_zenodo_file_acquisition(record, selected_files=["data.csv"])
    assert plan["items"][0]["decision"] == REVIEW_REQUIRED
    assert "source_checksum_algorithm_not_supported" in plan["items"][0]["reason_codes"]


def test_file_and_batch_budgets_route_to_review() -> None:
    body = b"12345678"
    metadata = _metadata(body=body)
    record = normalize_zenodo_record_metadata(
        metadata_bytes=metadata,
        request_url=zenodo_record_url(20503603),
    )
    plan = plan_zenodo_file_acquisition(
        record,
        selected_files=["data.csv"],
        max_file_bytes=4,
        max_total_bytes=100,
    )
    assert plan["items"][0]["decision"] == REVIEW_REQUIRED
    assert "automatic_file_budget_exceeded" in plan["items"][0]["reason_codes"]


def test_acquisition_preserves_source_md5_and_computes_local_sha256(tmp_path: Path) -> None:
    body = b"x,y\n1,2\n"
    metadata = _metadata(body=body, license_id="cc-zero")
    record = normalize_zenodo_record_metadata(
        metadata_bytes=metadata,
        request_url=zenodo_record_url(20503603),
    )

    def fake_fetcher(url: str, **kwargs: object) -> FetchResult:
        del kwargs
        return FetchResult(
            body=body,
            status_code=200,
            final_url=url,
            content_type="text/csv",
        )

    output = tmp_path / "acquisition"
    result = acquire_zenodo_files(
        metadata_bytes=metadata,
        normalized_record=record,
        selected_files=["data.csv"],
        output_dir=output,
        fetcher=fake_fetcher,
    )
    file_record = result["files"][0]
    assert file_record["source_checksum_algorithm"] == "md5"
    assert file_record["source_checksum_digest"] == hashlib.md5(
        body, usedforsecurity=False
    ).hexdigest()
    assert file_record["local_sha256"] == hashlib.sha256(body).hexdigest()
    assert result["source_checksum_preserved_without_algorithm_relabeling"] is True
    assert result["source_license_ids"] == ["cc-zero"]
    assert result["license_ids"] == ["cc0-1.0"]
    assert result["scientific_status_changed"] is False
    assert (output / "files" / "data.csv").read_bytes() == body
    manifest = json.loads(
        (output / "zenodo_acquisition_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["source_license_ids"] == ["cc-zero"]
    assert manifest["license_ids"] == ["cc0-1.0"]
    assert manifest["requires_scientific_intake"] is True


def test_wrong_source_checksum_fails_closed(tmp_path: Path) -> None:
    expected = b"expected"
    actual = b"tampered"
    metadata = _metadata(body=expected)
    record = normalize_zenodo_record_metadata(
        metadata_bytes=metadata,
        request_url=zenodo_record_url(20503603),
    )

    def fake_fetcher(url: str, **kwargs: object) -> FetchResult:
        del kwargs
        return FetchResult(
            body=actual,
            status_code=200,
            final_url=url,
            content_type="text/plain",
        )

    with pytest.raises(ZenodoEvidenceAcquisitionError):
        acquire_zenodo_files(
            metadata_bytes=metadata,
            normalized_record=record,
            selected_files=["data.csv"],
            output_dir=tmp_path / "bad",
            fetcher=fake_fetcher,
        )


def test_record_identity_mismatch_fails_closed() -> None:
    body = b"x"
    metadata = _metadata(body=body)
    with pytest.raises(ZenodoEvidenceAcquisitionError, match="record id"):
        normalize_zenodo_record_metadata(
            metadata_bytes=metadata,
            request_url=zenodo_record_url(20503603),
            expected_record_id=123,
        )


def test_download_url_may_not_leave_zenodo_host() -> None:
    body = b"x"
    payload = json.loads(_metadata(body=body).decode("utf-8"))
    payload["files"]["entries"]["data.csv"]["links"]["content"] = (
        "https://evil.example/data.csv"
    )
    with pytest.raises(ZenodoEvidenceAcquisitionError, match="exact HTTPS host"):
        normalize_zenodo_record_metadata(
            metadata_bytes=json.dumps(payload).encode("utf-8"),
            request_url=zenodo_record_url(20503603),
        )
