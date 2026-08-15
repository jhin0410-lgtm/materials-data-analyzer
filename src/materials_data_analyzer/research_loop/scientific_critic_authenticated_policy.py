"""Scientific Critic adapter for independently authenticated current transition bundles.

This policy invokes the bundle consumer itself. It never accepts a caller-supplied
consumer report as scientific authority and never mutates the persistent epistemic graph
or the evaluator assessment embedded in the base critic report.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .authenticated_transition_consumer import authenticate_transition_bundle
from .scientific_critic import ScientificCriticError
from .scientific_critic_policy import build_policy_hardened_scientific_critic_report

AUTHENTICATED_SCIENTIFIC_CRITIC_POLICY_VERSION = "1.0"
_NEGATIVE_RELATIONS = {"contradicts", "falsifies"}


def _target_report_by_id(report: Mapping[str, Any], target_id: str) -> dict[str, Any] | None:
    raw = report.get("target_reports")
    if not isinstance(raw, list):
        raise ScientificCriticError("critic report target_reports are malformed")
    found: dict[str, Any] | None = None
    for item in raw:
        if not isinstance(item, dict):
            raise ScientificCriticError("critic target report is malformed")
        if item.get("target_node_id") != target_id:
            continue
        if found is not None:
            raise ScientificCriticError(
                f"critic report contains duplicate target report: {target_id}"
            )
        found = item
    return found


def _append_unique_by_key(
    values: list[dict[str, Any]],
    item: dict[str, Any],
    *,
    key: str,
) -> None:
    identity = item.get(key)
    if any(isinstance(existing, Mapping) and existing.get(key) == identity for existing in values):
        return
    values.append(item)


def _apply_authenticated_directional_advisory(
    target: dict[str, Any], *, consumer: Mapping[str, Any]
) -> None:
    relation = str(consumer["relation"])
    target_id = str(consumer["target_node_id"])
    edge_id = str(consumer["inference_edge_id"])
    result_node_id = str(consumer["result_node_id"])
    inference_scope = str(consumer["inference_scope"])

    assessment = target.get("epistemic_assessment")
    if not isinstance(assessment, Mapping):
        raise ScientificCriticError("critic target epistemic_assessment is malformed")
    findings = target.get("critic_findings")
    actions = target.get("discriminating_actions")
    if not isinstance(findings, list) or not isinstance(actions, list):
        raise ScientificCriticError("critic target proposal collections are malformed")
    if not all(isinstance(item, dict) for item in findings + actions):
        raise ScientificCriticError("critic target proposal item is malformed")

    target["authenticated_directional_assessment"] = {
        "schema_version": "1.0",
        "transition_id": consumer["transition_id"],
        "inference_edge_id": edge_id,
        "result_node_id": result_node_id,
        "target_node_id": target_id,
        "relation": relation,
        "inference_scope": inference_scope,
        "current_transition_exact_provenance_authenticated": True,
        "persistent_graph_assessment_level": "diagnostic",
        "persistent_graph_or_evaluator_status_changed": False,
        "critic_directional_advisory_authorized": True,
        "scientific_status_promotion_authorized": False,
        "support_independence_established": False,
        "calibrated_confidence_established": False,
        "execution_authorized": False,
        "positive_closeout_granted": False,
    }

    if relation == "supports":
        _append_unique_by_key(
            findings,
            {
                "finding_id": f"critic:{target_id}:authenticated-directional-support",
                "code": "AUTHENTICATED_DIRECTIONAL_SUPPORT_PRESENT",
                "severity": "medium",
                "statement": (
                    "The current bundle independently authenticates the exact diagnostic support "
                    "edge for this target within its declared scope."
                ),
                "rationale": (
                    "Exact-edge provenance is sufficient for a critic-level directional advisory, "
                    "but it does not promote the persistent graph edge, establish source independence, "
                    "calibrate confidence, or grant positive scientific closeout."
                ),
                "edge_ids": [edge_id],
                "node_ids": [result_node_id],
                "scientific_status_changed": False,
            },
            key="finding_id",
        )
        return

    if relation not in _NEGATIVE_RELATIONS:
        raise ScientificCriticError(
            f"authenticated directional relation is unsupported by critic adapter: {relation}"
        )

    if relation == "falsifies":
        finding_code = "AUTHENTICATED_DIRECTIONAL_FALSIFICATION_PRESENT"
        finding_suffix = "authenticated-directional-falsification"
        statement = (
            "The current bundle independently authenticates the exact diagnostic falsification "
            "edge for this target within its declared scope."
        )
        action_suffix = "reframe-authenticated-falsified-scope"
        action_description = (
            "Reframe or narrow the scope challenged by the authenticated falsification before "
            "continuing positive-claim work."
        )
        recommendation = "reframe_or_narrow_authenticated_falsified_scope"
    else:
        finding_code = "AUTHENTICATED_DIRECTIONAL_CONTRADICTION_PRESENT"
        finding_suffix = "authenticated-directional-contradiction"
        statement = (
            "The current bundle independently authenticates the exact diagnostic contradiction "
            "edge for this target within its declared scope."
        )
        action_suffix = "reassess-authenticated-contradicted-scope"
        action_description = (
            "Reassess, narrow, or reframe the scope challenged by the authenticated contradiction "
            "before unsupported positive-claim continuation."
        )
        recommendation = "reassess_or_narrow_authenticated_contradicted_scope"

    _append_unique_by_key(
        findings,
        {
            "finding_id": f"critic:{target_id}:{finding_suffix}",
            "code": finding_code,
            "severity": "high",
            "statement": statement,
            "rationale": (
                "The adapter independently re-authenticated the current bundle's exact inference-edge "
                "identity. This restores critic-level directional objection authority without changing "
                "the evaluator assessment or persistent graph assessment level."
            ),
            "edge_ids": [edge_id],
            "node_ids": [result_node_id],
            "scientific_status_changed": False,
        },
        key="finding_id",
    )
    _append_unique_by_key(
        actions,
        {
            "action_id": f"critic:{target_id}:{action_suffix}",
            "action_class": "manual_review",
            "description": action_description,
            "rationale": (
                "Exact directional provenance is authenticated, so the negative result may inform "
                "manual scientific reframing while automatic stop and positive closeout remain forbidden."
            ),
            "execution_mode": "plan_only",
            "information_gain_priority": "high",
            "information_gain_is_calibrated_probability": False,
            "expected_discrimination": (
                "Separates explicit scope revision from silently ignoring an exactly authenticated "
                "negative directional result."
            ),
            "automatic_execution_authorized": False,
            "availability_asserted": False,
        },
        key="action_id",
    )
    target["authenticated_stop_advisory"] = {
        "recommendation": recommendation,
        "rationale": (
            "Exact current-transition negative directional provenance is independently authenticated. "
            "This is a separate advisory and does not replace the base critic stop recommendation."
        ),
        "base_critic_stop_recommendation_preserved": True,
        "automatic_stop_authorized": False,
        "positive_scientific_closeout_granted": False,
    }



def _validate_consumer_authority_boundary(consumer: Mapping[str, Any]) -> None:
    if consumer.get("schema_version") != "1.0" or consumer.get("consumer_policy_version") != "1.0":
        raise ScientificCriticError(
            "authenticated critic adapter supports only transition consumer schema/policy 1.0"
        )
    if consumer.get("current_transition_exact_provenance_authenticated") is not True:
        raise ScientificCriticError(
            "authenticated critic adapter requires independently authenticated current-transition provenance"
        )
    boundary = consumer.get("authority_boundary")
    if not isinstance(boundary, Mapping):
        raise ScientificCriticError("authenticated transition consumer authority boundary is malformed")
    forbidden_true = (
        "scientific_authority_applied",
        "scientific_status_changed",
        "execution_authorized",
        "positive_closeout_granted",
        "verifier_identity_or_credential_authenticated",
        "support_independence_established",
        "empirical_origin_independently_established",
    )
    for field in forbidden_true:
        if boundary.get(field) is not False:
            raise ScientificCriticError(
                f"authenticated transition consumer must explicitly keep {field}=false"
            )
    if consumer.get("inference_scope") in {"empirical_derived", "empirical_direct"}:
        raise ScientificCriticError(
            "empirical critic authority remains disabled until the evidence-origin contract is authenticated"
        )

def build_authenticated_scientific_critic_report(
    bundle_root: str | Path,
    *,
    program_state: Mapping[str, Any],
    target_node_ids: Sequence[object] | None = None,
) -> dict[str, Any]:
    """Build a hardened critic report with one independently authenticated advisory.

    `bundle_root` is the only accepted authentication input. The adapter always re-reads the
    authoritative bundle itself, so callers cannot inject a precomputed consumer-report dict.
    """
    root = Path(bundle_root).expanduser()
    consumer = authenticate_transition_bundle(root)
    _validate_consumer_authority_boundary(consumer)
    graph_path = root / "epistemic_graph.json"
    report = build_policy_hardened_scientific_critic_report(
        graph_path,
        program_state=program_state,
        artifact_root=root,
        target_node_ids=target_node_ids,
    )
    result = copy.deepcopy(report)

    target_id = str(consumer["target_node_id"])
    target = _target_report_by_id(result, target_id)
    advisory_applied = target is not None
    negative_manual_reframe = (
        advisory_applied and str(consumer["relation"]) in _NEGATIVE_RELATIONS
    )
    if target is not None:
        _apply_authenticated_directional_advisory(target, consumer=consumer)

    result["authenticated_critic_policy_version"] = (
        AUTHENTICATED_SCIENTIFIC_CRITIC_POLICY_VERSION
    )
    result["authenticated_transition_consumer"] = {
        "transition_id": consumer["transition_id"],
        "inference_edge_id": consumer["inference_edge_id"],
        "result_node_id": consumer["result_node_id"],
        "target_node_id": consumer["target_node_id"],
        "relation": consumer["relation"],
        "inference_scope": consumer["inference_scope"],
        "current_transition_exact_provenance_authenticated": True,
        "advisory_applied_to_requested_target_set": advisory_applied,
        "consumer_report_supplied_by_caller": False,
    }

    boundary = result.get("autonomy_boundary")
    if not isinstance(boundary, dict):
        raise ScientificCriticError("critic report autonomy boundary is malformed")
    boundary.update(
        {
            "authenticated_bundle_re_read_by_critic_adapter": True,
            "caller_supplied_consumer_report_accepted": False,
            "persistent_graph_promoted_by_authenticated_advisory": False,
            "evaluator_status_changed_by_authenticated_advisory": False,
            "authenticated_directional_advisory_may_inform_manual_reframe": negative_manual_reframe,
            "authenticated_directional_advisory_authorizes_automatic_stop": False,
            "authenticated_directional_advisory_authorizes_execution": False,
            "authenticated_directional_advisory_grants_positive_closeout": False,
            "support_independence_established_by_exact_edge_provenance": False,
            "calibrated_confidence_established_by_exact_edge_provenance": False,
            "empirical_derived_authority_enabled_without_evidence_origin_contract": False,
            "empirical_direct_authority_enabled_without_evidence_origin_contract": False,
        }
    )

    summary = result.get("summary")
    target_reports = result.get("target_reports")
    if not isinstance(summary, dict) or not isinstance(target_reports, list):
        raise ScientificCriticError("critic report summary/target_reports are malformed")
    summary["findings"] = sum(
        len(item.get("critic_findings", []))
        for item in target_reports
        if isinstance(item, Mapping)
    )
    summary["discriminating_actions"] = sum(
        len(item.get("discriminating_actions", []))
        for item in target_reports
        if isinstance(item, Mapping)
    )
    summary["authenticated_directional_advisories"] = 1 if advisory_applied else 0
    return result


__all__ = [
    "AUTHENTICATED_SCIENTIFIC_CRITIC_POLICY_VERSION",
    "build_authenticated_scientific_critic_report",
]
