"""Deterministic baseline policy for the next NASA research action."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .action_registry import describe_action, load_action_registry
from .kernel import ResearchLoopError, load_research_state
from .nasa_audit_executor import (
    ACTION_REPORT_FILENAME,
    ACTION_TYPE as AUDIT_ACTION_TYPE,
    verify_nasa_audit_action_report,
)

POLICY_VERSION = "1.1"
_ACTION_EXECUTION_REGISTRY_FILENAMES = {
    "target_reference_sensitivity": "nasa_target_reference_action_registry.v1.json",
}


class NasaActionPolicyError(ResearchLoopError):
    """Raised when verified research state cannot support policy evaluation."""


def _load_report(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise NasaActionPolicyError(f"invalid action report JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise NasaActionPolicyError("action report must contain a JSON object")
    return value


def _report_path(action: dict[str, Any]) -> Path:
    matches = [
        Path(item["path"])
        for item in action.get("artifacts", [])
        if Path(item["path"]).name == ACTION_REPORT_FILENAME
    ]
    if len(matches) != 1:
        raise NasaActionPolicyError(
            "audit ledger action must bind exactly one action_result.json"
        )
    return matches[0]


def _load_execution_registry_overrides(
    planning_registry: dict[str, Any],
    *,
    repository_root: str | Path,
) -> dict[str, dict[str, Any]]:
    """Load stricter executable contracts without changing scientific ranking."""
    planning_path = Path(planning_registry["registry_path"])
    overrides: dict[str, dict[str, Any]] = {}
    for action_type, filename in _ACTION_EXECUTION_REGISTRY_FILENAMES.items():
        planning_contract = describe_action(planning_registry, action_type)
        execution_path = planning_path.with_name(filename)
        if not execution_path.is_file():
            continue
        execution_registry = load_action_registry(
            execution_path,
            repository_root=repository_root,
        )
        execution_contract = describe_action(execution_registry, action_type)
        if planning_contract["availability"] != "planned":
            raise NasaActionPolicyError(
                f"execution registry override is only valid for planned action: {action_type}"
            )
        if execution_contract["availability"] != "available":
            raise NasaActionPolicyError(
                f"execution registry override is not available: {action_type}"
            )
        for field in ("category", "cost_units", "allowed_outcomes"):
            if execution_contract[field] != planning_contract[field]:
                raise NasaActionPolicyError(
                    f"execution registry changes planning field {field}: {action_type}"
                )
        overrides[action_type] = execution_registry
    return overrides


def _proposal(
    registry: dict[str, Any],
    action_type: str,
    score: int,
    trigger: str,
    rationale: str,
    *,
    execution_registries: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    selected_registry = (execution_registries or {}).get(action_type, registry)
    contract = describe_action(selected_registry, action_type)
    return {
        "action_type": action_type,
        "action_version": contract["version"],
        "availability": contract["availability"],
        "cost_units": contract["cost_units"],
        "score": score,
        "trigger": trigger,
        "rationale": rationale,
        "execution_registry_id": contract["registry_id"],
        "execution_registry_sha256": contract["registry_sha256"],
        "execution_registry_path": selected_registry["registry_path"],
    }


def _post_audit_candidates(
    registry: dict[str, Any],
    report: dict[str, Any],
    *,
    execution_registries: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    outcomes = set(report.get("outcomes", []))
    evidence_level = report.get("evidence_level_after")
    candidates: dict[str, dict[str, Any]] = {}

    def add(
        action_type: str,
        score: int,
        trigger: str,
        rationale: str,
    ) -> None:
        candidate = _proposal(
            registry,
            action_type,
            score,
            trigger,
            rationale,
            execution_registries=execution_registries,
        )
        previous = candidates.get(action_type)
        if previous is None or score > int(previous["score"]):
            candidates[action_type] = candidate

    if "partial_dimensions_inconclusive" in outcomes:
        add(
            "external_data_requirement_generation",
            130,
            "partial_dimensions_inconclusive",
            "Define the minimum missing evidence before another model experiment.",
        )
    if "target_or_reference_flags_detected" in outcomes:
        add(
            "target_reference_sensitivity",
            120,
            "target_or_reference_flags_detected",
            "Resolve defensible target-reference sensitivity before model expansion.",
        )
    if "pooled_error_instability_detected" in outcomes:
        add(
            "protocol_stratification",
            110,
            "pooled_error_instability_detected",
            "Test whether observed protocol heterogeneity explains concentrated error.",
        )
        add(
            "source_cohort_leave_one_out",
            100,
            "pooled_error_instability_detected",
            "Measure source-cohort transport separately from pooled performance.",
        )
        add(
            "selective_prediction_abstention",
            80,
            "pooled_error_instability_detected",
            "Test whether abstention reduces retained risk without hiding failures.",
        )
    if "no_audit_flag_with_complete_dimensions" in outcomes:
        add(
            "feature_family_ablation",
            85,
            "no_audit_flag_with_complete_dimensions",
            "Test grouped incremental value by predeclared feature family.",
        )
    if evidence_level == "Unsupported":
        add(
            "feature_family_ablation",
            75,
            "predictive_evidence_unsupported",
            "Require feature-level incremental value before deeper models.",
        )
        add(
            "hierarchical_state_space_baseline",
            60,
            "predictive_evidence_unsupported",
            "Retain a constrained state-space baseline as a lower-priority candidate.",
        )
    return sorted(
        candidates.values(),
        key=lambda item: (-int(item["score"]), str(item["action_type"])),
    )


def plan_nasa_next_action(
    research_run: str | Path,
    registry_path: str | Path,
    repository_root: str | Path,
) -> dict[str, Any]:
    """Return a deterministic recommendation without executing an action."""
    state = load_research_state(research_run)
    registry = load_action_registry(registry_path, repository_root=repository_root)
    execution_registries = _load_execution_registry_overrides(
        registry,
        repository_root=repository_root,
    )
    base = {
        "policy_version": POLICY_VERSION,
        "research_id": state["research_id"],
        "research_status": state["status"],
        "registry_id": registry["registry_id"],
        "registry_sha256": registry["registry_sha256"],
        "actions_remaining": state["budget"]["actions_remaining"],
        "cost_units_remaining": state["budget"]["cost_units_remaining"],
    }
    if state["status"] != "active":
        return {
            **base,
            "selection_status": "research_stopped",
            "selected_action": None,
            "candidates": [],
            "reason": "The research run is terminal.",
        }

    audits = [
        item for item in state["actions"] if item["action_type"] == AUDIT_ACTION_TYPE
    ]
    if not audits:
        selected = _proposal(
            registry,
            AUDIT_ACTION_TYPE,
            100,
            "audit_not_yet_executed",
            "Audit target/reference integrity and concentrated battery-level error.",
            execution_registries=execution_registries,
        )
        enough_budget = (
            state["budget"]["actions_remaining"] > 0
            and selected["cost_units"] <= state["budget"]["cost_units_remaining"]
        )
        return {
            **base,
            "selection_status": (
                "ready_to_execute" if enough_budget else "blocked_by_budget"
            ),
            "selected_action": selected,
            "candidates": [selected],
            "reason": selected["rationale"],
        }

    latest = audits[-1]
    report_path = _report_path(latest)
    verify_nasa_audit_action_report(report_path)
    report = _load_report(report_path)
    if latest["status"] == "failed":
        return {
            **base,
            "selection_status": "manual_review_required",
            "selected_action": None,
            "candidates": [],
            "reason": "The latest audit failed; automatic repetition is disabled.",
            "latest_audit_report": str(report_path),
            "latest_audit_error": report.get("error"),
        }
    if latest["status"] != "completed":
        raise NasaActionPolicyError(
            f"unexpected audit ledger status: {latest['status']!r}"
        )

    tried = {item["action_type"] for item in state["actions"]}
    candidates = [
        item
        for item in _post_audit_candidates(
            registry,
            report,
            execution_registries=execution_registries,
        )
        if item["action_type"] not in tried
    ]
    if not candidates:
        return {
            **base,
            "selection_status": "no_positive_value_action",
            "selected_action": None,
            "candidates": [],
            "reason": "No untried registered action is justified by the audit outcomes.",
            "latest_audit_report": str(report_path),
        }

    selected = candidates[0]
    if (
        state["budget"]["actions_remaining"] <= 0
        or selected["cost_units"] > state["budget"]["cost_units_remaining"]
    ):
        status = "blocked_by_budget"
    elif selected["availability"] != "available":
        status = "blocked_unimplemented_action"
    else:
        status = "ready_to_execute"
    return {
        **base,
        "selection_status": status,
        "selected_action": selected,
        "candidates": candidates,
        "reason": selected["rationale"],
        "latest_audit_report": str(report_path),
        "latest_audit_outcomes": list(report.get("outcomes", [])),
        "latest_evidence_level": report.get("evidence_level_after"),
    }
