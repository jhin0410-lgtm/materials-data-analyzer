"""Authenticate provenance-derived NIST AMMT calibration candidate acquisition authority."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

POLICY_ID = "nist-ammt-calibration-candidate-derived-acquisition-v1"
ACTION_CLASS = "experiment_specific_calibration_record_candidate_acquisition"
POLICY_PATH = (
    "configs/research/nist_ammt_calibration_candidate_derived_acquisition_policy.v1.json"
)
POLICY_SHA256 = "ef92f5d436a85f756d87e136ebc59a2cf64c932f8c599f23cd13c4c59bd8319b"
DISCOVERY_POLICY_ID = "nist-ammt-publication-index-source-discovery-v1"
DISCOVERY_SOURCE_ID = "nist-ammt-relevant-publications-index"
REQUIRED_CANDIDATE_RANK = 1
REQUIRED_CANDIDATE_HOST = "www.nist.gov"
CANDIDATE_PATH_PREFIX = "/publications/"
CANDIDATE_PAGE_ALLOWED_HOSTS = ("www.nist.gov",)
FULL_TEXT_ALLOWED_HOSTS = ("tsapps.nist.gov",)
MAX_REQUESTS = 2
MAX_CANDIDATE_PAGE_BYTES = 2_097_152
MAX_FULL_TEXT_BYTES = 16_777_216
MAX_TOTAL_BYTES = 18_874_368
TIMEOUT_SECONDS = 90
FULL_TEXT_LINK_LABEL = "Local Download"
FULL_TEXT_PATH_PREFIX = "/publication/get_pdf.cfm"
FULL_TEXT_REQUIRED_QUERY_PARAMETER = "pub_id"


class NistAmmtCandidateAcquisitionPolicyError(ValueError):
    """Raised when derived acquisition authority drifts or cannot authenticate."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise NistAmmtCandidateAcquisitionPolicyError(
                f"duplicate JSON key is not allowed: {key}"
            )
        result[key] = value
    return result


def _load_object(path: Path, field: str) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NistAmmtCandidateAcquisitionPolicyError(
            f"{field} must be valid UTF-8 JSON"
        ) from exc
    if not isinstance(value, dict):
        raise NistAmmtCandidateAcquisitionPolicyError(f"{field} root must be an object")
    return value, raw


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise NistAmmtCandidateAcquisitionPolicyError(message)


