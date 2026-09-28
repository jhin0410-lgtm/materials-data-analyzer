"""Bounded IN625 model-discrepancy inquiry after a published comparator.

This domain composer consumes an externally authenticated retrospective AMB2018-02
published-model evaluation and routes its unresolved interpretation through the existing
Scientific Critic -> Evidence Provider -> Research Agent path.

It deliberately does not reinterpret small A/C errors as prospective blind validation.
The highest-value unresolved question is provenance/chronology: whether comparable
performance existed in the original blind challenge submissions or emerged only after
post-challenge input corrections or model-form refinement.
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .evidence_packet import canonical_sha256
from .evidence_provider_contract import (
    AuthenticatedProviderStateInput,
    adapt_authenticated_planning_gaps,
)
from .evidence_provider_planning import build_provider_planner_program_state
from .research_agent import build_research_agent_iteration
from .scientific_critic import build_scientific_critic_report

SCHEMA_VERSION = "1.0"
POLICY_VERSION = "1.0"

QUESTION_NODE_ID = "question:in625-retrospective-vs-blind-generalization"
CLAIM_NODE_ID = "claim:retrospective-agreement-proves-blind-generalization"
ANALYSIS_NODE_ID = "analysis:published-retrospective-ac-comparator"

_HYPOTHESES: tuple[tuple[str, str], ...] = (
    (
        "H_generalizable_physics",
        "A Case-B-calibrated model form genuinely generalizes to Cases A/C under fixed parameters.",
    ),
    (
        "H_post_challenge_refinement",
        "The small retrospective A/C errors depend materially on model-form or parameter choices made after challenge-response information became available.",
    ),
    (
        "H_corrected_input_semantics",
        "Much of the retrospective improvement is explained by later corrected AMMT power, spot-size, or protocol semantics rather than response leakage.",
    ),
    (
        "H_target_metric_mismatch",
        "Apparent tension between historical blind performance and the retrospective comparator is partly due to different target systems, response metrics, aggregation, or measurement semantics.",
    ),
)


class In625ModelDiscrepancyInquiryError(ValueError):
    """Raised when the inquiry would exceed authenticated comparator evidence."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise In625ModelDiscrepancyInquiryError(message)


def _sha(value: object, field: str) -> str:
    _require(
        isinstance(value, str)
        and len(value) == 64
        and all(ch in "0123456789abcdef" for ch in value),
        f"{field} must be lowercase SHA-256",
    )
    return str(value)


