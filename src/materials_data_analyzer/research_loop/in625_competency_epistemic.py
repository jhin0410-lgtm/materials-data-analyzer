"""Canonical epistemic/critic bridge for the first IN625 competency episode.

This module composes existing epistemic-graph, authenticated-transition, independent
transition-consumer, and Scientific Critic primitives around the verified mds2 spot-size
sensitivity action.  It deliberately avoids turning the descriptive sensitivity result
into proof that cross-source protocol equivalence is false.

The narrow supported proposition is structural:

    spot diameter must remain explicit comparison context because the authenticated
    mds2 target subset contains multiple source-native spot levels.

The original benchmark hypotheses remain open and are re-criticized after the transition.
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .authenticated_epistemic_transition import (
    apply_authenticated_epistemic_transition_files,
)
from .authenticated_transition_consumer import authenticate_transition_bundle
from .comparability_engine import AuthenticatedEvidenceInput
from .evidence_packet import canonical_sha256
from .in625_spot_size_sensitivity import (
    ACTION_TYPE,
    ACTION_VERSION,
    verify_in625_spot_size_sensitivity,
)
from .scientific_critic import build_scientific_critic_report

EPISTEMIC_BRIDGE_SCHEMA_VERSION = "1.0"
EPISTEMIC_BRIDGE_POLICY_VERSION = "1.0"
BASE_GRAPH_ID = "in625-competency-graph-v1"
SUCCESSOR_GRAPH_ID = "in625-competency-graph-v2"
SPOT_CONTEXT_CLAIM_ID = "claim:mds2-spot-context-must-remain-explicit"


class In625CompetencyEpistemicError(ValueError):
    """Raised when the IN625 epistemic bridge would exceed verified evidence."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise In625CompetencyEpistemicError(message)


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


def _write_json(path: Path, value: object) -> str:
    raw = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def _program_state() -> dict[str, Any]:
    return {
        "mission": {
            "mission_id": "in625-autonomous-scientist-competency-benchmark-v1",
            "autonomy_policy": {
                "reasoning_proposals": "schema_validated",
            },
        },
        "mission_binding": None,
        "runtime_context_binding": None,
        "workstreams": [],
        "generated_goals": [],
    }


def build_in625_competency_base_graph(
    bootstrap: Mapping[str, Any],
    *,
    trusted_bootstrap_sha256: str,
) -> dict[str, Any]:
    """Project the authenticated benchmark hypotheses into the canonical graph schema."""

    snapshot, bootstrap_sha = _authenticate_snapshot(
        bootstrap,
        trusted_sha256=trusted_bootstrap_sha256,
        embedded_sha_field="bootstrap_sha256",
        field="bootstrap",
    )
    portfolio = snapshot.get("hypothesis_portfolio")
    _require(isinstance(portfolio, list) and len(portfolio) >= 2, "hypothesis portfolio is missing")
    question = snapshot.get("research_question")
    _require(isinstance(question, str) and bool(question.strip()), "research question is missing")

    nodes: list[dict[str, Any]] = [
        {
            "node_id": "question:in625-cross-source-comparison",
            "node_type": "research_question",
            "statement": question.strip(),
        }
    ]
    edges: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(portfolio):
        _require(isinstance(raw, Mapping), f"hypothesis_portfolio[{index}] must be an object")
        hypothesis_id = raw.get("hypothesis_id")
        statement = raw.get("statement")
        _require(
            isinstance(hypothesis_id, str) and bool(hypothesis_id),
            f"hypothesis_portfolio[{index}].hypothesis_id is missing",
        )
        _require(hypothesis_id not in seen, "hypothesis ids must be unique")
        _require(
            isinstance(statement, str) and bool(statement.strip()),
            f"hypothesis_portfolio[{index}].statement is missing",
        )
        seen.add(hypothesis_id)
        nodes.append(
            {
                "node_id": hypothesis_id,
                "node_type": "hypothesis",
                "statement": statement.strip(),
                "metadata": {
                    "claim_scope": "mixed",
                    "benchmark_initial_status": raw.get("status"),
                    "benchmark_verified_positive": raw.get("verified_positive"),
                    "benchmark_blocking_observation": raw.get("blocking_observation"),
                },
            }
        )
        edges.append(
            {
                "edge_id": f"question-motivates:{hypothesis_id}",
                "source_node_id": "question:in625-cross-source-comparison",
                "target_node_id": hypothesis_id,
                "relation": "motivates",
                "assessment_level": "proposal",
                "rationale": "The bounded benchmark question requires this competing state to remain explicit.",
                "active": True,
            }
        )

    nodes.append(
        {
            "node_id": SPOT_CONTEXT_CLAIM_ID,
            "node_type": "claim",
            "statement": (
                "Spot diameter must remain explicit comparison context for the mds2 AMMT "
                "195 W / 800 mm/s target subset rather than being silently ignored."
            ),
            "metadata": {
                "claim_scope": "structural",
                "claim_origin": "verified benchmark protocol/spot evidence gap",
            },
        }
    )
    edges.append(
        {
            "edge_id": "question-motivates:spot-context-claim",
            "source_node_id": "question:in625-cross-source-comparison",
            "target_node_id": SPOT_CONTEXT_CLAIM_ID,
            "relation": "motivates",
            "assessment_level": "proposal",
            "rationale": "Protocol comparability requires explicit treatment of varying source-native context.",
            "active": True,
        }
    )

    return {
        "schema_version": "1.0",
        "graph_id": BASE_GRAPH_ID,
        "research_scope": (
            "IN625 NIST AM-Bench versus mds2-2923 direct-comparison competency benchmark"
        ),
        "nodes": nodes,
        "edges": edges,
        "metadata": {
            "authenticated_bootstrap_sha256": bootstrap_sha,
            "scientific_status_promoted": False,
        },
    }


