from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

import materials_data_analyzer.research_loop.nasa_audit_executor as executor
from materials_data_analyzer.research_loop import (
    NasaAuditActionError,
    append_stop,
    execute_nasa_audit_action,
    initialize_research_loop,
    load_action_registry,
    load_research_state,
    verify_nasa_audit_action_report,
)
from platform_core.battery_intelligence import BatteryIntelligenceConfig

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "configs/research/nasa_research_action_registry.v1.json"


def _objective(path: Path, *, maximum_actions: int = 3, maximum_cost: int = 10) -> Path:
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "research_id": "typed-nasa-audit-test",
                "question": "Which existing Battery run limitations require the next research action?",
                "metrics": {
                    "primary": "battery_macro_mae",
                    "secondary": ["worst_battery_mae"],
                },
                "constraints": [
                    "no_battery_exclusion",
                    "preserve_negative_results",
                ],
                "budget": {
                    "maximum_actions": maximum_actions,
                    "maximum_cost_units": maximum_cost,
                },
                "stop_rules": ["external_evidence_required", "budget_exhausted"],
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

    cycle_rows: list[dict[str, object]] = []
    forecast_rows: list[dict[str, object]] = []
    prediction_rows: list[dict[str, object]] = []
    for battery in range(4):
        battery_id = f"B{battery}"
        cycles = [1, 2, 3, 4, 5, 6]
        if battery == 3:
            cycles = [1, 2, 4, 5, 6, 7]
        targets = [100.0, 99.0, 98.0, 97.0, 96.0, 95.0]
        if battery == 3:
            targets = [100.0, 99.0, 420.0, 96.0, 95.0, 94.0]
        for cycle, target in zip(cycles, targets, strict=True):
            reference = 2.0 if not (battery == 2 and cycle == 6) else 2.1
            cycle_rows.append(
                {
                    "battery_id": battery_id,
                    "cycle_index": cycle,
                    "capacity_retention_percent": target,
                    "reference_capacity_ah": reference,
                    "discharge_capacity_ah": reference * target / 100.0,
                    "ambient_temperature_c": 25.0 + battery * 10.0,
                }
            )
        for origin in (1, 2, 3):
            actual = 98.0 - origin
            forecast_rows.append(
                {
                    "battery_id": battery_id,
                    "origin_cycle": origin,
                    "target_cycle": origin + 2,
                    "future_target": actual,
                    "current_target": 100.0 - origin,
                }
            )
            persistence_error = 1.0 if battery < 3 else 100.0
            ridge_error = 2.0 if battery < 3 else 150.0
            prediction_rows.append(
                {
                    "battery_id": battery_id,
                    "origin_cycle": origin,
                    "target_cycle": origin + 2,
                    "actual": actual,
                    "persistence_prediction": actual + persistence_error,
                    "ridge_prediction": actual + ridge_error,
                }
            )

    pd.DataFrame(cycle_rows).to_csv(
        tables / "validated_cycle_summary.csv", index=False
    )
    pd.DataFrame(forecast_rows).to_csv(
        tables / "forecast_feature_table.csv", index=False
    )
    pd.DataFrame(prediction_rows).to_csv(
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
        "primary_limitation": "Original fixed-model limitation.",
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
    research_run: Path,
    analysis_run: Path,
    action_id: str = "A1",
    registry_sha: str | None = None,
) -> Path:
    registry_sha = registry_sha or load_action_registry(
        REGISTRY, repository_root=ROOT
    )["registry_sha256"]
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "action_id": action_id,
                "action_type": "audit_existing_battery_run",
                "research_run": str(research_run),
                "analysis_run": str(analysis_run),
                "registry": str(REGISTRY),
                "repository_root": str(ROOT),
                "expected_registry_sha256": registry_sha,
            }
        ),
        encoding="utf-8",
    )
    return path


def _immutable_bytes(analysis_run: Path) -> dict[str, bytes]:
    paths = (
        "tables/validated_cycle_summary.csv",
        "tables/forecast_feature_table.csv",
        "tables/validation_predictions.csv",
        "config_snapshot.json",
    )
    return {relative: (analysis_run / relative).read_bytes() for relative in paths}


