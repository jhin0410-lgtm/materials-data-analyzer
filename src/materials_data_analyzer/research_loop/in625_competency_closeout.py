"""Bounded closeout for the first real IN625 autonomous-scientist episode.

This composer closes one benchmark episode without pretending that one diagnostic action
resolved the original NIST-vs-mds2 comparison.  It recomputes the original comparability
assessment from the same authenticated EvidencePackets, verifies that the new within-source
spot analysis did not silently change cross-source authority, re-plans from the verified
diagnostic result, publishes/re-consumes the canonical epistemic transition, and emits an
explicit external-evidence stop.

No new planner, executor, comparability rule, or scientific-authority mechanism is defined
here; this is a domain-level composition of the existing primitives.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .comparability_engine import AuthenticatedEvidenceInput, assess_comparability
from .evidence_packet import canonical_sha256
from .in625_competency_episode import build_in625_post_sensitivity_reassessment
from .in625_competency_epistemic import (
    SPOT_CONTEXT_CLAIM_ID,
    run_in625_spot_epistemic_transition_and_critic,
)

CLOSEOUT_SCHEMA_VERSION = "1.0"
CLOSEOUT_POLICY_VERSION = "1.0"


class In625CompetencyCloseoutError(ValueError):
    """Raised when a benchmark closeout would overstate the verified episode."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise In625CompetencyCloseoutError(message)


def _sha(value: object, field: str) -> str:
    _require(
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value),
        f"{field} must be lowercase SHA-256",
    )
    return value


def _authenticate_snapshot(
    value: Mapping[str, Any],
    *,
    trusted_sha256: str,
    embedded_sha_field: str,
    field: str,
) -> tuple[dict[str, Any], str]:
    trusted = _sha(trusted_sha256, f"trusted_{field}_sha256")
    snapshot = copy.deepcopy(dict(value))
    _require(
        canonical_sha256(snapshot) == trusted,
        f"{field} does not match external trust-root SHA-256",
    )
    unsigned = copy.deepcopy(snapshot)
    embedded = _sha(
        unsigned.pop(embedded_sha_field, None),
        f"{field}.{embedded_sha_field}",
    )
    _require(
        canonical_sha256(unsigned) == embedded,
        f"{field} embedded self-hash mismatch",
    )
    return snapshot, embedded


def _critic_statuses(report: Mapping[str, Any]) -> dict[str, str]:
    targets = report.get("target_reports")
    _require(isinstance(targets, list), "critic target_reports are missing")
    result: dict[str, str] = {}
    for index, item in enumerate(targets):
        _require(isinstance(item, Mapping), f"critic target_reports[{index}] is malformed")
        node_id = item.get("target_node_id")
        assessment = item.get("epistemic_assessment")
        _require(
            isinstance(node_id, str) and bool(node_id) and isinstance(assessment, Mapping),
            f"critic target_reports[{index}] is incomplete",
        )
        status = assessment.get("status")
        _require(isinstance(status, str) and bool(status), "critic status is missing")
        result[node_id] = status
    return result


