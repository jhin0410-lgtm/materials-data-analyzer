from __future__ import annotations

import json
from pathlib import Path

import pytest

import materials_data_analyzer.research_loop.nasa_action_policy as policy
from materials_data_analyzer.research_loop import (
    NasaActionPolicyError,
    append_action,
    append_stop,
    initialize_research_loop,
    plan_nasa_next_action,
)

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "configs/research/nasa_research_action_registry.v1.json"


def _objective(
    path: Path,
    *,
    maximum_actions: int = 5,
    maximum_cost_units: int = 20,
) -> Path:
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "research_id": "nasa-policy-test",
                "question": "Which bounded action should follow the verified audit?",
                "metrics": {"primary": "battery_macro_mae", "secondary": []},
                "constraints": ["preserve_negative_results"],
                "budget": {
                    "maximum_actions": maximum_actions,
                    "maximum_cost_units": maximum_cost_units,
                },
                "stop_rules": ["budget_exhausted", "external_evidence_required"],
            }
        ),
        encoding="utf-8",
    )
    return path


def _run(tmp_path: Path, **budget) -> Path:
    run = tmp_path / "research"
    initialize_research_loop(
        _objective(tmp_path / "objective.json", **budget),
        run,
    )
    return run


def _audit_action(
    run: Path,
    tmp_path: Path,
    *,
    status: str,
    outcomes: list[str] | None = None,
    evidence_level: str = "Unsupported",
) -> Path:
    report = tmp_path / "action_result.json"
    report.write_text(
        json.dumps(
            {
                "execution_status": status,
                "outcomes": outcomes or [],
                "evidence_level_after": evidence_level,
                "error": "forced failure" if status == "failed" else None,
            }
        ),
        encoding="utf-8",
    )
    append_action(
        run,
        action_id="A1",
        action_type="audit_existing_battery_run",
        status=status,
        summary="Recorded audit action.",
        cost_units=2,
        artifact_paths=[report],
    )
    return report


def _target_action(
    run: Path,
    tmp_path: Path,
    *,
    status: str,
    outcome: str | None = None,
    error: str | None = None,
) -> Path:
    action_directory = tmp_path / "target-action"
    action_directory.mkdir()
    report = action_directory / "action_result.json"
    report.write_text(
        json.dumps(
            {
                "execution_status": status,
                "outcome": outcome,
                "error": error,
            }
        ),
        encoding="utf-8",
    )
    append_action(
        run,
        action_id="A2",
        action_type="target_reference_sensitivity",
        status=status,
        summary="Recorded target-reference action.",
        cost_units=4,
        artifact_paths=[report],
    )
    return report


def _verified_stub(_: Path) -> dict[str, object]:
    return {"valid": True}


def _stub_verifiers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(policy, "verify_nasa_audit_action_report", _verified_stub)
    monkeypatch.setattr(policy, "verify_nasa_target_reference_report", _verified_stub)


def test_policy_selects_available_audit_before_any_audit_action(tmp_path: Path) -> None:
    result = plan_nasa_next_action(_run(tmp_path), REGISTRY, ROOT)

    assert result["selection_status"] == "ready_to_execute"
    assert result["selected_action"]["action_type"] == "audit_existing_battery_run"
    assert result["selected_action"]["availability"] == "available"
    assert result["selected_action"]["cost_units"] == 2
    assert result["selected_action"]["execution_registry_path"] == str(REGISTRY)


def test_policy_respects_budget_before_initial_audit(tmp_path: Path) -> None:
    result = plan_nasa_next_action(
        _run(tmp_path, maximum_actions=2, maximum_cost_units=1),
        REGISTRY,
        ROOT,
    )

    assert result["selection_status"] == "blocked_by_budget"
    assert result["selected_action"]["action_type"] == "audit_existing_battery_run"


