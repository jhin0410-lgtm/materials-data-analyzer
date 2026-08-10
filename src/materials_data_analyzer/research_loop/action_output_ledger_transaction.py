"""Recoverable output-to-ledger transaction journal for authorized NASA actions.

The transaction is intentionally owned by the common authorized execution boundary.
The same persistent research-ledger advisory lock is held for prepare -> typed
execution -> pinned verification -> cleanup. Existing typed executors keep using
their normal kernel helpers; nested acquisitions in the owning context reuse the
already-held descriptor-bound lock rather than creating a second lock domain.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping

from . import kernel as _kernel
from .action_registry import describe_action, load_action_registry
from .kernel import ResearchLoopError, append_action, append_action_and_stop

SCHEMA_VERSION = "1.0"
TRANSACTION_DIRECTORY = ".action_output_ledger_transactions"
JOURNAL_FILENAME = "journal.json"
ACTION_REPORT_FILENAME = "action_result.json"
EXTERNAL_REQUIREMENT_ACTION_TYPE = "external_data_requirement_generation"
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


_OWNED_LEDGER_LOCKS: ContextVar[frozenset[str]] = ContextVar(
    "owned_research_ledger_locks", default=frozenset()
)
_ORIGINAL_LOCK_EXISTING_LEDGER = _kernel._lock_existing_ledger


@contextmanager
def _reentrant_lock_existing_ledger(run_directory: Path) -> Iterator[None]:
    """Reuse the kernel's existing advisory lock when this context already owns it."""
    key = os.path.normcase(str(run_directory.resolve()))
    owned = _OWNED_LEDGER_LOCKS.get()
    if key in owned:
        yield
        return
    with _ORIGINAL_LOCK_EXISTING_LEDGER(run_directory):
        token = _OWNED_LEDGER_LOCKS.set(owned | {key})
        try:
            yield
        finally:
            _OWNED_LEDGER_LOCKS.reset(token)


# Extend the existing kernel lock rather than introducing a second advisory lock.
# Both _exclusive_ledger_lock() and read-side _load_consistent_read() resolve this
# module global at call time, so nested executor reads/writes stay in one lock scope.
_kernel._lock_existing_ledger = _reentrant_lock_existing_ledger


@contextmanager
def shared_research_ledger_transaction_lock(
    research_run: str | Path,
) -> Iterator[Path]:
    """Hold the kernel's persistent ledger lock across output publication and commit."""
    run = Path(research_run).expanduser().resolve(strict=True)
    if not run.is_dir():
        raise ActionOutputLedgerTransactionError(
            f"research transaction run is not a directory: {run}"
        )
    with _kernel._exclusive_ledger_lock(run):
        yield run


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
    return research_run / TRANSACTION_DIRECTORY / digest


def _journal_path(research_run: Path, action_id: str) -> Path:
    return _transaction_directory(research_run, action_id) / JOURNAL_FILENAME


def _ensure_within(path: Path, root: Path, *, message: str) -> None:
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ActionOutputLedgerTransactionError(message) from exc


def _action_directory(research_run: Path, action_id: str) -> Path:
    actions_root = (research_run / "actions").resolve(strict=False)
    _ensure_within(
        actions_root,
        research_run,
        message="research actions directory resolves outside the research run",
    )
    candidate = (actions_root / action_id).resolve(strict=False)
    _ensure_within(
        candidate,
        actions_root,
        message="action transaction path escapes the research actions directory",
    )
    return candidate


def _safe_child(root: Path, relative: str) -> Path:
    root_resolved = root.resolve(strict=True)
    candidate = (root_resolved / relative).resolve(strict=False)
    _ensure_within(
        candidate,
        root_resolved,
        message=f"transaction path escapes its declared root: {relative}",
    )
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
    if any(char not in "0123456789abcdef" for char in digest):
        return False
    try:
        current = _file_record(Path(raw_path))
    except (OSError, ResearchLoopError):
        return False
    return current == {
        "path": str(Path(raw_path).expanduser().resolve()),
        "bytes": size,
        "sha256": digest,
    }


def _write_phase(journal_path: Path, journal: dict[str, Any], phase: str) -> None:
    journal["phase"] = phase
    journal["updated_at_utc"] = _utc_now()
    _atomic_write_json(journal_path, journal)


