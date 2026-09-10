"""Independently verify a persisted cycle-1 Zenodo transport bounded stop.

This verifier reconstructs the current mission-pinned standing network authority from
repository bytes and checks that the persisted stop is exactly bound to it.  Successful
verification authenticates only the bounded-stop record and its local authority bindings;
it neither attests the historical provider event nor satisfies a full autonomous live run.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .autonomous_production_cycle1_transport_stop import (
    Cycle1TransportStopError,
    authenticate_cycle1_transport_stop,
)
from .in625_archive_network_acquisition import (
    In625ArchiveNetworkAcquisitionError,
    validate_in625_archive_network_authorization,
)
from .in625_network_policy import authenticate_in625_network_policy
from .kernel import ResearchLoopError

EXPECTED_MISSION_SHA256 = (
    "98d8730a4ba1221685267ed56cd7ae75f2ce60fcfdd8f8bb426a3825986c70ea"
)
MISSION_PATH = "configs/research/autonomous_in625_production_mission.v1.json"
NETWORK_POLICY_PATH = "configs/research/in625_zenodo_network_acquisition_policy.v1.json"
SOURCE_CONFIG_PATH = "configs/research/in625_zenodo_20503603_verified_source.v1.json"
STOP_PATH = "cycle-1-transport-stop.json"


class Cycle1TransportStopVerificationError(ResearchLoopError):
    """Raised when a cycle-1 transport stop does not match current trusted authority."""


def _read_json(path: Path, field: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Cycle1TransportStopVerificationError(
            f"{field} must be valid UTF-8 JSON"
        ) from exc
    if not isinstance(value, dict):
        raise Cycle1TransportStopVerificationError(f"{field} root must be an object")
    return value


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise Cycle1TransportStopVerificationError(message)


def verify_cycle1_transport_stop(
    *, repository_root: str | Path, output_root: str | Path
) -> dict[str, Any]:
    """Rebuild exact authority and authenticate one persisted cycle-1 transport stop."""
    root = Path(repository_root).expanduser().resolve(strict=True)
    output = Path(output_root).expanduser()
    if not output.is_absolute():
        output = root / output
    output = output.resolve(strict=True)

    mission = (root / MISSION_PATH).resolve(strict=True)
    policy = (root / NETWORK_POLICY_PATH).resolve(strict=True)
    source = (root / SOURCE_CONFIG_PATH).resolve(strict=True)
    observed_mission_sha = hashlib.sha256(mission.read_bytes()).hexdigest()
    _require(
        observed_mission_sha == EXPECTED_MISSION_SHA256,
        "current mission bytes differ from the independently pinned production mission",
    )
    qualification = authenticate_in625_network_policy(
        repository_root=root,
        mission_path=mission,
        expected_mission_sha256=EXPECTED_MISSION_SHA256,
        policy_path=policy,
        source_config_path=source,
    )
    persisted = _read_json(output / STOP_PATH, "cycle-1 transport stop")
    try:
        stop = authenticate_cycle1_transport_stop(persisted)
    except Cycle1TransportStopError as exc:
        raise Cycle1TransportStopVerificationError(
            "persisted cycle-1 transport stop failed intrinsic authentication"
        ) from exc

    authority = stop.get("authority")
    _require(isinstance(authority, Mapping), "transport stop authority is missing")
    _require(
        authority.get("mission_sha256") == EXPECTED_MISSION_SHA256,
        "transport stop mission binding differs from independent mission pin",
    )
    _require(
        authority.get("network_policy_sha256") == qualification.get("policy_sha256"),
        "transport stop network-policy binding differs from reconstructed authority",
    )
    _require(
        authority.get("source_config_sha256")
        == hashlib.sha256(source.read_bytes()).hexdigest()
        == qualification.get("source_config_sha256"),
        "transport stop source-config binding differs from reconstructed authority",
    )
    _require(
        authority.get("maximum_network_requests_per_cycle")
        == qualification.get("maximum_network_requests_per_cycle")
        == 3,
        "transport stop request budget differs from reconstructed standing policy",
    )
    _require(
        qualification.get("unrestricted_search_authorized") is False
        and qualification.get("arbitrary_url_fetch_authorized") is False,
        "reconstructed standing policy unexpectedly widened network authority",
    )

    bounded = _read_json(output / "bounded-stop.json", "bounded stop")
    _require(
        bounded == stop,
        "bounded-stop.json differs from authenticated cycle-1 transport stop",
    )
    _require(
        not (output / "autonomous-production-manifest.json").exists(),
        "transport-stop path may not emit a successful autonomous production manifest",
    )

    stage = stop["stage"]
    prior = stop["observed_prior_evidence"]
    if stage in {"zenodo_record_metadata", "zenodo_readme"}:
        _require(
            not (output / "source-readme-manifest.json").exists(),
            "pre-README transport stop may not promote partial control-plane bytes to source evidence",
        )
        _require(
            not (output / "network-authorization.json").exists(),
            "pre-archive transport stop may not emit archive authorization",
        )
    elif stage == "zenodo_archive":
        record_path = output / "record.json"
        source_manifest_path = output / "source-readme-manifest.json"
        authorization_path = output / "network-authorization.json"
        _require(
            record_path.is_file()
            and source_manifest_path.is_file()
            and authorization_path.is_file(),
            "archive transport stop requires completed metadata/README authority artifacts",
        )
        metadata_bytes = record_path.read_bytes()
        _require(
            prior.get("metadata_sha256") == hashlib.sha256(metadata_bytes).hexdigest(),
            "archive stop prior metadata hash differs from persisted completed metadata",
        )
        source_bytes = source.read_bytes()
        source_config = _read_json(source, "source config")
        readme_name = source_config.get("zenodo", {}).get("readme_file")
        _require(
            isinstance(readme_name, str) and readme_name,
            "source README identity is invalid",
        )
        readme_path = output / readme_name
        _require(readme_path.is_file(), "archive stop lost completed README bytes")
        readme_bytes = readme_path.read_bytes()
        _require(
            prior.get("readme_sha256") == hashlib.sha256(readme_bytes).hexdigest(),
            "archive stop prior README hash differs from persisted completed README",
        )
        authorization = _read_json(authorization_path, "network authorization")
        try:
            reconstructed_authorization = validate_in625_archive_network_authorization(
                authorization,
                config=source_config,
                config_bytes=source_bytes,
                metadata_bytes=metadata_bytes,
                readme_bytes=readme_bytes,
            )
        except In625ArchiveNetworkAcquisitionError as exc:
            raise Cycle1TransportStopVerificationError(
                "archive stop prior authorization failed authoritative reconstruction"
            ) from exc
        _require(
            prior.get("network_authorization_sha256")
            == reconstructed_authorization.get("authorization_sha256"),
            "archive stop prior authorization hash differs from reconstructed authorization",
        )

    return {
        "verification_status": "cycle_1_transport_stop_authenticated",
        "stage": stage,
        "request_ordinal": stop["request_ordinal"],
        "stop_sha256_without_self_field": stop["stop_sha256_without_self_field"],
        "mission_sha256": EXPECTED_MISSION_SHA256,
        "network_policy_sha256": qualification["policy_sha256"],
        "source_config_sha256": qualification["source_config_sha256"],
        "provider_event_externally_attested": False,
        "full_autonomous_live_gate_satisfied": False,
        "scientific_status_changed": False,
    }


__all__ = [
    "Cycle1TransportStopVerificationError",
    "verify_cycle1_transport_stop",
]