def test_typed_nasa_audit_executes_verifies_and_records_ledger(tmp_path: Path) -> None:
    research_run = tmp_path / "research"
    analysis_run = _analysis_run(tmp_path / "analysis")
    initialize_research_loop(_objective(tmp_path / "objective.json"), research_run)
    request = _request(
        tmp_path / "request.json",
        research_run=research_run,
        analysis_run=analysis_run,
    )
    immutable_before = _immutable_bytes(analysis_run)

    result = execute_nasa_audit_action(request)

    assert result["execution_status"] == "completed"
    assert set(result["outcomes"]) == {
        "target_or_reference_flags_detected",
        "pooled_error_instability_detected",
    }
    report_path = Path(result["action_report"])
    assert report_path.is_file()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["evidence_level_before"] == "Unsupported"
    assert report["evidence_level_after"] == "Unsupported"
    assert all(report["verification"].values())
    assert _immutable_bytes(analysis_run) == immutable_before

    state = load_research_state(research_run)
    assert state["budget"]["actions_used"] == 1
    assert state["budget"]["cost_units_used"] == 2
    assert state["actions"][0]["status"] == "completed"
    assert state["actions"][0]["action_type"] == "audit_existing_battery_run"
    assert json.loads(
        (analysis_run / "reports/scientific_closeout.json").read_text(
            encoding="utf-8"
        )
    )["evidence_level"] == "Unsupported"

    verification = verify_nasa_audit_action_report(report_path)
    assert verification["valid"] is True
    assert verification["execution_status"] == "completed"


def test_preflight_rejection_does_not_consume_budget(tmp_path: Path) -> None:
    research_run = tmp_path / "research"
    analysis_run = _analysis_run(tmp_path / "analysis")
    initialize_research_loop(_objective(tmp_path / "objective.json"), research_run)
    request = _request(
        tmp_path / "request.json",
        research_run=research_run,
        analysis_run=analysis_run,
        registry_sha="0" * 64,
    )

    with pytest.raises(NasaAuditActionError, match="registry SHA-256"):
        execute_nasa_audit_action(request)

    state = load_research_state(research_run)
    assert state["actions"] == []
    assert not (research_run / "actions").exists()


def test_missing_required_run_input_fails_before_execution(tmp_path: Path) -> None:
    research_run = tmp_path / "research"
    analysis_run = _analysis_run(tmp_path / "analysis")
    (analysis_run / "tables/forecast_feature_table.csv").unlink()
    initialize_research_loop(_objective(tmp_path / "objective.json"), research_run)
    request = _request(
        tmp_path / "request.json",
        research_run=research_run,
        analysis_run=analysis_run,
    )

    with pytest.raises(NasaAuditActionError, match="missing required action inputs"):
        execute_nasa_audit_action(request)

    assert load_research_state(research_run)["actions"] == []


