"""Verify the two valid outcomes of the public autonomous-production live replay.

A live run may finish in exactly one of two ways:

1. the existing full twelve-cycle evidence path succeeds and retains all scientific gates; or
2. the exact NIST MDS2-2923 acquisition is blocked by the narrow typed transport boundary,
   producing a self-hashed temporary-source-unavailability stop with no scientific intake.

No other partial result is accepted as a successful live replay.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from .autonomous_production_transport_recovery import TRANSPORT_STOP_REASON_CODE
from .nist_mds2_2923_network_policy import ACTION_CLASS as NIST_ACTION_CLASS


class AutonomousProductionLiveVerificationError(AssertionError):
    """Raised when a live autonomous-production output violates its outcome contract."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AutonomousProductionLiveVerificationError(message)


def _canonical_sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _load(root: Path, name: str) -> dict[str, Any]:
    path = root / name
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AutonomousProductionLiveVerificationError(
            f"required live artifact is not valid JSON: {name}"
        ) from exc
    _require(isinstance(value, dict), f"live artifact root must be an object: {name}")
    return value


def _verify_self_hash(value: dict[str, Any], field: str, *, label: str) -> str:
    digest = value.get(field)
    _require(isinstance(digest, str), f"{label} omitted {field}")
    unsigned = dict(value)
    unsigned.pop(field, None)
    _require(_canonical_sha(unsigned) == digest, f"{label} self-hash mismatch")
    return digest


