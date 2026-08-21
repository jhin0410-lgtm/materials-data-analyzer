"""Planning-state projection for the audited reference heat-conduction action."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping

from .action_registry import describe_action, load_action_registry
from .heat_conduction_action import ACTION_TYPE, ACTION_VERSION, COST_UNITS
from .heat_execution_verifier import ADAPTER_ID, REGISTRY_DOMAIN
from .kernel import LEDGER_FILENAME, ResearchLoopError, load_research_state


class HeatExecutionPlanningError(ResearchLoopError):
    """Raised when the reference-physics planning boundary drifts."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_file(value: str | Path, *, root: Path, field: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = root / path
    path = path.resolve(strict=True)
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise HeatExecutionPlanningError(f"{field} escapes repository root") from exc
    if not path.is_file():
        raise HeatExecutionPlanningError(f"{field} must resolve to a file")
    return path


def _verified_registry(path: Path, root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    registry = load_action_registry(path, repository_root=root)
    if registry.get("domain") != REGISTRY_DOMAIN:
        raise HeatExecutionPlanningError("reference heat registry domain drifted")
    contract = describe_action(registry, ACTION_TYPE)
    if (
        contract.get("version") != ACTION_VERSION
        or contract.get("availability") != "available"
        or contract.get("category") != "simulation"
        or contract.get("cost_units") != COST_UNITS
    ):
        raise HeatExecutionPlanningError("reference heat action contract drifted")
    required_prohibited = {
        "material_identity_inference",
        "material_property_imputation",
        "process_specific_validity_claim",
        "empirical_validation_claim",
        "physical_experiment_execution",
        "scientific_evidence_promotion",
        "engineering_decision",
    }
    if not required_prohibited.issubset(set(contract.get("prohibited_effects", []))):
        raise HeatExecutionPlanningError("reference heat registry lost scientific boundary prohibitions")
    return registry, contract


def build_heat_execution_planning_state(
    *,
    repository_root: str | Path,
    research_run: str | Path,
    action_registry_path: str | Path,
) -> dict[str, Any]:
    root = Path(repository_root).expanduser().resolve(strict=True)
    run = Path(research_run).expanduser().resolve(strict=True)
    registry_path = _resolve_file(action_registry_path, root=root, field="action_registry_path")
    registry, contract = _verified_registry(registry_path, root)
    state = load_research_state(run)
    if state.get("status") != "active":
        raise HeatExecutionPlanningError("reference heat research run must be active")
    actions = state.get("actions")
    budget = state.get("budget")
    if not isinstance(actions, list) or not isinstance(budget, Mapping):
        raise HeatExecutionPlanningError("reference heat research state is malformed")
    ledger = (run / LEDGER_FILENAME).resolve(strict=True)
    bindings = [
        {
            "role": "reference_heat_execution_registry",
            "path": registry_path.relative_to(root).as_posix(),
            "sha256": _sha256_file(registry_path),
        },
        {
            "role": "research_ledger",
            "path": str(ledger),
            "sha256": state["ledger_sha256"],
        },
    ]
    prior = [item for item in actions if isinstance(item, Mapping) and item.get("action_type") == ACTION_TYPE]
    if prior:
        reason = (
            "The audited reference heat solver has already been executed in this run. "
            "Repeating the same reference action is not autonomously justified."
        )
        selected = None
        frontier: list[dict[str, Any]] = []
        stop_state = {
            "status": "terminal_for_current_scope",
            "selection_status": "no_positive_value_action",
            "reason": reason,
            "reopen_conditions": [
                "A distinct hypothesis requires a new explicitly parameterized and separately authorized solver request."
            ],
        }
    else:
        selected = {
            "action_type": ACTION_TYPE,
            "action_version": ACTION_VERSION,
            "availability": "available",
            "cost_units": COST_UNITS,
            "priority_score": 100,
            "trigger": "audited_reference_physics_solver_requested",
            "rationale": (
                "Run one checksum-bound 1D transient heat-conduction reference calculation to "
                "establish numerical-solver and validation evidence only; empirical validity remains unclaimed."
            ),
            "execution_registry_id": registry["registry_id"],
            "execution_registry_sha256": registry["registry_sha256"],
            "execution_registry_path": registry["registry_path"],
            "expected_information_gain": {
                "status": "not_quantified",
                "value": None,
                "unit": None,
                "boundary": "Numerical reference validation is not empirical information gain.",
            },
        }
        frontier = [selected]
        reason = selected["rationale"]
        stop_state = {
            "status": "continue",
            "selection_status": "ready_to_execute",
            "reason": reason,
            "reopen_conditions": [],
        }
    return {
        "schema_version": "1.0",
        "adapter_id": ADAPTER_ID,
        "domain": REGISTRY_DOMAIN,
        "research_question": state["question"],
        "metrics": state["metrics"],
        "constraints": list(state["constraints"]),
        "stop_rules": list(state["stop_rules"]),
        "budget": dict(budget),
        "evidence_bindings": bindings,
        "action_frontier": frontier,
        "selected_action": selected,
        "current_blocker": {
            "kind": "audited_reference_physics_solver",
            "code": "physics_solver_reference_missing" if selected else "reference_solver_already_executed",
            "summary": reason,
        },
        "evidence_gap": {
            "status": "action_expected_to_reduce_numerical_model_uncertainty" if selected else "reference_action_complete",
            "requirements": [
                "No empirical material/process claim may be promoted from this reference calculation alone."
            ],
        },
        "stop_state": stop_state,
        "scientific_status_upgrade_authorized": False,
    }


__all__ = ["HeatExecutionPlanningError", "build_heat_execution_planning_state"]
