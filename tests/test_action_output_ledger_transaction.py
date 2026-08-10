from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop.action_output_ledger_transaction import (
    AUDIT_ACTION_TYPE,
    EXTERNAL_REQUIREMENT_ACTION_TYPE,
    EXTERNAL_REQUIREMENT_STOP_REASON,
    ActionOutputLedgerTransactionError,
    cleanup_action_output_ledger_transaction,
    prepare_action_output_ledger_transaction,
    shared_research_ledger_transaction_lock,
)
from materials_data_analyzer.research_loop.kernel import (
    append_action,
    initialize_research_loop,
    load_research_state,
)


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _record(path: Path) -> dict[str, object]:
    return {
        "path": str(path.resolve()),
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _research_run(tmp_path: Path) -> Path:
    objective = tmp_path / "objective.json"
    _write_json(
        objective,
        {
            "schema_version": "1.0",
            "research_id": "tx-test",
            "question": "Can output publication and ledger commit recover safely?",
            "metrics": {"primary": "transaction_integrity", "secondary": []},
            "constraints": ["no orphan final outputs"],
            "budget": {"maximum_actions": 8, "maximum_cost_units": 32},
            "stop_rules": [EXTERNAL_REQUIREMENT_STOP_REASON],
        },
    )
    run = tmp_path / "research_run"
    initialize_research_loop(objective, run)
    return run


def _request_record(tmp_path: Path, payload: dict[str, object]) -> tuple[Path, dict[str, object]]:
    request = tmp_path / "request.json"
    _write_json(request, payload)
    return request.resolve(), _record(request)


def _publish_report(
    run: Path,
    *,
    action_id: str,
    action_type: str,
    request_record: dict[str, object],
    output_name: str = "result.json",
    stop_reason: str | None = None,
) -> Path:
    action_directory = run / "actions" / action_id
    action_directory.mkdir(parents=True)
    output = action_directory / output_name
    _write_json(output, {"ok": True})
    report: dict[str, object] = {
        "schema_version": "1.0",
        "execution_status": "completed",
        "action_id": action_id,
        "action_type": action_type,
        "action_version": "1.0",
        "cost_units": 1,
        "request": request_record,
        "outputs": [{"relative_path": output_name, **_record(output)}],
    }
    if stop_reason is not None:
        report["stop_reason"] = stop_reason
        report["output"] = {"relative_path": output_name, **_record(output)}
        report.pop("outputs")
    report_path = action_directory / "action_result.json"
    _write_json(report_path, report)
    return report_path


def test_same_kernel_ledger_lock_is_reentrant_for_nested_writer(tmp_path: Path) -> None:
    run = _research_run(tmp_path)
    artifact = tmp_path / "artifact.txt"
    artifact.write_text("bound\n", encoding="utf-8")

    with shared_research_ledger_transaction_lock(run):
        state = load_research_state(run)
        assert state["budget"]["actions_used"] == 0
        state = append_action(
            run,
            action_id="nested-lock",
            action_type="test_action",
            status="completed",
            summary="Nested writer reused the transaction-owned ledger lock.",
            cost_units=0,
            artifact_paths=[artifact],
        )

    assert state["budget"]["actions_used"] == 1


def test_published_output_without_ledger_is_recovered_and_checksum_bound(
    tmp_path: Path,
) -> None:
    run = _research_run(tmp_path)
    request_payload = {
        "action_id": "recover-published",
        "action_type": "target_reference_sensitivity",
    }
    request_path, request_record = _request_record(tmp_path, request_payload)

    with shared_research_ledger_transaction_lock(run):
        prepared = prepare_action_output_ledger_transaction(
            research_run=run,
            request=request_payload,
            request_path=request_path,
            request_record=request_record,
            action_id="recover-published",
            action_type="target_reference_sensitivity",
            action_version="1.0",
            cost_units=1,
            state=load_research_state(run),
        )
        assert prepared["recovered"] is False

    report_path = _publish_report(
        run,
        action_id="recover-published",
        action_type="target_reference_sensitivity",
        request_record=request_record,
    )

    with shared_research_ledger_transaction_lock(run):
        recovered = prepare_action_output_ledger_transaction(
            research_run=run,
            request=request_payload,
            request_path=request_path,
            request_record=request_record,
            action_id="recover-published",
            action_type="target_reference_sensitivity",
            action_version="1.0",
            cost_units=1,
            state=load_research_state(run),
        )
        state = load_research_state(run)
        assert recovered["recovered"] is True
        assert len(state["actions"]) == 1
        assert state["actions"][0]["action_id"] == "recover-published"
        assert any(
            item["path"] == str(report_path.resolve())
            and item["sha256"] == _sha256(report_path)
            for item in state["actions"][0]["artifacts"]
        )
        cleanup_action_output_ledger_transaction(
            research_run=run, action_id="recover-published"
        )


def test_published_checksum_mismatch_fails_closed_without_ledger_mutation(
    tmp_path: Path,
) -> None:
    run = _research_run(tmp_path)
    request_payload = {
        "action_id": "hash-conflict",
        "action_type": "protocol_stratification",
    }
    request_path, request_record = _request_record(tmp_path, request_payload)
    with shared_research_ledger_transaction_lock(run):
        prepare_action_output_ledger_transaction(
            research_run=run,
            request=request_payload,
            request_path=request_path,
            request_record=request_record,
            action_id="hash-conflict",
            action_type="protocol_stratification",
            action_version="1.0",
            cost_units=1,
            state=load_research_state(run),
        )

    report = _publish_report(
        run,
        action_id="hash-conflict",
        action_type="protocol_stratification",
        request_record=request_record,
    )
    output = report.parent / "result.json"
    output.write_text("tampered\n", encoding="utf-8")

    with shared_research_ledger_transaction_lock(run):
        with pytest.raises(
            ActionOutputLedgerTransactionError,
            match="checksum does not match",
        ):
            prepare_action_output_ledger_transaction(
                research_run=run,
                request=request_payload,
                request_path=request_path,
                request_record=request_record,
                action_id="hash-conflict",
                action_type="protocol_stratification",
                action_version="1.0",
                cost_units=1,
                state=load_research_state(run),
            )
        assert load_research_state(run)["actions"] == []


def test_interrupted_audit_restores_mutable_analysis_snapshot_before_retry(
    tmp_path: Path,
) -> None:
    run = _research_run(tmp_path)
    analysis = tmp_path / "analysis"
    for relative in (
        "tables/validated_cycle_summary.csv",
        "tables/forecast_feature_table.csv",
        "tables/validation_predictions.csv",
        "config_snapshot.json",
    ):
        path = analysis / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"original:{relative}\n", encoding="utf-8")
    mutable = analysis / "reports/scientific_closeout.json"
    _write_json(mutable, {"evidence_level": "Unsupported", "original": True})

    request_payload = {
        "action_id": "audit-crash",
        "action_type": AUDIT_ACTION_TYPE,
        "analysis_run": str(analysis),
    }
    request_path, request_record = _request_record(tmp_path, request_payload)
    with shared_research_ledger_transaction_lock(run):
        prepare_action_output_ledger_transaction(
            research_run=run,
            request=request_payload,
            request_path=request_path,
            request_record=request_record,
            action_id="audit-crash",
            action_type=AUDIT_ACTION_TYPE,
            action_version="1.0",
            cost_units=1,
            state=load_research_state(run),
        )

    _write_json(mutable, {"evidence_level": "Unsupported", "corrupted": True})
    generated = analysis / "tables/target_integrity_by_battery.csv"
    generated.parent.mkdir(parents=True, exist_ok=True)
    generated.write_text("partial\n", encoding="utf-8")

    with shared_research_ledger_transaction_lock(run):
        retried = prepare_action_output_ledger_transaction(
            research_run=run,
            request=request_payload,
            request_path=request_path,
            request_record=request_record,
            action_id="audit-crash",
            action_type=AUDIT_ACTION_TYPE,
            action_version="1.0",
            cost_units=1,
            state=load_research_state(run),
        )
        assert retried["recovered"] is False

    assert json.loads(mutable.read_text(encoding="utf-8"))["original"] is True
    assert not generated.exists()


