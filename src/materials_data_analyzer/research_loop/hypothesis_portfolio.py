"""Persistent hypothesis state derived from verified epistemic-graph assessments.

The autonomous inquiry planner can generate hypotheses on every iteration, while the
provenance-aware epistemic graph evaluates already represented hypothesis nodes.  This
module connects those layers with a durable, fail-closed portfolio: verified graph state
is carried forward so falsified, contested, provisionally supported, and inconclusive
hypotheses do not silently reset to fresh candidates on the next planning cycle.

The portfolio is deliberately not a Bayesian belief state.  It assigns no posterior
probabilities, creates no empirical evidence, and never promotes provisional support to
scientific truth.  It only converts existing verified graph assessments into bounded
research directives and checksum-bound ancestry.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from .kernel import ResearchLoopError

HYPOTHESIS_PORTFOLIO_SCHEMA_VERSION = "1.0"
HYPOTHESIS_PORTFOLIO_POLICY_VERSION = "1.0"

_STATUS_TO_STATE = {
    "inconclusive": "active_discrimination_required",
    "provisionally_supported": "positive_closeout_required",
    "contested": "contested_discrimination_required",
    "contradicted_within_verified_scope": "challenge_or_retirement_review",
    "falsified_within_verified_scope": "retired_falsified_within_verified_scope",
}
_STATE_TO_DIRECTIVE = {
    "active_discrimination_required": "continue_discriminating_research",
    "positive_closeout_required": "seek_domain_closeout_no_auto_promotion",
    "contested_discrimination_required": "prioritize_discriminating_work",
    "challenge_or_retirement_review": "seek_replication_or_scope_review",
    "retired_falsified_within_verified_scope": "do_not_repeat_without_new_hypothesis_identity",
}
_EDGE_FIELDS = (
    "verified_support_edges",
    "verified_contradiction_edges",
    "verified_falsification_edges",
)


class HypothesisPortfolioError(ResearchLoopError):
    """Raised when hypothesis-state persistence would weaken epistemic provenance."""


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
        raise HypothesisPortfolioError(
            "hypothesis portfolio input must be canonical-JSON serializable"
        ) from exc
    return hashlib.sha256(payload).hexdigest()


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise HypothesisPortfolioError(f"{field} must be non-empty trimmed text")
    return value


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise HypothesisPortfolioError(f"{field} must be an object")
    return value


def _sequence(value: object, field: str) -> Sequence[object]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise HypothesisPortfolioError(f"{field} must be a sequence")
    return value


def _sha256_text(value: object, field: str) -> str:
    text = _text(value, field)
    if len(text) != 64 or text != text.lower():
        raise HypothesisPortfolioError(f"{field} must be a lowercase SHA-256 digest")
    if any(char not in "0123456789abcdef" for char in text):
        raise HypothesisPortfolioError(f"{field} must be a lowercase SHA-256 digest")
    return text


def _unique_text_list(value: object, field: str) -> list[str]:
    items = _sequence(value, field)
    result: list[str] = []
    for index, raw in enumerate(items):
        item = _text(raw, f"{field}[{index}]")
        if item in result:
            raise HypothesisPortfolioError(f"{field} must not contain duplicate edge IDs")
        result.append(item)
    return result


def _verified_plan_sha(plan: Mapping[str, Any]) -> str:
    plan_map = dict(plan)
    embedded = _sha256_text(plan_map.pop("plan_sha256", None), "plan.plan_sha256")
    actual = _canonical_sha256(plan_map)
    if actual != embedded:
        raise HypothesisPortfolioError(
            f"plan.plan_sha256 mismatch: expected {embedded}, recomputed {actual}"
        )
    return embedded


def _verified_portfolio_sha(portfolio: Mapping[str, Any]) -> str:
    value = dict(portfolio)
    embedded = _sha256_text(
        value.pop("portfolio_sha256", None),
        "previous_portfolio.portfolio_sha256",
    )
    actual = _canonical_sha256(value)
    if actual != embedded:
        raise HypothesisPortfolioError(
            "previous portfolio canonical SHA-256 does not match its content"
        )
    return embedded


def _hypothesis_nodes(evaluated_graph: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    nodes = _sequence(evaluated_graph.get("nodes", []), "evaluated_graph.nodes")
    result: dict[str, dict[str, Any]] = {}
    all_node_ids: set[str] = set()
    for index, raw in enumerate(nodes):
        node = _mapping(raw, f"evaluated_graph.nodes[{index}]")
        node_id = _text(node.get("node_id"), f"evaluated_graph.nodes[{index}].node_id")
        if node_id in all_node_ids:
            raise HypothesisPortfolioError(f"duplicate graph node_id: {node_id}")
        all_node_ids.add(node_id)
        if node.get("node_type") != "hypothesis":
            continue
        result[node_id] = {
            "node_id": node_id,
            "statement": _text(
                node.get("statement"),
                f"evaluated_graph.nodes[{index}].statement",
            ),
        }
    if not result:
        raise HypothesisPortfolioError(
            "evaluated graph contains no hypothesis nodes to persist"
        )
    return result


def _hypothesis_assessments(
    evaluated_graph: Mapping[str, Any],
    hypotheses: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    raw_assessments = _sequence(
        evaluated_graph.get("assessments", []),
        "evaluated_graph.assessments",
    )
    assessments: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(raw_assessments):
        item = _mapping(raw, f"evaluated_graph.assessments[{index}]")
        node_id = _text(item.get("node_id"), f"evaluated_graph.assessments[{index}].node_id")
        if node_id not in hypotheses:
            continue
        if node_id in assessments:
            raise HypothesisPortfolioError(f"duplicate hypothesis assessment: {node_id}")
        if item.get("node_type") != "hypothesis":
            raise HypothesisPortfolioError(
                f"assessment node_type substitution for hypothesis {node_id}"
            )
        status = _text(item.get("status"), f"assessment[{node_id}].status")
        if status not in _STATUS_TO_STATE:
            raise HypothesisPortfolioError(
                f"unsupported epistemic status for hypothesis {node_id}: {status}"
            )
        if item.get("final_positive_support_granted") is not False:
            raise HypothesisPortfolioError(
                "hypothesis portfolio cannot consume automatically final-positive support"
            )
        if item.get("confidence_score") is not None:
            raise HypothesisPortfolioError(
                "hypothesis portfolio does not accept invented numeric confidence"
            )
        normalized: dict[str, Any] = {
            "status": status,
            "diagnostic_relation_edges": _unique_text_list(
                item.get("diagnostic_relation_edges", []),
                f"assessment[{node_id}].diagnostic_relation_edges",
            ),
        }
        for field in _EDGE_FIELDS:
            normalized[field] = _unique_text_list(
                item.get(field, []),
                f"assessment[{node_id}].{field}",
            )
        assessments[node_id] = normalized

    missing = sorted(set(hypotheses) - set(assessments))
    if missing:
        raise HypothesisPortfolioError(
            "every graph hypothesis requires an evaluated assessment: " + ", ".join(missing)
        )
    return assessments


def _previous_records(
    previous_portfolio: Mapping[str, Any] | None,
    *,
    graph_id: str,
) -> tuple[str | None, dict[str, dict[str, Any]]]:
    if previous_portfolio is None:
        return None, {}
    previous = dict(previous_portfolio)
    if previous.get("schema_version") != HYPOTHESIS_PORTFOLIO_SCHEMA_VERSION:
        raise HypothesisPortfolioError("unsupported previous portfolio schema_version")
    if previous.get("policy_version") != HYPOTHESIS_PORTFOLIO_POLICY_VERSION:
        raise HypothesisPortfolioError("unsupported previous portfolio policy_version")
    if previous.get("graph_id") != graph_id:
        raise HypothesisPortfolioError("previous portfolio graph_id does not match current graph")
    previous_sha = _verified_portfolio_sha(previous)
    records = _sequence(previous.get("hypotheses", []), "previous_portfolio.hypotheses")
    result: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(records):
        record = dict(_mapping(raw, f"previous_portfolio.hypotheses[{index}]"))
        hypothesis_id = _text(
            record.get("hypothesis_id"),
            f"previous_portfolio.hypotheses[{index}].hypothesis_id",
        )
        if hypothesis_id in result:
            raise HypothesisPortfolioError(
                f"duplicate previous hypothesis record: {hypothesis_id}"
            )
        result[hypothesis_id] = record
    return previous_sha, result


def _validate_ancestry(
    *,
    previous_records: Mapping[str, Mapping[str, Any]],
    current_hypotheses: Mapping[str, Mapping[str, Any]],
    current_assessments: Mapping[str, Mapping[str, Any]],
) -> None:
    removed = sorted(set(previous_records) - set(current_hypotheses))
    if removed:
        raise HypothesisPortfolioError(
            "previous hypothesis nodes cannot disappear without an explicit future retirement contract: "
            + ", ".join(removed)
        )

    for hypothesis_id, previous in previous_records.items():
        current_node = current_hypotheses[hypothesis_id]
        if previous.get("statement") != current_node["statement"]:
            raise HypothesisPortfolioError(
                f"hypothesis statement changed under stable identity: {hypothesis_id}"
            )
        current = current_assessments[hypothesis_id]
        for field in _EDGE_FIELDS:
            prior_edges = set(
                _unique_text_list(
                    previous.get(field, []),
                    f"previous[{hypothesis_id}].{field}",
                )
            )
            current_edges = set(current[field])
            if not prior_edges.issubset(current_edges):
                raise HypothesisPortfolioError(
                    f"verified epistemic edges were removed for {hypothesis_id}.{field}"
                )
        prior_state = previous.get("portfolio_state")
        if (
            prior_state == "retired_falsified_within_verified_scope"
            and current["status"] != "falsified_within_verified_scope"
        ):
            raise HypothesisPortfolioError(
                f"falsified hypothesis cannot silently reactivate: {hypothesis_id}"
            )


def _transition_label(
    previous: Mapping[str, Any] | None,
    current: Mapping[str, Any],
) -> str:
    if previous is None:
        return "entered_from_current_verified_graph"
    previous_state = previous.get("portfolio_state")
    current_state = current["portfolio_state"]
    if previous_state == current_state:
        return "unchanged_under_current_verified_graph"
    previous_edges = {
        edge
        for field in _EDGE_FIELDS
        for edge in previous.get(field, [])
        if isinstance(edge, str)
    }
    current_edges = {
        edge
        for field in _EDGE_FIELDS
        for edge in current[field]
    }
    if not current_edges.difference(previous_edges):
        raise HypothesisPortfolioError(
            f"hypothesis state changed without new verified epistemic evidence: {current['hypothesis_id']}"
        )
    return "advanced_by_new_verified_epistemic_evidence"


def _portfolio_directive(states: Sequence[str]) -> str:
    state_set = set(states)
    if "contested_discrimination_required" in state_set:
        return "prioritize_discrimination"
    if state_set.intersection(
        {"active_discrimination_required", "challenge_or_retirement_review"}
    ):
        return "continue_bounded_discrimination"
    if "positive_closeout_required" in state_set:
        return "domain_closeout_required"
    if state_set == {"retired_falsified_within_verified_scope"}:
        return "bounded_stop_all_hypotheses_retired"
    raise HypothesisPortfolioError("could not derive a bounded portfolio directive")


def build_hypothesis_portfolio(
    evaluated_graph: Mapping[str, Any],
    *,
    plan: Mapping[str, Any],
    previous_portfolio: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a persistent hypothesis portfolio from an already evaluated epistemic graph."""
    graph = _mapping(evaluated_graph, "evaluated_graph")
    graph_id = _text(graph.get("graph_id"), "evaluated_graph.graph_id")
    research_scope = _text(
        graph.get("research_scope"),
        "evaluated_graph.research_scope",
    )
    hypotheses = _hypothesis_nodes(graph)
    assessments = _hypothesis_assessments(graph, hypotheses)
    plan_sha = _verified_plan_sha(plan)
    previous_sha, prior_records = _previous_records(
        previous_portfolio,
        graph_id=graph_id,
    )
    _validate_ancestry(
        previous_records=prior_records,
        current_hypotheses=hypotheses,
        current_assessments=assessments,
    )

    records: list[dict[str, Any]] = []
    for hypothesis_id in sorted(hypotheses):
        node = hypotheses[hypothesis_id]
        assessment = assessments[hypothesis_id]
        state = _STATUS_TO_STATE[assessment["status"]]
        record = {
            "hypothesis_id": hypothesis_id,
            "statement": node["statement"],
            "epistemic_status": assessment["status"],
            "portfolio_state": state,
            "research_directive": _STATE_TO_DIRECTIVE[state],
            "verified_support_edges": list(assessment["verified_support_edges"]),
            "verified_contradiction_edges": list(
                assessment["verified_contradiction_edges"]
            ),
            "verified_falsification_edges": list(
                assessment["verified_falsification_edges"]
            ),
            "diagnostic_relation_edges": list(
                assessment["diagnostic_relation_edges"]
            ),
            "final_positive_support_granted": False,
            "confidence_score": None,
        }
        record["transition"] = _transition_label(
            prior_records.get(hypothesis_id),
            record,
        )
        records.append(record)

    states = [str(record["portfolio_state"]) for record in records]
    state_counts = dict(sorted(Counter(states).items()))
    result: dict[str, Any] = {
        "schema_version": HYPOTHESIS_PORTFOLIO_SCHEMA_VERSION,
        "policy_version": HYPOTHESIS_PORTFOLIO_POLICY_VERSION,
        "graph_id": graph_id,
        "research_scope": research_scope,
        "evaluated_graph_binding": {"canonical_sha256": _canonical_sha256(graph)},
        "plan_binding": {"plan_sha256": plan_sha},
        "previous_portfolio_sha256": previous_sha,
        "hypothesis_count": len(records),
        "state_counts": state_counts,
        "portfolio_directive": _portfolio_directive(states),
        "hypotheses": records,
        "autonomy_boundary": {
            "numeric_belief_probability_assigned": False,
            "final_positive_support_granted": False,
            "empirical_evidence_created": False,
            "domain_mechanism_invented": False,
            "scientific_status_changed": False,
            "execution_authorized": False,
            "physical_experiment_executed": False,
        },
    }
    result["portfolio_sha256"] = _canonical_sha256(result)
    return result


