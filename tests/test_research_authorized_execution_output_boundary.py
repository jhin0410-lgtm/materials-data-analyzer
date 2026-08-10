from __future__ import annotations

import json
from pathlib import Path

import pytest

import materials_data_analyzer.research_loop.authorized_execution as execution


def test_action_directory_symlink_escape_is_rejected_before_dispatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = tmp_path / "run"
    run.mkdir()
    actions = run / "actions"
    actions.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    action_id = "test-action-1"
    try:
        (actions / action_id).symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlink creation is unavailable on this platform: {exc}")

    registry = tmp_path / "registry.json"
    registry.write_text("{}", encoding="utf-8")
    request = tmp_path / "request.json"
    request.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "action_id": action_id,
                "action_type": "protocol_stratification",
                "research_run": str(run),
                "registry": str(registry),
                "repository_root": str(tmp_path),
                "expected_registry_sha256": "a" * 64,
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        execution,
        "assess_current_action_authorization",
        lambda *args, **kwargs: {
            "authorization_status": "ready_for_explicit_execution_request",
            "selected_action": {
                "action_type": "protocol_stratification",
                "action_version": "1.0",
            },
            "execution_contract": {
                "registry_id": "test-registry",
                "registry_sha256": "a" * 64,
                "registry_path": str(registry),
                "action_version": "1.0",
            },
        },
    )

    dispatched = False

    def fake_executor(path: str | Path) -> dict[str, object]:
        nonlocal dispatched
        dispatched = True
        return {"action_id": action_id}

    monkeypatch.setitem(
        execution._DISPATCH,
        ("protocol_stratification", "1.0"),
        (fake_executor, lambda path: {"action_id": action_id}),
    )

    with pytest.raises(
        execution.AuthorizedExecutionError,
        match="action directory resolves outside",
    ):
        execution.execute_authorized_action(
            "nasa-battery",
            repository_root=tmp_path,
            research_run=run,
            action_registry_path=tmp_path / "planning.json",
            request_path=request,
        )

    assert dispatched is False
