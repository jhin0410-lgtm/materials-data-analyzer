from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop.action_output_ledger_transaction import (
    ActionOutputLedgerTransactionError,
    cleanup_action_output_ledger_transaction,
    prepare_action_output_ledger_transaction,
    recover_action_output_ledger_transaction_before_authorization,
    shared_research_ledger_transaction_lock,
)
from materials_data_analyzer.research_loop.action_registry import load_action_registry
from materials_data_analyzer.research_loop.kernel import (
    STATE_FILENAME,
    append_action,
    initialize_research_loop,
    load_research_state,
)

ACTION_TYPE = "target_reference_sensitivity"
ACTION_VERSION = "1.0"
COST_UNITS = 4


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _record(path: Path) -> dict[str, object]:
    data = path.read_bytes()
    return {
        "path": str(path.resolve()),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _registry() -> tuple[Path, str]:
    root = _repo_root()
    path = root / "configs/research/nasa_target_reference_action_registry.v1.json"
    registry = load_action_registry(path, repository_root=root)
    return path, str(registry["registry_sha256"])


def _research_run(tmp_path: Path) -> Path:
    objective = tmp_path / "objective.json"
    _write_json(
        objective,
        {
            "schema_version": "1.0",
            "research_id": "pre-auth-recovery-test",
            "question": "Can an authorized action transaction recover before replanning?",
            "metrics": {"primary": "transaction_integrity", "secondary": []},
            "constraints": ["recovery_must_fail_closed"],
            "budget": {"maximum_actions": 8, "maximum_cost_units": 64},
            "stop_rules": ["external_evidence_required"],
        },
    )
    run = tmp_path / "research_run"
    initialize_research_loop(objective, run)
    return run


def _request(
    tmp_path: Path,
    run: Path,
    *,
    action_id: str,
) -> tuple[Path, dict[str, object], dict[str, object]]:
    registry_path, registry_sha = _registry()
    payload: dict[str, object] = {
        "schema_version": "1.0",
        "action_id": action_id,
        "action_type": ACTION_TYPE,
        "research_run": str(run),
        "analysis_run": str(tmp_path / "unused-analysis"),
        "registry": str(registry_path),
        "repository_root": str(_repo_root()),
        "expected_registry_sha256": registry_sha,
    }
    path = tmp_path / f"{action_id}.json"
    _write_json(path, payload)
    return path.resolve(), payload, _record(path)


def _prepare(
    run: Path,
    request_path: Path,
    request: dict[str, object],
    request_record: dict[str, object],
    *,
    action_id: str,
) -> None:
    prepare_action_output_ledger_transaction(
        research_run=run,
        request=request,
        request_path=request_path,
        request_record=request_record,
        action_id=action_id,
        action_type=ACTION_TYPE,
        action_version=ACTION_VERSION,
        cost_units=COST_UNITS,
        state=load_research_state(run),
    )


def _publish_report(
    run: Path,
    *,
    action_id: str,
    request_record: dict[str, object],
    output_path: Path | None = None,
) -> Path:
    action_directory = run / "actions" / action_id
    action_directory.mkdir(parents=True, exist_ok=False)
    report: dict[str, object] = {
        "schema_version": "1.0",
        "execution_status": "completed",
        "action_id": action_id,
        "action_type": ACTION_TYPE,
        "action_version": ACTION_VERSION,
        "cost_units": COST_UNITS,
        "request": request_record,
    }
    if output_path is not None:
        report["outputs"] = [
            {
                "relative_path": output_path.name,
                **_record(output_path),
            }
        ]
    report_path = action_directory / "action_result.json"
    _write_json(report_path, report)
    return report_path


def test_pre_authorization_recovery_commits_published_report(tmp_path: Path) -> None:
    run = _research_run(tmp_path)
    request_path, request, request_record = _request(
        tmp_path,
        run,
        action_id="published-before-ledger",
    )
    with shared_research_ledger_transaction_lock(run):
        _prepare(
            run,
            request_path,
            request,
            request_record,
            action_id="published-before-ledger",
        )
    report = _publish_report(
        run,
        action_id="published-before-ledger",
        request_record=request_record,
    )

    with shared_research_ledger_transaction_lock(run):
        recovered = recover_action_output_ledger_transaction_before_authorization(
            research_run=run,
            request=request,
            request_path=request_path,
            request_record=request_record,
        )
        assert recovered is not None
        assert recovered["recovery_stage"] == "published"
        state = load_research_state(run)
        assert len(state["actions"]) == 1
        assert state["actions"][0]["action_id"] == "published-before-ledger"
        assert state["actions"][0]["artifacts"] == [_record(report)]
        cleanup_action_output_ledger_transaction(
            research_run=run,
            action_id="published-before-ledger",
        )


def test_pre_authorization_recovery_cleans_committed_journal_without_new_action(
    tmp_path: Path,
) -> None:
    run = _research_run(tmp_path)
    request_path, request, request_record = _request(
        tmp_path,
        run,
        action_id="ledger-before-cleanup",
    )
    with shared_research_ledger_transaction_lock(run):
        _prepare(
            run,
            request_path,
            request,
            request_record,
            action_id="ledger-before-cleanup",
        )
    report = _publish_report(
        run,
        action_id="ledger-before-cleanup",
        request_record=request_record,
    )
    append_action(
        run,
        action_id="ledger-before-cleanup",
        action_type=ACTION_TYPE,
        status="completed",
        summary="Simulate a crash after ledger/state commit but before journal cleanup.",
        cost_units=COST_UNITS,
        artifact_paths=[report],
    )
    before = load_research_state(run)

    with shared_research_ledger_transaction_lock(run):
        recovered = recover_action_output_ledger_transaction_before_authorization(
            research_run=run,
            request=request,
            request_path=request_path,
            request_record=request_record,
        )
        assert recovered is not None
        assert recovered["recovery_stage"] == "ledger_committed"
        after = load_research_state(run)
        assert after["event_count"] == before["event_count"]
        assert len(after["actions"]) == 1
        cleanup_action_output_ledger_transaction(
            research_run=run,
            action_id="ledger-before-cleanup",
        )


def test_pre_authorization_recovery_repairs_stale_state_snapshot(tmp_path: Path) -> None:
    run = _research_run(tmp_path)
    request_path, request, request_record = _request(
        tmp_path,
        run,
        action_id="ledger-before-state",
    )
    stale_snapshot = (run / STATE_FILENAME).read_bytes()
    with shared_research_ledger_transaction_lock(run):
        _prepare(
            run,
            request_path,
            request,
            request_record,
            action_id="ledger-before-state",
        )
    report = _publish_report(
        run,
        action_id="ledger-before-state",
        request_record=request_record,
    )
    append_action(
        run,
        action_id="ledger-before-state",
        action_type=ACTION_TYPE,
        status="completed",
        summary="Simulate the action event being committed before state replacement.",
        cost_units=COST_UNITS,
        artifact_paths=[report],
    )
    (run / STATE_FILENAME).write_bytes(stale_snapshot)
    with pytest.raises(Exception, match="snapshot does not match"):
        load_research_state(run)

    with shared_research_ledger_transaction_lock(run):
        recovered = recover_action_output_ledger_transaction_before_authorization(
            research_run=run,
            request=request,
            request_path=request_path,
            request_record=request_record,
        )
        assert recovered is not None
        assert recovered["state_snapshot_repaired"] is True
        repaired = load_research_state(run)
        assert repaired["actions"][0]["action_id"] == "ledger-before-state"
        cleanup_action_output_ledger_transaction(
            research_run=run,
            action_id="ledger-before-state",
        )


def test_recovery_rejects_completed_output_path_escape(tmp_path: Path) -> None:
    run = _research_run(tmp_path)
    request_path, request, request_record = _request(
        tmp_path,
        run,
        action_id="escaped-output",
    )
    with shared_research_ledger_transaction_lock(run):
        _prepare(
            run,
            request_path,
            request,
            request_record,
            action_id="escaped-output",
        )
    outside = tmp_path / "outside.json"
    _write_json(outside, {"not": "an action-owned output"})
    _publish_report(
        run,
        action_id="escaped-output",
        request_record=request_record,
        output_path=outside,
    )

    with shared_research_ledger_transaction_lock(run):
        with pytest.raises(
            ActionOutputLedgerTransactionError,
            match="escapes the action directory",
        ):
            recover_action_output_ledger_transaction_before_authorization(
                research_run=run,
                request=request,
                request_path=request_path,
                request_record=request_record,
            )
        assert load_research_state(run)["actions"] == []
