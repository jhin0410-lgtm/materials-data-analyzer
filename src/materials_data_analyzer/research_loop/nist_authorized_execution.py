"""Authorized execution extension for one NIST response-free simulation action."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .action_authorization import assess_current_action_authorization
from .kernel import load_research_state
from .nist_pinned_verifier import verify_nist_structural_design_report_pinned
from .nist_structural_design_action import (
    ACTION_TYPE,
    ACTION_VERSION,
    execute_nist_structural_design_action_preparsed,
)
from .authorized_execution_nasa_legacy import (
    AuthorizedExecutionError,
    _load_request_snapshot,
    _require_expected_action_type,
    _require_request_binding,
)

ADAPTER_ID = "nist-ambench-process-characterization"
COST_UNITS = 1


def execute_nist_authorized_action(
    *,
    repository_root: str | Path,
    research_run: str | Path,
    action_registry_path: str | Path,
    request_path: str | Path,
    expected_action_type: str | None = None,
) -> dict[str, Any]:
    root = Path(repository_root).expanduser().resolve(strict=True)
    run = Path(research_run).expanduser().resolve(strict=True)
    request_file = Path(request_path).expanduser().resolve(strict=True)
    request, request_record = _load_request_snapshot(request_file)
    _require_expected_action_type(request, expected_action_type=expected_action_type)
    authorization = assess_current_action_authorization(
        ADAPTER_ID,
        repository_root=root,
        research_run=run,
        action_registry_path=action_registry_path,
    )
    if authorization.get("authorization_status") != "ready_for_explicit_execution_request":
        raise AuthorizedExecutionError(
            "NIST selected action is not ready for explicit typed execution"
        )
    selected = authorization.get("selected_action")
    contract = authorization.get("execution_contract")
    if not isinstance(selected, Mapping) or not isinstance(contract, Mapping):
        raise AuthorizedExecutionError("NIST authorization omitted selected action contract")
    if (
        selected.get("action_type") != ACTION_TYPE
        or selected.get("action_version") != ACTION_VERSION
        or selected.get("cost_units") != COST_UNITS
        or contract.get("action_type") != ACTION_TYPE
        or contract.get("action_version") != ACTION_VERSION
        or contract.get("cost_units") != COST_UNITS
    ):
        raise AuthorizedExecutionError("NIST authorization action/version/cost drifted")
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
    before = load_research_state(run)
    before_actions = len(before["actions"])
    result = execute_nist_structural_design_action_preparsed(
        request,
        request_path=request_file,
        request_record=request_record,
    )
    after = load_research_state(run)
    if len(after["actions"]) != before_actions + 1:
        raise AuthorizedExecutionError("NIST typed action must append exactly one ledger action")
    if after["actions"][-1].get("action_id") != action_id:
        raise AuthorizedExecutionError("NIST typed action ledger action_id drifted")
    report_path = Path(str(result["action_report"])).resolve(strict=True)
    verified = verify_nist_structural_design_report_pinned(
        report_path,
        request_value=request,
        request_path=request_file,
        request_record=request_record,
    )
    return {
        "schema_version": "1.0",
        "execution_policy_version": "1.7+nist-structural-1.0",
        "adapter_id": ADAPTER_ID,
        "action_type": ACTION_TYPE,
        "action_version": ACTION_VERSION,
        "request_binding": {
            "path": request_record["path"],
            "sha256": request_record["sha256"],
            "size_bytes": request_record["bytes"],
        },
        "authorization_status": authorization["authorization_status"],
        "execution_registry": {
            "registry_id": contract["registry_id"],
            "registry_sha256": registry_sha,
            "registry_path": str(registry_path),
        },
        "execution_status": "completed",
        "ledger_action_id": action_id,
        "action_report": str(report_path),
        "verified_report": verified,
        "actions_before": before_actions,
        "actions_after": len(after["actions"]),
        "maximum_actions_executed_per_invocation": 1,
        "action_executed": True,
        "transaction_recovered": False,
        "state_snapshot_repaired": False,
        "explicit_execution_request_used": True,
        "generic_command_execution_available": False,
        "network_access_initiated_by_orchestrator": False,
        "model_fit_initiated_by_orchestrator": False,
        "physical_experiment_execution_initiated": False,
        "synthetic_response_generated": False,
        "scientific_evidence_upgraded_by_orchestrator": False,
        "scientific_boundary": (
            "This typed action verifies only response-free design-matrix structure. "
            "Nine real Stage 1 traces remain required before stronger scientific use."
        ),
    }


__all__ = ["execute_nist_authorized_action"]
