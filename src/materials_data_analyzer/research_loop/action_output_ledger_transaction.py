"""Recoverable output-to-ledger transaction journal for authorized NASA actions.

The transaction is intentionally owned by the common authorized execution boundary.
Callers must hold the research kernel's exclusive ledger lock for the full lifetime
of prepare -> typed execution -> pinned verification -> cleanup. The kernel lock is
re-entrant for the owning thread so existing typed executors can keep using their
normal load/append helpers without creating a second synchronization domain.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .kernel import ResearchLoopError, append_action, append_action_and_stop

SCHEMA_VERSION = "1.0"
TRANSACTION_DIRECTORY = ".action_output_ledger_transactions"
JOURNAL_FILENAME = "journal.json"
ACTION_REPORT_FILENAME = "action_result.json"
EXTERNAL_REQUIREMENT_ACTION_TYPE = "external_data_requirement"
EXTERNAL_REQUIREMENT_STOP_REASON = "external_evidence_required"
AUDIT_ACTION_TYPE = "audit_existing_battery_run"

_AUDIT_IMMUTABLE_RELATIVE_PATHS = (
    "tables/validated_cycle_summary.csv",
    "tables/forecast_feature_table.csv",
    "tables/validation_predictions.csv",
    "config_snapshot.json",
)
_AUDIT_MUTABLE_RELATIVE_PATHS = (
    "tables/target_integrity_by_battery.csv",
    "tables/error_concentration_by_battery.csv",
    "tables/battery_influence_by_model.csv",
    "tables/battery_diagnostic_priority.csv",
    "tables/battery_condition_error_profile.csv",
    "reports/target_comparability_audit.json",
    "reports/target_comparability_audit.md",
    "reports/battery_influence_triage.json",
    "reports/battery_influence_triage.md",
    "reports/scientific_closeout.json",
    "reports/scientific_closeout.md",
    "run_manifest.json",
)


class ActionOutputLedgerTransactionError(ResearchLoopError):
    """Raised when crash recovery cannot prove a safe output/ledger transition."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, indent=2, ensure_ascii=False, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ActionOutputLedgerTransactionError(
            f"invalid action transaction JSON: {path}"
        ) from exc
    if not isinstance(value, dict):
        raise ActionOutputLedgerTransactionError(
            f"action transaction JSON must contain an object: {path}"
        )
    return value


def _transaction_directory(research_run: Path, action_id: str) -> Path:
    digest = hashlib.sha256(action_id.encode("utf-8")).hexdigest()[:32]
    root = research_run / TRANSACTION_DIRECTORY
    return root / digest


def _journal_path(research_run: Path, action_id: str) -> Path:
    return _transaction_directory(research_run, action_id) / JOURNAL_FILENAME


def _action_directory(research_run: Path, action_id: str) -> Path:
    actions_root = (research_run / "actions").resolve(strict=False)
    candidate = (actions_root / action_id).resolve(strict=False)
    try:
        candidate.relative_to(actions_root)
    except ValueError as exc:
        raise ActionOutputLedgerTransactionError(
            "action transaction path escapes the research actions directory"
        ) from exc
    return candidate


def _resolve_request_path(raw: object, *, base: Path, field: str) -> Path:
    if not isinstance(raw, str) or not raw.strip():
        raise ActionOutputLedgerTransactionError(
            f"transaction request {field} must be a non-empty path string"
        )
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = base / candidate
    return candidate.resolve(strict=True)


def _file_record(path: Path) -> dict[str, Any]:
    resolved = path.expanduser().resolve(strict=True)
    if not resolved.is_file():
        raise ActionOutputLedgerTransactionError(
            f"transaction-bound artifact is not a file: {resolved}"
        )
    return {
        "path": str(resolved),
        "bytes": resolved.stat().st_size,
        "sha256": _sha256_file(resolved),
    }


def _record_matches(record: Mapping[str, Any]) -> bool:
    raw_path = record.get("path")
    size = record.get("bytes")
    digest = record.get("sha256")
    if not isinstance(raw_path, str) or not isinstance(size, int) or isinstance(size, bool):
        return False
    if not isinstance(digest, str) or len(digest) != 64:
        return False
    try:
        current = _file_record(Path(raw_path))
    except (OSError, ResearchLoopError):
        return False
    return current == {"path": str(Path(raw_path).expanduser().resolve()), "bytes": size, "sha256": digest}