def _write_json(path: Path, value: object) -> str:
    raw = (
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def _authenticate_evaluation(
    evaluation: Mapping[str, Any],
    *,
    trusted_evaluation_sha256: str,
) -> tuple[dict[str, Any], str]:
    trusted = _sha(trusted_evaluation_sha256, "trusted_evaluation_sha256")
    snapshot = copy.deepcopy(dict(evaluation))
    _require(
        canonical_sha256(snapshot) == trusted,
        "published comparator evaluation does not match external trust-root SHA-256",
    )
    unsigned = copy.deepcopy(snapshot)
    embedded = _sha(
        unsigned.pop("evaluation_sha256", None),
        "evaluation.evaluation_sha256",
    )
    _require(
        canonical_sha256(unsigned) == embedded,
        "published comparator evaluation self-hash mismatch",
    )
    _require(
        snapshot.get("evaluation_type")
        == "published_retrospective_amb2018_02_ac_comparison",
        "unsupported comparator evaluation type",
    )

    interpretation = snapshot.get("scientific_interpretation")
    boundary = snapshot.get("scientific_boundary")
    aggregate = snapshot.get("aggregate_ac_metrics")
    cases = snapshot.get("case_metrics")
    _require(isinstance(interpretation, Mapping), "scientific_interpretation is missing")
    _require(isinstance(boundary, Mapping), "scientific_boundary is missing")
    _require(isinstance(aggregate, Mapping), "aggregate_ac_metrics is missing")
    _require(isinstance(cases, list), "case_metrics is missing")
    _require(
        interpretation.get("parameter_fit_reported_case_b_only") is True
        and interpretation.get("published_parameters_fixed_for_a_c") is True
        and interpretation.get("strict_blind_model_selection_established") is False
        and interpretation.get("eligible_as_strict_phase1_holdout_prediction") is False
        and interpretation.get("eligible_as_retrospective_published_comparator") is True,
        "comparator interpretation boundary drifted",
    )
    _require(
        boundary.get("published_computational_result_is_empirical") is False
        and boundary.get("agreement_establishes_causality") is False
        and boundary.get("agreement_establishes_mechanistic_uniqueness") is False
        and boundary.get("prospective_blind_validation_established") is False
        and boundary.get("engineering_readiness_established") is False
        and boundary.get("scientific_status_promoted") is False,
        "comparator scientific authority was widened",
    )
    _require(
        aggregate.get("case_b_included") is False
        and aggregate.get("case_count") == 2,
        "A/C comparator aggregation contract drifted",
    )
    case_ids = [
        item.get("case_id")
        for item in cases
        if isinstance(item, Mapping)
    ]
    _require(
        len(cases) == 2 and sorted(case_ids) == ["A", "C"],
        "comparator must preserve exactly one A and one C case metric",
    )
    return snapshot, embedded


def _number(value: object, field: str) -> float:
    _require(
        isinstance(value, (int, float))
        and not isinstance(value, bool),
        f"{field} must be numeric",
    )
    numeric = float(value)
    _require(numeric >= 0.0 and numeric < float("inf"), f"{field} must be finite nonnegative")
    return numeric


def _graph(
    evaluation: Mapping[str, Any],
    *,
    evaluation_object_sha256: str,
    evaluation_file_sha256: str,
    evaluation_path: Path,
) -> dict[str, Any]:
    aggregate = evaluation["aggregate_ac_metrics"]
    width_mae = _number(aggregate.get("width_mae_um"), "aggregate width MAE")
    depth_mae = _number(aggregate.get("depth_mae_um"), "aggregate depth MAE")

    nodes: list[dict[str, Any]] = [
        {
            "node_id": QUESTION_NODE_ID,
            "node_type": "research_question",
            "statement": (
                "Does the small retrospective A/C error demonstrate blind-generalizable "
                "LPBF model validity, or does it require post-challenge/input-semantics "
                "explanations before that claim can be supported?"
            ),
        },
        {
            "node_id": CLAIM_NODE_ID,
            "node_type": "claim",
            "statement": (
                "The retrospective A/C agreement establishes prospective blind-generalizable "
                "predictive validity for the published model."
            ),
            "metadata": {
                "claim_scope": "predictive",
                "claim_origin": "retrospective_published_model_comparison",
                "strict_blind_model_selection_established": False,
            },
        },
        {
            "node_id": ANALYSIS_NODE_ID,
            "node_type": "analysis",
            "statement": (
                f"The source-bound retrospective comparator reports A/C width MAE "
                f"{width_mae:.6g} um and depth MAE {depth_mae:.6g} um, while its authenticated "
                "scope explicitly does not establish prospective blind model selection."
            ),
            "artifact_bindings": [
                {
                    "role": "primary_result",
                    "path": str(evaluation_path),
                    "sha256": evaluation_file_sha256,
                }
            ],
            "metadata": {
                "claim_scope": "diagnostic",
                "evaluation_object_sha256": evaluation_object_sha256,
                "computational_evidence_is_empirical": False,
            },
        },
    ]
    edges: list[dict[str, Any]] = [
        {
            "edge_id": "question-motivates:blind-generalization-claim",
            "source_node_id": QUESTION_NODE_ID,
            "target_node_id": CLAIM_NODE_ID,
            "relation": "motivates",
            "assessment_level": "proposal",
            "rationale": "The bounded question asks whether the retrospective result supports this stronger claim.",
            "active": True,
        },
        {
            "edge_id": "diagnostic-tests:retrospective-agreement",
            "source_node_id": ANALYSIS_NODE_ID,
            "target_node_id": CLAIM_NODE_ID,
            "relation": "tests",
            "assessment_level": "diagnostic",
            "rationale": (
                "The comparator quantifies A/C agreement but explicitly lacks strict blind "
                "model-selection provenance, so it is diagnostic rather than verified support."
            ),
            "active": True,
        },
    ]

    for hypothesis_id, statement in _HYPOTHESES:
        nodes.append(
            {
                "node_id": hypothesis_id,
                "node_type": "hypothesis",
                "statement": statement,
                "metadata": {
                    "claim_scope": "mixed",
                    "status": "open_competing_hypothesis",
                    "verified_positive": False,
                },
            }
        )
        edges.append(
            {
                "edge_id": f"question-motivates:{hypothesis_id}",
                "source_node_id": QUESTION_NODE_ID,
                "target_node_id": hypothesis_id,
                "relation": "motivates",
                "assessment_level": "proposal",
                "rationale": "The authenticated comparator does not uniquely discriminate this explanation.",
                "active": True,
            }
        )

    return {
        "schema_version": "1.0",
        "graph_id": "in625-model-discrepancy-inquiry-v1",
        "research_scope": "AMB2018-02 retrospective model agreement versus blind-generalization evidence",
        "nodes": nodes,
        "edges": edges,
        "metadata": {
            "authenticated_evaluation_sha256": evaluation_object_sha256,
            "hypothesis_truth_established": False,
            "scientific_status_promoted": False,
        },
    }


def _planning_state() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "state_type": "in625_model_discrepancy_unresolved_evidence",
        "unresolved_evidence_gaps": [
            {
                "gap_id": "in625-model-discrepancy:original-blind-submission-provenance",
                "requirement": (
                    "Acquire authoritative archived source/provenance evidence for the original "
                    "2018 AMB2018-02-MP blind challenge submissions, including submitted prediction "
                    "values, target system and response definitions, submission timing, and "
                    "response-availability/model-selection chronology needed to discriminate blind "
                    "generalization from post-challenge refinement."
                ),
                "action_class_hint": "external_evidence_search",
            },
            {
                "gap_id": "in625-model-discrepancy:correction-and-model-form-chronology",
                "requirement": (
                    "Acquire source-bound chronology for corrected AMMT power and spot-size "
                    "semantics and for model-form/parameter revisions relative to the original "
                    "challenge submission and response-release dates."
                ),
                "action_class_hint": "external_evidence_search",
            },
        ],
        "hypothesis_truth_established": False,
        "prospective_blind_validation_established": False,
        "scientific_status_changed": False,
    }


