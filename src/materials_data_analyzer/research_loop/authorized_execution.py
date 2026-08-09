"""Explicit one-action executor for authorized bounded research actions.

This module deliberately has no generic shell, subprocess, eval, exec, or dynamic
callable dispatch. Only hardcoded typed package executors are supported. Each
invocation can execute at most one action and then independently re-verifies the
new ledger-bound action report.
"""

from __future__ import annotations

import hashlib
import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping

from .action_authorization import (
    ActionAuthorizationError,
    assess_current_action_authorization,
)
from .kernel import ResearchLoopError, load_research_state
from .nasa_audit_executor import (
    ACTION_TYPE as AUDIT_ACTION_TYPE,
    execute_nasa_audit_action,
    verify_nasa_audit_action_report,
)
from .nasa_external_data_requirement_action import (
    ACTION_TYPE as EXTERNAL_REQUIREMENT_ACTION_TYPE,
    execute_nasa_external_data_requirement_action,
    verify_nasa_external_data_requirement_report,
)
from .nasa_protocol_stratification_action import (
    ACTION_TYPE as PROTOCOL_ACTION_TYPE,
    execute_nasa_protocol_stratification_action,
    verify_nasa_protocol_stratification_report,
)
from .nasa_target_reference_action import (
    ACTION_TYPE as TARGET_REFERENCE_ACTION_TYPE,
    execute_nasa_target_reference_action,
    verify_nasa_target_reference_report,
)

EXECUTION_SCHEMA_VERSION = "1.0"
EXECUTION_POLICY_VERSION = "1.1"
_ACTION_REPORT_FILENAME = "action_result.json"
_AUTHORIZED_REQUEST_DIRECTORY = "authorized_requests"
_EXECUTION_LOCK_FILENAME = ".authorized_execution.lock"

Executor = Callable[[str | Path], dict[str, Any]]
Verifier = Callable[[str | Path], dict[str, Any]]

# Dispatch is deliberately bound to the exact action contract version implemented
# by each hardcoded executor. A registry upgrade must add explicit code support.
_DISPATCH: dict[tuple[str, str], tuple[Executor, Verifier]] = {
    (AUDIT_ACTION_TYPE, "1.0"): (
        execute_nasa_audit_action,
        verify_nasa_audit_action_report,
    ),
    (TARGET_REFERENCE_ACTION_TYPE, "1.0"): (
        execute_nasa_target_reference_action,
        verify_nasa_target_reference_report,
    ),
    (PROTOCOL_ACTION_TYPE, "1.0"): (
        execute_nasa_protocol_stratification_action,
        verify_nasa_protocol_stratification_report,
    ),
    (EXTERNAL_REQUIREMENT_ACTION_TYPE, "1.0"): (
        execute_nasa_external_data_requirement_action,
        verify_nasa_external_data_requirement_report,
    ),
}


