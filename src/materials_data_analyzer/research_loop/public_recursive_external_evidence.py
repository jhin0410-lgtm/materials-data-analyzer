"""Public recursive planner bridge for a real IN625 external-evidence candidate.

This module is the positive counterpart to the bounded external-evidence waiting state. It
may expose an already repository-registered real source as a planner candidate only when the
exact discrepancy objective, typed request, action registry, source config, archive bytes,
and immutable research ledger independently verify. It grants no execution or scientific
authority by itself.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .action_registry import describe_action, load_action_registry
from .in625_execution_verifier import verify_in625_execution_handoff
from .in625_external_evidence_action import ACTION_TYPE, ACTION_VERSION
from .kernel import ResearchLoopError
from .planning_adapter import plan_research_next_action
from .public_recursive_planning import (
    PublicRecursivePlanningError,
    validate_public_recursive_discrepancy_planning_handoff,
)

ADAPTER_ID = "in625-external-evidence"
EXTERNAL_EVIDENCE_RECURSIVE_BRIDGE_SCHEMA_VERSION = "1.0"
EXTERNAL_EVIDENCE_RECURSIVE_BRIDGE_POLICY_VERSION = "1.0"


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PublicRecursivePlanningError(f"{field} must be an object")
    return value


def _sequence(value: object, field: str) -> Sequence[object]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise PublicRecursivePlanningError(f"{field} must be a sequence")
    return value


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise PublicRecursivePlanningError(f"{field} must be non-empty trimmed text")
    return value


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PublicRecursivePlanningError(f"duplicate JSON key is not allowed: {key}")
        result[key] = value
    return result


def _request_snapshot(path: str | Path) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        request_path = Path(path).expanduser().resolve(strict=True)
        raw = request_path.read_bytes()
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_pairs)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PublicRecursivePlanningError("IN625 execution request is not stable UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise PublicRecursivePlanningError("IN625 execution request root must be an object")
    return value, {
        "path": str(request_path),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
    }


def _autonomy_policy() -> dict[str, str]:
    return {
        "goal_generation": "bounded_autonomous",
        "reasoning_proposals": "schema_validated",
        "typed_computational_actions": "explicit_request",
        "network_evidence_search": "explicit_authorization",
        "physical_experiment_execution": "external_only",
    }


def build_external_evidence_recursive_planner_program_state(
    *,
    planning_handoff: Mapping[str, Any],
    discrepancy_report: Mapping[str, Any],
    evaluated_graph: Mapping[str, Any],
    repository_root: str | Path,
    research_run: str | Path,
    action_registry_path: str | Path,
    request_path: str | Path,
    previous_discrepancy_report: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Expose the exact verified IN625 external source as one recursive planner candidate."""
    handoff_check = validate_public_recursive_discrepancy_planning_handoff(
        planning_handoff,
        discrepancy_report=discrepancy_report,
        evaluated_graph=evaluated_graph,
        previous_discrepancy_report=previous_discrepancy_report,
    )
    objectives = [
        dict(_mapping(item, "research_objective"))
        for item in _sequence(planning_handoff.get("research_objectives", []), "research_objectives")
    ]
    matches = [
        item for item in objectives if item.get("research_action_class") == "external_evidence_search"
    ]
    if len(matches) != 1:
        raise PublicRecursivePlanningError(
            "real external-evidence recursive planning requires exactly one external_evidence_search objective"
        )

    try:
        execution_pin = verify_in625_execution_handoff(
            repository_root=repository_root,
            research_run=research_run,
            action_registry_path=action_registry_path,
            request_path=request_path,
        )
        live_plan = plan_research_next_action(
            ADAPTER_ID,
            repository_root=repository_root,
            research_run=research_run,
            action_registry_path=action_registry_path,
        )
    except ResearchLoopError as exc:
        raise PublicRecursivePlanningError(
            "verified IN625 live planning/request pins are unavailable"
        ) from exc
    if live_plan.get("selection_status") != "ready_to_execute":
        raise PublicRecursivePlanningError(
            "IN625 planning adapter did not expose an executable external-evidence candidate"
        )
    selected = _mapping(live_plan.get("selected_action"), "live_in625_plan.selected_action")
    request, request_record = _request_snapshot(request_path)
    if request_record["sha256"] != execution_pin.get("request_sha256"):
        raise PublicRecursivePlanningError("IN625 request changed after independent verifier handoff")
    if (
        request.get("action_type") != ACTION_TYPE
        or request.get("action_version") != ACTION_VERSION
        or selected.get("action_type") != ACTION_TYPE
        or selected.get("action_version") != ACTION_VERSION
    ):
        raise PublicRecursivePlanningError("IN625 request and selected action type/version differ")
    registry = load_action_registry(action_registry_path, repository_root=repository_root)
    contract = describe_action(registry, ACTION_TYPE)
    if contract.get("category") != "external_evidence_search":
        raise PublicRecursivePlanningError("IN625 registry category is not external_evidence_search")
    if selected.get("execution_registry_sha256") != registry.get("registry_sha256"):
        raise PublicRecursivePlanningError("IN625 selected-action registry binding drifted")
    if execution_pin.get("registry_sha256") != registry.get("registry_sha256"):
        raise PublicRecursivePlanningError("IN625 verifier and planner registry SHA differ")
    if request.get("expected_archive_sha256") != execution_pin.get("archive_sha256"):
        raise PublicRecursivePlanningError("IN625 request and verifier archive SHA differ")
    if request.get("expected_source_config_sha256") != execution_pin.get("source_config_sha256"):
        raise PublicRecursivePlanningError("IN625 request and verifier source-config SHA differ")

    objective = matches[0]
    action_id = _text(request.get("action_id"), "IN625 execution request action_id")
    action = {
        "action_id": action_id,
        "action_class": "external_evidence_search",
        "description": (
            "Register the exact real IN625 Zenodo archive already bound by the typed request and independent verifier."
        ),
        "rationale": str(
            objective.get("rationale")
            or "Resolve the verified empirical-evidence availability gap without synthesizing an observation."
        ),
        "required_evidence": [
            "Exact repository-pinned source-config SHA-256",
            "Exact real external archive SHA-256",
            "Immutable research-ledger SHA-256 before execution",
        ],
        "expected_outcome": (
            "A typed immutable-ledger source-provenance record that can enter later scientific intake; no condition-comparability or truth claim."
        ),
        "execution_mode": "typed_local_action",
        "expected_information_score": 0.85,
        "hypothesis_discrimination_score": 0.55,
        "feasibility_score": 0.95,
        "cost_units": float(selected.get("cost_units", 2.0)),
        "risk_penalty": 0.05,
    }
    return {
        "schema_version": EXTERNAL_EVIDENCE_RECURSIVE_BRIDGE_SCHEMA_VERSION,
        "policy_version": EXTERNAL_EVIDENCE_RECURSIVE_BRIDGE_POLICY_VERSION,
        "mission": {"autonomy_policy": _autonomy_policy()},
        "generated_goals": [
            {
                "goal_id": "public-recursive:acquire-real-empirical-evidence",
                "workstream_id": "in625-external-empirical-evidence",
                "research_question": "Can a real provenance-bound external IN625 source reduce the verified empirical-evidence gap?",
                "goal_statement": (
                    "Register real independent IN625 source evidence without inventing measurements or widening scientific authority."
                ),
                "status": "active",
                "priority": 100,
                "evidence_requirements": [
                    "A real externally acquired archive",
                    "Exact source/provenance identity",
                    "Independent request/registry/archive/ledger verification",
                    "Subsequent domain-specific scientific intake before claim promotion",
                ],
                "claim_boundary": {
                    "synthetic_measurement_allowed": False,
                    "condition_comparability_claimed": False,
                    "empirical_model_validation_claimed": False,
                    "hypothesis_truth_claimed": False,
                },
                "action_frontier": [action],
            }
        ],
        "public_recursive_planner_binding": {
            "handoff_sha256": handoff_check["handoff_sha256"],
            "source_discrepancy_report_sha256": handoff_check[
                "source_discrepancy_report_sha256"
            ],
            "matched_objective_id": objective["objective_id"],
            "execution_request": request_record,
            "execution_request_action_id": action_id,
            "execution_handoff": dict(execution_pin),
            "planning_adapter_selection_status": live_plan.get("selection_status"),
            "planning_adapter_selected_action": dict(selected),
            "registry_id": registry["registry_id"],
            "registry_sha256": registry["registry_sha256"],
            "repository_authorized_external_candidate_available": True,
            "available_external_evidence_action_count": 1,
            "candidate_created_from_live_planning_adapter_and_typed_request": True,
            "caller_injected_candidate": False,
            "synthetic_candidate_created": False,
            "network_access_performed_by_planner": False,
            "authorization_granted": False,
            "execution_performed": False,
            "scientific_status_changed": False,
        },
    }


__all__ = [
    "EXTERNAL_EVIDENCE_RECURSIVE_BRIDGE_POLICY_VERSION",
    "EXTERNAL_EVIDENCE_RECURSIVE_BRIDGE_SCHEMA_VERSION",
    "build_external_evidence_recursive_planner_program_state",
]
