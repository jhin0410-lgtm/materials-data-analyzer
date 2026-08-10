from __future__ import annotations

import json
from pathlib import Path

import pytest

import materials_data_analyzer.research_loop.authorized_execution as execution


def test_expected_action_type_is_checked_from_the_pinned_request(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = tmp_path / "run"
    run.mkdir()
    request = tmp_path / "request.json"
    request.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "action_id": "protocol-1",
                "action_type": "protocol_stratification",
            }
        ),
        encoding="utf-8",
    )

    def fail_authorization(*args: object, **kwargs: object) -> dict[str, object]:
        raise AssertionError("surface mismatch must fail before authorization or dispatch")

    monkeypatch.setattr(execution, "assess_current_action_authorization", fail_authorization)

    with pytest.raises(
        execution.AuthorizedExecutionError,
        match="surface requires action_type='external_data_requirement_generation'",
    ):
        execution.execute_authorized_action(
            "nasa-battery",
            repository_root=tmp_path,
            research_run=run,
            action_registry_path=tmp_path / "planning.json",
            request_path=request,
            expected_action_type="external_data_requirement_generation",
        )


def test_failure_classifier_marks_post_ledger_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = tmp_path / "run"
    run.mkdir()
    counts = iter([4, 5])
    monkeypatch.setattr(execution, "_action_count", lambda *args, **kwargs: next(counts))

    def fail_execution(*args: object, **kwargs: object) -> dict[str, object]:
        raise execution.AuthorizedExecutionError("pinned verification failed")

    monkeypatch.setattr(execution, "execute_authorized_action", fail_execution)

    with pytest.raises(
        execution.AuthorizedExecutionStartedError,
        match="pinned verification failed",
    ):
        execution.execute_authorized_action_with_failure_classification(
            "nasa-battery",
            repository_root=tmp_path,
            research_run=run,
            action_registry_path=tmp_path / "planning.json",
            request_path=tmp_path / "request.json",
        )


def test_failure_classifier_preserves_preflight_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = tmp_path / "run"
    run.mkdir()
    counts = iter([4, 4])
    monkeypatch.setattr(execution, "_action_count", lambda *args, **kwargs: next(counts))

    def fail_execution(*args: object, **kwargs: object) -> dict[str, object]:
        raise execution.AuthorizedExecutionError("authorization denied")

    monkeypatch.setattr(execution, "execute_authorized_action", fail_execution)

    with pytest.raises(execution.AuthorizedExecutionError, match="authorization denied") as exc:
        execution.execute_authorized_action_with_failure_classification(
            "nasa-battery",
            repository_root=tmp_path,
            research_run=run,
            action_registry_path=tmp_path / "planning.json",
            request_path=tmp_path / "request.json",
        )

    assert not isinstance(exc.value, execution.AuthorizedExecutionStartedError)
