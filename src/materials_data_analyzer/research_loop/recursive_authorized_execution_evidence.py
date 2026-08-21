"""Independent typed-execution evidence for recursive research progression.

The public recursive controller never accepts a caller-authored verified execution
record. This adapter reconstructs one only from an existing typed request, the live
action registry, the domain-pinned verifier, and the immutable research ledger.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .action_registry import describe_action, load_action_registry
from .heat_conduction_action import (
    ACTION_TYPE as HEAT_ACTION_TYPE,
    ACTION_VERSION as HEAT_ACTION_VERSION,
    verify_heat_conduction_action_report_pinned,
)
from .kernel import ResearchLoopError, load_research_state
from .nist_pinned_verifier import verify_nist_structural_design_report_pinned
from .nist_structural_design_action import (
    ACTION_TYPE as NIST_ACTION_TYPE,
    ACTION_VERSION as NIST_ACTION_VERSION,
)

VERIFIED_EXECUTION_RECORD_SCHEMA_VERSION = "1.0"
RECURSIVE_EXECUTION_EVIDENCE_POLICY_VERSION = "1.0"

_ADAPTERS = {
    "reference-heat-conduction": (HEAT_ACTION_TYPE, HEAT_ACTION_VERSION),
    "nist-ambench-process-characterization": (NIST_ACTION_TYPE, NIST_ACTION_VERSION),
}


class RecursiveAuthorizedExecutionEvidenceError(ResearchLoopError):
    """Raised when typed execution cannot be independently reconstructed."""


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


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RecursiveAuthorizedExecutionEvidenceError(
                f"duplicate JSON key is not allowed: {key}"
            )
        result[key] = value
    return result


def _load_json_record(path: Path, *, field: str) -> tuple[dict[str, Any], dict[str, Any]]:
    raw = path.read_bytes()
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RecursiveAuthorizedExecutionEvidenceError(
            f"{field} must be valid UTF-8 JSON"
        ) from exc
    if not isinstance(value, dict):
        raise RecursiveAuthorizedExecutionEvidenceError(f"{field} root must be an object")
    return value, {
        "path": str(path),
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def _resolve_file(value: str | Path, *, field: str) -> Path:
    try:
        path = Path(value).expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise RecursiveAuthorizedExecutionEvidenceError(
            f"{field} does not resolve to an existing file"
        ) from exc
    if not path.is_file():
        raise RecursiveAuthorizedExecutionEvidenceError(f"{field} must be a regular file")
    return path


def _resolve_directory(value: str | Path, *, field: str) -> Path:
    try:
        path = Path(value).expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise RecursiveAuthorizedExecutionEvidenceError(
            f"{field} does not resolve to an existing directory"
        ) from exc
    if not path.is_dir():
        raise RecursiveAuthorizedExecutionEvidenceError(f"{field} must be a directory")
    return path


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
    """Reconstruct one recursive execution record from verified repository artifacts."""
    if adapter_id not in _ADAPTERS:
        raise RecursiveAuthorizedExecutionEvidenceError(
            "recursive execution evidence supports only independently pinned heat/NIST adapters"
        )
    if (
        not isinstance(source_checkpoint_sha256, str)
        or len(source_checkpoint_sha256) != 64
        or any(ch not in "0123456789abcdef" for ch in source_checkpoint_sha256)
    ):
        raise RecursiveAuthorizedExecutionEvidenceError(
            "source_checkpoint_sha256 must be lowercase SHA-256"
        )
    if not isinstance(expected_candidate_action_id, str) or not expected_candidate_action_id.strip():
        raise RecursiveAuthorizedExecutionEvidenceError(
            "expected_candidate_action_id must be non-empty"
        )
    if (
        not isinstance(expected_candidate_action_class, str)
        or not expected_candidate_action_class.strip()
    ):
        raise RecursiveAuthorizedExecutionEvidenceError(
            "expected_candidate_action_class must be non-empty"
        )

    root = _resolve_directory(repository_root, field="repository_root")
    run = _resolve_directory(research_run, field="research_run")
    registry_path = _resolve_file(action_registry_path, field="action_registry_path")
    request_file = _resolve_file(request_path, field="request_path")
    report_file = _resolve_file(action_report_path, field="action_report_path")
    request, request_record = _load_json_record(request_file, field="typed execution request")

    concrete_action_type, concrete_action_version = _ADAPTERS[adapter_id]
    if request.get("action_id") != expected_candidate_action_id:
        raise RecursiveAuthorizedExecutionEvidenceError(
            "typed request action_id differs from recursive planner-selected candidate"
        )
    if request.get("action_type") != concrete_action_type:
        raise RecursiveAuthorizedExecutionEvidenceError(
            "typed request action_type differs from the selected execution adapter"
        )
    if request.get("action_version") != concrete_action_version:
        raise RecursiveAuthorizedExecutionEvidenceError(
            "typed request action_version differs from the selected execution adapter"
        )

    registry = load_action_registry(registry_path, repository_root=root)
    contract = describe_action(registry, concrete_action_type)
    if contract.get("version") != concrete_action_version:
        raise RecursiveAuthorizedExecutionEvidenceError(
            "live registry action version differs from typed execution adapter"
        )
    if contract.get("category") != expected_candidate_action_class:
        raise RecursiveAuthorizedExecutionEvidenceError(
            "live registry action category differs from planner-selected action class"
        )
    if request.get("expected_registry_sha256") != registry.get("registry_sha256"):
        raise RecursiveAuthorizedExecutionEvidenceError(
            "typed request is not pinned to the live execution registry"
        )

    request_run = Path(str(request.get("research_run"))).expanduser()
    if not request_run.is_absolute():
        request_run = request_file.parent / request_run
    if request_run.resolve(strict=True) != run:
        raise RecursiveAuthorizedExecutionEvidenceError(
            "typed request research_run differs from supplied immutable ledger"
        )
    request_registry = Path(str(request.get("registry"))).expanduser()
    if not request_registry.is_absolute():
        request_registry = request_file.parent / request_registry
    if request_registry.resolve(strict=True) != registry_path:
        raise RecursiveAuthorizedExecutionEvidenceError(
            "typed request registry path differs from supplied live registry"
        )

    if adapter_id == "reference-heat-conduction":
        verified = verify_heat_conduction_action_report_pinned(
            report_file,
            request_value=request,
            request_path=request_file,
            request_record=request_record,
        )
        if (
            verified.get("deterministic_recomputation_verified") is not True
            or verified.get("ledger_artifact_binding_verified") is not True
        ):
            raise RecursiveAuthorizedExecutionEvidenceError(
                "heat domain verifier did not establish deterministic ledger-bound execution"
            )
        result_sha256 = verified.get("solver_result_sha256")
    else:
        verified = verify_nist_structural_design_report_pinned(
            report_file,
            request_value=request,
            request_path=request_file,
            request_record=request_record,
        )
        if verified.get("valid") is not True:
            raise RecursiveAuthorizedExecutionEvidenceError(
                "NIST domain verifier did not establish a valid ledger-bound execution"
            )
        report_value, _ = _load_json_record(report_file, field="NIST action report")
        output = report_value.get("output")
        if not isinstance(output, Mapping):
            raise RecursiveAuthorizedExecutionEvidenceError(
                "NIST verified report omitted output binding"
            )
        result_sha256 = output.get("sha256")

    if (
        not isinstance(result_sha256, str)
        or len(result_sha256) != 64
        or any(ch not in "0123456789abcdef" for ch in result_sha256)
    ):
        raise RecursiveAuthorizedExecutionEvidenceError(
            "domain verifier did not yield one canonical result artifact SHA-256"
        )

    state = load_research_state(run)
    actions = state.get("actions")
    if not isinstance(actions, list):
        raise RecursiveAuthorizedExecutionEvidenceError("research action ledger is malformed")
    matches = [
        item
        for item in actions
        if isinstance(item, Mapping)
        and item.get("action_id") == expected_candidate_action_id
    ]
    if len(matches) != 1:
        raise RecursiveAuthorizedExecutionEvidenceError(
            "research ledger must contain exactly one planner-selected typed action"
        )
    action = matches[0]
    if action.get("action_type") != concrete_action_type:
        raise RecursiveAuthorizedExecutionEvidenceError(
            "research ledger concrete action type differs from verified request"
        )
    outcome = action.get("status")
    if outcome not in {"completed", "rejected", "failed"}:
        raise RecursiveAuthorizedExecutionEvidenceError(
            "research ledger action status is not a terminal execution outcome"
        )

    record: dict[str, Any] = {
        "schema_version": VERIFIED_EXECUTION_RECORD_SCHEMA_VERSION,
        "policy_version": RECURSIVE_EXECUTION_EVIDENCE_POLICY_VERSION,
        "source_checkpoint_sha256": source_checkpoint_sha256,
        "authorization_status": "explicit_request_authorized_by_existing_chain",
        "independent_verification_status": "verified_by_existing_chain",
        "action_id": expected_candidate_action_id,
        "action_type": expected_candidate_action_class,
        "action_version": concrete_action_version,
        "request_sha256": request_record["sha256"],
        "registry_sha256": registry["registry_sha256"],
        "result_sha256": result_sha256,
        "execution_outcome": outcome,
        "execution_success": outcome == "completed",
        "concrete_execution": {
            "adapter_id": adapter_id,
            "action_type": concrete_action_type,
            "action_version": concrete_action_version,
            "report_path": str(report_file),
            "research_ledger_sha256": state["ledger_sha256"],
            "domain_verifier_result_sha256": _canonical_sha256(verified),
            "domain_verifier_recomputed": True,
            "ledger_artifact_binding_reverified": True,
        },
        "scientific_evidence_upgraded": False,
    }
    record["verification_record_sha256"] = _canonical_sha256(record)
    return record


__all__ = [
    "RECURSIVE_EXECUTION_EVIDENCE_POLICY_VERSION",
    "RecursiveAuthorizedExecutionEvidenceError",
    "build_authenticated_recursive_execution_record",
]
