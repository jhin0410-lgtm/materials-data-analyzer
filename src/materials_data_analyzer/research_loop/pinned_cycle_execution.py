"""Pinned one-cycle execution for policy-authorized closed-loop research.

The ordinary explicit-request surface snapshots a request from its pathname when the
executor begins.  A closed-loop controller has already authorized *specific bytes*
before it delegates a side effect, so reopening that pathname would create a TOCTOU
window.  This module carries the validated bytes/value across that boundary and reuses
the existing authorization, transaction, hardcoded dispatch, and pinned-verifier
contracts without re-reading the request file.

This is an internal orchestration adapter.  It does not add a generic executor, widen
network/laboratory authority, or convert execution success into scientific support.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from . import authorized_execution as _ae
from .action_authorization import ActionAuthorizationError, assess_action_authorization
from .kernel import ResearchLoopError
from .planning_state import build_research_planning_state
from .planning_transition import determine_research_transition

PINNED_CYCLE_SCHEMA_VERSION = "1.0"
PINNED_CYCLE_POLICY_VERSION = "1.0"


class PinnedCycleExecutionError(ResearchLoopError):
    """Raised when exact prevalidated request bytes cannot remain authoritative."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PinnedCycleExecutionError(f"duplicate JSON key is not allowed: {key}")
        result[key] = value
    return result


def _parse_pinned_request(
    *,
    request_path: str | Path,
    request_bytes: bytes,
    expected_sha256: str,
) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    if not isinstance(request_bytes, bytes) or not request_bytes:
        raise PinnedCycleExecutionError("request_bytes must be non-empty immutable bytes")
    actual_sha = hashlib.sha256(request_bytes).hexdigest()
    if actual_sha != expected_sha256:
        raise PinnedCycleExecutionError(
            "pinned request bytes do not match the predeclared request SHA-256"
        )
    try:
        text = request_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PinnedCycleExecutionError("pinned request must be UTF-8 JSON") from exc
    try:
        request = json.loads(text, object_pairs_hook=_reject_duplicate_pairs)
    except json.JSONDecodeError as exc:
        raise PinnedCycleExecutionError(f"invalid pinned request JSON: {exc}") from exc
    if not isinstance(request, dict):
        raise PinnedCycleExecutionError("pinned request JSON root must be an object")

    # The pathname is retained only as the semantic base for relative paths and as
    # provenance.  The request bytes are never read from it in this execution path.
    path = Path(request_path).expanduser().resolve(strict=False)
    parent = path.parent.resolve(strict=True)
    if not parent.is_dir():
        raise PinnedCycleExecutionError(
            f"pinned request parent directory does not exist: {parent}"
        )
    record = {"path": str(path), "bytes": len(request_bytes), "sha256": actual_sha}
    return path, request, record


