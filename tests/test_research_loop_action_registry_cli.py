from __future__ import annotations

import json
from pathlib import Path

import materials_data_analyzer.research_loop_cli as cli

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "configs/research/nasa_research_action_registry.v1.json"


def _registry_args() -> list[str]:
    return [
        "--registry",
        str(REGISTRY),
        "--repository-root",
        str(ROOT),
    ]


def test_action_registry_cli_validates_and_lists(capsys) -> None:
    assert cli.main(["validate-actions", *_registry_args()]) == 0
    validated = json.loads(capsys.readouterr().out)
    assert validated["valid"] is True
    assert validated["available_action_count"] == 4
    assert validated["planned_action_count"] == 7

    assert cli.main(["list-actions", *_registry_args()]) == 0
    actions = json.loads(capsys.readouterr().out)
    assert len(actions) == 11
    assert [action["action_type"] for action in actions] == sorted(
        action["action_type"] for action in actions
    )


def test_action_registry_cli_describes_exact_action(capsys) -> None:
    assert (
        cli.main(
            [
                "describe-action",
                *_registry_args(),
                "--action-type",
                "run_fixed_battery_intelligence",
            ]
        )
        == 0
    )
    action = json.loads(capsys.readouterr().out)
    assert action["availability"] == "available"
    assert action["binding"]["name"] == "mda-battery-intelligence"
    assert action["cost_units"] == 10


def test_action_registry_cli_fails_closed_on_unknown_action(capsys) -> None:
    assert (
        cli.main(
            [
                "describe-action",
                *_registry_args(),
                "--action-type",
                "unregistered_action",
            ]
        )
        == 1
    )
    assert "unknown action_type" in capsys.readouterr().err
