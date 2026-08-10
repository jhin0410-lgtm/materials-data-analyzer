"""Immutable state kernel for bounded autonomous materials research loops."""

from __future__ import annotations

import errno
import hashlib
import json
import os
import tempfile
import time
from collections.abc import Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from platform_core.output_safety import transactional_output_directory

SCHEMA_VERSION = "1.0"
OBJECTIVE_FILENAME = "research_objective.json"
LEDGER_FILENAME = "research_ledger.jsonl"
STATE_FILENAME = "research_state.json"
LOCK_FILENAME = ".research_ledger.lock"

_ALLOWED_ACTION_STATUSES = {"completed", "failed", "rejected"}
_REQUIRED_OBJECTIVE_KEYS = {
    "schema_version",
    "research_id",
    "question",
    "metrics",
    "constraints",
    "budget",
    "stop_rules",
}
_ALLOWED_OBJECTIVE_KEYS = _REQUIRED_OBJECTIVE_KEYS | {"metadata"}
_REQUIRED_METRIC_KEYS = {"primary", "secondary"}
_REQUIRED_BUDGET_KEYS = {"maximum_actions", "maximum_cost_units"}
_WINDOWS_LOCK_RETRY_ERRNOS = {errno.EACCES, errno.EAGAIN, errno.EDEADLK}
_WINDOWS_LOCK_RETRY_SECONDS = 0.05


