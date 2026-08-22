"""Stable planning-state facade with audited executable planning projections.

The preserved legacy implementation remains the compatibility surface for existing domains;
this facade adds bounded executable projections while retaining historical module namespace
and monkeypatch semantics.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from . import planning_state_legacy as _legacy
from .planning_state_legacy import *  # noqa: F401,F403

_NIST_ADAPTER = "nist-ambench-process-characterization"
_HEAT_ADAPTER = "reference-heat-conduction"
_IN625_ADAPTER = "in625-external-evidence"
_LEGACY_ENTRYPOINTS = {"build_research_planning_state"}


def __getattr__(name: str) -> Any:
    try:
        return getattr(_legacy, name)
    except AttributeError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc


def _call_legacy_with_compat_namespace(
    function: Callable[..., dict[str, Any]],
    /,
    *args: Any,
    **kwargs: Any,
) -> dict[str, Any]:
    """Preserve pre-facade module-global monkeypatch behavior for legacy projection."""
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
    if adapter_id == _HEAT_ADAPTER:
        if research_run is None or action_registry_path is None:
            raise PlanningStateError(
                "reference heat executable planning requires both research_run and action_registry_path"
            )
        from .heat_execution_planning import build_heat_execution_planning_state

        return build_heat_execution_planning_state(
            repository_root=repository_root,
            research_run=research_run,
            action_registry_path=action_registry_path,
        )
    if adapter_id == _IN625_ADAPTER:
        if research_run is None or action_registry_path is None:
            raise PlanningStateError(
                "IN625 external-evidence executable planning requires both research_run and action_registry_path"
            )
        from .in625_execution_planning import build_in625_execution_planning_state

        return build_in625_execution_planning_state(
            repository_root=repository_root,
            research_run=research_run,
            action_registry_path=action_registry_path,
        )
    return _call_legacy_with_compat_namespace(
        _legacy.build_research_planning_state,
        adapter_id,
        repository_root=repository_root,
        research_run=research_run,
        action_registry_path=action_registry_path,
    )
