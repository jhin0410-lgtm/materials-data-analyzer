from __future__ import annotations

from collections.abc import Callable
from urllib.error import HTTPError, URLError

import pytest

import materials_data_analyzer.research_loop.public_data_acquisition as acquisition
from materials_data_analyzer.research_loop.public_data_acquisition import (
    PublicAcquisitionError,
    PublicAcquisitionTransportError,
    fetch_https_bytes,
)


class _FailingOpener:
    def __init__(self, exc: BaseException) -> None:
        self._exc = exc

    def open(self, *_: object, **__: object) -> object:
        raise self._exc


class _Response:
    def __init__(
        self,
        *,
        status: int,
        final_url: str = "https://data.example.org/example.bin",
        headers: dict[str, str] | None = None,
        body: bytes = b"",
    ) -> None:
        self.status = status
        self._final_url = final_url
        self.headers = {} if headers is None else headers
        self._body = body
        self._offset = 0

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def geturl(self) -> str:
        return self._final_url

    def getcode(self) -> int:
        return self.status

    def read(self, size: int = -1) -> bytes:
        if self._offset >= len(self._body):
            return b""
        if size < 0:
            size = len(self._body) - self._offset
        chunk = self._body[self._offset : self._offset + size]
        self._offset += len(chunk)
        return chunk


@pytest.mark.parametrize(
    "factory",
    [
        lambda: HTTPError(
            "https://data.example.org/example.bin",
            524,
            "A timeout occurred",
            hdrs=None,
            fp=None,
        ),
        lambda: URLError("temporary DNS failure"),
        lambda: TimeoutError("socket timed out"),
        lambda: OSError("connection reset"),
    ],
)
def test_network_delivery_failures_use_transport_subtype(
    monkeypatch: pytest.MonkeyPatch,
    factory: Callable[[], BaseException],
) -> None:
    monkeypatch.setattr(
        acquisition,
        "build_opener",
        lambda *_: _FailingOpener(factory()),
    )

    with pytest.raises(PublicAcquisitionTransportError) as caught:
        fetch_https_bytes(
            "https://data.example.org/example.bin",
            allowed_hosts=["data.example.org"],
            max_bytes=1024,
        )

    assert isinstance(caught.value, PublicAcquisitionError)
    assert "HTTP acquisition failed" in str(caught.value)


def test_explicit_non_success_status_is_transport_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        acquisition,
        "build_opener",
        lambda *_: _StaticOpener(_Response(status=503)),
    )

    with pytest.raises(
        PublicAcquisitionTransportError,
        match="non-success status 503",
    ):
        fetch_https_bytes(
            "https://data.example.org/example.bin",
            allowed_hosts=["data.example.org"],
            max_bytes=1024,
        )


def test_untrusted_endpoint_remains_hard_integrity_failure() -> None:
    with pytest.raises(PublicAcquisitionError) as caught:
        fetch_https_bytes(
            "https://untrusted.example.net/example.bin",
            allowed_hosts=["data.example.org"],
            max_bytes=1024,
        )

    assert not isinstance(caught.value, PublicAcquisitionTransportError)
    assert "outside the exact allowed_hosts set" in str(caught.value)


def test_byte_ceiling_violation_remains_hard_integrity_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        acquisition,
        "build_opener",
        lambda *_: _StaticOpener(
            _Response(
                status=200,
                headers={"Content-Length": "2048"},
            )
        ),
    )

    with pytest.raises(PublicAcquisitionError) as caught:
        fetch_https_bytes(
            "https://data.example.org/example.bin",
            allowed_hosts=["data.example.org"],
            max_bytes=1024,
        )

    assert not isinstance(caught.value, PublicAcquisitionTransportError)
    assert "byte ceiling" in str(caught.value)


class _StaticOpener:
    def __init__(self, response: _Response) -> None:
        self._response = response

    def open(self, *_: object, **__: object) -> _Response:
        return self._response
