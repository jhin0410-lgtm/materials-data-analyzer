from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

import materials_data_analyzer.research_loop.nasa_protocol_stratification_action as action
from materials_data_analyzer.research_loop import (
    NasaProtocolStratificationActionError,
    append_action,
    execute_nasa_protocol_stratification_action,
    initialize_research_loop,
    load_action_registry,
    load_research_state,
    verify_nasa_protocol_stratification_report,
)
from materials_data_analyzer.research_loop.protocol_stratification import (
    build_protocol_stratification,
)

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "configs/research/nasa_protocol_stratification_action_registry.v1.json"


def _protocol(group_size: int = 5) -> pd.DataFrame:
    rows = []
    for temperature in (25.0, 40.0):
        for index in range(group_size):
            rows.append(
                {
                    "battery_id": f"T{int(temperature)}-{index}",
                    "ambient_temperature_median_c": temperature,
                }
            )
    return pd.DataFrame(rows)


def _predictions(
    protocol: pd.DataFrame,
    *,
    separated: bool = True,
) -> pd.DataFrame:
    rows = []
    for record in protocol.to_dict(orient="records"):
        temperature = record["ambient_temperature_median_c"]
        ridge_error = 0.1 if separated and temperature == 25.0 else 3.0
        if not separated:
            ridge_error = 1.0
        for cycle in range(3):
            actual = 90.0 - cycle
            rows.append(
                {
                    "battery_id": record["battery_id"],
                    "actual": actual,
                    "persistence_prediction": actual + 1.0,
                    "ridge_prediction": actual + ridge_error,
                }
            )
    return pd.DataFrame(rows)


def test_protocol_stratification_supports_large_exact_temperature_effect() -> None:
    protocol = _protocol()
    result = build_protocol_stratification(
        protocol_summary=protocol,
        predictions=_predictions(protocol),
    )

    summary = result["summary"]
    assert summary["outcome"] == "protocol_effect_supported"
    assert summary["status"] == "Diagnostic"
    assert summary["exact_protocol_group_count"] == 2
    assert summary["smallest_evaluated_protocol_group_count"] == 5
    assert summary["kruskal_wallis_p_value"] <= 0.05
    assert summary["epsilon_squared"] >= 0.10
    assert len(result["battery_protocol_errors"]) == 10
    assert len(result["protocol_group_metrics"]) == 2


def test_protocol_stratification_reports_effect_not_supported() -> None:
    protocol = _protocol()
    result = build_protocol_stratification(
        protocol_summary=protocol,
        predictions=_predictions(protocol, separated=False),
    )

    assert result["summary"]["outcome"] == "protocol_effect_not_supported"
    assert result["summary"]["kruskal_wallis_p_value"] == 1.0
    assert result["summary"]["epsilon_squared"] == 0.0


def test_protocol_stratification_reports_missing_evaluated_metadata() -> None:
    protocol = _protocol()
    predictions = _predictions(protocol)
    protocol.loc[0, "ambient_temperature_median_c"] = None

    result = build_protocol_stratification(
        protocol_summary=protocol,
        predictions=predictions,
    )

    assert result["summary"]["outcome"] == "protocol_metadata_insufficient"
    assert result["summary"][
        "missing_evaluated_protocol_metadata_battery_count"
    ] == 1
    assert result["summary"]["kruskal_wallis_p_value"] is None


def test_protocol_stratification_does_not_drop_sparse_groups() -> None:
    protocol = _protocol(group_size=4)
    result = build_protocol_stratification(
        protocol_summary=protocol,
        predictions=_predictions(protocol),
    )

    assert result["summary"]["outcome"] == "protocol_groups_too_small"
    assert result["summary"]["smallest_evaluated_protocol_group_count"] == 4
    assert len(result["battery_protocol_errors"]) == 8
    assert not result["protocol_group_metrics"]["eligible_for_primary_test"].any()


