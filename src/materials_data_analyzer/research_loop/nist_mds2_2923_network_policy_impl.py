"""Authenticate the exact NIST mds2-2923 production network authority.

This module performs no network access.  It reconstructs a deliberately narrow standing
policy from exact mission-pinned bytes and the repository frontier entry that selected
mds2-2923.  Re-pinning a widened host, product, candidate, or file set is not enough to
bypass the intrinsic production identity checks in this module.
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
POLICY_ID = "nist-mds2-2923-network-acquisition-v1"
ACTION_CLASS = "nist_mds2_2923_geometry_evidence_acquisition"
CANDIDATE_ID = "nist-mds2-2923-cross-sectional-micrographs"
PRODUCT_ID = "mds2-2923"
IDENTIFIER = "10.18434/mds2-2923"
METADATA_ENDPOINT = "https://data.nist.gov/od/id/mds2-2923"
EXPECTED_METADATA_SHA256 = (
    "e10b2afb0e8b5f0d3b0a015bb38ed59a285510e1bb8534fed73f2fd0b7e883b6"
)
FRONTIER_PATH = "configs/research/in625_external_physical_source_frontier.v1.json"
EXPECTED_FILES = {
    "2923_README.txt": {
        "sha256": "8b8fc00ce62915af3e0c91c138dc4d033c031d7758161fb9da0e8702fa621c39",
        "size_bytes": 8372,
    },
    "Master_TrackList_Measurements.xlsx": {
        "sha256": "6cd32669f5c84cdb9e90890ba40ddc5548c85b0dbb95cf038f2f6fc69da67a52",
        "size_bytes": 59141,
    },
}
METADATA_ALLOWED_HOSTS = ("data.nist.gov",)
ARTIFACT_ALLOWED_HOSTS = (
    "data.nist.gov",
    "nist-oar-cache.s3.amazonaws.com",
)
MAX_NETWORK_REQUESTS = 3
MAX_METADATA_BYTES = 32 * 1024 * 1024
MAX_ARTIFACT_BYTES = 8 * 1024 * 1024
MAX_TOTAL_ARTIFACT_BYTES = 1024 * 1024
TIMEOUT_SECONDS = 180


class NistMds22923NetworkPolicyError(ResearchLoopError):
    """Raised when exact NIST mds2-2923 standing authority cannot be proven."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise NistMds22923NetworkPolicyError(
                f"duplicate JSON key is not allowed: {key}"
            )
        result[key] = value
    return result


def _load_json_bytes(raw: bytes, field: str) -> dict[str, Any]:
    try:
        value = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_pairs
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NistMds22923NetworkPolicyError(
            f"{field} must be valid UTF-8 JSON"
        ) from exc
    if not isinstance(value, dict):
        raise NistMds22923NetworkPolicyError(f"{field} root must be an object")
    return value


def _sha256(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise NistMds22923NetworkPolicyError(
            f"{field} must be canonical lowercase SHA-256"
        )
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], field: str) -> None:
    if set(value) != expected:
        raise NistMds22923NetworkPolicyError(f"{field} field set drifted")


def _repo_file(root: Path, path: str | Path, field: str) -> Path:
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise NistMds22923NetworkPolicyError(f"{field} does not resolve") from exc
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise NistMds22923NetworkPolicyError(f"{field} escapes repository root") from exc
    if not resolved.is_file():
        raise NistMds22923NetworkPolicyError(f"{field} must be a file")
    return resolved


def _frontier_candidate(frontier: Mapping[str, Any]) -> Mapping[str, Any]:
    candidates = frontier.get("candidates")
    if not isinstance(candidates, list):
        raise NistMds22923NetworkPolicyError("frontier candidates must be a list")
    matches = [
        item
        for item in candidates
        if isinstance(item, Mapping) and item.get("candidate_id") == CANDIDATE_ID
    ]
    if len(matches) != 1:
        raise NistMds22923NetworkPolicyError(
            "exact NIST mds2-2923 candidate must occur once in frontier"
        )
    return matches[0]


