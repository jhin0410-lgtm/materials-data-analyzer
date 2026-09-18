from __future__ import annotations

from typing import Any

import pytest

from materials_data_analyzer.research_loop import in625_archive_network_acquisition as archive
from materials_data_analyzer.research_loop.public_data_acquisition import (
    FetchResult,
    PublicAcquisitionError,
    PublicAcquisitionTransportError,
)


def test_archive_shared_transport_failure_maps_to_archive_transport_subtype(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def fail_transport(*_: object, **__: object) -> FetchResult:
        nonlocal calls
        calls += 1
        raise PublicAcquisitionTransportError("HTTP acquisition failed: 504 Gateway Time-out")

    monkeypatch.setattr(archive, "fetch_https_bytes", fail_transport)

    with pytest.raises(archive.In625ArchiveNetworkTransportError) as caught:
        archive.fetch_authorized_zenodo_bytes(
            "https://zenodo.org/api/records/20503603/files/Dataset.zip/content",
            max_bytes=1024,
        )

    assert calls == 1
    assert isinstance(caught.value, archive.In625ArchiveNetworkAcquisitionError)
    assert isinstance(caught.value.__cause__, PublicAcquisitionTransportError)
    assert "archive transport failed" in str(caught.value)


def test_archive_shared_hard_failure_stays_non_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_hard(*_: object, **__: object) -> FetchResult:
        raise PublicAcquisitionError("HTTP acquisition failed: 404 Not Found")

    monkeypatch.setattr(archive, "fetch_https_bytes", fail_hard)

    with pytest.raises(archive.In625ArchiveNetworkAcquisitionError) as caught:
        archive.fetch_authorized_zenodo_bytes(
            "https://zenodo.org/api/records/20503603/files/Dataset.zip/content",
            max_bytes=1024,
        )

    assert not isinstance(caught.value, archive.In625ArchiveNetworkTransportError)
    assert isinstance(caught.value.__cause__, PublicAcquisitionError)
    assert "trust/integrity boundary failed" in str(caught.value)


def test_archive_shared_fetch_result_is_adapted_without_widening(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, Any] = {}

    def success(url: str, **kwargs: object) -> FetchResult:
        observed["url"] = url
        observed.update(kwargs)
        return FetchResult(
            body=b"archive",
            status_code=200,
            final_url=url,
            content_type="application/zip",
        )

    monkeypatch.setattr(archive, "fetch_https_bytes", success)
    result = archive.fetch_authorized_zenodo_bytes(
        "https://zenodo.org/api/records/20503603/files/Dataset.zip/content",
        max_bytes=8,
        timeout_seconds=12.0,
    )

    assert result.body == b"archive"
    assert result.status_code == 200
    assert observed["allowed_hosts"] == ["zenodo.org"]
    assert observed["max_bytes"] == 8
    assert observed["timeout_seconds"] == 12.0


def test_archive_invalid_host_is_rejected_before_shared_fetcher(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def forbidden(*_: object, **__: object) -> FetchResult:
        nonlocal called
        called = True
        raise AssertionError("shared fetcher must not be reached")

    monkeypatch.setattr(archive, "fetch_https_bytes", forbidden)

    with pytest.raises(archive.In625ArchiveNetworkAcquisitionError, match="exact Zenodo host"):
        archive.fetch_authorized_zenodo_bytes(
            "https://example.com/Dataset.zip",
            max_bytes=1024,
        )

    assert called is False
