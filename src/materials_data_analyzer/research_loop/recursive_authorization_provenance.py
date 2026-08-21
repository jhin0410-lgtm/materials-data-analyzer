"""Historical authorization reconstruction for recursive execution evidence.

This module never authorizes or executes an action. It deterministically replays the
repository's existing authorization policy against the exact immutable-ledger prefix
immediately before a recorded action. This distinguishes "an action/report exists" from
"the same action was actually authorizable before execution".
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from .action_authorization import assess_current_action_authorization
from .kernel import (
    LEDGER_FILENAME,
    LOCK_FILENAME,
    OBJECTIVE_FILENAME,
    STATE_FILENAME,
    ResearchLoopError,
    _load_consistent_read,
    _reconstruct_state,
    _serialize_ledger,
)

RECURSIVE_AUTHORIZATION_PROVENANCE_SCHEMA_VERSION = "1.0"
RECURSIVE_AUTHORIZATION_PROVENANCE_POLICY_VERSION = "1.0"


class RecursiveAuthorizationProvenanceError(ResearchLoopError):
    """Raised when pre-execution authorization cannot be reconstructed exactly."""


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


def verify_preexecution_authorization(
    *,
    adapter_id: str,
    repository_root: str | Path,
    research_run: str | Path,
    action_registry_path: str | Path,
    expected_action_id: str,
    expected_concrete_action_type: str,
    expected_concrete_action_version: str,
    expected_candidate_action_class: str,
) -> dict[str, Any]:
    """Replay existing authorization on the exact ledger prefix before one action."""
    root = Path(repository_root).expanduser().resolve(strict=True)
    run = Path(research_run).expanduser().resolve(strict=True)
    registry_path = Path(action_registry_path).expanduser().resolve(strict=True)
    run_path, events, current_state = _load_consistent_read(run)

    matches = [
        (index, event)
        for index, event in enumerate(events)
        if event.get("event_type") == "action_recorded"
        and isinstance(event.get("payload"), Mapping)
        and event["payload"].get("action_id") == expected_action_id
    ]
    if len(matches) != 1:
        raise RecursiveAuthorizationProvenanceError(
            "immutable ledger must contain exactly one matching action event"
        )
    action_index, action_event = matches[0]
    action_payload = action_event["payload"]
    if action_payload.get("action_type") != expected_concrete_action_type:
        raise RecursiveAuthorizationProvenanceError(
            "immutable ledger action type differs from expected concrete action"
        )
    if action_index < 1:
        raise RecursiveAuthorizationProvenanceError(
            "action event cannot precede the immutable research objective"
        )

    prefix = events[:action_index]
    prefix_text = _serialize_ledger(prefix)
    prefix_sha = hashlib.sha256(prefix_text.encode("utf-8")).hexdigest()
    pre_state = _reconstruct_state(prefix, prefix_sha)
    if pre_state.get("status") != "active":
        raise RecursiveAuthorizationProvenanceError(
            "pre-execution immutable research state was not active"
        )

    objective_path = run_path / OBJECTIVE_FILENAME
    if not objective_path.is_file():
        raise RecursiveAuthorizationProvenanceError(
            "immutable run objective disappeared during authorization reconstruction"
        )
    with TemporaryDirectory(prefix="recursive-auth-replay-") as temporary:
        replay = Path(temporary)
        (replay / OBJECTIVE_FILENAME).write_bytes(objective_path.read_bytes())
        (replay / LEDGER_FILENAME).write_text(prefix_text, encoding="utf-8")
        (replay / STATE_FILENAME).write_text(
            json.dumps(pre_state, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (replay / LOCK_FILENAME).write_bytes(b"\0")
        authorization = assess_current_action_authorization(
            adapter_id,
            repository_root=root,
            research_run=replay,
            action_registry_path=registry_path,
        )

    if authorization.get("authorization_status") != "ready_for_explicit_execution_request":
        raise RecursiveAuthorizationProvenanceError(
            "exact pre-execution state was not ready for an explicit typed request"
        )
    for field in (
        "execution_registry_verified",
        "selected_action_binding_verified",
        "budget_verified",
    ):
        if authorization.get(field) is not True:
            raise RecursiveAuthorizationProvenanceError(
                f"pre-execution authorization did not establish {field}"
            )
    selected = authorization.get("selected_action")
    contract = authorization.get("execution_contract")
    if not isinstance(selected, Mapping) or not isinstance(contract, Mapping):
        raise RecursiveAuthorizationProvenanceError(
            "pre-execution authorization omitted selected action or execution contract"
        )
    if (
        selected.get("action_type") != expected_concrete_action_type
        or selected.get("action_version") != expected_concrete_action_version
    ):
        raise RecursiveAuthorizationProvenanceError(
            "pre-execution selected action differs from executed type/version"
        )
    if (
        contract.get("action_type") != expected_concrete_action_type
        or contract.get("action_version") != expected_concrete_action_version
    ):
        raise RecursiveAuthorizationProvenanceError(
            "pre-execution execution contract differs from executed type/version"
        )
    if contract.get("category") != expected_candidate_action_class:
        raise RecursiveAuthorizationProvenanceError(
            "pre-execution execution contract category differs from planner action class"
        )
    if selected.get("cost_units") != action_payload.get("cost_units"):
        raise RecursiveAuthorizationProvenanceError(
            "pre-execution selected cost differs from immutable action event"
        )

    result: dict[str, Any] = {
        "schema_version": RECURSIVE_AUTHORIZATION_PROVENANCE_SCHEMA_VERSION,
        "policy_version": RECURSIVE_AUTHORIZATION_PROVENANCE_POLICY_VERSION,
        "verification_status": "preexecution_authorization_deterministically_reconstructed",
        "adapter_id": adapter_id,
        "action_id": expected_action_id,
        "concrete_action_type": expected_concrete_action_type,
        "concrete_action_version": expected_concrete_action_version,
        "candidate_action_class": expected_candidate_action_class,
        "pre_execution_ledger_sha256": prefix_sha,
        "pre_execution_event_count": len(prefix),
        "terminal_ledger_sha256": current_state.get("ledger_sha256"),
        "authorization_result_sha256": _canonical_sha256(authorization),
        "authorization_status": authorization.get("authorization_status"),
        "execution_registry_verified": True,
        "selected_action_binding_verified": True,
        "budget_verified": True,
        "explicit_request_was_not_inferred_from_execution_completion": True,
        "execution_performed_by_replay": False,
        "scientific_status_changed": False,
    }
    result["verification_sha256"] = _canonical_sha256(result)
    return result


__all__ = [
    "RECURSIVE_AUTHORIZATION_PROVENANCE_POLICY_VERSION",
    "RECURSIVE_AUTHORIZATION_PROVENANCE_SCHEMA_VERSION",
    "RecursiveAuthorizationProvenanceError",
    "verify_preexecution_authorization",
]
