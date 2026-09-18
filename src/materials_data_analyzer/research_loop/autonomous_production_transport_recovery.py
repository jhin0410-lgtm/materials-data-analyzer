"""Top-level fail-closed recovery for transient autonomous-production transport failures.

The audited reference-chain production path remains the primary implementation.  This module
only intercepts the narrow typed NIST mds2-2923 transport failure emitted after source policy
and authorization have already authenticated.  It converts that operational outage into a
self-hashed bounded stop while preserving the last verified scientific state.

Integrity, checksum, size, host, provenance, policy, parsing, and scientific-validation errors
are deliberately not caught here.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .autonomous_production_reference_chain_extension import (
    run_autonomous_production as run_reference_chain_production,
)
from .nist_mds2_2923_network_policy import (
    ACTION_CLASS as NIST_ACTION_CLASS,
    CANDIDATE_ID as NIST_CANDIDATE_ID,
    POLICY_ID as NIST_POLICY_ID,
    PRODUCT_ID as NIST_PRODUCT_ID,
)
from .nist_mds2_2923_production_acquisition import (
    NistMds22923ProductionTransportError,
)

TRANSPORT_STOP_CONTRACT_VERSION = "1.0"
TRANSPORT_STOP_REASON_CODE = "source_transport_temporarily_unavailable"


class AutonomousProductionTransportRecoveryError(ValueError):
    """Raised when transport recovery cannot preserve predecessor authority."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AutonomousProductionTransportRecoveryError(message)


def _canonical_sha(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _read_json(path: Path, field: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AutonomousProductionTransportRecoveryError(
            f"{field} must be valid UTF-8 JSON"
        ) from exc
    if not isinstance(value, dict):
        raise AutonomousProductionTransportRecoveryError(f"{field} root must be an object")
    return value


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True, allow_nan=False)
        + "\n",
        encoding="utf-8",
    )


def _resolved_output(root: Path, output_root: str | Path) -> Path:
    output = Path(output_root).expanduser()
    if not output.is_absolute():
        output = root / output
    output = output.resolve(strict=True)
    try:
        output.relative_to(root)
    except ValueError as exc:
        raise AutonomousProductionTransportRecoveryError(
            "autonomous production output escaped repository root"
        ) from exc
    return output


def _validate_self_hash(value: Mapping[str, Any], field: str) -> str:
    digest = value.get(field)
    _require(isinstance(digest, str) and len(digest) == 64, f"{field} is missing")
    unsigned = dict(value)
    unsigned.pop(field, None)
    _require(_canonical_sha(unsigned) == digest, f"{field} is invalid")
    return digest


def _validate_authorization_binding(
    *,
    qualification: Mapping[str, Any],
    authorization: Mapping[str, Any],
) -> tuple[str, str]:
    _require(
        qualification.get("policy_id") == NIST_POLICY_ID
        and qualification.get("action_class") == NIST_ACTION_CLASS
        and qualification.get("candidate_id") == NIST_CANDIDATE_ID
        and qualification.get("product_id") == NIST_PRODUCT_ID,
        "NIST transport qualification identity drifted",
    )
    policy_sha = qualification.get("policy_sha256")
    _require(isinstance(policy_sha, str) and len(policy_sha) == 64, "NIST policy SHA is missing")

    authorization_sha = authorization.get("authorization_sha256")
    _require(
        isinstance(authorization_sha, str) and len(authorization_sha) == 64,
        "NIST authorization SHA is missing",
    )
    unsigned_authorization = dict(authorization)
    unsigned_authorization.pop("authorization_sha256", None)
    _require(
        _canonical_sha(unsigned_authorization) == authorization_sha,
        "NIST authorization self-hash is invalid",
    )
    _require(
        authorization.get("policy_id") == NIST_POLICY_ID
        and authorization.get("policy_sha256") == policy_sha
        and authorization.get("action_class") == NIST_ACTION_CLASS
        and authorization.get("candidate_id") == NIST_CANDIDATE_ID
        and authorization.get("product_id") == NIST_PRODUCT_ID,
        "NIST authorization/qualification binding drifted",
    )
    _require(
        authorization.get("network_access_performed") is False
        and authorization.get("unrestricted_search_authorized") is False
        and authorization.get("arbitrary_url_fetch_authorized") is False,
        "NIST transport authorization widened network authority",
    )
    return policy_sha, authorization_sha


