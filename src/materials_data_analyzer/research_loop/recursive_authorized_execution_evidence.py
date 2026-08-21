"""Authorization-hardened recursive typed-execution evidence.

The preserved legacy adapter verifies request/registry/report/terminal-ledger identity.
This facade additionally reconstructs the existing authorization policy against the exact
immutable pre-execution ledger prefix before publishing any recursive execution record.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from . import recursive_authorized_execution_evidence_legacy as _legacy
from .recursive_authorization_provenance import verify_preexecution_authorization

VERIFIED_EXECUTION_RECORD_SCHEMA_VERSION = _legacy.VERIFIED_EXECUTION_RECORD_SCHEMA_VERSION
RECURSIVE_EXECUTION_EVIDENCE_POLICY_VERSION = "1.1"
RecursiveAuthorizedExecutionEvidenceError = (
    _legacy.RecursiveAuthorizedExecutionEvidenceError
)


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def build_authenticated_recursive_execution_record(
    *,
    source_checkpoint_sha256: str,
    expected_candidate_action_id: str,
    expected_candidate_action_class: str,
    adapter_id: str,
    repository_root: str | Path,
    research_run: str | Path,
    action_registry_path: str | Path,
    request_path: str | Path,
    action_report_path: str | Path,
) -> dict[str, Any]:
    """Reconstruct execution and its historical authorization from authoritative inputs."""
    record = _legacy.build_authenticated_recursive_execution_record(
        source_checkpoint_sha256=source_checkpoint_sha256,
        expected_candidate_action_id=expected_candidate_action_id,
        expected_candidate_action_class=expected_candidate_action_class,
        adapter_id=adapter_id,
        repository_root=repository_root,
        research_run=research_run,
        action_registry_path=action_registry_path,
        request_path=request_path,
        action_report_path=action_report_path,
    )
    concrete = record.get("concrete_execution")
    if not isinstance(concrete, dict):
        raise RecursiveAuthorizedExecutionEvidenceError(
            "legacy execution reconstruction omitted concrete_execution"
        )
    concrete_type = concrete.get("action_type")
    concrete_version = concrete.get("action_version")
    if not isinstance(concrete_type, str) or not isinstance(concrete_version, str):
        raise RecursiveAuthorizedExecutionEvidenceError(
            "legacy execution reconstruction omitted concrete action type/version"
        )
    authorization = verify_preexecution_authorization(
        adapter_id=adapter_id,
        repository_root=repository_root,
        research_run=research_run,
        action_registry_path=action_registry_path,
        expected_action_id=expected_candidate_action_id,
        expected_concrete_action_type=concrete_type,
        expected_concrete_action_version=concrete_version,
        expected_candidate_action_class=expected_candidate_action_class,
    )
    record = dict(record)
    record["policy_version"] = RECURSIVE_EXECUTION_EVIDENCE_POLICY_VERSION
    record["authorization_status"] = (
        "preexecution_authorization_deterministically_reconstructed"
    )
    concrete = dict(concrete)
    concrete["preexecution_authorization"] = authorization
    record["concrete_execution"] = concrete
    record.pop("verification_record_sha256", None)
    record["verification_record_sha256"] = _canonical_sha256(record)
    return record


__all__ = [
    "RECURSIVE_EXECUTION_EVIDENCE_POLICY_VERSION",
    "VERIFIED_EXECUTION_RECORD_SCHEMA_VERSION",
    "RecursiveAuthorizedExecutionEvidenceError",
    "build_authenticated_recursive_execution_record",
]
