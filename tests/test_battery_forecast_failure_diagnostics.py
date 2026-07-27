import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.cli import main
from src.platform_core.battery_forecast_diagnostics import (
    DIAGNOSTIC_ID,
    DIAGNOSTIC_VERSION,
    BatteryForecastDiagnosticConfig,
    canonical_checksum,
    load_config,
    preview_diagnostics,
    run_diagnostics,
    validate_result_payload,
)


def _group_reference(group_id):
    digest = hashlib.sha256(f"battery-group:{group_id}".encode()).hexdigest()
    return f"battery_ref_{digest[:12]}"


def _metric(actual, predicted):
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)
    error = predicted - actual
    denominator = float(np.sum((actual - np.mean(actual)) ** 2))
    return {
        "prediction_count": len(actual),
        "mae": float(np.mean(np.abs(error))),
        "rmse": float(np.sqrt(np.mean(error**2))),
        "r2": (
            float(1 - np.sum(error**2) / denominator)
            if denominator > 0
            else None
        ),
    }


def _write_synthetic_repo(root: Path) -> tuple[Path, dict]:
    source_rows = []
    prediction_rows = []
    for group_index in range(4):
        battery_id = f"B{group_index:04d}"
        reference = _group_reference(battery_id)
        values = []
        for cycle in range(1, 21):
            if group_index == 0:
                value = 100.0 - 0.5 * cycle
            elif group_index == 1:
                value = 100.0 - 0.3 * cycle - (15.0 if cycle >= 10 else 0.0)
            elif group_index == 2:
                value = 95.0 - 0.4 * cycle + (12.0 if cycle == 10 else 0.0)
            else:
                value = 90.0
            values.append(value)
            source_rows.append(
                {
                    "battery_id": battery_id,
                    "cycle_index": cycle,
                    "capacity_retention_percent": value,
                    "ambient_temperature_c": 24,
                    "source_filename": f"{battery_id}_{cycle}.csv",
                    "test_id": cycle,
                    "internal_resistance_ohm": np.nan,
                }
            )
        for origin in range(5, 16):
            actual = values[origin + 5 - 1]
            current = values[origin - 1]
            for model in ("persistence", "ridge"):
                predicted = current if model == "persistence" else current + 2.0
                if group_index == 1 and origin == 9 and model == "ridge":
                    predicted = -2.0
                prediction_rows.append(
                    {
                        "fold_id": f"group_fold_{group_index + 1:02d}",
                        "model": model,
                        "battery_id": battery_id,
                        "group_reference": reference,
                        "prediction_origin": origin,
                        "forecast_target_cycle": origin + 5,
                        "feature_cutoff_cycle": origin,
                        "actual": actual,
                        "capacity_current": current,
                        "prediction_raw": predicted,
                        "prediction_clipped": np.nan,
                        "outside_training_target_range": False,
                    }
                )

    source = pd.DataFrame(source_rows)
    predictions = pd.DataFrame(prediction_rows)
    source_path = root / "data/processed/source.csv"
    predictions_path = root / "outputs/v2_6_battery_generalization/predictions.csv"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    predictions_path.parent.mkdir(parents=True, exist_ok=True)
    source.to_csv(source_path, index=False)
    predictions.to_csv(predictions_path, index=False)
    source_sha = hashlib.sha256(source_path.read_bytes()).hexdigest()

    aggregate = []
    for model in ("persistence", "ridge"):
        rows = predictions.loc[predictions["model"] == model]
        metrics = _metric(rows["actual"], rows["prediction_raw"])
        aggregate.append({"model": model, **metrics})

    required_common = {
        "schema_version": "2.6.1",
        "benchmark_id": "battery_warm_start_cross_battery_forecast_v1",
        "evaluation_scenario": "warm_start_cross_battery",
        "source_sha256": source_sha,
        "forecast_horizon_cycles": 5,
        "aggregate_metrics": aggregate,
        "baseline_comparison": {
            "model": "ridge",
            "baseline": "persistence",
            "mae_absolute_difference": (
                aggregate[1]["mae"] - aggregate[0]["mae"]
            ),
        },
        "leakage_checks": {
            "status": "passed",
            "group_overlap_count": 0,
            "target_horizon_alignment_valid": True,
            "future_feature_accessed": False,
            "preprocessing_fit_scope": "training_partition_only",
        },
        "physical_plausibility_checks": [],
        "software_validation": "passed",
        "scientific_assessment": {"status": "unsupported"},
    }
    detailed = {
        **required_common,
        "artifact_kind": "battery_generalization_forecast_result",
        "model_specification": {
            "hyperparameter_search_performed": False,
            "prediction_clipping_performed": False,
        },
    }
    detailed["deterministic_result_checksum"] = canonical_checksum(detailed)
    detailed_path = root / "outputs/v2_6_battery_generalization/forecast_summary.json"
    detailed_path.write_text(
        json.dumps(detailed, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    summary = {
        **required_common,
        "artifact_kind": "battery_generalization_forecast_compact_summary",
        "source_rows": len(source),
        "source_trajectory_count": source["battery_id"].nunique(),
        "group_overlap_count": 0,
    }
    summary["deterministic_result_checksum"] = canonical_checksum(summary)
    summary_path = root / "data/processed/benchmark_summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    benchmark_config_path = root / "configs/benchmark.json"
    benchmark_config_path.parent.mkdir(parents=True, exist_ok=True)
    benchmark_config_path.write_text("{}", encoding="utf-8")
    lineage_path = root / "data/processed/lineage.json"
    lineage_path.write_text(
        json.dumps(
            {
                "schema_version": "2.3.5",
                "exact_lineage_cell_count": 4,
                "protocol_document_cell_coverage": 4,
                "original_nasa_snapshot_status": "unresolved",
            }
        ),
        encoding="utf-8",
    )
    metadata_path = root / "data/processed/metadata_recovery.csv"
    pd.DataFrame(
        [
            {
                "metadata_field": "documented_protocol_group",
                "limitation": "cycle-specific command log unavailable",
            }
        ]
    ).to_csv(metadata_path, index=False)

    payload = {
        "schema_version": DIAGNOSTIC_VERSION,
        "diagnostic_id": DIAGNOSTIC_ID,
        "case_study_id": "kaggle_battery",
        "source_benchmark_config_path": "configs/benchmark.json",
        "source_benchmark_summary_path": "data/processed/benchmark_summary.json",
        "source_benchmark_result_path": (
            "outputs/v2_6_battery_generalization/forecast_summary.json"
        ),
        "source_predictions_path": (
            "outputs/v2_6_battery_generalization/predictions.csv"
        ),
        "source_analysis_ready_path": "data/processed/source.csv",
        "source_lineage_path": "data/processed/lineage.json",
        "metadata_recovery_summary_path": (
            "data/processed/metadata_recovery.csv"
        ),
        "expected_benchmark_summary_checksum": summary[
            "deterministic_result_checksum"
        ],
        "expected_benchmark_result_checksum": detailed[
            "deterministic_result_checksum"
        ],
        "group_column": "battery_id",
        "time_column": "cycle_index",
        "target_column": "capacity_retention_percent",
        "models": ["persistence", "ridge"],
        "horizon": 5,
        "local_window": 5,
        "regime_early_max_cycle": 8,
        "regime_middle_max_cycle": 12,
        "sparse_prediction_max": 3,
        "abrupt_change_threshold": 10.0,
        "high_target_std_threshold": 8.0,
        "low_target_std_threshold": 1.0,
        "high_local_volatility_threshold": 4.0,
        "flat_range_threshold": 0.5,
        "flat_window": 5,
        "physical_min": 0.0,
        "physical_max": 150.0,
        "source_benchmark_execution_status": "existing_local_output_reused",
        "credential_policy": {
            "store_credentials": False,
            "network_access_required": False,
        },
        "output_root": "outputs/v2_6_battery_diagnostics",
        "tracked_summary_path": (
            "data/processed/battery_v2_6_2_forecast_failure_diagnostic_summary.json"
        ),
        "output_policy": "local_details_and_tracked_compact_summary",
    }
    config_path = root / "configs/diagnostics.json"
    config_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return config_path, payload


def test_contributions_leave_one_out_and_metric_preservation(tmp_path):
    config_path, _ = _write_synthetic_repo(tmp_path)
    config = load_config(config_path.relative_to(tmp_path), tmp_path)
    execution = run_diagnostics(config, tmp_path, write_outputs=False)
    result = execution["result"]
    influence = execution["frames"]["influence_analysis"]

    assert math.isclose(influence["prediction_count_contribution"].sum(), 1.0)
    for model in ("persistence", "ridge"):
        metric = next(row for row in result["aggregate_metrics"] if row["model"] == model)
        assert math.isclose(
            influence[f"{model}_absolute_error_sum"].sum(),
            metric["mae"] * metric["prediction_count"],
            abs_tol=1e-10,
        )
        assert metric["source_benchmark_metric_preserved"] is True
    first = influence.iloc[0]
    remaining = result["prediction_count"] - first["prediction_count"]
    expected = (
        sum(row["ridge_absolute_error_sum"] for row in result["influence_analysis"])
        - first["ridge_absolute_error_sum"]
    ) / remaining
    assert math.isclose(first["leave_one_out_ridge_mae"], expected)


def test_quality_regime_physical_and_classification_diagnostics(tmp_path):
    config_path, _ = _write_synthetic_repo(tmp_path)
    config = load_config(config_path.relative_to(tmp_path), tmp_path)
    execution = run_diagnostics(config, tmp_path, write_outputs=False)
    quality = execution["frames"]["trajectory_quality_flags"]
    regimes = execution["frames"]["regime_metrics"]
    result = execution["result"]

    assert quality["abrupt_drop_count"].sum() >= 1
    assert quality["abrupt_upward_recovery_count"].sum() >= 1
    assert quality["low_target_variation_flag"].sum() >= 1
    assert set(regimes["regime"]) == {"early", "middle", "late"}
    assert not regimes["future_target_used_for_assignment"].any()
    assert result["physical_violation_analysis"]["ridge_violation_count"] == 1
    classifications = ";".join(
        row["diagnostic_classifications"]
        for row in result["per_battery_diagnostics"]
    )
    assert "abrupt_transition" in classifications
    assert "metadata_comparability_unresolved" in classifications


def test_deterministic_source_non_mutating_and_no_model_retraining(tmp_path):
    config_path, _ = _write_synthetic_repo(tmp_path)
    config = load_config(config_path.relative_to(tmp_path), tmp_path)
    source_path = tmp_path / config.source_analysis_ready_path
    before = hashlib.sha256(source_path.read_bytes()).hexdigest()

    execution = run_diagnostics(config, tmp_path, write_outputs=False)
    result = execution["result"]

    assert result["first_run_checksum"] == result["second_run_checksum"]
    assert result["deterministic_rerun_match"] is True
    assert result["source_hashes_before"] == result["source_hashes_after"]
    assert hashlib.sha256(source_path.read_bytes()).hexdigest() == before
    assert result["model_retrained"] is False
    assert execution["model_retrained"] is False
    assert execution["source_benchmark_regenerated"] is False
    assert execution["source_benchmark_checksum_verified"] is True
    assert execution["diagnostic_model_trained"] is False
    assert execution["model_tuned"] is False
    assert validate_result_payload(result, repo_root=tmp_path)["valid"] is True


def test_preview_is_side_effect_free(tmp_path):
    config_path, _ = _write_synthetic_repo(tmp_path)
    config = load_config(config_path.relative_to(tmp_path), tmp_path)
    before = {
        path.relative_to(tmp_path): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }

    preview = preview_diagnostics(config, tmp_path)

    after = {
        path.relative_to(tmp_path): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    assert preview["status"] == "ready"
    assert preview["writes_performed"] is False
    assert preview["model_retrained"] is False
    assert preview["source_benchmark_regenerated"] is False
    assert preview["source_benchmark_checksum_verified"] is True
    assert preview["diagnostic_model_trained"] is False
    assert preview["model_tuned"] is False
    assert before == after


def test_cli_run_and_validate_writes_only_registered_outputs(
    tmp_path,
    monkeypatch,
    capsys,
):
    _write_synthetic_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert main(
        ["--json", "preview-battery-forecast-diagnostics", "configs/diagnostics.json"]
    ) == 0
    assert json.loads(capsys.readouterr().out)["writes_performed"] is False

    assert main(
        ["--json", "run-battery-forecast-diagnostics", "configs/diagnostics.json"]
    ) == 0
    run_payload = json.loads(capsys.readouterr().out)
    assert len(run_payload["written"]) == 8
    assert run_payload["source_benchmark_regenerated"] is False
    assert run_payload["source_benchmark_checksum_verified"] is True
    assert run_payload["diagnostic_model_trained"] is False
    assert run_payload["model_tuned"] is False
    result_path = "outputs/v2_6_battery_diagnostics/diagnostic_summary.json"
    assert main(
        ["--json", "validate-battery-forecast-diagnostics", result_path]
    ) == 0
    assert json.loads(capsys.readouterr().out)["valid"] is True


def test_checksum_mismatch_and_result_tampering_are_rejected(tmp_path):
    config_path, payload = _write_synthetic_repo(tmp_path)
    payload["expected_benchmark_summary_checksum"] = "0" * 64
    config_path.write_text(json.dumps(payload), encoding="utf-8")
    config = load_config(config_path.relative_to(tmp_path), tmp_path)
    with pytest.raises(ValueError, match="source benchmark checksum mismatch"):
        run_diagnostics(config, tmp_path, write_outputs=False)

    _, payload = _write_synthetic_repo(tmp_path)
    config = BatteryForecastDiagnosticConfig.from_mapping(payload)
    result = run_diagnostics(config, tmp_path, write_outputs=False)["result"]
    result["prediction_count"] += 1
    validation = validate_result_payload(result, repo_root=tmp_path)
    assert validation["valid"] is False
    assert "deterministic checksum mismatch" in validation["errors"]


@pytest.mark.parametrize(
    "field",
    ["module_path", "callable_name", "expression", "model_class"],
)
def test_unknown_dynamic_execution_fields_are_rejected(tmp_path, field):
    _, payload = _write_synthetic_repo(tmp_path)
    payload[field] = "package.module.callable"
    with pytest.raises(ValueError, match="unknown config field"):
        BatteryForecastDiagnosticConfig.from_mapping(payload)


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_predictions_path", "C:/outside/predictions.csv"),
        ("source_analysis_ready_path", "../outside.csv"),
        ("output_root", "/tmp/output"),
    ],
)
def test_absolute_and_traversal_paths_are_rejected(tmp_path, field, value):
    _, payload = _write_synthetic_repo(tmp_path)
    payload[field] = value
    with pytest.raises(ValueError, match="repository-relative"):
        BatteryForecastDiagnosticConfig.from_mapping(payload)


def test_secret_like_values_unknown_version_and_result_fields_are_rejected(tmp_path):
    _, payload = _write_synthetic_repo(tmp_path)
    payload["source_lineage_path"] = "api_key=fixture"
    with pytest.raises(ValueError, match="secret-like value"):
        BatteryForecastDiagnosticConfig.from_mapping(payload)

    _, payload = _write_synthetic_repo(tmp_path)
    payload["schema_version"] = "9.9.9"
    with pytest.raises(ValueError, match="schema_version"):
        BatteryForecastDiagnosticConfig.from_mapping(payload)

    config = BatteryForecastDiagnosticConfig.from_mapping(
        _write_synthetic_repo(tmp_path)[1]
    )
    result = run_diagnostics(config, tmp_path, write_outputs=False)["result"]
    checksum = result.pop("deterministic_result_checksum")
    result["unexpected"] = "field"
    result["deterministic_result_checksum"] = canonical_checksum(result)
    validation = validate_result_payload(result)
    assert validation["valid"] is False
    assert validation["errors"] == ["unknown result field(s): unexpected"]
    assert checksum != result["deterministic_result_checksum"]


def test_v2_6_1_tracked_decision_is_preserved_under_v2_7():
    payload = json.loads(
        Path(
            "data/processed/battery_v2_6_1_generalization_forecast_summary.json"
        ).read_text(encoding="utf-8")
    )
    metrics = {row["model"]: row for row in payload["aggregate_metrics"]}
    assert payload["deterministic_result_checksum"] == (
        "9bcc58b0f7df95cc996aee6f509aac6a9293f753186b50d8b1635bb6ad392d42"
    )
    assert payload["scientific_assessment"]["status"] == "unsupported"
    assert metrics["persistence"]["mae"] == pytest.approx(3.425575369058076)
    assert metrics["ridge"]["mae"] == pytest.approx(4.15369918179312)
    from src.platform_core.version import PLATFORM_VERSION

    # Tracked v2.6 artifacts retain historical checksums; the current public runtime is v2.7.0.
    assert PLATFORM_VERSION == "2.7.0"


def test_diagnostic_config_and_result_schema_json_parse():
    for path in (
        Path("data/platform/battery_forecast_diagnostic_config_schema_v1.json"),
        Path("data/platform/battery_forecast_diagnostic_result_schema_v1.json"),
        Path("configs/examples/battery_forecast_diagnostics.json"),
    ):
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(payload, dict)


def test_actual_compact_summary_matches_diagnostic_closeout():
    path = Path(
        "data/processed/battery_v2_6_2_forecast_failure_diagnostic_summary.json"
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    validation = validate_result_payload(payload, repo_root=Path.cwd())

    assert validation["valid"] is True
    assert payload["battery_count"] == 33
    assert payload["prediction_count"] == 2100
    assert payload["scientific_closeout"]["status"] == "diagnostic"
    assert payload["scientific_closeout"][
        "worst_battery_exclusion_preserves_persistence_advantage"
    ] is True
    assert payload["scientific_closeout"]["ridge_worse_regime_count"] == 3
    assert payload["comparability_readiness"]["status"] == (
        "comparability_not_established"
    )
    assert payload["source_benchmark_regenerated"] is True
    assert payload["source_benchmark_checksum_verified"] is True
    assert payload["diagnostic_model_trained"] is False
    assert payload["model_tuned"] is False
    assert "battery_id" not in path.read_text(encoding="utf-8")


def test_module_has_no_model_network_dynamic_execution_or_pickle():
    text = Path(
        "src/platform_core/battery_forecast_diagnostics.py"
    ).read_text(encoding="utf-8")
    forbidden = (
        "from sklearn",
        "import requests",
        "import urllib",
        "importlib",
        "subprocess",
        "pickle",
        "eval(",
        "exec(",
        ".fit(",
        ".predict(",
    )
    for token in forbidden:
        assert token not in text
