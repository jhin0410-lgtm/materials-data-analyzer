from __future__ import annotations

import socket
import ssl
from collections.abc import Callable
from http.client import BadStatusLine, IncompleteRead, InvalidURL
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
        read_error: BaseException | None = None,
    ) -> None:
        self.status = status
        self._final_url = final_url
        self.headers = {} if headers is None else headers
        self._body = body
        self._offset = 0
        self._read_error = read_error

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def geturl(self) -> str:
        return self._final_url

    def getcode(self) -> int:
        return self.status

    def read(self, size: int = -1) -> bytes:
        if self._read_error is not None:
            raise self._read_error
        if self._offset >= len(self._body):
            return b""
        if size < 0:
            size = len(self._body) - self._offset
        chunk = self._body[self._offset : self._offset + size]
        self._offset += len(chunk)
        return chunk


class _StaticOpener:
    def __init__(self, response: _Response) -> None:
        self._response = response

    def open(self, *_: object, **__: object) -> _Response:
        return self._response


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
        lambda: BadStatusLine("malformed HTTP status line"),
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


def test_incomplete_chunk_read_is_transport_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        acquisition,
        "build_opener",
        lambda *_: _StaticOpener(
            _Response(
                status=200,
                read_error=IncompleteRead(b"partial", 10),
            )
        ),
    )

    with pytest.raises(PublicAcquisitionTransportError) as caught:
        fetch_https_bytes(
            "https://data.example.org/example.bin",
            allowed_hosts=["data.example.org"],
            max_bytes=1024,
        )

    assert isinstance(caught.value.__cause__, IncompleteRead)


@pytest.mark.parametrize("status", [408, 425, 429, 500, 502, 503, 504, 520, 521, 522, 523, 524])
def test_explicit_transient_non_success_status_is_transport_failure(
    monkeypatch: pytest.MonkeyPatch,
    status: int,
) -> None:
    monkeypatch.setattr(
        acquisition,
        "build_opener",
        lambda *_: _StaticOpener(_Response(status=status)),
    )

    with pytest.raises(
        PublicAcquisitionTransportError,
        match=rf"non-success status {status}",
    ):
        fetch_https_bytes(
            "https://data.example.org/example.bin",
            allowed_hosts=["data.example.org"],
            max_bytes=1024,
        )


@pytest.mark.parametrize("status", [401, 403, 404, 410, 451])
def test_explicit_policy_or_resource_status_remains_hard_failure(
    monkeypatch: pytest.MonkeyPatch,
    status: int,
) -> None:
    monkeypatch.setattr(
        acquisition,
        "build_opener",
        lambda *_: _StaticOpener(_Response(status=status)),
    )

    with pytest.raises(PublicAcquisitionError) as caught:
        fetch_https_bytes(
            "https://data.example.org/example.bin",
            allowed_hosts=["data.example.org"],
            max_bytes=1024,
        )

    assert not isinstance(caught.value, PublicAcquisitionTransportError)
    assert f"non-success status {status}" in str(caught.value)


@pytest.mark.parametrize("status", [401, 403, 404, 410, 451])
def test_http_error_policy_or_resource_status_remains_hard_failure(
    monkeypatch: pytest.MonkeyPatch,
    status: int,
) -> None:
    error = HTTPError(
        "https://data.example.org/example.bin",
        status,
        "policy/resource response",
        hdrs=None,
        fp=None,
    )
    monkeypatch.setattr(
        acquisition,
        "build_opener",
        lambda *_: _FailingOpener(error),
    )

    with pytest.raises(PublicAcquisitionError) as caught:
        fetch_https_bytes(
            "https://data.example.org/example.bin",
            allowed_hosts=["data.example.org"],
            max_bytes=1024,
        )

    assert not isinstance(caught.value, PublicAcquisitionTransportError)
    assert isinstance(caught.value.__cause__, HTTPError)
    assert f"HTTP acquisition failed: {status}" in str(caught.value)


@pytest.mark.parametrize("status", [403, 407, 418])
def test_proxy_tunnel_policy_or_nontransient_status_remains_hard_failure(
    monkeypatch: pytest.MonkeyPatch,
    status: int,
) -> None:
    error = URLError(OSError(f"Tunnel connection failed: {status} proxy response"))
    monkeypatch.setattr(
        acquisition,
        "build_opener",
        lambda *_: _FailingOpener(error),
    )

    with pytest.raises(PublicAcquisitionError) as caught:
        fetch_https_bytes(
            "https://data.example.org/example.bin",
            allowed_hosts=["data.example.org"],
            max_bytes=1024,
        )

    assert not isinstance(caught.value, PublicAcquisitionTransportError)
    assert isinstance(caught.value.__cause__, URLError)
    assert f"proxy tunnel status {status}" in str(caught.value)