def _write_phase(journal_path: Path, journal: dict[str, Any], phase: str) -> None:
    journal["phase"] = phase
    journal["updated_at_utc"] = _utc_now()
    _atomic_write_json(journal_path, journal)


def _snapshot_audit_run(
    *,
    journal: dict[str, Any],
    transaction_directory: Path,
    request: Mapping[str, Any],
    request_path: Path,
    research_run: Path,
) -> None:
    analysis_run = _resolve_request_path(
        request.get("analysis_run"), base=request_path.parent, field="analysis_run"
    )
    if not analysis_run.is_dir():
        raise ActionOutputLedgerTransactionError(
            "audit transaction analysis_run must be a directory"
        )
    if analysis_run == research_run or analysis_run in research_run.parents or research_run in analysis_run.parents:
        raise ActionOutputLedgerTransactionError(
            "audit transaction requires non-overlapping analysis and research runs"
        )

    immutable: list[dict[str, Any]] = []
    for relative in _AUDIT_IMMUTABLE_RELATIVE_PATHS:
        target = analysis_run / relative
        immutable.append({"relative_path": relative, **_file_record(target)})

    backup_root = transaction_directory / "audit_backup"
    mutable: list[dict[str, Any]] = []
    for index, relative in enumerate(_AUDIT_MUTABLE_RELATIVE_PATHS):
        target = analysis_run / relative
        if not target.exists():
            mutable.append(
                {
                    "relative_path": relative,
                    "path": str(target.resolve(strict=False)),
                    "existed": False,
                }
            )
            continue
        if not target.is_file():
            raise ActionOutputLedgerTransactionError(
                f"audit mutable transaction target is not a file: {target}"
            )
        backup = backup_root / f"{index:03d}.bin"
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(target, backup)
        with backup.open("rb") as handle:
            os.fsync(handle.fileno())
        mutable.append(
            {
                "relative_path": relative,
                "path": str(target.resolve()),
                "existed": True,
                "backup_path": str(backup.resolve()),
                "bytes": backup.stat().st_size,
                "sha256": _sha256_file(backup),
            }
        )
    journal["audit_snapshot"] = {
        "analysis_run": str(analysis_run),
        "immutable": immutable,
        "mutable": mutable,
    }