def build_in625_competency_bounded_closeout(
    *,
    bootstrap: Mapping[str, Any],
    trusted_bootstrap_sha256: str,
    first_iteration: Mapping[str, Any],
    trusted_iteration_sha256: str,
    nist_evidence: AuthenticatedEvidenceInput,
    mds2_comparison_evidence: AuthenticatedEvidenceInput,
    direct_comparison_claim: Mapping[str, Any],
    trusted_claim_scope_sha256: str,
    request: Mapping[str, Any],
    authorization_receipt: Mapping[str, Any],
    trusted_authorization_sha256: str,
    sensitivity_result: Mapping[str, Any],
    trusted_result_sha256: str,
    spot_evidence_inputs: Sequence[AuthenticatedEvidenceInput],
    epistemic_output_root: str | Path,
) -> dict[str, Any]:
    """Close one real-evidence episode at the remaining external-evidence boundary."""

    bootstrap_snapshot, bootstrap_embedded = _authenticate_snapshot(
        bootstrap,
        trusted_sha256=trusted_bootstrap_sha256,
        embedded_sha_field="bootstrap_sha256",
        field="bootstrap",
    )
    iteration_snapshot, iteration_embedded = _authenticate_snapshot(
        first_iteration,
        trusted_sha256=trusted_iteration_sha256,
        embedded_sha_field="iteration_sha256",
        field="iteration",
    )
    _require(
        iteration_snapshot.get("bootstrap_sha256") == bootstrap_embedded,
        "first iteration does not descend from authenticated bootstrap",
    )

    initial_assessment = bootstrap_snapshot.get("comparability_assessment")
    _require(isinstance(initial_assessment, Mapping), "initial comparability assessment is missing")
    initial_assessment_sha = _sha(
        initial_assessment.get("assessment_sha256"),
        "bootstrap.comparability_assessment.assessment_sha256",
    )
    recomputed_assessment = assess_comparability(
        nist_evidence,
        mds2_comparison_evidence,
        claim_scope=direct_comparison_claim,
        trusted_claim_scope_sha256=trusted_claim_scope_sha256,
    )
    recomputed_sha = _sha(
        recomputed_assessment.get("assessment_sha256"),
        "recomputed comparability assessment_sha256",
    )
    _require(
        recomputed_assessment == dict(initial_assessment)
        and recomputed_sha == initial_assessment_sha,
        "within-source diagnostic action unexpectedly changed comparison-defining evidence",
    )
    _require(
        recomputed_assessment.get("assessment_status") != "COMPARABLE",
        "bounded closeout cannot proceed after direct comparability became established",
    )

    reassessment = build_in625_post_sensitivity_reassessment(
        bootstrap=bootstrap_snapshot,
        trusted_bootstrap_sha256=canonical_sha256(bootstrap_snapshot),
        first_iteration=iteration_snapshot,
        trusted_iteration_sha256=canonical_sha256(iteration_snapshot),
        sensitivity_result=sensitivity_result,
        trusted_result_sha256=trusted_result_sha256,
    )
    next_plan = reassessment.get("next_plan")
    _require(isinstance(next_plan, Mapping), "reassessment next_plan is missing")
    generated = next_plan.get("self_generated_gap_actions")
    _require(isinstance(generated, list), "reassessment generated actions are missing")
    generated_classes = {
        str(item.get("action_class"))
        for item in generated
        if isinstance(item, Mapping)
    }
    _require(
        "sensitivity_analysis" not in generated_classes,
        "verified spot sensitivity must not regenerate the same analysis design",
    )
    _require(
        "external_evidence_search" in generated_classes
        or "physical_experiment_design" in generated_classes,
        "reassessment did not expose the remaining external-evidence route",
    )
    selected_next = next_plan.get("selected_next_action")
    _require(
        selected_next is None or isinstance(selected_next, Mapping),
        "reassessment selected_next_action is malformed",
    )
    if isinstance(selected_next, Mapping):
        _require(
            selected_next.get("action_class") != "sensitivity_analysis",
            "reassessment selected the already-completed sensitivity analysis again",
        )

    epistemic = run_in625_spot_epistemic_transition_and_critic(
        bootstrap=bootstrap_snapshot,
        trusted_bootstrap_sha256=canonical_sha256(bootstrap_snapshot),
        request=request,
        authorization_receipt=authorization_receipt,
        trusted_authorization_sha256=trusted_authorization_sha256,
        sensitivity_result=sensitivity_result,
        trusted_result_sha256=trusted_result_sha256,
        evidence_inputs=spot_evidence_inputs,
        output_root=epistemic_output_root,
    )
    epistemic_boundary = epistemic.get("scientific_boundary")
    _require(isinstance(epistemic_boundary, Mapping), "epistemic scientific boundary is missing")
    _require(
        epistemic_boundary.get("positive_scientific_closeout_granted") is False
        and epistemic_boundary.get("protocol_equivalence_established") is False
        and epistemic_boundary.get("direct_numerical_cross_source_validation_authorized")
        is False,
        "epistemic critic path widened scientific authority",
    )
    post_critic = epistemic.get("post_action_critic")
    _require(isinstance(post_critic, Mapping), "post-action critic report is missing")
    critic_statuses = _critic_statuses(post_critic)
    _require(
        SPOT_CONTEXT_CLAIM_ID in critic_statuses,
        "post-action critic omitted the spot-context structural claim",
    )

    initial_plan = iteration_snapshot.get("plan")
    _require(isinstance(initial_plan, Mapping), "initial planner result is missing")
    selected_initial = initial_plan.get("selected_next_action")
    _require(isinstance(selected_initial, Mapping), "initial selected action is missing")

    request_sha = _sha(request.get("request_sha256"), "request.request_sha256")
    authorization_sha = _sha(
        authorization_receipt.get("authorization_sha256"),
        "authorization_receipt.authorization_sha256",
    )
    result_sha = _sha(
        sensitivity_result.get("result_sha256"),
        "sensitivity_result.result_sha256",
    )
    next_plan_sha = _sha(next_plan.get("plan_sha256"), "next_plan.plan_sha256")
    episode_transition_sha = _sha(
        epistemic.get("episode_transition_sha256"),
        "epistemic.episode_transition_sha256",
    )

    spot_packet_shas = sorted(
        _sha(item.packet.get("packet_sha256"), "spot EvidencePacket packet_sha256")
        for item in spot_evidence_inputs
    )
    _require(
        len(spot_packet_shas) == 18 and len(set(spot_packet_shas)) == 18,
        "bounded closeout requires 18 distinct authenticated spot EvidencePackets",
    )

    selected_next_summary = None
    if isinstance(selected_next, Mapping):
        selected_next_summary = {
            "action_id": selected_next.get("action_id"),
            "action_class": selected_next.get("action_class"),
            "execution_mode": selected_next.get("execution_mode"),
            "utility_score": selected_next.get("utility_score"),
        }

    result: dict[str, Any] = {
        "schema_version": CLOSEOUT_SCHEMA_VERSION,
        "policy_version": CLOSEOUT_POLICY_VERSION,
        "episode_stage": "bounded_scientific_closeout",
        "episode_status": "external_evidence_required_before_direct_comparison",
        "research_question": bootstrap_snapshot.get("research_question"),
        "ancestry": {
            "bootstrap_sha256": bootstrap_embedded,
            "first_iteration_sha256": iteration_embedded,
            "initial_comparability_assessment_sha256": initial_assessment_sha,
            "recomputed_comparability_assessment_sha256": recomputed_sha,
            "request_sha256": request_sha,
            "authorization_sha256": authorization_sha,
            "verified_sensitivity_result_sha256": result_sha,
            "reassessment_sha256": reassessment["reassessment_sha256"],
            "next_plan_sha256": next_plan_sha,
            "epistemic_transition_episode_sha256": episode_transition_sha,
            "nist_comparison_packet_sha256": nist_evidence.packet.get("packet_sha256"),
            "mds2_comparison_packet_sha256": mds2_comparison_evidence.packet.get("packet_sha256"),
            "spot_evidence_packet_sha256s": spot_packet_shas,
        },
        "comparability_reassessment": {
            "initial_status": initial_assessment.get("assessment_status"),
            "final_status": recomputed_assessment.get("assessment_status"),
            "assessment_unchanged": True,
            "direct_comparison_authorized": False,
        },
        "hypothesis_closeout": {
            "initial_portfolio": copy.deepcopy(bootstrap_snapshot.get("hypothesis_portfolio")),
            "post_sensitivity_portfolio": copy.deepcopy(
                reassessment.get("hypothesis_portfolio")
            ),
            "post_action_critic_status_by_node": critic_statuses,
            "hypothesis_truth_established": False,
        },
        "action_trace": {
            "initial_selected_action": {
                "action_id": selected_initial.get("action_id"),
                "action_class": selected_initial.get("action_class"),
                "execution_mode": selected_initial.get("execution_mode"),
                "utility_score": selected_initial.get("utility_score"),
            },
            "request_compiled": True,
            "explicit_authorization_authenticated": True,
            "execution_verified": True,
            "independent_recomputation_performed": True,
            "epistemic_transition_published_and_reauthenticated": True,
            "scientific_critic_rerun": True,
            "next_selected_action": selected_next_summary,
            "next_candidate_action_classes": sorted(generated_classes),
        },
        "bounded_conclusion": {
            "statement": (
                "The authenticated mds2 AMMT 195 W / 800 mm/s subset contains a stable "
                "within-source association between source-native spot diameter and melt-pool "
                "geometry, so spot/protocol context cannot be silently erased. The diagnostic "
                "action does not alter the original NIST-vs-mds2 ComparabilityAssessment; direct "
                "quantitative cross-source comparison remains unauthorized pending external "
                "experiment/protocol/calibration evidence."
            ),
            "new_verified_information_obtained": True,
            "scientific_status_promoted": False,
            "direct_numerical_cross_source_validation_authorized": False,
            "directly_comparable_mds2_rows": 0,
            "issue_76_exact_target_cells_satisfied": 0,
            "calibrated_power_relation_established": False,
            "protocol_equivalence_established": False,
            "causal_spot_size_effect_established": False,
        },
        "unresolved_external_evidence": copy.deepcopy(
            reassessment["updated_planning_state"]["unresolved_evidence_gaps"]
        ),
        "claims_not_authorized": [
            "NIST AM-Bench and mds2 rows are directly numerically comparable",
            "mds2 195 W machine setting equals an AM-Bench calibrated actual power",
            "spot diameter causally determines melt-pool geometry",
            "measurement protocols or response definitions are equivalent across sources",
            "the mds2 rows satisfy Issue #76 target cells",
            "the diagnostic analysis establishes predictive or engineering readiness",
            "the benchmark establishes final positive scientific truth",
        ],
        "stop_decision": {
            "stop_current_episode": True,
            "reason": "external_evidence_required_before_direct_comparison",
            "scientific_reason": (
                "The completed within-source analysis produced new diagnostic information but "
                "left the authenticated cross-source comparability assessment unchanged. The "
                "remaining blockers require source/experiment/protocol/calibration evidence "
                "that cannot be manufactured by repeating the same local analysis."
            ),
            "next_action_may_resume_episode": selected_next_summary is not None,
        },
        "authority_boundary": {
            "automatic_followup_execution_authorized": False,
            "positive_scientific_closeout_granted": False,
            "scientific_status_promoted": False,
            "physical_experiment_executed": False,
            "simulation_treated_as_empirical": False,
        },
    }
    result["closeout_sha256"] = canonical_sha256(result)
    return result


__all__ = [
    "CLOSEOUT_POLICY_VERSION",
    "CLOSEOUT_SCHEMA_VERSION",
    "In625CompetencyCloseoutError",
    "build_in625_competency_bounded_closeout",
]
