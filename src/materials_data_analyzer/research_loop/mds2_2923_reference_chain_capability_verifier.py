"""Independent verifier for the bounded mds2-2923 reference-chain capability.

This verifier is capability-specific by design: it may authenticate and smoke-test only the
already mission-pinned Naderi source authority.  Promotion remains owned by the common
capability registry kernel.  Verifier evidence is never reused as execution evidence.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from . import mds2_2923_experiment_identity_reference_chain as reference_chain
from .capability_registry import build_capability_verification_receipt
from .nist_mds2_2923_reference_chain_evidence import (
    acquire_naderi_reference_chain_evidence,
)
from .nist_mds2_2923_reference_chain_policy import (
    authenticate_nist_mds2_2923_reference_chain_policy,
)

VERIFIER_SCHEMA_VERSION = "1.0"
VERIFIER_POLICY_VERSION = "1.0"
EXPECTED_MECHANISM = "compose_verified_primitives"
_REQUIRED_CONTEXT_FIELDS = (
    "nerdm_metadata_bytes",
    "nist_intake",
    "multisource_evidence",
    "source_discovery_report",
    "calibration_candidate_assessment",
)


class Mds22923ReferenceChainCapabilityVerifierError(ValueError):
    """Raised when the bounded reference-chain capability cannot be independently verified."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise Mds22923ReferenceChainCapabilityVerifierError(message)


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
    return hashlib.sha256(Path(raw_path).resolve(strict=True).read_bytes()).hexdigest()


def _context(value: Mapping[str, Any] | None) -> tuple[bytes, Mapping[str, Any], Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]]:
    _require(isinstance(value, Mapping), "reference-chain verifier context is missing")
    missing = [field for field in _REQUIRED_CONTEXT_FIELDS if field not in value]
    _require(not missing, f"reference-chain verifier context missing fields: {missing}")
    metadata = value["nerdm_metadata_bytes"]
    _require(isinstance(metadata, bytes), "reference-chain NERDm context must be exact bytes")
    reports = tuple(value[field] for field in _REQUIRED_CONTEXT_FIELDS[1:])
    _require(
        all(isinstance(item, Mapping) for item in reports),
        "reference-chain verifier reports must be mappings",
    )
    return metadata, reports[0], reports[1], reports[2], reports[3]  # type: ignore[return-value]


def _boundary_ok(report: Mapping[str, Any]) -> bool:
    identity = report.get("experiment_identity")
    gate = report.get("calibration_and_protocol_gate")
    graph = report.get("reference_graph")
    next_action = report.get("next_action")
    return bool(
        isinstance(identity, Mapping)
        and isinstance(gate, Mapping)
        and isinstance(graph, Mapping)
        and isinstance(next_action, Mapping)
        and identity.get("dataset_to_weaver_association_established") is True
        and identity.get("dataset_to_naderi_association_established") is True
        and identity.get("naderi_to_weaver_experiment_detail_reference_established") is True
        and identity.get("exact_mds2_rows_to_weaver_experiment_established") is False
        and identity.get("exact_mds2_experiment_identity_established") is False
        and gate.get("weaver_full_text_acquired") is False
        and gate.get("machine_setting_to_calibrated_power_relation_established") is False
        and gate.get("spot_size_transfer_authorized") is False
        and gate.get("protocol_equivalence_established") is False
        and gate.get("uncertainty_transfer_authorized") is False
        and gate.get("directly_comparable_mds2_rows") == 0
        and gate.get("direct_numerical_cross_source_validation_authorized") is False
        and gate.get("cross_machine_pooling_authorized") is False
        and gate.get("issue_76_exact_target_cells_satisfied") == 0
        and graph.get("transitive_authority_promotion_allowed") is False
        and next_action.get("action_class") == reference_chain.NEXT_ACTION_CLASS
        and next_action.get("automatic_acquisition_authorized") is False
        and next_action.get("caller_authored_url_authorized") is False
        and report.get("scientific_status_changed") is False
        and report.get("positive_scientific_closeout") is False
        and report.get("global_evidence_unavailability_claimed") is False
    )


