"""Bind integrated autonomous decisions into persistent ResearchEpisode step records."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .autonomous_decision_integration import AutonomousDecisionIntegrationError

AUTONOMOUS_EPISODE_STEP_SCHEMA_VERSION = "1.0"


def _text_list(value: Sequence[str] | None, field: str) -> list[str]:
    if value is None:
        return []
    result: list[str] = []
    for raw in value:
        if not isinstance(raw, str) or not raw.strip() or raw != raw.strip():
            raise AutonomousDecisionIntegrationError(f"{field} must contain non-empty trimmed text")
        if raw not in result:
            result.append(raw)
    return result


def decision_report_to_episode_step(
    *,
    plan: Mapping[str, Any],
    decision_report: Mapping[str, Any],
    evidence_refs: Sequence[str] = (),
    unresolved_gaps: Sequence[str] = (),
    review_queue: Sequence[str] = (),
    blockers: Sequence[str] = (),
) -> dict[str, Any]:
    """Create one persistence-ready step without performing the selected action."""
    report_sha = decision_report.get("report_sha256")
    if (
        not isinstance(report_sha, str)
        or len(report_sha) != 64
        or report_sha != report_sha.lower()
        or any(char not in "0123456789abcdef" for char in report_sha)
    ):
        raise AutonomousDecisionIntegrationError("decision report requires canonical report_sha256")
    if decision_report.get("scientific_status_changed") is not False:
        raise AutonomousDecisionIntegrationError("decision support cannot change scientific status")
    if decision_report.get("physical_experiment_executed") is not False:
        raise AutonomousDecisionIntegrationError("decision support cannot execute a physical experiment")

    selected = decision_report.get("selected_action")
    cost_units = 0.0
    iteration_status = "decision_recorded"
    if selected is not None:
        if not isinstance(selected, Mapping):
            raise AutonomousDecisionIntegrationError("selected_action must be null or an object")
        raw_cost = selected.get("cost_units", 0.0)
        if isinstance(raw_cost, bool) or not isinstance(raw_cost, (int, float)) or raw_cost < 0:
            raise AutonomousDecisionIntegrationError("selected action cost must be non-negative")
        # Planning/selection itself does not consume the selected action's execution cost.
        # The executor iteration records execution cost separately after authorization.
        cost_units = 0.0

    stop = plan.get("stop_decision")
    if not isinstance(stop, Mapping) or not isinstance(stop.get("stop"), bool):
        raise AutonomousDecisionIntegrationError("plan stop_decision is invalid")
    episode_status = "stopped" if stop["stop"] else "active"
    if review_queue or blockers:
        episode_status = "blocked"
        iteration_status = "decision_blocked_pending_evidence_or_review"

    conclusion = None
    if stop["stop"]:
        conclusion = {
            "kind": "bounded_stop_without_scientific_promotion",
            "reason": str(stop.get("reason", "upstream_stop_decision")),
            "scientific_status_changed": False,
        }

    return {
        "planner_record": {
            "schema_version": AUTONOMOUS_EPISODE_STEP_SCHEMA_VERSION,
            "plan": dict(plan),
            "decision_report": dict(decision_report),
        },
        "artifact_refs": [f"decision-report-sha256:{report_sha}"],
        "evidence_refs": _text_list(evidence_refs, "evidence_refs"),
        "unresolved_gaps": _text_list(unresolved_gaps, "unresolved_gaps"),
        "review_queue": _text_list(review_queue, "review_queue"),
        "blockers": _text_list(blockers, "blockers"),
        "cost_units": cost_units,
        "iteration_status": iteration_status,
        "episode_status": episode_status,
        "conclusion": conclusion,
    }


__all__ = ["AUTONOMOUS_EPISODE_STEP_SCHEMA_VERSION", "decision_report_to_episode_step"]
