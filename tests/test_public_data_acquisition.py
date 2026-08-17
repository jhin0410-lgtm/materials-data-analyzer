from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop.acquisition_record_binding import (
    authenticate_acquisition_record_binding,
)
from materials_data_analyzer.research_loop.public_data_acquisition import (
    AUTO,
    BLOCKED,
    REVIEW_REQUIRED,
    FetchResult,
    PublicAcquisitionError,
    acquire_public_artifact,
    assess_public_acquisition_candidate,
    plan_public_acquisition_queue,
)


def _candidate(
    artifact: bytes,
    metadata: bytes,
    *,
    access_overrides: dict[str, object] | None = None,
    expected_size_bytes: int | None = None,
) -> dict[str, object]:
    access: dict[str, object] = {
        "publicly_accessible": True,
        "authentication_required": False,
        "interactive_acceptance_required": False,
        "known_automation_prohibited": False,
        "rights_status": "public_repository",
    }
    if access_overrides:
        access.update(access_overrides)
    return {
        "schema_version": "1.0",
        "candidate_id": "example-public-artifact",
        "evidence_role": "source_artifact",
        "source_system": "Example Public Repository",
        "source_version": "1.0",
        "metadata_endpoint": "https://data.example.org/metadata.json",
        "metadata_sha256": hashlib.sha256(metadata).hexdigest(),
        "artifact_path": "raw/example.bin",
        "retrieval_endpoint": "https://data.example.org/example.bin",
        "expected_sha256": hashlib.sha256(artifact).hexdigest(),
        "expected_size_bytes": (
            len(artifact) if expected_size_bytes is None else expected_size_bytes
        ),
        "allowed_hosts": ["data.example.org"],
        "access": access,
        "limitations": ["Scientific validity requires downstream intake."],
    }


def test_public_checksum_bound_candidate_is_auto() -> None:
    metadata = b'{"version":"1.0"}\n'
    artifact = b"physical-data"

    result = assess_public_acquisition_candidate(_candidate(artifact, metadata))

    assert result == {
        "candidate_id": "example-public-artifact",
        "decision": AUTO,
        "reason_codes": [],
    }


@pytest.mark.parametrize(
    ("overrides", "decision", "reason"),
    [
        (
            {"authentication_required": True},
            REVIEW_REQUIRED,
            "authentication_required",
        ),
        (
            {"interactive_acceptance_required": True},
            REVIEW_REQUIRED,
            "interactive_acceptance_required",
        ),
        (
            {"rights_status": "unknown"},
            REVIEW_REQUIRED,
            "rights_unknown",
        ),
        (
            {"known_automation_prohibited": True},
            BLOCKED,
            "automation_explicitly_prohibited",
        ),
        (
            {"rights_status": "restricted"},
            BLOCKED,
            "rights_restricted",
        ),
    ],
)
def test_human_review_is_exception_only(
    overrides: dict[str, object], decision: str, reason: str
) -> None:
    metadata = b'{"version":"1.0"}\n'
    artifact = b"physical-data"

    result = assess_public_acquisition_candidate(
        _candidate(artifact, metadata, access_overrides=overrides)
    )

    assert result["decision"] == decision
    assert reason in result["reason_codes"]


def test_automatic_size_budget_routes_large_file_to_review() -> None:
    metadata = b'{"version":"1.0"}\n'
    artifact = b"0123456789"

    result = assess_public_acquisition_candidate(
        _candidate(artifact, metadata),
        max_auto_bytes=5,
    )

    assert result["decision"] == REVIEW_REQUIRED
    assert result["reason_codes"] == ["automatic_size_budget_exceeded"]


def test_queue_exposes_only_exception_groups() -> None:
    metadata = b'{"version":"1.0"}\n'
    artifact = b"physical-data"
    auto = _candidate(artifact, metadata)
    review = _candidate(
        artifact,
        metadata,
        access_overrides={"authentication_required": True},
    )
    review["candidate_id"] = "review"
    blocked = _candidate(
        artifact,
        metadata,
        access_overrides={"known_automation_prohibited": True},
    )
    blocked["candidate_id"] = "blocked"

    queue = plan_public_acquisition_queue([auto, review, blocked])

    assert queue["candidate_count"] == 3
    assert queue["auto_count"] == 1
    assert queue["review_required_count"] == 1
    assert queue["blocked_count"] == 1
    assert [item["candidate_id"] for item in queue["review_required"]] == ["review"]