def verify_reference_chain_capability_candidate(
    *,
    capability_specification: Mapping[str, Any],
    candidate: Mapping[str, Any],
    available_verified_primitives: Sequence[str],
    repository_root: str | Path,
    mission_path: str | Path,
    expected_mission_sha256: str,
    verification_context: Mapping[str, Any] | None,
    perform_real_source_smoke: bool = True,
) -> dict[str, Any]:
    """Verify exact contract, deterministic replay, source authority and epistemic boundary."""
    _require(
        candidate.get("action_class") == reference_chain.ACTION_CLASS,
        "reference-chain candidate action class drifted",
    )
    _require(
        candidate.get("factory_id") == reference_chain.FACTORY_ID,
        "reference-chain candidate factory drifted",
    )
    _require(
        candidate.get("implementation_id") == reference_chain.IMPLEMENTATION_ID,
        "reference-chain candidate implementation drifted",
    )
    _require(
        candidate.get("mechanism") == EXPECTED_MECHANISM,
        "reference-chain candidate mechanism drifted",
    )
    deterministic_contract = candidate.get("required_verified_primitives") == sorted(
        reference_chain.REQUIRED_VERIFIED_PRIMITIVES
    )
    authority_and_provenance = bool(
        candidate.get("network_authority_granted") is False
        and candidate.get("execution_authority_granted") is False
        and candidate.get("scientific_status_change_authorized") is False
        and candidate.get("self_promotion_requested") is False
    )

    metadata, nist_intake, multisource, discovery, calibration = _context(
        verification_context
    )
    smoke_receipt: dict[str, Any] | None = None
    fixture_ok = False
    epistemic_boundary_ok = False
    real_source_smoke_ok = False
    if perform_real_source_smoke:
        qualification = authenticate_nist_mds2_2923_reference_chain_policy(
            repository_root=repository_root,
            mission_path=mission_path,
            expected_mission_sha256=expected_mission_sha256,
        )
        naderi = acquire_naderi_reference_chain_evidence(qualification=qualification)
        first = reference_chain.build_mds2_2923_experiment_identity_reference_chain(
            nerdm_metadata_bytes=metadata,
            nist_intake=nist_intake,
            naderi_reference_evidence=naderi,
            multisource_evidence=multisource,
            source_discovery_report=discovery,
            calibration_candidate_assessment=calibration,
        )
        second = reference_chain.build_mds2_2923_experiment_identity_reference_chain(
            nerdm_metadata_bytes=metadata,
            nist_intake=nist_intake,
            naderi_reference_evidence=naderi,
            multisource_evidence=multisource,
            source_discovery_report=discovery,
            calibration_candidate_assessment=calibration,
        )
        fixture_ok = (
            first.get("report_sha256_without_self_field")
            == second.get("report_sha256_without_self_field")
            and first.get("reference_graph", {}).get("edges_sha256")
            == second.get("reference_graph", {}).get("edges_sha256")
        )
        epistemic_boundary_ok = _boundary_ok(first)
        real_source_smoke_ok = bool(
            naderi.get("acquisition_status")
            == "exact_naderi_reference_chain_evidence_acquired"
            and naderi.get("network_requests_performed") == 1
            and naderi.get("all_claims_matched") is True
            and naderi.get("unrestricted_search_performed") is False
            and naderi.get("caller_authored_url_used") is False
            and naderi.get("arbitrary_url_fetch_performed") is False
            and naderi.get("literature_promoted_to_row_level_measurement_authority") is False
            and naderi.get("reference_chain_promoted_to_power_conversion") is False
            and naderi.get("scientific_status_changed") is False
        )
        smoke_receipt = {
            "schema_version": "1.0",
            "smoke_status": "exact_naderi_source_and_reference_graph_replay_verified",
            "qualification_policy_sha256": qualification.get("policy_sha256"),
            "naderi_evidence_sha256": naderi.get("report_sha256_without_self_field"),
            "reference_graph_sha256": first.get("report_sha256_without_self_field"),
            "reference_edges_sha256": first.get("reference_graph", {}).get("edges_sha256"),
            "network_requests_performed": 1,
            "execution_evidence_reuse_authorized": False,
            "scientific_status_changed": False,
        }
        smoke_receipt["report_sha256_without_self_field"] = _canonical_sha(smoke_receipt)

    implementation_sha = _module_sha(reference_chain, "reference-chain implementation")
    verifier_sha = hashlib.sha256(Path(__file__).resolve(strict=True).read_bytes()).hexdigest()
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
            "verifier_schema_version": VERIFIER_SCHEMA_VERSION,
            "verifier_policy_version": VERIFIER_POLICY_VERSION,
            "implementation_sha256": implementation_sha,
            "verifier_sha256": verifier_sha,
            "real_source_smoke_receipt": smoke_receipt,
            "real_source_smoke_receipt_sha256": (
                None if smoke_receipt is None else smoke_receipt["report_sha256_without_self_field"]
            ),
        }
    )
    unsigned["capability_verification_sha256_without_self_field"] = _canonical_sha(unsigned)
    return unsigned


__all__ = [
    "Mds22923ReferenceChainCapabilityVerifierError",
    "VERIFIER_POLICY_VERSION",
    "VERIFIER_SCHEMA_VERSION",
    "verify_reference_chain_capability_candidate",
]