def execute_authorized_action_snapshot(
    adapter_id: str,
    *,
    repository_root: str | Path,
    research_run: str | Path,
    action_registry_path: str | Path,
    request_path: str | Path,
    request_bytes: bytes,
    expected_request_sha256: str,
    expected_action_type: str | None = None,
) -> dict[str, Any]:
    """Execute exactly one typed action from bytes already checksum-validated by policy."""
    if adapter_id != "nasa-battery":
        raise PinnedCycleExecutionError(
            "pinned typed execution is currently implemented only for nasa-battery"
        )
    root = Path(repository_root).expanduser().resolve(strict=True)
    run = Path(research_run).expanduser().resolve(strict=True)
    request_file, request, request_record = _parse_pinned_request(
        request_path=request_path,
        request_bytes=request_bytes,
        expected_sha256=expected_request_sha256,
    )
    try:
        _ae._require_expected_action_type(
            request, expected_action_type=expected_action_type
        )
    except _ae.AuthorizedExecutionError as exc:
        raise PinnedCycleExecutionError(str(exc)) from exc

    with _ae.shared_research_ledger_transaction_lock(run):
        prior_recovery = _ae.recover_journalless_action_transaction_before_authorization(
            research_run=run,
            request=request,
            request_path=request_file,
            request_record=request_record,
        )
        if prior_recovery is None:
            prior_recovery = _ae.recover_action_output_ledger_transaction_before_authorization(
                research_run=run,
                request=request,
                request_path=request_file,
                request_record=request_record,
            )
        if prior_recovery is not None:
            try:
                result = _ae._finish_recovered_transaction(
                    adapter_id=adapter_id,
                    run=run,
                    request=request,
                    request_file=request_file,
                    request_record=request_record,
                    recovery=prior_recovery,
                )
            except _ae.AuthorizedExecutionError as exc:
                raise PinnedCycleExecutionError(str(exc)) from exc
            result["request_bytes_source"] = "pinned_in_memory_snapshot"
            return result

        before_state = build_research_planning_state(
            adapter_id,
            repository_root=root,
            research_run=run,
            action_registry_path=action_registry_path,
        )
        try:
            authorization = assess_action_authorization(before_state, repository_root=root)
        except ActionAuthorizationError as exc:
            raise PinnedCycleExecutionError(str(exc)) from exc
        if authorization.get("authorization_status") != "ready_for_explicit_execution_request":
            raise PinnedCycleExecutionError(
                "current selected action is not ready for the pinned execution request: "
                f"{authorization.get('authorization_status')!r}"
            )
        selected = authorization.get("selected_action")
        contract = authorization.get("execution_contract")
        if not isinstance(selected, Mapping) or not isinstance(contract, Mapping):
            raise PinnedCycleExecutionError("authorization omitted selected action contract")
        action_type = selected.get("action_type")
        action_version = selected.get("action_version")
        if not isinstance(action_type, str) or not isinstance(action_version, str):
            raise PinnedCycleExecutionError("selected action type/version binding is malformed")
        if contract.get("action_version") != action_version:
            raise PinnedCycleExecutionError(
                "selected action version does not match the authorized execution contract"
            )
        dispatch_key = (action_type, action_version)
        if dispatch_key not in _ae._DISPATCH:
            raise PinnedCycleExecutionError(
                "selected action type/version has no hardcoded typed executor"
            )
        registry_raw = contract.get("registry_path")
        registry_sha = contract.get("registry_sha256")
        if not isinstance(registry_raw, str) or not isinstance(registry_sha, str):
            raise PinnedCycleExecutionError("authorization execution registry binding is malformed")
        registry_path = Path(registry_raw).expanduser().resolve(strict=True)
        try:
            cost_units = _ae._dispatch_cost_units(dispatch_key, contract)
            action_id = _ae._require_request_binding(
                request,
                request_path=request_file,
                action_type=action_type,
                research_run=run,
                repository_root=root,
                registry_path=registry_path,
                registry_sha256=registry_sha,
            )
            expected_action_directory = _ae._expected_action_directory(run, action_id)
        except _ae.AuthorizedExecutionError as exc:
            raise PinnedCycleExecutionError(str(exc)) from exc

        before_ledger = _ae.load_research_state(run)
        before_actions = before_ledger.get("actions")
        if not isinstance(before_actions, list):
            raise PinnedCycleExecutionError("pre-execution research action ledger is malformed")
        before_count = len(before_actions)

        transaction = _ae.prepare_action_output_ledger_transaction(
            research_run=run,
            request=request,
            request_path=request_file,
            request_record=request_record,
            action_id=action_id,
            action_type=action_type,
            action_version=action_version,
            cost_units=cost_units,
            state=before_ledger,
        )
        executor, verifier = _ae._DISPATCH[dispatch_key]
        if transaction.get("recovered"):
            executor_result: Mapping[str, Any] = {
                "execution_status": "recovered",
                "action_id": action_id,
            }
        else:
            executor_result = executor(
                request,
                request_path=request_file,
                request_record=request_record,
            )

        after_ledger = _ae.load_research_state(run)
        after_actions = after_ledger.get("actions")
        if not isinstance(after_actions, list):
            raise PinnedCycleExecutionError("post-execution research action ledger is malformed")
        if len(after_actions) != before_count + 1:
            raise PinnedCycleExecutionError(
                "typed executor or recovery must append exactly one research action"
            )
        try:
            ledger_action, report_path = _ae._latest_action_report(
                after_ledger,
                expected_action_type=action_type,
                expected_action_id=action_id,
                expected_action_directory=expected_action_directory,
            )
            _ae.mark_action_output_ledger_committed(
                research_run=run,
                action_id=action_id,
                action_type=action_type,
                state=after_ledger,
            )
            verified_report = verifier(
                report_path,
                request_value=request,
                request_path=request_file,
                request_record=request_record,
            )
        except _ae.AuthorizedExecutionError as exc:
            raise PinnedCycleExecutionError(str(exc)) from exc
        if not isinstance(executor_result, Mapping) or not isinstance(verified_report, Mapping):
            raise PinnedCycleExecutionError("typed executor/verifier returned malformed result")
        if executor_result.get("action_id") != action_id:
            raise PinnedCycleExecutionError(
                "typed executor result action_id does not match pinned request"
            )
        if verified_report.get("action_id") != action_id:
            raise PinnedCycleExecutionError(
                "verified action report action_id does not match pinned request"
            )
        _ae.cleanup_action_output_ledger_transaction(research_run=run, action_id=action_id)

        result = _ae._build_result(
            adapter_id=adapter_id,
            action_type=action_type,
            action_version=action_version,
            request_record=request_record,
            authorization_status=str(authorization["authorization_status"]),
            registry_id=contract.get("registry_id"),
            registry_sha=registry_sha,
            registry_path=registry_path,
            ledger_action=ledger_action,
            report_path=report_path,
            verified_report=verified_report,
            actions_before=before_count,
            actions_after=len(after_actions),
            transaction_recovered=bool(transaction.get("recovered")),
            recovery_stage="published" if transaction.get("recovered") else None,
            state_snapshot_repaired=False,
            action_executed=not bool(transaction.get("recovered")),
        )
        result["request_bytes_source"] = "pinned_in_memory_snapshot"
        return result


