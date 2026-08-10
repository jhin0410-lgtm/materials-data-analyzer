from __future__ import annotations

import json
import multiprocessing
import os
import stat
from pathlib import Path
from queue import Empty
from typing import Any

import pytest

from materials_data_analyzer.research_loop import kernel


def _objective(*, maximum_actions: int, maximum_cost_units: int) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "research_id": "ledger-concurrency-test",
        "question": "Can concurrent research writers preserve one verified ledger?",
        "metrics": {"primary": "verified_ledger", "secondary": []},
        "constraints": ["fail_closed"],
        "budget": {
            "maximum_actions": maximum_actions,
            "maximum_cost_units": maximum_cost_units,
        },
        "stop_rules": ["manual_stop"],
    }


def _initialize_run(
    tmp_path: Path,
    *,
    maximum_actions: int,
    maximum_cost_units: int,
) -> Path:
    objective = tmp_path / "objective.json"
    objective.write_text(
        json.dumps(
            _objective(
                maximum_actions=maximum_actions,
                maximum_cost_units=maximum_cost_units,
            )
        ),
        encoding="utf-8",
    )
    run = tmp_path / "run"
    kernel.initialize_research_loop(objective, run)
    return run


def _append_action_worker(
    run: str,
    action_id: str,
    ready: Any,
    start: Any,
    results: Any,
) -> None:
    ready.set()
    if not start.wait(15):
        results.put(("error", action_id, "start_timeout"))
        return
    try:
        state = kernel.append_action(
            run,
            action_id=action_id,
            action_type="concurrency_probe",
            status="completed",
            summary="Cross-process ledger serialization probe.",
            cost_units=1,
        )
    except Exception as exc:  # pragma: no cover - executed in a child process
        results.put(("error", action_id, type(exc).__name__, str(exc)))
    else:
        results.put(("ok", action_id, state["ledger_sha256"]))


def _crash_while_holding_lock(run: str, acquired: Any) -> None:
    run_path = Path(run).resolve(strict=True)
    with kernel._exclusive_ledger_lock(run_path):
        acquired.set()
        os._exit(0)


def _run_two_writers(run: Path, first_id: str, second_id: str) -> list[tuple[Any, ...]]:
    context = multiprocessing.get_context("spawn")
    start = context.Event()
    ready_first = context.Event()
    ready_second = context.Event()
    results = context.Queue()
    processes = [
        context.Process(
            target=_append_action_worker,
            args=(str(run), first_id, ready_first, start, results),
        ),
        context.Process(
            target=_append_action_worker,
            args=(str(run), second_id, ready_second, start, results),
        ),
    ]
    for process in processes:
        process.start()
    assert ready_first.wait(20)
    assert ready_second.wait(20)
    start.set()
    for process in processes:
        process.join(30)
        assert process.exitcode == 0

    output: list[tuple[Any, ...]] = []
    for _ in processes:
        try:
            output.append(results.get(timeout=10))
        except Empty as exc:  # pragma: no cover - diagnostic failure path
            raise AssertionError("concurrent writer produced no result") from exc
    return output


def test_duplicate_action_id_is_serialized_across_processes(tmp_path: Path) -> None:
    run = _initialize_run(
        tmp_path,
        maximum_actions=2,
        maximum_cost_units=2,
    )

    results = _run_two_writers(run, "same-action", "same-action")

    assert sum(item[0] == "ok" for item in results) == 1
    failures = [item for item in results if item[0] == "error"]
    assert len(failures) == 1
    assert failures[0][2] == "ResearchLoopError"
    assert "duplicate action_id" in failures[0][3]
    state = kernel.load_research_state(run)
    assert [item["action_id"] for item in state["actions"]] == ["same-action"]
    assert state["budget"]["actions_used"] == 1
    assert state["budget"]["cost_units_used"] == 1
    assert state["event_count"] == 2
    assert kernel.verify_research_loop(run)["valid"] is True


def test_action_budget_is_serialized_across_processes(tmp_path: Path) -> None:
    run = _initialize_run(
        tmp_path,
        maximum_actions=1,
        maximum_cost_units=1,
    )

    results = _run_two_writers(run, "action-a", "action-b")

    assert sum(item[0] == "ok" for item in results) == 1
    failures = [item for item in results if item[0] == "error"]
    assert len(failures) == 1
    assert failures[0][2] == "ResearchLoopError"
    assert "budget" in failures[0][3]
    state = kernel.load_research_state(run)
    assert len(state["actions"]) == 1
    assert state["actions"][0]["action_id"] in {"action-a", "action-b"}
    assert state["budget"]["actions_remaining"] == 0
    assert state["budget"]["cost_units_remaining"] == 0
    assert state["event_count"] == 2
    assert kernel.verify_research_loop(run)["valid"] is True


