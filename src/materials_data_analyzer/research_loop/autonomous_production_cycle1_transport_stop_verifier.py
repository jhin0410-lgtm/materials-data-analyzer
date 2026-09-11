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
from urllib.parse import unquote, urlparse

from .autonomous_production_cycle1_transport_stop import (
    Cycle1TransportStopError,
    authenticate_cycle1_transport_stop,
)
from .in625_archive_network_acquisition import (
    In625ArchiveNetworkAcquisitionError,
    validate_in625_archive_network_authorization,
)
from .in625_network_policy import authenticate_in625_network_policy
from .in625_zenodo_live_evidence import (
    In625ZenodoLiveEvidenceError,
    validate_verified_in625_zenodo_metadata,
)
from .kernel import ResearchLoopError

EXPECTED_MISSION_SHA256 = (
    "98d8730a4ba1221685267ed56cd7ae75f2ce60fcfdd8f8bb426a3825986c70ea"
)
MISSION_PATH = "configs/research/autonomous_in625_production_mission.v1.json"
NETWORK_POLICY_PATH = "configs/research/in625_zenodo_network_acquisition_policy.v1.json"
SOURCE_CONFIG_PATH = "configs/research/in625_zenodo_20503603_verified_source.v1.json"
STOP_PATH = "cycle-1-transport-stop.json"
ZENODO_HOST = "zenodo.org"