def _base_program() -> dict[str, Any]:
    return {
        "mission": {
            "mission_id": "in625-model-discrepancy-inquiry-v1",
            "research_question": (
                "What evidence best discriminates blind-generalizable physics from "
                "post-challenge refinement or corrected-input explanations?"
            ),
            "autonomy_policy": {
                "goal_generation": "bounded_autonomous",
                "reasoning_proposals": "schema_validated",
                "typed_computational_actions": "explicit_request",
                "network_evidence_search": "explicit_authorization",
                "physical_experiment_execution": "external_only",
            },
        },
        "generated_goals": [],
    }


def run_in625_model_discrepancy_inquiry(
    evaluation: Mapping[str, Any],
    *,
    trusted_evaluation_sha256: str,
    output_root: str | Path,
) -> dict[str, Any]:
    """Critique a verified retrospective result and select a bounded next evidence action."""

    snapshot, evaluation_sha = _authenticate_evaluation(
        evaluation,
        trusted_evaluation_sha256=trusted_evaluation_sha256,
    )
    root = Path(output_root).expanduser().resolve()
    _require(not root.exists(), "output_root must not already exist")
    root.mkdir(parents=True)

    evaluation_path = root / "authenticated_retrospective_evaluation.json"
    evaluation_file_sha = _write_json(evaluation_path, snapshot)
    graph = _graph(
        snapshot,
        evaluation_object_sha256=evaluation_sha,
        evaluation_file_sha256=evaluation_file_sha,
        evaluation_path=evaluation_path,
    )
    graph_path = root / "model_discrepancy_graph.json"
    graph_file_sha = _write_json(graph_path, graph)

    program = _base_program()
    critic = build_scientific_critic_report(
        graph_path,
        program_state=program,
        artifact_root=root,
        target_node_ids=[
            CLAIM_NODE_ID,
            *[hypothesis_id for hypothesis_id, _statement in _HYPOTHESES],
        ],
    )

    planning_state = _planning_state()
    planning_sha = canonical_sha256(planning_state)
    provider = adapt_authenticated_planning_gaps(
        planning_state,
        trusted_state_sha256=planning_sha,
    )
    provider_input = AuthenticatedProviderStateInput(
        state=provider,
        trusted_provider_state_sha256=provider["provider_state_sha256"],
    )
    program_with_gaps = build_provider_planner_program_state(
        program,
        [provider_input],
    )
    plan = build_research_agent_iteration(
        program_with_gaps,
        scientific_critic_report=critic,
        budget_units=8.0,
        minimum_utility=0.01,
        max_iterations=8,
    )

    selected = plan.get("selected_next_action")
    _require(isinstance(selected, Mapping), "model-discrepancy inquiry selected no next action")
    _require(
        selected.get("action_class") == "external_evidence_search",
        "model-discrepancy inquiry did not prioritize the unresolved provenance evidence path",
    )
    _require(
        selected.get("automatic_execution_authorized") is False,
        "selected evidence search was automatically authorized",
    )
    generated = plan.get("self_generated_gap_actions")
    _require(isinstance(generated, list), "planner generated-action frontier is missing")
    generated_searches = [
        item
        for item in generated
        if isinstance(item, Mapping)
        and item.get("action_class") == "external_evidence_search"
    ]
    _require(
        len(generated_searches) >= 2,
        "model-discrepancy inquiry must preserve multiple source-evidence routes",
    )

    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "policy_version": POLICY_VERSION,
        "inquiry_type": "in625_retrospective_model_discrepancy",
        "ancestry": {
            "retrospective_evaluation_sha256": evaluation_sha,
            "retrospective_evaluation_file_sha256": evaluation_file_sha,
            "epistemic_graph_file_sha256": graph_file_sha,
            "planning_state_sha256": planning_sha,
            "provider_state_sha256": provider["provider_state_sha256"],
            "critic_report_sha256": canonical_sha256(critic),
            "planner_plan_sha256": plan["plan_sha256"],
        },
        "competing_hypotheses": [
            {
                "hypothesis_id": hypothesis_id,
                "statement": statement,
                "status": "open",
                "verified_positive": False,
            }
            for hypothesis_id, statement in _HYPOTHESES
        ],
        "critic_report": critic,
        "planning_state": planning_state,
        "plan": plan,
        "bounded_interpretation": {
            "retrospective_agreement_observed": True,
            "prospective_blind_validation_established": False,
            "generalizable_physics_established": False,
            "post_challenge_refinement_established": False,
            "corrected_input_semantics_explanation_established": False,
            "target_metric_mismatch_explanation_established": False,
            "highest_value_next_evidence": (
                "source-bound original blind challenge submissions and model-selection chronology"
            ),
        },
        "authority_boundary": {
            "network_execution_authorized": False,
            "physical_experiment_execution_authorized": False,
            "published_computational_result_promoted_to_empirical": False,
            "hypothesis_truth_established": False,
            "engineering_readiness_established": False,
            "scientific_status_promoted": False,
        },
    }
    result["inquiry_sha256"] = canonical_sha256(result)
    _write_json(root / "model_discrepancy_inquiry.json", result)
    return result


__all__ = [
    "ANALYSIS_NODE_ID",
    "CLAIM_NODE_ID",
    "In625ModelDiscrepancyInquiryError",
    "POLICY_VERSION",
    "QUESTION_NODE_ID",
    "SCHEMA_VERSION",
    "run_in625_model_discrepancy_inquiry",
]
