"""Fourth exact-head fail-closed closure for PR #233.

This additive verifier closes the four P2 findings from the Codex review of
``d58690bc46fc8c9b3c8615c1e26dafd9a8ddc1f6``. It authenticates late-cycle
identity/search authority fields, the terminal capability resolution,
Naderi reference-chain provenance and claim receipts, and the complete
physical-comparability gate decision.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from . import autonomous_production_exact_head_p2_round3 as _round3
from . import autonomous_production_merge_gate_hardening as _merge_gate

AutonomousProductionExactHeadRound4Error = (
    _merge_gate.AutonomousProductionMergeGateHardeningError
)

_NADERI_POLICY = (
    "configs/research/nist_mds2_2923_reference_chain_naderi_evidence_policy.v1.json"
)

_ADDITIONAL_DENIED_LATE_TRUE_FIELDS = {
    "acquisition_authority_granted",
    "acquisition_authorized",
    "arbitrary_code_execution_granted",
    "arbitrary_url_fetch_performed",
    "automatic_acquisition_authorized",
    "automatic_unrestricted_search_authorized",
    "caller_authored_arbitrary_urls_authorized",
    "caller_authored_url_authorized",
    "caller_authored_url_used",
    "candidate_rediscovery_performed",
    "candidate_url_followed",
    "cross_section_protocol_identity_established",
    "exact_experiment_identity_established",
    "exact_machine_setting_to_calibrated_power_relation_established",
    "exact_mds2_2923_experiment_identity_established",
    "exact_mds2_experiment_identity_established",
    "exact_mds2_rows_to_weaver_experiment_established",
    "exact_mds2_spot_size_value_transfer_established",
    "exact_row_identity_established",
    "execution_authority_granted",
    "execution_evidence_reuse_authorized",
    "execution_performed",
    "machine_setting_to_calibrated_power_relation_established",
    "network_authority_granted",
    "protocol_equivalence_established",
    "source_index_text_is_row_level_measurement_authority",
    "spot_size_transfer_authorized",
    "uncertainty_transfer_authorized",
    "uncertainty_transfer_established",
    "unrestricted_discovery_performed",
    "unrestricted_search_authorized",
    "unrestricted_search_performed",
}
_DENIED_LATE_TRUE_FIELDS = (
    set(_round3._DENIED_LATE_TRUE_FIELDS) | _ADDITIONAL_DENIED_LATE_TRUE_FIELDS
)

_COMPLETE_COMPARABILITY_GATE = {
    "decision_code": (
        "direct_nist_numerical_validation_blocked_by_response_and_protocol_incompatibility"
    ),
    "direct_nist_condition_comparability_established": False,
    "empirical_model_validation_established": False,
    "hypothesis_truth_established": False,
    "material_identity_established": True,
    "numerical_cross_source_validation_authorized": False,
    "protocol_compatibility_established": False,
    "response_compatibility_established": False,
    "scalar_residual_comparison_authorized": False,
    "scientific_status_changed": False,
    "source_globally_unusable_claimed": False,
    "source_remains_usable_for_mechanical_property_questions": True,
}

_NADERI_MATCH_RECEIPTS = {
    "naderi-ammt-in625-weaver-detail-reference": {
        "selected_text_extraction_mode": "layout",
        "matches": [
            {
                "matched_span_sha256": (
                    "23fbcf689b4310b59474f808a330b71a817766598a093f40aa63146bd9e1f3ec"
                ),
                "matched_span_utf8_bytes": 2218,
                "page_index_zero_based": 4,
                "text_extraction_mode": "layout",
            }
        ],
    },
    "naderi-reference-7-weaver-spot-size-paper": {
        "selected_text_extraction_mode": "plain",
        "matches": [
            {
                "matched_span_sha256": (
                    "00018095c67c6fb15d356cd3dee7cafcac73da029fbfcde5973edd6080039a4f"
                ),
                "matched_span_utf8_bytes": 135,
                "page_index_zero_based": 15,
                "text_extraction_mode": "plain",
            }
        ],
    },
    "naderi-reference-31-ammt-design": {
        "selected_text_extraction_mode": "plain",
        "matches": [
            {
                "matched_span_sha256": (
                    "bdf6cf87bed40c83aabf9b5ec03c130b518e86d79c678d014e3ae5a8e3db2489"
                ),
                "matched_span_utf8_bytes": 275,
                "page_index_zero_based": 15,
                "text_extraction_mode": "plain",
            }
        ],
    },
    "naderi-reference-32-lane-in625-protocol": {
        "selected_text_extraction_mode": "plain",
        "matches": [
            {
                "matched_span_sha256": (
                    "c47543dec9b1da931cbdefb48fd1e598f68ba4dcb82c42cf329145cc618cef1e"
                ),
                "matched_span_utf8_bytes": 253,
                "page_index_zero_based": 15,
                "text_extraction_mode": "plain",
            }
        ],
    },
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AutonomousProductionExactHeadRound4Error(message)


def _mapping(value: object, *, label: str) -> Mapping[str, Any]:
    _require(isinstance(value, Mapping), f"{label} must be an object")
    return value


def _trusted_repository_root() -> Path:
    return _merge_gate._trusted_repository_root().resolve(strict=True)


def _canonical_sha256(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _walk_round4_authority(value: object, *, label: str) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if key in _DENIED_LATE_TRUE_FIELDS:
                _require(
                    child is False,
                    f"{label} promoted fail-closed authority: {key}",
                )
            if key in _round3._ZERO_LATE_AUTHORITY_FIELDS:
                _require(
                    child == 0 and not isinstance(child, bool),
                    f"{label} promoted zero-valued authority: {key}",
                )
            _walk_round4_authority(child, label=label)
    elif isinstance(value, list):
        for child in value:
            _walk_round4_authority(child, label=label)


def _verify_late_authority_contract(
    root: Path,
    cycles: list[dict[str, Any]],
) -> None:
    if len(cycles) < 12:
        return
    for filename, self_field in _round3._LATE_SELF_HASH_SPECS:
        report = _merge_gate._load(root, filename)
        _merge_gate._verify_self_hash(
            report,
            self_field,
            label=f"round4 late-cycle report {filename}",
        )
        _walk_round4_authority(
            report,
            label=f"round4 late-cycle report {filename}",
        )


def _verify_terminal_capability_resolution(root: Path, cycles: list[dict[str, Any]]) -> None:
    if len(cycles) < 12:
        return

    gap = _merge_gate._load(root, "capability-gap-5.json")
    gap_sha = _merge_gate._verify_self_hash(
        gap,
        "capability_gap_sha256_without_self_field",
        label="terminal capability gap",
    )
    specification = _merge_gate._load(root, "capability-specification-5.json")
    _merge_gate._verify_self_hash(
        specification,
        "capability_specification_sha256_without_self_field",
        label="terminal capability specification",
    )
    registry = _merge_gate._load(root, "capability-registry-promoted-4.json")
    registry_sha = _merge_gate._verify_self_hash(
        registry,
        "capability_registry_sha256_without_self_field",
        label="terminal predecessor capability registry",
    )
    resolution = _merge_gate._load(root, "capability-resolution-5.json")

    requested_action = gap.get("requested_action_class")
    _require(
        isinstance(requested_action, str) and requested_action,
        "terminal capability gap requested action is invalid",
    )
    _require(
        specification.get("capability_gap_sha256") == gap_sha
        and specification.get("requested_action_class") == requested_action,
        "terminal capability specification is not bound to the authenticated gap",
    )
    expected_resolution = {
        "action_class": requested_action,
        "arbitrary_code_generation_performed": False,
        "candidate": None,
        "factory_catalogue_size": 4,
        "implementation_id": None,
        "policy_version": "1.3",
        "registry_sha256": registry_sha,
        "resolution_status": "no_bounded_candidate_available",
        "schema_version": "1.3",
        "unrestricted_discovery_performed": False,
    }
    _require(
        resolution == expected_resolution,
        "terminal capability resolution drifted from the authenticated fail-closed contract",
    )


def _load_naderi_policy() -> tuple[dict[str, Any], str]:
    trusted_root = _trusted_repository_root()
    path = (trusted_root / _NADERI_POLICY).resolve(strict=True)
    try:
        path.relative_to(trusted_root)
    except ValueError as exc:
        raise AutonomousProductionExactHeadRound4Error(
            "Naderi policy escaped the trusted checkout"
        ) from exc
    raw = path.read_bytes()
    value = json.loads(raw.decode("utf-8"))
    _require(isinstance(value, dict), "Naderi policy root must be an object")
    return value, hashlib.sha256(raw).hexdigest()


def _verify_naderi_claim_receipts(
    report: Mapping[str, Any],
    policy: Mapping[str, Any],
) -> None:
    policy_claims_value = policy.get("claims")
    report_claims_value = report.get("claims")
    _require(
        isinstance(policy_claims_value, list) and isinstance(report_claims_value, list),
        "Naderi policy/report claims must be lists",
    )
    policy_claims: dict[str, Mapping[str, Any]] = {}
    for value in policy_claims_value:
        claim = _mapping(value, label="Naderi policy claim")
        claim_id = claim.get("claim_id")
        _require(
            isinstance(claim_id, str) and claim_id not in policy_claims,
            "Naderi policy claim identity is invalid or duplicated",
        )
        policy_claims[claim_id] = claim

    report_claims: dict[str, Mapping[str, Any]] = {}
    for value in report_claims_value:
        claim = _mapping(value, label="Naderi report claim")
        claim_id = claim.get("claim_id")
        _require(
            isinstance(claim_id, str) and claim_id not in report_claims,
            "Naderi report claim identity is invalid or duplicated",
        )
        report_claims[claim_id] = claim

    _require(
        set(report_claims) == set(policy_claims) == set(_NADERI_MATCH_RECEIPTS),
        "Naderi claim receipt set drifted from the pinned policy",
    )
    for claim_id, policy_claim in policy_claims.items():
        report_claim = report_claims[claim_id]
        fragments = policy_claim.get("required_fragments")
        _require(
            isinstance(fragments, list)
            and all(isinstance(fragment, str) for fragment in fragments),
            f"Naderi policy required fragments are invalid: {claim_id}",
        )
        receipt = _NADERI_MATCH_RECEIPTS[claim_id]
        expected = {
            "allowed_text_extraction_modes": ["plain", "layout"],
            "claim_id": claim_id,
            "match_count": 1,
            "match_mode": policy_claim.get("match_mode"),
            "matched": True,
            "matches": receipt["matches"],
            "max_span_utf8_bytes": policy_claim.get("max_span_utf8_bytes"),
            "required_fragment_count": len(fragments),
            "required_fragments_sha256": _canonical_sha256(fragments),
            "scope": policy_claim.get("scope"),
            "selected_text_extraction_mode": receipt[
                "selected_text_extraction_mode"
            ],
            "source_text_persisted": False,
        }
        _require(
            dict(report_claim) == expected,
            f"Naderi canonical claim receipt drifted: {claim_id}",
        )


def _verify_naderi_source_provenance(root: Path, cycles: list[dict[str, Any]]) -> None:
    if len(cycles) < 12:
        return
    report = _merge_gate._load(root, "nist-mds2-2923-reference-chain-evidence.json")
    _merge_gate._verify_self_hash(
        report,
        "report_sha256_without_self_field",
        label="Naderi reference-chain evidence",
    )
    policy, policy_sha = _load_naderi_policy()
    source_policy = _mapping(policy.get("source"), label="Naderi policy source")
    source = _mapping(report.get("source"), label="Naderi report source")

    _require(
        report.get("policy_id") == policy.get("policy_id")
        and report.get("policy_sha256") == policy_sha
        and report.get("action_class") == policy.get("action_class"),
        "Naderi evidence is not bound to the tracked policy bytes",
    )
    _require(
        source.get("source_id") == source_policy.get("source_id")
        and source.get("requested_url") == source_policy.get("url")
        and source.get("final_url") == source_policy.get("url")
        and source.get("doi") == source_policy.get("doi")
        and source.get("source_sha256") == source_policy.get("expected_sha256")
        and source.get("source_size_bytes") == source_policy.get("expected_size_bytes"),
        "Naderi evidence source provenance drifted from the pinned source contract",
    )
    _require(
        source.get("source_bytes_persisted") is False
        and source.get("source_text_persisted") is False
        and source.get("row_level_measurement_authority") is False,
        "Naderi source persistence/row-authority boundary drifted",
    )
    _require(
        report.get("network_requests_performed") == 1
        and report.get("unrestricted_search_performed") is False
        and report.get("arbitrary_url_fetch_performed") is False
        and report.get("caller_authored_url_used") is False,
        "Naderi evidence network authority drifted",
    )
    _verify_naderi_claim_receipts(report, policy)


def _verify_complete_comparability_gate(root: Path) -> None:
    assessment = _merge_gate._load(root, "physical-comparability-assessment.json")
    _merge_gate._verify_self_hash(
        assessment,
        "assessment_sha256",
        label="physical comparability assessment",
    )
    _require(
        assessment.get("gate_decision") == _COMPLETE_COMPARABILITY_GATE,
        "physical comparability gate decision drifted from the complete fail-closed contract",
    )


def verify_exact_head_round4_boundaries(output_root: str | Path) -> None:
    root = Path(output_root).expanduser().resolve(strict=True)
    manifest = _merge_gate._load(root, "autonomous-production-manifest.json")
    cycles_value = manifest.get("cycles")
    _require(isinstance(cycles_value, list), "autonomous production cycles must be a list")
    cycles: list[dict[str, Any]] = []
    for index, value in enumerate(cycles_value, start=1):
        _require(isinstance(value, dict), f"cycle {index} must be an object")
        cycles.append(value)

    _verify_complete_comparability_gate(root)
    _verify_late_authority_contract(root, cycles)
    _verify_terminal_capability_resolution(root, cycles)
    _verify_naderi_source_provenance(root, cycles)


__all__ = [
    "AutonomousProductionExactHeadRound4Error",
    "verify_exact_head_round4_boundaries",
]
