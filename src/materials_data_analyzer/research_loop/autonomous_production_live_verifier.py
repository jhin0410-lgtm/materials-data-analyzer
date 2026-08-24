"""Live autonomous-production verifier with explicit transport-stop provenance binding.

The full twelve-cycle success verifier remains in the sibling implementation module. This
wrapper hardens only the temporary NIST transport-stop branch. A transport outage is accepted
only when the report, policy qualification, authorization, bounded stop, predecessor scientific
artifacts, cycle chain, and manifest all authenticate the same exact mission-pinned request.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from . import autonomous_production_live_verifier_impl as _impl
from .nist_mds2_2923_network_policy import (
    ACTION_CLASS as NIST_ACTION_CLASS,
    CANDIDATE_ID as NIST_CANDIDATE_ID,
    POLICY_ID as NIST_POLICY_ID,
    PRODUCT_ID as NIST_PRODUCT_ID,
)
from .nist_mds2_2923_production_acquisition import (
    NistMds22923ProductionTransportError,
)

AutonomousProductionLiveVerificationError = (
    _impl.AutonomousProductionLiveVerificationError
)

# These are production-profile trust anchors, not values learned from the output being checked.
# They are already pinned by the immutable mission and are repeated here so a consistently
# re-hashed forged qualification/report/manifest cannot create its own root of trust.
_EXPECTED_MISSION_SHA256 = (
    "98d8730a4ba1221685267ed56cd7ae75f2ce60fcfdd8f8bb426a3825986c70ea"
)
_EXPECTED_NIST_POLICY_SHA256 = (
    "4b19c64f4f2c764f5315971c5afba16000763a4d307929ec5e463f42ee1cbebf"
)
_EXPECTED_PRODUCTION_PROFILE = "in625_zenodo_20503603_first_real_closed_loop"
_EXPECTED_TRANSPORT_EXCEPTION_TYPE = NistMds22923ProductionTransportError.__name__
_EXPECTED_COMPARABILITY_DECISION = (
    "direct_nist_numerical_validation_blocked_by_response_and_protocol_incompatibility"
)

_original_verify_transport_stop = _impl._verify_transport_stop


def _verify_transport_authority(
    root: Path,
    *,
    manifest: dict[str, Any],
    report: dict[str, Any],
    cycle3: dict[str, Any],
) -> None:
    qualification = _impl._load(root, "nist-network-policy-qualification.json")
    authorization = _impl._load(root, "nist-network-authorization.json")
    authorization_sha = _impl._verify_self_hash(
        authorization,
        "authorization_sha256",
        label="NIST network authorization",
    )

    _impl._require(
        qualification.get("qualification_status")
        == "exact_nist_mds2_2923_network_policy_authenticated",
        "NIST transport policy qualification status drifted",
    )
    for value, expected, label in (
        (qualification.get("mission_sha256"), _EXPECTED_MISSION_SHA256, "mission SHA"),
        (qualification.get("policy_id"), NIST_POLICY_ID, "policy id"),
        (qualification.get("policy_sha256"), _EXPECTED_NIST_POLICY_SHA256, "policy SHA"),
        (qualification.get("action_class"), NIST_ACTION_CLASS, "action class"),
        (qualification.get("candidate_id"), NIST_CANDIDATE_ID, "candidate id"),
        (qualification.get("product_id"), NIST_PRODUCT_ID, "product id"),
    ):
        _impl._require(value == expected, f"NIST transport qualification {label} drifted")
    _impl._require(
        qualification.get("network_access_performed") is False
        and qualification.get("unrestricted_search_authorized") is False
        and qualification.get("arbitrary_url_fetch_authorized") is False
        and qualification.get("scientific_status_changed") is False,
        "NIST transport qualification widened authority",
    )

    _impl._require(
        authorization.get("authorization_status")
        == "authorized_exact_nist_mds2_2923_acquisition",
        "NIST transport authorization status drifted",
    )
    for value, expected, label in (
        (authorization.get("mission_sha256"), _EXPECTED_MISSION_SHA256, "mission SHA"),
        (authorization.get("policy_id"), NIST_POLICY_ID, "policy id"),
        (authorization.get("policy_sha256"), _EXPECTED_NIST_POLICY_SHA256, "policy SHA"),
        (authorization.get("action_class"), NIST_ACTION_CLASS, "action class"),
        (authorization.get("candidate_id"), NIST_CANDIDATE_ID, "candidate id"),
        (authorization.get("product_id"), NIST_PRODUCT_ID, "product id"),
    ):
        _impl._require(value == expected, f"NIST transport authorization {label} drifted")
    _impl._require(
        authorization.get("network_access_performed") is False
        and authorization.get("unrestricted_search_authorized") is False
        and authorization.get("arbitrary_url_fetch_authorized") is False
        and authorization.get("caller_authored_url_used") is False
        and authorization.get("caller_authored_file_queue_used") is False
        and authorization.get("scientific_status_changed") is False,
        "NIST transport authorization widened authority",
    )

    _impl._require(
        report.get("source_system") == "NIST Public Data Repository"
        and report.get("product_id") == NIST_PRODUCT_ID
        and report.get("candidate_id") == NIST_CANDIDATE_ID
        and report.get("action_class") == NIST_ACTION_CLASS
        and report.get("policy_id") == NIST_POLICY_ID,
        "NIST transport report source/request identity drifted",
    )
    _impl._require(
        report.get("transport_exception_type") == _EXPECTED_TRANSPORT_EXCEPTION_TYPE,
        "NIST transport report did not prove the typed transient exception",
    )

    for observed, expected, label in (
        (report.get("policy_sha256"), _EXPECTED_NIST_POLICY_SHA256, "report policy"),
        (report.get("authorization_sha256"), authorization_sha, "report authorization"),
        (cycle3.get("network_policy_id"), NIST_POLICY_ID, "cycle policy id"),
        (cycle3.get("network_policy_sha256"), _EXPECTED_NIST_POLICY_SHA256, "cycle policy"),
        (cycle3.get("network_authorization_sha256"), authorization_sha, "cycle authorization"),
        (manifest.get("nist_mds2_2923_policy_sha256"), _EXPECTED_NIST_POLICY_SHA256, "manifest policy"),
        (
            manifest.get("nist_mds2_2923_network_authorization_sha256"),
            authorization_sha,
            "manifest authorization",
        ),
    ):
        _impl._require(observed == expected, f"NIST transport {label} binding mismatch")


def _verify_comparability_artifact(
    root: Path,
    *,
    manifest: dict[str, Any],
    cycle2: dict[str, Any],
) -> None:
    assessment = _impl._load(root, "physical-comparability-assessment.json")
    assessment_sha = _impl._verify_self_hash(
        assessment,
        "assessment_sha256",
        label="physical comparability assessment",
    )
    _impl._require(
        cycle2.get("comparability_assessment_sha256") == assessment_sha,
        "physical comparability assessment cycle binding mismatch",
    )
    _impl._require(
        manifest.get("comparability_assessment_sha256") == assessment_sha,
        "physical comparability assessment manifest binding mismatch",
    )
    _impl._require(
        assessment.get("action_class") == "reviewed_physical_comparability_assessment"
        and assessment.get("assessment_status")
        == "reviewed_comparability_assessed_direct_validation_blocked",
        "physical comparability assessment identity/status drifted",
    )
    gate = assessment.get("gate_decision")
    next_action = assessment.get("next_action")
    boundary = assessment.get("scientific_boundary")
    _impl._require(isinstance(gate, dict), "comparability gate decision is invalid")
    _impl._require(isinstance(next_action, dict), "comparability next action is invalid")
    _impl._require(isinstance(boundary, dict), "comparability scientific boundary is invalid")
    _impl._require(
        gate.get("decision_code") == _EXPECTED_COMPARABILITY_DECISION
        and gate.get("direct_nist_condition_comparability_established") is False
        and gate.get("numerical_cross_source_validation_authorized") is False
        and gate.get("scalar_residual_comparison_authorized") is False
        and gate.get("empirical_model_validation_established") is False
        and gate.get("hypothesis_truth_established") is False
        and gate.get("scientific_status_changed") is False,
        "physical comparability gate scientific authority drifted",
    )
    _impl._require(
        next_action.get("action_class") == NIST_ACTION_CLASS
        and next_action.get("candidate_id") == NIST_CANDIDATE_ID
        and next_action.get("network_access_performed") is False
        and next_action.get("automatic_execution_authorized") is False,
        "physical comparability next-action authority drifted",
    )
    _impl._require(
        boundary.get("numerical_cross_source_comparison_performed") is False
        and boundary.get("model_fit_performed") is False
        and boundary.get("empirical_model_validation_established") is False
        and boundary.get("hypothesis_truth_established") is False
        and boundary.get("automatic_scientific_promotion") is False
        and boundary.get("scientific_status_changed") is False,
        "physical comparability scientific boundary drifted",
    )


def _verify_pretransport_scientific_state(
    root: Path,
    manifest: dict[str, Any],
    cycles: list[Any],
) -> None:
    cycle1, cycle2 = cycles[0], cycles[1]
    _impl._require(isinstance(cycle1, dict), "transport predecessor cycle 1 is invalid")
    _impl._require(isinstance(cycle2, dict), "transport predecessor cycle 2 is invalid")
    cycle1_sha = _impl._verify_self_hash(cycle1, "cycle_sha256", label="transport cycle 1")
    _impl._verify_self_hash(cycle2, "cycle_sha256", label="transport cycle 2")
    _impl._require(cycle1.get("cycle_index") == 1, "transport cycle 1 index drifted")
    _impl._require(cycle2.get("cycle_index") == 2, "transport cycle 2 index drifted")
    _impl._require(
        cycle2.get("predecessor_cycle_sha256") == cycle1_sha,
        "transport predecessor cycle linkage drifted",
    )
    _impl._require(
        cycle1.get("selected_action_class") == "external_evidence_search"
        and cycle1.get("output_next_action_class")
        == "reviewed_physical_comparability_assessment"
        and cycle1.get("new_verified_information") is True
        and cycle1.get("scientific_status_changed") is False,
        "transport cycle 1 scientific state drifted",
    )
    _impl._require(
        cycle2.get("selected_action_class")
        == "reviewed_physical_comparability_assessment"
        and cycle2.get("direct_nist_condition_comparability_established") is False
        and cycle2.get("numerical_cross_source_validation_authorized") is False
        and cycle2.get("output_blocker")
        == "response_compatible_geometry_evidence_not_acquired"
        and cycle2.get("output_next_action_class") == NIST_ACTION_CLASS
        and cycle2.get("new_verified_information") is True
        and cycle2.get("scientific_status_changed") is False,
        "transport cycle 2 scientific state drifted",
    )
    _verify_comparability_artifact(root, manifest=manifest, cycle2=cycle2)

    exact_manifest_values = {
        "mission_id": "autonomous-in625-production-v1",
        "mission_sha256": _EXPECTED_MISSION_SHA256,
        "production_profile": _EXPECTED_PRODUCTION_PROFILE,
        "measurement_row_count": 200289,
        "complete_numeric_measurement_row_count": 200288,
        "incomplete_numeric_measurement_row_count": 1,
        "parallel_test_block_count": 19,
        "comparability_decision_code": _EXPECTED_COMPARABILITY_DECISION,
        "caller_authored_request_queue_used": False,
        "machine_authored_typed_request_used": True,
        "unrestricted_network_search_performed": False,
        "arbitrary_command_execution_performed": False,
        "missing_value_imputation_performed": False,
        "row_exclusion_performed": False,
        "empirical_model_validation_established": False,
        "hypothesis_truth_established": False,
        "numerical_cross_source_comparison_performed": False,
        "numerical_cross_source_validation_authorized": False,
        "direct_nist_condition_comparability_established": False,
        "response_compatible_geometry_evidence_acquired": False,
        "paper_evidence_promoted_to_row_level_authority": False,
        "preferred_geometry_candidate_id": NIST_CANDIDATE_ID,
        "scientific_status_changed": False,
        "global_evidence_unavailability_claimed": False,
        "positive_scientific_closeout_established": False,
    }
    for key, expected in exact_manifest_values.items():
        _impl._require(
            manifest.get(key) == expected,
            f"transport predecessor scientific field drifted: {key}",
        )

    # These stronger claims are not necessarily present before NIST intake. If present they
    # must retain the fail-closed value; a transport outage may never introduce them as true.
    _impl._require(
        manifest.get("direct_numerical_cross_source_validation_authorized") in (None, False),
        "transport predecessor authorized direct numerical cross-source validation",
    )
    _impl._require(
        manifest.get("bridge_established") in (None, False),
        "transport predecessor established a bridge",
    )
    _impl._require(
        manifest.get("directly_comparable_mds2_rows") in (None, 0),
        "transport predecessor invented directly comparable MDS2 rows",
    )
    _impl._require(
        manifest.get("issue_76_exact_target_cells_satisfied") in (None, 0),
        "transport predecessor promoted Issue #76 cells",
    )


def _verify_transport_stop(
    root: Path, manifest: dict[str, Any], stop: dict[str, Any]
) -> str:
    report = _impl._load(root, "nist-transport-unavailability.json")
    report_sha = _impl._verify_self_hash(
        report,
        "report_sha256_without_self_field",
        label="NIST transport report",
    )

    result = _original_verify_transport_stop(root, manifest, stop)

    _impl._require(
        manifest.get("stop") == stop,
        "bounded-stop artifact does not match manifest stop",
    )
    _impl._require(
        stop.get("candidate_id") == NIST_CANDIDATE_ID,
        "transport stop candidate identity drifted",
    )

    cycles = manifest.get("cycles")
    _impl._require(
        isinstance(cycles, list) and len(cycles) == 3,
        "transport cycle history drifted",
    )
    cycle3 = cycles[-1]
    _impl._require(isinstance(cycle3, dict), "transport cycle 3 is invalid")
    _impl._require(
        cycle3.get("predecessor_cycle_sha256") == cycles[1].get("cycle_sha256"),
        "transport cycle 3 predecessor binding mismatch",
    )
    _impl._require(
        cycle3.get("transport_unavailability_sha256") == report_sha,
        "transport report cycle binding mismatch",
    )
    _impl._require(
        manifest.get("nist_mds2_2923_transport_unavailability_sha256") == report_sha,
        "transport report manifest binding mismatch",
    )

    _verify_transport_authority(
        root,
        manifest=manifest,
        report=report,
        cycle3=cycle3,
    )
    _verify_pretransport_scientific_state(root, manifest, cycles)
    return result


# The delegated verifier resolves this global at runtime. Replace only the transport-stop
# branch so normal twelve-cycle success remains delegated to the existing implementation.
_impl._verify_transport_stop = _verify_transport_stop


def verify_live_autonomous_output(output_root: str | Path) -> str:
    return _impl.verify_live_autonomous_output(output_root)


def main(argv: list[str] | None = None) -> int:
    return _impl.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
