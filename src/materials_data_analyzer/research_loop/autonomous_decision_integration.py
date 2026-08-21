"""Decision-support integration for persistent autonomous research episodes.

This layer connects already-validated planning, physical-lineage statistical eligibility,
probabilistic EIG, hypothesis-portfolio state, and research-agent benchmark results.  It
deliberately does not create an execution authority: a selected action can only be handed
to the repository's existing authenticated authorization and typed-executor chain.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

from .advanced_statistics_gate import assess_statistical_model_eligibility
from .experimental_lineage import ObservationLineage
from .hypothesis_portfolio import (
    HypothesisPortfolioError,
    validate_hypothesis_portfolio_for_plan,
)
from .kernel import ResearchLoopError

AUTONOMOUS_DECISION_INTEGRATION_SCHEMA_VERSION = "1.0"
AUTONOMOUS_DECISION_INTEGRATION_POLICY_VERSION = "1.0"


class AutonomousDecisionIntegrationError(ResearchLoopError):
    """Raised when decision-support inputs violate the integration contract."""


def _canonical_sha256(value: object) -> str:
    try:
        payload = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise AutonomousDecisionIntegrationError(
            "decision input must be canonical-JSON serializable"
        ) from exc
    return hashlib.sha256(payload).hexdigest()


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AutonomousDecisionIntegrationError(f"{field} must be non-empty text")
    if value != value.strip():
        raise AutonomousDecisionIntegrationError(f"{field} must not contain edge whitespace")
    return value


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AutonomousDecisionIntegrationError(f"{field} must be an object")
    return value


def _sequence(value: object, field: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise AutonomousDecisionIntegrationError(f"{field} must be a sequence")
    return value


def _eligible_planner_actions(plan: Mapping[str, Any]) -> list[dict[str, Any]]:
    ranked = _sequence(plan.get("ranked_actions", []), "plan.ranked_actions")
    budget_record = _mapping(plan.get("planning_budget", {}), "plan.planning_budget")
    try:
        budget = float(budget_record["budget_units"])
        threshold = float(budget_record["minimum_utility"])
    except (KeyError, TypeError, ValueError) as exc:
        raise AutonomousDecisionIntegrationError("invalid planning budget") from exc

    eligible: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(ranked):
        action = _mapping(raw, f"plan.ranked_actions[{index}]")
        action_id = _text(action.get("action_id"), "action_id")
        if action_id in seen:
            raise AutonomousDecisionIntegrationError("ranked action IDs must be unique")
        seen.add(action_id)
        try:
            cost = float(action["cost_units"])
            utility = float(action["utility_score"])
        except (KeyError, TypeError, ValueError) as exc:
            raise AutonomousDecisionIntegrationError("invalid planner action score") from exc
        if cost <= budget and utility >= threshold:
            eligible.append(dict(action))
    return eligible


def _validate_benchmark_summary(
    benchmark_summary: Mapping[str, Any] | None,
) -> tuple[dict[str, Any] | None, bool]:
    if benchmark_summary is None:
        return None, False
    summary = dict(benchmark_summary)
    passed = summary.get("benchmark_passed")
    if not isinstance(passed, bool):
        raise AutonomousDecisionIntegrationError(
            "benchmark_summary.benchmark_passed must be boolean"
        )
    critical = summary.get("critical_failure_count")
    if isinstance(critical, bool) or not isinstance(critical, int) or critical < 0:
        raise AutonomousDecisionIntegrationError(
            "benchmark_summary.critical_failure_count must be a non-negative integer"
        )
    if passed and critical != 0:
        raise AutonomousDecisionIntegrationError(
            "benchmark cannot pass with critical failures"
        )
    return summary, passed and critical == 0


def _validated_eig_priorities(
    eig_results: Mapping[str, Mapping[str, Any]] | None,
    eligible_ids: set[str],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    if eig_results is None:
        return [], {}
    ranked: list[dict[str, Any]] = []
    ignored: dict[str, str] = {}
    for raw_action_id, raw_result in eig_results.items():
        action_id = _text(raw_action_id, "eig action_id")
        if action_id not in eligible_ids:
            raise AutonomousDecisionIntegrationError(
                f"EIG result references non-eligible planner action: {action_id}"
            )
        result = _mapping(raw_result, f"eig_results[{action_id}]")
        mode = result.get("mode")
        if mode == "structural_proxy_only":
            ignored[action_id] = "structural_proxy_cannot_reorder_actions"
            continue
        if mode != "probabilistic_eig":
            raise AutonomousDecisionIntegrationError(
                f"unsupported EIG mode for {action_id}: {mode}"
            )
        digest = result.get("model_artifact_sha256")
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or digest != digest.lower()
            or any(char not in "0123456789abcdef" for char in digest)
        ):
            raise AutonomousDecisionIntegrationError(
                "probabilistic EIG must remain bound to a lowercase SHA-256 model artifact"
            )
        value = result.get("eig_per_cost_unit")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            raise AutonomousDecisionIntegrationError("invalid eig_per_cost_unit")
        ranked.append(
            {
                "action_id": action_id,
                "eig_per_cost_unit": float(value),
                "model_artifact_sha256": digest,
            }
        )
    ranked.sort(key=lambda item: (-item["eig_per_cost_unit"], item["action_id"]))
    return ranked, ignored


def _validated_hypothesis_portfolio_binding(
    hypothesis_portfolio: Mapping[str, Any] | None,
    *,
    plan: Mapping[str, Any],
) -> dict[str, Any] | None:
    if hypothesis_portfolio is None:
        return None
    try:
        return validate_hypothesis_portfolio_for_plan(
            hypothesis_portfolio,
            plan=plan,
        )
    except HypothesisPortfolioError as exc:
        raise AutonomousDecisionIntegrationError(
            "hypothesis portfolio failed exact planning-cycle validation"
        ) from exc


def build_autonomous_decision_report(
    plan: Mapping[str, Any],
    *,
    lineages: Sequence[ObservationLineage] | None = None,
    fixed_effects_declared: bool = False,
    repeated_measurements_expected: bool = False,
    eig_results: Mapping[str, Mapping[str, Any]] | None = None,
    benchmark_summary: Mapping[str, Any] | None = None,
    hypothesis_portfolio: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Integrate decision evidence without expanding the planner's action frontier.

    True probabilistic EIG may reorder only actions already affordable/informative under the
    upstream plan. Structural proxies never reorder actions. A bound hypothesis portfolio
    may suppress confirmatory execution when all hypotheses are falsified or when verified
    provisional support requires domain closeout, but it cannot inject or invent an action.
    Benchmark qualification is a prerequisite only for automated *handoff requests*; it
    never authorizes execution.
    """
    plan_map = dict(_mapping(plan, "plan"))
    stop = _mapping(plan_map.get("stop_decision", {}), "plan.stop_decision")
    stop_flag = stop.get("stop")
    if not isinstance(stop_flag, bool):
        raise AutonomousDecisionIntegrationError("plan.stop_decision.stop must be boolean")

    eligible = _eligible_planner_actions(plan_map)
    eligible_by_id = {str(item["action_id"]): item for item in eligible}
    eig_ranked, eig_ignored = _validated_eig_priorities(
        eig_results,
        set(eligible_by_id),
    )
    benchmark, benchmark_qualified = _validate_benchmark_summary(benchmark_summary)
    portfolio_binding = _validated_hypothesis_portfolio_binding(
        hypothesis_portfolio,
        plan=plan_map,
    )

    statistics: dict[str, Any] | None = None
    if lineages is not None:
        statistics = assess_statistical_model_eligibility(
            lineages,
            fixed_effects_declared=fixed_effects_declared,
            repeated_measurements_expected=repeated_measurements_expected,
        )

    original_selected = plan_map.get("selected_next_action")
    original_selected_id = (
        _text(original_selected.get("action_id"), "selected_next_action.action_id")
        if isinstance(original_selected, Mapping)
        else None
    )
    selected: dict[str, Any] | None = None
    selection_reason = "upstream_stop_decision"
    if not stop_flag and eligible:
        if eig_ranked:
            selected = dict(eligible_by_id[eig_ranked[0]["action_id"]])
            selection_reason = "validated_probabilistic_eig_within_upstream_eligible_frontier"
        elif original_selected_id is not None:
            if original_selected_id not in eligible_by_id:
                raise AutonomousDecisionIntegrationError(
                    "upstream selected action is not in its own eligible frontier"
                )
            selected = dict(eligible_by_id[original_selected_id])
            selection_reason = "upstream_planner_order_preserved"
        else:
            selected = dict(eligible[0])
            selection_reason = "first_upstream_eligible_action"

    portfolio_gated_selection = False
    if portfolio_binding is not None and selected is not None:
        directive = portfolio_binding["portfolio_directive"]
        if directive == "domain_closeout_required":
            selected = None
            selection_reason = "hypothesis_portfolio_requires_domain_closeout"
            portfolio_gated_selection = True
        elif directive == "bounded_stop_all_hypotheses_retired":
            selected = None
            selection_reason = "hypothesis_portfolio_all_hypotheses_retired"
            portfolio_gated_selection = True
        elif directive not in {
            "prioritize_discrimination",
            "continue_bounded_discrimination",
        }:
            raise AutonomousDecisionIntegrationError(
                f"unsupported hypothesis portfolio directive: {directive}"
            )

    execution_mode = selected.get("execution_mode") if selected is not None else None
    automatic_handoff_request_eligible = bool(
        selected is not None
        and benchmark_qualified
        and execution_mode in {"typed_local_action", "explicit_authorization_required"}
        and not bool(selected.get("physical_experiment_execution_authorized", False))
    )

    report: dict[str, Any] = {
        "schema_version": AUTONOMOUS_DECISION_INTEGRATION_SCHEMA_VERSION,
        "policy_version": AUTONOMOUS_DECISION_INTEGRATION_POLICY_VERSION,
        "plan_binding": {"canonical_sha256": _canonical_sha256(plan_map)},
        "eligible_action_ids": [str(item["action_id"]) for item in eligible],
        "original_selected_action_id": original_selected_id,
        "selected_action": selected,
        "selection_reason": selection_reason,
        "probabilistic_eig_ranking": eig_ranked,
        "ignored_eig_results": eig_ignored,
        "advanced_statistics_eligibility": statistics,
        "benchmark_summary": benchmark,
        "benchmark_qualified_for_automatic_handoff": benchmark_qualified,
        "hypothesis_portfolio_binding": portfolio_binding,
        "hypothesis_portfolio_gated_selection": portfolio_gated_selection,
        "execution_handoff": {
            "eligible_to_request_existing_authorization_chain": automatic_handoff_request_eligible,
            "destination": "existing_independent_action_authorization_and_typed_executor_chain",
            "authorization_granted_here": False,
            "request_compiled_here": False,
            "execution_performed_here": False,
        },
        "scientific_status_changed": False,
        "physical_experiment_executed": False,
        "planner_frontier_expanded": False,
    }
    report["report_sha256"] = _canonical_sha256(report)
    return report


__all__ = [
    "AUTONOMOUS_DECISION_INTEGRATION_POLICY_VERSION",
    "AUTONOMOUS_DECISION_INTEGRATION_SCHEMA_VERSION",
    "AutonomousDecisionIntegrationError",
    "build_autonomous_decision_report",
]
