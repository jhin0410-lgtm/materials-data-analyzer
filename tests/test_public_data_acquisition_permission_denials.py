from __future__ import annotations

import errno
from urllib.error import URLError

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


def _assert_hard_permission_failure(
    monkeypatch: pytest.MonkeyPatch,
    exc: BaseException,
) -> None:
    monkeypatch.setattr(
        acquisition,
        "build_opener",
        lambda *_: _FailingOpener(exc),
    )

    with pytest.raises(PublicAcquisitionError) as caught:
        fetch_https_bytes(
            "https://data.example.org/example.bin",
            allowed_hosts=["data.example.org"],
            max_bytes=1024,
        )

    assert not isinstance(caught.value, PublicAcquisitionTransportError)
    assert "permission/access-control failure" in str(caught.value)


@pytest.mark.parametrize("error_number", [errno.EACCES, errno.EPERM])
def test_wrapped_socket_permission_denial_remains_hard_failure(
    monkeypatch: pytest.MonkeyPatch,
    error_number: int,
) -> None:
    _assert_hard_permission_failure(
        monkeypatch,
        URLError(PermissionError(error_number, "socket operation not permitted")),
    )


@pytest.mark.parametrize("error_number", [errno.EACCES, errno.EPERM])
def test_direct_socket_permission_denial_remains_hard_failure(
    monkeypatch: pytest.MonkeyPatch,
    error_number: int,
) -> None:
    _assert_hard_permission_failure(
        monkeypatch,
        PermissionError(error_number, "socket operation not permitted"),
    )