class ResearchLoopError(ValueError):
    """Raised when research-loop evidence or state violates its contract."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ResearchLoopError(f"duplicate JSON key is not allowed: {key}")
        result[key] = value
    return result


def _load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle, object_pairs_hook=_reject_duplicate_pairs)
    except json.JSONDecodeError as exc:
        raise ResearchLoopError(f"invalid JSON in {path}: {exc}") from exc


def _require_nonempty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ResearchLoopError(f"{field} must be a non-empty string")
    return value.strip()


def _require_string_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list):
        raise ResearchLoopError(f"{field} must be a JSON array")
    result = [_require_nonempty_string(item, f"{field} item") for item in value]
    if len(set(result)) != len(result):
        raise ResearchLoopError(f"{field} must not contain duplicate values")
    return result


def _require_exact_keys(
    value: Any,
    *,
    required: set[str],
    allowed: set[str],
    field: str,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ResearchLoopError(f"{field} must be a JSON object")
    keys = set(value)
    missing = sorted(required - keys)
    unknown = sorted(keys - allowed)
    if missing:
        raise ResearchLoopError(f"{field} is missing required keys: {', '.join(missing)}")
    if unknown:
        raise ResearchLoopError(f"{field} has unknown keys: {', '.join(unknown)}")
    return value


def validate_objective(value: Any) -> dict[str, Any]:
    """Validate and normalize the versioned research-objective contract."""
    objective = _require_exact_keys(
        value,
        required=_REQUIRED_OBJECTIVE_KEYS,
        allowed=_ALLOWED_OBJECTIVE_KEYS,
        field="research objective",
    )
    if objective["schema_version"] != SCHEMA_VERSION:
        raise ResearchLoopError(
            f"unsupported research objective schema_version: {objective['schema_version']!r}"
        )

    metrics = _require_exact_keys(
        objective["metrics"],
        required=_REQUIRED_METRIC_KEYS,
        allowed=_REQUIRED_METRIC_KEYS,
        field="metrics",
    )
    budget = _require_exact_keys(
        objective["budget"],
        required=_REQUIRED_BUDGET_KEYS,
        allowed=_REQUIRED_BUDGET_KEYS,
        field="budget",
    )
    maximum_actions = budget["maximum_actions"]
    maximum_cost_units = budget["maximum_cost_units"]
    if isinstance(maximum_actions, bool) or not isinstance(maximum_actions, int):
        raise ResearchLoopError("budget.maximum_actions must be an integer")
    if maximum_actions <= 0:
        raise ResearchLoopError("budget.maximum_actions must be greater than zero")
    if isinstance(maximum_cost_units, bool) or not isinstance(maximum_cost_units, int):
        raise ResearchLoopError("budget.maximum_cost_units must be an integer")
    if maximum_cost_units < 0:
        raise ResearchLoopError("budget.maximum_cost_units must be non-negative")

    normalized: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "research_id": _require_nonempty_string(objective["research_id"], "research_id"),
        "question": _require_nonempty_string(objective["question"], "question"),
        "metrics": {
            "primary": _require_nonempty_string(metrics["primary"], "metrics.primary"),
            "secondary": _require_string_list(metrics["secondary"], "metrics.secondary"),
        },
        "constraints": _require_string_list(objective["constraints"], "constraints"),
        "budget": {
            "maximum_actions": maximum_actions,
            "maximum_cost_units": maximum_cost_units,
        },
        "stop_rules": _require_string_list(objective["stop_rules"], "stop_rules"),
    }
    if "metadata" in objective:
        if not isinstance(objective["metadata"], dict):
            raise ResearchLoopError("metadata must be a JSON object when provided")
        normalized["metadata"] = objective["metadata"]
    return normalized


def _event_hash(event_without_hash: Mapping[str, Any]) -> str:
    return _sha256_bytes(_canonical_json(event_without_hash).encode("utf-8"))


def _build_event(
    *,
    sequence: int,
    event_type: str,
    payload: Mapping[str, Any],
    previous_event_hash: str | None,
    recorded_at_utc: str | None = None,
) -> dict[str, Any]:
    event_without_hash: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "sequence": sequence,
        "event_type": event_type,
        "recorded_at_utc": recorded_at_utc or _utc_now(),
        "previous_event_hash": previous_event_hash,
        "payload": dict(payload),
    }
    return {**event_without_hash, "event_hash": _event_hash(event_without_hash)}


def _serialize_ledger(events: Sequence[Mapping[str, Any]]) -> str:
    return "".join(_canonical_json(event) + "\n" for event in events)


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def _write_json(path: Path, value: Any) -> None:
    _atomic_write_text(
        path,
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
    )


def _read_ledger(run_directory: Path) -> list[dict[str, Any]]:
    ledger_path = run_directory / LEDGER_FILENAME
    if not ledger_path.is_file():
        raise FileNotFoundError(f"research ledger not found: {ledger_path}")
    events: list[dict[str, Any]] = []
    with ledger_path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            if not raw_line.strip():
                raise ResearchLoopError(
                    f"blank ledger line is not allowed: {ledger_path}:{line_number}"
                )
            try:
                event = json.loads(raw_line, object_pairs_hook=_reject_duplicate_pairs)
            except json.JSONDecodeError as exc:
                raise ResearchLoopError(
                    f"invalid ledger JSON at {ledger_path}:{line_number}: {exc}"
                ) from exc
            if not isinstance(event, dict):
                raise ResearchLoopError(
                    f"ledger entry must be a JSON object: {ledger_path}:{line_number}"
                )
            events.append(event)
    if not events:
        raise ResearchLoopError("research ledger must contain at least one event")
    return events


def _verify_events(events: Sequence[Mapping[str, Any]]) -> None:
    previous_hash: str | None = None
    for expected_sequence, event in enumerate(events, start=1):
        required = {
            "schema_version",
            "sequence",
            "event_type",
            "recorded_at_utc",
            "previous_event_hash",
            "payload",
            "event_hash",
        }
        if set(event) != required:
            raise ResearchLoopError(
                f"ledger event {expected_sequence} has an invalid field set"
            )
        if event["schema_version"] != SCHEMA_VERSION:
            raise ResearchLoopError(
                f"ledger event {expected_sequence} has unsupported schema_version"
            )
        if event["sequence"] != expected_sequence:
            raise ResearchLoopError(
                "ledger sequence mismatch: "
                f"expected {expected_sequence}, got {event['sequence']!r}"
            )
        if event["previous_event_hash"] != previous_hash:
            raise ResearchLoopError(
                f"ledger hash-chain mismatch at sequence {expected_sequence}"
            )
        if not isinstance(event["payload"], dict):
            raise ResearchLoopError(
                f"ledger payload must be an object at sequence {expected_sequence}"
            )
        without_hash = {key: event[key] for key in event if key != "event_hash"}
        expected_hash = _event_hash(without_hash)
        if event["event_hash"] != expected_hash:
            raise ResearchLoopError(
                f"ledger event hash mismatch at sequence {expected_sequence}"
            )
        previous_hash = expected_hash


def _event_ids(
    events: Iterable[Mapping[str, Any]], event_type: str, id_key: str
) -> set[str]:
    return {
        str(event["payload"][id_key])
        for event in events
        if event["event_type"] == event_type
    }


def _reconstruct_state(
    events: Sequence[Mapping[str, Any]], ledger_sha256: str
) -> dict[str, Any]:
    _verify_events(events)
    first = events[0]
    if first["event_type"] != "objective_registered":
        raise ResearchLoopError(
            "the first ledger event must register the research objective"
        )
    objective = validate_objective(first["payload"]["objective"])

    hypotheses: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []
    stop_event: dict[str, Any] | None = None
    for event in events[1:]:
        event_type = event["event_type"]
        payload = dict(event["payload"])
        if event_type == "hypothesis_registered":
            hypotheses.append(payload)
        elif event_type == "evidence_registered":
            evidence.append(payload)
        elif event_type == "action_recorded":
            actions.append(payload)
        elif event_type == "research_stopped":
            if stop_event is not None:
                raise ResearchLoopError("research may be stopped only once")
            stop_event = payload
        else:
            raise ResearchLoopError(f"unknown ledger event_type: {event_type}")

    action_cost_used = sum(int(action["cost_units"]) for action in actions)
    maximum_actions = int(objective["budget"]["maximum_actions"])
    maximum_cost_units = int(objective["budget"]["maximum_cost_units"])
    return {
        "schema_version": SCHEMA_VERSION,
        "research_id": objective["research_id"],
        "question": objective["question"],
        "status": "stopped" if stop_event is not None else "active",
        "metrics": objective["metrics"],
        "constraints": objective["constraints"],
        "stop_rules": objective["stop_rules"],
        "budget": {
            "maximum_actions": maximum_actions,
            "actions_used": len(actions),
            "actions_remaining": maximum_actions - len(actions),
            "maximum_cost_units": maximum_cost_units,
            "cost_units_used": action_cost_used,
            "cost_units_remaining": maximum_cost_units - action_cost_used,
        },
        "hypotheses": hypotheses,
        "evidence": evidence,
        "actions": actions,
        "stop": stop_event,
        "event_count": len(events),
        "latest_event_hash": events[-1]["event_hash"],
        "ledger_sha256": ledger_sha256,
    }


def _write_run_state(
    run_directory: Path, events: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    ledger_text = _serialize_ledger(events)
    ledger_sha256 = _sha256_bytes(ledger_text.encode("utf-8"))
    state = _reconstruct_state(events, ledger_sha256)
    _atomic_write_text(run_directory / LEDGER_FILENAME, ledger_text)
    _write_json(run_directory / STATE_FILENAME, state)
    return state


def initialize_research_loop(
    objective_path: str | Path,
    output_directory: str | Path,
) -> dict[str, Any]:
    """Create a new research run with an immutable objective-registration event."""
    source_path = Path(objective_path).expanduser().resolve(strict=True)
    objective = validate_objective(_load_json(source_path))
    objective_text = (
        json.dumps(objective, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    )
    objective_sha256 = _sha256_bytes(objective_text.encode("utf-8"))
    event = _build_event(
        sequence=1,
        event_type="objective_registered",
        previous_event_hash=None,
        payload={
            "objective": objective,
            "objective_sha256": objective_sha256,
        },
    )
    with transactional_output_directory(
        output_directory,
        protected_paths=(source_path,),
        recognized_markers=(OBJECTIVE_FILENAME, LEDGER_FILENAME, STATE_FILENAME),
    ) as staging:
        _atomic_write_text(staging / OBJECTIVE_FILENAME, objective_text)
        state = _write_run_state(staging, [event])
    return state


def _resolve_run_path(run_directory: str | Path) -> Path:
    run_path = Path(run_directory).expanduser().resolve(strict=True)
    if not run_path.is_dir():
        raise NotADirectoryError(f"research run is not a directory: {run_path}")
    return run_path


def _seed_lock_file(handle: Any) -> None:
    handle.seek(0, os.SEEK_END)
    if handle.tell() == 0:
        handle.write(b"\0")
        handle.flush()
        os.fsync(handle.fileno())
    handle.seek(0)


def _acquire_windows_lock(handle: Any) -> None:
    import msvcrt

    handle.seek(0)
    while True:
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            return
        except OSError as exc:
            if exc.errno not in _WINDOWS_LOCK_RETRY_ERRNOS:
                raise
            time.sleep(_WINDOWS_LOCK_RETRY_SECONDS)


def _release_windows_lock(handle: Any) -> None:
    import msvcrt

    handle.seek(0)
    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


@contextmanager
def _exclusive_ledger_lock(run_directory: Path) -> Iterator[None]:
    """Serialize ledger/state transactions across processes without stale sentinels."""
    lock_path = run_directory / LOCK_FILENAME
    with lock_path.open("a+b") as handle:
        _seed_lock_file(handle)
        if os.name == "nt":
            _acquire_windows_lock(handle)
            try:
                yield
            finally:
                _release_windows_lock(handle)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _load_verified_run(
    run_directory: str | Path,
) -> tuple[Path, list[dict[str, Any]], dict[str, Any]]:
    run_path = _resolve_run_path(run_directory)
    events = _read_ledger(run_path)
    ledger_text = _serialize_ledger(events)
    state = _reconstruct_state(
        events, _sha256_bytes(ledger_text.encode("utf-8"))
    )
    snapshot_path = run_path / STATE_FILENAME
    if not snapshot_path.is_file():
        raise FileNotFoundError(
            f"research state snapshot not found: {snapshot_path}"
        )
    snapshot = _load_json(snapshot_path)
    if snapshot != state:
        raise ResearchLoopError(
            "research state snapshot does not match the immutable ledger reconstruction"
        )
    objective_path = run_path / OBJECTIVE_FILENAME
    if not objective_path.is_file():
        raise FileNotFoundError(
            f"research objective copy not found: {objective_path}"
        )
    objective = validate_objective(_load_json(objective_path))
    registered = events[0]["payload"]
    expected_text = (
        json.dumps(objective, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    )
    if (
        _sha256_bytes(expected_text.encode("utf-8"))
        != registered["objective_sha256"]
    ):
        raise ResearchLoopError(
            "research objective copy does not match the registered hash"
        )
    return run_path, events, state


@contextmanager
def _locked_verified_run(
    run_directory: str | Path,
) -> Iterator[tuple[Path, list[dict[str, Any]], dict[str, Any]]]:
    run_path = _resolve_run_path(run_directory)
    with _exclusive_ledger_lock(run_path):
        yield _load_verified_run(run_path)


def _append_events_locked(
    run_path: Path,
    events: Sequence[Mapping[str, Any]],
    state: Mapping[str, Any],
    additions: Sequence[tuple[str, Mapping[str, Any]]],
) -> dict[str, Any]:
    if state["status"] != "active":
        raise ResearchLoopError(
            "research run is stopped and cannot accept new events"
        )
    updated = [dict(event) for event in events]
    previous_hash = updated[-1]["event_hash"]
    for event_type, payload in additions:
        event = _build_event(
            sequence=len(updated) + 1,
            event_type=event_type,
            payload=payload,
            previous_event_hash=previous_hash,
        )
        updated.append(event)
        previous_hash = event["event_hash"]
    return _write_run_state(run_path, updated)


def _append_event(
    run_directory: str | Path,
    *,
    event_type: str,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    with _locked_verified_run(run_directory) as (run_path, events, state):
        return _append_events_locked(
            run_path,
            events,
            state,
            [(event_type, payload)],
        )


def append_hypothesis(
    run_directory: str | Path,
    *,
    hypothesis_id: str,
    statement: str,
    rationale: str,
) -> dict[str, Any]:
    normalized_id = _require_nonempty_string(hypothesis_id, "hypothesis_id")
    normalized_statement = _require_nonempty_string(statement, "statement")
    normalized_rationale = _require_nonempty_string(rationale, "rationale")
    with _locked_verified_run(run_directory) as (run_path, events, state):
        if state["status"] != "active":
            raise ResearchLoopError(
                "research run is stopped and cannot accept hypotheses"
            )
        if normalized_id in _event_ids(
            events, "hypothesis_registered", "hypothesis_id"
        ):
            raise ResearchLoopError(f"duplicate hypothesis_id: {normalized_id}")
        return _append_events_locked(
            run_path,
            events,
            state,
            [
                (
                    "hypothesis_registered",
                    {
                        "hypothesis_id": normalized_id,
                        "statement": normalized_statement,
                        "rationale": normalized_rationale,
                        "status": "proposed",
                    },
                )
            ],
        )


def append_evidence(
    run_directory: str | Path,
    *,
    evidence_id: str,
    evidence_type: str,
    source_path: str | Path,
    summary: str,
) -> dict[str, Any]:
    normalized_id = _require_nonempty_string(evidence_id, "evidence_id")
    normalized_type = _require_nonempty_string(evidence_type, "evidence_type")
    normalized_summary = _require_nonempty_string(summary, "summary")
    evidence_path = Path(source_path).expanduser().resolve(strict=True)
    if not evidence_path.is_file():
        raise ResearchLoopError(
            f"evidence source must be a regular file: {evidence_path}"
        )
    with _locked_verified_run(run_directory) as (run_path, events, state):
        if state["status"] != "active":
            raise ResearchLoopError(
                "research run is stopped and cannot accept evidence"
            )
        if normalized_id in _event_ids(
            events, "evidence_registered", "evidence_id"
        ):
            raise ResearchLoopError(f"duplicate evidence_id: {normalized_id}")
        return _append_events_locked(
            run_path,
            events,
            state,
            [
                (
                    "evidence_registered",
                    {
                        "evidence_id": normalized_id,
                        "evidence_type": normalized_type,
                        "source_path": str(evidence_path),
                        "source_sha256": _sha256_file(evidence_path),
                        "source_bytes": evidence_path.stat().st_size,
                        "summary": normalized_summary,
                    },
                )
            ],
        )


def _validate_action_inputs(
    *,
    action_id: str,
    action_type: str,
    status: str,
    summary: str,
    cost_units: int,
) -> tuple[str, str, str]:
    normalized_id = _require_nonempty_string(action_id, "action_id")
    normalized_type = _require_nonempty_string(action_type, "action_type")
    normalized_summary = _require_nonempty_string(summary, "summary")
    if status not in _ALLOWED_ACTION_STATUSES:
        raise ResearchLoopError(
            "action status must be one of: "
            + ", ".join(sorted(_ALLOWED_ACTION_STATUSES))
        )
    if (
        isinstance(cost_units, bool)
        or not isinstance(cost_units, int)
        or cost_units < 0
    ):
        raise ResearchLoopError("cost_units must be a non-negative integer")
    return normalized_id, normalized_type, normalized_summary


def _action_artifacts(
    artifact_paths: Sequence[str | Path],
) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    for raw_path in artifact_paths:
        artifact_path = Path(raw_path).expanduser().resolve(strict=True)
        if not artifact_path.is_file():
            raise ResearchLoopError(
                f"action artifact must be a regular file: {artifact_path}"
            )
        artifacts.append(
            {
                "path": str(artifact_path),
                "sha256": _sha256_file(artifact_path),
                "bytes": artifact_path.stat().st_size,
            }
        )
    return artifacts


def _validate_action_against_state(
    *,
    events: Sequence[Mapping[str, Any]],
    state: Mapping[str, Any],
    action_id: str,
    cost_units: int,
) -> None:
    if state["status"] != "active":
        raise ResearchLoopError(
            "research run is stopped and cannot accept actions"
        )
    if action_id in _event_ids(events, "action_recorded", "action_id"):
        raise ResearchLoopError(f"duplicate action_id: {action_id}")
    budget = state["budget"]
    if budget["actions_remaining"] <= 0:
        raise ResearchLoopError("research action budget is exhausted")
    if cost_units > budget["cost_units_remaining"]:
        raise ResearchLoopError("research cost budget would be exceeded")


def append_action(
    run_directory: str | Path,
    *,
    action_id: str,
    action_type: str,
    status: str,
    summary: str,
    cost_units: int,
    artifact_paths: Sequence[str | Path] = (),
) -> dict[str, Any]:
    normalized_id, normalized_type, normalized_summary = _validate_action_inputs(
        action_id=action_id,
        action_type=action_type,
        status=status,
        summary=summary,
        cost_units=cost_units,
    )
    with _locked_verified_run(run_directory) as (run_path, events, state):
        _validate_action_against_state(
            events=events,
            state=state,
            action_id=normalized_id,
            cost_units=cost_units,
        )
        artifacts = _action_artifacts(artifact_paths)
        return _append_events_locked(
            run_path,
            events,
            state,
            [
                (
                    "action_recorded",
                    {
                        "action_id": normalized_id,
                        "action_type": normalized_type,
                        "status": status,
                        "summary": normalized_summary,
                        "cost_units": cost_units,
                        "artifacts": artifacts,
                    },
                )
            ],
        )


def append_action_and_stop(
    run_directory: str | Path,
    *,
    action_id: str,
    action_type: str,
    status: str,
    summary: str,
    cost_units: int,
    reason_code: str,
    stop_summary: str,
    artifact_paths: Sequence[str | Path] = (),
) -> dict[str, Any]:
    """Atomically record one action and the terminal stop event it requires."""
    normalized_id, normalized_type, normalized_summary = _validate_action_inputs(
        action_id=action_id,
        action_type=action_type,
        status=status,
        summary=summary,
        cost_units=cost_units,
    )
    normalized_reason = _require_nonempty_string(reason_code, "reason_code")
    normalized_stop_summary = _require_nonempty_string(stop_summary, "stop_summary")
    with _locked_verified_run(run_directory) as (run_path, events, state):
        _validate_action_against_state(
            events=events,
            state=state,
            action_id=normalized_id,
            cost_units=cost_units,
        )
        artifacts = _action_artifacts(artifact_paths)
        return _append_events_locked(
            run_path,
            events,
            state,
            [
                (
                    "action_recorded",
                    {
                        "action_id": normalized_id,
                        "action_type": normalized_type,
                        "status": status,
                        "summary": normalized_summary,
                        "cost_units": cost_units,
                        "artifacts": artifacts,
                    },
                ),
                (
                    "research_stopped",
                    {
                        "reason_code": normalized_reason,
                        "summary": normalized_stop_summary,
                    },
                ),
            ],
        )


def append_stop(
    run_directory: str | Path,
    *,
    reason_code: str,
    summary: str,
) -> dict[str, Any]:
    normalized_reason = _require_nonempty_string(reason_code, "reason_code")
    normalized_summary = _require_nonempty_string(summary, "summary")
    return _append_event(
        run_directory,
        event_type="research_stopped",
        payload={
            "reason_code": normalized_reason,
            "summary": normalized_summary,
        },
    )


def load_research_state(run_directory: str | Path) -> dict[str, Any]:
    """Return a lock-consistent state reconstructed from the immutable ledger."""
    with _locked_verified_run(run_directory) as (_, _, state):
        return state


def verify_research_loop(run_directory: str | Path) -> dict[str, Any]:
    """Verify ledger chaining, objective binding, and snapshot reconstruction."""
    with _locked_verified_run(run_directory) as (run_path, events, state):
        return {
            "valid": True,
            "run_directory": str(run_path),
            "research_id": state["research_id"],
            "status": state["status"],
            "event_count": len(events),
            "latest_event_hash": state["latest_event_hash"],
            "ledger_sha256": state["ledger_sha256"],
        }