def validate_hypothesis_portfolio_for_plan(
    portfolio: Mapping[str, Any],
    *,
    plan: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate a portfolio's canonical identity and exact planning-cycle binding."""
    value = dict(_mapping(portfolio, "hypothesis_portfolio"))
    if value.get("schema_version") != HYPOTHESIS_PORTFOLIO_SCHEMA_VERSION:
        raise HypothesisPortfolioError("unsupported hypothesis portfolio schema_version")
    if value.get("policy_version") != HYPOTHESIS_PORTFOLIO_POLICY_VERSION:
        raise HypothesisPortfolioError("unsupported hypothesis portfolio policy_version")
    digest = _verified_portfolio_sha(value)
    plan_sha = _verified_plan_sha(plan)
    binding = _mapping(value.get("plan_binding"), "hypothesis_portfolio.plan_binding")
    bound_plan_sha = _sha256_text(
        binding.get("plan_sha256"),
        "hypothesis_portfolio.plan_binding.plan_sha256",
    )
    if bound_plan_sha != plan_sha:
        raise HypothesisPortfolioError(
            "hypothesis portfolio is not bound to the current planning cycle"
        )
    directive = _text(
        value.get("portfolio_directive"),
        "hypothesis_portfolio.portfolio_directive",
    )
    allowed_directives = {
        "prioritize_discrimination",
        "continue_bounded_discrimination",
        "domain_closeout_required",
        "bounded_stop_all_hypotheses_retired",
    }
    if directive not in allowed_directives:
        raise HypothesisPortfolioError(
            f"unsupported hypothesis portfolio directive: {directive}"
        )
    count = value.get("hypothesis_count")
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise HypothesisPortfolioError("hypothesis_count must be a positive integer")
    records = _sequence(value.get("hypotheses", []), "hypothesis_portfolio.hypotheses")
    if len(records) != count:
        raise HypothesisPortfolioError("hypothesis_count does not match hypotheses")
    return {
        "portfolio_sha256": digest,
        "portfolio_directive": directive,
        "hypothesis_count": count,
        "state_counts": dict(
            _mapping(value.get("state_counts", {}), "hypothesis_portfolio.state_counts")
        ),
    }


__all__ = [
    "HYPOTHESIS_PORTFOLIO_POLICY_VERSION",
    "HYPOTHESIS_PORTFOLIO_SCHEMA_VERSION",
    "HypothesisPortfolioError",
    "build_hypothesis_portfolio",
    "validate_hypothesis_portfolio_for_plan",
]
