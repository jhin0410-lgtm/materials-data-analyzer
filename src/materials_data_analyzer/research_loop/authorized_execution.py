"""Single public typed-execution router with a legacy-compatible NASA facade.

The NASA implementation remains byte-for-byte preserved in the internal legacy module. This
facade also preserves the historical module namespace and monkeypatch seams used by tests and
downstream integrations while adding the audited NIST response-free route.
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
_NIST_ACTION_TYPE = "nist_structural_design_simulation"
_LEGACY_ENTRYPOINTS = {
    "execute_authorized_action",
    "execute_authorized_action_with_failure_classification",
}


def __getattr__(name: str) -> Any:
    """Expose the complete historical NASA module namespace lazily.

    The legacy module defines a narrow ``__all__`` but existing tests/integrations also use
    intentional internal seams such as ``_DISPATCH`` and ``_dispatch_cost_units``. Delegating
    attribute reads retains that compatibility without copying the legacy implementation.
    """
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
    """Temporarily project facade monkeypatches into the preserved legacy module.

    Before this facade existed, monkeypatching a symbol on ``authorized_execution`` changed
    the global resolved by the executor function itself. Splitting the implementation into a
    legacy module would otherwise silently break that behavior. Only names that already exist
    in the legacy module are projected, and every projected value is restored after the call.
    """
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
    """Execute one bounded typed action.

    NIST execution requires exact request and pre-execution-ledger SHA handoff pins.
    Mission/policy provenance for those pins is established by the higher-level
    ``nist_authenticated_execution`` boundary, which runs the independent verifier in
    the same call before entering this typed executor.
    """
    if adapter_id == _NASA_ADAPTER:
        if expected_action_type == _NIST_ACTION_TYPE:
            raise AuthorizedExecutionError(
                "the NIST structural action cannot be routed through the NASA adapter"
            )
        if (
            expected_request_sha256 is not None
            or expected_research_ledger_sha256 is not None
        ):
            raise AuthorizedExecutionError(
                "machine-verifier SHA handoff pins are implemented only for the NIST route"
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
        if (
            expected_request_sha256 is None
            or expected_research_ledger_sha256 is None
        ):
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
    raise AuthorizedExecutionError(
        "bounded typed execution is currently implemented only for nasa-battery"
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
    """Execute once and preserve pre/post-ledger failure classification across routes."""
    if adapter_id == _NASA_ADAPTER:
        if (
            expected_request_sha256 is not None
            or expected_research_ledger_sha256 is not None
        ):
            raise AuthorizedExecutionError(
                "machine-verifier SHA handoff pins are implemented only for the NIST route"
            )
        return _call_nasa_with_compat_namespace(
            _nasa_legacy.execute_authorized_action_with_failure_classification,
            adapter_id,
            repository_root=repository_root,
            research_run=research_run,
            action_registry_path=action_registry_path,
            request_path=request_path,
            expected_action_type=expected_action_type,
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
