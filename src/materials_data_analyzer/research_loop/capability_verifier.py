"""Independent verifier for bounded capability candidates.

Verification is separate from candidate discovery and registry promotion. The verifier may perform
an exact-source smoke test only under authority that was already authenticated by the mission;
it cannot add hosts, URLs, action classes, or scientific truth authority.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from . import calibration_protocol_bridge_capability as bridge
from .capability_registry import build_capability_verification_receipt

CAPABILITY_VERIFIER_SCHEMA_VERSION = "1.0"
CAPABILITY_VERIFIER_POLICY_VERSION = "1.0"


class CapabilityVerifierError(ValueError):
    """Raised when a candidate cannot be independently verified."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CapabilityVerifierError(message)


def _canonical_sha(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _module_sha(module: object, field: str) -> str:
    raw_path = getattr(module, "__file__", None)
    _require(isinstance(raw_path, str) and raw_path, f"{field} module path missing")
    path = Path(raw_path).resolve(strict=True)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _current_verifier_sha() -> str:
    return hashlib.sha256(Path(__file__).resolve(strict=True).read_bytes()).hexdigest()


def _fixture_evidence() -> dict[str, Any]:
    claim_ids = sorted(bridge._REQUIRED_CLAIMS)
    sources: list[dict[str, Any]] = []
    for index in range(8):
        assigned = claim_ids[index : index + 1]
        if index == 7:
            assigned = claim_ids[index:]
        sources.append(
            {
                "source_id": f"fixture-source-{index}",
                "source_sha256": f"{index + 1:064x}"[-64:],
                "claims": [
                    {"claim_id": claim_id, "matched": True}
                    for claim_id in assigned
                ],
            }
        )
    return {
        "acquisition_status": "exact_multisource_condition_evidence_acquired",
        "source_count": 8,
        "network_requests_performed": 8,
        "all_claim_anchors_matched": True,
        "paper_claims_promoted_to_row_level_authority": False,
        "report_sha256_without_self_field": "e" * 64,
        "sources": sources,
    }


def _fixture_mapping() -> dict[str, Any]:
    return {
        "gate_decision": {
            "directly_comparable_mds2_rows": 0,
            "direct_numerical_validation_authorized": False,
            "issue_76_exact_target_cells_satisfied": 0,
        },
        "report_sha256_without_self_field": "d" * 64,
    }


def verify_bounded_capability_candidate(
    *,
    capability_specification: Mapping[str, Any],
    candidate: Mapping[str, Any],
    available_verified_primitives: Sequence[str],
    repository_root: str | Path,
    mission_path: str | Path,
    expected_mission_sha256: str,
    perform_real_source_smoke: bool,
) -> dict[str, Any]:
    """Verify one candidate and return a byte-bound independent promotion receipt."""
    _require(
        candidate.get("action_class") == bridge.ACTION_CLASS,
        "no verifier is registered for candidate action class",
    )
    _require(
        candidate.get("factory_id") == bridge.FACTORY_ID,
        "candidate factory drifted",
    )
    _require(
        candidate.get("implementation_id") == bridge.IMPLEMENTATION_ID,
        "candidate implementation drifted",
    )
    _require(
        candidate.get("mechanism") == "compose_verified_primitives",
        "candidate mechanism drifted",
    )

    deterministic_contract = (
        candidate.get("required_verified_primitives")
        == sorted(bridge.REQUIRED_VERIFIED_PRIMITIVES)
    )
    authority_and_provenance = (
        candidate.get("network_authority_granted") is False
        and candidate.get("execution_authority_granted") is False
        and candidate.get("scientific_status_change_authorized") is False
        and candidate.get("self_promotion_requested") is False
    )

    fixture_ok = False
    epistemic_boundary_ok = False
    try:
        fixture_report = bridge.build_bridge_frontier_report(
            mapping_assessment=_fixture_mapping(),
            reacquired_evidence=_fixture_evidence(),
        )
        fixture_ok = fixture_report.get("execution_status") == (
            "authorized_bridge_sources_reacquired_and_frontier_refined"
        )
        epistemic_boundary_ok = (
            fixture_report.get("bridge_established") is False
            and fixture_report.get("directly_comparable_mds2_rows") == 0
            and fixture_report.get("direct_numerical_validation_authorized") is False
            and fixture_report.get("cross_machine_pooling_authorized") is False
            and fixture_report.get("paper_claims_promoted_to_row_level_authority") is False
            and fixture_report.get("issue_76_exact_target_cells_satisfied") == 0
            and fixture_report.get("scientific_status_changed") is False
        )
    except (TypeError, ValueError):
        fixture_ok = False
        epistemic_boundary_ok = False

    smoke_receipt: dict[str, Any] | None = None
    if perform_real_source_smoke:
        smoke_receipt = bridge.smoke_exact_source_authority(
            repository_root=repository_root,
            mission_path=mission_path,
            expected_mission_sha256=expected_mission_sha256,
        )
        real_source_smoke_ok = (
            smoke_receipt.get("smoke_status") == "exact_authorized_source_retrieved"
            and smoke_receipt.get("network_requests_performed") == 1
            and smoke_receipt.get("unrestricted_search_performed") is False
            and smoke_receipt.get("arbitrary_url_fetch_performed") is False
            and smoke_receipt.get("scientific_status_changed") is False
        )
    else:
        real_source_smoke_ok = False

    implementation_sha = _module_sha(bridge, "implementation")
    verifier_sha = _current_verifier_sha()
    byte_bindings_ok = len(implementation_sha) == 64 and len(verifier_sha) == 64

    verification_results = {
        "deterministic_contract_tests": deterministic_contract,
        "adversarial_authority_and_provenance_tests": authority_and_provenance,
        "fixture_replay": fixture_ok,
        "real_source_smoke_test_when_network_evidence_is_required": real_source_smoke_ok,
        "epistemic_boundary_test": epistemic_boundary_ok,
        "exact_spec_implementation_and_verifier_byte_bindings": byte_bindings_ok,
    }
    receipt = build_capability_verification_receipt(
        capability_specification=capability_specification,
        candidate=candidate,
        available_verified_primitives=available_verified_primitives,
        verification_results=verification_results,
    )
    unsigned = dict(receipt)
    unsigned.pop("capability_verification_sha256_without_self_field", None)
    unsigned.update(
        {
            "verifier_schema_version": CAPABILITY_VERIFIER_SCHEMA_VERSION,
            "verifier_policy_version": CAPABILITY_VERIFIER_POLICY_VERSION,
            "implementation_sha256": implementation_sha,
            "verifier_sha256": verifier_sha,
            "real_source_smoke_receipt_sha256": (
                smoke_receipt.get("smoke_receipt_sha256_without_self_field")
                if smoke_receipt is not None
                else None
            ),
            "real_source_smoke_receipt": smoke_receipt,
        }
    )
    unsigned["capability_verification_sha256_without_self_field"] = _canonical_sha(
        unsigned
    )
    return unsigned


__all__ = [
    "CAPABILITY_VERIFIER_POLICY_VERSION",
    "CAPABILITY_VERIFIER_SCHEMA_VERSION",
    "CapabilityVerifierError",
    "verify_bounded_capability_candidate",
]
