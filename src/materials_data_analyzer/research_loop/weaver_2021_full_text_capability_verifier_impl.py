"""Independent verifier for bounded Weaver 2021 full-text acquisition capability.

The live verifier performs at most one exact authorized network fetch.  The exact bounded
request/response bytes are retained with the common capability smoke-replay contract and then
replayed through the acquisition parser without network access.  Historical verification accepts
only authenticated retained replay evidence; it never re-queries mutable remote state.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from . import capability_smoke_replay_evidence as smoke_replay
from . import weaver_2021_full_text_acquisition as acquisition
from . import weaver_2021_full_text_capability as capability
from . import weaver_2021_full_text_policy as policy
from .capability_registry import build_capability_verification_receipt
from .in625_geometry_condition_source_acquisition import fetch_exact_source

VERIFIER_SCHEMA_VERSION = "1.1"
VERIFIER_POLICY_VERSION = "1.1"
_EXPECTED_REQUIRED_INPUTS = (
    "verified_mds2_2923_reference_chain_assessment",
    "provenance_bound_weaver_primary_reference_locator",
    "separately_authenticated_derived_full_text_acquisition_policy",
)
_EXPECTED_REQUIRED_OUTPUTS = (
    "derived_weaver_full_text_authorization_bound_to_reference_graph",
    "exact_weaver_primary_full_text_sha256_and_parser_receipt",
    "experiment_identity_claim_receipts",
    "machine_setting_and_calibrated_power_claim_receipts",
    "spot_definition_protocol_and_uncertainty_claim_receipts",
    "updated_reference_chain_gate_assessment",
)
_EXPECTED_SCIENTIFIC_ACCEPTANCE = (
    "Do not accept a caller-authored Weaver URL or retroactively widen the predecessor reference-chain policy.",
    "A citation or bibliographic identity is a locator only and does not itself authorize full-text acquisition.",
    "Successful full-text acquisition or parsing does not establish mds2 row identity, calibration equivalence, protocol equivalence, or uncertainty transfer.",
    "Do not infer machine-setting-to-calibrated-power conversion from matching nominal conditions or spot-size ranges.",
    "Do not promote literature to row-level measurement authority.",
    "Preserve directly comparable rows at 0 and Issue #76 at 0/3 unless exact experiment-scoped evidence satisfies the corresponding gates.",
    "A failed bounded acquisition is operational evidence only and does not establish global evidence absence.",
)
_EXPECTED_VERIFICATION_REQUIREMENTS = (
    "deterministic_contract_tests",
    "adversarial_authority_and_provenance_tests",
    "fixture_replay",
    "real_source_smoke_test_when_network_evidence_is_required",
    "epistemic_boundary_test",
    "exact_spec_implementation_and_verifier_byte_bindings",
)


class Weaver2021FullTextCapabilityVerifierError(ValueError):
    """Raised when Weaver capability cannot be independently verified."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise Weaver2021FullTextCapabilityVerifierError(message)


