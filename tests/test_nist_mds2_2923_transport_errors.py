from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest

from materials_data_analyzer.research_loop import nist_mds2_2923_production_acquisition as mds2
from materials_data_analyzer.research_loop.public_data_acquisition import (
    FetchResult,
    PublicAcquisitionError,
    PublicAcquisitionTransportError,
)


def _qualification() -> dict[str, Any]:
    return {
        "qualification_status": "exact_nist_mds2_2923_network_policy_authenticated",
        "mission_sha256": "a" * 64,
        "policy_id": mds2.POLICY_ID,
        "policy_sha256": "b" * 64,
        "action_class": mds2.ACTION_CLASS,
        "candidate_id": mds2.CANDIDATE_ID,
        "product_id": mds2.PRODUCT_ID,
        "metadata_endpoint": mds2.METADATA_ENDPOINT,
        "expected_nerdm_metadata_sha256": mds2.EXPECTED_METADATA_SHA256,
        "expected_files": {
            path: {"path": path, **rule} for path, rule in mds2.EXPECTED_FILES.items()
        },
        "metadata_allowed_hosts": list(mds2.METADATA_ALLOWED_HOSTS),
        "artifact_allowed_hosts": list(mds2.ARTIFACT_ALLOWED_HOSTS),
        "maximum_network_requests": mds2.MAX_NETWORK_REQUESTS,
        "maximum_metadata_bytes": mds2.MAX_METADATA_BYTES,
        "maximum_artifact_bytes": mds2.MAX_ARTIFACT_BYTES,
        "maximum_total_artifact_bytes": mds2.MAX_TOTAL_ARTIFACT_BYTES,
        "timeout_seconds": mds2.TIMEOUT_SECONDS,
        "unrestricted_search_authorized": False,
        "arbitrary_url_fetch_authorized": False,
        "network_access_performed": False,
    }


def _authorization() -> dict[str, Any]:
    return mds2.build_nist_mds2_2923_network_authorization(_qualification())


def test_metadata_transport_failure_is_preserved_as_nist_transport_subtype(
    tmp_path: Path,
) -> None:
    calls = 0

    def transport_failure(*_: object, **__: object) -> FetchResult:
        nonlocal calls
        calls += 1
        raise PublicAcquisitionTransportError("HTTP acquisition failed: 524")

    with pytest.raises(mds2.NistMds22923ProductionTransportError) as caught:
        mds2.execute_authorized_nist_mds2_2923_acquisition(
            authorization=_authorization(),
            output_root=tmp_path / "out",
            fetcher=transport_failure,
        )

    assert calls == 1
    assert isinstance(caught.value, mds2.NistMds22923ProductionAcquisitionError)
    assert isinstance(caught.value.__cause__, PublicAcquisitionTransportError)
    assert "metadata transport failed" in str(caught.value)


def test_metadata_integrity_failure_remains_non_transport_hard_failure(
    tmp_path: Path,
) -> None:
    def integrity_failure(*_: object, **__: object) -> FetchResult:
        raise PublicAcquisitionError("redirect endpoint host is outside allowlist")

    with pytest.raises(mds2.NistMds22923ProductionAcquisitionError) as caught:
        mds2.execute_authorized_nist_mds2_2923_acquisition(
            authorization=_authorization(),
            output_root=tmp_path / "out",
            fetcher=integrity_failure,
        )

    assert not isinstance(caught.value, mds2.NistMds22923ProductionTransportError)
    assert isinstance(caught.value.__cause__, PublicAcquisitionError)
    assert "metadata acquisition integrity failed" in str(caught.value)


def test_artifact_transport_failure_is_preserved_without_retry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    metadata = b"exact-test-metadata"
    metadata_sha = hashlib.sha256(metadata).hexdigest()
    monkeypatch.setattr(mds2, "EXPECTED_METADATA_SHA256", metadata_sha)

    authorization = _authorization()
    fetch_calls = 0
    artifact_calls = 0

    def fetch_metadata(*_: object, **__: object) -> FetchResult:
        nonlocal fetch_calls
        fetch_calls += 1
        return FetchResult(
            body=metadata,
            status_code=200,
            final_url=mds2.METADATA_ENDPOINT,
            content_type="application/json",
        )

    candidates = [
        {
            "artifact_path": path,
            "expected_sha256": rule["sha256"],
            "expected_size_bytes": rule["size_bytes"],
            "metadata_sha256": metadata_sha,
            "allowed_hosts": list(mds2.ARTIFACT_ALLOWED_HOSTS),
        }
        for path, rule in mds2.EXPECTED_FILES.items()
    ]
    monkeypatch.setattr(mds2, "discover_nist_pdr_candidates", lambda **_: candidates)

    def artifact_transport_failure(**_: object) -> dict[str, Any]:
        nonlocal artifact_calls
        artifact_calls += 1
        raise PublicAcquisitionTransportError("HTTP acquisition failed: 524")

    monkeypatch.setattr(mds2, "acquire_public_artifact", artifact_transport_failure)

    with pytest.raises(mds2.NistMds22923ProductionTransportError) as caught:
        mds2.execute_authorized_nist_mds2_2923_acquisition(
            authorization=authorization,
            output_root=tmp_path / "out",
            fetcher=fetch_metadata,
        )

    assert fetch_calls == 1
    assert artifact_calls == 1
    assert isinstance(caught.value.__cause__, PublicAcquisitionTransportError)
    assert "artifact transport failed" in str(caught.value)


def test_artifact_integrity_failure_remains_non_transport_hard_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    metadata = b"exact-test-metadata"
    metadata_sha = hashlib.sha256(metadata).hexdigest()
    monkeypatch.setattr(mds2, "EXPECTED_METADATA_SHA256", metadata_sha)
    authorization = _authorization()

    def fetch_metadata(*_: object, **__: object) -> FetchResult:
        return FetchResult(
            body=metadata,
            status_code=200,
            final_url=mds2.METADATA_ENDPOINT,
            content_type="application/json",
        )

    candidates = [
        {
            "artifact_path": path,
            "expected_sha256": rule["sha256"],
            "expected_size_bytes": rule["size_bytes"],
            "metadata_sha256": metadata_sha,
            "allowed_hosts": list(mds2.ARTIFACT_ALLOWED_HOSTS),
        }
        for path, rule in mds2.EXPECTED_FILES.items()
    ]
    monkeypatch.setattr(mds2, "discover_nist_pdr_candidates", lambda **_: candidates)
    monkeypatch.setattr(
        mds2,
        "acquire_public_artifact",
        lambda **_: (_ for _ in ()).throw(PublicAcquisitionError("checksum mismatch")),
    )

    with pytest.raises(mds2.NistMds22923ProductionAcquisitionError) as caught:
        mds2.execute_authorized_nist_mds2_2923_acquisition(
            authorization=authorization,
            output_root=tmp_path / "out",
            fetcher=fetch_metadata,
        )

    assert not isinstance(caught.value, mds2.NistMds22923ProductionTransportError)
    assert isinstance(caught.value.__cause__, PublicAcquisitionError)
    assert "artifact acquisition failed" in str(caught.value)