def test_execution_failure_rolls_back_and_records_failed_action(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    research_run = tmp_path / "research"
    analysis_run = _analysis_run(tmp_path / "analysis")
    initialize_research_loop(_objective(tmp_path / "objective.json"), research_run)
    request = _request(
        tmp_path / "request.json",
        research_run=research_run,
        analysis_run=analysis_run,
    )
    closeout_before = (analysis_run / "reports/scientific_closeout.json").read_bytes()
    manifest_before = (analysis_run / "run_manifest.json").read_bytes()

    def fail_influence(_: Path) -> dict:
        raise RuntimeError("forced influence audit failure")

    monkeypatch.setattr(executor, "audit_battery_influence_run", fail_influence)
    result = execute_nasa_audit_action(request)

    assert result["execution_status"] == "failed"
    assert result["rollback_verified"] is True
    assert not (analysis_run / "tables/target_integrity_by_battery.csv").exists()
    assert not (analysis_run / "reports/target_comparability_audit.json").exists()
    assert (analysis_run / "reports/scientific_closeout.json").read_bytes() == closeout_before
    assert (analysis_run / "run_manifest.json").read_bytes() == manifest_before

    state = load_research_state(research_run)
    assert state["actions"][0]["status"] == "failed"
    assert state["budget"]["cost_units_used"] == 2
    verification = verify_nasa_audit_action_report(result["action_report"])
    assert verification["valid"] is True
    assert verification["execution_status"] == "failed"


def test_immutable_input_mutation_is_detected_and_restored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    research_run = tmp_path / "research"
    analysis_run = _analysis_run(tmp_path / "analysis")
    initialize_research_loop(_objective(tmp_path / "objective.json"), research_run)
    request = _request(
        tmp_path / "request.json",
        research_run=research_run,
        analysis_run=analysis_run,
    )
    predictions = analysis_run / "tables/validation_predictions.csv"
    predictions_before = predictions.read_bytes()
    real_target_audit = executor.audit_battery_intelligence_run

    def mutate_input(path: Path) -> dict:
        result = real_target_audit(path)
        predictions.write_text(
            predictions.read_text(encoding="utf-8") + "\n", encoding="utf-8"
        )
        return result

    monkeypatch.setattr(executor, "audit_battery_intelligence_run", mutate_input)
    result = execute_nasa_audit_action(request)

    assert result["execution_status"] == "failed"
    assert "immutable Battery run input" in result["error"]
    assert predictions.read_bytes() == predictions_before
    assert result["rollback_verified"] is True


def test_stopped_or_duplicate_action_is_rejected(tmp_path: Path) -> None:
    research_run = tmp_path / "research"
    analysis_run = _analysis_run(tmp_path / "analysis")
    initialize_research_loop(_objective(tmp_path / "objective.json"), research_run)
    request = _request(
        tmp_path / "request.json",
        research_run=research_run,
        analysis_run=analysis_run,
    )
    execute_nasa_audit_action(request)
    with pytest.raises(NasaAuditActionError, match="duplicate action_id"):
        execute_nasa_audit_action(request)

    stopped_run = tmp_path / "stopped"
    initialize_research_loop(_objective(tmp_path / "stopped-objective.json"), stopped_run)
    append_stop(stopped_run, reason_code="external_evidence_required", summary="Stop.")
    stopped_request = _request(
        tmp_path / "stopped-request.json",
        research_run=stopped_run,
        analysis_run=_analysis_run(tmp_path / "stopped-analysis"),
    )
    with pytest.raises(NasaAuditActionError, match="stopped"):
        execute_nasa_audit_action(stopped_request)


def test_report_verifier_detects_output_drift(tmp_path: Path) -> None:
    research_run = tmp_path / "research"
    analysis_run = _analysis_run(tmp_path / "analysis")
    initialize_research_loop(_objective(tmp_path / "objective.json"), research_run)
    request = _request(
        tmp_path / "request.json",
        research_run=research_run,
        analysis_run=analysis_run,
    )
    result = execute_nasa_audit_action(request)
    output = analysis_run / "reports/target_comparability_audit.json"
    output.write_text("{}\n", encoding="utf-8")

    with pytest.raises(NasaAuditActionError, match="output no longer matches"):
        verify_nasa_audit_action_report(result["action_report"])


def test_request_rejects_unknown_fields_and_unsafe_action_id(tmp_path: Path) -> None:
    research_run = tmp_path / "research"
    analysis_run = _analysis_run(tmp_path / "analysis")
    initialize_research_loop(_objective(tmp_path / "objective.json"), research_run)
    request = _request(
        tmp_path / "request.json",
        research_run=research_run,
        analysis_run=analysis_run,
    )
    payload = json.loads(request.read_text(encoding="utf-8"))
    payload["unexpected"] = True
    request.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(NasaAuditActionError, match="unknown keys"):
        execute_nasa_audit_action(request)

    payload.pop("unexpected")
    payload["action_id"] = "../unsafe"
    request.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(NasaAuditActionError, match="action_id"):
        execute_nasa_audit_action(request)
