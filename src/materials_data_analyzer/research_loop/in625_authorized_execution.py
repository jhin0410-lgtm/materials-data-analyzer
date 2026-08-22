"""Authorized typed execution for the verified IN625 external-evidence action."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping

from .action_authorization import assess_current_action_authorization
from .action_output_ledger_transaction import (
    cleanup_action_output_ledger_transaction,
    mark_action_output_ledger_committed,
    prepare_action_output_ledger_transaction,
    recover_action_output_ledger_transaction_before_authorization,
    shared_research_ledger_transaction_lock,
)
from .authorized_execution_nasa_legacy import (
    AuthorizedExecutionError,
    _load_request_snapshot,
    _require_expected_action_type,
    _require_request_binding,
)
from .in625_execution_verifier import ADAPTER_ID
from .in625_external_evidence_action import (
    ACTION_TYPE,
    ACTION_VERSION,
    COST_UNITS,
    execute_in625_external_evidence_action_preparsed,
    verify_in625_external_evidence_action_report_pinned,
)
from .kernel import load_research_state

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _required_sha_pin(value: str | None, *, field: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise AuthorizedExecutionError(f"{field} must be canonical lowercase SHA-256 hex")
    return value


def _build_result(
    *,
    request_record: Mapping[str, Any],
    authorization_status: str,
    registry: Mapping[str, Any],
    report_path: Path,
    verified: Mapping[str, Any],
    action_id: str,
    actions_before: int,
    actions_after: int,
    action_executed: bool,
    transaction_recovered: bool,
    recovery_stage: str | None,
    state_snapshot_repaired: bool,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "execution_policy_version": "1.8+in625-external-evidence-1.0",
        "adapter_id": ADAPTER_ID,
        "action_type": ACTION_TYPE,
        "action_version": ACTION_VERSION,
        "request_binding": {
            "path": request_record["path"],
            "sha256": request_record["sha256"],
            "size_bytes": request_record["bytes"],
        },
        "authorization_status": authorization_status,
        "execution_registry": {
            "registry_id": registry.get("registry_id"),
            "registry_sha256": registry.get("registry_sha256"),
            "registry_path": registry.get("registry_path"),
        },
        "execution_status": "completed_or_structured_rejection",
        "ledger_action_id": action_id,
        "action_report": str(report_path),
        "verified_report": dict(verified),
        "actions_before": actions_before,
        "actions_after": actions_after,
        "maximum_actions_executed_per_invocation": 1,
        "action_executed": action_executed,
        "transaction_recovered": transaction_recovered,
        "transaction_recovery_stage": recovery_stage,
        "state_snapshot_repaired": state_snapshot_repaired,
        "output_ledger_transaction": "cleaned",
        "explicit_execution_request_used": True,
        "verifier_request_sha256_handoff_pinned": True,
        "verifier_research_ledger_sha256_handoff_pinned": True,
        "generic_command_execution_available": False,
        "network_access_initiated_by_typed_action": False,
        "real_external_archive_consumed": True,
        "physical_experiment_execution_initiated": False,
        "direct_condition_comparability_established": False,
        "empirical_model_validation_established": False,
        "scientific_evidence_upgraded_by_orchestrator": False,
        "scientific_boundary": (
            "This action establishes exact-byte provenance and availability of one real external IN625 source archive only. "
            "It does not establish measurement semantics, condition comparability, empirical model validity, hypothesis truth, or positive scientific closeout."
        ),
    }


def _finish_recovery(
    *,
    request: Mapping[str, Any],
    request_file: Path,
    request_record: Mapping[str, Any],
    run: Path,
    recovery: Mapping[str, Any],
) -> dict[str, Any]:
    if recovery.get("action_type") != ACTION_TYPE or recovery.get("action_version") != ACTION_VERSION:
        raise AuthorizedExecutionError("recovered IN625 action type/version binding drifted")
    if recovery.get("cost_units") != COST_UNITS:
        raise AuthorizedExecutionError("recovered IN625 action cost binding drifted")
    action_id = recovery.get("action_id")
    if not isinstance(action_id, str) or request.get("action_id") != action_id:
        raise AuthorizedExecutionError("recovered IN625 action_id differs from pinned request")
    report_path = Path(str(recovery.get("action_report"))).expanduser().resolve(strict=True)
    verified = verify_in625_external_evidence_action_report_pinned(
        report_path,
        request_value=request,
        request_path=request_file,
        request_record=request_record,
    )
    state = recovery.get("research_state")
    if not isinstance(state, Mapping) or not isinstance(state.get("actions"), list):
        raise AuthorizedExecutionError("recovered IN625 research state is malformed")
    actions = state["actions"]
    cleanup_action_output_ledger_transaction(research_run=run, action_id=action_id)
    stage_raw = recovery.get("recovery_stage")
    stage = str(stage_raw) if stage_raw is not None else "prepared_recovery"
    actions_added = 1 if stage == "published" else 0
    registry = recovery.get("registry")
    if not isinstance(registry, Mapping):
        raise AuthorizedExecutionError("recovered IN625 execution registry is malformed")
    return _build_result(
        request_record=request_record,
        authorization_status="recovered_prior_authorized_transaction",
        registry=registry,
        report_path=report_path,
        verified=verified,
        action_id=action_id,
        actions_before=len(actions) - actions_added,
        actions_after=len(actions),
        action_executed=False,
        transaction_recovered=True,
        recovery_stage=stage,
        state_snapshot_repaired=bool(recovery.get("state_snapshot_repaired")),
    )


def execute_in625_authorized_action(
    *,
    repository_root: str | Path,
    research_run: str | Path,
    action_registry_path: str | Path,
    request_path: str | Path,
    expected_action_type: str | None = None,
    expected_request_sha256: str | None = None,
    expected_research_ledger_sha256: str | None = None,
) -> dict[str, Any]:
    """Execute exactly one verified external-source registration action."""
    root = Path(repository_root).expanduser().resolve(strict=True)
    run = Path(research_run).expanduser().resolve(strict=True)
    request_file = Path(request_path).expanduser().resolve(strict=True)
    request, request_record = _load_request_snapshot(request_file)
    _require_expected_action_type(request, expected_action_type=expected_action_type)
    request_sha_pin = _required_sha_pin(expected_request_sha256, field="expected_request_sha256")
    ledger_sha_pin = _required_sha_pin(
        expected_research_ledger_sha256, field="expected_research_ledger_sha256"
    )
    if request_record.get("sha256") != request_sha_pin:
        raise AuthorizedExecutionError(
            "exact IN625 execution request bytes differ from the independently verified request SHA-256"
        )

    with shared_research_ledger_transaction_lock(run):
        prior_recovery = recover_action_output_ledger_transaction_before_authorization(
            research_run=run,
            request=request,
            request_path=request_file,
            request_record=request_record,
        )
        if prior_recovery is not None:
            return _finish_recovery(
                request=request,
                request_file=request_file,
                request_record=request_record,
                run=run,
                recovery=prior_recovery,
            )

        before = load_research_state(run)
        if before.get("ledger_sha256") != ledger_sha_pin:
            raise AuthorizedExecutionError(
                "research ledger changed after independent IN625 execution verification"
            )
        authorization = assess_current_action_authorization(
            ADAPTER_ID,
            repository_root=root,
            research_run=run,
            action_registry_path=action_registry_path,
        )
        if authorization.get("authorization_status") != "ready_for_explicit_execution_request":
            raise AuthorizedExecutionError(
                "IN625 external-evidence action is not ready for explicit typed execution"
            )
        selected = authorization.get("selected_action")
        contract = authorization.get("execution_contract")
        if not isinstance(selected, Mapping) or not isinstance(contract, Mapping):
            raise AuthorizedExecutionError("IN625 authorization omitted action contract")
        if (
            selected.get("action_type") != ACTION_TYPE
            or selected.get("action_version") != ACTION_VERSION
            or selected.get("cost_units") != COST_UNITS
            or contract.get("action_type") != ACTION_TYPE
            or contract.get("action_version") != ACTION_VERSION
            or contract.get("category") != "external_evidence_search"
            or contract.get("cost_units") != COST_UNITS
        ):
            raise AuthorizedExecutionError("IN625 authorization action/version/category/cost drifted")
        registry_path = Path(str(contract["registry_path"])).expanduser().resolve(strict=True)
        registry_sha = str(contract["registry_sha256"])
        action_id = _require_request_binding(
            request,
            request_path=request_file,
            action_type=ACTION_TYPE,
            research_run=run,
            repository_root=root,
            registry_path=registry_path,
            registry_sha256=registry_sha,
        )
        if request.get("action_version") != ACTION_VERSION:
            raise AuthorizedExecutionError(
                "execution request action_version differs from authorized IN625 action"
            )
        if request.get("expected_source_config_sha256") != selected.get("expected_source_config_sha256"):
            raise AuthorizedExecutionError(
                "execution request source config SHA differs from planner-selected IN625 source"
            )
        if request.get("expected_archive_sha256") != selected.get("expected_archive_sha256"):
            raise AuthorizedExecutionError(
                "execution request archive SHA differs from planner-selected IN625 source"
            )
        before_actions = before.get("actions")
        if not isinstance(before_actions, list):
            raise AuthorizedExecutionError("pre-execution IN625 action ledger is malformed")
        before_count = len(before_actions)
        transaction = prepare_action_output_ledger_transaction(
            research_run=run,
            request=request,
            request_path=request_file,
            request_record=request_record,
            action_id=action_id,
            action_type=ACTION_TYPE,
            action_version=ACTION_VERSION,
            cost_units=COST_UNITS,
            state=before,
        )
        if transaction.get("recovered"):
            recovered_state = transaction.get("research_state")
            if not isinstance(recovered_state, Mapping):
                raise AuthorizedExecutionError("prepared IN625 transaction recovery state is malformed")
            return _finish_recovery(
                request=request,
                request_file=request_file,
                request_record=request_record,
                run=run,
                recovery={
                    "action_type": ACTION_TYPE,
                    "action_version": ACTION_VERSION,
                    "cost_units": COST_UNITS,
                    "action_id": action_id,
                    "action_report": transaction.get("action_report"),
                    "research_state": recovered_state,
                    "registry": {
                        "registry_id": contract.get("registry_id"),
                        "registry_path": str(registry_path),
                        "registry_sha256": registry_sha,
                    },
                    "recovery_stage": "prepared_recovery",
                    "state_snapshot_repaired": False,
                },
            )
        result = execute_in625_external_evidence_action_preparsed(
            request,
            request_path=request_file,
            request_record=request_record,
        )
        after = load_research_state(run)
        after_actions = after.get("actions")
        if not isinstance(after_actions, list) or len(after_actions) != before_count + 1:
            raise AuthorizedExecutionError("IN625 typed action must append exactly one ledger action")
        if after_actions[-1].get("action_id") != action_id:
            raise AuthorizedExecutionError("IN625 typed action ledger action_id drifted")
        mark_action_output_ledger_committed(
            research_run=run,
            action_id=action_id,
            action_type=ACTION_TYPE,
            state=after,
        )
        report_path = Path(str(result["action_report"])).expanduser().resolve(strict=True)
        verified = verify_in625_external_evidence_action_report_pinned(
            report_path,
            request_value=request,
            request_path=request_file,
            request_record=request_record,
        )
        cleanup_action_output_ledger_transaction(research_run=run, action_id=action_id)
        return _build_result(
            request_record=request_record,
            authorization_status=str(authorization["authorization_status"]),
            registry={
                "registry_id": contract.get("registry_id"),
                "registry_path": str(registry_path),
                "registry_sha256": registry_sha,
            },
            report_path=report_path,
            verified=verified,
            action_id=action_id,
            actions_before=before_count,
            actions_after=len(after_actions),
            action_executed=True,
            transaction_recovered=False,
            recovery_stage=None,
            state_snapshot_repaired=False,
        )


__all__ = ["execute_in625_authorized_action"]
