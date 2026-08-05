from __future__ import annotations

import json
from pathlib import Path

import pytest

import materials_data_analyzer.research_loop.nasa_action_policy as policy
from materials_data_analyzer.research_loop import (
    append_action,
    initialize_research_loop,
    plan_nasa_next_action,
)

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "configs/research/nasa_research_action_registry.v1.json"


def test_post_audit_policy_respects_exhausted_action_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    objective = tmp_path / "objective.json"
    objective.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "research_id": "post-audit-budget-test",
                "question": "Can another action be selected after the action count is exhausted?",
                "metrics": {"primary": "battery_macro_mae", "secondary": []},
                "constraints": ["preserve_negative_results"],
                "budget": {"maximum_actions": 1, "maximum_cost_units": 20},
                "stop_rules": ["budget_exhausted"],
            }
        ),
        encoding="utf-8",
    )
    run = tmp_path / "research"
    initialize_research_loop(objective, run)
    report = tmp_path / "action_result.json"
    report.write_text(
        json.dumps(
            {
                "execution_status": "completed",
                "outcomes": ["target_or_reference_flags_detected"],
                "evidence_level_after": "Unsupported",
            }
        ),
        encoding="utf-8",
    )
    append_action(
        run,
        action_id="A1",
        action_type="audit_existing_battery_run",
        status="completed",
        summary="Completed audit.",
        cost_units=2,
        artifact_paths=[report],
    )
    monkeypatch.setattr(
        policy,
        "verify_nasa_audit_action_report",
        lambda _: {"valid": True},
    )

    result = plan_nasa_next_action(run, REGISTRY, ROOT)

    assert result["actions_remaining"] == 0
    assert result["selection_status"] == "blocked_by_budget"
    assert result["selected_action"]["action_type"] == "target_reference_sensitivity"