def _restore_audit_snapshot(journal: Mapping[str, Any]) -> None:
    snapshot = journal.get("audit_snapshot")
    if not isinstance(snapshot, Mapping):
        raise ActionOutputLedgerTransactionError(
            "interrupted audit transaction is missing its recovery snapshot"
        )
    immutable = snapshot.get("immutable")
    mutable = snapshot.get("mutable")
    if not isinstance(immutable, list) or not isinstance(mutable, list):
        raise ActionOutputLedgerTransactionError("audit recovery snapshot is malformed")
    for record in immutable:
        if not isinstance(record, Mapping) or not _record_matches(record):
            raise ActionOutputLedgerTransactionError(
                "audit immutable input changed during an interrupted transaction"
            )
    for record in mutable:
        if not isinstance(record, Mapping):
            raise ActionOutputLedgerTransactionError("audit mutable snapshot is malformed")
        target_raw = record.get("path")
        existed = record.get("existed")
        if not isinstance(target_raw, str) or not isinstance(existed, bool):
            raise ActionOutputLedgerTransactionError("audit mutable snapshot is malformed")
        target = Path(target_raw)
        if not existed:
            target.unlink(missing_ok=True)
            continue
        backup_raw = record.get("backup_path")
        if not isinstance(backup_raw, str):
            raise ActionOutputLedgerTransactionError("audit backup path is missing")
        backup = Path(backup_raw)
        expected = {
            "path": str(backup.resolve()),
            "bytes": record.get("bytes"),
            "sha256": record.get("sha256"),
        }
        if not _record_matches(expected):
            raise ActionOutputLedgerTransactionError(
                "audit recovery backup checksum does not match the journal"
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(backup, target)


def _validate_journal_binding(
    journal: Mapping[str, Any],
    *,
    action_id: str,
    action_type: str,
    action_version: str,
    cost_units: int,
    request_record: Mapping[str, Any],
    action_directory: Path,
) -> None:
    expected = {
        "schema_version": SCHEMA_VERSION,
        "action_id": action_id,
        "action_type": action_type,
        "action_version": action_version,
        "cost_units": cost_units,
        "action_directory": str(action_directory),
    }
    for key, value in expected.items():
        if journal.get(key) != value:
            raise ActionOutputLedgerTransactionError(
                f"existing action transaction journal conflicts on {key}"
            )
    if journal.get("request") != dict(request_record):
        raise ActionOutputLedgerTransactionError(
            "existing action transaction request bytes do not match the pinned request"
        )


def _published_artifact_paths(report_path: Path, report: Mapping[str, Any]) -> list[Path]:
    paths = [report_path]
    records: list[Mapping[str, Any]] = []
    outputs = report.get("outputs")
    if isinstance(outputs, list):
        records.extend(item for item in outputs if isinstance(item, Mapping))
    output = report.get("output")
    if isinstance(output, Mapping):
        records.append(output)
    if report.get("execution_status") == "completed":
        for record in records:
            if not _record_matches(record):
                raise ActionOutputLedgerTransactionError(
                    "published action output checksum does not match its action report"
                )
            raw_path = record.get("path")
            assert isinstance(raw_path, str)
            paths.append(Path(raw_path).expanduser().resolve(strict=True))
    return paths


def _recover_published_report(
    *,
    research_run: Path,
    action_id: str,
    action_type: str,
    action_version: str,
    cost_units: int,
    request_record: Mapping[str, Any],
    report_path: Path,
) -> dict[str, Any]:
    report = _load_json(report_path)
    checks = {
        "action_id": action_id,
        "action_type": action_type,
        "action_version": action_version,
        "cost_units": cost_units,
        "request": dict(request_record),
    }
    for key, expected in checks.items():
        if report.get(key) != expected:
            raise ActionOutputLedgerTransactionError(
                f"published action report conflicts with transaction binding: {key}"
            )
    status = report.get("execution_status")
    if status not in {"completed", "failed"}:
        raise ActionOutputLedgerTransactionError(
            "published action report has unsupported execution_status"
        )
    artifact_paths = _published_artifact_paths(report_path, report)
    summary = (
        "Recovered checksum-bound published action output after an interrupted "
        "output-to-ledger commit."
    )
    if action_type == EXTERNAL_REQUIREMENT_ACTION_TYPE:
        if status != "completed":
            raise ActionOutputLedgerTransactionError(
                "external-data requirement recovery requires a completed report"
            )
        stop_reason = report.get("stop_reason")
        if stop_reason != EXTERNAL_REQUIREMENT_STOP_REASON:
            raise ActionOutputLedgerTransactionError(
                "external-data requirement report has an unexpected stop reason"
            )
        return append_action_and_stop(
            research_run,
            action_id=action_id,
            action_type=action_type,
            status=status,
            summary=summary,
            cost_units=cost_units,
            reason_code=stop_reason,
            stop_summary=(
                "Recovered the checksum-bound external-evidence requirement and "
                "terminal stop after an interrupted ledger commit."
            ),
            artifact_paths=artifact_paths,
        )
    return append_action(
        research_run,
        action_id=action_id,
        action_type=action_type,
        status=status,
        summary=summary,
        cost_units=cost_units,
        artifact_paths=artifact_paths,
    )


def prepare_action_output_ledger_transaction(
    *,
    research_run: Path,
    request: Mapping[str, Any],
    request_path: Path,
    request_record: Mapping[str, Any],
    action_id: str,
    action_type: str,
    action_version: str,
    cost_units: int,
    state: Mapping[str, Any],
) -> dict[str, Any]:
    """Recover an interrupted commit if possible, then journal a new execution intent."""
    transaction_directory = _transaction_directory(research_run, action_id)
    journal_path = transaction_directory / JOURNAL_FILENAME
    action_directory = _action_directory(research_run, action_id)

    if transaction_directory.exists():
        if not transaction_directory.is_dir() or not journal_path.is_file():
            raise ActionOutputLedgerTransactionError(
                "action transaction directory exists without a valid journal"
            )
        journal = _load_json(journal_path)
        _validate_journal_binding(
            journal,
            action_id=action_id,
            action_type=action_type,
            action_version=action_version,
            cost_units=cost_units,
            request_record=request_record,
            action_directory=action_directory,
        )
        actions = state.get("actions")
        if not isinstance(actions, list):
            raise ActionOutputLedgerTransactionError("research action state is malformed")
        matches = [item for item in actions if isinstance(item, Mapping) and item.get("action_id") == action_id]
        if len(matches) > 1:
            raise ActionOutputLedgerTransactionError(
                "research ledger contains duplicate action IDs during transaction recovery"
            )
        if matches:
            if matches[0].get("action_type") != action_type:
                raise ActionOutputLedgerTransactionError(
                    "ledgered transaction action type conflicts with the journal"
                )
            _write_phase(journal_path, journal, "ledger_committed")
            return {
                "recovered": True,
                "research_state": dict(state),
                "action_report": str(action_directory / ACTION_REPORT_FILENAME),
                "journal_path": str(journal_path),
            }

        report_path = action_directory / ACTION_REPORT_FILENAME
        if report_path.is_file():
            _write_phase(journal_path, journal, "published")
            recovered_state = _recover_published_report(
                research_run=research_run,
                action_id=action_id,
                action_type=action_type,
                action_version=action_version,
                cost_units=cost_units,
                request_record=request_record,
                report_path=report_path,
            )
            _write_phase(journal_path, journal, "ledger_committed")
            return {
                "recovered": True,
                "research_state": recovered_state,
                "action_report": str(report_path),
                "journal_path": str(journal_path),
            }

        phase = journal.get("phase")
        if action_directory.exists():
            raise ActionOutputLedgerTransactionError(
                "interrupted action directory exists without a checksum-bound action report"
            )
        if phase == "journaled" and action_type == AUDIT_ACTION_TYPE:
            _restore_audit_snapshot(journal)
        elif phase not in {"staged", "journaled"}:
            raise ActionOutputLedgerTransactionError(
                f"cannot recover action transaction from phase {phase!r}"
            )
        shutil.rmtree(transaction_directory)

    transaction_directory.mkdir(parents=True, exist_ok=False)
    journal: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "action_id": action_id,
        "action_type": action_type,
        "action_version": action_version,
        "cost_units": cost_units,
        "action_directory": str(action_directory),
        "request": dict(request_record),
        "phase": "staged",
        "created_at_utc": _utc_now(),
        "updated_at_utc": _utc_now(),
    }
    _atomic_write_json(journal_path, journal)
    if action_type == AUDIT_ACTION_TYPE:
        _snapshot_audit_run(
            journal=journal,
            transaction_directory=transaction_directory,
            request=request,
            request_path=request_path,
            research_run=research_run,
        )
    _write_phase(journal_path, journal, "journaled")
    return {
        "recovered": False,
        "journal_path": str(journal_path),
        "action_report": str(action_directory / ACTION_REPORT_FILENAME),
    }


