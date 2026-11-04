from __future__ import annotations

from datetime import UTC, datetime, timedelta
from email.message import Message
from email.utils import format_datetime
from io import BytesIO
from urllib.error import HTTPError

import pytest

from materials_data_analyzer.research_loop import (
    in625_geometry_condition_source_acquisition as acquisition,
)

NOW = datetime(2026, 11, 4, 6, 0, tzinfo=UTC)


class FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW


@pytest.mark.parametrize(("retry_after", "expected"), [
    ("120", 120),
    (format_datetime(NOW + timedelta(seconds=180), usegmt=True), 180),
    (format_datetime(NOW - timedelta(seconds=30), usegmt=True), 0),
    (None, None), ("-1", None), ("0.5", None), ("not-a-date", None),
    ("Wed, 04 Nov 2026 06:01:00", None), ("x" * 129, None),
    ("9" * 40, int("9" * 40)),
])
def test_429_defers_without_extra_requests_or_error_body_reads(
    retry_after, expected, monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = Message()
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    class UnreadBody(BytesIO):
        def read(self, *args, **kwargs):
            pytest.fail("a throttling response must not be consumed as evidence")

    body = UnreadBody(b"not publication evidence")
    failure = HTTPError("https://www.nist.gov/test", 429, "Too Many Requests", headers, body)
    calls = []

    class Opener:
        def open(self, request, *, timeout):
            calls.append(request.full_url)
            raise failure

    monkeypatch.setattr(acquisition, "datetime", FrozenDateTime)
    monkeypatch.setattr(acquisition, "build_opener", lambda *_args: Opener())
    with pytest.raises(acquisition.SourceRateLimitedError) as caught:
        acquisition.fetch_exact_source(
            "https://www.nist.gov/test", allowed_hosts=["www.nist.gov"],
            max_bytes=100, timeout_seconds=1,
        )
    assert calls == ["https://www.nist.gov/test"]
    assert caught.value.__cause__ is failure
    assert caught.value.http_status == 429
    assert caught.value.retry_after_seconds == expected
    assert body.closed
    if expected is not None and expected < 1000:
        assert caught.value.retry_not_before_utc == (NOW + timedelta(seconds=expected)).isoformat()
    else:
        assert caught.value.retry_not_before_utc is None
    assert "no automatic retry performed" in str(caught.value)


def test_non_429_transport_failure_remains_operational(monkeypatch: pytest.MonkeyPatch) -> None:
    failure = HTTPError("https://www.nist.gov/test", 503, "Unavailable", Message(), None)

    class Opener:
        def open(self, request, *, timeout):
            raise failure

    monkeypatch.setattr(acquisition, "build_opener", lambda *_args: Opener())
    with pytest.raises(acquisition.GeometryConditionSourceAcquisitionError) as caught:
        acquisition.fetch_exact_source(
            "https://www.nist.gov/test", allowed_hosts=["www.nist.gov"],
            max_bytes=100, timeout_seconds=1,
        )
    assert not isinstance(caught.value, acquisition.SourceRateLimitedError)
    assert caught.value.__cause__ is failure


def test_comparator_metadata_throttling_never_requests_pdf(monkeypatch: pytest.MonkeyPatch) -> None:
    from materials_data_analyzer.research_loop import (
        in625_published_model_comparator as comparator,
    )

    calls = []

    def blocked_fetch(url, **kwargs):
        calls.append(url)
        raise acquisition.SourceRateLimitedError("120")

    monkeypatch.setattr(comparator, "fetch_exact_source", blocked_fetch)
    with pytest.raises(acquisition.SourceRateLimitedError):
        comparator.acquire_kollmannsberger_retrospective_evidence()
    assert calls == [comparator.ARTICLE_METADATA_URL]