def test_acquisition_downloads_verifies_and_self_authenticates(
    tmp_path: Path,
) -> None:
    metadata = b'{"version":"1.0","source":"example"}\n'
    artifact = b"row-level-physical-data"
    candidate = _candidate(artifact, metadata)
    calls: list[tuple[str, int]] = []

    def fake_fetcher(
        url: str,
        *,
        allowed_hosts: list[str],
        max_bytes: int,
        timeout_seconds: float,
        headers: dict[str, str],
    ) -> FetchResult:
        assert allowed_hosts == ["data.example.org"]
        assert timeout_seconds == 60.0
        assert headers["Accept"] == "*/*"
        calls.append((url, max_bytes))
        return FetchResult(
            body=artifact,
            status_code=200,
            final_url=url,
            content_type="application/octet-stream",
        )

    output = tmp_path / "acquired"
    receipt = acquire_public_artifact(
        candidate=candidate,
        metadata_bytes=metadata,
        output_dir=output,
        fetcher=fake_fetcher,
    )

    assert calls == [
        ("https://data.example.org/example.bin", len(artifact) + 1)
    ]
    assert receipt["artifact_sha256"] == hashlib.sha256(artifact).hexdigest()
    assert receipt["recorded_acquisition_provenance_authenticated"] is True
    assert receipt["scientific_status_changed"] is False
    assert (output / "raw" / "example.bin").read_bytes() == artifact
    assert (output / "source_metadata.json").read_bytes() == metadata

    authenticated = authenticate_acquisition_record_binding(
        evidence_bytes=artifact,
        acquisition_manifest_bytes=(output / "acquisition_manifest.json").read_bytes(),
        acquisition_declaration_bytes=(
            output / "acquisition_declaration.json"
        ).read_bytes(),
    )
    assert authenticated["recorded_network_performed"] is True
    assert authenticated["recorded_retrieval_status"] == (
        "downloaded_checksum_verified"
    )

    stored_receipt = json.loads(
        (output / "acquisition_receipt.json").read_text(encoding="utf-8")
    )
    assert stored_receipt == receipt


def test_checksum_mismatch_fails_before_output_promotion(tmp_path: Path) -> None:
    metadata = b'{"version":"1.0"}\n'
    expected = b"expected"
    observed = b"tampered"
    candidate = _candidate(expected, metadata)

    def fake_fetcher(url: str, **_: object) -> FetchResult:
        return FetchResult(observed, 200, url)

    output = tmp_path / "acquired"
    with pytest.raises(PublicAcquisitionError, match="SHA-256"):
        acquire_public_artifact(
            candidate=candidate,
            metadata_bytes=metadata,
            output_dir=output,
            fetcher=fake_fetcher,
        )

    assert not output.exists()


def test_metadata_bytes_are_exactly_bound_before_network_fetch(
    tmp_path: Path,
) -> None:
    metadata = b'{"version":"1.0"}\n'
    artifact = b"expected"
    candidate = _candidate(artifact, metadata)
    called = False

    def fake_fetcher(url: str, **_: object) -> FetchResult:
        nonlocal called
        called = True
        return FetchResult(artifact, 200, url)

    with pytest.raises(PublicAcquisitionError, match="metadata bytes"):
        acquire_public_artifact(
            candidate=candidate,
            metadata_bytes=b'{"version":"different"}\n',
            output_dir=tmp_path / "acquired",
            fetcher=fake_fetcher,
        )

    assert called is False


def test_final_redirect_host_cannot_escape_candidate_allowlist(
    tmp_path: Path,
) -> None:
    metadata = b'{"version":"1.0"}\n'
    artifact = b"expected"
    candidate = _candidate(artifact, metadata)

    def fake_fetcher(url: str, **_: object) -> FetchResult:
        return FetchResult(
            artifact,
            200,
            "https://untrusted.example.net/example.bin",
        )

    with pytest.raises(PublicAcquisitionError, match="outside the exact allowed_hosts"):
        acquire_public_artifact(
            candidate=candidate,
            metadata_bytes=metadata,
            output_dir=tmp_path / "acquired",
            fetcher=fake_fetcher,
        )


def test_non_https_candidate_is_fail_closed() -> None:
    metadata = b'{"version":"1.0"}\n'
    artifact = b"expected"
    candidate = _candidate(artifact, metadata)
    candidate["retrieval_endpoint"] = "http://data.example.org/example.bin"

    with pytest.raises(PublicAcquisitionError, match="must use HTTPS"):
        assess_public_acquisition_candidate(candidate)