def authenticate_nist_ammt_candidate_acquisition_policy(
    *,
    repository_root: str | Path,
    mission_path: str | Path,
    expected_mission_sha256: str,
    policy_path: str | Path | None = None,
) -> dict[str, Any]:
    """Authenticate mission and exact derived-candidate acquisition policy without network."""
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
            raise NistAmmtCandidateAcquisitionPolicyError(
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
    _require(policy_sha == POLICY_SHA256, "derived acquisition policy exact bytes drifted")

    pins = mission.get("source_trust_policy_pins")
    _require(isinstance(pins, list), "mission source-trust pins are missing")
    matches = [
        item
        for item in pins
        if isinstance(item, dict) and item.get("policy_id") == POLICY_ID
    ]
    _require(
        len(matches) == 1 and matches[0].get("sha256") == policy_sha,
        "mission derived acquisition policy pin does not match exact policy bytes",
    )

    expected_policy = {
        "schema_version": "1.0",
        "policy_id": POLICY_ID,
        "action_class": ACTION_CLASS,
        "derived_authority": {
            "required_discovery_policy_id": DISCOVERY_POLICY_ID,
            "required_discovery_source_id": DISCOVERY_SOURCE_ID,
            "required_candidate_rank": REQUIRED_CANDIDATE_RANK,
            "required_candidate_host": REQUIRED_CANDIDATE_HOST,
            "candidate_path_prefix": CANDIDATE_PATH_PREFIX,
            "caller_authored_candidate_urls_allowed": False,
            "candidate_may_self_authorize": False,
            "discovery_report_and_manifest_binding_required": True,
        },
        "network": {
            "scheme": "https",
            "candidate_page_allowed_hosts": list(CANDIDATE_PAGE_ALLOWED_HOSTS),
            "full_text_allowed_hosts": list(FULL_TEXT_ALLOWED_HOSTS),
            "max_requests": MAX_REQUESTS,
            "max_candidate_page_bytes": MAX_CANDIDATE_PAGE_BYTES,
            "max_full_text_bytes": MAX_FULL_TEXT_BYTES,
            "max_total_bytes": MAX_TOTAL_BYTES,
            "timeout_seconds": TIMEOUT_SECONDS,
            "unrestricted_search_allowed": False,
            "caller_authored_urls_allowed": False,
            "candidate_page_same_host_redirects_only": True,
            "full_text_link_must_be_derived_from_candidate_page": True,
        },
        "full_text": {
            "required_link_label": FULL_TEXT_LINK_LABEL,
            "allowed_path_prefix": FULL_TEXT_PATH_PREFIX,
            "required_query_parameter": FULL_TEXT_REQUIRED_QUERY_PARAMETER,
            "pdf_magic_required": True,
            "full_text_may_be_row_level_measurement_authority": False,
        },
        "authority": {
            "acquisition_success_establishes_calibration_bridge": False,
            "literature_may_be_row_level_measurement_authority": False,
            "scientific_status_change_authorized_by_acquisition": False,
            "global_evidence_unavailability_may_be_claimed_from_failure": False,
        },
    }
    _require(policy == expected_policy, "derived acquisition policy semantics drifted or widened")

    return {
        "schema_version": "1.0",
        "qualification_status": "exact_nist_ammt_candidate_acquisition_policy_authenticated",
        "policy_id": POLICY_ID,
        "action_class": ACTION_CLASS,
        "mission_sha256": mission_sha,
        "policy_sha256": policy_sha,
        "required_discovery_policy_id": DISCOVERY_POLICY_ID,
        "required_discovery_source_id": DISCOVERY_SOURCE_ID,
        "required_candidate_rank": REQUIRED_CANDIDATE_RANK,
        "required_candidate_host": REQUIRED_CANDIDATE_HOST,
        "candidate_path_prefix": CANDIDATE_PATH_PREFIX,
        "candidate_page_allowed_hosts": list(CANDIDATE_PAGE_ALLOWED_HOSTS),
        "full_text_allowed_hosts": list(FULL_TEXT_ALLOWED_HOSTS),
        "max_requests": MAX_REQUESTS,
        "max_candidate_page_bytes": MAX_CANDIDATE_PAGE_BYTES,
        "max_full_text_bytes": MAX_FULL_TEXT_BYTES,
        "max_total_bytes": MAX_TOTAL_BYTES,
        "timeout_seconds": TIMEOUT_SECONDS,
        "full_text_link_label": FULL_TEXT_LINK_LABEL,
        "full_text_path_prefix": FULL_TEXT_PATH_PREFIX,
        "full_text_required_query_parameter": FULL_TEXT_REQUIRED_QUERY_PARAMETER,
        "network_access_performed": False,
        "caller_authored_url_used": False,
        "candidate_url_derived_from_discovery": False,
        "full_text_url_derived_from_candidate_page": False,
        "scientific_status_changed": False,
    }


__all__ = [
    "ACTION_CLASS",
    "CANDIDATE_PAGE_ALLOWED_HOSTS",
    "CANDIDATE_PATH_PREFIX",
    "DISCOVERY_POLICY_ID",
    "DISCOVERY_SOURCE_ID",
    "FULL_TEXT_ALLOWED_HOSTS",
    "FULL_TEXT_LINK_LABEL",
    "FULL_TEXT_PATH_PREFIX",
    "FULL_TEXT_REQUIRED_QUERY_PARAMETER",
    "MAX_CANDIDATE_PAGE_BYTES",
    "MAX_FULL_TEXT_BYTES",
    "MAX_REQUESTS",
    "MAX_TOTAL_BYTES",
    "NistAmmtCandidateAcquisitionPolicyError",
    "POLICY_ID",
    "POLICY_PATH",
    "POLICY_SHA256",
    "REQUIRED_CANDIDATE_HOST",
    "REQUIRED_CANDIDATE_RANK",
    "TIMEOUT_SECONDS",
    "authenticate_nist_ammt_candidate_acquisition_policy",
]
