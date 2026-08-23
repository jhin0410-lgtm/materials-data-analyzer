"""Independently verify that a derived acquisition request descends from exact NIST discovery lineage."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping
from urllib.parse import urlparse

from .nist_ammt_candidate_acquisition_policy import (
    DISCOVERY_POLICY_ID,
    DISCOVERY_POLICY_SHA256,
    DISCOVERY_SOURCE_ID,
    DISCOVERY_SOURCE_URL,
    REQUIRED_CANDIDATE_HOST,
    REQUIRED_CANDIDATE_RANK,
)


class NistAmmtCandidateDiscoveryLineageError(ValueError):
    """Raised when a discovery report cannot support derived acquisition authority."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise NistAmmtCandidateDiscoveryLineageError(message)


def _canonical_sha(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def verify_discovery_lineage(
    *,
    qualification: Mapping[str, Any],
    discovery_report: Mapping[str, Any],
) -> dict[str, Any]:
    """Verify exact policy/source lineage and rank-1 candidate identity without network access."""
    _require(
        qualification.get("qualification_status")
        == "exact_nist_ammt_candidate_acquisition_policy_authenticated",
        "derived acquisition policy is not authenticated",
    )
    _require(
        qualification.get("required_discovery_policy_id") == DISCOVERY_POLICY_ID
        and qualification.get("required_discovery_policy_sha256")
        == DISCOVERY_POLICY_SHA256
        and qualification.get("required_discovery_source_id") == DISCOVERY_SOURCE_ID
        and qualification.get("required_discovery_source_url") == DISCOVERY_SOURCE_URL,
        "derived acquisition qualification discovery lineage drifted",
    )

    digest = discovery_report.get("report_sha256_without_self_field")
    _require(isinstance(digest, str) and len(digest) == 64, "discovery report SHA is missing")
    unsigned = dict(discovery_report)
    unsigned.pop("report_sha256_without_self_field", None)
    _require(_canonical_sha(unsigned) == digest, "discovery report self binding is invalid")
    _require(
        discovery_report.get("policy_id") == DISCOVERY_POLICY_ID
        and discovery_report.get("policy_sha256") == DISCOVERY_POLICY_SHA256,
        "discovery report did not originate under the exact mission-pinned discovery policy",
    )
    source = discovery_report.get("source_index")
    _require(isinstance(source, Mapping), "discovery source-index receipt is missing")
    _require(
        source.get("source_id") == DISCOVERY_SOURCE_ID
        and source.get("requested_url") == DISCOVERY_SOURCE_URL
        and source.get("final_url") == DISCOVERY_SOURCE_URL,
        "discovery source-index identity/URL lineage drifted",
    )
    source_sha = source.get("source_sha256")
    _require(
        isinstance(source_sha, str)
        and len(source_sha) == 64
        and all(char in "0123456789abcdef" for char in source_sha),
        "discovery source-index SHA is invalid",
    )
    _require(
        discovery_report.get("candidate_links_followed") == 0
        and discovery_report.get("candidate_urls_gain_acquisition_authority") is False
        and discovery_report.get("caller_authored_url_used") is False
        and discovery_report.get("unrestricted_search_performed") is False,
        "discovery report widened authority before derived acquisition",
    )
    candidates = discovery_report.get("candidates")
    _require(isinstance(candidates, list), "discovery candidates are missing")
    selected = [
        item
        for item in candidates
        if isinstance(item, Mapping) and item.get("rank") == REQUIRED_CANDIDATE_RANK
    ]
    _require(len(selected) == 1, "exactly one rank-1 discovery candidate is required")
    candidate = selected[0]
    url = candidate.get("url")
    _require(isinstance(url, str), "rank-1 discovery candidate URL is missing")
    parsed = urlparse(url)
    _require(
        parsed.scheme.lower() == "https"
        and (parsed.hostname or "").lower() == REQUIRED_CANDIDATE_HOST,
        "rank-1 discovery candidate left exact NIST host lineage",
    )
    expected_id = "nist-ammt-index-" + hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    _require(
        candidate.get("candidate_id") == expected_id,
        "rank-1 discovery candidate ID is not derived from its exact URL",
    )
    _require(
        candidate.get("discovered_from_source_id") == DISCOVERY_SOURCE_ID
        and candidate.get("candidate_url_followed") is False
        and candidate.get("acquisition_authorized") is False
        and candidate.get("row_level_measurement_authority") is False,
        "rank-1 discovery candidate authority/provenance drifted",
    )
    receipt: dict[str, Any] = {
        "schema_version": "1.0",
        "verification_status": "exact_discovery_policy_source_and_rank1_lineage_verified",
        "discovery_report_sha256": digest,
        "discovery_policy_id": DISCOVERY_POLICY_ID,
        "discovery_policy_sha256": DISCOVERY_POLICY_SHA256,
        "source_index_id": DISCOVERY_SOURCE_ID,
        "source_index_url": DISCOVERY_SOURCE_URL,
        "source_index_sha256": source_sha,
        "candidate_id": expected_id,
        "candidate_rank": REQUIRED_CANDIDATE_RANK,
        "candidate_url": url,
        "network_access_performed": False,
        "acquisition_authority_granted": False,
        "scientific_status_changed": False,
    }
    receipt["verification_sha256_without_self_field"] = _canonical_sha(receipt)
    return receipt


__all__ = [
    "NistAmmtCandidateDiscoveryLineageError",
    "verify_discovery_lineage",
]