def run_pinned_research_cycle(
    adapter_id: str,
    *,
    repository_root: str | Path,
    research_run: str | Path,
    action_registry_path: str | Path,
    request_path: str | Path,
    request_bytes: bytes,
    expected_request_sha256: str,
) -> dict[str, Any]:
    """Execute one pinned action and rebuild planning state exactly once."""
    root = Path(repository_root).expanduser().resolve(strict=True)
    before_state = build_research_planning_state(
        adapter_id,
        repository_root=root,
        research_run=research_run,
        action_registry_path=action_registry_path,
    )
    before_transition = determine_research_transition(before_state)
    authorization = assess_action_authorization(before_state, repository_root=root)
    if authorization.get("authorization_status") != "ready_for_explicit_execution_request":
        return {
            "schema_version": PINNED_CYCLE_SCHEMA_VERSION,
            "pinned_cycle_policy_version": PINNED_CYCLE_POLICY_VERSION,
            "adapter_id": adapter_id,
            "cycle_status": "authorization_denied",
            "before_planning_state": before_state,
            "before_transition": before_transition,
            "authorization": authorization,
            "execution": None,
            "after_planning_state": None,
            "after_transition": None,
            "actions_executed": 0,
        }
    execution = execute_authorized_action_snapshot(
        adapter_id,
        repository_root=root,
        research_run=research_run,
        action_registry_path=action_registry_path,
        request_path=request_path,
        request_bytes=request_bytes,
        expected_request_sha256=expected_request_sha256,
    )
    after_state = build_research_planning_state(
        adapter_id,
        repository_root=root,
        research_run=research_run,
        action_registry_path=action_registry_path,
    )
    return {
        "schema_version": PINNED_CYCLE_SCHEMA_VERSION,
        "pinned_cycle_policy_version": PINNED_CYCLE_POLICY_VERSION,
        "adapter_id": adapter_id,
        "cycle_status": "one_action_executed",
        "before_planning_state": before_state,
        "before_transition": before_transition,
        "authorization": authorization,
        "execution": execution,
        "after_planning_state": after_state,
        "after_transition": determine_research_transition(after_state),
        "actions_executed": 1,
        "request_bytes_source": "pinned_in_memory_snapshot",
        "automatic_request_generation_available": False,
        "generic_command_execution_available": False,
        "network_access_initiated_by_cycle_orchestrator": False,
        "scientific_evidence_upgraded_by_cycle_orchestrator": False,
    }


__all__ = [
    "PINNED_CYCLE_POLICY_VERSION",
    "PINNED_CYCLE_SCHEMA_VERSION",
    "PinnedCycleExecutionError",
    "execute_authorized_action_snapshot",
    "run_pinned_research_cycle",
]
