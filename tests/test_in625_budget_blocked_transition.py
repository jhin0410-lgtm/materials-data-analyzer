from __future__ import annotations

import json
from pathlib import Path

from materials_data_analyzer.research_loop.action_authorization import (
    assess_current_action_authorization,
)
from materials_data_analyzer.research_loop.kernel import initialize_research_loop
from materials_data_analyzer.research_loop.planning_adapter import plan_research_next_action
from materials_data_analyzer.research_loop.planning_transition import (
    build_current_research_transition,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRY = REPO_ROOT / "configs/research/in625_external_evidence_action_registry.v1.json"


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def test_in625_budget_shortfall_is_a_supported_blocked_transition(tmp_path: Path) -> None:
    objective = tmp_path / "objective.json"
    _write_json(
        objective,
        {
            "schema_version": "1.0",
            "research_id": "in625-budget-blocked",
            "question": "Can the registered IN625 external source be acquired within this budget?",
            "metrics": {"primary": "source provenance", "secondary": []},
            "constraints": ["No scientific promotion"],
            "budget": {"maximum_actions": 1, "maximum_cost_units": 1},
            "stop_rules": ["Stop when the registered action cannot be funded"],
        },
    )
    run = tmp_path / "run"
    initialize_research_loop(objective, run)

    plan = plan_research_next_action(
        "in625-external-evidence",
        repository_root=REPO_ROOT,
        research_run=run,
        action_registry_path=REGISTRY,
    )
    assert plan["selection_status"] == "budget_blocked"
    assert plan["selected_action"] is None

    transition = build_current_research_transition(
        "in625-external-evidence",
        repository_root=REPO_ROOT,
        research_run=run,
        action_registry_path=REGISTRY,
    )
    assert transition["planning_stop_status"] == "operationally_blocked"
    assert transition["planning_selection_status"] == "budget_blocked"
    assert transition["transition_type"] == "blocked"
    assert transition["action_executed"] is False
    assert transition["scientific_evidence_upgraded"] is False

    authorization = assess_current_action_authorization(
        "in625-external-evidence",
        repository_root=REPO_ROOT,
        research_run=run,
        action_registry_path=REGISTRY,
    )
    assert authorization["authorization_status"] == "not_authorizable_current_state"
    assert authorization["action_executed"] is False
    assert authorization["scientific_evidence_upgraded"] is False
