"""Authenticate the exact IN625 Zenodo standing network policy under a mission root.

This contract qualifies only the narrow network authority needed to retrieve the exact
Zenodo 20503603 metadata, README, and archive already pinned by repository source identity.
It never performs network access and grants no scientific authority.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .kernel import ResearchLoopError
from .research_program import ResearchProgramError, validate_research_mission

SCHEMA_VERSION = "1.0"
QUALIFICATION_SCHEMA_VERSION = "1.0"
POLICY_ID = "in625-zenodo-20503603-network-acquisition-v1"
ADAPTER_ID = "in625-external-evidence"
SOURCE_ID = "zenodo-20503603-in625-lpbf-publication-supplement"
RECORD_ID = 20503603


class In625NetworkPolicyError(ResearchLoopError):
    """Raised when the exact standing network authority cannot be reconstructed."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise In625NetworkPolicyError(f"duplicate JSON key is not allowed: {key}")
        value[key] = item
    return value


def _json(raw: bytes, field: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise In625NetworkPolicyError(f"{field} must be valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise In625NetworkPolicyError(f"{field} root must be an object")
    return value


def _sha(value: object, field: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise In625NetworkPolicyError(f"{field} must be canonical lowercase SHA-256")
    return value


def _strict_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise In625NetworkPolicyError(f"{field} must be non-empty trimmed text")
    return value


def _repo_file(root: Path, raw: object, field: str) -> Path:
    path = Path(_strict_text(raw, field)).expanduser()
    if not path.is_absolute():
        path = root / path
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise In625NetworkPolicyError(f"{field} does not resolve") from exc
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise In625NetworkPolicyError(f"{field} escapes repository root") from exc
    if not resolved.is_file():
        raise In625NetworkPolicyError(f"{field} must be a file")
    return resolved


def _exact_keys(value: Mapping[str, Any], expected: set[str], field: str) -> None:
    if set(value) != expected:
        raise In625NetworkPolicyError(f"{field} field set drifted")


def _file_map(value: object, field: str) -> dict[str, Mapping[str, Any]]:
    if not isinstance(value, list) or len(value) != 2:
        raise In625NetworkPolicyError(f"{field} must contain exactly README and Dataset.zip")
    result: dict[str, Mapping[str, Any]] = {}
    expected_keys = {
        "name",
        "size_bytes",
        "provider_checksum_algorithm",
        "provider_checksum_digest",
        "verified_sha256",
    }
    for index, raw in enumerate(value):
        if not isinstance(raw, Mapping):
            raise In625NetworkPolicyError(f"{field}[{index}] must be an object")
        _exact_keys(raw, expected_keys, f"{field}[{index}]")
        name = _strict_text(raw.get("name"), f"{field}[{index}].name")
        if name in result:
            raise In625NetworkPolicyError("network policy contains duplicate file identity")
        result[name] = raw
    if set(result) != {"README - Dataset description.txt", "Dataset.zip"}:
        raise In625NetworkPolicyError("network policy exact file set drifted")
    return result


def authenticate_in625_network_policy(
    *,
    repository_root: str | Path,
    mission_path: str | Path,
    expected_mission_sha256: str,
    policy_path: str | Path,
    source_config_path: str | Path,
) -> dict[str, Any]:
    """Reconstruct exact mission-pinned Zenodo authority without performing network access."""
    root = Path(repository_root).expanduser().resolve(strict=True)
    mission_file = Path(mission_path).expanduser().resolve(strict=True)
    policy_file = Path(policy_path).expanduser().resolve(strict=True)
    source_file = Path(source_config_path).expanduser().resolve(strict=True)
    for path, field in ((mission_file, "mission_path"), (policy_file, "policy_path"), (source_file, "source_config_path")):
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise In625NetworkPolicyError(f"{field} escapes repository root") from exc
        if not path.is_file():
            raise In625NetworkPolicyError(f"{field} must be a file")

    mission_bytes = mission_file.read_bytes()
    mission_sha = hashlib.sha256(mission_bytes).hexdigest()
    if mission_sha != _sha(expected_mission_sha256, "expected_mission_sha256"):
        raise In625NetworkPolicyError("mission bytes do not match supplied expected mission SHA-256")
    try:
        mission = validate_research_mission(_json(mission_bytes, "research mission"))
    except ResearchProgramError as exc:
        raise In625NetworkPolicyError("research mission failed current mission validation") from exc
    if mission.get("schema_version") != "1.2":
        raise In625NetworkPolicyError("standing network authority requires mission schema_version 1.2")
    if mission.get("autonomy_policy", {}).get("network_evidence_search") != "explicit_authorization":
        raise In625NetworkPolicyError("mission does not permit explicit-authorized network evidence search")

    policy_bytes = policy_file.read_bytes()
    policy_sha = hashlib.sha256(policy_bytes).hexdigest()
    pins = mission.get("source_trust_policy_pins")
    matches = [item for item in pins if isinstance(item, Mapping) and item.get("policy_id") == POLICY_ID] if isinstance(pins, list) else []
    if len(matches) != 1 or matches[0].get("sha256") != policy_sha:
        raise In625NetworkPolicyError("exact network policy bytes do not match one mission source-trust pin")

    policy = _json(policy_bytes, "IN625 network policy")
    _exact_keys(
        policy,
        {
            "schema_version",
            "policy_id",
            "adapter_id",
            "provider",
            "transport",
            "source_binding",
            "allowed_files",
            "limits",
            "scientific_boundary",
            "limitations",
        },
        "IN625 network policy",
    )
    if policy.get("schema_version") != SCHEMA_VERSION or policy.get("policy_id") != POLICY_ID:
        raise In625NetworkPolicyError("unsupported IN625 network policy identity")
    if policy.get("adapter_id") != ADAPTER_ID or policy.get("provider") != "zenodo":
        raise In625NetworkPolicyError("network policy adapter/provider drifted")

    transport = policy.get("transport")
    if not isinstance(transport, Mapping):
        raise In625NetworkPolicyError("network policy transport must be an object")
    _exact_keys(transport, {"scheme", "host", "allowed_port", "redirect_host_must_remain_exact"}, "network policy transport")
    if dict(transport) != {
        "scheme": "https",
        "host": "zenodo.org",
        "allowed_port": 443,
        "redirect_host_must_remain_exact": True,
    }:
        raise In625NetworkPolicyError("network transport authority widened or drifted")

    source_binding = policy.get("source_binding")
    if not isinstance(source_binding, Mapping):
        raise In625NetworkPolicyError("network policy source_binding must be an object")
    _exact_keys(source_binding, {"source_config_path", "source_config_sha256", "record_id", "record_api_path"}, "network policy source_binding")
    pinned_source = _repo_file(root, source_binding.get("source_config_path"), "source_binding.source_config_path")
    if pinned_source != source_file:
        raise In625NetworkPolicyError("caller source config differs from mission-pinned network policy")
    source_bytes = source_file.read_bytes()
    source_sha = hashlib.sha256(source_bytes).hexdigest()
    if source_sha != _sha(source_binding.get("source_config_sha256"), "source_binding.source_config_sha256"):
        raise In625NetworkPolicyError("source config bytes differ from network policy pin")
    if source_binding.get("record_id") != RECORD_ID or source_binding.get("record_api_path") != "/api/records/20503603":
        raise In625NetworkPolicyError("network policy record identity drifted")

    source = _json(source_bytes, "IN625 source config")
    if source.get("source_id") != SOURCE_ID:
        raise In625NetworkPolicyError("source config identity drifted")
    zenodo = source.get("zenodo")
    if not isinstance(zenodo, Mapping) or zenodo.get("record_id") != RECORD_ID:
        raise In625NetworkPolicyError("source config Zenodo identity drifted")
    files = zenodo.get("files")
    if not isinstance(files, Mapping):
        raise In625NetworkPolicyError("source config files are malformed")
    allowed = _file_map(policy.get("allowed_files"), "network policy allowed_files")
    for name, rule in allowed.items():
        source_rule = files.get(name)
        if not isinstance(source_rule, Mapping):
            raise In625NetworkPolicyError(f"source config lost exact allowed file: {name}")
        for field in ("size_bytes", "provider_checksum_algorithm", "provider_checksum_digest", "verified_sha256"):
            if source_rule.get(field) != rule.get(field):
                raise In625NetworkPolicyError(f"network/source file binding drifted: {name}.{field}")

    limits = policy.get("limits")
    if not isinstance(limits, Mapping):
        raise In625NetworkPolicyError("network policy limits must be an object")
    _exact_keys(limits, {"maximum_network_requests_per_cycle", "maximum_archive_bytes", "unrestricted_search", "arbitrary_url_fetch"}, "network policy limits")
    if limits.get("maximum_network_requests_per_cycle") != 3 or limits.get("maximum_archive_bytes") != 180726708:
        raise In625NetworkPolicyError("network request/byte limits drifted")
    if limits.get("unrestricted_search") is not False or limits.get("arbitrary_url_fetch") is not False:
        raise In625NetworkPolicyError("network policy improperly permits open-ended discovery")

    boundary = policy.get("scientific_boundary")
    if not isinstance(boundary, Mapping) or not boundary:
        raise In625NetworkPolicyError("network scientific boundary is missing")
    if any(value is not False for value in boundary.values()):
        raise In625NetworkPolicyError("network policy improperly widens scientific authority")

    return {
        "schema_version": QUALIFICATION_SCHEMA_VERSION,
        "qualification_status": "exact_standing_network_policy_authenticated",
        "mission_sha256": mission_sha,
        "policy_id": POLICY_ID,
        "policy_sha256": policy_sha,
        "adapter_id": ADAPTER_ID,
        "provider": "zenodo",
        "record_id": RECORD_ID,
        "record_api_url": "https://zenodo.org/api/records/20503603",
        "source_config_path": str(source_file),
        "source_config_sha256": source_sha,
        "allowed_file_names": sorted(allowed),
        "maximum_network_requests_per_cycle": 3,
        "maximum_archive_bytes": 180726708,
        "unrestricted_search_authorized": False,
        "arbitrary_url_fetch_authorized": False,
        "network_access_performed": False,
        "scientific_evidence_upgraded": False,
        "empirical_authority_granted": False,
        "positive_scientific_closeout_granted": False,
    }


__all__ = [
    "ADAPTER_ID",
    "In625NetworkPolicyError",
    "POLICY_ID",
    "authenticate_in625_network_policy",
]
