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


def _run(tmp_path: Path) -> Path:
    objective = tmp_path / "objective.json"
    objective.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "research_id": "protocol-policy-test",
                "question": "Which protocol-aware action follows the audit?",
                "metrics": {"primary": "battery_macro_mae", "secondary": []},
                "constraints": ["preserve_negative_results"],
                "budget": {"maximum_actions": 6, "maximum_cost_units": 20},
                "stop_rules": ["budget_exhausted", "external_evidence_required"],
            }
        ),
        encoding="utf-8",
    )
    run = tmp_path / "research"
    initialize_research_loop(objective, run)
    return run


def _report(tmp_path: Path, name: str, payload: dict[str, object]) -> Path:
    directory = tmp_path / name
    directory.mkdir()
    path = directory / "action_result.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _audit(run: Path, tmp_path: Path) -> None:
    append_action(
        run,
        action_id="A1",
        action_type="audit_existing_battery_run",
        status="completed",
        summary="Audit completed.",
        cost_units=2,
        artifact_paths=[
            _report(
                tmp_path,
                "audit",
                {
                    "execution_status": "completed",
                    "outcomes": ["pooled_error_instability_detected"],
                    "evidence_level_after": "Unsupported",
                },
            )
        ],
    )


def _protocol(
    run: Path,
    tmp_path: Path,
    *,
    status: str = "completed",
    outcome: str | None = None,
) -> Path:
    report = _report(
        tmp_path,
        "protocol",
        {
            "execution_status": status,
            "outcome": outcome,
            "error": "forced protocol failure" if status == "failed" else None,
        },
    )
    append_action(
        run,
        action_id="A2",
        action_type="protocol_stratification",
        status=status,
        summary="Protocol action recorded.",
        cost_units=5,
        artifact_paths=[report],
    )
    return report


def _verified_stub(_: Path) -> dict[str, object]:
    return {"valid": True}


def _stub_verifiers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(policy, "verify_nasa_audit_action_report", _verified_stub)
    monkeypatch.setattr(
        policy, "verify_nasa_protocol_stratification_report", _verified_stub
    )


def test_policy_routes_protocol_to_specialized_execution_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _run(tmp_path)
    _audit(run, tmp_path)
    monkeypatch.setattr(policy, "verify_nasa_audit_action_report", _verified_stub)

    result = plan_nasa_next_action(run, REGISTRY, ROOT)

    selected = result["selected_action"]
    assert result["selection_status"] == "ready_to_execute"
    assert selected["action_type"] == "protocol_stratification"
    assert selected["availability"] == "available"
    assert selected["action_version"] == "1.0"
    assert selected["cost_units"] == 5
    assert selected["execution_registry_id"] == (
        "nasa-protocol-stratification-actions-v1"
    )
    assert Path(selected["execution_registry_path"]).name == (
        "nasa_protocol_stratification_action_registry.v1.json"
    )


@pytest.mark.parametrize(
    "outcome",
    ["protocol_metadata_insufficient", "protocol_groups_too_small"],
)
def test_protocol_data_limits_prioritize_external_requirement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    outcome: str,
) -> None:
    run = _run(tmp_path)
    _audit(run, tmp_path)
    report = _protocol(run, tmp_path, outcome=outcome)
    _stub_verifiers(monkeypatch)

    result = plan_nasa_next_action(run, REGISTRY, ROOT)

    selected = result["selected_action"]
    assert result["policy_version"] == "1.4"
    assert result["selection_status"] == "ready_to_execute"
    assert selected["action_type"] == "external_data_requirement_generation"
    assert selected["availability"] == "available"
    assert selected["action_version"] == "1.0"
    assert selected["score"] == 135
    assert selected["execution_registry_id"] == (
        "nasa-external-data-requirement-actions-v1"
    )
    assert Path(selected["execution_registry_path"]).name == (
        "nasa_external_data_requirement_action_registry.v1.json"
    )
    assert result["latest_protocol_stratification_report"] == str(report)
    assert result["latest_protocol_stratification_outcome"] == outcome


def test_protocol_completed_result_continues_to_source_cohort(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _run(tmp_path)
    _audit(run, tmp_path)
    _protocol(run, tmp_path, outcome="protocol_effect_not_supported")
    _stub_verifiers(monkeypatch)

    result = plan_nasa_next_action(run, REGISTRY, ROOT)

    assert result["selection_status"] == "blocked_unimplemented_action"
    assert result["selected_action"]["action_type"] == (
        "source_cohort_leave_one_out"
    )
    assert result["latest_protocol_stratification_outcome"] == (
        "protocol_effect_not_supported"
    )


def test_failed_protocol_action_requires_verified_manual_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _run(tmp_path)
    _audit(run, tmp_path)
    report = _protocol(run, tmp_path, status="failed")
    _stub_verifiers(monkeypatch)

    result = plan_nasa_next_action(run, REGISTRY, ROOT)

    assert result["selection_status"] == "manual_review_required"
    assert result["selected_action"] is None
    assert result["latest_failed_action_type"] == "protocol_stratification"
    assert result["latest_failed_action_report"] == str(report)
    assert result["latest_failed_action_error"] == "forced protocol failure"
