"""Retain and replay exact capability-verifier smoke inputs without network access.

A self-hashed verification receipt is not sufficient historical authority when its real-source
smoke is rerun against mutable remote state.  This module records the exact bounded fetch request
contract and response bytes used by the original verifier, then provides a strict single-use
fetcher that can replay only those retained calls.  The retained packet is provenance evidence;
it does not grant new network, execution, or scientific authority.
"""
from __future__ import annotations

import base64
import hashlib
import json
import zlib
from collections.abc import Mapping, Sequence
from typing import Any, Callable

from .in625_geometry_condition_source_acquisition import FetchResult

SMOKE_REPLAY_EVIDENCE_SCHEMA_VERSION = "1.0"
_BYTES_MARKER = "__mda_exact_bytes_zlib_base64__"


class CapabilitySmokeReplayEvidenceError(ValueError):
    """Raised when retained smoke evidence is incomplete, substituted, or over-consumed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CapabilitySmokeReplayEvidenceError(message)


def _canonical_sha(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _encode_bytes(raw: bytes) -> dict[str, Any]:
    compressed = zlib.compress(raw, level=9)
    return {
        _BYTES_MARKER: base64.b64encode(compressed).decode("ascii"),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size_bytes": len(raw),
        "compression": "zlib-9",
    }


def _decode_bytes(value: Mapping[str, Any], *, label: str) -> bytes:
    encoded = value.get(_BYTES_MARKER)
    _require(isinstance(encoded, str) and encoded, f"{label} encoded bytes are missing")
    _require(value.get("compression") == "zlib-9", f"{label} compression drifted")
    try:
        compressed = base64.b64decode(encoded.encode("ascii"), validate=True)
        raw = zlib.decompress(compressed)
    except (ValueError, zlib.error) as exc:
        raise CapabilitySmokeReplayEvidenceError(f"{label} bytes could not be decoded") from exc
    _require(value.get("size_bytes") == len(raw), f"{label} byte size drifted")
    _require(
        value.get("sha256") == hashlib.sha256(raw).hexdigest(),
        f"{label} byte SHA-256 drifted",
    )
    return raw


def encode_context(value: object) -> object:
    """Convert bytes-containing verifier context into deterministic JSON-safe evidence."""
    if isinstance(value, bytes):
        return _encode_bytes(value)
    if isinstance(value, Mapping):
        return {str(key): encode_context(item) for key, item in value.items()}
    if isinstance(value, list):
        return [encode_context(item) for item in value]
    if isinstance(value, tuple):
        return [encode_context(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise CapabilitySmokeReplayEvidenceError(
        f"unsupported verifier-context value type: {type(value).__name__}"
    )


def decode_context(value: object, *, label: str = "verification context") -> object:
    """Restore the exact verifier context retained by :func:`encode_context`."""
    if isinstance(value, Mapping):
        if _BYTES_MARKER in value:
            return _decode_bytes(value, label=label)
        return {
            str(key): decode_context(item, label=f"{label}.{key}")
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            decode_context(item, label=f"{label}[{index}]")
            for index, item in enumerate(value)
        ]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise CapabilitySmokeReplayEvidenceError(f"{label} contains unsupported JSON value")


class RecordingFetcher:
    """Proxy one audited fetcher while retaining exact request/response replay evidence."""

    def __init__(self, delegate: Callable[..., FetchResult]) -> None:
        self._delegate = delegate
        self.records: list[dict[str, Any]] = []

    def __call__(
        self,
        url: str,
        *,
        allowed_hosts: Sequence[str],
        max_bytes: int,
        timeout_seconds: int,
    ) -> FetchResult:
        result = self._delegate(
            url,
            allowed_hosts=allowed_hosts,
            max_bytes=max_bytes,
            timeout_seconds=timeout_seconds,
        )
        _require(isinstance(result, FetchResult), "recording fetcher delegate returned invalid result")
        record: dict[str, Any] = {
            "request": {
                "url": url,
                "allowed_hosts": list(allowed_hosts),
                "max_bytes": max_bytes,
                "timeout_seconds": timeout_seconds,
            },
            "response": {
                "body": _encode_bytes(result.body),
                "final_url": result.final_url,
                "status_code": result.status_code,
                "content_type": result.content_type,
            },
        }
        record["fetch_record_sha256_without_self_field"] = _canonical_sha(record)
        self.records.append(record)
        return result


class ReplayFetcher:
    """Strictly consume retained fetch records without performing any network access."""

    def __init__(self, records: Sequence[Mapping[str, Any]]) -> None:
        self._records = [dict(record) for record in records]
        self._index = 0

    def __call__(
        self,
        url: str,
        *,
        allowed_hosts: Sequence[str],
        max_bytes: int,
        timeout_seconds: int,
    ) -> FetchResult:
        _require(self._index < len(self._records), "historical smoke replay requested extra fetch")
        record = self._records[self._index]
        self._index += 1
        supplied_sha = record.get("fetch_record_sha256_without_self_field")
        unsigned = dict(record)
        unsigned.pop("fetch_record_sha256_without_self_field", None)
        _require(
            isinstance(supplied_sha, str) and supplied_sha == _canonical_sha(unsigned),
            "retained fetch-record self binding is invalid",
        )
        request = record.get("request")
        response = record.get("response")
        _require(isinstance(request, Mapping), "retained fetch request is missing")
        _require(isinstance(response, Mapping), "retained fetch response is missing")
        _require(request.get("url") == url, "historical smoke replay URL drifted")
        _require(
            request.get("allowed_hosts") == list(allowed_hosts),
            "historical smoke replay host authority drifted",
        )
        _require(request.get("max_bytes") == max_bytes, "historical smoke replay byte budget drifted")
        _require(
            request.get("timeout_seconds") == timeout_seconds,
            "historical smoke replay timeout contract drifted",
        )
        body_record = response.get("body")
        _require(isinstance(body_record, Mapping), "retained fetch response bytes are missing")
        body = _decode_bytes(body_record, label=f"retained fetch {self._index} response")
        final_url = response.get("final_url")
        status_code = response.get("status_code")
        content_type = response.get("content_type")
        _require(isinstance(final_url, str) and final_url, "retained final URL is invalid")
        _require(isinstance(status_code, int) and not isinstance(status_code, bool), "retained status code is invalid")
        _require(content_type is None or isinstance(content_type, str), "retained content type is invalid")
        return FetchResult(
            body=body,
            final_url=final_url,
            status_code=status_code,
            content_type=content_type,
        )

    def assert_consumed(self) -> None:
        _require(
            self._index == len(self._records),
            "historical smoke replay left retained fetch records unconsumed",
        )


def build_smoke_replay_evidence(
    *,
    action_class: str,
    capability_specification_sha256: str,
    capability_candidate_sha256: str,
    mission_sha256: str,
    verification_context: Mapping[str, Any] | None,
    fetch_records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build the self-bound retained packet produced by the original live verifier."""
    _require(bool(action_class), "smoke replay action class is missing")
    for value, label in (
        (capability_specification_sha256, "specification SHA"),
        (capability_candidate_sha256, "candidate SHA"),
        (mission_sha256, "mission SHA"),
    ):
        _require(isinstance(value, str) and len(value) == 64, f"{label} is invalid")
    _require(bool(fetch_records), "live network smoke retained no fetch records")
    packet: dict[str, Any] = {
        "schema_version": SMOKE_REPLAY_EVIDENCE_SCHEMA_VERSION,
        "artifact_type": "capability_smoke_replay_evidence",
        "action_class": action_class,
        "capability_specification_sha256": capability_specification_sha256,
        "capability_candidate_sha256": capability_candidate_sha256,
        "mission_sha256": mission_sha256,
        "verification_context": encode_context(verification_context),
        "fetch_records": [dict(record) for record in fetch_records],
        "network_requests_replayed_during_historical_verification": 0,
        "scientific_status_changed": False,
    }
    packet["smoke_replay_evidence_sha256_without_self_field"] = _canonical_sha(packet)
    return packet


