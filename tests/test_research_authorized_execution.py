from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import materials_data_analyzer.research_loop.authorized_execution as execution


def _authorization(
    *,
    action_type: str,
    registry: Path,
    action_version: str = "1.0",
    registry_sha: str = "a" * 64,
    status: str = "ready_for_explicit_execution_request",
) -> dict[str, object]:
    return {
        "authorization_status": status,
        "selected_action": {
            "action_type": action_type,
            "action_version": action_version,
        },
        "execution_contract": {
            "registry_id": "test-execution-registry",
            "registry_sha256": registry_sha,
            "registry_path": str(registry),
            "action_version": action_version,
        },
    }


def _write_request(
    path: Path,
    *,
    action_type: str,
    run: Path,
    root: Path,
    registry: Path,
    registry_sha: str = "a" * 64,
    action_id: str = "test-action-1",
) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "action_id": action_id,
                "action_type": action_type,
                "research_run": str(run),
                "registry": str(registry),
                "repository_root": str(root),
                "expected_registry_sha256": registry_sha,
            }
        ),
        encoding="utf-8",
    )


def _before_state() -> dict[str, object]:
    return {"actions": [{"action_id": "old", "action_type": "old", "artifacts": []}]}


def _after_state(
    action_type: str,
    report: Path,
    *,
    action_id: str = "test-action-1",
) -> dict[str, object]:
    return {
        "actions": [
            {"action_id": "old", "action_type": "old", "artifacts": []},
            {
                "action_id": action_id,
                "action_type": action_type,
                "status": "completed",
                "artifacts": [{"path": str(report)}],
            },
        ]
    }


def _report_path(run: Path, action_id: str = "test-action-1") -> Path:
    path = run / "actions" / action_id / "action_result.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}", encoding="utf-8")
    return path