def test_policy_routes_target_action_to_verified_execution_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _run(tmp_path)
    _audit_action(
        run,
        tmp_path,
        status="completed",
        outcomes=[
            "target_or_reference_flags_detected",
            "pooled_error_instability_detected",
        ],
    )
    monkeypatch.setattr(policy, "verify_nasa_audit_action_report", _verified_stub)

    first = plan_nasa_next_action(run, REGISTRY, ROOT)
    second = plan_nasa_next_action(run, REGISTRY, ROOT)

    assert first == second
    assert first["selection_status"] == "ready_to_execute"
    selected = first["selected_action"]
    assert selected["action_type"] == "target_reference_sensitivity"
    assert selected["score"] == 120
    assert selected["availability"] == "available"
    assert selected["action_version"] == "1.0"
    assert selected["execution_registry_id"] == "nasa-target-reference-actions-v1"
    execution_registry_path = Path(selected["execution_registry_path"])
    assert execution_registry_path.name == (
        "nasa_target_reference_action_registry.v1.json"
    )
    assert execution_registry_path.parent.name == "research"
    assert execution_registry_path.parent.parent.name == "configs"
    assert len(selected["execution_registry_sha256"]) == 64
    assert [item["action_type"] for item in first["candidates"]][:3] == [
        "target_reference_sensitivity",
        "protocol_stratification",
        "source_cohort_leave_one_out",
    ]
    assert first["candidates"][0]["availability"] == "available"
    assert first["candidates"][1]["availability"] == "available"
    assert all(
        item["availability"] == "planned" for item in first["candidates"][2:]
    )


def test_stable_target_result_continues_to_protocol_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _run(tmp_path)
    _audit_action(
        run,
        tmp_path,
        status="completed",
        outcomes=[
            "target_or_reference_flags_detected",
            "pooled_error_instability_detected",
        ],
    )
    target_report = _target_action(
        run,
        tmp_path,
        status="completed",
        outcome="conclusion_stable_across_defensible_targets",
    )
    _stub_verifiers(monkeypatch)

    result = plan_nasa_next_action(run, REGISTRY, ROOT)

    assert result["policy_version"] == "1.3"
    assert result["selection_status"] == "ready_to_execute"
    assert result["selected_action"]["action_type"] == "protocol_stratification"
    assert result["selected_action"]["cost_units"] == 5
    assert result["latest_target_reference_report"] == str(target_report)
    assert result["latest_target_reference_outcome"] == (
        "conclusion_stable_across_defensible_targets"
    )
    assert all(
        item["action_type"] != "target_reference_sensitivity"
        for item in result["candidates"]
    )


@pytest.mark.parametrize(
    "outcome",
    [
        "conclusion_sensitive_to_target_reference",
        "alternative_target_not_scientifically_defensible",
    ],
)
def test_unresolved_target_result_requires_manual_review(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    outcome: str,
) -> None:
    run = _run(tmp_path)
    _audit_action(
        run,
        tmp_path,
        status="completed",
        outcomes=["target_or_reference_flags_detected"],
    )
    _target_action(run, tmp_path, status="completed", outcome=outcome)
    _stub_verifiers(monkeypatch)

    result = plan_nasa_next_action(run, REGISTRY, ROOT)

    assert result["selection_status"] == "manual_review_required"
    assert result["selected_action"] is None
    assert result["latest_target_reference_outcome"] == outcome


def test_missing_target_reference_metadata_prioritizes_data_requirement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _run(tmp_path)
    _audit_action(
        run,
        tmp_path,
        status="completed",
        outcomes=["target_or_reference_flags_detected"],
    )
    _target_action(
        run,
        tmp_path,
        status="completed",
        outcome="required_reference_metadata_missing",
    )
    _stub_verifiers(monkeypatch)

    result = plan_nasa_next_action(run, REGISTRY, ROOT)

    assert result["selection_status"] == "blocked_unimplemented_action"
    assert result["selected_action"]["action_type"] == (
        "external_data_requirement_generation"
    )
    assert result["selected_action"]["score"] == 140
    assert result["selected_action"]["trigger"] == (
        "required_reference_metadata_missing"
    )


def test_failed_target_action_requires_review_and_is_not_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _run(tmp_path)
    _audit_action(
        run,
        tmp_path,
        status="completed",
        outcomes=[
            "target_or_reference_flags_detected",
            "pooled_error_instability_detected",
        ],
    )
    target_report = _target_action(
        run,
        tmp_path,
        status="failed",
        error="forced target failure",
    )
    _stub_verifiers(monkeypatch)

    result = plan_nasa_next_action(run, REGISTRY, ROOT)

    assert result["selection_status"] == "manual_review_required"
    assert result["selected_action"] is None
    assert result["latest_failed_action_type"] == "target_reference_sensitivity"
    assert result["latest_failed_action_report"] == str(target_report)
    assert result["latest_failed_action_error"] == "forced target failure"