def authenticate_smoke_replay_evidence(
    evidence: Mapping[str, Any],
    *,
    action_class: str,
    capability_specification_sha256: str,
    capability_candidate_sha256: str,
    mission_sha256: str,
) -> tuple[ReplayFetcher, Mapping[str, Any] | None]:
    """Authenticate retained evidence and return its zero-network replay inputs."""
    _require(
        evidence.get("schema_version") == SMOKE_REPLAY_EVIDENCE_SCHEMA_VERSION
        and evidence.get("artifact_type") == "capability_smoke_replay_evidence",
        "smoke replay evidence schema/type drifted",
    )
    supplied_sha = evidence.get("smoke_replay_evidence_sha256_without_self_field")
    unsigned = dict(evidence)
    unsigned.pop("smoke_replay_evidence_sha256_without_self_field", None)
    _require(
        isinstance(supplied_sha, str) and supplied_sha == _canonical_sha(unsigned),
        "smoke replay evidence self binding is invalid",
    )
    _require(evidence.get("action_class") == action_class, "smoke replay action class drifted")
    _require(
        evidence.get("capability_specification_sha256") == capability_specification_sha256,
        "smoke replay specification binding drifted",
    )
    _require(
        evidence.get("capability_candidate_sha256") == capability_candidate_sha256,
        "smoke replay candidate binding drifted",
    )
    _require(evidence.get("mission_sha256") == mission_sha256, "smoke replay mission binding drifted")
    _require(
        evidence.get("network_requests_replayed_during_historical_verification") == 0
        and evidence.get("scientific_status_changed") is False,
        "smoke replay evidence widened historical authority",
    )
    records = evidence.get("fetch_records")
    _require(isinstance(records, list) and records, "smoke replay fetch record set is missing")
    context_value = decode_context(evidence.get("verification_context"))
    _require(
        context_value is None or isinstance(context_value, Mapping),
        "smoke replay verification context is invalid",
    )
    return ReplayFetcher(records), context_value  # type: ignore[arg-type]


__all__ = [
    "CapabilitySmokeReplayEvidenceError",
    "RecordingFetcher",
    "ReplayFetcher",
    "SMOKE_REPLAY_EVIDENCE_SCHEMA_VERSION",
    "authenticate_smoke_replay_evidence",
    "build_smoke_replay_evidence",
    "decode_context",
    "encode_context",
]
