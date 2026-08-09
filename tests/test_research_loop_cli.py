from __future__ import annotations

import json
from pathlib import Path

import pytest

import materials_data_analyzer.research_loop_cli as cli


def _objective(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "research_id": "loop-cli-test",
                "question": "Can the loop preserve a bounded research episode?",
                "metrics": {"primary": "mae", "secondary": []},
                "constraints": ["no_locked_test_reuse"],
                "budget": {"maximum_actions": 1, "maximum_cost_units": 2},
                "stop_rules": ["budget_exhausted"],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_research_loop_cli_initializes_and_verifies(tmp_path: Path, capsys) -> None:
    objective = _objective(tmp_path / "objective.json")
    run = tmp_path / "run"

    assert (
        cli.main(
            [
                "init",
                "--objective",
                str(objective),
                "--output",
                str(run),
            ]
        )
        == 0
    )
    initialized = json.loads(capsys.readouterr().out)
    assert initialized["research_id"] == "loop-cli-test"

    assert cli.main(["verify", "--run", str(run)]) == 0
    verified = json.loads(capsys.readouterr().out)
    assert verified["valid"] is True
    assert verified["event_count"] == 1


def test_research_loop_cli_records_hypothesis_and_action(tmp_path: Path, capsys) -> None:
    objective = _objective(tmp_path / "objective.json")
    run = tmp_path / "run"
    cli.main(["init", "--objective", str(objective), "--output", str(run)])
    capsys.readouterr()

    assert (
        cli.main(
            [
                "add-hypothesis",
                "--run",
                str(run),
                "--hypothesis-id",
                "H1",
                "--statement",
                "A bounded hypothesis.",
                "--rationale",
                "It distinguishes two candidate explanations.",
            ]
        )
        == 0
    )
    capsys.readouterr()

    assert (
        cli.main(
            [
                "record-action",
                "--run",
                str(run),
                "--action-id",
                "A1",
                "--action-type",
                "baseline_audit",
                "--status",
                "completed",
                "--summary",
                "The baseline was reproduced.",
                "--cost-units",
                "1",
            ]
        )
        == 0
    )
    state = json.loads(capsys.readouterr().out)
    assert state["budget"]["actions_remaining"] == 0
    assert state["actions"][0]["action_id"] == "A1"


def test_research_loop_cli_fails_closed(tmp_path: Path, capsys) -> None:
    missing = tmp_path / "missing"

    assert cli.main(["verify", "--run", str(missing)]) == 1
    assert "Research loop command failed" in capsys.readouterr().err


@pytest.mark.parametrize(
    "command",
    [
        "execute-nasa-audit",
        "execute-nasa-target-reference",
        "execute-nasa-protocol-stratification",
    ],
)
def test_legacy_execute_commands_route_through_authorized_wrapper(
    command: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = tmp_path / "run"
    registry = tmp_path / "planning-registry.json"
    request = tmp_path / "request.json"
    captured: dict[str, object] = {}

    def fake_execute(
        adapter_id: str,
        *,
        repository_root: Path,
        research_run: Path,
        action_registry_path: Path,
        request_path: Path,
    ) -> dict[str, object]:
        captured.update(
            {
                "adapter_id": adapter_id,
                "repository_root": repository_root,
                "research_run": research_run,
                "action_registry_path": action_registry_path,
                "request_path": request_path,
            }
        )
        return {"execution_status": "completed"}

    monkeypatch.setattr(cli, "execute_authorized_action", fake_execute)
    args = cli.build_parser().parse_args(
        [
            command,
            "--repository-root",
            str(tmp_path),
            "--run",
            str(run),
            "--registry",
            str(registry),
            "--request",
            str(request),
        ]
    )

    result = cli._run_command(args)

    assert result["execution_status"] == "completed"
    assert captured == {
        "adapter_id": "nasa-battery",
        "repository_root": tmp_path,
        "research_run": run,
        "action_registry_path": registry,
        "request_path": request,
    }


@pytest.mark.parametrize(
    "command",
    [
        "execute-nasa-audit",
        "execute-nasa-target-reference",
        "execute-nasa-protocol-stratification",
    ],
)
def test_legacy_execute_commands_require_authorization_context(
    command: str,
    tmp_path: Path,
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        cli.build_parser().parse_args(
            [command, "--request", str(tmp_path / "request.json")]
        )

    assert exc_info.value.code == 2


def test_cycle_nested_failed_execution_returns_nonzero_exit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
) -> None:
    monkeypatch.setattr(
        cli,
        "_run_command",
        lambda args: {
            "cycle_status": "one_action_executed",
            "execution": {"execution_status": "failed"},
        },
    )

    exit_code = cli.main(["verify", "--run", str(tmp_path / "unused")])

    assert exit_code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["execution"]["execution_status"] == "failed"


def test_cycle_nested_completed_execution_returns_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
) -> None:
    monkeypatch.setattr(
        cli,
        "_run_command",
        lambda args: {
            "cycle_status": "one_action_executed",
            "execution": {"execution_status": "completed"},
        },
    )

    assert cli.main(["verify", "--run", str(tmp_path / "unused")]) == 0
    capsys.readouterr()


def test_top_level_failed_execution_still_returns_nonzero_exit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
) -> None:
    monkeypatch.setattr(
        cli,
        "_run_command",
        lambda args: {"execution_status": "failed"},
    )

    assert cli.main(["verify", "--run", str(tmp_path / "unused")]) == 2
    capsys.readouterr()
