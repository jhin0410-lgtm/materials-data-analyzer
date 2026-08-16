"""Integrated mission-authenticated execution boundary for the NIST typed action.

This module is the operational machine path. It runs the independent authenticated-request
verifier itself and forwards only the verifier-derived request/ledger SHA pins into the common
typed executor. A caller therefore cannot turn a self-computed pair of hashes into a claim
that the mission/delegation verifier actually ran.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .authorized_execution import execute_authorized_action_with_failure_classification
from .nist_authenticated_request import verify_nist_authenticated_request

ADAPTER_ID = "nist-ambench-process-characterization"
ACTION_TYPE = "nist_structural_design_simulation"


def execute_nist_authenticated_action(
    *,
    repository_root: str | Path,
    mission_path: str | Path,
    expected_mission_sha256: str,
    policy_id: str,
    request_delegation_policy_path: str | Path,
    research_run: str | Path,
    action_registry_path: str | Path,
    request_path: str | Path,
    manifest_path: str | Path,
) -> dict[str, Any]:
    """Verify mission-rooted request provenance, then execute exactly that NIST request."""
    verified = verify_nist_authenticated_request(
        repository_root=repository_root,
        mission_path=mission_path,
        expected_mission_sha256=expected_mission_sha256,
        policy_id=policy_id,
        request_delegation_policy_path=request_delegation_policy_path,
        research_run=research_run,
        action_registry_path=action_registry_path,
        request_path=request_path,
        manifest_path=manifest_path,
    )
    if (
        verified.get("verification_status")
        != "bounded_nist_request_verified_eligible_for_existing_typed_executor"
        or verified.get("adapter_id") != ADAPTER_ID
        or verified.get("action_type") != ACTION_TYPE
        or verified.get("execution_authorized") is not False
        or verified.get("physical_experiment_execution_authorized") is not False
        or verified.get("scientific_evidence_upgraded") is not False
    ):
        raise RuntimeError("NIST authenticated-request verifier returned an unsafe receipt")
    request_binding = verified.get("request_binding")
    if not isinstance(request_binding, dict):
        raise RuntimeError("NIST authenticated-request verifier omitted request binding")
    request_sha = request_binding.get("sha256")
    ledger_sha = verified.get("ledger_sha256")
    if not isinstance(request_sha, str) or not isinstance(ledger_sha, str):
        raise RuntimeError("NIST authenticated-request verifier omitted SHA handoff pins")

    execution = execute_authorized_action_with_failure_classification(
        ADAPTER_ID,
        repository_root=repository_root,
        research_run=research_run,
        action_registry_path=action_registry_path,
        request_path=request_path,
        expected_action_type=ACTION_TYPE,
        expected_request_sha256=request_sha,
        expected_research_ledger_sha256=ledger_sha,
    )
    return {
        **execution,
        "machine_authenticated_execution": True,
        "authenticated_request_verification": verified,
    }


__all__ = ["execute_nist_authenticated_action"]