def authenticate_nist_mds2_2923_network_policy(
    *,
    repository_root: str | Path,
    mission_path: str | Path,
    expected_mission_sha256: str,
    policy_path: str | Path,
    frontier_path: str | Path = FRONTIER_PATH,
) -> dict[str, Any]:
    """Authenticate the exact mission-pinned NIST authority without network access."""
    root = Path(repository_root).expanduser().resolve(strict=True)
    mission_file = _repo_file(root, mission_path, "mission_path")
    policy_file = _repo_file(root, policy_path, "policy_path")
    frontier_file = _repo_file(root, frontier_path, "frontier_path")

    mission_bytes = mission_file.read_bytes()
    mission_sha = hashlib.sha256(mission_bytes).hexdigest()
    if mission_sha != _sha256(expected_mission_sha256, "expected_mission_sha256"):
        raise NistMds22923NetworkPolicyError(
            "mission bytes do not match supplied expected mission SHA-256"
        )
    try:
        mission = validate_research_mission(
            _load_json_bytes(mission_bytes, "research mission")
        )
    except ResearchProgramError as exc:
        raise NistMds22923NetworkPolicyError(
            "research mission failed current validation"
        ) from exc
    if mission.get("schema_version") != "1.2":
        raise NistMds22923NetworkPolicyError(
            "NIST standing network authority requires mission schema_version 1.2"
        )
    if (
        mission.get("autonomy_policy", {}).get("network_evidence_search")
        != "explicit_authorization"
    ):
        raise NistMds22923NetworkPolicyError(
            "mission does not permit explicit-authorized network evidence search"
        )

    policy_bytes = policy_file.read_bytes()
    policy_sha = hashlib.sha256(policy_bytes).hexdigest()
    pins = mission.get("source_trust_policy_pins")
    matches = (
        [
            item
            for item in pins
            if isinstance(item, Mapping) and item.get("policy_id") == POLICY_ID
        ]
        if isinstance(pins, list)
        else []
    )
    if len(matches) != 1 or matches[0].get("sha256") != policy_sha:
        raise NistMds22923NetworkPolicyError(
            "exact NIST network policy bytes do not match one mission source-trust pin"
        )

    policy = _load_json_bytes(policy_bytes, "NIST mds2-2923 network policy")
    _exact_keys(
        policy,
        {
            "schema_version",
            "policy_id",
            "action_class",
            "candidate_id",
            "source_identity",
            "network",
            "expected_nerdm_metadata_sha256",
            "files",
            "scientific_boundaries",
        },
        "NIST network policy",
    )
    if policy.get("schema_version") != SCHEMA_VERSION:
        raise NistMds22923NetworkPolicyError("unsupported NIST policy schema")
    if policy.get("policy_id") != POLICY_ID:
        raise NistMds22923NetworkPolicyError("NIST policy identity drifted")
    if policy.get("action_class") != ACTION_CLASS:
        raise NistMds22923NetworkPolicyError("NIST action class drifted")
    if policy.get("candidate_id") != CANDIDATE_ID:
        raise NistMds22923NetworkPolicyError("NIST candidate identity drifted")

    expected_identity = {
        "authority": "NIST Public Data Repository / AM-Bench",
        "identifier": IDENTIFIER,
        "product_id": PRODUCT_ID,
        "metadata_endpoint": METADATA_ENDPOINT,
    }
    if policy.get("source_identity") != expected_identity:
        raise NistMds22923NetworkPolicyError("NIST source identity drifted")

    expected_network = {
        "scheme": "https",
        "metadata_allowed_hosts": list(METADATA_ALLOWED_HOSTS),
        "artifact_allowed_hosts": list(ARTIFACT_ALLOWED_HOSTS),
        "allowed_ports": [443],
        "max_network_requests": MAX_NETWORK_REQUESTS,
        "timeout_seconds": TIMEOUT_SECONDS,
        "max_metadata_bytes": MAX_METADATA_BYTES,
        "max_artifact_bytes": MAX_ARTIFACT_BYTES,
        "max_total_artifact_bytes": MAX_TOTAL_ARTIFACT_BYTES,
        "unrestricted_search": False,
        "arbitrary_url_fetch": False,
    }
    if policy.get("network") != expected_network:
        raise NistMds22923NetworkPolicyError(
            "NIST network authority widened or drifted"
        )
    if policy.get("expected_nerdm_metadata_sha256") != EXPECTED_METADATA_SHA256:
        raise NistMds22923NetworkPolicyError("NIST metadata identity drifted")

    raw_files = policy.get("files")
    if not isinstance(raw_files, list) or len(raw_files) != len(EXPECTED_FILES):
        raise NistMds22923NetworkPolicyError("NIST policy exact file set drifted")
    observed_files: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(raw_files):
        if not isinstance(item, Mapping):
            raise NistMds22923NetworkPolicyError(
                f"NIST policy files[{index}] must be an object"
            )
        _exact_keys(item, {"path", "sha256", "size_bytes"}, f"files[{index}]")
        path = item.get("path")
        if not isinstance(path, str) or not path or path != path.strip():
            raise NistMds22923NetworkPolicyError("NIST file path must be trimmed text")
        if path in observed_files:
            raise NistMds22923NetworkPolicyError("NIST policy repeats file identity")
        observed_files[path] = dict(item)
    if observed_files != {
        path: {"path": path, **rule} for path, rule in EXPECTED_FILES.items()
    }:
        raise NistMds22923NetworkPolicyError("NIST file bytes/size identity drifted")

    expected_boundaries = {
        "material": "IN625",
        "responses": ["melt_pool_width", "melt_pool_depth"],
        "data_sheet_row_level_authority": True,
        "summary_is_derived_view": True,
        "machine_setting_power_is_calibrated_actual_power": False,
        "cross_machine_pooling_authorized": False,
        "issue_76_automatic_promotion_authorized": False,
        "paper_and_other_source_lanes_remain_allowed": True,
    }
    if policy.get("scientific_boundaries") != expected_boundaries:
        raise NistMds22923NetworkPolicyError(
            "NIST scientific authority widened or drifted"
        )

    frontier_bytes = frontier_file.read_bytes()
    frontier = _load_json_bytes(frontier_bytes, "IN625 physical source frontier")
    candidate = _frontier_candidate(frontier)
    if candidate.get("authority") != expected_identity["authority"]:
        raise NistMds22923NetworkPolicyError("frontier NIST authority drifted")
    if candidate.get("identifier") != IDENTIFIER:
        raise NistMds22923NetworkPolicyError("frontier NIST identifier drifted")
    if candidate.get("material_states") != ["bare_plate_single_track"]:
        raise NistMds22923NetworkPolicyError("frontier NIST material state drifted")
    if candidate.get("responses") != ["melt_pool_width", "melt_pool_depth"]:
        raise NistMds22923NetworkPolicyError("frontier NIST response semantics drifted")
    plan = candidate.get("automatic_acquisition_plan")
    if plan != {
        "adapter": "nist_pdr",
        "product_id": PRODUCT_ID,
        "filepaths": list(EXPECTED_FILES),
        "approval_mode": "automatic_when_public_checksum_bound_policy_passes",
        "human_review_is_exception_only": True,
    }:
        raise NistMds22923NetworkPolicyError(
            "frontier automatic acquisition plan drifted"
        )

    return {
        "schema_version": QUALIFICATION_SCHEMA_VERSION,
        "qualification_status": "exact_nist_mds2_2923_network_policy_authenticated",
        "mission_sha256": mission_sha,
        "policy_id": POLICY_ID,
        "policy_sha256": policy_sha,
        "action_class": ACTION_CLASS,
        "candidate_id": CANDIDATE_ID,
        "product_id": PRODUCT_ID,
        "identifier": IDENTIFIER,
        "metadata_endpoint": METADATA_ENDPOINT,
        "expected_nerdm_metadata_sha256": EXPECTED_METADATA_SHA256,
        "frontier_path": str(frontier_file),
        "frontier_sha256": hashlib.sha256(frontier_bytes).hexdigest(),
        "expected_files": observed_files,
        "metadata_allowed_hosts": list(METADATA_ALLOWED_HOSTS),
        "artifact_allowed_hosts": list(ARTIFACT_ALLOWED_HOSTS),
        "maximum_network_requests": MAX_NETWORK_REQUESTS,
        "maximum_metadata_bytes": MAX_METADATA_BYTES,
        "maximum_artifact_bytes": MAX_ARTIFACT_BYTES,
        "maximum_total_artifact_bytes": MAX_TOTAL_ARTIFACT_BYTES,
        "timeout_seconds": TIMEOUT_SECONDS,
        "unrestricted_search_authorized": False,
        "arbitrary_url_fetch_authorized": False,
        "network_access_performed": False,
        "scientific_status_changed": False,
        "issue_76_automatic_promotion_authorized": False,
        "paper_and_other_source_lanes_remain_allowed": True,
    }


__all__ = [
    "ACTION_CLASS",
    "ARTIFACT_ALLOWED_HOSTS",
    "CANDIDATE_ID",
    "EXPECTED_FILES",
    "EXPECTED_METADATA_SHA256",
    "METADATA_ALLOWED_HOSTS",
    "NistMds22923NetworkPolicyError",
    "POLICY_ID",
    "PRODUCT_ID",
    "authenticate_nist_mds2_2923_network_policy",
]