def mark_action_output_ledger_committed(
    *,
    research_run: Path,
    action_id: str,
    action_type: str,
    state: Mapping[str, Any],
) -> None:
    journal_path = _journal_path(research_run, action_id)
    journal = _load_json(journal_path)
    actions = state.get("actions")
    if not isinstance(actions, list):
        raise ActionOutputLedgerTransactionError("post-execution action state is malformed")
    matches = [item for item in actions if isinstance(item, Mapping) and item.get("action_id") == action_id]
    if len(matches) != 1 or matches[0].get("action_type") != action_type:
        raise ActionOutputLedgerTransactionError(
            "transaction cannot mark ledger_committed without one matching ledger action"
        )
    _write_phase(journal_path, journal, "ledger_committed")


def cleanup_action_output_ledger_transaction(
    *, research_run: Path, action_id: str
) -> None:
    transaction_directory = _transaction_directory(research_run, action_id)
    journal_path = transaction_directory / JOURNAL_FILENAME
    if not journal_path.is_file():
        raise ActionOutputLedgerTransactionError(
            "transaction cleanup requires an existing journal"
        )
    journal = _load_json(journal_path)
    if journal.get("phase") != "ledger_committed":
        raise ActionOutputLedgerTransactionError(
            "transaction cleanup is allowed only after ledger commit"
        )
    shutil.rmtree(transaction_directory)
    root = research_run / TRANSACTION_DIRECTORY
    try:
        root.rmdir()
    except OSError:
        pass


__all__ = [
    "ActionOutputLedgerTransactionError",
    "cleanup_action_output_ledger_transaction",
    "mark_action_output_ledger_committed",
    "prepare_action_output_ledger_transaction",
]
