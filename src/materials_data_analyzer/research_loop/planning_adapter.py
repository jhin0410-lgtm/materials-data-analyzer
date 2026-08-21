"""Stable planning-adapter facade with audited executable planning projections.

The complete historical planning-adapter namespace remains available through the preserved
legacy module, including intentional monkeypatch/test seams. The historical adapter
enumeration remains stable; the reference-heat adapter is an explicit typed execution
projection rather than a silently expanded legacy discovery surface.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from . import planning_adapter_legacy as _legacy
from .planning_adapter_legacy import *  # noqa: F401,F403

_NIST_ADAPTER = "nist-ambench-process-characterization"
_HEAT_ADAPTER = "reference-heat-conduction"
_LEGACY_ENTRYPOINTS = {"available_planning_adapters", "plan_research_next_action"}


def __getattr__(name: str) -> Any:
    try:
        return getattr(_legacy, name)
    except AttributeError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc


def _call_legacy_with_compat_namespace(
    function: Callable[..., dict[str, Any] | tuple[str, ...]],
    /,
    *args: Any,
    **kwargs: Any,
) -> Any:
    """Preserve pre-facade module-global monkeypatch behavior for legacy planning."""
    restored: dict[str, Any] = {}
    facade_globals = globals()
    for name, legacy_value in vars(_legacy).items():
        if name.startswith("__") or name in _LEGACY_ENTRYPOINTS:
            continue
        if name not in facade_globals:
            continue
        facade_value = facade_globals[name]
        if facade_value is legacy_value:
            continue
        restored[name] = legacy_value
        setattr(_legacy, name, facade_value)
    try:
        return function(*args, **kwargs)
    finally:
        for name, value in restored.items():
            setattr(_legacy, name, value)


def available_planning_adapters() -> tuple[str, ...]:
    """Return the stable historical discovery surface.

    New typed execution adapters must not silently mutate this compatibility contract.
    They remain addressable explicitly through ``plan_research_next_action``.
    """
    return tuple(_call_legacy_with_compat_namespace(_legacy.available_planning_adapters))


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
    if adapter_id == _HEAT_ADAPTER:
        if research_run is None or action_registry_path is None:
            raise PlanningAdapterError(
                "reference heat executable planning requires both research_run and action_registry_path"
            )
        from .heat_execution_planning import build_heat_execution_planning_state

        state = build_heat_execution_planning_state(
            repository_root=repository_root,
            research_run=research_run,
            action_registry_path=action_registry_path,
        )
        return {
            "adapter_id": state["adapter_id"],
            "domain": state["domain"],
            "selection_status": state["stop_state"]["selection_status"],
            "selected_action": state["selected_action"],
            "candidates": list(state["action_frontier"]),
            "reason": state["stop_state"]["reason"],
            "evidence_bindings": list(state["evidence_bindings"]),
        }
    return _call_legacy_with_compat_namespace(
        _legacy.plan_research_next_action,
        adapter_id,
        repository_root=repository_root,
        research_run=research_run,
        action_registry_path=action_registry_path,
    )
