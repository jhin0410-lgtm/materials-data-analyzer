"""External trust boundary for authority-bearing EvidencePacket expectations.

The low-level :mod:`evidence_packet` validator can prove structural consistency, exact
artifact-byte bindings, and agreement with a supplied expectation mapping.  It cannot prove
that the expectation mapping itself came from Governance, a trusted provider adapter, a signed
receipt, an immutable mission pin, or another authority outside the packet/expectation pair.

This module makes that trust dependency explicit.  Callers that intend to use an
EvidencePacket as authority-bearing scientific evidence must supply an expectation mapping plus
an independently obtained SHA-256 digest for the *entire* canonical expectation object.  The
digest is a trust-root input; it must not be generated from the same mutable expectation object
inside the validation path.

Authentication here remains provenance/expectation authentication only.  It does not establish
comparability, calibration transfer, causal validity, model validity, row identity, physical
origin, or scientific truth.
"""
from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

from . import evidence_packet as _packet

EXPECTATION_TRUST_SCHEMA_VERSION = "1.0"


class EvidenceExpectationTrustError(_packet.EvidencePacketError):
    """Raised when an external expectation trust root is missing or does not match."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise EvidenceExpectationTrustError(message)


def _trusted_sha256(value: object) -> str:
    _require(
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value),
        "trusted expectation SHA-256 must be an external lowercase SHA-256 digest",
    )
    return value


def authenticate_validation_expectations(
    expected: Mapping[str, Any],
    *,
    trusted_expectation_sha256: str,
) -> dict[str, Any]:
    """Authenticate one complete expectation object against an external digest.

    ``trusted_expectation_sha256`` is deliberately not derived here.  Its authority must come
    from a boundary outside the mutable EvidencePacket and expectation object, for example a
    mission-pinned immutable record, an independently authenticated adapter receipt, or a future
    signed/attested Governance record.
    """

    _require(isinstance(expected, Mapping), "validation expectations must be an object")
    trusted = _trusted_sha256(trusted_expectation_sha256)
    observed = _packet.canonical_sha256(expected)
    _require(
        observed == trusted,
        "validation expectations do not match the external trust-root digest",
    )
    return copy.deepcopy(dict(expected))


def validate_authenticated_evidence_packet(
    value: object,
    *,
    artifacts: Mapping[str, bytes],
    expected: Mapping[str, Any],
    trusted_expectation_sha256: str,
) -> dict[str, Any]:
    """Validate an EvidencePacket only after authenticating its external expectations."""

    authenticated_expected = authenticate_validation_expectations(
        expected,
        trusted_expectation_sha256=trusted_expectation_sha256,
    )
    return _packet.validate_evidence_packet(
        value,
        artifacts=artifacts,
        expected=authenticated_expected,
    )


def normalize_authenticated_evidence_packet(
    value: object,
    *,
    artifacts: Mapping[str, bytes],
    expected: Mapping[str, Any],
    trusted_expectation_sha256: str,
) -> dict[str, Any]:
    """Normalize only after the same external expectation-authentication boundary."""

    authenticated_expected = authenticate_validation_expectations(
        expected,
        trusted_expectation_sha256=trusted_expectation_sha256,
    )
    return _packet.normalize_evidence_packet(
        value,
        artifacts=artifacts,
        expected=authenticated_expected,
    )


__all__ = [
    "EXPECTATION_TRUST_SCHEMA_VERSION",
    "EvidenceExpectationTrustError",
    "authenticate_validation_expectations",
    "normalize_authenticated_evidence_packet",
    "validate_authenticated_evidence_packet",
]