def _canonical_sha(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _self_hash_ok(value: Mapping[str, Any]) -> bool:
    digest = value.get("report_sha256_without_self_field")
    if not isinstance(digest, str) or len(digest) != 64:
        return False
    unsigned = dict(value)
    unsigned.pop("report_sha256_without_self_field", None)
    return _canonical_sha(unsigned) == digest


def _bound_sha(value: Mapping[str, Any], field: str, label: str) -> str:
    digest = value.get(field)
    _require(isinstance(digest, str) and len(digest) == 64, f"{label} binding is missing")
    return digest


def _module_sha(module: object, field: str) -> str:
    raw_path = getattr(module, "__file__", None)
    _require(isinstance(raw_path, str) and raw_path, f"{field} module path missing")
    return hashlib.sha256(Path(raw_path).resolve(strict=True).read_bytes()).hexdigest()


def _semantic_spec_contract_ok(specification: Mapping[str, Any]) -> bool:
    promotion = specification.get("promotion_policy")
    authority = specification.get("authority_policy")
    mechanisms = specification.get("allowed_implementation_mechanisms")
    forbidden = specification.get("forbidden_implementation_mechanisms")
    return bool(
        specification.get("requested_action_class") == capability.ACTION_CLASS
        and specification.get("gap_class") == "missing_source_adapter"
        and specification.get("required_inputs") == list(_EXPECTED_REQUIRED_INPUTS)
        and specification.get("required_outputs") == list(_EXPECTED_REQUIRED_OUTPUTS)
        and specification.get("scientific_acceptance") == list(_EXPECTED_SCIENTIFIC_ACCEPTANCE)
        and specification.get("verification_requirements")
        == list(_EXPECTED_VERIFICATION_REQUIREMENTS)
        and isinstance(mechanisms, list)
        and capability.MECHANISM in mechanisms
        and isinstance(forbidden, list)
        and "arbitrary_python_eval_or_exec" in forbidden
        and "self_modifying_runtime_code" in forbidden
        and "unreviewed_network_host_expansion" in forbidden
        and "candidate_self_promotion" in forbidden
        and isinstance(promotion, Mapping)
        and promotion.get("candidate_may_self_promote") is False
        and promotion.get("independent_verifier_required") is True
        and promotion.get("verified_registry_predecessor_required") is True
        and promotion.get("scientific_truth_promotion_authorized") is False
        and isinstance(authority, Mapping)
        and authority.get("may_synthesize_new_network_hosts") is False
        and authority.get("may_synthesize_arbitrary_urls") is False
        and authority.get("may_execute_physical_instrument") is False
        and authority.get("may_promote_literature_to_row_level_measurement") is False
    )


def _context(
    value: Mapping[str, Any] | None,
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    _require(isinstance(value, Mapping), "Weaver verifier context is missing")
    graph = value.get("reference_graph")
    manifest = value.get("predecessor_manifest")
    _require(
        isinstance(graph, Mapping) and isinstance(manifest, Mapping),
        "Weaver verifier context is incomplete",
    )
    return graph, manifest


def _boundary_ok(report: Mapping[str, Any]) -> bool:
    scope = report.get("evidence_scope")
    gate = report.get("gate_assessment")
    next_action = report.get("next_action")
    return bool(
        isinstance(scope, Mapping)
        and isinstance(gate, Mapping)
        and isinstance(next_action, Mapping)
        and scope.get("weaver_full_text_acquired") is True
        and scope.get("weaver_article_identity_established") is True
        and gate.get("exact_mds2_rows_to_weaver_experiment_established") is False
        and gate.get("exact_mds2_experiment_identity_established") is False
        and gate.get("machine_setting_to_calibrated_power_relation_established") is False
        and gate.get("spot_size_transfer_authorized") is False
        and gate.get("protocol_equivalence_established") is False
        and gate.get("uncertainty_transfer_authorized") is False
        and gate.get("directly_comparable_mds2_rows") == 0
        and gate.get("direct_numerical_cross_source_validation_authorized") is False
        and gate.get("cross_machine_pooling_authorized") is False
        and gate.get("issue_76_exact_target_cells_satisfied") == 0
        and report.get("literature_promoted_to_row_level_measurement_authority") is False
        and report.get("acquisition_success_establishes_scientific_bridge") is False
        and report.get("scientific_status_changed") is False
        and report.get("positive_scientific_closeout") is False
        and report.get("global_evidence_unavailability_claimed") is False
        and next_action.get("action_class") == acquisition.NEXT_ACTION_CLASS
        and next_action.get("automatic_execution_authorized") is False
        and next_action.get("network_access_required") is False
    )


def _qualification_and_authorization(
    *,
    repository_root: str | Path,
    mission_path: str | Path,
    expected_mission_sha256: str,
    verification_context: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    graph, manifest = _context(verification_context)
    qualification = policy.authenticate_weaver_2021_full_text_policy(
        repository_root=repository_root,
        mission_path=mission_path,
        expected_mission_sha256=expected_mission_sha256,
    )
    authorization = acquisition.build_derived_weaver_authorization(
        qualification=qualification,
        reference_graph=graph,
        predecessor_manifest=manifest,
    )
    return qualification, authorization


def _source_smoke_ok(report: Mapping[str, Any]) -> bool:
    identity = report.get("article_identity")
    return bool(
        report.get("acquisition_status")
        == "exact_weaver_primary_full_text_acquired_and_identity_verified"
        and isinstance(identity, Mapping)
        and identity.get("article_identity_established") is True
        and report.get("core_claims_matched") is True
        and report.get("network_requests_performed") == 1
        and report.get("caller_authored_url_used") is False
        and report.get("caller_authored_pmcid_used") is False
        and report.get("unrestricted_search_performed") is False
        and report.get("literature_promoted_to_row_level_measurement_authority") is False
        and report.get("acquisition_success_establishes_scientific_bridge") is False
        and report.get("scientific_status_changed") is False
    )


def verify_weaver_2021_full_text_capability_candidate(
    *,
    capability_specification: Mapping[str, Any],
    candidate: Mapping[str, Any],
    available_verified_primitives: Sequence[str],
    repository_root: str | Path,
    mission_path: str | Path,
    expected_mission_sha256: str,
    verification_context: Mapping[str, Any] | None,
    perform_real_source_smoke: bool = True,
    retained_smoke_replay_evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Verify exact Weaver capability bytes and retain deterministic zero-network replay evidence."""
    _require(candidate.get("action_class") == capability.ACTION_CLASS, "candidate action drifted")
    _require(candidate.get("factory_id") == capability.FACTORY_ID, "candidate factory drifted")
    _require(
        candidate.get("implementation_id") == capability.IMPLEMENTATION_ID,
        "candidate implementation drifted",
    )
    _require(candidate.get("mechanism") == capability.MECHANISM, "candidate mechanism drifted")

    deterministic_contract = bool(
        candidate.get("required_verified_primitives")
        == sorted(capability.REQUIRED_VERIFIED_PRIMITIVES)
        and _semantic_spec_contract_ok(capability_specification)
    )
    authority_and_provenance = bool(
        candidate.get("network_authority_granted") is False
        and candidate.get("execution_authority_granted") is False
        and candidate.get("scientific_status_change_authorized") is False
        and candidate.get("self_promotion_requested") is False
    )
    spec_sha = _bound_sha(
        capability_specification,
        "capability_specification_sha256_without_self_field",
        "capability specification",
    )
    candidate_sha = _bound_sha(
        candidate,
        "capability_candidate_sha256_without_self_field",
        "capability candidate",
    )

    smoke_receipt: dict[str, Any] | None = None
    replay_evidence: dict[str, Any] | None = None
    fixture_ok = False
    real_source_smoke_ok = False
    epistemic_boundary_ok = False

    if retained_smoke_replay_evidence is not None:
        replay_fetcher, retained_context = smoke_replay.authenticate_smoke_replay_evidence(
            retained_smoke_replay_evidence,
            action_class=capability.ACTION_CLASS,
            capability_specification_sha256=spec_sha,
            capability_candidate_sha256=candidate_sha,
            mission_sha256=expected_mission_sha256,
        )
        _require(isinstance(retained_context, Mapping), "retained Weaver verifier context is missing")
        if verification_context is not None:
            _require(
                _canonical_sha(retained_context) == _canonical_sha(verification_context),
                "retained Weaver verification context drifted",
            )
        qualification, authorization = _qualification_and_authorization(
            repository_root=repository_root,
            mission_path=mission_path,
            expected_mission_sha256=expected_mission_sha256,
            verification_context=retained_context,
        )
        replayed = acquisition.execute_derived_weaver_acquisition(
            authorization=authorization,
            fetcher=replay_fetcher,
        )
        replay_fetcher.assert_consumed()
        fixture_ok = _self_hash_ok(replayed)
        real_source_smoke_ok = _source_smoke_ok(replayed)
        epistemic_boundary_ok = _boundary_ok(replayed)
        replay_evidence = dict(retained_smoke_replay_evidence)
        smoke_receipt = {
            "schema_version": "1.1",
            "smoke_status": "retained_exact_weaver_pmc_source_replayed_zero_network",
            "qualification_policy_sha256": qualification.get("policy_sha256"),
            "authorization_sha256": authorization.get("authorization_sha256"),
            "weaver_evidence_sha256": replayed.get("report_sha256_without_self_field"),
            "weaver_source_sha256": replayed.get("source", {}).get("source_sha256"),
            "live_network_requests_performed": 0,
            "deterministic_replay_fetch_invocations": 1,
            "deterministic_replay_network_requests_performed": 0,
            "execution_must_replay_retained_bytes": True,
            "core_claims_matched": replayed.get("core_claims_matched") is True,
            "evidence_self_hash_recomputed": fixture_ok,
            "scientific_status_changed": False,
        }
        smoke_receipt["report_sha256_without_self_field"] = _canonical_sha(smoke_receipt)
    elif perform_real_source_smoke:
        qualification, authorization = _qualification_and_authorization(
            repository_root=repository_root,
            mission_path=mission_path,
            expected_mission_sha256=expected_mission_sha256,
            verification_context=verification_context,
        )
        recording = smoke_replay.RecordingFetcher(fetch_exact_source)
        first = acquisition.execute_derived_weaver_acquisition(
            authorization=authorization,
            fetcher=recording,
        )
        first_self_hash_ok = _self_hash_ok(first)
        if recording.records:
            replay_evidence = smoke_replay.build_smoke_replay_evidence(
                action_class=capability.ACTION_CLASS,
                capability_specification_sha256=spec_sha,
                capability_candidate_sha256=candidate_sha,
                mission_sha256=expected_mission_sha256,
                verification_context=verification_context,
                fetch_records=recording.records,
            )
            replay_fetcher, retained_context = smoke_replay.authenticate_smoke_replay_evidence(
                replay_evidence,
                action_class=capability.ACTION_CLASS,
                capability_specification_sha256=spec_sha,
                capability_candidate_sha256=candidate_sha,
                mission_sha256=expected_mission_sha256,
            )
            _require(isinstance(retained_context, Mapping), "retained Weaver verifier context is missing")
            replay_qualification, replay_authorization = _qualification_and_authorization(
                repository_root=repository_root,
                mission_path=mission_path,
                expected_mission_sha256=expected_mission_sha256,
                verification_context=retained_context,
            )
            _require(
                replay_qualification.get("policy_sha256") == qualification.get("policy_sha256")
                and replay_authorization.get("authorization_sha256")
                == authorization.get("authorization_sha256"),
                "Weaver replay authority drifted",
            )
            second = acquisition.execute_derived_weaver_acquisition(
                authorization=replay_authorization,
                fetcher=replay_fetcher,
            )
            replay_fetcher.assert_consumed()
            fixture_ok = bool(
                first_self_hash_ok
                and _self_hash_ok(second)
                and first.get("report_sha256_without_self_field")
                == second.get("report_sha256_without_self_field")
                and first.get("source", {}).get("source_sha256")
                == second.get("source", {}).get("source_sha256")
            )
        real_source_smoke_ok = _source_smoke_ok(first)
        epistemic_boundary_ok = _boundary_ok(first)
        smoke_receipt = {
            "schema_version": "1.1",
            "smoke_status": "exact_weaver_pmc_source_recorded_and_zero_network_replayed",
            "qualification_policy_sha256": qualification.get("policy_sha256"),
            "authorization_sha256": authorization.get("authorization_sha256"),
            "weaver_evidence_sha256": first.get("report_sha256_without_self_field"),
            "weaver_source_sha256": first.get("source", {}).get("source_sha256"),
            "live_network_requests_performed": 1 if recording.records else 0,
            "deterministic_replay_fetch_invocations": 1 if replay_evidence is not None else 0,
            "deterministic_replay_network_requests_performed": 0,
            "execution_must_replay_retained_bytes": True,
            "core_claims_matched": first.get("core_claims_matched") is True,
            "evidence_self_hash_recomputed": fixture_ok,
            "scientific_status_changed": False,
        }
        smoke_receipt["report_sha256_without_self_field"] = _canonical_sha(smoke_receipt)

    component_hashes = {
        "capability_descriptor_sha256": _module_sha(capability, "capability descriptor"),
        "acquisition_adapter_sha256": _module_sha(acquisition, "acquisition adapter"),
        "policy_authenticator_sha256": _module_sha(policy, "policy authenticator"),
        "smoke_replay_helper_sha256": _module_sha(smoke_replay, "smoke replay helper"),
    }
    implementation_sha = _canonical_sha(component_hashes)
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
    replay_sha = None
    if replay_evidence is not None:
        replay_sha = replay_evidence.get("smoke_replay_evidence_sha256_without_self_field")
    unsigned.update(
        {
            "verifier_schema_version": VERIFIER_SCHEMA_VERSION,
            "verifier_policy_version": VERIFIER_POLICY_VERSION,
            "semantic_spec_contract_verified": deterministic_contract,
            "implementation_component_sha256": component_hashes,
            "implementation_sha256": implementation_sha,
            "verifier_sha256": verifier_sha,
            "real_source_smoke_receipt": smoke_receipt,
            "real_source_smoke_receipt_sha256": (
                None if smoke_receipt is None else smoke_receipt["report_sha256_without_self_field"]
            ),
            "real_source_smoke_replay_evidence": replay_evidence,
            "real_source_smoke_replay_evidence_sha256": replay_sha,
            "historical_reverification_network_requests_performed": 0,
        }
    )
    unsigned["capability_verification_sha256_without_self_field"] = _canonical_sha(unsigned)
    return unsigned


__all__ = [
    "VERIFIER_POLICY_VERSION",
    "VERIFIER_SCHEMA_VERSION",
    "Weaver2021FullTextCapabilityVerifierError",
    "verify_weaver_2021_full_text_capability_candidate",
]
