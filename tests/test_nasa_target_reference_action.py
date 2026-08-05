from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from materials_data_analyzer.research_loop import (
    NasaTargetReferenceActionError,
    execute_nasa_audit_action,
    execute_nasa_target_reference_action,
    initialize_research_loop,
    load_action_registry,
    load_research_state,
    plan_nasa_next_action,
    verify_nasa_target_reference_report,
)
from platform_core.battery_intelligence import BatteryIntelligenceConfig

ROOT = Path(__file__).resolve().parents[1]
PLANNER_REGISTRY = ROOT / "configs/research/nasa_research_action_registry.v1.json"
TARGET_REGISTRY = (
    ROOT / "configs/research/nasa_target_reference_action_registry.v1.json"
)


def _objective(path: Path, *, maximum_cost: int = 20) -> Path:
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "research_id": "target-reference-action-test",
                "question": "Is the model conclusion robust to fixed reference definitions?",
                "metrics": {
                    "primary": "battery_macro_mae",
                    "secondary": ["worst_battery_mae"],
                },
                "constraints": [
                    "no_model_refit",
                    "no_target_repair",
                    "no_battery_exclusion",
                ],
                "budget": {
                    "maximum_actions": 4,
                    "maximum_cost_units": maximum_cost,
                },
                "stop_rules": ["budget_exhausted", "external_evidence_required"],
            }
        ),
        encoding="utf-8",
    )
    return path


def _analysis_run(path: Path) -> Path:
    tables = path / "tables"
    reports = path / "reports"
    tables.mkdir(parents=True)
    reports.mkdir(parents=True)
    cycles: list[dict[str, float | int | str]] = []
    forecasts: list[dict[str, float | int | str]] = []
    predictions: list[dict[str, float | int | str]] = []
    for battery in range(4):
        battery_id = f"B{battery}"
        reference = 2.0 + 0.1 * battery
        for cycle in range(1, 7):
            target = 100.0 - float(cycle)
            cycles.append(
                {
                    "battery_id": battery_id,
                    "cycle_index": cycle,
                    "capacity_retention_percent": target,
                    "reference_capacity_ah": reference,
                    "discharge_capacity_ah": reference * target / 100.0,
                    "ambient_temperature_c": 25.0 + battery,
                }
            )
        for origin in (1, 2, 3):
            target_cycle = origin + 2
            actual = 100.0 - float(target_cycle)
            forecasts.append(
                {
                    "battery_id": battery_id,
                    "origin_cycle": origin,
                    "target_cycle": target_cycle,
                    "future_target": actual,
                    "current_target": 100.0 - float(origin),
                }
            )
            predictions.append(
                {
                    "battery_id": battery_id,
                    "origin_cycle": origin,
                    "target_cycle": target_cycle,
                    "actual": actual,
                    "persistence_prediction": actual + 1.0,
                    "ridge_prediction": actual + 2.0,
                }
            )
    pd.DataFrame(cycles).to_csv(
        tables / "validated_cycle_summary.csv", index=False
    )
    pd.DataFrame(forecasts).to_csv(
        tables / "forecast_feature_table.csv", index=False
    )
    pd.DataFrame(predictions).to_csv(
        tables / "validation_predictions.csv", index=False
    )
    config = BatteryIntelligenceConfig(n_splits=2, knee_bootstrap_samples=0)
    (path / "config_snapshot.json").write_text(
        json.dumps({"config": config.to_dict()}), encoding="utf-8"
    )
    closeout = {
        "evidence_level": "Unsupported",
        "component_statuses": {},
        "strongest_evidence": {},
        "limitations": [],
        "primary_limitation": "The fixed Ridge model does not beat persistence.",
    }
    (reports / "scientific_closeout.json").write_text(
        json.dumps(closeout), encoding="utf-8"
    )
    (reports / "scientific_closeout.md").write_text(
        "# Scientific Closeout\n", encoding="utf-8"
    )
    (path / "run_manifest.json").write_text(
        json.dumps(
            {
                "artifact_paths": [],
                "artifact_checksums": {},
                "scientific_closeout": closeout,
                "scientific_validation": "Unsupported",
                "limitations": [],
            }
        ),
        encoding="utf-8",
    )
    return path


def _request(
    path: Path,
    *,
    action_id: str,
    action_type: str,
    research_run: Path,
    analysis_run: Path,
    registry: Path,
) -> Path:
    registry_sha = load_action_registry(
        registry, repository_root=ROOT
    )["registry_sha256"]
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "action_id": action_id,
                "action_type": action_type,
                "research_run": str(research_run),
                "analysis_run": str(analysis_run),
                "registry": str(registry),
                "repository_root": str(ROOT),
                "expected_registry_sha256": registry_sha,
            }
        ),
        encoding="utf-8",
    )
    return path


def _initialize_with_audit(tmp_path: Path) -> tuple[Path, Path]:
    research_run = tmp_path / "research"
    analysis_run = _analysis_run(tmp_path / "analysis")
    initialize_research_loop(_objective(tmp_path / "objective.json"), research_run)
    audit_request = _request(
        tmp_path / "audit-request.json",
        action_id="AUDIT-1",
        action_type="audit_existing_battery_run",
        research_run=research_run,
        analysis_run=analysis_run,
        registry=PLANNER_REGISTRY,
    )
    audit = execute_nasa_audit_action(audit_request)
    assert audit["execution_status"] == "completed"
    return research_run, analysis_run