def test_os_releases_ledger_lock_when_holder_process_dies(tmp_path: Path) -> None:
    run = _initialize_run(
        tmp_path,
        maximum_actions=1,
        maximum_cost_units=1,
    )
    context = multiprocessing.get_context("spawn")
    acquired = context.Event()
    process = context.Process(
        target=_crash_while_holding_lock,
        args=(str(run), acquired),
    )
    process.start()
    assert acquired.wait(20)
    process.join(20)
    assert process.exitcode == 0

    state = kernel.append_action(
        run,
        action_id="after-crash",
        action_type="lock_recovery_probe",
        status="completed",
        summary="The OS advisory lock was released after process termination.",
        cost_units=1,
    )

    assert [item["action_id"] for item in state["actions"]] == ["after-crash"]
    assert (run / kernel.LOCK_FILENAME).is_file()
    assert kernel.verify_research_loop(run)["valid"] is True


def test_read_only_lock_file_does_not_break_state_verification(tmp_path: Path) -> None:
    run = _initialize_run(
        tmp_path,
        maximum_actions=1,
        maximum_cost_units=1,
    )
    lock_path = run / kernel.LOCK_FILENAME
    original_mode = stat.S_IMODE(lock_path.stat().st_mode)
    lock_path.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    try:
        state = kernel.load_research_state(run)
        verification = kernel.verify_research_loop(run)
    finally:
        lock_path.chmod(original_mode)

    assert state["research_id"] == "ledger-concurrency-test"
    assert verification["valid"] is True
    assert verification["ledger_sha256"] == state["ledger_sha256"]


def test_legacy_read_without_lock_does_not_mutate_run(tmp_path: Path) -> None:
    run = _initialize_run(
        tmp_path,
        maximum_actions=1,
        maximum_cost_units=1,
    )
    lock_path = run / kernel.LOCK_FILENAME
    lock_path.unlink()

    state = kernel.load_research_state(run)
    verification = kernel.verify_research_loop(run)

    assert state["research_id"] == "ledger-concurrency-test"
    assert verification["valid"] is True
    assert not lock_path.exists()

    migrated = kernel.append_action(
        run,
        action_id="first-writer-after-legacy-read",
        action_type="lock_migration_probe",
        status="completed",
        summary="The first writer creates the persistent advisory lock.",
        cost_units=1,
    )
    assert lock_path.is_file()
    assert migrated["actions"][0]["action_id"] == "first-writer-after-legacy-read"
    assert kernel.verify_research_loop(run)["valid"] is True


def test_action_and_stop_are_committed_as_one_terminal_transaction(
    tmp_path: Path,
) -> None:
    run = _initialize_run(
        tmp_path,
        maximum_actions=1,
        maximum_cost_units=1,
    )

    state = kernel.append_action_and_stop(
        run,
        action_id="terminal-action",
        action_type="external_requirement",
        status="completed",
        summary="Generated the terminal external evidence contract.",
        cost_units=1,
        reason_code="external_evidence_required",
        stop_summary="External evidence is required before further research.",
    )

    assert state["status"] == "stopped"
    assert state["event_count"] == 3
    assert [item["action_id"] for item in state["actions"]] == ["terminal-action"]
    assert state["stop"] == {
        "reason_code": "external_evidence_required",
        "summary": "External evidence is required before further research.",
    }
    assert kernel.verify_research_loop(run)["valid"] is True

    ledger_lines = (run / kernel.LEDGER_FILENAME).read_text(encoding="utf-8").splitlines()
    events = [json.loads(line) for line in ledger_lines]
    assert [event["sequence"] for event in events] == [1, 2, 3]
    assert events[2]["previous_event_hash"] == events[1]["event_hash"]


@pytest.mark.parametrize("writer", ["hypothesis", "evidence"])
def test_non_action_writers_remain_supported_under_locked_transactions(
    tmp_path: Path,
    writer: str,
) -> None:
    run = _initialize_run(
        tmp_path,
        maximum_actions=1,
        maximum_cost_units=1,
    )
    if writer == "hypothesis":
        state = kernel.append_hypothesis(
            run,
            hypothesis_id="h1",
            statement="A locked writer remains valid.",
            rationale="The transaction boundary must preserve existing APIs.",
        )
        assert state["hypotheses"][0]["hypothesis_id"] == "h1"
    else:
        source = tmp_path / "evidence.txt"
        source.write_text("authoritative evidence placeholder", encoding="utf-8")
        state = kernel.append_evidence(
            run,
            evidence_id="e1",
            evidence_type="test_record",
            source_path=source,
            summary="Locked evidence registration remains valid.",
        )
        assert state["evidence"][0]["evidence_id"] == "e1"
    assert kernel.verify_research_loop(run)["valid"] is True