class Cycle1TransportStopVerificationError(ResearchLoopError):
    """Raised when a cycle-1 transport stop does not match current trusted authority."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise Cycle1TransportStopVerificationError(
                f"duplicate JSON key is not allowed: {key}"
            )
        result[key] = value
    return result


def _read_json_bytes(raw: bytes, field: str) -> dict[str, Any]:
    try:
        value = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_pairs
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Cycle1TransportStopVerificationError(
            f"{field} must be valid UTF-8 JSON"
        ) from exc
    if not isinstance(value, dict):
        raise Cycle1TransportStopVerificationError(f"{field} root must be an object")
    return value


def _read_json(path: Path, field: str) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise Cycle1TransportStopVerificationError(f"{field} must be readable") from exc
    return _read_json_bytes(raw, field)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise Cycle1TransportStopVerificationError(message)


def _published_record_file_route(
    value: object,
    *,
    record_id: int,
    file_name: str,
    field: str,
) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise Cycle1TransportStopVerificationError(f"{field} must be non-empty text")
    parsed = urlparse(value)
    try:
        port = parsed.port
    except ValueError as exc:
        raise Cycle1TransportStopVerificationError(
            f"{field} contains an invalid port"
        ) from exc
    if (
        parsed.scheme.lower() != "https"
        or (parsed.hostname or "").lower() != ZENODO_HOST
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        raise Cycle1TransportStopVerificationError(
            f"{field} left exact query-free Zenodo HTTPS authority"
        )
    expected_path = f"/api/records/{record_id}/files/{file_name}/content"
    if unquote(parsed.path) != expected_path:
        raise Cycle1TransportStopVerificationError(
            f"{field} is not the pinned published-record file content route"
        )
    return value


def _completed_metadata_control_plane_witness(
    output: Path,
    *,
    source_config: Mapping[str, Any],
    record_id: int,
    readme_name: str,
    requested_readme_url: str | None,
) -> tuple[bytes, str]:
    """Replay trusted record semantics without granting scientific authority."""
    record_path = output / "record.json"
    _require(
        record_path.is_file(),
        "post-metadata transport stop requires retained completed record metadata",
    )
    metadata_bytes = record_path.read_bytes()
    try:
        metadata_witness = validate_verified_in625_zenodo_metadata(
            config=source_config,
            metadata_bytes=metadata_bytes,
        )
    except In625ZenodoLiveEvidenceError as exc:
        raise Cycle1TransportStopVerificationError(
            "retained completed record metadata failed authoritative source-identity replay"
        ) from exc
    file_bindings = metadata_witness.get("file_bindings")
    _require(
        isinstance(file_bindings, Mapping),
        "authoritative metadata replay omitted exact file bindings",
    )
    readme_binding = file_bindings.get(readme_name)
    _require(
        isinstance(readme_binding, Mapping),
        "authoritative metadata replay omitted configured README binding",
    )
    metadata_readme_url = _published_record_file_route(
        readme_binding.get("download_url"),
        record_id=record_id,
        file_name=readme_name,
        field="retained metadata README download URL",
    )
    if requested_readme_url is not None:
        _require(
            metadata_readme_url == requested_readme_url,
            "README stop requested URL differs from retained completed metadata",
        )
    return metadata_bytes, metadata_readme_url


def verify_cycle1_transport_stop(
    *, repository_root: str | Path, output_root: str | Path
) -> dict[str, Any]:
    """Rebuild exact authority and authenticate one persisted cycle-1 transport stop."""
    root = Path(repository_root).expanduser().resolve(strict=True)
    output = Path(output_root).expanduser()
    if not output.is_absolute():
        output = root / output
    # Output may intentionally be an exported/downloaded evidence directory outside the
    # repository.  It is read-only input to this verifier; all trusted authority roots
    # below are reconstructed from fixed repository paths.
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
    source_bytes = source.read_bytes()
    source_config = _read_json_bytes(source_bytes, "source config")
    _require(
        authority.get("source_config_sha256")
        == hashlib.sha256(source_bytes).hexdigest()
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

    zenodo = source_config.get("zenodo")
    _require(isinstance(zenodo, Mapping), "source config Zenodo identity is missing")
    record_id = zenodo.get("record_id")
    _require(
        isinstance(record_id, int)
        and not isinstance(record_id, bool)
        and record_id == authority.get("record_id")
        and record_id == 20503603,
        "transport stop record identity differs from pinned source config",
    )
    readme_name = zenodo.get("readme_file")
    archive_name = zenodo.get("archive_file")
    _require(
        isinstance(readme_name, str) and readme_name,
        "source README identity is invalid",
    )
    _require(
        isinstance(archive_name, str) and archive_name,
        "source archive identity is invalid",
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
    requested_url = stop["requested_url"]
    requested_route_basis: str
    completed_metadata_witness_replayed = False
    if stage == "zenodo_record_metadata":
        expected_record_url = qualification.get("record_api_url")
        _require(
            isinstance(expected_record_url, str)
            and requested_url == expected_record_url,
            "metadata stop requested URL differs from reconstructed standing-policy record API",
        )
        requested_route_basis = "standing_network_policy_record_api"
        _require(
            not (output / "record.json").exists(),
            "metadata transport stop may not retain nonexistent completed metadata",
        )
        _require(
            not (output / "source-readme-manifest.json").exists(),
            "metadata transport stop may not promote partial control-plane bytes to source evidence",
        )
        _require(
            not (output / "network-authorization.json").exists(),
            "metadata transport stop may not emit archive authorization",
        )
    elif stage == "zenodo_readme":
        _published_record_file_route(
            requested_url,
            record_id=record_id,
            file_name=readme_name,
            field="README stop requested URL",
        )
        metadata_bytes, _ = _completed_metadata_control_plane_witness(
            output,
            source_config=source_config,
            record_id=record_id,
            readme_name=readme_name,
            requested_readme_url=requested_url,
        )
        _require(
            prior.get("metadata_sha256") == hashlib.sha256(metadata_bytes).hexdigest(),
            "README stop prior metadata hash differs from retained completed metadata",
        )
        completed_metadata_witness_replayed = True
        requested_route_basis = "retained_metadata_and_pinned_readme_content_route"
        _require(
            not (output / readme_name).exists(),
            "README transport stop may not retain failed README bytes as completed evidence",
        )
        _require(
            not (output / "source-readme-manifest.json").exists(),
            "README transport stop may not promote partial control-plane bytes to source evidence",
        )
        _require(
            not (output / "network-authorization.json").exists(),
            "README transport stop may not emit archive authorization",
        )
    elif stage == "zenodo_archive":
        source_manifest_path = output / "source-readme-manifest.json"
        authorization_path = output / "network-authorization.json"
        _require(
            source_manifest_path.is_file() and authorization_path.is_file(),
            "archive transport stop requires completed metadata/README authority artifacts",
        )
        metadata_bytes, _ = _completed_metadata_control_plane_witness(
            output,
            source_config=source_config,
            record_id=record_id,
            readme_name=readme_name,
            requested_readme_url=None,
        )
        _require(
            prior.get("metadata_sha256") == hashlib.sha256(metadata_bytes).hexdigest(),
            "archive stop prior metadata hash differs from persisted completed metadata",
        )
        completed_metadata_witness_replayed = True
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
        archive_binding = reconstructed_authorization.get("archive")
        _require(
            isinstance(archive_binding, Mapping)
            and isinstance(archive_binding.get("download_url"), str),
            "reconstructed archive authorization omitted exact download URL",
        )
        archive_url = archive_binding["download_url"]
        _published_record_file_route(
            archive_url,
            record_id=record_id,
            file_name=archive_name,
            field="reconstructed archive URL",
        )
        _require(
            requested_url == archive_url,
            "archive stop requested URL differs from reconstructed authorization",
        )
        requested_route_basis = "reconstructed_archive_authorization"
    else:  # pragma: no cover - intrinsic authentication closes this branch.
        raise Cycle1TransportStopVerificationError("unsupported transport-stop stage")

    return {
        "verification_status": "cycle_1_transport_stop_authenticated",
        "stage": stage,
        "request_ordinal": stop["request_ordinal"],
        "requested_url_authenticated": True,
        "requested_route_basis": requested_route_basis,
        "completed_metadata_control_plane_witness_replayed": completed_metadata_witness_replayed,
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