def _verify_transport_stop(root: Path, manifest: dict[str, Any], stop: dict[str, Any]) -> str:
    _verify_self_hash(manifest, "manifest_sha256", label="transport-stop manifest")
    report = _load(root, "nist-transport-unavailability.json")
    _verify_self_hash(
        report,
        "report_sha256_without_self_field",
        label="NIST transport report",
    )

    _require(stop.get("status") == "stopped", "transport stop status drifted")
    _require(
        stop.get("reason_code") == TRANSPORT_STOP_REASON_CODE,
        "transport stop reason drifted",
    )
    _require(
        stop.get("requested_action_class") == NIST_ACTION_CLASS,
        "transport stop next action drifted",
    )
    _require(
        stop.get("scope") == "exact_current_authorized_nist_delivery_attempt",
        "transport stop scope widened",
    )
    _require(stop.get("retry_performed") is False, "transport stop performed a retry")
    _require(
        stop.get("retry_authorized_within_current_request_budget") is False,
        "transport stop claimed retry authority",
    )
    _require(
        stop.get("partial_output_reuse_authorized") is False,
        "transport stop authorized partial-output reuse",
    )
    _require(
        stop.get("alternative_evidence_lanes_remain_allowed") is True,
        "transport stop incorrectly closed alternative evidence lanes",
    )
    _require(
        stop.get("global_evidence_unavailability_claimed") is False,
        "transport stop overclaimed global evidence unavailability",
    )
    _require(
        stop.get("network_failure_interpreted_as_negative_scientific_evidence") is False,
        "transport stop converted a network failure into scientific evidence",
    )
    _require(
        stop.get("positive_scientific_closeout") is False,
        "transport stop claimed scientific closeout",
    )
    _require(
        stop.get("scientific_status_changed") is False,
        "transport stop changed scientific status",
    )

    _require(
        report.get("reason_code") == TRANSPORT_STOP_REASON_CODE,
        "transport report reason drifted",
    )
    _require(report.get("acquisition_completed") is False, "transport report claimed acquisition")
    _require(
        report.get("scientific_intake_performed") is False,
        "transport report claimed scientific intake",
    )
    _require(report.get("retry_performed") is False, "transport report performed a retry")
    _require(
        report.get("retry_authorized_within_current_request_budget") is False,
        "transport report claimed retry authority",
    )
    _require(
        report.get("network_request_budget_widened") is False,
        "transport report widened the request budget",
    )
    _require(
        report.get("allowed_hosts_widened") is False,
        "transport report widened allowed hosts",
    )
    _require(
        report.get("alternate_url_synthesized") is False,
        "transport report synthesized an alternate URL",
    )
    _require(
        report.get("partial_output_reuse_authorized") is False,
        "transport report authorized partial-output reuse",
    )
    _require(
        report.get("network_failure_interpreted_as_negative_scientific_evidence") is False,
        "transport report converted network failure to scientific evidence",
    )
    _require(
        report.get("global_evidence_unavailability_claimed") is False,
        "transport report overclaimed evidence unavailability",
    )
    _require(
        report.get("alternative_evidence_lanes_remain_allowed") is True,
        "transport report closed alternative evidence lanes",
    )
    _require(
        report.get("scientific_status_changed") is False,
        "transport report changed scientific status",
    )

    cycles = manifest.get("cycles")
    _require(isinstance(cycles, list) and len(cycles) == 3, "transport cycle history drifted")
    cycle3 = cycles[-1]
    _require(isinstance(cycle3, dict), "transport cycle 3 is invalid")
    _verify_self_hash(cycle3, "cycle_sha256", label="transport cycle 3")
    _require(cycle3.get("selected_action_class") == NIST_ACTION_CLASS, "cycle 3 action drifted")
    _require(cycle3.get("acquisition_completed") is False, "cycle 3 claimed acquisition")
    _require(
        cycle3.get("scientific_intake_performed") is False,
        "cycle 3 claimed scientific intake",
    )
    _require(cycle3.get("retry_performed") is False, "cycle 3 performed retry")
    _require(
        cycle3.get("partial_output_reuse_authorized") is False,
        "cycle 3 authorized partial-output reuse",
    )
    _require(
        cycle3.get("new_verified_operational_information") is True,
        "cycle 3 omitted verified operational outcome",
    )
    _require(
        cycle3.get("new_verified_scientific_information") is False,
        "cycle 3 invented scientific information",
    )
    _require(
        cycle3.get("scientific_status_changed") is False,
        "cycle 3 changed scientific status",
    )

    _require(
        manifest.get("nist_mds2_2923_acquisition_completed") is False,
        "transport manifest claimed MDS2 acquisition",
    )
    _require(
        manifest.get("nist_mds2_2923_scientific_intake_performed") is False,
        "transport manifest claimed MDS2 scientific intake",
    )
    _require(
        manifest.get("response_compatible_geometry_evidence_acquired") is False,
        "transport manifest claimed geometry evidence",
    )
    _require(
        manifest.get("generated_next_action_class") == NIST_ACTION_CLASS,
        "transport manifest changed the scientific next action",
    )
    _require(
        manifest.get("final_blocker") == "response_compatible_geometry_evidence_not_acquired",
        "transport manifest changed the scientific blocker",
    )
    _require(
        manifest.get("paper_and_other_source_lanes_remain_allowed") is True,
        "transport manifest closed other source lanes",
    )
    _require(
        manifest.get("network_failure_interpreted_as_negative_scientific_evidence") is False,
        "transport manifest converted outage into scientific evidence",
    )
    _require(
        manifest.get("global_evidence_unavailability_claimed") is False,
        "transport manifest overclaimed evidence unavailability",
    )
    _require(
        manifest.get("positive_scientific_closeout_established") is False,
        "transport manifest claimed scientific closeout",
    )
    _require(
        manifest.get("scientific_status_changed") is False,
        "transport manifest changed scientific status",
    )

    _require(
        not (root / "nist-scientific-intake.json").exists(),
        "transport stop must not emit NIST scientific intake",
    )
    _require(
        not (root / "nist-network-acquisition-receipt.json").exists(),
        "transport stop must not emit a completed NIST acquisition receipt",
    )
    return "typed_nist_transport_stop_verified"


