"""Close one bounded recursive cycle by validating re-diagnosis and re-entering planning.

This layer does not rebuild scientific evidence.  It requires the current discrepancy
report to pass the existing discrepancy validator against the post-transition graph and
portfolio, requires that report to bind the prior discrepancy report, then delegates to
the existing discrepancy-planning handoff builder.  The output is therefore another
planning-only handoff, not an executable action.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any

from .discrepancy_planning_handoff import build_discrepancy_planning_handoff
from .kernel import ResearchLoopError
from .model_evidence_discrepancy import validate_model_evidence_discrepancy_report
from .recursive_research_cycle_controller import (
    RECURSIVE_CYCLE_POLICY_VERSION,
    RECURSIVE_CYCLE_SCHEMA_VERSION,
)
from .recursive_research_cycle_evidence import RECURSIVE_EVIDENCE_POLICY_VERSION

RECURSIVE_REDIAGNOSIS_POLICY_VERSION = "1.0"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class RecursiveResearchRediagnosisError(ResearchLoopError):
    """Raised when recursive re-diagnosis ancestry or planning re-entry drifts."""


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
        raise RecursiveResearchRediagnosisError(
            "recursive re-diagnosis state must be canonical-JSON serializable"
        ) from exc
    return hashlib.sha256(payload).hexdigest()


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RecursiveResearchRediagnosisError(f"{field} must be an object")
    return value


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise RecursiveResearchRediagnosisError(f"{field} must be non-empty trimmed text")
    return value


def _sha(value: object, field: str) -> str:
    text = _text(value, field)
    if _SHA256.fullmatch(text) is None:
        raise RecursiveResearchRediagnosisError(f"{field} must be lowercase SHA-256")
    return text


def _embedded_sha(value: Mapping[str, Any], *, field: str, sha_field: str) -> str:
    snapshot = dict(value)
    digest = _sha(snapshot.pop(sha_field, None), f"{field}.{sha_field}")
    if _canonical_sha256(snapshot) != digest:
        raise RecursiveResearchRediagnosisError(
            f"{field}.{sha_field} does not match canonical content"
        )
    return digest


def _authorization_checkpoint(
    checkpoint: Mapping[str, Any],
) -> tuple[str, Mapping[str, Any], str]:
    if checkpoint.get("schema_version") != RECURSIVE_CYCLE_SCHEMA_VERSION:
        raise RecursiveResearchRediagnosisError(
            "unsupported authorization checkpoint schema_version"
        )
    if checkpoint.get("policy_version") != RECURSIVE_CYCLE_POLICY_VERSION:
        raise RecursiveResearchRediagnosisError(
            "unsupported authorization checkpoint policy_version"
        )
    digest = _embedded_sha(
        checkpoint,
        field="authorization_checkpoint",
        sha_field="checkpoint_sha256",
    )
    if checkpoint.get("checkpoint_status") != "explicit_authorization_required":
        raise RecursiveResearchRediagnosisError(
            "re-diagnosis cycle must descend from an authorization-required checkpoint"
        )
    target = _mapping(checkpoint.get("target"), "authorization_checkpoint.target")
    ancestry = _mapping(checkpoint.get("ancestry"), "authorization_checkpoint.ancestry")
    previous_report_sha = _sha(
        ancestry.get("source_discrepancy_report_sha256"),
        "authorization_checkpoint.ancestry.source_discrepancy_report_sha256",
    )
    return digest, target, previous_report_sha


def _progression(
    progression: Mapping[str, Any],
    *,
    checkpoint_sha: str,
    target: Mapping[str, Any],
    evaluated_graph: Mapping[str, Any],
    hypothesis_portfolio: Mapping[str, Any],
) -> str:
    if progression.get("schema_version") != RECURSIVE_CYCLE_SCHEMA_VERSION:
        raise RecursiveResearchRediagnosisError("unsupported progression schema_version")
    if progression.get("policy_version") != RECURSIVE_EVIDENCE_POLICY_VERSION:
        raise RecursiveResearchRediagnosisError("unsupported progression policy_version")
    digest = _embedded_sha(
        progression,
        field="progression",
        sha_field="progression_sha256",
    )
    if progression.get("progression_status") != "re_diagnosis_required":
        raise RecursiveResearchRediagnosisError(
            "progression does not require another discrepancy diagnosis"
        )
    if progression.get("target") != target:
        raise RecursiveResearchRediagnosisError(
            "progression target differs from authorization checkpoint target"
        )
    ancestry = _mapping(progression.get("ancestry"), "progression.ancestry")
    if ancestry.get("authorization_checkpoint_sha256") != checkpoint_sha:
        raise RecursiveResearchRediagnosisError(
            "progression is bound to a different authorization checkpoint"
        )
    graph_sha = _canonical_sha256(evaluated_graph)
    if ancestry.get("evaluated_graph_canonical_sha256") != graph_sha:
        raise RecursiveResearchRediagnosisError(
            "progression is bound to a different evaluated graph"
        )
    portfolio_sha = _embedded_sha(
        hypothesis_portfolio,
        field="hypothesis_portfolio",
        sha_field="portfolio_sha256",
    )
    if ancestry.get("hypothesis_portfolio_sha256") != portfolio_sha:
        raise RecursiveResearchRediagnosisError(
            "progression is bound to a different hypothesis portfolio"
        )
    return digest


def complete_recursive_cycle_with_rediagnosis(
    *,
    authorization_checkpoint: Mapping[str, Any],
    progression: Mapping[str, Any],
    current_discrepancy_report: Mapping[str, Any],
    previous_discrepancy_report: Mapping[str, Any],
    evaluated_graph: Mapping[str, Any],
    hypothesis_portfolio: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate post-result re-diagnosis and project it into a new planning-only handoff."""
    checkpoint = _mapping(authorization_checkpoint, "authorization_checkpoint")
    progress = _mapping(progression, "progression")
    current = _mapping(current_discrepancy_report, "current_discrepancy_report")
    previous = _mapping(previous_discrepancy_report, "previous_discrepancy_report")
    graph = _mapping(evaluated_graph, "evaluated_graph")
    portfolio = _mapping(hypothesis_portfolio, "hypothesis_portfolio")

    checkpoint_sha, target, expected_previous_report_sha = _authorization_checkpoint(checkpoint)
    progression_sha = _progression(
        progress,
        checkpoint_sha=checkpoint_sha,
        target=target,
        evaluated_graph=graph,
        hypothesis_portfolio=portfolio,
    )
    previous_report_sha = _embedded_sha(
        previous,
        field="previous_discrepancy_report",
        sha_field="report_sha256",
    )
    if previous_report_sha != expected_previous_report_sha:
        raise RecursiveResearchRediagnosisError(
            "recursive cycle previous discrepancy report differs from checkpoint ancestry"
        )

    verified = validate_model_evidence_discrepancy_report(
        current,
        evaluated_graph=graph,
        hypothesis_portfolio=portfolio,
        previous_report=previous,
    )
    current_report_sha = _sha(
        verified.get("report_sha256"),
        "validated_current_discrepancy_report.report_sha256",
    )
    if current_report_sha == previous_report_sha:
        raise RecursiveResearchRediagnosisError(
            "re-diagnosis must not reuse the previous discrepancy report bytes"
        )
    current_target = _mapping(current.get("target"), "current_discrepancy_report.target")
    if current_target != target:
        raise RecursiveResearchRediagnosisError(
            "re-diagnosis target differs from recursive cycle target"
        )
    input_bindings = _mapping(
        current.get("input_bindings"),
        "current_discrepancy_report.input_bindings",
    )
    bound_previous = _mapping(
        input_bindings.get("previous_discrepancy_report"),
        "current_discrepancy_report.input_bindings.previous_discrepancy_report",
    )
    if bound_previous.get("report_sha256") != previous_report_sha:
        raise RecursiveResearchRediagnosisError(
            "current discrepancy report does not preserve exact previous-report ancestry"
        )

    next_handoff = build_discrepancy_planning_handoff(
        current,
        evaluated_graph=graph,
        hypothesis_portfolio=portfolio,
        previous_discrepancy_report=previous,
    )
    boundary = _mapping(next_handoff.get("planner_boundary"), "next_planning_handoff.planner_boundary")
    if boundary.get("fresh_planner_candidate_matching_required") is not True:
        raise RecursiveResearchRediagnosisError(
            "next discrepancy handoff weakened fresh planner matching"
        )
    if boundary.get("automatic_execution_authorized") is not False:
        raise RecursiveResearchRediagnosisError(
            "next discrepancy handoff cannot authorize execution"
        )

    result: dict[str, Any] = {
        "schema_version": RECURSIVE_CYCLE_SCHEMA_VERSION,
        "policy_version": RECURSIVE_REDIAGNOSIS_POLICY_VERSION,
        "cycle_id": checkpoint.get("cycle_id"),
        "cycle_index": checkpoint.get("cycle_index"),
        "completion_status": "next_planning_handoff_ready",
        "target": dict(target),
        "ancestry": {
            "authorization_checkpoint_sha256": checkpoint_sha,
            "progression_sha256": progression_sha,
            "previous_discrepancy_report_sha256": previous_report_sha,
            "current_discrepancy_report_sha256": current_report_sha,
            "evaluated_graph_canonical_sha256": _canonical_sha256(graph),
            "hypothesis_portfolio_sha256": _embedded_sha(
                portfolio,
                field="hypothesis_portfolio",
                sha_field="portfolio_sha256",
            ),
            "next_planning_handoff_sha256": _sha(
                next_handoff.get("handoff_sha256"),
                "next_planning_handoff.handoff_sha256",
            ),
        },
        "validated_rediagnosis": {
            "report_sha256": current_report_sha,
            "iteration_index": verified.get("iteration_index"),
            "diagnosis_types": list(verified.get("diagnosis_types", [])),
            "scientific_status_changed": False,
            "automatic_execution_authorized": False,
        },
        "next_planning_handoff": next_handoff,
        "autonomy_boundary": {
            "scientific_evidence_created": False,
            "epistemic_edge_created": False,
            "planner_candidate_created": False,
            "authorization_granted": False,
            "request_compiled": False,
            "execution_performed": False,
            "automatic_execution_authorized": False,
            "scientific_status_changed": False,
        },
    }
    result["completion_sha256"] = _canonical_sha256(result)
    return result


__all__ = [
    "RECURSIVE_REDIAGNOSIS_POLICY_VERSION",
    "RecursiveResearchRediagnosisError",
    "complete_recursive_cycle_with_rediagnosis",
]
