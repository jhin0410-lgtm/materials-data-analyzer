from __future__ import annotations

import json
from pathlib import Path

import materials_data_analyzer.research_loop_cli as cli
from materials_data_analyzer.research_loop import initialize_research_loop

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "configs/research/nasa_research_action_registry.v1.json"


def _research_run(tmp_path: Path, *, maximum_cost_units: int = 10) -> Path:
    objective = tmp_path / "objective.json"
    objective.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "research_id": "nasa-policy-cli-test",
                "question": "What is the next bounded NASA action?",
                "metrics": {"primary": "battery_macro_mae", "secondary": []},
                "constraints": ["preserve_negative_results"],
                "budget": {
                    "maximum_actions": 3,
                    "maximum_cost_units": maximum_cost_units,
                },
                "stop_rules": ["budget_exhausted"],
            }
        ),
        encoding="utf-8",
    )
    run = tmp_path / "research"
    initialize_research_loop(objective, run)
    return run


def test_cli_plans_initial_available_audit_action(tmp_path: Path, capsys) -> None:
    run = _research_run(tmp_path)

    assert (
        cli.main(
            [
                "plan-nasa-next-action",
                "--run",
                str(run),
                "--registry",
                str(REGISTRY),
                "--repository-root",
                str(ROOT),
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["selection_status"] == "ready_to_execute"
    assert result["selected_action"]["action_type"] == (
        "audit_existing_battery_run"
    )


def test_cli_reports_budget_block_without_execution(tmp_path: Path, capsys) -> None:
    run = _research_run(tmp_path, maximum_cost_units=1)

    assert (
        cli.main(
            [
                "plan-nasa-next-action",
                "--run",
                str(run),
                "--registry",
                str(REGISTRY),
                "--repository-root",
                str(ROOT),
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["selection_status"] == "blocked_by_budget"
    assert result["actions_remaining"] == 3
    assert result["cost_units_remaining"] == 1