def _finalize_transport_stop(
    *,
    repository_root: Path,
    output_root: str | Path,
    transport_error: NistMds22923ProductionTransportError,
) -> dict[str, Any]:
    output = _resolved_output(repository_root, output_root)
    manifest_path = output / "autonomous-production-manifest.json"
    manifest = _read_json(manifest_path, "pre-transport autonomous production manifest")
    _validate_self_hash(manifest, "manifest_sha256")
    _require(
        manifest.get("generated_next_action_class") == NIST_ACTION_CLASS
        and manifest.get("preferred_geometry_candidate_id") == NIST_CANDIDATE_ID
        and manifest.get("final_blocker")
        == "response_compatible_geometry_evidence_not_acquired",
        "transport recovery predecessor did not stop at the exact NIST acquisition frontier",
    )
    _require(
        manifest.get("scientific_status_changed") is False
        and manifest.get("global_evidence_unavailability_claimed") is False,
        "transport recovery predecessor scientific boundary drifted",
    )
    raw_cycles = manifest.get("cycles")
    _require(
        isinstance(raw_cycles, list) and len(raw_cycles) == 2,
        "transport recovery predecessor cycle history drifted",
    )
    cycles = [dict(item) for item in raw_cycles if isinstance(item, Mapping)]
    _require(len(cycles) == 2, "transport recovery predecessor cycles are invalid")
    predecessor_cycle_sha = cycles[-1].get("cycle_sha256")
    _require(
        isinstance(predecessor_cycle_sha, str) and len(predecessor_cycle_sha) == 64,
        "transport recovery predecessor cycle binding is missing",
    )

    qualification = _read_json(
        output / "nist-network-policy-qualification.json",
        "NIST network policy qualification",
    )
    authorization = _read_json(
        output / "nist-network-authorization.json",
        "NIST network authorization",
    )
    policy_sha, authorization_sha = _validate_authorization_binding(
        qualification=qualification,
        authorization=authorization,
    )

    nist_output = output / "nist-mds2-2923"
    partial_output_present = nist_output.is_dir() and any(nist_output.iterdir())
    transport_report: dict[str, Any] = {
        "schema_version": TRANSPORT_STOP_CONTRACT_VERSION,
        "artifact_type": "temporary_source_transport_unavailability",
        "reason_code": TRANSPORT_STOP_REASON_CODE,
        "source_system": "NIST Public Data Repository",
        "product_id": NIST_PRODUCT_ID,
        "candidate_id": NIST_CANDIDATE_ID,
        "action_class": NIST_ACTION_CLASS,
        "policy_id": NIST_POLICY_ID,
        "policy_sha256": policy_sha,
        "authorization_sha256": authorization_sha,
        "transport_exception_type": type(transport_error).__name__,
        "transport_exception_message": str(transport_error),
        "partial_output_present": partial_output_present,
        "partial_output_reuse_authorized": False,
        "acquisition_completed": False,
        "scientific_intake_performed": False,
        "retry_performed": False,
        "retry_authorized_within_current_request_budget": False,
        "network_request_budget_widened": False,
        "allowed_hosts_widened": False,
        "alternate_url_synthesized": False,
        "network_failure_interpreted_as_negative_scientific_evidence": False,
        "global_evidence_unavailability_claimed": False,
        "alternative_evidence_lanes_remain_allowed": True,
        "scientific_status_changed": False,
    }
    transport_report["report_sha256_without_self_field"] = _canonical_sha(transport_report)
    _write_json(output / "nist-transport-unavailability.json", transport_report)

    cycle3: dict[str, Any] = {
        "cycle_index": 3,
        "predecessor_cycle_sha256": predecessor_cycle_sha,
        "input_blocker": "response_compatible_geometry_evidence_not_acquired",
        "selected_action_class": NIST_ACTION_CLASS,
        "handler": "nist_mds2_2923_exact_pdr_acquire_and_scientific_intake",
        "capability_available": True,
        "candidate_id": NIST_CANDIDATE_ID,
        "network_policy_id": NIST_POLICY_ID,
        "network_policy_sha256": policy_sha,
        "network_authorization_sha256": authorization_sha,
        "transport_unavailability_sha256": transport_report[
            "report_sha256_without_self_field"
        ],
        "acquisition_completed": False,
        "scientific_intake_performed": False,
        "retry_performed": False,
        "partial_output_reuse_authorized": False,
        "network_failure_interpreted_as_negative_scientific_evidence": False,
        "output_blocker": "response_compatible_geometry_evidence_not_acquired",
        "output_next_action_class": NIST_ACTION_CLASS,
        "new_verified_operational_information": True,
        "new_verified_scientific_information": False,
        "scientific_status_changed": False,
    }
    cycle3["cycle_sha256"] = _canonical_sha(cycle3)
    cycles.append(cycle3)

    stop: dict[str, Any] = {
        "status": "stopped",
        "reason_code": TRANSPORT_STOP_REASON_CODE,
        "requested_action_class": NIST_ACTION_CLASS,
        "candidate_id": NIST_CANDIDATE_ID,
        "scope": "exact_current_authorized_nist_delivery_attempt",
        "retry_performed": False,
        "retry_authorized_within_current_request_budget": False,
        "partial_output_reuse_authorized": False,
        "alternative_evidence_lanes_remain_allowed": True,
        "global_evidence_unavailability_claimed": False,
        "network_failure_interpreted_as_negative_scientific_evidence": False,
        "positive_scientific_closeout": False,
        "scientific_status_changed": False,
    }

    result = dict(manifest)
    result.pop("manifest_sha256", None)
    result.update(
        {
            "cycles": cycles,
            "stop": stop,
            "transport_stop_contract_version": TRANSPORT_STOP_CONTRACT_VERSION,
            "nist_mds2_2923_policy_sha256": policy_sha,
            "nist_mds2_2923_network_authorization_sha256": authorization_sha,
            "nist_mds2_2923_transport_unavailability_sha256": transport_report[
                "report_sha256_without_self_field"
            ],
            "nist_mds2_2923_acquisition_completed": False,
            "nist_mds2_2923_scientific_intake_performed": False,
            "response_compatible_geometry_evidence_acquired": False,
            "paper_and_other_source_lanes_remain_allowed": True,
            "final_blocker": "response_compatible_geometry_evidence_not_acquired",
            "generated_next_action_class": NIST_ACTION_CLASS,
            "network_failure_interpreted_as_negative_scientific_evidence": False,
            "global_evidence_unavailability_claimed": False,
            "positive_scientific_closeout_established": False,
            "scientific_status_changed": False,
        }
    )
    result["manifest_sha256"] = _canonical_sha(result)
    _write_json(output / "bounded-stop.json", stop)
    _write_json(manifest_path, result)
    return result


def run_autonomous_production(
    *,
    repository_root: str | Path,
    mission_path: str | Path,
    expected_mission_sha256: str,
    output_root: str | Path,
    max_cycles: int = 12,
) -> dict[str, Any]:
    """Run the audited production path and fail closed on typed NIST transport outages."""

    root = Path(repository_root).expanduser().resolve(strict=True)
    try:
        return run_reference_chain_production(
            repository_root=root,
            mission_path=mission_path,
            expected_mission_sha256=expected_mission_sha256,
            output_root=output_root,
            max_cycles=max_cycles,
        )
    except NistMds22923ProductionTransportError as exc:
        return _finalize_transport_stop(
            repository_root=root,
            output_root=output_root,
            transport_error=exc,
        )


__all__ = [
    "AutonomousProductionTransportRecoveryError",
    "TRANSPORT_STOP_CONTRACT_VERSION",
    "TRANSPORT_STOP_REASON_CODE",
    "run_autonomous_production",
]
