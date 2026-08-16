"""Explicit one-action executor for authorized bounded research actions.

This module deliberately has no generic shell, subprocess, eval, exec, or dynamic
callable dispatch. Only hardcoded typed package executors are supported. Each
invocation can execute at most one action and then independently re-verifies the
new ledger-bound action report.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Mapping

from .action_authorization import (
    ActionAuthorizationError,
    assess_current_action_authorization,
)
from .action_output_journalless_recovery import (
    recover_journalless_action_transaction_before_authorization,
)
from .action_output_ledger_transaction import (
    cleanup_action_output_ledger_transaction,
    mark_action_output_ledger_committed,
    prepare_action_output_ledger_transaction,
    recover_action_output_ledger_transaction_before_authorization,
    shared_research_ledger_transaction_lock,
)
from .kernel import ResearchLoopError, load_research_state
from .nasa_audit_executor import (
    ACTION_TYPE as AUDIT_ACTION_TYPE,
    execute_nasa_audit_action_preparsed,
)
from .nasa_external_data_requirement_action import (
    ACTION_TYPE as EXTERNAL_REQUIREMENT_ACTION_TYPE,
    execute_nasa_external_data_requirement_action_preparsed,
)
from .nasa_protocol_stratification_action import (
    ACTION_TYPE as PROTOCOL_ACTION_TYPE,
    execute_nasa_protocol_stratification_action_preparsed,
)
from .nasa_target_reference_action import (
    ACTION_TYPE as TARGET_REFERENCE_ACTION_TYPE,
    execute_nasa_target_reference_action_preparsed,
)
from .nist_structural_design_simulation_action import (
    ACTION_TYPE as NIST_STRUCTURAL_ACTION_TYPE,
    execute_nist_structural_design_simulation_action_preparsed,
)
from .nist_structural_pinned_verifier import (
    verify_nist_structural_design_simulation_report_pinned,
)
from .nist_structural_research import (
    ADAPTER_ID as NIST_STRUCTURAL_ADAPTER_ID,
    assess_nist_structural_action_authorization,
)
from .pinned_execution_verifier import (
    verify_nasa_audit_action_report_pinned,
    verify_nasa_external_data_requirement_report_pinned,
    verify_nasa_protocol_stratification_report_pinned,
    verify_nasa_target_reference_report_pinned,
)

EXECUTION_SCHEMA_VERSION = "1.0"
EXECUTION_POLICY_VERSION = "1.8"
_ACTION_REPORT_FILENAME = "action_result.json"
_SUPPORTED_ADAPTERS = {"nasa-battery", NIST_STRUCTURAL_ADAPTER_ID}

Executor = Callable[..., dict[str, Any]]
Verifier = Callable[..., dict[str, Any]]

_DISPATCH: dict[tuple[str, str], tuple[Executor, Verifier]] = {
    (AUDIT_ACTION_TYPE, "1.0"): (
        execute_nasa_audit_action_preparsed,
        verify_nasa_audit_action_report_pinned,
    ),
    (TARGET_REFERENCE_ACTION_TYPE, "1.0"): (
        execute_nasa_target_reference_action_preparsed,
        verify_nasa_target_reference_report_pinned,
    ),
    (PROTOCOL_ACTION_TYPE, "1.0"): (
        execute_nasa_protocol_stratification_action_preparsed,
        verify_nasa_protocol_stratification_report_pinned,
    ),
    (EXTERNAL_REQUIREMENT_ACTION_TYPE, "1.0"): (
        execute_nasa_external_data_requirement_action_preparsed,
        verify_nasa_external_data_requirement_report_pinned,
    ),
    (NIST_STRUCTURAL_ACTION_TYPE, "1.0"): (
        execute_nist_structural_design_simulation_action_preparsed,
        verify_nist_structural_design_simulation_report_pinned,
    ),
}

_DISPATCH_COST_UNITS: dict[tuple[str, str], int] = {
    (AUDIT_ACTION_TYPE, "1.0"): 2,
    (TARGET_REFERENCE_ACTION_TYPE, "1.0"): 4,
    (PROTOCOL_ACTION_TYPE, "1.0"): 5,
    (EXTERNAL_REQUIREMENT_ACTION_TYPE, "1.0"): 2,
    (NIST_STRUCTURAL_ACTION_TYPE, "1.0"): 2,
}


class AuthorizedExecutionError(ResearchLoopError):
    """Raised when explicit typed execution cannot preserve its frozen contract."""


class AuthorizedExecutionStartedError(AuthorizedExecutionError):
    """Raised when a later verification failure follows a ledger mutation."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise AuthorizedExecutionError(f"duplicate JSON key is not allowed: {key}")
        result[key] = value
    return result


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_request_snapshot(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Read and parse the request once, preserving the exact authorized bytes."""
    if not path.is_file():
        raise AuthorizedExecutionError(f"execution request is not a file: {path}")
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise AuthorizedExecutionError(f"could not read execution request: {path}") from exc
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
    record = {
        "path": str(path),
        "bytes": len(data),
        "sha256": _sha256_bytes(data),
    }
    return value, record


def _resolve_request_path(raw: object, *, field: str, base: Path) -> Path:
    if not isinstance(raw, str) or not raw.strip():
        raise AuthorizedExecutionError(f"execution request {field} must be a path string")
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = base / candidate
    return candidate.resolve(strict=True)


def _require_expected_action_type(
    request: Mapping[str, Any],
    *,
    expected_action_type: str | None,
) -> None:
    if expected_action_type is None:
        return
    if not expected_action_type.strip():
        raise AuthorizedExecutionError("expected_action_type must be a non-empty string")
    requested = request.get("action_type")
    if requested != expected_action_type:
        raise AuthorizedExecutionError(
            f"execution surface requires action_type={expected_action_type!r}; "
            f"pinned request contains {requested!r}"
        )


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
        request.get("repository_root"), field="repository_root", base=request_path.parent
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


def _expected_action_directory(research_run: Path, action_id: str) -> Path:
    actions_root = (research_run / "actions").resolve(strict=False)
    _ensure_within(
        actions_root,
        research_run,
        message="research actions directory resolves outside the research run",
    )
    action_directory = (actions_root / action_id).resolve(strict=False)
    _ensure_within(
        action_directory,
        actions_root,
        message="requested action directory resolves outside the research actions directory",
    )
    return action_directory


def _action_report_for_id(
    state: Mapping[str, Any],
    *,
    expected_action_type: str,
    expected_action_id: str,
    expected_action_directory: Path,
    require_latest: bool,
) -> tuple[Mapping[str, Any], Path]:
    actions = state.get("actions")
    if not isinstance(actions, list) or not actions:
        raise AuthorizedExecutionError("post-execution research state contains no actions")
    if require_latest:
        candidates = [actions[-1]]
    else:
        candidates = [
            action
            for action in actions
            if isinstance(action, Mapping) and action.get("action_id") == expected_action_id
        ]
    if len(candidates) != 1 or not isinstance(candidates[0], Mapping):
        raise AuthorizedExecutionError(
            "research ledger must contain exactly one matching executed action"
        )
    action = candidates[0]
    if action.get("action_type") != expected_action_type:
        raise AuthorizedExecutionError(
            "ledger action type does not match the explicitly executed action"
        )
    if action.get("action_id") != expected_action_id:
        raise AuthorizedExecutionError(
            "ledger action ID does not match the explicit execution request"
        )
    artifacts = action.get("artifacts")
    if not isinstance(artifacts, list):
        raise AuthorizedExecutionError("ledger action artifacts are malformed")
    matches: list[Path] = []
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
    return action, matches[0]


def _latest_action_report(
    state: Mapping[str, Any],
    *,
    expected_action_type: str,
    expected_action_id: str,
    expected_action_directory: Path,
) -> tuple[Mapping[str, Any], Path]:
    return _action_report_for_id(
        state,
        expected_action_type=expected_action_type,
        expected_action_id=expected_action_id,
        expected_action_directory=expected_action_directory,
        require_latest=True,
    )


def _action_count(run: Path, *, phase: str) -> int:
    state = load_research_state(run)
    actions = state.get("actions")
    if not isinstance(actions, list):
        raise AuthorizedExecutionError(f"{phase} research action ledger is malformed")
    return len(actions)


def _dispatch_cost_units(
    dispatch_key: tuple[str, str], contract: Mapping[str, Any]
) -> int:
    expected = _DISPATCH_COST_UNITS.get(dispatch_key)
    if expected is None:
        raise AuthorizedExecutionError(
            "selected action type/version has no hardcoded cost contract"
        )
    observed = contract.get("cost_units")
    if observed is None:
        return expected
    if isinstance(observed, bool) or not isinstance(observed, int) or observed < 0:
        raise AuthorizedExecutionError("authorization execution cost binding is malformed")
    if observed != expected:
        raise AuthorizedExecutionError(
            "authorization execution cost does not match the hardcoded action version"
        )
    return expected


def _build_result(
    *,
    adapter_id: str,
    action_type: str,
    action_version: str,
    request_record: Mapping[str, Any],
    authorization_status: str,
    registry_id: object,
    registry_sha: str,
    registry_path: Path,
    ledger_action: Mapping[str, Any],
    report_path: Path,
    verified_report: Mapping[str, Any],
    actions_before: int,
    actions_after: int,
    transaction_recovered: bool,
    recovery_stage: str | None,
    state_snapshot_repaired: bool,
    action_executed: bool,
) -> dict[str, Any]:
    return {
        "schema_version": EXECUTION_SCHEMA_VERSION,
        "execution_policy_version": EXECUTION_POLICY_VERSION,
        "adapter_id": adapter_id,
        "action_type": action_type,
        "action_version": action_version,
        "request_binding": {
            "path": request_record["path"],
            "sha256": request_record["sha256"],
            "size_bytes": request_record["bytes"],
        },
        "authorization_status": authorization_status,
        "execution_registry": {
            "registry_id": registry_id,
            "registry_sha256": registry_sha,
            "registry_path": str(registry_path),
        },
        "execution_status": ledger_action.get("status"),
        "ledger_action_id": ledger_action.get("action_id"),
        "action_report": str(report_path),
        "verified_report": dict(verified_report),
        "actions_before": actions_before,
        "actions_after": actions_after,
        "maximum_actions_executed_per_invocation": 1,
        "action_executed": action_executed,
        "transaction_recovered": transaction_recovered,
        "transaction_recovery_stage": recovery_stage,
        "state_snapshot_repaired": state_snapshot_repaired,
        "output_ledger_transaction": "cleaned",
        "automatic_execution_authorized": False,
        "explicit_execution_request_used": True,
        "generic_command_execution_available": False,
        "network_access_initiated_by_orchestrator": False,
        "model_fit_initiated_by_orchestrator": False,
        "scientific_evidence_upgraded_by_orchestrator": False,
        "scientific_boundary": (
            "This wrapper proves bounded typed dispatch, exact request-byte handoff, "
            "surface-specific action restriction, recoverable output-to-ledger commit, "
            "and independent pinned-snapshot report verification. Scientific "
            "interpretation remains owned by the typed action and downstream evidence "
            "contracts; execution success or crash recovery does not itself upgrade "
            "scientific evidence."
        ),
    }


def _finish_recovered_transaction(
    *,
    adapter_id: str,
    run: Path,
    request: Mapping[str, Any],
    request_file: Path,
    request_record: Mapping[str, Any],
    recovery: Mapping[str, Any],
) -> dict[str, Any]:
    action_type = recovery.get("action_type")
    action_version = recovery.get("action_version")
    action_id = recovery.get("action_id")
    if not isinstance(action_type, str) or not isinstance(action_version, str):
        raise AuthorizedExecutionError("recovered action type/version binding is malformed")
    if not isinstance(action_id, str):
        raise AuthorizedExecutionError("recovered action ID is malformed")
    dispatch_key = (action_type, action_version)
    if dispatch_key not in _DISPATCH:
        raise AuthorizedExecutionError(
            "recovered action type/version has no hardcoded typed verifier"
        )
    expected_cost = _DISPATCH_COST_UNITS.get(dispatch_key)
    if recovery.get("cost_units") != expected_cost:
        raise AuthorizedExecutionError(
            "recovered action cost does not match the hardcoded action version"
        )
    expected_action_directory = _expected_action_directory(run, action_id)
    after_state = recovery.get("research_state")
    if not isinstance(after_state, Mapping):
        raise AuthorizedExecutionError("recovered research state is malformed")
    ledger_action, report_path = _action_report_for_id(
        after_state,
        expected_action_type=action_type,
        expected_action_id=action_id,
        expected_action_directory=expected_action_directory,
        require_latest=False,
    )
    _, verifier = _DISPATCH[dispatch_key]
    verified_report = verifier(
        report_path,
        request_value=request,
        request_path=request_file,
        request_record=request_record,
    )
    if not isinstance(verified_report, Mapping):
        raise AuthorizedExecutionError("typed verifier returned malformed result")
    if verified_report.get("action_id") != action_id:
        raise AuthorizedExecutionError(
            "verified recovered report action_id does not match the explicit request"
        )
    cleanup_action_output_ledger_transaction(research_run=run, action_id=action_id)
    actions = after_state.get("actions")
    if not isinstance(actions, list):
        raise AuthorizedExecutionError("recovered research actions are malformed")
    recovery_stage = recovery.get("recovery_stage")
    actions_added = 1 if recovery_stage == "published" else 0
    registry = recovery.get("registry")
    if not isinstance(registry, Mapping):
        raise AuthorizedExecutionError("recovered execution registry is malformed")
    registry_path_raw = registry.get("registry_path")
    registry_sha = registry.get("registry_sha256")
    if not isinstance(registry_path_raw, str) or not isinstance(registry_sha, str):
        raise AuthorizedExecutionError("recovered execution registry binding is malformed")
    return _build_result(
        adapter_id=adapter_id,
        action_type=action_type,
        action_version=action_version,
        request_record=request_record,
        authorization_status="recovered_prior_authorized_transaction",
        registry_id=registry.get("registry_id"),
        registry_sha=registry_sha,
        registry_path=Path(registry_path_raw),
        ledger_action=ledger_action,
        report_path=report_path,
        verified_report=verified_report,
        actions_before=len(actions) - actions_added,
        actions_after=len(actions),
        transaction_recovered=True,
        recovery_stage=str(recovery_stage) if recovery_stage is not None else None,
        state_snapshot_repaired=bool(recovery.get("state_snapshot_repaired")),
        action_executed=False,
    )


def _current_authorization(
    adapter_id: str,
    *,
    repository_root: Path,
    research_run: Path,
    action_registry_path: str | Path,
) -> dict[str, Any]:
    if adapter_id == NIST_STRUCTURAL_ADAPTER_ID:
        return assess_nist_structural_action_authorization(
            repository_root=repository_root,
            research_run=research_run,
            action_registry_path=action_registry_path,
        )
    return assess_current_action_authorization(
        adapter_id,
        repository_root=repository_root,
        research_run=research_run,
        action_registry_path=action_registry_path,
    )


def execute_authorized_action(
    adapter_id: str,
    *,
    repository_root: str | Path,
    research_run: str | Path,
    action_registry_path: str | Path,
    request_path: str | Path,
    expected_action_type: str | None = None,
) -> dict[str, Any]:
    """Execute exactly one explicitly requested, currently authorized typed action."""
    if adapter_id not in _SUPPORTED_ADAPTERS:
        raise AuthorizedExecutionError(
            "bounded typed execution is implemented only for audited finite adapters: "
            + ", ".join(sorted(_SUPPORTED_ADAPTERS))
        )
    root = Path(repository_root).expanduser().resolve(strict=True)
    run = Path(research_run).expanduser().resolve(strict=True)
    request_file = Path(request_path).expanduser().resolve(strict=True)
    request, request_record = _load_request_snapshot(request_file)
    _require_expected_action_type(request, expected_action_type=expected_action_type)

    with shared_research_ledger_transaction_lock(run):
        prior_recovery = recover_journalless_action_transaction_before_authorization(
            research_run=run,
            request=request,
            request_path=request_file,
            request_record=request_record,
        )
        if prior_recovery is None:
            prior_recovery = recover_action_output_ledger_transaction_before_authorization(
                research_run=run,
                request=request,
                request_path=request_file,
                request_record=request_record,
            )
        if prior_recovery is not None:
            return _finish_recovered_transaction(
                adapter_id=adapter_id,
                run=run,
                request=request,
                request_file=request_file,
                request_record=request_record,
                recovery=prior_recovery,
            )

        try:
            authorization = _current_authorization(
                adapter_id,
                repository_root=root,
                research_run=run,
                action_registry_path=action_registry_path,
            )
        except (ActionAuthorizationError, ResearchLoopError) as exc:
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
        cost_units = _dispatch_cost_units(dispatch_key, contract)
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
        if adapter_id == NIST_STRUCTURAL_ADAPTER_ID:
            selected_config = selected.get("simulation_config")
            request_config = request.get("simulation_config")
            if not isinstance(selected_config, str) or not isinstance(request_config, str):
                raise AuthorizedExecutionError("NIST structural request must bind simulation_config")
            if _resolve_request_path(
                request_config,
                field="simulation_config",
                base=request_file.parent,
            ) != Path(selected_config).expanduser().resolve(strict=True):
                raise AuthorizedExecutionError(
                    "NIST structural request simulation_config does not match planner selection"
                )
        expected_action_directory = _expected_action_directory(run, request_action_id)

        before_state = load_research_state(run)
        before_actions = before_state.get("actions")
        if not isinstance(before_actions, list):
            raise AuthorizedExecutionError("pre-execution research action ledger is malformed")
        before_count = len(before_actions)

        transaction = prepare_action_output_ledger_transaction(
            research_run=run,
            request=request,
            request_path=request_file,
            request_record=request_record,
            action_id=request_action_id,
            action_type=action_type,
            action_version=action_version,
            cost_units=cost_units,
            state=before_state,
        )

        executor, verifier = _DISPATCH[dispatch_key]
        if transaction.get("recovered"):
            executor_result: Mapping[str, Any] = {
                "execution_status": "recovered",
                "action_id": request_action_id,
            }
        else:
            executor_result = executor(
                request,
                request_path=request_file,
                request_record=request_record,
            )

        after_state = load_research_state(run)
        after_actions = after_state.get("actions")
        if not isinstance(after_actions, list):
            raise AuthorizedExecutionError("post-execution research action ledger is malformed")
        if len(after_actions) != before_count + 1:
            raise AuthorizedExecutionError(
                "typed executor or recovery must append exactly one research action per invocation"
            )
        ledger_action, report_path = _latest_action_report(
            after_state,
            expected_action_type=action_type,
            expected_action_id=request_action_id,
            expected_action_directory=expected_action_directory,
        )
        mark_action_output_ledger_committed(
            research_run=run,
            action_id=request_action_id,
            action_type=action_type,
            state=after_state,
        )
        verified_report = verifier(
            report_path,
            request_value=request,
            request_path=request_file,
            request_record=request_record,
        )
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
        cleanup_action_output_ledger_transaction(
            research_run=run,
            action_id=request_action_id,
        )

        return _build_result(
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


def execute_authorized_action_with_failure_classification(
    adapter_id: str,
    *,
    repository_root: str | Path,
    research_run: str | Path,
    action_registry_path: str | Path,
    request_path: str | Path,
    expected_action_type: str | None = None,
) -> dict[str, Any]:
    """Execute once and distinguish post-ledger verification failure from preflight failure."""
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
        )
    except ResearchLoopError as exc:
        try:
            after_count = _action_count(run, phase="post-failure")
        except ResearchLoopError:
            raise
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
