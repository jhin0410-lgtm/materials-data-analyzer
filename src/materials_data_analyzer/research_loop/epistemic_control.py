"""Fail-closed execution directives derived from verified epistemic assessments.

This module does not infer scientific truth. It consumes the already validated output of
``evaluate_epistemic_graph`` and turns selected target-node statuses into a bounded
execution directive for repeated research orchestration. The directive is deliberately
asymmetric: verified falsification stops the targeted line of inquiry, verified
contradiction or conflict requires discrimination/manual review, and positive support
requires domain closeout rather than additional automatic result-seeking.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .kernel import ResearchLoopError

EPISTEMIC_CONTROL_SCHEMA_VERSION = "1.0"
EPISTEMIC_CONTROL_POLICY_VERSION = "1.0"

_ALLOWED_STATUSES = {
    "inconclusive",
    "provisionally_supported",
    "contested",
    "contradicted_within_verified_scope",
    "falsified_within_verified_scope",
}


class EpistemicControlError(ResearchLoopError):
    """Raised when an epistemic execution-control input is malformed or ambiguous."""


def _nonempty_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EpistemicControlError(f"{field} must be a non-empty string")
    return value.strip()


def _target_ids(values: Sequence[object]) -> list[str]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence) or not values:
        raise EpistemicControlError("target_node_ids must be a non-empty sequence")
    result: list[str] = []
    for index, value in enumerate(values):
        node_id = _nonempty_text(value, f"target_node_ids[{index}]")
        if node_id in result:
            raise EpistemicControlError(f"duplicate target_node_id: {node_id}")
        result.append(node_id)
    return result


def derive_epistemic_directive(
    evaluation: Mapping[str, Any],
    *,
    target_node_ids: Sequence[object],
) -> dict[str, Any]:
    """Map selected verified graph statuses to a bounded orchestration directive."""
    targets = _target_ids(target_node_ids)
    assessments = evaluation.get("assessments")
    if not isinstance(assessments, list):
        raise EpistemicControlError("epistemic evaluation assessments must be a list")

    by_id: dict[str, Mapping[str, Any]] = {}
    for index, assessment in enumerate(assessments):
        if not isinstance(assessment, Mapping):
            raise EpistemicControlError(
                f"epistemic evaluation assessments[{index}] must be an object"
            )
        node_id = _nonempty_text(
            assessment.get("node_id"), f"epistemic evaluation assessments[{index}].node_id"
        )
        if node_id in by_id:
            raise EpistemicControlError(f"duplicate assessment node_id: {node_id}")
        status = _nonempty_text(
            assessment.get("status"), f"epistemic evaluation assessment {node_id}.status"
        )
        if status not in _ALLOWED_STATUSES:
            raise EpistemicControlError(
                f"unsupported epistemic status for {node_id}: {status!r}"
            )
        by_id[node_id] = assessment

    missing = [node_id for node_id in targets if node_id not in by_id]
    if missing:
        raise EpistemicControlError(
            "target epistemic nodes are missing from the current evaluation: "
            + ", ".join(missing)
        )

    selected = [by_id[node_id] for node_id in targets]
    status_by_node = {node_id: str(by_id[node_id]["status"]) for node_id in targets}
    statuses = set(status_by_node.values())

    if "falsified_within_verified_scope" in statuses:
        directive = "stop_falsified_target"
        automatic_execution_permitted = False
        reason = (
            "At least one selected target is falsified within verified scope. Do not continue "
            "the same hypothesis merely to seek a preferred result; reopen only under a new "
            "versioned hypothesis or materially changed evidence scope."
        )
    elif "contested" in statuses:
        directive = "manual_discrimination_required"
        automatic_execution_permitted = False
        reason = (
            "At least one selected target has both verified support and verified contradiction. "
            "A discriminating analysis, replication, stronger evidence source, or manual domain "
            "review is required before automatic repetition."
        )
    elif "contradicted_within_verified_scope" in statuses:
        directive = "manual_discrimination_required"
        automatic_execution_permitted = False
        reason = (
            "At least one selected target is contradicted within verified scope. Automatic "
            "result-seeking is stopped pending a predeclared discrimination or revised hypothesis."
        )
    elif "provisionally_supported" in statuses:
        directive = "domain_closeout_required"
        automatic_execution_permitted = False
        reason = (
            "At least one selected target is provisionally supported. Positive support is not "
            "final scientific truth; applicable domain closeout is required before accepting a "
            "positive conclusion or launching additional confirmatory cycles."
        )
    else:
        directive = "continue_discriminating_research"
        automatic_execution_permitted = True
        reason = (
            "All selected targets remain inconclusive under verified relations. Further bounded, "
            "predeclared discriminating research may continue under the existing execution and "
            "authorization contracts."
        )

    return {
        "schema_version": EPISTEMIC_CONTROL_SCHEMA_VERSION,
        "epistemic_control_policy_version": EPISTEMIC_CONTROL_POLICY_VERSION,
        "graph_id": evaluation.get("graph_id"),
        "target_node_ids": targets,
        "target_statuses": status_by_node,
        "directive": directive,
        "automatic_execution_permitted": automatic_execution_permitted,
        "reason": reason,
        "selected_assessments": [dict(item) for item in selected],
        "autonomy_boundary": {
            "proposal_only_relations_can_authorize_execution": False,
            "diagnostic_only_relations_can_authorize_execution": False,
            "verified_falsification_can_be_ignored_by_repetition": False,
            "positive_support_grants_final_truth": False,
            "numeric_confidence_invented": False,
        },
    }


__all__ = [
    "EPISTEMIC_CONTROL_POLICY_VERSION",
    "EPISTEMIC_CONTROL_SCHEMA_VERSION",
    "EpistemicControlError",
    "derive_epistemic_directive",
]