def test_other_failed_post_audit_action_requires_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _run(tmp_path)
    _audit_action(
        run,
        tmp_path,
        status="completed",
        outcomes=["pooled_error_instability_detected"],
    )
    action_directory = tmp_path / "protocol-failure"
    action_directory.mkdir()
    diagnostic = action_directory / "action_result.json"
    diagnostic.write_text(
        json.dumps(
            {
                "execution_status": "failed",
                "outcome": None,
                "error": "Forced protocol failure.",
            }
        ),
        encoding="utf-8",
    )
    append_action(
        run,
        action_id="A2",
        action_type="protocol_stratification",
        status="failed",
        summary="Forced protocol failure.",
        cost_units=5,
        artifact_paths=[diagnostic],
    )
    monkeypatch.setattr(policy, "verify_nasa_audit_action_report", _verified_stub)
    monkeypatch.setattr(
        policy, "verify_nasa_protocol_stratification_report", _verified_stub
    )

    result = plan_nasa_next_action(run, REGISTRY, ROOT)

    assert result["selection_status"] == "manual_review_required"
    assert result["selected_action"] is None
    assert result["latest_failed_action_type"] == "protocol_stratification"
    assert result["latest_failed_action_report"] == str(diagnostic)
    assert result["latest_failed_action_error"] == "Forced protocol failure."


def test_partial_dimensions_prioritize_exact_data_requirement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _run(tmp_path)
    _audit_action(
        run,
        tmp_path,
        status="completed",
        outcomes=["partial_dimensions_inconclusive"],
    )
    monkeypatch.setattr(policy, "verify_nasa_audit_action_report", _verified_stub)

    result = plan_nasa_next_action(run, REGISTRY, ROOT)

    assert result["selected_action"]["action_type"] == (
        "external_data_requirement_generation"
    )
    assert result["selection_status"] == "blocked_unimplemented_action"


def test_no_audit_flag_selects_feature_ablation_baseline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _run(tmp_path)
    _audit_action(
        run,
        tmp_path,
        status="completed",
        outcomes=["no_audit_flag_with_complete_dimensions"],
    )
    monkeypatch.setattr(policy, "verify_nasa_audit_action_report", _verified_stub)

    result = plan_nasa_next_action(run, REGISTRY, ROOT)

    assert result["selected_action"]["action_type"] == "feature_family_ablation"
    assert result["selected_action"]["score"] == 85


def test_failed_audit_requires_review_and_is_not_repeated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _run(tmp_path)
    _audit_action(run, tmp_path, status="failed")
    monkeypatch.setattr(policy, "verify_nasa_audit_action_report", _verified_stub)

    result = plan_nasa_next_action(run, REGISTRY, ROOT)

    assert result["selection_status"] == "manual_review_required"
    assert result["selected_action"] is None
    assert result["latest_audit_error"] == "forced failure"


def test_stopped_research_has_no_next_action(tmp_path: Path) -> None:
    run = _run(tmp_path)
    append_stop(run, reason_code="external_evidence_required", summary="Stopped.")

    result = plan_nasa_next_action(run, REGISTRY, ROOT)

    assert result["selection_status"] == "research_stopped"
    assert result["selected_action"] is None
    assert result["candidates"] == []


def test_policy_requires_exactly_one_bound_audit_report(tmp_path: Path) -> None:
    run = _run(tmp_path)
    unrelated = tmp_path / "other.json"
    unrelated.write_text("{}\n", encoding="utf-8")
    append_action(
        run,
        action_id="A1",
        action_type="audit_existing_battery_run",
        status="completed",
        summary="Invalid report binding fixture.",
        cost_units=2,
        artifact_paths=[unrelated],
    )

    with pytest.raises(NasaActionPolicyError, match="exactly one"):
        plan_nasa_next_action(run, REGISTRY, ROOT)
