"""Bounded planning and authorization for the NIST AM-Bench structural simulation.

This module deliberately exposes one response-free simulation action.  It does not
synthesize measurements, satisfy the physical-acquisition requirement, fit a response
model, control equipment, or promote scientific evidence.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping

from .action_authorization import assess_action_authorization
from .action_registry import describe_action, load_action_registry
from .kernel import ResearchLoopError, load_research_state

ADAPTER_ID = "nist-ambench-structural"
DOMAIN = "nist_ambench_2018_02_stage1_structural_design"
ACTION_TYPE = "nist_structural_design_simulation"
ACTION_VERSION = "1.0"
RESEARCH_ID = "nist-ambench-2018-02-stage1-structural-research-v1"
PLANNING_SCHEMA_VERSION = "1.0"
PLANNING_POLICY_VERSION = "1.0"
DEFAULT_SIMULATION_CONFIG = Path(
    "configs/research/nist_ambench_stage1_structural_design_simulation.v1.json"
)


class NistStructuralResearchError(ResearchLoopError):
    """Raised when the bounded NIST structural planning contract drifts."""


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_repo_file(root: Path, value: str | Path, field: str) -> Path:
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve(strict=True)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise NistStructuralResearchError(f"{field} escapes repository_root") from exc
    if not resolved.is_file():
        raise NistStructuralResearchError(f"{field} must resolve to a file")
    return resolved


def _resolve_run(value: str | Path) -> Path:
    path = Path(value).expanduser().resolve(strict=True)
    if not path.is_dir():
        raise NistStructuralResearchError("research_run must resolve to a directory")
    return path


def _validate_run(state: Mapping[str, Any]) -> None:
    if state.get("research_id") != RESEARCH_ID:
        raise NistStructuralResearchError(
            "research run is not the frozen NIST AM-Bench structural research objective"
        )
    constraints = state.get("constraints")
    required = {
        "no_synthetic_trace_substitution",
        "no_response_value_synthesis",
        "no_predictive_or_causal_model_fit",
        "no_automatic_experiment_control",
        "no_scientific_evidence_promotion_from_simulation",
        "preserve_authoritative_process_and_metrology_lineage",
    }
    if not isinstance(constraints, list) or not required.issubset(set(constraints)):
        raise NistStructuralResearchError("research run lost one or more frozen safety constraints")
    budget = state.get("budget")
    if not isinstance(budget, Mapping):
        raise NistStructuralResearchError("research run budget is malformed")
    if budget.get("maximum_actions") != 1 or budget.get("maximum_cost_units") != 2:
        raise NistStructuralResearchError("research run budget drifted from one bounded action")


def build_nist_structural_planning_state(
    *,
    repository_root: str | Path,
    research_run: str | Path,
    action_registry_path: str | Path,
    simulation_config_path: str | Path = DEFAULT_SIMULATION_CONFIG,
) -> dict[str, Any]:
    """Build one fail-closed planning state for the response-free simulation."""
    root = Path(repository_root).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise NistStructuralResearchError("repository_root must resolve to a directory")
    run = _resolve_run(research_run)
    state = load_research_state(run)
    _validate_run(state)
    registry_path = _resolve_repo_file(root, action_registry_path, "action_registry_path")
    registry = load_action_registry(registry_path, repository_root=root)
    if registry.get("domain") != DOMAIN:
        raise NistStructuralResearchError("action registry domain does not match NIST structural domain")
    contract = describe_action(registry, ACTION_TYPE)
    if contract.get("version") != ACTION_VERSION:
        raise NistStructuralResearchError("NIST structural action version drifted")
    if contract.get("availability") != "available" or contract.get("category") != "simulation":
        raise NistStructuralResearchError("NIST structural simulation must remain available and simulation-only")
    if contract.get("cost_units") != 2:
        raise NistStructuralResearchError("NIST structural simulation cost contract drifted")
    config_path = _resolve_repo_file(root, simulation_config_path, "simulation_config_path")
    evidence_bindings = [
        {
            "role": "response_free_structural_simulation_config",
            "path": str(config_path),
            "sha256": _file_sha256(config_path),
        }
    ]
    actions = state.get("actions")
    if not isinstance(actions, list):
        raise NistStructuralResearchError("research run actions are malformed")

    common: dict[str, Any] = {
        "schema_version": PLANNING_SCHEMA_VERSION,
        "planning_policy_version": PLANNING_POLICY_VERSION,
        "adapter_id": ADAPTER_ID,
        "domain": DOMAIN,
        "research_id": RESEARCH_ID,
        "budget": dict(state["budget"]),
        "evidence_bindings": evidence_bindings,
        "selected_action": None,
        "evidence_gap": {
            "status": "physical_evidence_required_after_structural_simulation",
            "description": (
                "Nine new measured traces across the three missing power-speed cells remain "
                "required; the response-free simulation cannot satisfy this gap."
            ),
        },
    }
    if state.get("status") != "active" or actions:
        common["stop_state"] = {
            "status": "terminal_for_current_scope",
            "selection_status": "no_positive_value_action",
            "reason": (
                "The single bounded structural simulation has already been consumed or the run "
                "is stopped. Further progress requires new authoritative physical measurements."
            ),
            "reopen_conditions": [
                "new_authoritative_physical_traces_for_one_or_more_missing_power_speed_cells"
            ],
        }
        return common

    selected = {
        "action_type": ACTION_TYPE,
        "action_version": ACTION_VERSION,
        "availability": contract["availability"],
        "category": contract["category"],
        "cost_units": contract["cost_units"],
        "scientific_purpose": contract["scientific_purpose"],
        "execution_registry_id": registry["registry_id"],
        "execution_registry_sha256": registry["registry_sha256"],
        "execution_registry_path": registry["registry_path"],
        "simulation_config": str(config_path),
    }
    common["selected_action"] = selected
    common["evidence_gap"] = {
        "status": "structural_simulation_needed",
        "description": (
            "Verify whether the predeclared nine-trace augmentation repairs interaction-design "
            "rank before spending physical acquisition effort."
        ),
    }
    common["stop_state"] = {
        "status": "continue",
        "selection_status": "selected_positive_value_action",
        "reason": (
            "One response-free structural simulation can reduce design uncertainty without "
            "creating empirical evidence or changing the physical data requirement."
        ),
        "reopen_conditions": [],
    }
    return common


def assess_nist_structural_action_authorization(
    *,
    repository_root: str | Path,
    research_run: str | Path,
    action_registry_path: str | Path,
    simulation_config_path: str | Path = DEFAULT_SIMULATION_CONFIG,
) -> dict[str, Any]:
    """Authorize only the planner-selected response-free simulation."""
    state = build_nist_structural_planning_state(
        repository_root=repository_root,
        research_run=research_run,
        action_registry_path=action_registry_path,
        simulation_config_path=simulation_config_path,
    )
    return assess_action_authorization(state, repository_root=repository_root)


__all__ = [
    "ACTION_TYPE",
    "ACTION_VERSION",
    "ADAPTER_ID",
    "DEFAULT_SIMULATION_CONFIG",
    "DOMAIN",
    "NistStructuralResearchError",
    "assess_nist_structural_action_authorization",
    "build_nist_structural_planning_state",
]
