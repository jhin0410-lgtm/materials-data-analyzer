from __future__ import annotations

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


def _report_path(run: Path, action_id: str = "test-action-1") -> Path:
    path = run / "actions" / action_id / "action_result.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}", encoding="utf-8")
    return path


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


def _install_happy_path(
    monkeypatch: pytest.MonkeyPatch,
    *,
    registry: Path,
    run: Path,
    action_type: str = "protocol_stratification",
    action_version: str = "1.0",
    action_id: str = "test-action-1",
) -> Path:
    report = _report_path(run, action_id)
    monkeypatch.setattr(
        execution,
        "assess_current_action_authorization",
        lambda *args, **kwargs: _authorization(
            action_type=action_type,
            action_version=action_version,
            registry=registry,
        ),
    )
    states = iter(
        [
            _before_state(),
            _after_state(action_type, report, action_id=action_id),
        ]
    )
    monkeypatch.setattr(execution, "load_research_state", lambda path: next(states))
    monkeypatch.setitem(
        execution._DISPATCH,
        (action_type, action_version),
        (
            lambda path: {"execution_status": "completed", "action_id": action_id},
            lambda path: {"valid": True, "action_id": action_id},
        ),
    )
    return report


def test_authorized_execution_preserves_original_request_path_semantics(
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
    seen: list[Path] = []

    def executor(path: str | Path) -> dict[str, object]:
        seen.append(Path(path))
        return {"execution_status": "completed", "action_id": "test-action-1"}

    monkeypatch.setitem(
        execution._DISPATCH,
        ("protocol_stratification", "1.0"),
        (
            executor,
            lambda path: {"valid": True, "action_id": "test-action-1"},
        ),
    )

    result = execution.execute_authorized_action(
        "nasa-battery",
        repository_root=tmp_path,
        research_run=run,
        action_registry_path=tmp_path / "planning.json",
        request_path=request,
    )

    assert seen == [request.resolve()]
    assert result["action_version"] == "1.0"
    assert result["ledger_action_id"] == "test-action-1"


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


def test_request_action_id_must_match_appended_ledger_action(
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
    wrong_report = _report_path(run, "other-action")
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
            lambda path: {"valid": True, "action_id": "other-action"},
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
    outside_report = tmp_path / "action_result.json"
    outside_report.write_text("{}", encoding="utf-8")
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
            _after_state("protocol_stratification", outside_report),
        ]
    )
    monkeypatch.setattr(execution, "load_research_state", lambda path: next(states))
    monkeypatch.setitem(
        execution._DISPATCH,
        ("protocol_stratification", "1.0"),
        (
            lambda path: {"execution_status": "completed", "action_id": "test-action-1"},
            lambda path: {"valid": True, "action_id": "test-action-1"},
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


def test_executor_result_action_id_must_match_request(
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
    monkeypatch.setitem(
        execution._DISPATCH,
        ("protocol_stratification", "1.0"),
        (
            lambda path: {"execution_status": "completed", "action_id": "wrong"},
            lambda path: {"valid": True, "action_id": "test-action-1"},
        ),
    )

    with pytest.raises(execution.AuthorizedExecutionError, match="executor result action_id"):
        execution.execute_authorized_action(
            "nasa-battery",
            repository_root=tmp_path,
            research_run=run,
            action_registry_path=tmp_path / "planning.json",
            request_path=request,
        )


def test_verifier_report_action_id_must_match_request(
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
    monkeypatch.setitem(
        execution._DISPATCH,
        ("protocol_stratification", "1.0"),
        (
            lambda path: {"execution_status": "completed", "action_id": "test-action-1"},
            lambda path: {"valid": True, "action_id": "wrong"},
        ),
    )

    with pytest.raises(execution.AuthorizedExecutionError, match="verified action report action_id"):
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


def test_empty_request_is_rejected_before_authorization(tmp_path: Path) -> None:
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
