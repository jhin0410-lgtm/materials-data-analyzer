"""Single public typed-execution router.

NASA execution remains byte-for-byte preserved in the internal legacy core. The only
additional route is the audited NIST response-free structural simulation. No generic
command, dynamic callable, subprocess, eval, exec, network, or physical-experiment
surface is introduced here.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .authorized_execution_nasa_legacy import *  # noqa: F401,F403
from .authorized_execution_nasa_legacy import (
    EXECUTION_POLICY_VERSION,
    _action_count,
    assess_current_action_authorization,
    execute_authorized_action as _execute_nasa_authorized_action,
)
from .kernel import ResearchLoopError

_NASA_ADAPTER = "nasa-battery"
_NIST_ADAPTER = "nist-ambench-process-characterization"
_NIST_ACTION_TYPE = "nist_structural_design_simulation"


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
    """Execute one typed action, optionally pinning the exact NIST request/state handoff.

    The extra SHA pins are deliberately NIST-only. They connect a separately verified
    machine-authored request to the exact bytes and pre-execution research ledger seen by
    the executor. The long-standing NASA explicit-request surface is preserved unchanged.
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
        return _execute_nasa_authorized_action(
            adapter_id,
            repository_root=repository_root,
            research_run=research_run,
            action_registry_path=action_registry_path,
            request_path=request_path,
            expected_action_type=expected_action_type,
        )
    if adapter_id == _NIST_ADAPTER:
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
        f"bounded typed execution is not implemented for adapter_id={adapter_id!r}"
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