def test_external_requirement_recovery_commits_action_and_stop_exactly_once(
    tmp_path: Path,
) -> None:
    run = _research_run(tmp_path)
    request_payload = {
        "action_id": "external-crash",
        "action_type": EXTERNAL_REQUIREMENT_ACTION_TYPE,
    }
    request_path, request_record = _request_record(tmp_path, request_payload)
    with shared_research_ledger_transaction_lock(run):
        prepare_action_output_ledger_transaction(
            research_run=run,
            request=request_payload,
            request_path=request_path,
            request_record=request_record,
            action_id="external-crash",
            action_type=EXTERNAL_REQUIREMENT_ACTION_TYPE,
            action_version="1.0",
            cost_units=1,
            state=load_research_state(run),
        )

    _publish_report(
        run,
        action_id="external-crash",
        action_type=EXTERNAL_REQUIREMENT_ACTION_TYPE,
        request_record=request_record,
        stop_reason=EXTERNAL_REQUIREMENT_STOP_REASON,
    )

    with shared_research_ledger_transaction_lock(run):
        first = prepare_action_output_ledger_transaction(
            research_run=run,
            request=request_payload,
            request_path=request_path,
            request_record=request_record,
            action_id="external-crash",
            action_type=EXTERNAL_REQUIREMENT_ACTION_TYPE,
            action_version="1.0",
            cost_units=1,
            state=load_research_state(run),
        )
        state_after_first = load_research_state(run)
        assert first["recovered"] is True
        assert state_after_first["status"] == "stopped"
        assert len(state_after_first["actions"]) == 1
        event_count = state_after_first["event_count"]

        second = prepare_action_output_ledger_transaction(
            research_run=run,
            request=request_payload,
            request_path=request_path,
            request_record=request_record,
            action_id="external-crash",
            action_type=EXTERNAL_REQUIREMENT_ACTION_TYPE,
            action_version="1.0",
            cost_units=1,
            state=state_after_first,
        )
        state_after_second = load_research_state(run)
        assert second["recovered"] is True
        assert state_after_second["event_count"] == event_count
        assert len(state_after_second["actions"]) == 1
        cleanup_action_output_ledger_transaction(
            research_run=run, action_id="external-crash"
        )
