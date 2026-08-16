"""Single public typed-execution router.

NASA execution remains byte-for-byte preserved in the internal legacy core.  The only
additional route is the audited NIST response-free structural simulation.  No generic
command, dynamic callable, subprocess, eval, exec, network, or physical-experiment
surface is introduced here.
"""
from __future__ import annotations

from pathlib import Path

from .authorized_execution_nasa_legacy import *  # noqa: F401,F403
from .authorized_execution_nasa_legacy import (
    EXECUTION_POLICY_VERSION,
    execute_authorized_action as _execute_nasa_authorized_action,
)

_NASA_ADAPTER = "nasa-battery"
_NIST_ADAPTER = "nist-ambench-process-characterization"


def execute_authorized_action(
    adapter_id: str,
    *,
    repository_root: str | Path,
    research_run: str | Path,
    action_registry_path: str | Path,
    request_path: str | Path,
    expected_action_type: str | None = None,
) -> dict:
    if adapter_id == _NASA_ADAPTER:
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
        )
    raise AuthorizedExecutionError(
        f"bounded typed execution is not implemented for adapter_id={adapter_id!r}"
    )