def _critic_digest(report: Mapping[str, Any]) -> str:
    embedded = report.get("report_sha256")
    if isinstance(embedded, str) and len(embedded) == 64:
        return embedded
    return canonical_sha256(report)


def run_in625_spot_epistemic_transition_and_critic(
    *,
    bootstrap: Mapping[str, Any],
    trusted_bootstrap_sha256: str,
    request: Mapping[str, Any],
    authorization_receipt: Mapping[str, Any],
    trusted_authorization_sha256: str,
    sensitivity_result: Mapping[str, Any],
    trusted_result_sha256: str,
    evidence_inputs: Sequence[AuthenticatedEvidenceInput],
    output_root: str | Path,
) -> dict[str, Any]:
    """Verify the action, publish an authenticated diagnostic transition, and re-criticize."""

    result_snapshot, result_embedded = _authenticate_snapshot(
        sensitivity_result,
        trusted_sha256=trusted_result_sha256,
        embedded_sha_field="result_sha256",
        field="sensitivity_result",
    )
    verified = verify_in625_spot_size_sensitivity(
        result_snapshot,
        request=request,
        authorization_receipt=authorization_receipt,
        trusted_authorization_sha256=trusted_authorization_sha256,
        evidence_inputs=evidence_inputs,
    )
    _require(
        verified.get("result_sha256") == result_embedded,
        "independent sensitivity verification changed the result identity",
    )
    interpretation = verified.get("scientific_interpretation")
    _require(isinstance(interpretation, Mapping), "verified interpretation is missing")
    _require(
        interpretation.get("protocol_spot_context_can_be_ignored") is False
        and interpretation.get("protocol_equivalence_established") is False
        and interpretation.get("cross_source_numerical_validation_authorized") is False,
        "verified result widened the protocol/comparability conclusion",
    )

    request_snapshot = copy.deepcopy(dict(request))
    request_sha = _sha(request_snapshot.get("request_sha256"), "request.request_sha256")
    unsigned_request = copy.deepcopy(request_snapshot)
    unsigned_request.pop("request_sha256", None)
    _require(
        canonical_sha256(unsigned_request) == request_sha,
        "request embedded self-hash mismatch",
    )
    selected = request_snapshot.get("selected_planner_action")
    _require(isinstance(selected, Mapping), "request selected planner action is missing")
    action_id = selected.get("action_id")
    _require(isinstance(action_id, str) and bool(action_id), "selected action_id is missing")
    _require(
        selected.get("action_class") == "sensitivity_analysis",
        "epistemic bridge accepts only the selected sensitivity analysis",
    )

    root = Path(output_root).expanduser().resolve()
    _require(not root.exists(), "output_root must not already exist")
    root.mkdir(parents=True)
    inputs_dir = root / "inputs"
    inputs_dir.mkdir()
    bundle_dir = root / "transition_bundle"

    base_graph = build_in625_competency_base_graph(
        bootstrap,
        trusted_bootstrap_sha256=trusted_bootstrap_sha256,
    )
    base_path = inputs_dir / "base_graph.json"
    base_sha = _write_json(base_path, base_graph)

    result_path = inputs_dir / "verified_spot_sensitivity_result.json"
    result_file_sha = _write_json(result_path, verified)

    program_state = _program_state()
    pre_critic = build_scientific_critic_report(
        base_path,
        program_state=program_state,
        artifact_root=root,
    )

    proposal = {
        "schema_version": "1.0",
        "transition_id": "in625-spot-sensitivity-transition-v1",
        "base_graph_id": BASE_GRAPH_ID,
        "base_graph_sha256": base_sha,
        "new_graph_id": SUCCESSOR_GRAPH_ID,
        "target_node_id": SPOT_CONTEXT_CLAIM_ID,
        "source_action": {
            "action_id": action_id,
            "action_class": "sensitivity_analysis",
            "action_version": ACTION_VERSION,
            "execution_mode": "typed_local_action",
        },
        "result_node": {
            "node_id": "analysis:in625-mds2-spot-size-sensitivity-v1",
            "node_type": "analysis",
            "statement": (
                "Authenticated mds2 rows were reanalyzed across seven source-native spot "
                "diameter levels at fixed 195 W / 800 mm/s machine settings."
            ),
            "artifact_bindings": [
                {
                    "role": "primary_result",
                    "path": str(result_path),
                    "sha256": result_file_sha,
                }
            ],
            "metadata": {
                "result_origin": "authorized_local_analysis",
                "claim_scope": "structural",
                "notes": {
                    "action_type": ACTION_TYPE,
                    "result_object_sha256": result_embedded,
                    "causal_claim_created": False,
                    "protocol_equivalence_established": False,
                },
            },
        },
        "input_evidence_bindings": [],
        "proposed_inference": {
            "tests_edge_id": "tests:spot-context-explicitness",
            "inference_edge_id": "supports:spot-context-explicitness",
            "relation": "supports",
            "rationale": (
                "The authenticated subset contains seven source-native spot levels; therefore "
                "spot diameter cannot be silently erased from comparison context."
            ),
        },
        "limitations": [
            "The result is descriptive within one authenticated source.",
            "It does not establish spot-size causality.",
            "It does not establish NIST-to-mds2 protocol equivalence.",
            "It does not establish calibrated-power transfer or Issue #76 completion.",
        ],
    }
    proposal_path = inputs_dir / "transition_proposal.json"
    proposal_sha = _write_json(proposal_path, proposal)

    verification = {
        "schema_version": "1.1",
        "decision_id": "in625-spot-context-verification-v1",
        "transition_id": proposal["transition_id"],
        "proposal_sha256": proposal_sha,
        "base_graph_sha256": base_sha,
        "inference_edge_id": proposal["proposed_inference"]["inference_edge_id"],
        "result_node_id": proposal["result_node"]["node_id"],
        "target_node_id": SPOT_CONTEXT_CLAIM_ID,
        "relation": "supports",
        "inference_scope": "structural",
        "verifier_id": "in625-mds2-spot-context-structural-verifier-v1",
        "rationale": (
            "Independent action recomputation verifies only the structural proposition that "
            "spot diameter is non-constant and must remain explicit context."
        ),
        "limitations": [
            "No empirical causal inference is granted.",
            "No cross-source comparability or positive scientific closeout is granted.",
        ],
        "domain_verified": True,
    }
    verification_path = inputs_dir / "verification_decision.json"
    verification_file_sha = _write_json(verification_path, verification)

    apply_authenticated_epistemic_transition_files(
        base_graph_path=base_path,
        proposal_path=proposal_path,
        verification_decision_path=verification_path,
        program_state=program_state,
        artifact_root=root,
        output_dir=bundle_dir,
    )
    consumer = authenticate_transition_bundle(bundle_dir)
    _require(
        consumer.get("current_transition_exact_provenance_authenticated") is True,
        "transition consumer did not authenticate exact provenance",
    )
    authority = consumer.get("authority_boundary")
    _require(isinstance(authority, Mapping), "transition consumer authority boundary is missing")
    _require(
        authority.get("scientific_authority_applied") is False
        and authority.get("positive_closeout_granted") is False
        and authority.get("execution_authorized") is False,
        "transition consumer widened authority",
    )

    post_critic = build_scientific_critic_report(
        bundle_dir / "epistemic_graph.json",
        program_state=program_state,
        artifact_root=bundle_dir,
    )
    post_targets = post_critic.get("target_reports")
    _require(isinstance(post_targets, list), "post-transition critic target reports are missing")
    spot_reports = [
        item
        for item in post_targets
        if isinstance(item, Mapping) and item.get("target_node_id") == SPOT_CONTEXT_CLAIM_ID
    ]
    _require(len(spot_reports) == 1, "spot-context claim must have exactly one critic report")
    spot_report = spot_reports[0]
    assessment = spot_report.get("epistemic_assessment")
    _require(isinstance(assessment, Mapping), "spot-context critic assessment is missing")
    _require(
        assessment.get("status") == "inconclusive"
        and assessment.get("verified_support_edges") == []
        and "supports:spot-context-explicitness"
        in assessment.get("diagnostic_relation_edges", []),
        "producer/consumer transition must remain diagnostic before separate authority review",
    )

    result: dict[str, Any] = {
        "schema_version": EPISTEMIC_BRIDGE_SCHEMA_VERSION,
        "policy_version": EPISTEMIC_BRIDGE_POLICY_VERSION,
        "episode_stage": "authenticated_transition_and_scientific_critic",
        "ancestry": {
            "bootstrap_sha256": base_graph["metadata"]["authenticated_bootstrap_sha256"],
            "request_sha256": request_sha,
            "verified_result_sha256": result_embedded,
            "base_graph_file_sha256": base_sha,
            "proposal_file_sha256": proposal_sha,
            "verification_file_sha256": verification_file_sha,
            "transition_graph_sha256": consumer["graph_binding"]["sha256"],
            "pre_critic_sha256": _critic_digest(pre_critic),
            "post_critic_sha256": _critic_digest(post_critic),
        },
        "transition_consumer": consumer,
        "pre_action_critic": pre_critic,
        "post_action_critic": post_critic,
        "scientific_boundary": {
            "spot_context_explicitness_supported_by_verified_action": True,
            "directional_edge_still_diagnostic_in_producer_graph": True,
            "original_competing_hypotheses_closed": False,
            "protocol_equivalence_established": False,
            "calibrated_power_relation_established": False,
            "direct_numerical_cross_source_validation_authorized": False,
            "issue_76_exact_target_cells_satisfied": 0,
            "positive_scientific_closeout_granted": False,
        },
        "authority_boundary": {
            "new_planner_introduced": False,
            "new_executor_introduced": False,
            "automatic_execution_authorized": False,
            "scientific_status_promoted": False,
        },
    }
    result["episode_transition_sha256"] = canonical_sha256(result)
    return result


__all__ = [
    "BASE_GRAPH_ID",
    "EPISTEMIC_BRIDGE_POLICY_VERSION",
    "EPISTEMIC_BRIDGE_SCHEMA_VERSION",
    "In625CompetencyEpistemicError",
    "SPOT_CONTEXT_CLAIM_ID",
    "SUCCESSOR_GRAPH_ID",
    "build_in625_competency_base_graph",
    "run_in625_spot_epistemic_transition_and_critic",
]
