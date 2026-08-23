"""Authenticate the finite NIST AMMT publication-index discovery authority."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

POLICY_ID = "nist-ammt-publication-index-source-discovery-v1"
ACTION_CLASS = "experiment_specific_calibration_record_source_discovery"
POLICY_PATH = "configs/research/nist_ammt_publication_index_source_discovery_policy.v1.json"
POLICY_SHA256 = "e053faca2a28adae1d299d5771b6df4a99e1e15400b536e1f7502f34051a9324"
SOURCE_ID = "nist-ammt-relevant-publications-index"
SOURCE_URL = "https://www.nist.gov/el/ammt/relevant-publications"
SOURCE_CLASS = "official_curated_publication_index"
ALLOWED_HOSTS = ("www.nist.gov",)
CANDIDATE_LINK_HOSTS = ("www.nist.gov", "tsapps.nist.gov", "doi.org")
QUERY_TERMS = (
    "AMMT",
    "calibration",
    "laser",
    "power",
    "spot",
    "metrology",
    "machine-setting",
)
MAX_REQUESTS = 1
MAX_SOURCE_BYTES = 2_097_152
MAX_TOTAL_BYTES = 2_097_152
TIMEOUT_SECONDS = 60
MAX_CANDIDATES = 12


class NistAmmtSourceDiscoveryPolicyError(ValueError):
    """Raised when AMMT source-discovery authority cannot be authenticated exactly."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise NistAmmtSourceDiscoveryPolicyError(
                f"duplicate JSON key is not allowed: {key}"
            )
        result[key] = value
    return result


def _load_object(path: Path, field: str) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NistAmmtSourceDiscoveryPolicyError(
            f"{field} must be valid UTF-8 JSON"
        ) from exc
    if not isinstance(value, dict):
        raise NistAmmtSourceDiscoveryPolicyError(f"{field} root must be an object")
    return value, raw


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise NistAmmtSourceDiscoveryPolicyError(message)


def authenticate_nist_ammt_source_discovery_policy(
    *,
    repository_root: str | Path,
    mission_path: str | Path,
    expected_mission_sha256: str,
    policy_path: str | Path | None = None,
) -> dict[str, Any]:
    """Authenticate mission and exact discovery policy without network access."""
    root = Path(repository_root).expanduser().resolve(strict=True)
    mission_file = Path(mission_path).expanduser().resolve(strict=True)
    policy_file = (
        Path(policy_path).expanduser().resolve(strict=True)
        if policy_path is not None
        else (root / POLICY_PATH).resolve(strict=True)
    )
    for path, field in ((mission_file, "mission"), (policy_file, "policy")):
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise NistAmmtSourceDiscoveryPolicyError(
                f"{field} path escaped repository root"
            ) from exc

    mission, mission_raw = _load_object(mission_file, "mission")
    policy, policy_raw = _load_object(policy_file, "policy")
    mission_sha = hashlib.sha256(mission_raw).hexdigest()
    _require(
        mission_sha == expected_mission_sha256,
        "mission bytes do not match independently supplied mission SHA-256",
    )
    policy_sha = hashlib.sha256(policy_raw).hexdigest()
    _require(policy_sha == POLICY_SHA256, "discovery policy exact bytes drifted")

    pins = mission.get("source_trust_policy_pins")
    _require(isinstance(pins, list), "mission source-trust pins are missing")
    matches = [
        item
        for item in pins
        if isinstance(item, dict) and item.get("policy_id") == POLICY_ID
    ]
    _require(
        len(matches) == 1 and matches[0].get("sha256") == policy_sha,
        "mission discovery policy pin does not match exact policy bytes",
    )

    expected_policy = {
        "schema_version": "1.0",
        "policy_id": POLICY_ID,
        "action_class": ACTION_CLASS,
        "source_index": {
            "source_id": SOURCE_ID,
            "url": SOURCE_URL,
            "source_class": SOURCE_CLASS,
            "media_type": "html",
        },
        "network": {
            "scheme": "https",
            "allowed_hosts": list(ALLOWED_HOSTS),
            "max_requests": MAX_REQUESTS,
            "max_source_bytes": MAX_SOURCE_BYTES,
            "max_total_bytes": MAX_TOTAL_BYTES,
            "timeout_seconds": TIMEOUT_SECONDS,
            "unrestricted_search_allowed": False,
            "caller_authored_urls_allowed": False,
            "same_host_redirects_only": True,
        },
        "discovery": {
            "query_terms": list(QUERY_TERMS),
            "candidate_link_hosts": list(CANDIDATE_LINK_HOSTS),
            "max_candidates": MAX_CANDIDATES,
            "follow_candidate_links_during_discovery": False,
            "candidate_urls_gain_acquisition_authority": False,
            "source_index_text_may_be_row_level_measurement_authority": False,
        },
        "authority": {
            "scientific_status_change_authorized_by_discovery": False,
            "discovered_candidate_may_self_authorize_acquisition": False,
            "global_evidence_unavailability_may_be_claimed_from_empty_results": False,
        },
    }
    _require(policy == expected_policy, "discovery policy semantics drifted or widened")

    return {
        "schema_version": "1.0",
        "qualification_status": "exact_nist_ammt_source_discovery_policy_authenticated",
        "policy_id": POLICY_ID,
        "action_class": ACTION_CLASS,
        "mission_sha256": mission_sha,
        "policy_sha256": policy_sha,
        "source_id": SOURCE_ID,
        "source_url": SOURCE_URL,
        "source_class": SOURCE_CLASS,
        "allowed_hosts": list(ALLOWED_HOSTS),
        "candidate_link_hosts": list(CANDIDATE_LINK_HOSTS),
        "query_terms": list(QUERY_TERMS),
        "max_requests": MAX_REQUESTS,
        "max_source_bytes": MAX_SOURCE_BYTES,
        "max_total_bytes": MAX_TOTAL_BYTES,
        "timeout_seconds": TIMEOUT_SECONDS,
        "max_candidates": MAX_CANDIDATES,
        "network_access_performed": False,
        "unrestricted_search_performed": False,
        "caller_authored_url_used": False,
        "candidate_urls_gain_acquisition_authority": False,
        "scientific_status_changed": False,
    }


__all__ = [
    "ACTION_CLASS",
    "ALLOWED_HOSTS",
    "CANDIDATE_LINK_HOSTS",
    "MAX_CANDIDATES",
    "MAX_REQUESTS",
    "MAX_SOURCE_BYTES",
    "MAX_TOTAL_BYTES",
    "NistAmmtSourceDiscoveryPolicyError",
    "POLICY_ID",
    "POLICY_PATH",
    "POLICY_SHA256",
    "QUERY_TERMS",
    "SOURCE_CLASS",
    "SOURCE_ID",
    "SOURCE_URL",
    "TIMEOUT_SECONDS",
    "authenticate_nist_ammt_source_discovery_policy",
]
