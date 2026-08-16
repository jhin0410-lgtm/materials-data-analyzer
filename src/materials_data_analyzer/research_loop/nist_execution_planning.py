"""Execution-enabled NIST AM-Bench planning without changing scientific readiness."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping

from .action_registry import describe_action, load_action_registry
from .kernel import LEDGER_FILENAME, ResearchLoopError, load_research_state
from .planning_adapter_legacy import plan_research_next_action as _legacy_plan
from .planning_state_legacy import build_research_planning_state as _legacy_state

ADAPTER_ID = "nist-ambench-process-characterization"
ACTION_TYPE = "nist_structural_design_simulation"
ACTION_VERSION = "1.0"
ACTION_CATEGORY = "simulation"
ACTION_COST_UNITS = 1


class NistExecutionPlanningError(ResearchLoopError):
    """Raised when executable NIST planning cannot preserve the frozen boundary."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_file(value: str | Path, *, root: Path, field: str) -> Path:
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    path = candidate.resolve(strict=True)
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise NistExecutionPlanningError(f"{field} escapes repository root") from exc
    if not path.is_file():
        raise NistExecutionPlanningError(f"{field} must resolve to a file")
    return path


def _verify_registry(path: Path, root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    registry = load_action_registry(path, repository_root=root)
    if registry.get("domain") != "nist_ambench_stage1_structural_design":
        raise NistExecutionPlanningError("NIST execution registry domain drifted")
    contract = describe_action(registry, ACTION_TYPE)
    expected = {
        "version": ACTION_VERSION,
        "availability": "available",
        "category": ACTION_CATEGORY,
        "cost_units": ACTION_COST_UNITS,
    }
    for key, value in expected.items():
        if contract.get(key) != value:
            raise NistExecutionPlanningError(
                f"NIST structural simulation contract drifted on {key}"
            )
    prohibited = set(contract.get("prohibited_effects", []))
    required = {
        "synthetic_response_generation",
        "response_value_substitution",
        "model_fitting",
        "prediction",
        "causal_inference",
        "optimization",
        "engineering_decision",
        "physical_experiment_execution",
        "scientific_evidence_promotion",
        "physical_evidence_requirement_satisfaction",
    }
    if not required.issubset(prohibited):
        raise NistExecutionPlanningError(
            "NIST execution registry lost required prohibited effects"
        )
    return registry, contract


def _selection(registry: Mapping[str, Any], contract: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "action_type": ACTION_TYPE,
        "action_version": ACTION_VERSION,
        "availability": "available",
        "cost_units": ACTION_COST_UNITS,
        "score": 100,
        "trigger": "response_free_design_identifiability_not_yet_audited_in_research_ledger",
        "rationale": (
            "Run the checksum-bound response-free Stage 1 design simulator once to verify "
            "structural estimability before acquiring the nine required real traces. "
            "The action cannot satisfy the physical evidence requirement."
        ),
        "execution_registry_id": registry["registry_id"],
        "execution_registry_sha256": registry["registry_sha256"],
        "execution_registry_path": registry["registry_path"],
    }


def _run_state(run: Path) -> dict[str, Any]:
    state = load_research_state(run)
    if state.get("status") != "active":
        raise NistExecutionPlanningError("NIST executable research run must be active")
    if not isinstance(state.get("actions"), list) or not isinstance(state.get("budget"), Mapping):
        raise NistExecutionPlanningError("NIST research run state is malformed")
    return state


def plan_nist_execution_next_action(
    *, repository_root: str | Path, research_run: str | Path, action_registry_path: str | Path
) -> dict[str, Any]:
    root = Path(repository_root).expanduser().resolve(strict=True)
    run = Path(research_run).expanduser().resolve(strict=True)
    registry_path = _resolve_file(action_registry_path, root=root, field="action_registry_path")
    registry, contract = _verify_registry(registry_path, root)
    state = _run_state(run)

    baseline = _legacy_plan(ADAPTER_ID, repository_root=root)
    bindings = list(baseline.get("evidence_bindings", []))
    ledger = (run / LEDGER_FILENAME).resolve(strict=True)
    bindings.extend(
        [
            {
                "role": "nist_execution_registry",
                "path": registry_path.relative_to(root).as_posix(),
                "sha256": _sha256_file(registry_path),
            },
            {
                "role": "research_ledger",
                "path": str(ledger),
                "sha256": state["ledger_sha256"],
            },
        ]
    )
    prior = [
        item
        for item in state["actions"]
        if isinstance(item, Mapping) and item.get("action_type") == ACTION_TYPE
    ]
    if prior:
        if len(prior) != 1 or prior[0].get("status") != "completed":
            raise NistExecutionPlanningError(
                "NIST structural simulation must be recorded at most once and complete"
            )
        return {
            **baseline,
            "selection_status": "no_positive_value_action",
            "selected_action": None,
            "candidates": [],
            "reason": (
                "The response-free structural design simulation is already verified in the "
                "research ledger. The remaining blocker is nine real Stage 1 traces; repeating "
                "the simulation has no new scientific value."
            ),
            "evidence_bindings": bindings,
        }

    selected = _selection(registry, contract)
    return {
        **baseline,
        "selection_status": "ready_to_execute",
        "selected_action": selected,
        "candidates": [selected],
        "reason": selected["rationale"],
        "evidence_bindings": bindings,
    }


def build_nist_execution_planning_state(
    *, repository_root: str | Path, research_run: str | Path, action_registry_path: str | Path
) -> dict[str, Any]:
    root = Path(repository_root).expanduser().resolve(strict=True)
    run = Path(research_run).expanduser().resolve(strict=True)
    decision = plan_nist_execution_next_action(
        repository_root=root,
        research_run=run,
        action_registry_path=action_registry_path,
    )
    baseline = _legacy_state(ADAPTER_ID, repository_root=root)
    research = _run_state(run)
    baseline["action_frontier"] = [
        {
            "action_type": item["action_type"],
            "action_version": item["action_version"],
            "availability": item["availability"],
            "cost_units": item["cost_units"],
            "priority_score": item["score"],
            "trigger": item["trigger"],
            "rationale": item["rationale"],
            "execution_registry_id": item["execution_registry_id"],
            "execution_registry_sha256": item["execution_registry_sha256"],
            "execution_registry_path": item["execution_registry_path"],
            "expected_information_gain": {
                "status": "not_quantified",
                "value": None,
                "unit": None,
                "boundary": "Structural design value is not a probabilistic information-gain estimate.",
            },
        }
        for item in decision["candidates"]
    ]
    baseline["selected_action"] = baseline["action_frontier"][0] if baseline["action_frontier"] else None
    baseline["budget"] = dict(research["budget"])
    baseline["evidence_bindings"] = decision["evidence_bindings"]
    baseline["constraints"] = list(dict.fromkeys(
        list(baseline.get("constraints", [])) + list(research.get("constraints", []))
    ))
    baseline["stop_rules"] = list(dict.fromkeys(
        list(baseline.get("stop_rules", [])) + list(research.get("stop_rules", []))
    ))
    baseline["research_question"] = research["question"]
    if decision["selection_status"] == "ready_to_execute":
        baseline["stop_state"] = {
            "status": "continue",
            "selection_status": "ready_to_execute",
            "reason": decision["reason"],
            "reopen_conditions": list(baseline["stop_state"].get("reopen_conditions", [])),
        }
        baseline["current_blocker"] = {
            "kind": "structural_design_audit_before_physical_acquisition",
            "code": "response_free_design_simulation_pending",
            "summary": decision["reason"],
        }
        baseline["evidence_gap"] = {
            "status": "action_expected_to_reduce_design_uncertainty",
            "requirements": list(baseline["evidence_gap"].get("requirements", [])),
        }
    else:
        baseline["stop_state"] = {
            "status": "terminal_for_current_scope",
            "selection_status": "no_positive_value_action",
            "reason": decision["reason"],
            "reopen_conditions": list(baseline["stop_state"].get("reopen_conditions", [])),
        }
    return baseline


__all__ = [
    "ACTION_TYPE",
    "ACTION_VERSION",
    "ADAPTER_ID",
    "NistExecutionPlanningError",
    "build_nist_execution_planning_state",
    "plan_nist_execution_next_action",
]
