from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

import materials_data_analyzer.research_loop_cli as cli
from materials_data_analyzer.research_loop import (
    initialize_research_loop,
    load_action_registry,
)
from platform_core.battery_intelligence import BatteryIntelligenceConfig

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "configs/research/nasa_research_action_registry.v1.json"


def _prepare(tmp_path: Path) -> tuple[Path, Path]:
    objective = tmp_path / "objective.json"
    objective.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "research_id": "audit-cli-test",
                "question": "Can the existing run audit be executed deterministically?",
                "metrics": {"primary": "battery_macro_mae", "secondary": []},
                "constraints": ["preserve_negative_results"],
                "budget": {"maximum_actions": 2, "maximum_cost_units": 5},
                "stop_rules": ["budget_exhausted"],
            }
        ),
        encoding="utf-8",
    )
    research = tmp_path / "research"
    initialize_research_loop(objective, research)

    analysis = tmp_path / "analysis"
    tables = analysis / "tables"
    reports = analysis / "reports"
    tables.mkdir(parents=True)
    reports.mkdir(parents=True)
    cycles: list[dict[str, object]] = []
    forecast: list[dict[str, object]] = []
    predictions: list[dict[str, object]] = []
    for battery in range(4):
        battery_id = f"C{battery}"
        for cycle in range(1, 7):
            target = 101.0 - cycle
            cycles.append(
                {
                    "battery_id": battery_id,
                    "cycle_index": cycle,
                    "capacity_retention_percent": target,
                    "reference_capacity_ah": 2.0,
                    "discharge_capacity_ah": 2.0 * target / 100.0,
                    "ambient_temperature_c": 25.0 + battery,
                }
            )
        for origin in (1, 2, 3):
            actual = 99.0 - origin
            forecast.append(
                {
                    "battery_id": battery_id,
                    "origin_cycle": origin,
                    "target_cycle": origin + 2,
                    "future_target": actual,
                    "current_target": actual + 2.0,
                }
            )
            predictions.append(
                {
                    "battery_id": battery_id,
                    "actual": actual,
                    "persistence_prediction": actual + 1.0,
                    "ridge_prediction": actual + 1.0,
                }
            )
    pd.DataFrame(cycles).to_csv(tables / "validated_cycle_summary.csv", index=False)
    pd.DataFrame(forecast).to_csv(tables / "forecast_feature_table.csv", index=False)
    pd.DataFrame(predictions).to_csv(tables / "validation_predictions.csv", index=False)
    config = BatteryIntelligenceConfig(n_splits=2, knee_bootstrap_samples=0)
    (analysis / "config_snapshot.json").write_text(
        json.dumps({"config": config.to_dict()}), encoding="utf-8"
    )
    closeout = {
        "evidence_level": "Unsupported",
        "component_statuses": {},
        "strongest_evidence": {},
        "limitations": [],
        "primary_limitation": "Existing limitation.",
    }
    (reports / "scientific_closeout.json").write_text(
        json.dumps(closeout), encoding="utf-8"
    )
    (reports / "scientific_closeout.md").write_text(
        "# Scientific Closeout\n", encoding="utf-8"
    )
    (analysis / "run_manifest.json").write_text(
        json.dumps(
            {
                "artifact_paths": [],
                "artifact_checksums": {},
                "scientific_validation": "Unsupported",
                "scientific_closeout": closeout,
                "limitations": [],
            }
        ),
        encoding="utf-8",
    )

    registry_sha = load_action_registry(REGISTRY, repository_root=ROOT)[
        "registry_sha256"
    ]
    request = tmp_path / "request.json"
    request.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "action_id": "CLI-A1",
                "action_type": "audit_existing_battery_run",
                "research_run": str(research),
                "analysis_run": str(analysis),
                "registry": str(REGISTRY),
                "repository_root": str(ROOT),
                "expected_registry_sha256": registry_sha,
            }
        ),
        encoding="utf-8",
    )
    return request, research


def test_cli_executes_and_reverifies_typed_nasa_audit(tmp_path: Path, capsys) -> None:
    request, _ = _prepare(tmp_path)

    assert cli.main(["execute-nasa-audit", "--request", str(request)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["execution_status"] == "completed"

    assert (
        cli.main(
            ["verify-nasa-audit", "--report", result["action_report"]]
        )
        == 0
    )
    verified = json.loads(capsys.readouterr().out)
    assert verified["valid"] is True
    assert verified["action_id"] == "CLI-A1"


def test_cli_preflight_error_returns_nonzero_without_action(tmp_path: Path, capsys) -> None:
    request, research = _prepare(tmp_path)
    payload = json.loads(request.read_text(encoding="utf-8"))
    payload["expected_registry_sha256"] = "0" * 64
    request.write_text(json.dumps(payload), encoding="utf-8")

    assert cli.main(["execute-nasa-audit", "--request", str(request)]) == 1
    assert "registry SHA-256" in capsys.readouterr().err
    state = json.loads((research / "research_state.json").read_text(encoding="utf-8"))
    assert state["actions"] == []