def _verify_full_success(root: Path, manifest: dict[str, Any], stop: dict[str, Any]) -> str:
    nist = _load(root, "nist-scientific-intake.json")
    sources = _load(root, "multisource-source-acquisition.json")
    mapping = _load(root, "geometry-condition-mapping-assessment.json")
    bridge = _load(root, "calibration-protocol-bridge-capability-result.json")
    discovery = _load(root, "calibration-record-source-discovery.json")
    gap3 = _load(root, "capability-gap-3.json")
    candidate3 = _load(root, "capability-candidate-3.json")
    verification3 = _load(root, "capability-verification-3.json")
    registry3 = _load(root, "capability-registry-promoted-3.json")
    policy3 = _load(root, "nist-ammt-candidate-acquisition-policy-qualification.json")
    authorization3 = _load(root, "nist-ammt-derived-candidate-authorization.json")
    acquisition3 = _load(root, "nist-ammt-calibration-candidate-acquisition.json")
    assessment3 = _load(root, "nist-ammt-calibration-candidate-bridge-assessment.json")
    gap4 = _load(root, "capability-gap-4.json")
    spec4 = _load(root, "capability-specification-4.json")
    predecessor_resolution4 = _load(root, "capability-resolution-4.json")
    candidate_reauth4 = _load(root, "capability-resolution-4-derived.json")
    candidate4 = _load(root, "capability-candidate-4.json")
    verification4 = _load(root, "capability-verification-4.json")
    registry4 = _load(root, "capability-registry-promoted-4.json")
    resolved4 = _load(root, "capability-post-promotion-resolution-4.json")
    reference_policy = _load(root, "nist-mds2-2923-reference-chain-policy-qualification.json")
    reference_evidence = _load(root, "nist-mds2-2923-reference-chain-evidence.json")
    reference_graph = _load(root, "mds2-2923-experiment-identity-reference-chain.json")
    gap5 = _load(root, "capability-gap-5.json")
    resolution5 = _load(root, "capability-resolution-5.json")

    _require(manifest["schema_version"] == "1.8", "full-success schema drifted")
    _require(manifest["policy_version"] == "1.8", "full-success policy drifted")
    _require(manifest["measurement_row_count"] == 200289, "external row count drifted")
    _require(manifest["complete_numeric_measurement_row_count"] == 200288, "complete row count drifted")
    _require(manifest["incomplete_numeric_measurement_row_count"] == 1, "incomplete row count drifted")
    _require(manifest["caller_authored_request_queue_used"] is False, "caller queue authority widened")
    _require(manifest["machine_authored_typed_request_used"] is True, "typed request binding missing")
    _require(manifest["unrestricted_network_search_performed"] is False, "unrestricted search occurred")
    _require(manifest["arbitrary_command_execution_performed"] is False, "arbitrary command occurred")
    _require(manifest["missing_value_imputation_performed"] is False, "missing value imputation occurred")
    _require(manifest["row_exclusion_performed"] is False, "row exclusion occurred")

    _verify_self_hash(nist, "report_sha256_without_self_field", label="NIST scientific intake")
    _require(nist["in625_inventory"]["measurement_row_count"] == 178, "NIST row count drifted")
    _require(nist["in625_inventory"]["physical_track_count"] == 106, "NIST track count drifted")
    _require(
        nist["in625_inventory"]["machine_measurement_counts"] == {"AMMT": 34, "EOS M270": 144},
        "NIST machine counts drifted",
    )
    _require(nist["measurement_semantics"]["calibration_conversion_performed"] is False, "calibration conversion occurred")
    _require(nist["issue_76"]["exact_target_cells_satisfied"] == 0, "issue #76 gate changed")
    _require(sources["source_count"] == 8, "multisource count drifted")
    _require(sources["network_requests_performed"] == 8, "multisource request count drifted")
    _require(sources["all_claim_anchors_matched"] is True, "multisource anchors failed")
    _require(sources["paper_claims_promoted_to_row_level_authority"] is False, "paper authority promoted")
    _require(mapping["gate_decision"]["eos_rows_excluded_from_direct_mapping"] == 144, "EOS exclusion drifted")
    _require(mapping["gate_decision"]["directly_comparable_mds2_rows"] == 0, "directly comparable rows changed")
    _require(mapping["gate_decision"]["direct_numerical_validation_authorized"] is False, "numerical validation authorized")
    _require(bridge["bridge_established"] is False, "bridge unexpectedly established")
    _require(bridge["directly_comparable_mds2_rows"] == 0, "bridge comparable rows changed")
    _require(bridge["issue_76_exact_target_cells_satisfied"] == 0, "bridge issue #76 gate changed")

    _require(discovery["discovery_status"] == "official_nist_ammt_publication_index_reviewed", "AMMT discovery status drifted")
    _require(discovery["candidate_count"] > 0, "AMMT discovery candidates missing")
    _require(discovery["candidate_links_followed"] == 0, "discovery followed candidate links")
    _require(discovery["candidate_urls_gain_acquisition_authority"] is False, "discovery URLs gained authority")
    _require(discovery["next_action"]["action_class"] == "experiment_specific_calibration_record_candidate_acquisition", "AMMT next action drifted")
    rank1 = next(item for item in discovery["candidates"] if item["rank"] == 1)
    _require(rank1["link_host"] == "www.nist.gov", "rank-1 NIST host drifted")
    _require(rank1["candidate_url_followed"] is False, "rank-1 candidate was followed during discovery")
    _require(rank1["acquisition_authorized"] is False, "rank-1 candidate got discovery authority")

    _require(gap3["gap_class"] == "missing_source_adapter", "capability gap 3 drifted")
    _require(candidate3["state"] == "candidate", "capability candidate 3 state drifted")
    _require(candidate3["implementation_id"] == "nist-ammt-derived-calibration-candidate-acquisition-v1", "capability candidate 3 implementation drifted")
    _require(candidate3["network_authority_granted"] is False, "candidate 3 gained network authority")
    _require(candidate3["execution_authority_granted"] is False, "candidate 3 gained execution authority")
    _require(candidate3["self_promotion_requested"] is False, "candidate 3 requested self promotion")
    _require(verification3["promotion_eligible"] is True, "candidate 3 verification failed")
    _require(verification3["all_required_checks_passed"] is True, "candidate 3 checks failed")
    _require(
        any(
            item["action_class"] == "experiment_specific_calibration_record_candidate_acquisition"
            and item["state"] == "verified"
            for item in registry3["records"]
        ),
        "candidate 3 was not verified in promoted registry",
    )

    _require(policy3["qualification_status"] == "exact_nist_ammt_candidate_acquisition_policy_authenticated", "candidate acquisition policy drifted")
    _require(policy3["required_candidate_rank"] == 1, "required candidate rank drifted")
    _require(policy3["candidate_page_allowed_hosts"] == ["www.nist.gov"], "candidate page hosts widened")
    _require(policy3["full_text_allowed_hosts"] == ["tsapps.nist.gov"], "full-text hosts widened")
    _require(policy3["max_requests"] == 2, "candidate acquisition request budget drifted")
    _require(policy3["network_access_performed"] is False, "policy qualification performed network access")

    _require(authorization3["authorization_type"] == "provenance_derived_nist_candidate_acquisition", "candidate authorization type drifted")
    _require(authorization3["candidate_rank"] == 1, "authorized candidate rank drifted")
    _require(authorization3["candidate_id"] == rank1["candidate_id"], "authorized candidate identity drifted")
    _require(authorization3["candidate_url"] == rank1["url"], "authorized candidate URL drifted")
    _require(authorization3["candidate_url_derived_from_discovery"] is True, "candidate URL was not provenance-derived")
    _require(authorization3["full_text_url_derived_from_candidate_page"] is False, "full-text URL existed before candidate acquisition")
    _require(authorization3["caller_authored_url_used"] is False, "caller-authored URL used")
    _require(authorization3["scientific_status_change_authorized"] is False, "candidate acquisition gained scientific authority")

    _require(acquisition3["acquisition_status"] == "derived_nist_calibration_candidate_and_full_text_acquired", "derived candidate acquisition status drifted")
    _require(acquisition3["network_requests_performed"] == 2, "derived candidate request count drifted")
    _require(acquisition3["candidate_url_derived_from_discovery"] is True, "acquired candidate URL was not derived")
    _require(acquisition3["full_text_url_derived_from_candidate_page"] is True, "full-text URL was not derived from page")
    _require(acquisition3["caller_authored_url_used"] is False, "caller URL used in derived acquisition")
    _require(acquisition3["unrestricted_search_performed"] is False, "unrestricted search occurred in derived acquisition")
    _require(acquisition3["literature_promoted_to_row_level_measurement_authority"] is False, "literature promoted to row authority")
    _require(acquisition3["acquisition_success_establishes_calibration_bridge"] is False, "acquisition success established bridge")
    _require(acquisition3["full_text"]["final_url"].startswith("https://tsapps.nist.gov/publication/get_pdf.cfm?pub_id="), "full-text final URL drifted")
    _require(acquisition3["full_text"]["page_count"] > 0, "full-text page count invalid")
    _require(acquisition3["full_text"]["extractor"] == "pypdf", "full-text extractor drifted")
    _require(acquisition3["full_text"]["raw_bytes_persisted"] is False, "raw full-text bytes persisted")
    claims = {item["claim_id"]: item for item in acquisition3["claim_receipts"]}
    _require(claims["digital_camera_in_situ_calibration_methodology"]["matched"] is True, "digital camera claim missing")
    _require(claims["open_platform_testbed_experiment_scope"]["matched"] is True, "testbed scope claim missing")
    _require(claims["spot_calibration_200w_pulsed_condition"]["matched"] is True, "spot calibration claim missing")
    _require(claims["d4sigma_spot_definition"]["matched"] is True, "D4sigma claim missing")
    _require(claims["explicit_mds2_2923_identity"]["matched"] is False, "explicit MDS2 identity was inferred")
    _require(claims["explicit_machine_setting_actual_power_bridge"]["matched"] is False, "power bridge was inferred")

    _require(assessment3["evidence_scope"]["digital_camera_in_situ_calibration_methodology_established"] is True, "calibration methodology not established")
    _require(assessment3["evidence_scope"]["d4sigma_spot_definition_established"] is True, "D4sigma definition not established")
    _require(assessment3["experiment_specific_bridge"]["exact_mds2_2923_experiment_identity_established"] is False, "exact experiment identity was inferred")
    _require(assessment3["experiment_specific_bridge"]["exact_machine_setting_to_calibrated_power_relation_established"] is False, "machine-setting power relation was inferred")
    _require(assessment3["experiment_specific_bridge"]["bridge_established"] is False, "assessment bridge unexpectedly established")
    _require(assessment3["gate_decision"]["directly_comparable_mds2_rows"] == 0, "assessment comparable rows changed")
    _require(assessment3["gate_decision"]["direct_numerical_cross_source_validation_authorized"] is False, "assessment authorized direct numerical validation")
    _require(assessment3["gate_decision"]["issue_76_exact_target_cells_satisfied"] == 0, "assessment issue #76 gate changed")
    _require(assessment3["next_action"]["action_class"] == "mds2_2923_experiment_identity_reference_chain_assessment", "assessment next action drifted")

    _require(gap4["gap_class"] == "missing_analysis_executor", "capability gap 4 drifted")
    _require(predecessor_resolution4["resolution_status"] == "bounded_candidate_discovered", "predecessor resolution 4 drifted")
    predecessor_candidate4 = predecessor_resolution4["candidate"]
    _require(predecessor_candidate4["capability_specification_sha256"] == spec4["capability_specification_sha256_without_self_field"], "capability spec 4 binding drifted")
    _require(predecessor_candidate4["capability_candidate_sha256_without_self_field"] == candidate4["capability_candidate_sha256_without_self_field"], "capability candidate 4 binding drifted")
    _require(candidate_reauth4["resolution_status"] == "predecessor_candidate_reauthenticated", "candidate 4 reauthentication failed")
    _require(candidate_reauth4["capability_specification_sha256"] == spec4["capability_specification_sha256_without_self_field"], "candidate 4 specification reauth drifted")
    _require(candidate_reauth4["capability_candidate_sha256"] == candidate4["capability_candidate_sha256_without_self_field"], "candidate 4 digest reauth drifted")
    _require(candidate_reauth4["candidate_rediscovery_performed"] is False, "candidate 4 was rediscovered")
    _require(candidate_reauth4["unrestricted_discovery_performed"] is False, "candidate 4 used unrestricted discovery")
    _require(candidate4["state"] == "candidate", "candidate 4 state drifted")
    _require(candidate4["implementation_id"] == "mds2-2923-experiment-identity-reference-chain-v1", "candidate 4 implementation drifted")
    _require(candidate4["network_authority_granted"] is False, "candidate 4 gained network authority")
    _require(candidate4["execution_authority_granted"] is False, "candidate 4 gained execution authority")
    _require(candidate4["self_promotion_requested"] is False, "candidate 4 requested self promotion")
    _require(verification4["semantic_spec_contract_verified"] is True, "candidate 4 semantic spec failed")
    _require(verification4["all_required_checks_passed"] is True, "candidate 4 checks failed")
    _require(verification4["promotion_eligible"] is True, "candidate 4 not promotion eligible")
    _require(verification4["real_source_smoke_receipt"]["network_requests_performed"] == 1, "candidate 4 smoke request count drifted")
    _require(verification4["real_source_smoke_receipt"]["execution_evidence_reuse_authorized"] is False, "smoke evidence reuse authorized")
    _require(
        any(
            item["action_class"] == "mds2_2923_experiment_identity_reference_chain_assessment"
            and item["state"] == "verified"
            for item in registry4["records"]
        ),
        "candidate 4 was not verified in registry",
    )
    _require(resolved4["resolution_status"] == "verified_capability_resolved", "capability 4 post-promotion resolution failed")
    _require(resolved4["implementation_id"] == "mds2-2923-experiment-identity-reference-chain-v1", "resolved capability 4 implementation drifted")

    _require(reference_policy["qualification_status"] == "exact_nist_mds2_2923_reference_chain_policy_authenticated", "reference-chain policy drifted")
    _require(reference_policy["allowed_hosts"] == ["tsapps.nist.gov"], "reference-chain hosts widened")
    _require(reference_policy["max_requests"] == 1, "reference-chain request budget drifted")
    _require(reference_policy["network_access_performed"] is False, "reference policy performed network access")
    _require(reference_evidence["acquisition_status"] == "exact_naderi_reference_chain_evidence_acquired", "Naderi reference evidence status drifted")
    _require(reference_evidence["network_requests_performed"] == 1, "Naderi reference request count drifted")
    _require(reference_evidence["all_claims_matched"] is True, "Naderi reference claims failed")
    if "raw_bytes_persisted" in reference_evidence["source"]:
        _require(reference_evidence["source"]["raw_bytes_persisted"] is False, "Naderi raw bytes persisted")
    else:
        _require(reference_evidence["source"]["source_bytes_persisted"] is False, "Naderi source bytes persisted")
    _require(reference_evidence["literature_promoted_to_row_level_measurement_authority"] is False, "Naderi literature promoted to row authority")
    _require(reference_evidence["reference_chain_promoted_to_power_conversion"] is False, "reference chain promoted to power conversion")

    identity = reference_graph["experiment_identity"]
    gate = reference_graph["calibration_and_protocol_gate"]
    _require(reference_graph["reference_graph"]["transitive_authority_promotion_allowed"] is False, "transitive authority promotion enabled")
    _require(reference_graph["condition_signature"]["signature_match"] is True, "condition signature no longer matches")
    _require(identity["dataset_to_weaver_association_established"] is True, "dataset-Weaver association missing")
    _require(identity["dataset_to_naderi_association_established"] is True, "dataset-Naderi association missing")
    _require(identity["naderi_to_weaver_experiment_detail_reference_established"] is True, "Naderi-Weaver reference missing")
    _require(identity["exact_mds2_rows_to_weaver_experiment_established"] is False, "exact MDS2-row/Weaver identity inferred")
    _require(identity["exact_mds2_experiment_identity_established"] is False, "exact MDS2 experiment identity inferred")
    _require(gate["weaver_full_text_acquired"] is False, "Weaver full text unexpectedly acquired")
    _require(gate["machine_setting_to_calibrated_power_relation_established"] is False, "machine-setting power relation established")
    _require(gate["spot_size_transfer_authorized"] is False, "spot-size transfer authorized")
    _require(gate["protocol_equivalence_established"] is False, "protocol equivalence established")
    _require(gate["uncertainty_transfer_authorized"] is False, "uncertainty transfer authorized")
    _require(gate["directly_comparable_mds2_rows"] == 0, "reference graph comparable rows changed")
    _require(gate["direct_numerical_cross_source_validation_authorized"] is False, "reference graph authorized numerical validation")
    _require(gate["cross_machine_pooling_authorized"] is False, "cross-machine pooling authorized")
    _require(gate["issue_76_exact_target_cells_satisfied"] == 0, "reference graph issue #76 gate changed")
    _require(reference_graph["next_action"]["action_class"] == "weaver_2021_spot_size_full_text_derived_acquisition", "reference graph next action drifted")
    _require(reference_graph["next_action"]["automatic_acquisition_authorized"] is False, "Weaver automatic acquisition authority drifted")
    _require(reference_graph["next_action"]["caller_authored_url_authorized"] is False, "caller-authored Weaver URL authorized")

    _require(len(manifest["cycles"]) == 12, "full-success cycle count drifted")
    cycle9, cycle10, cycle11, cycle12 = manifest["cycles"][8:12]
    _require(cycle9["selected_action_class"] == "experiment_specific_calibration_record_candidate_acquisition", "cycle 9 action drifted")
    _require(cycle9["bounded_candidate_discovered"] is True, "cycle 9 candidate missing")
    _require(cycle10["capability_available"] is True, "cycle 10 capability unavailable")
    _require(cycle10["research_action_resumed"] is True, "cycle 10 did not resume")
    _require(cycle10["network_requests_performed"] == 2, "cycle 10 request count drifted")
    _require(cycle10["bridge_established"] is False, "cycle 10 established bridge")
    _require(cycle10["output_next_action_class"] == "mds2_2923_experiment_identity_reference_chain_assessment", "cycle 10 next action drifted")
    _require(cycle11["selected_action_class"] == "mds2_2923_experiment_identity_reference_chain_assessment", "cycle 11 action drifted")
    _require(cycle11["bounded_candidate_discovered"] is False, "cycle 11 rediscovered candidate")
    _require(cycle11["predecessor_candidate_reauthenticated"] is True, "cycle 11 predecessor reauth failed")
    _require(cycle11["candidate_rediscovery_performed"] is False, "cycle 11 candidate rediscovery occurred")
    _require(cycle11["capability_available"] is False, "cycle 11 capability unexpectedly available")
    _require(cycle11["arbitrary_code_generation_performed"] is False, "cycle 11 arbitrary code generation occurred")
    _require(cycle12["capability_available"] is True, "cycle 12 capability unavailable")
    _require(cycle12["research_action_resumed"] is True, "cycle 12 did not resume")
    _require(cycle12["execution_network_requests_performed"] == 1, "cycle 12 execution request count drifted")
    _require(cycle12["verifier_smoke_network_requests_performed"] == 1, "cycle 12 smoke request count drifted")
    _require(cycle12["dataset_publication_association_established"] is True, "cycle 12 dataset-publication association missing")
    _require(cycle12["condition_signature_match_established"] is True, "cycle 12 condition signature missing")
    _require(cycle12["exact_mds2_experiment_identity_established"] is False, "cycle 12 exact identity inferred")
    _require(cycle12["bridge_established"] is False, "cycle 12 bridge established")
    _require(cycle12["directly_comparable_mds2_rows"] == 0, "cycle 12 comparable rows changed")
    _require(cycle12["issue_76_exact_target_cells_satisfied"] == 0, "cycle 12 issue #76 gate changed")
    _require(cycle12["output_next_action_class"] == "weaver_2021_spot_size_full_text_derived_acquisition", "cycle 12 next action drifted")

    _require(gap5["gap_class"] == "missing_source_adapter", "capability gap 5 drifted")
    _require(resolution5["resolution_status"] == "no_bounded_candidate_available", "capability resolution 5 drifted")
    _require(manifest["third_capability_candidate_promoted"] is True, "third capability not promoted")
    _require(manifest["third_research_action_resumed"] is True, "third action not resumed")
    _require(manifest["derived_candidate_acquisition_executed"] is True, "derived candidate acquisition not executed")
    _require(manifest["fourth_capability_candidate_discovered"] is True, "fourth candidate not discovered")
    _require(manifest["fourth_capability_candidate_promoted"] is True, "fourth candidate not promoted")
    _require(manifest["fourth_research_action_resumed"] is True, "fourth action not resumed")
    _require(manifest["fourth_candidate_reauthenticated_from_predecessor"] is True, "fourth candidate not reauthenticated")
    _require(manifest["fourth_candidate_rediscovery_performed"] is False, "fourth candidate rediscovery occurred")
    _require(manifest["dataset_to_weaver_association_established"] is True, "manifest dataset-Weaver association missing")
    _require(manifest["naderi_to_weaver_experiment_detail_reference_established"] is True, "manifest Naderi-Weaver reference missing")
    _require(manifest["mds2_195_800_condition_signature_match"] is True, "manifest 195/800 signature mismatch")
    _require(manifest["exact_mds2_experiment_identity_established"] is False, "manifest exact MDS2 identity inferred")
    _require(manifest["exact_machine_setting_to_calibrated_power_relation_established"] is False, "manifest power relation inferred")
    _require(manifest["bridge_established"] is False, "manifest bridge established")
    _require(manifest["directly_comparable_mds2_rows"] == 0, "manifest comparable rows changed")
    _require(manifest["direct_numerical_cross_source_validation_authorized"] is False, "manifest direct validation authorized")
    _require(manifest["issue_76_exact_target_cells_satisfied"] == 0, "manifest issue #76 gate changed")
    _require(manifest["fifth_capability_gap_emitted"] is True, "fifth capability gap missing")
    _require(manifest["generated_next_action_class"] == "weaver_2021_spot_size_full_text_derived_acquisition", "manifest next action drifted")
    _require(manifest["final_blocker"] == "weaver_primary_full_text_acquisition_capability_not_established", "manifest final blocker drifted")
    _require(manifest["scientific_status_changed"] is False, "manifest scientific status changed")
    _require(manifest["positive_scientific_closeout_established"] is False, "manifest positive closeout established")
    _require(manifest["global_evidence_unavailability_claimed"] is False, "manifest global evidence unavailability claimed")

    _require(stop["reason_code"] == "capability_expansion_required", "full-success stop reason drifted")
    _require(stop["requested_action_class"] == "weaver_2021_spot_size_full_text_derived_acquisition", "full-success stop action drifted")
    _require(stop["bounded_candidate_discovered"] is False, "full-success stop candidate drifted")
    _require(stop["caller_authored_url_used"] is False, "full-success stop used caller URL")
    _require(stop["arbitrary_code_generation_performed"] is False, "full-success stop used arbitrary code generation")
    _require(stop["global_evidence_unavailability_claimed"] is False, "full-success stop overclaimed evidence unavailability")
    return "full_reference_chain_success_verified"


def verify_live_autonomous_output(output_root: str | Path) -> str:
    root = Path(output_root).expanduser().resolve(strict=True)
    manifest = _load(root, "autonomous-production-manifest.json")
    stop = _load(root, "bounded-stop.json")
    if stop.get("reason_code") == TRANSPORT_STOP_REASON_CODE:
        return _verify_transport_stop(root, manifest, stop)
    return _verify_full_success(root, manifest, stop)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print(
            "usage: python -m materials_data_analyzer.research_loop.autonomous_production_live_verifier <output-root>",
            file=sys.stderr,
        )
        return 2
    try:
        outcome = verify_live_autonomous_output(args[0])
    except (AutonomousProductionLiveVerificationError, FileNotFoundError, NotADirectoryError) as exc:
        print(f"Autonomous live verification failed: {exc}", file=sys.stderr)
        return 1
    print(outcome)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