def _input_bytes(analysis_run: Path) -> dict[str, bytes]:
    paths = (
        "tables/validated_cycle_summary.csv",
        "tables/validation_predictions.csv",
        "config_snapshot.json",
        "reports/target_comparability_audit.json",
        "reports/scientific_closeout.json",
        "run_manifest.json",
    )
    return {relative: (analysis_run / relative).read_bytes() for relative in paths}


def test_target_reference_action_executes_verifies_and_preserves_inputs(
    tmp_path: Path,
) -> None:
    research_run, analysis_run = _initialize_with_audit(tmp_path)
    request = _request(
        tmp_path / "target-request.json",
        action_id="TARGET-1",
        action_type="target_reference_sensitivity",
        research_run=research_run,
        analysis_run=analysis_run,
        registry=TARGET_REGISTRY,
    )
    before = _input_bytes(analysis_run)

    result = execute_nasa_target_reference_action(request)

    assert result["execution_status"] == "completed"
    assert result["outcome"] == "conclusion_stable_across_defensible_targets"
    assert _input_bytes(analysis_run) == before
    report_path = Path(result["action_report"])
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert all(report["verification"].values())
    assert report["summary"]["primary_reference_id"] == "declared_reference"
    assert len(report["summary"]["ridge_vs_persistence"]) == 3
    assert {
        item["preferred_model"]
        for item in report["summary"]["ridge_vs_persistence"]
    } == {"persistence"}

    state = load_research_state(research_run)
    assert state["budget"]["actions_used"] == 2
    assert state["budget"]["cost_units_used"] == 6
    assert state["actions"][-1]["action_type"] == "target_reference_sensitivity"
    assert state["actions"][-1]["status"] == "completed"

    verification = verify_nasa_target_reference_report(report_path)
    assert verification["valid"] is True
    assert verification["outcome"] == result["outcome"]


def test_target_action_requires_completed_verified_audit(tmp_path: Path) -> None:
    research_run = tmp_path / "research"
    analysis_run = _analysis_run(tmp_path / "analysis")
    initialize_research_loop(_objective(tmp_path / "objective.json"), research_run)
    request = _request(
        tmp_path / "target-request.json",
        action_id="TARGET-1",
        action_type="target_reference_sensitivity",
        research_run=research_run,
        analysis_run=analysis_run,
        registry=TARGET_REGISTRY,
    )

    with pytest.raises(
        NasaTargetReferenceActionError,
        match="completed audit_existing_battery_run",
    ):
        execute_nasa_target_reference_action(request)

    assert load_research_state(research_run)["actions"] == []


def test_target_report_verifier_detects_output_drift(tmp_path: Path) -> None:
    research_run, analysis_run = _initialize_with_audit(tmp_path)
    request = _request(
        tmp_path / "target-request.json",
        action_id="TARGET-1",
        action_type="target_reference_sensitivity",
        research_run=research_run,
        analysis_run=analysis_run,
        registry=TARGET_REGISTRY,
    )
    result = execute_nasa_target_reference_action(request)
    output = (
        research_run
        / "actions/TARGET-1/target_reference_sensitivity/model_metrics_by_reference.csv"
    )
    output.write_text("reference_id,model\n", encoding="utf-8")

    with pytest.raises(
        NasaTargetReferenceActionError,
        match="output no longer matches",
    ):
        verify_nasa_target_reference_report(result["action_report"])


def test_target_action_respects_cost_budget(tmp_path: Path) -> None:
    research_run = tmp_path / "research"
    analysis_run = _analysis_run(tmp_path / "analysis")
    initialize_research_loop(
        _objective(tmp_path / "objective.json", maximum_cost=5), research_run
    )
    audit_request = _request(
        tmp_path / "audit-request.json",
        action_id="AUDIT-1",
        action_type="audit_existing_battery_run",
        research_run=research_run,
        analysis_run=analysis_run,
        registry=PLANNER_REGISTRY,
    )
    assert execute_nasa_audit_action(audit_request)["execution_status"] == "completed"
    target_request = _request(
        tmp_path / "target-request.json",
        action_id="TARGET-1",
        action_type="target_reference_sensitivity",
        research_run=research_run,
        analysis_run=analysis_run,
        registry=TARGET_REGISTRY,
    )

    with pytest.raises(NasaTargetReferenceActionError, match="cost budget"):
        execute_nasa_target_reference_action(target_request)

    assert len(load_research_state(research_run)["actions"]) == 1


def test_planner_does_not_repeat_completed_target_action(tmp_path: Path) -> None:
    research_run, analysis_run = _initialize_with_audit(tmp_path)
    request = _request(
        tmp_path / "target-request.json",
        action_id="TARGET-1",
        action_type="target_reference_sensitivity",
        research_run=research_run,
        analysis_run=analysis_run,
        registry=TARGET_REGISTRY,
    )
    assert execute_nasa_target_reference_action(request)["execution_status"] == "completed"

    decision = plan_nasa_next_action(research_run, PLANNER_REGISTRY, ROOT)

    assert decision["selected_action"]["action_type"] != "target_reference_sensitivity"
    assert all(
        item["action_type"] != "target_reference_sensitivity"
        for item in decision["candidates"]
    )