class AuthorizedExecutionError(ResearchLoopError):
    """Raised when explicit typed execution cannot preserve its frozen contract."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise AuthorizedExecutionError(f"duplicate JSON key is not allowed: {key}")
        result[key] = value
    return result


def _load_request_snapshot(path: Path) -> tuple[dict[str, Any], bytes]:
    if not path.is_file():
        raise AuthorizedExecutionError(f"execution request is not a file: {path}")
    data = path.read_bytes()
    if not data:
        raise AuthorizedExecutionError("execution request file must not be empty")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AuthorizedExecutionError("execution request must be UTF-8 JSON") from exc
    try:
        value = json.loads(text, object_pairs_hook=_reject_duplicate_pairs)
    except json.JSONDecodeError as exc:
        raise AuthorizedExecutionError(f"invalid execution request JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise AuthorizedExecutionError("execution request root must be an object")
    return value, data


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_request_path(raw: object, *, field: str, base: Path) -> Path:
    if not isinstance(raw, str) or not raw.strip():
        raise AuthorizedExecutionError(f"execution request {field} must be a path string")
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = base / candidate
    return candidate.resolve(strict=True)


def _require_request_binding(
    request: Mapping[str, Any],
    *,
    request_path: Path,
    action_type: str,
    research_run: Path,
    repository_root: Path,
    registry_path: Path,
    registry_sha256: str,
) -> str:
    if request.get("action_type") != action_type:
        raise AuthorizedExecutionError(
            "execution request action_type does not match the authorized selected action"
        )
    action_id = request.get("action_id")
    if not isinstance(action_id, str) or not action_id.strip():
        raise AuthorizedExecutionError("execution request action_id must be a non-empty string")
    request_run = _resolve_request_path(
        request.get("research_run"), field="research_run", base=request_path.parent
    )
    if request_run != research_run:
        raise AuthorizedExecutionError(
            "execution request research_run does not match the authorized research run"
        )
    request_root = _resolve_request_path(
        request.get("repository_root"),
        field="repository_root",
        base=request_path.parent,
    )
    if request_root != repository_root:
        raise AuthorizedExecutionError(
            "execution request repository_root does not match authorization context"
        )
    request_registry = _resolve_request_path(
        request.get("registry"), field="registry", base=request_path.parent
    )
    if request_registry != registry_path:
        raise AuthorizedExecutionError(
            "execution request registry does not match the verified execution registry"
        )
    if request.get("expected_registry_sha256") != registry_sha256:
        raise AuthorizedExecutionError(
            "execution request expected_registry_sha256 does not match authorization"
        )
    return action_id


def _ensure_within(path: Path, parent: Path, *, message: str) -> None:
    try:
        path.relative_to(parent)
    except ValueError as exc:
        raise AuthorizedExecutionError(message) from exc


def _materialize_authorized_request_snapshot(
    request_bytes: bytes,
    *,
    research_run: Path,
) -> Path:
    """Persist the exact validated bytes that the typed executor must consume."""
    snapshot_directory = research_run / _AUTHORIZED_REQUEST_DIRECTORY
    snapshot_directory.mkdir(parents=True, exist_ok=True)
    resolved_directory = snapshot_directory.resolve(strict=True)
    _ensure_within(
        resolved_directory,
        research_run,
        message="authorized request directory escapes the research run",
    )

    digest = _sha256_bytes(request_bytes)
    snapshot_path = resolved_directory / f"{digest}.json"
    try:
        descriptor = os.open(
            snapshot_path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o400,
        )
    except FileExistsError:
        if snapshot_path.is_symlink() or not snapshot_path.is_file():
            raise AuthorizedExecutionError(
                "authorized request snapshot path already exists but is not a regular file"
            )
        if snapshot_path.read_bytes() != request_bytes:
            raise AuthorizedExecutionError(
                "authorized request snapshot digest collision or content drift detected"
            )
    else:
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(request_bytes)
                handle.flush()
                os.fsync(handle.fileno())
        except Exception:
            snapshot_path.unlink(missing_ok=True)
            raise

    if snapshot_path.read_bytes() != request_bytes:
        raise AuthorizedExecutionError(
            "authorized request snapshot changed before typed execution"
        )
    return snapshot_path


@contextmanager
def _exclusive_execution_lock(research_run: Path) -> Iterator[None]:
    """Serialize wrapper-owned ledger mutation for one research run."""
    lock_path = research_run / _EXECUTION_LOCK_FILENAME
    try:
        descriptor = os.open(
            lock_path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
    except FileExistsError as exc:
        raise AuthorizedExecutionError(
            "another authorized execution is already active for this research run"
        ) from exc
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(f"pid={os.getpid()}\n")
            handle.flush()
            os.fsync(handle.fileno())
        yield
    finally:
        lock_path.unlink(missing_ok=True)


def _latest_action_report(
    state: Mapping[str, Any],
    *,
    expected_action_type: str,
    expected_action_id: str,
    research_run: Path,
) -> tuple[Mapping[str, Any], Path]:
    actions = state.get("actions")
    if not isinstance(actions, list) or not actions:
        raise AuthorizedExecutionError("post-execution research state contains no actions")
    latest = actions[-1]
    if not isinstance(latest, Mapping):
        raise AuthorizedExecutionError("latest post-execution action is malformed")
    if latest.get("action_type") != expected_action_type:
        raise AuthorizedExecutionError(
            "latest ledger action type does not match the explicitly executed action"
        )
    if latest.get("action_id") != expected_action_id:
        raise AuthorizedExecutionError(
            "latest ledger action ID does not match the explicit execution request"
        )
    artifacts = latest.get("artifacts")
    if not isinstance(artifacts, list):
        raise AuthorizedExecutionError("latest ledger action artifacts are malformed")
    matches: list[Path] = []
    expected_action_directory = (research_run / "actions" / expected_action_id).resolve()
    for item in artifacts:
        if not isinstance(item, Mapping):
            continue
        raw_path = item.get("path")
        if isinstance(raw_path, str) and Path(raw_path).name == _ACTION_REPORT_FILENAME:
            report_path = Path(raw_path).expanduser().resolve(strict=True)
            _ensure_within(
                report_path,
                expected_action_directory,
                message="ledger-bound action report escapes the expected action directory",
            )
            matches.append(report_path)
    if len(matches) != 1:
        raise AuthorizedExecutionError(
            "executed ledger action must bind exactly one action_result.json"
        )
    return latest, matches[0]


def execute_authorized_action(
    adapter_id: str,
    *,
    repository_root: str | Path,
    research_run: str | Path,
    action_registry_path: str | Path,
    request_path: str | Path,
) -> dict[str, Any]:
    """Execute exactly one explicitly requested, currently authorized typed action."""
    if adapter_id != "nasa-battery":
        raise AuthorizedExecutionError(
            "bounded typed execution is currently implemented only for nasa-battery"
        )
    root = Path(repository_root).expanduser().resolve(strict=True)
    run = Path(research_run).expanduser().resolve(strict=True)
    request_file = Path(request_path).expanduser().resolve(strict=True)
    request, request_bytes = _load_request_snapshot(request_file)
    request_sha256 = _sha256_bytes(request_bytes)

    with _exclusive_execution_lock(run):
        try:
            authorization = assess_current_action_authorization(
                adapter_id,
                repository_root=root,
                research_run=run,
                action_registry_path=action_registry_path,
            )
        except ActionAuthorizationError as exc:
            raise AuthorizedExecutionError(str(exc)) from exc
        if authorization.get("authorization_status") != "ready_for_explicit_execution_request":
            raise AuthorizedExecutionError(
                "current selected action is not ready for an explicit execution request: "
                f"{authorization.get('authorization_status')!r}"
            )
        selected = authorization.get("selected_action")
        contract = authorization.get("execution_contract")
        if not isinstance(selected, Mapping) or not isinstance(contract, Mapping):
            raise AuthorizedExecutionError("authorization omitted selected action contract")
        action_type = selected.get("action_type")
        action_version = selected.get("action_version")
        contract_version = contract.get("action_version")
        if not isinstance(action_type, str) or not isinstance(action_version, str):
            raise AuthorizedExecutionError("selected action type/version binding is malformed")
        if contract_version != action_version:
            raise AuthorizedExecutionError(
                "selected action version does not match the authorized execution contract"
            )
        dispatch_key = (action_type, action_version)
        if dispatch_key not in _DISPATCH:
            raise AuthorizedExecutionError(
                "selected action type/version has no hardcoded typed executor: "
                f"{action_type!r} version {action_version!r}"
            )
        registry_raw = contract.get("registry_path")
        registry_sha = contract.get("registry_sha256")
        if not isinstance(registry_raw, str) or not isinstance(registry_sha, str):
            raise AuthorizedExecutionError("authorization execution registry binding is malformed")
        registry_path = Path(registry_raw).expanduser().resolve(strict=True)
        request_action_id = _require_request_binding(
            request,
            request_path=request_file,
            action_type=action_type,
            research_run=run,
            repository_root=root,
            registry_path=registry_path,
            registry_sha256=registry_sha,
        )
        request_snapshot = _materialize_authorized_request_snapshot(
            request_bytes,
            research_run=run,
        )

        before_state = load_research_state(run)
        before_actions = before_state.get("actions")
        if not isinstance(before_actions, list):
            raise AuthorizedExecutionError("pre-execution research action ledger is malformed")
        before_count = len(before_actions)

        executor, verifier = _DISPATCH[dispatch_key]
        executor_result = executor(request_snapshot)

        after_state = load_research_state(run)
        after_actions = after_state.get("actions")
        if not isinstance(after_actions, list):
            raise AuthorizedExecutionError("post-execution research action ledger is malformed")
        if len(after_actions) != before_count + 1:
            raise AuthorizedExecutionError(
                "typed executor must append exactly one research action per invocation"
            )
        ledger_action, report_path = _latest_action_report(
            after_state,
            expected_action_type=action_type,
            expected_action_id=request_action_id,
            research_run=run,
        )
        verified_report = verifier(report_path)
        if not isinstance(executor_result, Mapping) or not isinstance(verified_report, Mapping):
            raise AuthorizedExecutionError("typed executor/verifier returned malformed result")
        if executor_result.get("action_id") != request_action_id:
            raise AuthorizedExecutionError(
                "typed executor result action_id does not match the explicit request"
            )
        if verified_report.get("action_id") != request_action_id:
            raise AuthorizedExecutionError(
                "verified action report action_id does not match the explicit request"
            )

        return {
            "schema_version": EXECUTION_SCHEMA_VERSION,
            "execution_policy_version": EXECUTION_POLICY_VERSION,
            "adapter_id": adapter_id,
            "action_type": action_type,
            "action_version": action_version,
            "request_binding": {
                "path": str(request_file),
                "sha256": request_sha256,
                "size_bytes": len(request_bytes),
                "executed_snapshot_path": str(request_snapshot),
                "executed_snapshot_sha256": _sha256_file(request_snapshot),
            },
            "authorization_status": authorization["authorization_status"],
            "execution_registry": {
                "registry_id": contract.get("registry_id"),
                "registry_sha256": registry_sha,
                "registry_path": str(registry_path),
            },
            "execution_status": ledger_action.get("status"),
            "ledger_action_id": ledger_action.get("action_id"),
            "action_report": str(report_path),
            "verified_report": dict(verified_report),
            "actions_before": before_count,
            "actions_after": len(after_actions),
            "maximum_actions_executed_per_invocation": 1,
            "action_executed": True,
            "automatic_execution_authorized": False,
            "explicit_execution_request_used": True,
            "generic_command_execution_available": False,
            "network_access_initiated_by_orchestrator": False,
            "model_fit_initiated_by_orchestrator": False,
            "scientific_evidence_upgraded_by_orchestrator": False,
            "scientific_boundary": (
                "This wrapper proves bounded typed dispatch and independent report verification. "
                "Scientific interpretation remains owned by the typed action and downstream evidence "
                "contracts; execution success does not itself upgrade scientific evidence."
            ),
        }


__all__ = [
    "EXECUTION_POLICY_VERSION",
    "EXECUTION_SCHEMA_VERSION",
    "AuthorizedExecutionError",
    "execute_authorized_action",
]
