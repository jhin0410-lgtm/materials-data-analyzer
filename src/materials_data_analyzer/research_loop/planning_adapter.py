"""Stable planning-adapter facade with audited NIST execution planning."""
from __future__ import annotations

from pathlib import Path

from .planning_adapter_legacy import *  # noqa: F401,F403
from .planning_adapter_legacy import (
    available_planning_adapters as _legacy_available_planning_adapters,
    plan_research_next_action as _legacy_plan_research_next_action,
)

_NIST_ADAPTER = "nist-ambench-process-characterization"


def available_planning_adapters() -> tuple[str, ...]:
    return _legacy_available_planning_adapters()


def plan_research_next_action(
    adapter_id: str,
    *,
    repository_root: str | Path,
    research_run: str | Path | None = None,
    action_registry_path: str | Path | None = None,
) -> dict:
    if adapter_id == _NIST_ADAPTER and (
        research_run is not None or action_registry_path is not None
    ):
        if research_run is None or action_registry_path is None:
            raise PlanningAdapterError(
                "NIST executable planning requires both research_run and action_registry_path"
            )
        from .nist_execution_planning import plan_nist_execution_next_action

        return plan_nist_execution_next_action(
            repository_root=repository_root,
            research_run=research_run,
            action_registry_path=action_registry_path,
        )
    return _legacy_plan_research_next_action(
        adapter_id,
        repository_root=repository_root,
        research_run=research_run,
        action_registry_path=action_registry_path,
    )
