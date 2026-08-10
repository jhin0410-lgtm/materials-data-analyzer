from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import materials_data_analyzer.research_loop.authorized_execution as authorized_execution
from materials_data_analyzer.research_loop.action_output_journalless_recovery import (
    recover_journalless_action_transaction_before_authorization,
)
from materials_data_analyzer.research_loop.action_output_ledger_transaction import (
    ActionOutputLedgerTransactionError,
    _transaction_directory,
    cleanup_action_output_ledger_transaction,
    shared_research_ledger_transaction_lock,
)
from materials_data_analyzer.research_loop.action_registry import load_action_registry
from materials_data_analyzer.research_loop.kernel import (
    append_action,
    initialize_research_loop,
    load_research_state,
)

ACTION_TYPE = "target_reference_sensitivity"
ACTION_VERSION = "1.0"
COST_UNITS = 4


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _record(path: Path) -> dict[str, object]:
    data = path.read_bytes()
    return {
        "path": str(path.resolve()),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _run(tmp_path: Path) -> Path:
    objective = tmp_path / "objective.json"
    _write_json(
        objective,
        {
            "schema_version": "1.0",
            "research_id": "journalless-recovery-test",
            "question": "Can transaction crash states be recovered fail-closed?",
            "metrics": {"primary": "transaction_integrity", "secondary": []},
            "constraints": ["no_unproven_recovery"],
            "budget": {"maximum_actions": 8, "maximum_cost_units": 64},
            "stop_rules": ["external_evidence_required"],
        },
    )
    run = tmp_path / "research_run"
    initialize_research_loop(objective, run)
    return run


def _request(tmp_path: Path, run: Path, action_id: str) -> tuple[Path, dict[str, object], dict[str, object]]:
    root = _repo_root()
    registry_path = root / "configs/research/nasa_target_reference_action_registry.v1.json"
    registry = load_action_registry(registry_path, repository_root=root)
    value: dict[str, object] = {
        "schema_version": "1.0",
        "action_id": action_id,
        "action_type": ACTION_TYPE,
        "research_run": str(run),
        "analysis_run": str(tmp_path / "unused-analysis"),
        "registry": str(registry_path),
        "repository_root": str(root),
        "expected_registry_sha256": registry["registry_sha256"],
    }
    path = tmp_path / f"{action_id}.json"
    _write_json(path, value)
    return path.resolve(), value, _record(path)


def test_empty_journalless_directory_is_cleaned_before_authorization(tmp_path: Path) -> None:
    run = _run(tmp_path)
    request_path, request, request_record = _request(tmp_path, run, "pre-journal-crash")
    transaction_directory = _transaction_directory(run, "pre-journal-crash")
    transaction_directory.mkdir(parents=True)
    (transaction_directory / ".journal.json.partial.tmp").write_text("partial", encoding="utf-8")

    with shared_research_ledger_transaction_lock(run):
        recovered = recover_journalless_action_transaction_before_authorization(
            research_run=run,
            request=request,
            request_path=request_path,
            request_record=request_record,
        )

    assert recovered is None
    assert not transaction_directory.exists()
    assert load_research_state(run)["actions"] == []


def test_journalless_cleanup_interruption_reconstructs_committed_journal(tmp_path: Path) -> None:
    run = _run(tmp_path)
    action_id = "cleanup-crash"
    request_path, request, request_record = _request(tmp_path, run, action_id)
    transaction_directory = _transaction_directory(run, action_id)
    transaction_directory.mkdir(parents=True)
    (transaction_directory / "leftover-backup.bin").write_bytes(b"already-committed-backup")
    action_directory = run / "actions" / action_id
    action_directory.mkdir(parents=True)
    report_path = action_directory / "action_result.json"
    _write_json(
        report_path,
        {
            "schema_version": "1.0",
            "execution_status": "completed",
            "action_id": action_id,
            "action_type": ACTION_TYPE,
            "action_version": ACTION_VERSION,
            "cost_units": COST_UNITS,
            "request": request_record,
        },
    )
    append_action(
        run,
        action_id=action_id,
        action_type=ACTION_TYPE,
        status="completed",
        summary="Simulate commit completed before recursive transaction cleanup finished.",
        cost_units=COST_UNITS,
        artifact_paths=[report_path],
    )
    before = load_research_state(run)

    with shared_research_ledger_transaction_lock(run):
        recovered = recover_journalless_action_transaction_before_authorization(
            research_run=run,
            request=request,
            request_path=request_path,
            request_record=request_record,
        )
        assert recovered is not None
        assert recovered["recovery_stage"] == "ledger_committed_journalless"
        assert len(recovered["research_state"]["actions"]) == 1
        cleanup_action_output_ledger_transaction(research_run=run, action_id=action_id)

    after = load_research_state(run)
    assert after["event_count"] == before["event_count"]
    assert not transaction_directory.exists()


def test_post_ledger_transaction_error_is_classified_as_execution_started(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _run(tmp_path)

    def _started_then_failed(*_args: object, **_kwargs: object) -> dict[str, object]:
        append_action(
            run,
            action_id="started-action",
            action_type="test_action",
            status="failed",
            summary="Ledger mutation happened before transaction verification failed.",
            cost_units=1,
        )
        raise ActionOutputLedgerTransactionError("post-ledger transaction verification failed")

    monkeypatch.setattr(authorized_execution, "execute_authorized_action", _started_then_failed)

    with pytest.raises(
        authorized_execution.AuthorizedExecutionStartedError,
        match="post-ledger transaction verification failed",
    ):
        authorized_execution.execute_authorized_action_with_failure_classification(
            "nasa-battery",
            repository_root=tmp_path,
            research_run=run,
            action_registry_path=tmp_path / "unused-registry.json",
            request_path=tmp_path / "unused-request.json",
        )
