"""Fresh-review round 13: exact JSON type fidelity for retained NIST authority.

Canonical self-hashes authenticate bytes only after the verifier decides which semantic values are
allowed. Python equality is too permissive for that decision because ``3 == 3.0`` and
``False == 0``. This additive gate compares authority-bearing NIST budgets, routes, file
contracts, cycle indices, and scientific row-count identities through canonical JSON bytes so an
equal-valued type substitution cannot satisfy the public verifier.
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from . import autonomous_production_merge_gate_hardening as _merge_gate
from .autonomous_production_authority_binding_hardening import (
    EXPECTED_MISSION_SHA256,
    EXPECTED_NIST_POLICY_SHA256,
)
from .nist_mds2_2923_network_policy import (
    ACTION_CLASS,
    ARTIFACT_ALLOWED_HOSTS,
    CANDIDATE_ID,
    EXPECTED_FILES,
    EXPECTED_METADATA_SHA256,
    MAX_ARTIFACT_BYTES,
    MAX_METADATA_BYTES,
    MAX_NETWORK_REQUESTS,
    MAX_TOTAL_ARTIFACT_BYTES,
    METADATA_ALLOWED_HOSTS,
    METADATA_ENDPOINT,
    POLICY_ID,
    PRODUCT_ID,
    TIMEOUT_SECONDS,
)

AutonomousProductionFreshReviewRound13Error = (
    _merge_gate.AutonomousProductionMergeGateHardeningError
)

_EXPECTED_FILES_WITH_PATH = {
    path: {"path": path, **rule} for path, rule in EXPECTED_FILES.items()
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AutonomousProductionFreshReviewRound13Error(message)


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _require_json_equal(observed: object, expected: object, *, label: str) -> None:
    try:
        observed_bytes = _canonical_bytes(observed)
        expected_bytes = _canonical_bytes(expected)
    except (TypeError, ValueError) as exc:
        raise AutonomousProductionFreshReviewRound13Error(
            f"{label} must be canonical JSON"
        ) from exc
    _require(observed_bytes == expected_bytes, f"{label} JSON type/value drifted")


def _verify_finite_network_contract(value: Mapping[str, Any], *, label: str) -> None:
    expected = {
        "metadata_endpoint": METADATA_ENDPOINT,
        "expected_nerdm_metadata_sha256": EXPECTED_METADATA_SHA256,
        "expected_files": _EXPECTED_FILES_WITH_PATH,
        "metadata_allowed_hosts": list(METADATA_ALLOWED_HOSTS),
        "artifact_allowed_hosts": list(ARTIFACT_ALLOWED_HOSTS),
        "maximum_network_requests": MAX_NETWORK_REQUESTS,
        "maximum_metadata_bytes": MAX_METADATA_BYTES,
        "maximum_artifact_bytes": MAX_ARTIFACT_BYTES,
        "maximum_total_artifact_bytes": MAX_TOTAL_ARTIFACT_BYTES,
        "timeout_seconds": TIMEOUT_SECONDS,
    }
    for field, expected_value in expected.items():
        _require_json_equal(value.get(field), expected_value, label=f"{label} {field}")


def _verify_authority_documents(root: Path) -> None:
    qualification = _merge_gate._load(root, "nist-network-policy-qualification.json")
    authorization = _merge_gate._load(root, "nist-network-authorization.json")

    qualification_identity = {
        "qualification_status": "exact_nist_mds2_2923_network_policy_authenticated",
        "mission_sha256": EXPECTED_MISSION_SHA256,
        "policy_id": POLICY_ID,
        "policy_sha256": EXPECTED_NIST_POLICY_SHA256,
        "action_class": ACTION_CLASS,
        "candidate_id": CANDIDATE_ID,
        "product_id": PRODUCT_ID,
        "network_access_performed": False,
        "unrestricted_search_authorized": False,
        "arbitrary_url_fetch_authorized": False,
        "scientific_status_changed": False,
    }
    authorization_identity = {
        "authorization_status": "authorized_exact_nist_mds2_2923_acquisition",
        "mission_sha256": EXPECTED_MISSION_SHA256,
        "policy_id": POLICY_ID,
        "policy_sha256": EXPECTED_NIST_POLICY_SHA256,
        "action_class": ACTION_CLASS,
        "candidate_id": CANDIDATE_ID,
        "product_id": PRODUCT_ID,
        "network_access_performed": False,
        "unrestricted_search_authorized": False,
        "arbitrary_url_fetch_authorized": False,
        "caller_authored_url_used": False,
        "caller_authored_file_queue_used": False,
        "scientific_status_changed": False,
    }
    for field, expected in qualification_identity.items():
        _require_json_equal(
            qualification.get(field), expected, label=f"NIST qualification {field}"
        )
    for field, expected in authorization_identity.items():
        _require_json_equal(
            authorization.get(field), expected, label=f"NIST authorization {field}"
        )
    _verify_finite_network_contract(qualification, label="NIST qualification")
    _verify_finite_network_contract(authorization, label="NIST authorization")


def _verify_manifest_types(manifest: Mapping[str, Any]) -> None:
    cycles = manifest.get("cycles")
    _require(isinstance(cycles, list) and cycles, "autonomous production cycles must be a non-empty list")
    for expected_index, cycle in enumerate(cycles, start=1):
        _require(isinstance(cycle, Mapping), f"cycle {expected_index} must be an object")
        _require_json_equal(
            cycle.get("cycle_index"),
            expected_index,
            label=f"cycle {expected_index} index",
        )

    exact_counts = {
        "measurement_row_count": 200289,
        "complete_numeric_measurement_row_count": 200288,
        "incomplete_numeric_measurement_row_count": 1,
        "parallel_test_block_count": 19,
    }
    for field, expected in exact_counts.items():
        _require_json_equal(manifest.get(field), expected, label=f"manifest {field}")

    optional_zero_counts = (
        "directly_comparable_mds2_rows",
        "issue_76_exact_target_cells_satisfied",
    )
    for field in optional_zero_counts:
        if field in manifest:
            _require_json_equal(manifest.get(field), 0, label=f"manifest {field}")


def verify_fresh_review_round13_boundaries(output_root: str | Path) -> None:
    """Reject equal-valued JSON type substitutions in retained NIST authority evidence."""
    root = Path(output_root).expanduser().resolve(strict=True)
    manifest = _merge_gate._load(root, "autonomous-production-manifest.json")
    _verify_authority_documents(root)
    _verify_manifest_types(manifest)


__all__ = [
    "AutonomousProductionFreshReviewRound13Error",
    "verify_fresh_review_round13_boundaries",
]
