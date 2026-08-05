from __future__ import annotations

import json
from pathlib import Path

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