def test_explicit_authorized_action_dispatches_once_and_reverifies(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path
    run = root / "run"
    run.mkdir()
    registry = root / "registry.json"
    registry.write_text("{}", encoding="utf-8")
    request = root / "request.json"
    report = _report_path(run)
    _write_request(
        request,
        action_type="protocol_stratification",
        run=run,
        root=root,
        registry=registry,
    )
    original_request = request.read_bytes()

    calls = {"executor": 0, "verifier": 0}

    def fake_executor(path: str | Path) -> dict[str, object]:
        calls["executor"] += 1
        snapshot = Path(path)
        assert snapshot != request
        assert snapshot.read_bytes() == original_request
        return {"execution_status": "completed", "action_id": "test-action-1"}

    def fake_verifier(path: str | Path) -> dict[str, object]:
        calls["verifier"] += 1
        assert Path(path) == report
        return {"verified": True, "action_id": "test-action-1"}

    monkeypatch.setattr(
        execution,
        "assess_current_action_authorization",
        lambda *args, **kwargs: _authorization(
            action_type="protocol_stratification", registry=registry
        ),
    )
    states = iter([_before_state(), _after_state("protocol_stratification", report)])
    monkeypatch.setattr(execution, "load_research_state", lambda path: next(states))
    monkeypatch.setitem(
        execution._DISPATCH,
        ("protocol_stratification", "1.0"),
        (fake_executor, fake_verifier),
    )

    result = execution.execute_authorized_action(
        "nasa-battery",
        repository_root=root,
        research_run=run,
        action_registry_path=root / "planning.json",
        request_path=request,
    )

    assert calls == {"executor": 1, "verifier": 1}
    assert result["execution_status"] == "completed"
    assert result["actions_after"] == result["actions_before"] + 1
    assert result["maximum_actions_executed_per_invocation"] == 1
    assert result["action_executed"] is True
    assert result["automatic_execution_authorized"] is False
    assert result["generic_command_execution_available"] is False
    assert result["action_version"] == "1.0"
    assert result["request_binding"]["sha256"] == hashlib.sha256(
        original_request
    ).hexdigest()
    snapshot_path = Path(result["request_binding"]["executed_snapshot_path"])
    assert snapshot_path.read_bytes() == original_request
    assert result["request_binding"]["executed_snapshot_sha256"] == hashlib.sha256(
        original_request
    ).hexdigest()


def test_source_request_replacement_does_not_change_executor_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = tmp_path / "run"
    run.mkdir()
    registry = tmp_path / "registry.json"
    registry.write_text("{}", encoding="utf-8")
    request = tmp_path / "request.json"
    _write_request(
        request,
        action_type="protocol_stratification",
        run=run,
        root=tmp_path,
        registry=registry,
    )
    original_request = request.read_bytes()
    report = _report_path(run)

    monkeypatch.setattr(
        execution,
        "assess_current_action_authorization",
        lambda *args, **kwargs: _authorization(
            action_type="protocol_stratification", registry=registry
        ),
    )
    states = iter([_before_state(), _after_state("protocol_stratification", report)])
    monkeypatch.setattr(execution, "load_research_state", lambda path: next(states))

    def fake_executor(path: str | Path) -> dict[str, object]:
        request.write_text('{"action_type":"tampered"}', encoding="utf-8")
        assert Path(path).read_bytes() == original_request
        return {"execution_status": "completed", "action_id": "test-action-1"}

    monkeypatch.setitem(
        execution._DISPATCH,
        ("protocol_stratification", "1.0"),
        (
            fake_executor,
            lambda path: {"verified": True, "action_id": "test-action-1"},
        ),
    )

    result = execution.execute_authorized_action(
        "nasa-battery",
        repository_root=tmp_path,
        research_run=run,
        action_registry_path=tmp_path / "planning.json",
        request_path=request,
    )

    assert result["ledger_action_id"] == "test-action-1"


def test_unknown_selected_action_fails_before_dispatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = tmp_path / "run"
    run.mkdir()
    registry = tmp_path / "registry.json"
    registry.write_text("{}", encoding="utf-8")
    request = tmp_path / "request.json"
    _write_request(
        request,
        action_type="arbitrary_shell_command",
        run=run,
        root=tmp_path,
        registry=registry,
    )
    monkeypatch.setattr(
        execution,
        "assess_current_action_authorization",
        lambda *args, **kwargs: _authorization(
            action_type="arbitrary_shell_command", registry=registry
        ),
    )

    with pytest.raises(
        execution.AuthorizedExecutionError,
        match="no hardcoded typed executor",
    ):
        execution.execute_authorized_action(
            "nasa-battery",
            repository_root=tmp_path,
            research_run=run,
            action_registry_path=tmp_path / "planning.json",
            request_path=request,
        )


def test_unsupported_action_version_fails_before_dispatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = tmp_path / "run"
    run.mkdir()
    registry = tmp_path / "registry.json"
    registry.write_text("{}", encoding="utf-8")
    request = tmp_path / "request.json"
    _write_request(
        request,
        action_type="protocol_stratification",
        run=run,
        root=tmp_path,
        registry=registry,
    )
    monkeypatch.setattr(
        execution,
        "assess_current_action_authorization",
        lambda *args, **kwargs: _authorization(
            action_type="protocol_stratification",
            action_version="2.0",
            registry=registry,
        ),
    )

    with pytest.raises(
        execution.AuthorizedExecutionError,
        match="type/version has no hardcoded typed executor",
    ):
        execution.execute_authorized_action(
            "nasa-battery",
            repository_root=tmp_path,
            research_run=run,
            action_registry_path=tmp_path / "planning.json",
            request_path=request,
        )


def test_denied_authorization_never_dispatches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = tmp_path / "run"
    run.mkdir()
    registry = tmp_path / "registry.json"
    registry.write_text("{}", encoding="utf-8")
    request = tmp_path / "request.json"
    _write_request(
        request,
        action_type="protocol_stratification",
        run=run,
        root=tmp_path,
        registry=registry,
    )
    monkeypatch.setattr(
        execution,
        "assess_current_action_authorization",
        lambda *args, **kwargs: _authorization(
            action_type="protocol_stratification",
            registry=registry,
            status="denied_cost_budget_exceeded",
        ),
    )

    with pytest.raises(execution.AuthorizedExecutionError, match="not ready"):
        execution.execute_authorized_action(
            "nasa-battery",
            repository_root=tmp_path,
            research_run=run,
            action_registry_path=tmp_path / "planning.json",
            request_path=request,
        )


def test_request_action_type_must_match_authorized_action(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = tmp_path / "run"
    run.mkdir()
    registry = tmp_path / "registry.json"
    registry.write_text("{}", encoding="utf-8")
    request = tmp_path / "request.json"
    _write_request(
        request,
        action_type="target_reference_sensitivity",
        run=run,
        root=tmp_path,
        registry=registry,
    )
    monkeypatch.setattr(
        execution,
        "assess_current_action_authorization",
        lambda *args, **kwargs: _authorization(
            action_type="protocol_stratification", registry=registry
        ),
    )

    with pytest.raises(execution.AuthorizedExecutionError, match="action_type does not match"):
        execution.execute_authorized_action(
            "nasa-battery",
            repository_root=tmp_path,
            research_run=run,
            action_registry_path=tmp_path / "planning.json",
            request_path=request,
        )


def test_request_must_bind_same_research_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = tmp_path / "run"
    other_run = tmp_path / "other-run"
    run.mkdir()
    other_run.mkdir()
    registry = tmp_path / "registry.json"
    registry.write_text("{}", encoding="utf-8")
    request = tmp_path / "request.json"
    _write_request(
        request,
        action_type="protocol_stratification",
        run=other_run,
        root=tmp_path,
        registry=registry,
    )
    monkeypatch.setattr(
        execution,
        "assess_current_action_authorization",
        lambda *args, **kwargs: _authorization(
            action_type="protocol_stratification", registry=registry
        ),
    )

    with pytest.raises(execution.AuthorizedExecutionError, match="research_run does not match"):
        execution.execute_authorized_action(
            "nasa-battery",
            repository_root=tmp_path,
            research_run=run,
            action_registry_path=tmp_path / "planning.json",
            request_path=request,
        )


def test_executor_must_append_exactly_one_action(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = tmp_path / "run"
    run.mkdir()
    registry = tmp_path / "registry.json"
    registry.write_text("{}", encoding="utf-8")
    request = tmp_path / "request.json"
    _write_request(
        request,
        action_type="protocol_stratification",
        run=run,
        root=tmp_path,
        registry=registry,
    )
    monkeypatch.setattr(
        execution,
        "assess_current_action_authorization",
        lambda *args, **kwargs: _authorization(
            action_type="protocol_stratification", registry=registry
        ),
    )
    monkeypatch.setitem(
        execution._DISPATCH,
        ("protocol_stratification", "1.0"),
        (
            lambda path: {"ok": True, "action_id": "test-action-1"},
            lambda path: {"verified": True, "action_id": "test-action-1"},
        ),
    )
    after = _before_state()
    after["actions"] = [
        *after["actions"],  # type: ignore[index]
        {"action_id": "one", "action_type": "protocol_stratification", "artifacts": []},
        {"action_id": "two", "action_type": "protocol_stratification", "artifacts": []},
    ]
    states = iter([_before_state(), after])
    monkeypatch.setattr(execution, "load_research_state", lambda path: next(states))

    with pytest.raises(execution.AuthorizedExecutionError, match="exactly one"):
        execution.execute_authorized_action(
            "nasa-battery",
            repository_root=tmp_path,
            research_run=run,
            action_registry_path=tmp_path / "planning.json",
            request_path=request,
        )


def test_latest_ledger_action_must_match_request_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = tmp_path / "run"
    run.mkdir()
    registry = tmp_path / "registry.json"
    registry.write_text("{}", encoding="utf-8")
    request = tmp_path / "request.json"
    _write_request(
        request,
        action_type="protocol_stratification",
        run=run,
        root=tmp_path,
        registry=registry,
    )
    wrong_report = _report_path(run, action_id="other-action")
    monkeypatch.setattr(
        execution,
        "assess_current_action_authorization",
        lambda *args, **kwargs: _authorization(
            action_type="protocol_stratification", registry=registry
        ),
    )
    states = iter(
        [
            _before_state(),
            _after_state(
                "protocol_stratification",
                wrong_report,
                action_id="other-action",
            ),
        ]
    )
    monkeypatch.setattr(execution, "load_research_state", lambda path: next(states))
    monkeypatch.setitem(
        execution._DISPATCH,
        ("protocol_stratification", "1.0"),
        (
            lambda path: {"execution_status": "completed", "action_id": "test-action-1"},
            lambda path: {"verified": True, "action_id": "other-action"},
        ),
    )

    with pytest.raises(execution.AuthorizedExecutionError, match="action ID does not match"):
        execution.execute_authorized_action(
            "nasa-battery",
            repository_root=tmp_path,
            research_run=run,
            action_registry_path=tmp_path / "planning.json",
            request_path=request,
        )


def test_report_must_remain_inside_expected_action_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = tmp_path / "run"
    run.mkdir()
    registry = tmp_path / "registry.json"
    registry.write_text("{}", encoding="utf-8")
    request = tmp_path / "request.json"
    _write_request(
        request,
        action_type="protocol_stratification",
        run=run,
        root=tmp_path,
        registry=registry,
    )
    report = tmp_path / "action_result.json"
    report.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        execution,
        "assess_current_action_authorization",
        lambda *args, **kwargs: _authorization(
            action_type="protocol_stratification", registry=registry
        ),
    )
    states = iter([_before_state(), _after_state("protocol_stratification", report)])
    monkeypatch.setattr(execution, "load_research_state", lambda path: next(states))
    monkeypatch.setitem(
        execution._DISPATCH,
        ("protocol_stratification", "1.0"),
        (
            lambda path: {"execution_status": "completed", "action_id": "test-action-1"},
            lambda path: {"verified": True, "action_id": "test-action-1"},
        ),
    )

    with pytest.raises(execution.AuthorizedExecutionError, match="escapes"):
        execution.execute_authorized_action(
            "nasa-battery",
            repository_root=tmp_path,
            research_run=run,
            action_registry_path=tmp_path / "planning.json",
            request_path=request,
        )


def test_existing_execution_lock_fails_closed_before_dispatch(
    tmp_path: Path,
) -> None:
    run = tmp_path / "run"
    run.mkdir()
    request = tmp_path / "request.json"
    request.write_text("{}", encoding="utf-8")
    (run / execution._EXECUTION_LOCK_FILENAME).write_text("busy\n", encoding="utf-8")

    with pytest.raises(execution.AuthorizedExecutionError, match="already active"):
        execution.execute_authorized_action(
            "nasa-battery",
            repository_root=tmp_path,
            research_run=run,
            action_registry_path=tmp_path / "planning.json",
            request_path=request,
        )


def test_empty_request_is_rejected_before_authorization(
    tmp_path: Path,
) -> None:
    run = tmp_path / "run"
    run.mkdir()
    request = tmp_path / "request.json"
    request.write_bytes(b"")

    with pytest.raises(execution.AuthorizedExecutionError, match="must not be empty"):
        execution.execute_authorized_action(
            "nasa-battery",
            repository_root=tmp_path,
            research_run=run,
            action_registry_path=tmp_path / "planning.json",
            request_path=request,
        )


def test_non_nasa_adapter_has_no_execution_dispatch(tmp_path: Path) -> None:
    with pytest.raises(execution.AuthorizedExecutionError, match="only for nasa-battery"):
        execution.execute_authorized_action(
            "materials-project-external-source",
            repository_root=tmp_path,
            research_run=tmp_path,
            action_registry_path=tmp_path / "planning.json",
            request_path=tmp_path / "request.json",
        )
