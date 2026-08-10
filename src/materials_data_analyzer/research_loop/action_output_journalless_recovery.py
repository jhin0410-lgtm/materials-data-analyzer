"""Recovery guard for transaction directories left before/while journal cleanup.

This module handles only the narrow state where the action transaction directory
exists but journal.json does not. It never guesses a scientific/action result.
An unstarted transaction may be cleaned only when it contains no published action
and only atomic-journal temporary files. A post-ledger cleanup interruption may be
reconstructed only from an exact pinned request, checksum-bound action report,
verified registry contract, and one matching immutable-ledger action.
"""
from __future__ import annotations

import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from . import kernel as _kernel
from .action_output_ledger_transaction import (
    ACTION_REPORT_FILENAME,
    JOURNAL_FILENAME,
    SCHEMA_VERSION,
    ActionOutputLedgerTransactionError,
    _action_directory,
    _atomic_write_json,
    _matching_action,
    _transaction_directory,
    _utc_now,
    _validate_ledger_action_matches_report,
    _validate_recovery_registry_contract,
)


def _only_atomic_journal_temps(directory: Path) -> bool:
    for entry in directory.iterdir():
        if not entry.is_file() or entry.is_symlink():
            return False
        if not (
            entry.name.startswith(f".{JOURNAL_FILENAME}.")
            and entry.name.endswith(".tmp")
        ):
            return False
    return True


def _remove_transaction_directory(research_run: Path, action_id: str) -> None:
    transaction_directory = _transaction_directory(research_run, action_id)
    shutil.rmtree(transaction_directory)
    root = transaction_directory.parent
    try:
        root.rmdir()
    except OSError:
        pass


def recover_journalless_action_transaction_before_authorization(
    *,
    research_run: Path,
    request: Mapping[str, Any],
    request_path: Path,
    request_record: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Classify and recover a transaction directory that has no journal.json."""
    action_id = request.get("action_id")
    action_type = request.get("action_type")
    if not isinstance(action_id, str) or not action_id.strip():
        raise ActionOutputLedgerTransactionError(
            "journal-less recovery request action_id must be a non-empty string"
        )
    if not isinstance(action_type, str) or not action_type.strip():
        raise ActionOutputLedgerTransactionError(
            "journal-less recovery request action_type must be a non-empty string"
        )

    transaction_directory = _transaction_directory(research_run, action_id)
    if not transaction_directory.exists():
        return None
    journal_path = transaction_directory / JOURNAL_FILENAME
    if journal_path.is_file():
        return None
    if not transaction_directory.is_dir() or transaction_directory.is_symlink():
        raise ActionOutputLedgerTransactionError(
            "journal-less action transaction path is not a real directory"
        )

    action_directory = _action_directory(research_run, action_id)
    try:
        _, _, state = _kernel._load_verified_run(research_run)
    except (OSError, _kernel.ResearchLoopError) as exc:
        raise ActionOutputLedgerTransactionError(
            "journal-less recovery requires a currently verified ledger/state snapshot"
        ) from exc

    action = _matching_action(state, action_id)
    report_path = action_directory / ACTION_REPORT_FILENAME

    if action is None:
        if action_directory.exists():
            raise ActionOutputLedgerTransactionError(
                "journal-less transaction has published action output without a ledger proof"
            )
        if not _only_atomic_journal_temps(transaction_directory):
            raise ActionOutputLedgerTransactionError(
                "journal-less unstarted transaction contains unclassified recovery data"
            )
        _remove_transaction_directory(research_run, action_id)
        return None

    if not report_path.is_file():
        raise ActionOutputLedgerTransactionError(
            "journal-less ledgered transaction is missing its action report"
        )
    try:
        report = _kernel._load_json(report_path)
    except (OSError, _kernel.ResearchLoopError) as exc:
        raise ActionOutputLedgerTransactionError(
            "journal-less ledgered transaction report is invalid"
        ) from exc
    if not isinstance(report, Mapping):
        raise ActionOutputLedgerTransactionError(
            "journal-less ledgered transaction report must be an object"
        )
    action_version = report.get("action_version")
    cost_units = report.get("cost_units")
    if not isinstance(action_version, str) or not action_version.strip():
        raise ActionOutputLedgerTransactionError(
            "journal-less report action_version is malformed"
        )
    if isinstance(cost_units, bool) or not isinstance(cost_units, int) or cost_units < 0:
        raise ActionOutputLedgerTransactionError(
            "journal-less report cost_units is malformed"
        )

    registry = _validate_recovery_registry_contract(
        research_run=research_run,
        request=request,
        request_path=request_path,
        action_type=action_type,
        action_version=action_version,
        cost_units=cost_units,
    )
    _validate_ledger_action_matches_report(
        state=state,
        action=action,
        action_id=action_id,
        action_type=action_type,
        action_version=action_version,
        cost_units=cost_units,
        request_record=request_record,
        report_path=report_path,
    )

    journal = {
        "schema_version": SCHEMA_VERSION,
        "action_id": action_id,
        "action_type": action_type,
        "action_version": action_version,
        "cost_units": cost_units,
        "action_directory": str(action_directory),
        "request": dict(request_record),
        "phase": "ledger_committed",
        "created_at_utc": _utc_now(),
        "updated_at_utc": _utc_now(),
        "reconstructed_after_journalless_cleanup_interruption": True,
    }
    _atomic_write_json(journal_path, journal)
    return {
        "recovered": True,
        "recovery_stage": "ledger_committed_journalless",
        "state_snapshot_repaired": False,
        "research_state": dict(state),
        "action_report": str(report_path),
        "action_id": action_id,
        "action_type": action_type,
        "action_version": action_version,
        "cost_units": cost_units,
        "registry": registry,
    }


__all__ = ["recover_journalless_action_transaction_before_authorization"]