def test_proxy_tunnel_transient_status_uses_transport_subtype(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    error = URLError(OSError("Tunnel connection failed: 503 Service Unavailable"))
    monkeypatch.setattr(
        acquisition,
        "build_opener",
        lambda *_: _FailingOpener(error),
    )

    with pytest.raises(PublicAcquisitionTransportError, match="proxy tunnel status 503"):
        fetch_https_bytes(
            "https://data.example.org/example.bin",
            allowed_hosts=["data.example.org"],
            max_bytes=1024,
        )


def test_invalid_url_remains_hard_integrity_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    error = InvalidURL("URL can't contain control characters")
    monkeypatch.setattr(
        acquisition,
        "build_opener",
        lambda *_: _FailingOpener(error),
    )

    with pytest.raises(PublicAcquisitionError) as caught:
        fetch_https_bytes(
            "https://data.example.org/example.bin",
            allowed_hosts=["data.example.org"],
            max_bytes=1024,
        )

    assert not isinstance(caught.value, PublicAcquisitionTransportError)
    assert isinstance(caught.value.__cause__, InvalidURL)


def test_tls_certificate_verification_failure_remains_hard_trust_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    certificate_error = ssl.SSLCertVerificationError(1, "certificate verify failed")
    error = URLError(certificate_error)
    monkeypatch.setattr(
        acquisition,
        "build_opener",
        lambda *_: _FailingOpener(error),
    )

    with pytest.raises(PublicAcquisitionError) as caught:
        fetch_https_bytes(
            "https://data.example.org/example.bin",
            allowed_hosts=["data.example.org"],
            max_bytes=1024,
        )

    assert not isinstance(caught.value, PublicAcquisitionTransportError)
    assert isinstance(caught.value.__cause__, URLError)
    assert "TLS/trust failure" in str(caught.value)


@pytest.mark.parametrize(
    "reason",
    [
        "TLSV13_ALERT_CERTIFICATE_REQUIRED",
        "TLSV1_ALERT_ACCESS_DENIED",
    ],
)
def test_tls_authentication_or_policy_alert_remains_hard_failure(
    monkeypatch: pytest.MonkeyPatch,
    reason: str,
) -> None:
    error = URLError(ssl.SSLError(1, reason))
    monkeypatch.setattr(
        acquisition,
        "build_opener",
        lambda *_: _FailingOpener(error),
    )

    with pytest.raises(PublicAcquisitionError) as caught:
        fetch_https_bytes(
            "https://data.example.org/example.bin",
            allowed_hosts=["data.example.org"],
            max_bytes=1024,
        )

    assert not isinstance(caught.value, PublicAcquisitionTransportError)
    assert isinstance(caught.value.__cause__, URLError)
    assert "TLS/trust failure" in str(caught.value)


def test_temporary_dns_resolution_failure_uses_transport_subtype(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    error = URLError(socket.gaierror(socket.EAI_AGAIN, "temporary failure in name resolution"))
    monkeypatch.setattr(
        acquisition,
        "build_opener",
        lambda *_: _FailingOpener(error),
    )

    with pytest.raises(PublicAcquisitionTransportError, match="temporary DNS resolution failure"):
        fetch_https_bytes(
            "https://data.example.org/example.bin",
            allowed_hosts=["data.example.org"],
            max_bytes=1024,
        )


def test_permanent_dns_resolution_failure_remains_hard_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    error = URLError(socket.gaierror(socket.EAI_NONAME, "name or service not known"))
    monkeypatch.setattr(
        acquisition,
        "build_opener",
        lambda *_: _FailingOpener(error),
    )

    with pytest.raises(PublicAcquisitionError) as caught:
        fetch_https_bytes(
            "https://data.example.org/example.bin",
            allowed_hosts=["data.example.org"],
            max_bytes=1024,
        )

    assert not isinstance(caught.value, PublicAcquisitionTransportError)
    assert isinstance(caught.value.__cause__, URLError)
    assert "non-transient DNS resolution failure" in str(caught.value)


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
