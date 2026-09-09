from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

import pytest

from materials_data_analyzer.research_loop import capability_smoke_replay_evidence as replay
from materials_data_analyzer.research_loop.in625_geometry_condition_source_acquisition import (
    FetchResult,
)


def _canonical_sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _packet() -> tuple[dict[str, Any], list[str]]:
    live_calls: list[str] = []

    def delegate(
        url: str,
        *,
        allowed_hosts: tuple[str, ...],
        max_bytes: int,
        timeout_seconds: int,
    ) -> FetchResult:
        live_calls.append(url)
        body = ("exact retained bytes for " + url).encode("utf-8")
        assert len(body) <= max_bytes
        assert timeout_seconds == 17
        return FetchResult(
            body=body,
            final_url=url,
            status_code=200,
            content_type="application/octet-stream",
        )

    recorder = replay.RecordingFetcher(delegate)
    recorder(
        "https://example.test/one",
        allowed_hosts=("example.test",),
        max_bytes=4096,
        timeout_seconds=17,
    )
    recorder(
        "https://example.test/two",
        allowed_hosts=("example.test",),
        max_bytes=8192,
        timeout_seconds=17,
    )
    packet = replay.build_smoke_replay_evidence(
        action_class="bounded_test_acquisition",
        capability_specification_sha256="a" * 64,
        capability_candidate_sha256="b" * 64,
        mission_sha256="c" * 64,
        verification_context={
            "metadata": b"\x00\x01exact-context-bytes\xff",
            "nested": {"value": 7},
        },
        fetch_records=recorder.records,
    )
    return packet, live_calls


def test_retained_smoke_bytes_replay_without_calling_live_delegate() -> None:
    packet, live_calls = _packet()
    assert len(live_calls) == 2

    fetcher, context = replay.authenticate_smoke_replay_evidence(
        packet,
        action_class="bounded_test_acquisition",
        capability_specification_sha256="a" * 64,
        capability_candidate_sha256="b" * 64,
        mission_sha256="c" * 64,
    )
    assert context == {
        "metadata": b"\x00\x01exact-context-bytes\xff",
        "nested": {"value": 7},
    }
    first = fetcher(
        "https://example.test/one",
        allowed_hosts=("example.test",),
        max_bytes=4096,
        timeout_seconds=17,
    )
    second = fetcher(
        "https://example.test/two",
        allowed_hosts=("example.test",),
        max_bytes=8192,
        timeout_seconds=17,
    )
    fetcher.assert_consumed()
    assert first.body == b"exact retained bytes for https://example.test/one"
    assert second.body == b"exact retained bytes for https://example.test/two"
    assert len(live_calls) == 2


def test_retained_smoke_packet_corruption_fails_closed() -> None:
    packet, _ = _packet()
    corrupted = copy.deepcopy(packet)
    corrupted["fetch_records"][0]["response"]["body"]["sha256"] = "f" * 64

    with pytest.raises(
        replay.CapabilitySmokeReplayEvidenceError,
        match="smoke replay evidence self binding is invalid",
    ):
        replay.authenticate_smoke_replay_evidence(
            corrupted,
            action_class="bounded_test_acquisition",
            capability_specification_sha256="a" * 64,
            capability_candidate_sha256="b" * 64,
            mission_sha256="c" * 64,
        )


def test_self_consistently_rehashed_request_substitution_cannot_change_replay_contract() -> None:
    packet, _ = _packet()
    forged = copy.deepcopy(packet)
    first = forged["fetch_records"][0]
    first["request"]["url"] = "https://example.test/substituted"
    first.pop("fetch_record_sha256_without_self_field")
    first["fetch_record_sha256_without_self_field"] = _canonical_sha(first)
    forged.pop("smoke_replay_evidence_sha256_without_self_field")
    forged["smoke_replay_evidence_sha256_without_self_field"] = _canonical_sha(forged)

    fetcher, _context = replay.authenticate_smoke_replay_evidence(
        forged,
        action_class="bounded_test_acquisition",
        capability_specification_sha256="a" * 64,
        capability_candidate_sha256="b" * 64,
        mission_sha256="c" * 64,
    )
    with pytest.raises(
        replay.CapabilitySmokeReplayEvidenceError,
        match="historical smoke replay URL drifted",
    ):
        fetcher(
            "https://example.test/one",
            allowed_hosts=("example.test",),
            max_bytes=4096,
            timeout_seconds=17,
        )


def test_extra_or_unconsumed_replay_requests_fail_closed() -> None:
    packet, _ = _packet()
    fetcher, _context = replay.authenticate_smoke_replay_evidence(
        packet,
        action_class="bounded_test_acquisition",
        capability_specification_sha256="a" * 64,
        capability_candidate_sha256="b" * 64,
        mission_sha256="c" * 64,
    )
    fetcher(
        "https://example.test/one",
        allowed_hosts=("example.test",),
        max_bytes=4096,
        timeout_seconds=17,
    )
    with pytest.raises(
        replay.CapabilitySmokeReplayEvidenceError,
        match="left retained fetch records unconsumed",
    ):
        fetcher.assert_consumed()

    fetcher, _context = replay.authenticate_smoke_replay_evidence(
        packet,
        action_class="bounded_test_acquisition",
        capability_specification_sha256="a" * 64,
        capability_candidate_sha256="b" * 64,
        mission_sha256="c" * 64,
    )
    fetcher(
        "https://example.test/one",
        allowed_hosts=("example.test",),
        max_bytes=4096,
        timeout_seconds=17,
    )
    fetcher(
        "https://example.test/two",
        allowed_hosts=("example.test",),
        max_bytes=8192,
        timeout_seconds=17,
    )
    fetcher.assert_consumed()
    with pytest.raises(
        replay.CapabilitySmokeReplayEvidenceError,
        match="historical smoke replay requested extra fetch",
    ):
        fetcher(
            "https://example.test/three",
            allowed_hosts=("example.test",),
            max_bytes=1,
            timeout_seconds=17,
        )