def _objective(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "research_id": "protocol-action-test",
                "question": "Does explicit temperature metadata explain model error?",
                "metrics": {"primary": "battery_macro_mae", "secondary": []},
                "constraints": ["preserve_negative_results"],
                "budget": {"maximum_actions": 5, "maximum_cost_units": 20},
                "stop_rules": ["budget_exhausted", "external_evidence_required"],
            }
        ),
        encoding="utf-8",
    )
    return path


def _existing_runs(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    research = tmp_path / "research"
    import_run = tmp_path / "import"
    analysis = tmp_path / "analysis"
    initialize_research_loop(_objective(tmp_path / "objective.json"), research)
    import_run.mkdir()
    (analysis / "tables").mkdir(parents=True)
    (analysis / "reports").mkdir()

    protocol = _protocol()
    protocol.to_csv(import_run / "nasa_pcoe_protocol_summary.csv", index=False)
    _predictions(protocol).to_csv(
        analysis / "tables/validation_predictions.csv", index=False
    )
    (analysis / "reports/scientific_closeout.json").write_text(
        json.dumps({"evidence_level": "Unsupported"}), encoding="utf-8"
    )
    (analysis / "run_manifest.json").write_text("{}\n", encoding="utf-8")

    audit_report = tmp_path / "audit_action_result.json"
    audit_report.write_text(
        json.dumps(
            {
                "execution_status": "completed",
                "outcomes": ["pooled_error_instability_detected"],
            }
        ),
        encoding="utf-8",
    )
    append_action(
        research,
        action_id="A1",
        action_type="audit_existing_battery_run",
        status="completed",
        summary="Audit completed.",
        cost_units=2,
        artifact_paths=[audit_report],
    )

    registry = load_action_registry(REGISTRY, repository_root=ROOT)
    request = tmp_path / "protocol_request.json"
    request.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "action_id": "A2",
                "action_type": "protocol_stratification",
                "research_run": str(research),
                "import_run": str(import_run),
                "analysis_run": str(analysis),
                "registry": str(REGISTRY),
                "repository_root": str(ROOT),
                "expected_registry_sha256": registry["registry_sha256"],
            }
        ),
        encoding="utf-8",
    )
    return research, import_run, analysis, request


def _verified_stub(_: Path) -> dict[str, object]:
    return {"valid": True}


def test_protocol_action_executes_and_reverifies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    research, import_run, analysis, request = _existing_runs(tmp_path)
    source_paths = [
        import_run / "nasa_pcoe_protocol_summary.csv",
        analysis / "tables/validation_predictions.csv",
        analysis / "reports/scientific_closeout.json",
        analysis / "run_manifest.json",
    ]
    before = {path: path.read_bytes() for path in source_paths}
    monkeypatch.setattr(action, "verify_nasa_audit_action_report", _verified_stub)

    result = execute_nasa_protocol_stratification_action(request)
    verified = verify_nasa_protocol_stratification_report(result["action_report"])

    assert result["execution_status"] == "completed"
    assert result["outcome"] == "protocol_effect_supported"
    assert verified["valid"] is True
    assert verified["outcome"] == "protocol_effect_supported"
    assert all(path.read_bytes() == before[path] for path in source_paths)
    state = load_research_state(research)
    assert state["actions"][-1]["action_type"] == "protocol_stratification"
    assert state["actions"][-1]["status"] == "completed"


def test_protocol_action_requires_stable_target_when_audit_flags_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    research, _, _, request = _existing_runs(tmp_path)
    state = load_research_state(research)
    audit_path = Path(state["actions"][0]["artifacts"][0]["path"])
    audit_path.write_text(
        json.dumps(
            {
                "execution_status": "completed",
                "outcomes": [
                    "target_or_reference_flags_detected",
                    "pooled_error_instability_detected",
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(action, "verify_nasa_audit_action_report", _verified_stub)

    with pytest.raises(
        NasaProtocolStratificationActionError,
        match="target_reference_sensitivity",
    ):
        execute_nasa_protocol_stratification_action(request)
