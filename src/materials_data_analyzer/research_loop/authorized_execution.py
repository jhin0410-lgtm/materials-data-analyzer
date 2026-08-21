"""Single public typed-execution router with legacy-compatible bounded adapters.

The NASA implementation remains byte-for-byte preserved in the internal legacy module. This
facade preserves historical monkeypatch seams while routing NIST structural and audited
reference-heat actions through independent authorization and exact SHA handoff boundaries.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from . import authorized_execution_nasa_legacy as _nasa_legacy
from .authorized_execution_nasa_legacy import *  # noqa: F401,F403
from .authorized_execution_nasa_legacy import (
    EXECUTION_POLICY_VERSION,
    _action_count,
    assess_current_action_authorization,
)
from .kernel import ResearchLoopError

_NASA_ADAPTER = "nasa-battery"
_NIST_ADAPTER = "nist-ambench-process-characterization"
_HEAT_ADAPTER = "reference-heat-conduction"
_NIST_ACTION_TYPE = "nist_structural_design_simulation"
_HEAT_ACTION_TYPE = "reference_heat_conduction_simulation"
_LEGACY_ENTRYPOINTS = {
    "execute_authorized_action",
    "execute_authorized_action_with_failure_classification",
}


def __getattr__(name: str) -> Any:
    """Expose the complete historical NASA module namespace lazily."""
    try:
        return getattr(_nasa_legacy, name)
    except AttributeError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc


def _call_nasa_with_compat_namespace(
    function: Callable[..., dict[str, Any]],
    /,
    *args: Any,
    **kwargs: Any,
) -> dict[str, Any]:
    """Temporarily project facade monkeypatches into the preserved legacy module."""
    restored: dict[str, Any] = {}
    facade_globals = globals()
    for name, legacy_value in vars(_nasa_legacy).items():
        if name.startswith("__") or name in _LEGACY_ENTRYPOINTS:
            continue
        if name not in facade_globals:
            continue
        facade_value = facade_globals[name]
        if facade_value is legacy_value:
            continue
        restored[name] = legacy_value
        setattr(_nasa_legacy, name, facade_value)
    try:
        return function(*args, **kwargs)
    finally:
        for name, value in restored.items():
            setattr(_nasa_legacy, name, value)


def execute_authorized_action(
    adapter_id: str,
    *,
    repository_root: str | Path,
    research_run: str | Path,
    action_registry_path: str | Path,
    request_path: str | Path,
    expected_action_type: str | None = None,
    expected_request_sha256: str | None = None,
    expected_research_ledger_sha256: str | None = None,
) -> dict[str, Any]:
    """Execute one bounded typed action through its registered adapter."""
    if adapter_id == _NASA_ADAPTER:
        if expected_action_type in {_NIST_ACTION_TYPE, _HEAT_ACTION_TYPE}:
            raise AuthorizedExecutionError(
                "non-NASA simulation action cannot be routed through the NASA adapter"
            )
        if expected_request_sha256 is not None or expected_research_ledger_sha256 is not None:
            raise AuthorizedExecutionError(
                "machine-verifier SHA handoff pins are not accepted by the legacy NASA route"
            )
        return _call_nasa_with_compat_namespace(
            _nasa_legacy.execute_authorized_action,
            adapter_id,
            repository_root=repository_root,
            research_run=research_run,
            action_registry_path=action_registry_path,
            request_path=request_path,
            expected_action_type=expected_action_type,
        )
    if adapter_id == _NIST_ADAPTER:
        if expected_request_sha256 is None or expected_research_ledger_sha256 is None:
            raise AuthorizedExecutionError(
                "NIST typed execution requires exact request and research-ledger SHA pins"
            )
        from .nist_authorized_execution import execute_nist_authorized_action

        return execute_nist_authorized_action(
            repository_root=repository_root,
            research_run=research_run,
            action_registry_path=action_registry_path,
            request_path=request_path,
            expected_action_type=expected_action_type,
            expected_request_sha256=expected_request_sha256,
            expected_research_ledger_sha256=expected_research_ledger_sha256,
        )
    if adapter_id == _HEAT_ADAPTER:
        if expected_action_type != _HEAT_ACTION_TYPE:
            raise AuthorizedExecutionError(
                "reference heat adapter requires the exact heat action type pin"
            )
        if expected_request_sha256 is None or expected_research_ledger_sha256 is None:
            raise AuthorizedExecutionError(
                "reference heat typed execution requires exact request and research-ledger SHA pins"
            )
        from .heat_authorized_execution import execute_heat_authorized_action

        return execute_heat_authorized_action(
            repository_root=repository_root,
            research_run=research_run,
            action_registry_path=action_registry_path,
            request_path=request_path,
            expected_action_type=expected_action_type,
            expected_request_sha256=expected_request_sha256,
            expected_research_ledger_sha256=expected_research_ledger_sha256,
        )
    raise AuthorizedExecutionError(
        "bounded typed execution adapter is not registered in the public execution router"
    )


def execute_authorized_action_with_failure_classification(
    adapter_id: str,
    *,
    repository_root: str | Path,
    research_run: str | Path,
    action_registry_path: str | Path,
    request_path: str | Path,
    expected_action_type: str | None = None,
    expected_request_sha256: str | None = None,
    expected_research_ledger_sha256: str | None = None,
) -> dict[str, Any]:
    """Execute once and distinguish post-ledger failure from preflight failure."""
    if adapter_id == _NASA_ADAPTER:
        if expected_action_type in {_NIST_ACTION_TYPE, _HEAT_ACTION_TYPE}:
            raise AuthorizedExecutionError(
                "non-NASA simulation action cannot be routed through the NASA adapter"
            )
        if expected_request_sha256 is not None or expected_research_ledger_sha256 is not None:
            raise AuthorizedExecutionError(
                "machine-verifier SHA handoff pins are not accepted by the legacy NASA route"
            )

    run = Path(research_run).expanduser().resolve(strict=True)
    before_count = _action_count(run, phase="pre-execution")
    try:
        return execute_authorized_action(
            adapter_id,
            repository_root=repository_root,
            research_run=run,
            action_registry_path=action_registry_path,
            request_path=request_path,
            expected_action_type=expected_action_type,
            expected_request_sha256=expected_request_sha256,
            expected_research_ledger_sha256=expected_research_ledger_sha256,
        )
    except ResearchLoopError as exc:
        after_count = _action_count(run, phase="post-failure")
        if after_count > before_count:
            raise AuthorizedExecutionStartedError(str(exc)) from exc
        raise


__all__ = [
    "EXECUTION_POLICY_VERSION",
    "EXECUTION_SCHEMA_VERSION",
    "AuthorizedExecutionError",
    "AuthorizedExecutionStartedError",
    "execute_authorized_action",
    "execute_authorized_action_with_failure_classification",
]
