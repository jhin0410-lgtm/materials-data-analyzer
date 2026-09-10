"""Authenticated bounded-stop contract for cycle-1 Zenodo transport unavailability.

This artifact records only that an already-authorized finite network request could not
complete through the project's transient-transport taxonomy.  It binds the stop to the
exact mission, standing network policy, source configuration, request ordinal, and any
prior source bytes already observed in the same cycle.  It deliberately does not attest
that an external provider event historically occurred and grants no scientific authority.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse

from .kernel import ResearchLoopError

SCHEMA_VERSION = "1.0"
POLICY_ID = "in625-zenodo-20503603-network-acquisition-v1"
PROVIDER = "zenodo"
RECORD_ID = 20503603
ALLOWED_HOST = "zenodo.org"
_REASON_CODE = "transient_network_transport_unavailable"
_STAGE_ORDINALS = {
    "zenodo_record_metadata": 1,
    "zenodo_readme": 2,
    "zenodo_archive": 3,
}
_STAGE_PRIOR_KEYS = {
    "zenodo_record_metadata": frozenset(),
    "zenodo_readme": frozenset({"metadata_sha256"}),
    "zenodo_archive": frozenset(
        {"metadata_sha256", "readme_sha256", "network_authorization_sha256"}
    ),
}
_EXACT_KEYS = {
    "schema_version",
    "status",
    "reason_code",
    "cycle_index",
    "stage",
    "request_ordinal",
    "requested_url",
    "authority",
    "observed_prior_evidence",
    "transport_error_class",
    "transport_error_detail",
    "transient_transport_classification",
    "provider_event_externally_attested",
    "global_evidence_unavailability_claimed",
    "network_failure_interpreted_as_negative_scientific_evidence",
    "source_provenance_established_by_failed_request",
    "empirical_model_validation_established",
    "hypothesis_truth_established",
    "positive_scientific_closeout",
    "scientific_status_changed",
    "stop_sha256_without_self_field",
}
_AUTHORITY_KEYS = {
    "mission_sha256",
    "network_policy_id",
    "network_policy_sha256",
    "source_config_sha256",
    "provider",
    "record_id",
    "allowed_hosts",
    "maximum_network_requests_per_cycle",
}


class Cycle1TransportStopError(ResearchLoopError):
    """Raised when a cycle-1 transport stop cannot be authenticated exactly."""


def _canonical_sha(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _sha(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise Cycle1TransportStopError(f"{field} must be canonical lowercase SHA-256")
    return value


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise Cycle1TransportStopError(f"{field} must be non-empty trimmed text")
    return value


def _exact_https_zenodo_url(value: object) -> str:
    text = _text(value, "requested_url")
    parsed = urlparse(text)
    if (
        parsed.scheme.lower() != "https"
        or (parsed.hostname or "").lower() != ALLOWED_HOST
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in (None, 443)
        or parsed.fragment
    ):
        raise Cycle1TransportStopError(
            "requested_url must remain on exact authorized Zenodo HTTPS authority"
        )
    return text


def build_cycle1_transport_stop(
    *,
    mission_sha256: str,
    network_policy_sha256: str,
    source_config_sha256: str,
    maximum_network_requests_per_cycle: int,
    stage: str,
    requested_url: str,
    transport_error_class: str,
    transport_error_detail: str,
    observed_prior_evidence: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Build one self-authenticating stop after a typed transient delivery failure."""
    if stage not in _STAGE_ORDINALS:
        raise Cycle1TransportStopError(f"unsupported cycle-1 transport stage: {stage!r}")
    if (
        isinstance(maximum_network_requests_per_cycle, bool)
        or maximum_network_requests_per_cycle != 3
    ):
        raise Cycle1TransportStopError(
            "cycle-1 transport stop requires the exact three-request standing-policy budget"
        )
    prior = dict(observed_prior_evidence or {})
    if set(prior) != set(_STAGE_PRIOR_KEYS[stage]):
        raise Cycle1TransportStopError(
            "observed_prior_evidence field set does not match the failed request stage"
        )
    normalized_prior = {
        key: _sha(value, f"observed_prior_evidence.{key}")
        for key, value in sorted(prior.items())
    }
    stop: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "stopped",
        "reason_code": _REASON_CODE,
        "cycle_index": 1,
        "stage": stage,
        "request_ordinal": _STAGE_ORDINALS[stage],
        "requested_url": _exact_https_zenodo_url(requested_url),
        "authority": {
            "mission_sha256": _sha(mission_sha256, "mission_sha256"),
            "network_policy_id": POLICY_ID,
            "network_policy_sha256": _sha(
                network_policy_sha256, "network_policy_sha256"
            ),
            "source_config_sha256": _sha(
                source_config_sha256, "source_config_sha256"
            ),
            "provider": PROVIDER,
            "record_id": RECORD_ID,
            "allowed_hosts": [ALLOWED_HOST],
            "maximum_network_requests_per_cycle": 3,
        },
        "observed_prior_evidence": normalized_prior,
        "transport_error_class": _text(
            transport_error_class, "transport_error_class"
        ),
        "transport_error_detail": _text(
            transport_error_detail, "transport_error_detail"
        ),
        "transient_transport_classification": True,
        "provider_event_externally_attested": False,
        "global_evidence_unavailability_claimed": False,
        "network_failure_interpreted_as_negative_scientific_evidence": False,
        "source_provenance_established_by_failed_request": False,
        "empirical_model_validation_established": False,
        "hypothesis_truth_established": False,
        "positive_scientific_closeout": False,
        "scientific_status_changed": False,
    }
    stop["stop_sha256_without_self_field"] = _canonical_sha(stop)
    return stop


