from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop import (
    LEDGER_FILENAME,
    STATE_FILENAME,
    ResearchLoopError,
    append_action,
    append_evidence,
    append_hypothesis,
    append_stop,
    initialize_research_loop,
    load_research_state,
    verify_research_loop,
)

ROOT = Path(__file__).resolve().parents[1]


def _write_objective(path: Path, **updates) -> Path:
    objective = {
        "schema_version": "1.0",
        "research_id": "nasa-exact-horizon-autopilot",
        "question": (
            "Can a bounded research loop identify a defensible path beyond the "
            "strongest origin-only battery baseline?"
        ),
        "metrics": {
            "primary": "battery_macro_mae",
            "secondary": ["worst_battery_mae", "source_cohort_macro_mae"],
        },
        "constraints": [
            "battery_disjoint_validation",
            "no_target_repair",
            "no_locked_test_reuse",
        ],
        "budget": {"maximum_actions": 2, "maximum_cost_units": 5},
        "stop_rules": [
            "hypothesis_resolved",
            "external_evidence_required",
            "budget_exhausted",
        ],
    }
    objective.update(updates)
    path.write_text(json.dumps(objective), encoding="utf-8")
    return path


def test_research_loop_initialization_and_verification(tmp_path: Path) -> None:
    objective = _write_objective(tmp_path / "objective.json")
    run = tmp_path / "run"

    state = initialize_research_loop(objective, run)
    verified = verify_research_loop(run)

    assert state["research_id"] == "nasa-exact-horizon-autopilot"
    assert state["status"] == "active"
    assert state["event_count"] == 1
    assert state["budget"]["actions_remaining"] == 2
    assert (run / LEDGER_FILENAME).is_file()
    assert (run / STATE_FILENAME).is_file()
    assert verified["valid"] is True
    assert verified["event_count"] == 1
    assert verified["latest_event_hash"] == state["latest_event_hash"]


def test_research_loop_records_checksum_bound_episode(tmp_path: Path) -> None:
    objective = _write_objective(tmp_path / "objective.json")
    run = tmp_path / "run"
    evidence = tmp_path / "baseline.json"
    artifact = tmp_path / "ablation.csv"
    evidence.write_text('{"mae": 3.6}\n', encoding="utf-8")
    artifact.write_text("feature_set,mae\ncapacity_only,3.7\n", encoding="utf-8")

    initialize_research_loop(objective, run)
    append_hypothesis(
        run,
        hypothesis_id="H1",
        statement="Protocol heterogeneity dominates signal-feature value.",
        rationale="Source-cohort errors are concentrated rather than uniform.",
    )
    append_evidence(
        run,
        evidence_id="E1",
        evidence_type="baseline_result",
        source_path=evidence,
        summary="Persistence remains the strongest predeclared baseline.",
    )
    state = append_action(
        run,
        action_id="A1",
        action_type="feature_family_ablation",
        status="completed",
        summary="Signal families did not improve battery-macro MAE.",
        cost_units=2,
        artifact_paths=[artifact],
    )

    assert state["event_count"] == 4
    assert state["budget"] == {
        "maximum_actions": 2,
        "actions_used": 1,
        "actions_remaining": 1,
        "maximum_cost_units": 5,
        "cost_units_used": 2,
        "cost_units_remaining": 3,
    }
    assert state["hypotheses"][0]["hypothesis_id"] == "H1"
    assert state["evidence"][0]["source_bytes"] == evidence.stat().st_size
    assert len(state["evidence"][0]["source_sha256"]) == 64
    assert state["actions"][0]["artifacts"][0]["bytes"] == artifact.stat().st_size
    assert verify_research_loop(run)["valid"] is True


def test_research_loop_fails_closed_on_duplicate_ids_and_budget(tmp_path: Path) -> None:
    objective = _write_objective(tmp_path / "objective.json")
    run = tmp_path / "run"
    initialize_research_loop(objective, run)
    append_hypothesis(
        run,
        hypothesis_id="H1",
        statement="A first hypothesis.",
        rationale="A bounded rationale.",
    )

    with pytest.raises(ResearchLoopError, match="duplicate hypothesis_id"):
        append_hypothesis(
            run,
            hypothesis_id="H1",
            statement="A duplicate hypothesis.",
            rationale="This must not overwrite the first hypothesis.",
        )

    append_action(
        run,
        action_id="A1",
        action_type="baseline_audit",
        status="completed",
        summary="The baseline was reproduced.",
        cost_units=3,
    )
    with pytest.raises(ResearchLoopError, match="cost budget"):
        append_action(
            run,
            action_id="A2",
            action_type="expensive_model",
            status="rejected",
            summary="The action exceeds the remaining research budget.",
            cost_units=3,
        )


def test_research_loop_stop_is_terminal(tmp_path: Path) -> None:
    objective = _write_objective(tmp_path / "objective.json")
    run = tmp_path / "run"
    initialize_research_loop(objective, run)
    stopped = append_stop(
        run,
        reason_code="external_evidence_required",
        summary="No protocol-compatible independent cohort is available.",
    )

    assert stopped["status"] == "stopped"
    assert stopped["stop"]["reason_code"] == "external_evidence_required"
    with pytest.raises(ResearchLoopError, match="stopped"):
        append_action(
            run,
            action_id="A1",
            action_type="post_stop_action",
            status="rejected",
            summary="A stopped run must remain immutable except for verification.",
            cost_units=0,
        )


def test_research_loop_detects_ledger_tampering(tmp_path: Path) -> None:
    objective = _write_objective(tmp_path / "objective.json")
    run = tmp_path / "run"
    initialize_research_loop(objective, run)

    ledger = run / LEDGER_FILENAME
    event = json.loads(ledger.read_text(encoding="utf-8"))
    event["payload"]["objective"]["question"] = "tampered question"
    ledger.write_text(json.dumps(event) + "\n", encoding="utf-8")

    with pytest.raises(ResearchLoopError, match="event hash mismatch"):
        verify_research_loop(run)


def test_research_loop_detects_snapshot_drift(tmp_path: Path) -> None:
    objective = _write_objective(tmp_path / "objective.json")
    run = tmp_path / "run"
    initialize_research_loop(objective, run)

    state_path = run / STATE_FILENAME
    snapshot = json.loads(state_path.read_text(encoding="utf-8"))
    snapshot["status"] = "stopped"
    state_path.write_text(json.dumps(snapshot), encoding="utf-8")

    with pytest.raises(ResearchLoopError, match="does not match"):
        load_research_state(run)


def test_research_objective_rejects_unknown_and_duplicate_keys(tmp_path: Path) -> None:
    unknown = _write_objective(tmp_path / "unknown.json", unexpected=True)
    with pytest.raises(ResearchLoopError, match="unknown keys"):
        initialize_research_loop(unknown, tmp_path / "unknown-run")

    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text(
        '{"schema_version":"1.0","schema_version":"1.0"}', encoding="utf-8"
    )
    with pytest.raises(ResearchLoopError, match="duplicate JSON key"):
        initialize_research_loop(duplicate, tmp_path / "duplicate-run")


def test_research_loop_is_installed_console_command() -> None:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        project = tomllib.load(handle)["project"]

    assert project["scripts"]["mda-research-loop"] == (
        "materials_data_analyzer.research_loop_cli:main"
    )
