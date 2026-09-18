"""Public NIST mds2-2923 network-policy API with authenticated qualification output.

The audited policy implementation is preserved byte-for-byte in the sibling implementation
module.  This wrapper adds a canonical self-hash to the no-network qualification so persisted
qualification bytes cannot be changed independently of the live verifier.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from . import nist_mds2_2923_network_policy_impl as _impl

SCHEMA_VERSION = _impl.SCHEMA_VERSION
QUALIFICATION_SCHEMA_VERSION = _impl.QUALIFICATION_SCHEMA_VERSION
POLICY_ID = _impl.POLICY_ID
ACTION_CLASS = _impl.ACTION_CLASS
CANDIDATE_ID = _impl.CANDIDATE_ID
PRODUCT_ID = _impl.PRODUCT_ID
IDENTIFIER = _impl.IDENTIFIER
METADATA_ENDPOINT = _impl.METADATA_ENDPOINT
EXPECTED_METADATA_SHA256 = _impl.EXPECTED_METADATA_SHA256
FRONTIER_PATH = _impl.FRONTIER_PATH
EXPECTED_FILES = _impl.EXPECTED_FILES
METADATA_ALLOWED_HOSTS = _impl.METADATA_ALLOWED_HOSTS
ARTIFACT_ALLOWED_HOSTS = _impl.ARTIFACT_ALLOWED_HOSTS
MAX_NETWORK_REQUESTS = _impl.MAX_NETWORK_REQUESTS
MAX_METADATA_BYTES = _impl.MAX_METADATA_BYTES
MAX_ARTIFACT_BYTES = _impl.MAX_ARTIFACT_BYTES
MAX_TOTAL_ARTIFACT_BYTES = _impl.MAX_TOTAL_ARTIFACT_BYTES
TIMEOUT_SECONDS = _impl.TIMEOUT_SECONDS
NistMds22923NetworkPolicyError = _impl.NistMds22923NetworkPolicyError


def _canonical_sha(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def authenticate_nist_mds2_2923_network_policy(
    *,
    repository_root: str | Path,
    mission_path: str | Path,
    expected_mission_sha256: str,
    policy_path: str | Path,
    frontier_path: str | Path = FRONTIER_PATH,
) -> dict[str, Any]:
    """Authenticate exact policy bytes and self-hash the resulting qualification."""
    qualification = _impl.authenticate_nist_mds2_2923_network_policy(
        repository_root=repository_root,
        mission_path=mission_path,
        expected_mission_sha256=expected_mission_sha256,
        policy_path=policy_path,
        frontier_path=frontier_path,
    )
    if "qualification_sha256" in qualification:
        raise NistMds22923NetworkPolicyError(
            "policy implementation unexpectedly supplied qualification_sha256"
        )
    qualification["qualification_sha256"] = _canonical_sha(qualification)
    return qualification


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
