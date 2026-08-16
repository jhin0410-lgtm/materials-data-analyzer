"""Stable planning-state facade with audited NIST execution-state projection."""
from __future__ import annotations

from pathlib import Path

from .planning_state_legacy import *  # noqa: F401,F403
from .planning_state_legacy import build_research_planning_state as _legacy_build_state

_NIST_ADAPTER = "nist-ambench-process-characterization"


def build_research_planning_state(
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
            raise PlanningStateError(
                "NIST executable planning requires both research_run and action_registry_path"
            )
        from .nist_execution_planning import build_nist_execution_planning_state

        return build_nist_execution_planning_state(
            repository_root=repository_root,
            research_run=research_run,
            action_registry_path=action_registry_path,
        )
    return _legacy_build_state(
        adapter_id,
        repository_root=repository_root,
        research_run=research_run,
        action_registry_path=action_registry_path,
    )