def _remove_transaction_directory(research_run: Path, action_id: str) -> None:
    transaction_directory = _transaction_directory(research_run, action_id)
    shutil.rmtree(transaction_directory)
    root = research_run / TRANSACTION_DIRECTORY
    try:
        root.rmdir()
    except OSError:
        pass


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
    if (
        analysis_run == research_run
        or analysis_run in research_run.parents
        or research_run in analysis_run.parents
    ):
        raise ActionOutputLedgerTransactionError(
            "audit transaction requires non-overlapping analysis and research runs"
        )

    immutable: list[dict[str, Any]] = []
    for relative in _AUDIT_IMMUTABLE_RELATIVE_PATHS:
        target = _safe_child(analysis_run, relative)
        immutable.append({"relative_path": relative, **_file_record(target)})

    backup_root = transaction_directory / "audit_backup"
    mutable: list[dict[str, Any]] = []
    for index, relative in enumerate(_AUDIT_MUTABLE_RELATIVE_PATHS):
        target = _safe_child(analysis_run, relative)
        if not target.exists():
            mutable.append(
                {
                    "relative_path": relative,
                    "path": str(target),
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
        # Windows requires a writable descriptor for os.fsync().
        with backup.open("r+b") as handle:
            handle.flush()
            os.fsync(handle.fileno())
        mutable.append(
            {
                "relative_path": relative,
                "path": str(target),
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
    analysis_raw = snapshot.get("analysis_run")
    immutable = snapshot.get("immutable")
    mutable = snapshot.get("mutable")
    if (
        not isinstance(analysis_raw, str)
        or not isinstance(immutable, list)
        or not isinstance(mutable, list)
    ):
        raise ActionOutputLedgerTransactionError("audit recovery snapshot is malformed")
    analysis_run = Path(analysis_raw).expanduser().resolve(strict=True)
    for record in immutable:
        if not isinstance(record, Mapping) or not _record_matches(record):
            raise ActionOutputLedgerTransactionError(
                "audit immutable input changed during an interrupted transaction"
            )
        raw_path = record.get("path")
        if not isinstance(raw_path, str):
            raise ActionOutputLedgerTransactionError("audit immutable path is malformed")
        _ensure_within(
            Path(raw_path).expanduser().resolve(strict=True),
            analysis_run,
            message="audit immutable recovery path escapes analysis_run",
        )
    for record in mutable:
        if not isinstance(record, Mapping):
            raise ActionOutputLedgerTransactionError("audit mutable snapshot is malformed")
        target_raw = record.get("path")
        existed = record.get("existed")
        if not isinstance(target_raw, str) or not isinstance(existed, bool):
            raise ActionOutputLedgerTransactionError("audit mutable snapshot is malformed")
        target = Path(target_raw).expanduser().resolve(strict=False)
        _ensure_within(
            target,
            analysis_run,
            message="audit mutable recovery path escapes analysis_run",
        )
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


def _validate_journal_identity(
    journal: Mapping[str, Any],
    *,
    action_id: str,
    action_type: str,
    request_record: Mapping[str, Any],
    action_directory: Path,
) -> None:
    expected = {
        "schema_version": SCHEMA_VERSION,
        "action_id": action_id,
        "action_type": action_type,
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
    _validate_journal_identity(
        journal,
        action_id=action_id,
        action_type=action_type,
        request_record=request_record,
        action_directory=action_directory,
    )
    if journal.get("action_version") != action_version:
        raise ActionOutputLedgerTransactionError(
            "existing action transaction journal conflicts on action_version"
        )
    if journal.get("cost_units") != cost_units:
        raise ActionOutputLedgerTransactionError(
            "existing action transaction journal conflicts on cost_units"
        )


def _validate_report_binding(
    report: Mapping[str, Any],
    *,
    action_id: str,
    action_type: str,
    action_version: str,
    cost_units: int,
    request_record: Mapping[str, Any],
) -> str:
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
    return str(status)


def _published_artifact_records(
    report_path: Path,
    report: Mapping[str, Any],
    *,
    action_type: str,
) -> list[dict[str, Any]]:
    action_directory = report_path.parent.resolve(strict=True)
    records: list[Mapping[str, Any]] = []
    outputs = report.get("outputs")
    if isinstance(outputs, list):
        records.extend(item for item in outputs if isinstance(item, Mapping))
    output = report.get("output")
    if isinstance(output, Mapping):
        records.append(output)

    artifacts = [_file_record(report_path)]
    if report.get("execution_status") != "completed":
        return artifacts

    audit_allowed: set[Path] | None = None
    if action_type == AUDIT_ACTION_TYPE:
        analysis_raw = report.get("analysis_run")
        if not isinstance(analysis_raw, str):
            raise ActionOutputLedgerTransactionError(
                "audit action report is missing analysis_run for output recovery"
            )
        analysis_run = Path(analysis_raw).expanduser().resolve(strict=True)
        audit_allowed = {
            _safe_child(analysis_run, relative)
            for relative in _AUDIT_MUTABLE_RELATIVE_PATHS
        }

    for record in records:
        if not _record_matches(record):
            raise ActionOutputLedgerTransactionError(
                "published action output checksum does not match its action report"
            )
        raw_path = record.get("path")
        if not isinstance(raw_path, str):
            raise ActionOutputLedgerTransactionError(
                "published action output path is malformed"
            )
        path = Path(raw_path).expanduser().resolve(strict=True)
        if audit_allowed is not None:
            if path not in audit_allowed:
                raise ActionOutputLedgerTransactionError(
                    "audit recovery output is outside the predeclared mutable output set"
                )
        else:
            _ensure_within(
                path,
                action_directory,
                message="published action output escapes the action directory",
            )
        artifacts.append(_file_record(path))
    return artifacts


def _published_artifact_paths(
    report_path: Path,
    report: Mapping[str, Any],
    *,
    action_type: str,
) -> list[Path]:
    return [
        Path(record["path"])
        for record in _published_artifact_records(
            report_path,
            report,
            action_type=action_type,
        )
    ]


def _validate_recovery_registry_contract(
    *,
    research_run: Path,
    request: Mapping[str, Any],
    request_path: Path,
    action_type: str,
    action_version: str,
    cost_units: int,
) -> dict[str, Any]:
    request_run = _resolve_request_path(
        request.get("research_run"), base=request_path.parent, field="research_run"
    )
    if request_run != research_run:
        raise ActionOutputLedgerTransactionError(
            "recovery request research_run does not match the transaction run"
        )
    repository_root = _resolve_request_path(
        request.get("repository_root"), base=request_path.parent, field="repository_root"
    )
    registry_path = _resolve_request_path(
        request.get("registry"), base=request_path.parent, field="registry"
    )
    expected_sha = request.get("expected_registry_sha256")
    if not isinstance(expected_sha, str):
        raise ActionOutputLedgerTransactionError(
            "recovery request expected_registry_sha256 is malformed"
        )
    try:
        registry = load_action_registry(registry_path, repository_root=repository_root)
        contract = describe_action(registry, action_type)
    except (OSError, ResearchLoopError, ValueError) as exc:
        raise ActionOutputLedgerTransactionError(
            "recovery execution registry could not be independently verified"
        ) from exc
    if registry.get("registry_sha256") != expected_sha:
        raise ActionOutputLedgerTransactionError(
            "recovery execution registry SHA-256 no longer matches the pinned request"
        )
    if contract.get("version") != action_version:
        raise ActionOutputLedgerTransactionError(
            "recovery action version no longer matches the execution registry"
        )
    if contract.get("cost_units") != cost_units:
        raise ActionOutputLedgerTransactionError(
            "recovery action cost no longer matches the execution registry"
        )
    if contract.get("availability") != "available":
        raise ActionOutputLedgerTransactionError(
            "recovery action is no longer marked available in its execution registry"
        )
    return registry


def _validate_ledger_action_matches_report(
    *,
    state: Mapping[str, Any],
    action: Mapping[str, Any],
    action_id: str,
    action_type: str,
    action_version: str,
    cost_units: int,
    request_record: Mapping[str, Any],
    report_path: Path,
) -> None:
    report = _load_json(report_path)
    status = _validate_report_binding(
        report,
        action_id=action_id,
        action_type=action_type,
        action_version=action_version,
        cost_units=cost_units,
        request_record=request_record,
    )
    expected_artifacts = _published_artifact_records(
        report_path,
        report,
        action_type=action_type,
    )
    checks = {
        "action_id": action_id,
        "action_type": action_type,
        "status": status,
        "cost_units": cost_units,
        "artifacts": expected_artifacts,
    }
    for key, expected in checks.items():
        if action.get(key) != expected:
            raise ActionOutputLedgerTransactionError(
                f"ledgered action conflicts with the recoverable transaction: {key}"
            )
    if action_type == EXTERNAL_REQUIREMENT_ACTION_TYPE:
        if status != "completed":
            raise ActionOutputLedgerTransactionError(
                "external-data requirement recovery requires a completed report"
            )
        if report.get("stop_reason") != EXTERNAL_REQUIREMENT_STOP_REASON:
            raise ActionOutputLedgerTransactionError(
                "external-data requirement report has an unexpected stop reason"
            )
        stop = state.get("stop")
        if not isinstance(stop, Mapping) or stop.get("reason_code") != EXTERNAL_REQUIREMENT_STOP_REASON:
            raise ActionOutputLedgerTransactionError(
                "external-data requirement ledger recovery is missing its terminal stop"
            )


def _verify_objective_copy_without_snapshot(
    research_run: Path,
    events: list[dict[str, Any]],
) -> None:
    objective_path = research_run / _kernel.OBJECTIVE_FILENAME
    if not objective_path.is_file():
        raise ActionOutputLedgerTransactionError(
            "research objective copy is missing during transaction recovery"
        )
    objective = _kernel.validate_objective(_kernel._load_json(objective_path))
    expected_text = (
        json.dumps(objective, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    )
    registered = events[0].get("payload")
    if not isinstance(registered, Mapping):
        raise ActionOutputLedgerTransactionError(
            "objective registration is malformed during transaction recovery"
        )
    if (
        _kernel._sha256_bytes(expected_text.encode("utf-8"))
        != registered.get("objective_sha256")
    ):
        raise ActionOutputLedgerTransactionError(
            "research objective copy does not match the registered hash during recovery"
        )


def _reconstruct_state_without_snapshot(research_run: Path) -> dict[str, Any]:
    events = _kernel._read_ledger(research_run)
    ledger_text = _kernel._serialize_ledger(events)
    state = _kernel._reconstruct_state(
        events,
        _kernel._sha256_bytes(ledger_text.encode("utf-8")),
    )
    _verify_objective_copy_without_snapshot(research_run, events)
    return state


def _matching_action(
    state: Mapping[str, Any], action_id: str
) -> Mapping[str, Any] | None:
    actions = state.get("actions")
    if not isinstance(actions, list):
        raise ActionOutputLedgerTransactionError("research action state is malformed")
    matches = [
        item
        for item in actions
        if isinstance(item, Mapping) and item.get("action_id") == action_id
    ]
    if len(matches) > 1:
        raise ActionOutputLedgerTransactionError(
            "research ledger contains duplicate action IDs during transaction recovery"
        )
    return matches[0] if matches else None


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
    status = _validate_report_binding(
        report,
        action_id=action_id,
        action_type=action_type,
        action_version=action_version,
        cost_units=cost_units,
        request_record=request_record,
    )
    artifact_paths = _published_artifact_paths(
        report_path,
        report,
        action_type=action_type,
    )
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


def recover_action_output_ledger_transaction_before_authorization(
    *,
    research_run: Path,
    request: Mapping[str, Any],
    request_path: Path,
    request_record: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Recover a prior authorized execution before the planner can advance past it.

    Journal creation happens only after successful authorization. Therefore an existing
    journal is evidence of a previously authorized attempt. Recovery still revalidates
    exact request bytes, the execution registry/version/cost, report checksums, output
    confinement, ledger artifacts, and (for the terminal action) the stop event.
    """
    action_id = request.get("action_id")
    action_type = request.get("action_type")
    if not isinstance(action_id, str) or not action_id.strip():
        raise ActionOutputLedgerTransactionError(
            "recovery request action_id must be a non-empty string"
        )
    if not isinstance(action_type, str) or not action_type.strip():
        raise ActionOutputLedgerTransactionError(
            "recovery request action_type must be a non-empty string"
        )
    transaction_directory = _transaction_directory(research_run, action_id)
    if not transaction_directory.exists():
        return None
    journal_path = transaction_directory / JOURNAL_FILENAME
    if not transaction_directory.is_dir() or not journal_path.is_file():
        raise ActionOutputLedgerTransactionError(
            "action transaction directory exists without a valid journal"
        )
    action_directory = _action_directory(research_run, action_id)
    journal = _load_json(journal_path)
    _validate_journal_identity(
        journal,
        action_id=action_id,
        action_type=action_type,
        request_record=request_record,
        action_directory=action_directory,
    )
    action_version = journal.get("action_version")
    cost_units = journal.get("cost_units")
    if not isinstance(action_version, str) or not action_version.strip():
        raise ActionOutputLedgerTransactionError(
            "transaction journal action_version is malformed"
        )
    if isinstance(cost_units, bool) or not isinstance(cost_units, int) or cost_units < 0:
        raise ActionOutputLedgerTransactionError(
            "transaction journal cost_units is malformed"
        )
    registry = _validate_recovery_registry_contract(
        research_run=research_run,
        request=request,
        request_path=request_path,
        action_type=action_type,
        action_version=action_version,
        cost_units=cost_units,
    )

    snapshot_repaired = False
    try:
        _, _, state = _kernel._load_verified_run(research_run)
    except (ResearchLoopError, FileNotFoundError) as original_error:
        reconstructed = _reconstruct_state_without_snapshot(research_run)
        action = _matching_action(reconstructed, action_id)
        report_path = action_directory / ACTION_REPORT_FILENAME
        if action is None or not report_path.is_file():
            raise ActionOutputLedgerTransactionError(
                "research state snapshot is inconsistent for reasons not proven by the pending transaction"
            ) from original_error
        _validate_ledger_action_matches_report(
            state=reconstructed,
            action=action,
            action_id=action_id,
            action_type=action_type,
            action_version=action_version,
            cost_units=cost_units,
            request_record=request_record,
            report_path=report_path,
        )
        _kernel._write_json(research_run / _kernel.STATE_FILENAME, reconstructed)
        state = reconstructed
        snapshot_repaired = True

    action = _matching_action(state, action_id)
    report_path = action_directory / ACTION_REPORT_FILENAME
    if action is not None:
        if not report_path.is_file():
            raise ActionOutputLedgerTransactionError(
                "ledgered transaction action is missing its checksum-bound action report"
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
        _write_phase(journal_path, journal, "ledger_committed")
        return {
            "recovered": True,
            "recovery_stage": "ledger_committed",
            "state_snapshot_repaired": snapshot_repaired,
            "research_state": dict(state),
            "action_report": str(report_path),
            "action_id": action_id,
            "action_type": action_type,
            "action_version": action_version,
            "cost_units": cost_units,
            "registry": registry,
        }

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
        action = _matching_action(recovered_state, action_id)
        if action is None:
            raise ActionOutputLedgerTransactionError(
                "published-output recovery did not create the expected ledger action"
            )
        _validate_ledger_action_matches_report(
            state=recovered_state,
            action=action,
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
            "recovery_stage": "published",
            "state_snapshot_repaired": False,
            "research_state": recovered_state,
            "action_report": str(report_path),
            "action_id": action_id,
            "action_type": action_type,
            "action_version": action_version,
            "cost_units": cost_units,
            "registry": registry,
        }

    if action_directory.exists():
        raise ActionOutputLedgerTransactionError(
            "interrupted action directory exists without a checksum-bound action report"
        )
    phase = journal.get("phase")
    if phase == "journaled" and action_type == AUDIT_ACTION_TYPE:
        _restore_audit_snapshot(journal)
    elif phase not in {"staged", "journaled"}:
        raise ActionOutputLedgerTransactionError(
            f"cannot recover action transaction from phase {phase!r}"
        )
    _remove_transaction_directory(research_run, action_id)
    return None


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
        action = _matching_action(state, action_id)
        if action is not None:
            report_path = action_directory / ACTION_REPORT_FILENAME
            if not report_path.is_file():
                raise ActionOutputLedgerTransactionError(
                    "ledgered transaction action is missing its checksum-bound action report"
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
            _write_phase(journal_path, journal, "ledger_committed")
            return {
                "recovered": True,
                "research_state": dict(state),
                "action_report": str(report_path),
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
        _remove_transaction_directory(research_run, action_id)

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
    action = _matching_action(state, action_id)
    if action is None or action.get("action_type") != action_type:
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
    _remove_transaction_directory(research_run, action_id)


__all__ = [
    "AUDIT_ACTION_TYPE",
    "EXTERNAL_REQUIREMENT_ACTION_TYPE",
    "EXTERNAL_REQUIREMENT_STOP_REASON",
    "ActionOutputLedgerTransactionError",
    "cleanup_action_output_ledger_transaction",
    "mark_action_output_ledger_committed",
    "prepare_action_output_ledger_transaction",
    "recover_action_output_ledger_transaction_before_authorization",
    "shared_research_ledger_transaction_lock",
]