def authenticate_cycle1_transport_stop(value: object) -> dict[str, Any]:
    """Re-authenticate a persisted stop without trusting its self-declared classification."""
    if not isinstance(value, Mapping):
        raise Cycle1TransportStopError("cycle-1 transport stop must be an object")
    stop = dict(value)
    if set(stop) != _EXACT_KEYS:
        raise Cycle1TransportStopError("cycle-1 transport stop field set drifted")
    embedded = _sha(
        stop.get("stop_sha256_without_self_field"),
        "stop_sha256_without_self_field",
    )
    unsigned = dict(stop)
    unsigned.pop("stop_sha256_without_self_field", None)
    if _canonical_sha(unsigned) != embedded:
        raise Cycle1TransportStopError("cycle-1 transport stop self-hash is invalid")
    if (
        stop.get("schema_version") != SCHEMA_VERSION
        or stop.get("status") != "stopped"
        or stop.get("reason_code") != _REASON_CODE
        or stop.get("cycle_index") != 1
    ):
        raise Cycle1TransportStopError("cycle-1 transport stop identity drifted")
    stage = stop.get("stage")
    if stage not in _STAGE_ORDINALS:
        raise Cycle1TransportStopError("cycle-1 transport stop stage drifted")
    if stop.get("request_ordinal") != _STAGE_ORDINALS[stage]:
        raise Cycle1TransportStopError("cycle-1 transport request ordinal drifted")
    _exact_https_zenodo_url(stop.get("requested_url"))

    authority = stop.get("authority")
    if not isinstance(authority, Mapping) or set(authority) != _AUTHORITY_KEYS:
        raise Cycle1TransportStopError("cycle-1 transport authority field set drifted")
    _sha(authority.get("mission_sha256"), "authority.mission_sha256")
    _sha(authority.get("network_policy_sha256"), "authority.network_policy_sha256")
    _sha(authority.get("source_config_sha256"), "authority.source_config_sha256")
    if (
        authority.get("network_policy_id") != POLICY_ID
        or authority.get("provider") != PROVIDER
        or authority.get("record_id") != RECORD_ID
        or authority.get("allowed_hosts") != [ALLOWED_HOST]
        or authority.get("maximum_network_requests_per_cycle") != 3
    ):
        raise Cycle1TransportStopError("cycle-1 transport authority widened or drifted")

    prior = stop.get("observed_prior_evidence")
    if not isinstance(prior, Mapping) or set(prior) != set(_STAGE_PRIOR_KEYS[stage]):
        raise Cycle1TransportStopError("cycle-1 prior-evidence binding drifted")
    for key, digest in prior.items():
        _sha(digest, f"observed_prior_evidence.{key}")
    _text(stop.get("transport_error_class"), "transport_error_class")
    _text(stop.get("transport_error_detail"), "transport_error_detail")

    required_false = (
        "provider_event_externally_attested",
        "global_evidence_unavailability_claimed",
        "network_failure_interpreted_as_negative_scientific_evidence",
        "source_provenance_established_by_failed_request",
        "empirical_model_validation_established",
        "hypothesis_truth_established",
        "positive_scientific_closeout",
        "scientific_status_changed",
    )
    if stop.get("transient_transport_classification") is not True or any(
        stop.get(field) is not False for field in required_false
    ):
        raise Cycle1TransportStopError(
            "cycle-1 transport stop attempted to widen epistemic authority"
        )
    return stop


__all__ = [
    "Cycle1TransportStopError",
    "authenticate_cycle1_transport_stop",
    "build_cycle1_transport_stop",
]
