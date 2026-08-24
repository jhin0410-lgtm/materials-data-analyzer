"""Execute the exact mission-qualified NIST mds2-2923 production acquisition.

The generic public-acquisition machinery remains reusable infrastructure, but this production
adapter exposes only the already-selected mds2-2923 candidate and its exact metadata/README/
workbook bytes.  It therefore cannot turn the autonomous production driver into a generic URL
or repository downloader.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .nist_mds2_2923_network_policy import (
    ACTION_CLASS,
    ARTIFACT_ALLOWED_HOSTS,
    CANDIDATE_ID,
    EXPECTED_FILES,
    EXPECTED_METADATA_SHA256,
    METADATA_ALLOWED_HOSTS,
    METADATA_ENDPOINT,
    MAX_ARTIFACT_BYTES,
    MAX_METADATA_BYTES,
    MAX_NETWORK_REQUESTS,
    MAX_TOTAL_ARTIFACT_BYTES,
    POLICY_ID,
    PRODUCT_ID,
    TIMEOUT_SECONDS,
)
from .nist_pdr_acquisition import discover_nist_pdr_candidates
from .public_data_acquisition import (
    FetchResult,
    PublicAcquisitionError,
    PublicAcquisitionTransportError,
    acquire_public_artifact,
    fetch_https_bytes,
)

AUTHORIZATION_SCHEMA_VERSION = "1.0"
RECEIPT_SCHEMA_VERSION = "1.0"


class NistMds22923ProductionAcquisitionError(ValueError):
    """Raised when exact NIST production acquisition violates its finite authority."""


class NistMds22923ProductionTransportError(NistMds22923ProductionAcquisitionError):
    """Raised when exact NIST acquisition is blocked only by network delivery."""


def _canonical_sha(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise NistMds22923ProductionAcquisitionError(message)


def build_nist_mds2_2923_network_authorization(
    qualification: Mapping[str, Any],
) -> dict[str, Any]:
    """Turn a no-network policy qualification into one finite acquisition authorization."""
    _require(
        qualification.get("qualification_status")
        == "exact_nist_mds2_2923_network_policy_authenticated",
        "NIST network policy qualification status is not executable",
    )
    _require(qualification.get("policy_id") == POLICY_ID, "NIST policy identity drifted")
    _require(
        qualification.get("action_class") == ACTION_CLASS,
        "NIST action class drifted",
    )
    _require(
        qualification.get("candidate_id") == CANDIDATE_ID,
        "NIST candidate identity drifted",
    )
    _require(
        qualification.get("product_id") == PRODUCT_ID,
        "NIST product identity drifted",
    )
    _require(
        qualification.get("metadata_endpoint") == METADATA_ENDPOINT,
        "NIST metadata endpoint drifted",
    )
    _require(
        qualification.get("expected_nerdm_metadata_sha256")
        == EXPECTED_METADATA_SHA256,
        "NIST metadata digest drifted",
    )
    _require(
        qualification.get("expected_files")
        == {path: {"path": path, **rule} for path, rule in EXPECTED_FILES.items()},
        "NIST exact file identity drifted",
    )
    _require(
        qualification.get("metadata_allowed_hosts") == list(METADATA_ALLOWED_HOSTS),
        "NIST metadata host authority drifted",
    )
    _require(
        qualification.get("artifact_allowed_hosts") == list(ARTIFACT_ALLOWED_HOSTS),
        "NIST artifact host authority drifted",
    )
    _require(
        qualification.get("maximum_network_requests") == MAX_NETWORK_REQUESTS,
        "NIST request budget drifted",
    )
    _require(
        qualification.get("maximum_metadata_bytes") == MAX_METADATA_BYTES,
        "NIST metadata byte budget drifted",
    )
    _require(
        qualification.get("maximum_artifact_bytes") == MAX_ARTIFACT_BYTES,
        "NIST artifact byte budget drifted",
    )
    _require(
        qualification.get("maximum_total_artifact_bytes")
        == MAX_TOTAL_ARTIFACT_BYTES,
        "NIST total byte budget drifted",
    )
    _require(
        qualification.get("timeout_seconds") == TIMEOUT_SECONDS,
        "NIST timeout budget drifted",
    )
    _require(
        qualification.get("unrestricted_search_authorized") is False
        and qualification.get("arbitrary_url_fetch_authorized") is False,
        "NIST qualification widened network authority",
    )
    _require(
        qualification.get("network_access_performed") is False,
        "NIST qualification claimed prior network access",
    )

    authorization: dict[str, Any] = {
        "schema_version": AUTHORIZATION_SCHEMA_VERSION,
        "authorization_status": "authorized_exact_nist_mds2_2923_acquisition",
        "mission_sha256": qualification.get("mission_sha256"),
        "policy_id": POLICY_ID,
        "policy_sha256": qualification.get("policy_sha256"),
        "action_class": ACTION_CLASS,
        "candidate_id": CANDIDATE_ID,
        "product_id": PRODUCT_ID,
        "metadata_endpoint": METADATA_ENDPOINT,
        "expected_nerdm_metadata_sha256": EXPECTED_METADATA_SHA256,
        "expected_files": qualification.get("expected_files"),
        "metadata_allowed_hosts": list(METADATA_ALLOWED_HOSTS),
        "artifact_allowed_hosts": list(ARTIFACT_ALLOWED_HOSTS),
        "maximum_network_requests": MAX_NETWORK_REQUESTS,
        "maximum_metadata_bytes": MAX_METADATA_BYTES,
        "maximum_artifact_bytes": MAX_ARTIFACT_BYTES,
        "maximum_total_artifact_bytes": MAX_TOTAL_ARTIFACT_BYTES,
        "timeout_seconds": TIMEOUT_SECONDS,
        "caller_authored_url_used": False,
        "caller_authored_file_queue_used": False,
        "unrestricted_search_authorized": False,
        "arbitrary_url_fetch_authorized": False,
        "network_access_performed": False,
        "scientific_status_changed": False,
    }
    authorization["authorization_sha256"] = _canonical_sha(authorization)
    return authorization


def _validate_authorization(authorization: Mapping[str, Any]) -> None:
    supplied_sha = authorization.get("authorization_sha256")
    if not isinstance(supplied_sha, str):
        raise NistMds22923ProductionAcquisitionError(
            "NIST authorization omitted authorization_sha256"
        )
    unsigned = dict(authorization)
    unsigned.pop("authorization_sha256", None)
    _require(
        supplied_sha == _canonical_sha(unsigned),
        "NIST authorization self-hash mismatch",
    )
    _require(
        authorization.get("authorization_status")
        == "authorized_exact_nist_mds2_2923_acquisition",
        "NIST authorization status is not executable",
    )
    _require(authorization.get("policy_id") == POLICY_ID, "NIST policy drifted")
    _require(
        authorization.get("action_class") == ACTION_CLASS,
        "NIST action drifted",
    )
    _require(
        authorization.get("candidate_id") == CANDIDATE_ID,
        "NIST candidate drifted",
    )
    _require(authorization.get("product_id") == PRODUCT_ID, "NIST product drifted")
    _require(
        authorization.get("metadata_endpoint") == METADATA_ENDPOINT,
        "NIST metadata endpoint drifted",
    )
    _require(
        authorization.get("expected_nerdm_metadata_sha256")
        == EXPECTED_METADATA_SHA256,
        "NIST metadata digest drifted",
    )
    _require(
        authorization.get("expected_files")
        == {path: {"path": path, **rule} for path, rule in EXPECTED_FILES.items()},
        "NIST file identity drifted",
    )
    _require(
        authorization.get("metadata_allowed_hosts") == list(METADATA_ALLOWED_HOSTS)
        and authorization.get("artifact_allowed_hosts") == list(ARTIFACT_ALLOWED_HOSTS),
        "NIST host authority drifted",
    )
    _require(
        authorization.get("maximum_network_requests") == MAX_NETWORK_REQUESTS
        and authorization.get("maximum_metadata_bytes") == MAX_METADATA_BYTES
        and authorization.get("maximum_artifact_bytes") == MAX_ARTIFACT_BYTES
        and authorization.get("maximum_total_artifact_bytes")
        == MAX_TOTAL_ARTIFACT_BYTES
        and authorization.get("timeout_seconds") == TIMEOUT_SECONDS,
        "NIST execution budget drifted",
    )
    _require(
        authorization.get("caller_authored_url_used") is False
        and authorization.get("caller_authored_file_queue_used") is False
        and authorization.get("unrestricted_search_authorized") is False
        and authorization.get("arbitrary_url_fetch_authorized") is False,
        "NIST authorization widened caller/network authority",
    )
    _require(
        authorization.get("network_access_performed") is False,
        "NIST authorization must be pre-network",
    )


def execute_authorized_nist_mds2_2923_acquisition(
    *,
    authorization: Mapping[str, Any],
    output_root: str | Path,
    fetcher=fetch_https_bytes,
) -> dict[str, Any]:
    """Fetch exact NERDm metadata and the two exact NIST source files."""
    _validate_authorization(authorization)
    root = Path(output_root).expanduser().resolve(strict=False)
    root.mkdir(parents=True, exist_ok=True)
    if any(root.iterdir()):
        raise NistMds22923ProductionAcquisitionError(
            "NIST production acquisition output must be empty"
        )

    try:
        metadata_result = fetcher(
            METADATA_ENDPOINT,
            allowed_hosts=list(METADATA_ALLOWED_HOSTS),
            max_bytes=MAX_METADATA_BYTES,
            timeout_seconds=TIMEOUT_SECONDS,
            headers={"Accept": "application/json"},
        )
    except PublicAcquisitionTransportError as exc:
        raise NistMds22923ProductionTransportError(
            f"NIST metadata transport failed: {exc}"
        ) from exc
    except PublicAcquisitionError as exc:
        raise NistMds22923ProductionAcquisitionError(
            f"NIST metadata acquisition integrity failed: {exc}"
        ) from exc
    if not isinstance(metadata_result, FetchResult):
        raise NistMds22923ProductionAcquisitionError(
            "NIST metadata fetcher must return FetchResult"
        )
    metadata_bytes = metadata_result.body
    metadata_sha = hashlib.sha256(metadata_bytes).hexdigest()
    _require(
        metadata_sha == EXPECTED_METADATA_SHA256,
        "live NIST NERDm metadata changed from mission-qualified exact bytes",
    )
    metadata_path = root / "nerdm-metadata.json"
    metadata_path.write_bytes(metadata_bytes)

    try:
        candidates = discover_nist_pdr_candidates(
            metadata_bytes=metadata_bytes,
            product_id=PRODUCT_ID,
            filepaths=list(EXPECTED_FILES),
            evidence_role="response_compatible_geometry_evidence",
        )
    except Exception as exc:
        raise NistMds22923ProductionAcquisitionError(
            f"exact NIST candidate discovery failed: {exc}"
        ) from exc
    _require(
        len(candidates) == len(EXPECTED_FILES),
        "NIST metadata did not resolve the exact two-file production set",
    )
    by_path = {candidate["artifact_path"]: candidate for candidate in candidates}
    _require(set(by_path) == set(EXPECTED_FILES), "NIST file set drifted")

    expected_total = 0
    for path, rule in EXPECTED_FILES.items():
        candidate = by_path[path]
        _require(
            candidate["expected_sha256"] == rule["sha256"],
            f"NIST authoritative checksum changed for {path}",
        )
        _require(
            candidate["expected_size_bytes"] == rule["size_bytes"],
            f"NIST authoritative size changed for {path}",
        )
        _require(
            candidate["metadata_sha256"] == EXPECTED_METADATA_SHA256,
            f"NIST metadata binding changed for {path}",
        )
        _require(
            candidate["allowed_hosts"] == list(ARTIFACT_ALLOWED_HOSTS),
            f"NIST artifact host authority changed for {path}",
        )
        expected_total += int(candidate["expected_size_bytes"])
    _require(
        expected_total <= MAX_TOTAL_ARTIFACT_BYTES,
        "NIST exact file set exceeds production byte budget",
    )

    receipts: list[dict[str, Any]] = []
    artifact_paths: dict[str, str] = {}
    for index, path in enumerate(EXPECTED_FILES):
        candidate = by_path[path]
        package_dir = root / f"artifact-{index + 1:02d}"
        try:
            receipt = acquire_public_artifact(
                candidate=candidate,
                metadata_bytes=metadata_bytes,
                output_dir=package_dir,
                fetcher=fetcher,
                timeout_seconds=TIMEOUT_SECONDS,
                max_auto_bytes=MAX_ARTIFACT_BYTES,
            )
        except PublicAcquisitionTransportError as exc:
            raise NistMds22923ProductionTransportError(
                f"NIST exact artifact transport failed for {path}: {exc}"
            ) from exc
        except PublicAcquisitionError as exc:
            raise NistMds22923ProductionAcquisitionError(
                f"NIST exact artifact acquisition failed for {path}: {exc}"
            ) from exc
        artifact_path = package_dir / path
        _require(artifact_path.is_file(), f"NIST acquired artifact missing: {path}")
        body = artifact_path.read_bytes()
        _require(
            hashlib.sha256(body).hexdigest() == EXPECTED_FILES[path]["sha256"],
            f"NIST persisted artifact checksum mismatch: {path}",
        )
        _require(
            len(body) == EXPECTED_FILES[path]["size_bytes"],
            f"NIST persisted artifact size mismatch: {path}",
        )
        receipts.append({**receipt, "package_directory": str(package_dir)})
        artifact_paths[path] = str(artifact_path)

    report: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "acquisition_status": "exact_nist_mds2_2923_source_files_acquired",
        "authorization_sha256": authorization["authorization_sha256"],
        "policy_id": POLICY_ID,
        "action_class": ACTION_CLASS,
        "candidate_id": CANDIDATE_ID,
        "product_id": PRODUCT_ID,
        "metadata_endpoint": METADATA_ENDPOINT,
        "metadata_path": str(metadata_path),
        "metadata_sha256": metadata_sha,
        "artifact_paths": artifact_paths,
        "receipts": receipts,
        "network_requests_performed": 1 + len(receipts),
        "network_request_budget": MAX_NETWORK_REQUESTS,
        "artifact_bytes_acquired": sum(
            receipt["artifact_size_bytes"] for receipt in receipts
        ),
        "caller_authored_url_used": False,
        "caller_authored_file_queue_used": False,
        "unrestricted_network_search_performed": False,
        "arbitrary_url_fetch_performed": False,
        "all_acquisition_provenance_authenticated": all(
            receipt["recorded_acquisition_provenance_authenticated"] is True
            for receipt in receipts
        ),
        "requires_scientific_intake": True,
        "scientific_status_changed": False,
    }
    _require(
        report["network_requests_performed"] <= MAX_NETWORK_REQUESTS,
        "NIST request budget exceeded",
    )
    report["receipt_sha256"] = _canonical_sha(report)
    return report


__all__ = [
    "NistMds22923ProductionAcquisitionError",
    "NistMds22923ProductionTransportError",
    "build_nist_mds2_2923_network_authorization",
    "execute_authorized_nist_mds2_2923_acquisition",
]
