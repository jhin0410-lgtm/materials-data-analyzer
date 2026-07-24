import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.platform_core.battery_forecasting import (
    BENCHMARK_ID,
    BatteryForecastConfig,
    build_group_splits,
    build_lagged_forecast_frame,
    canonical_checksum,
    evaluate_forecast_frame,
    compact_summary,
    preview_benchmark,
    run_benchmark,
    validate_result_payload,
)


def _config_payload(**overrides):
    payload = {
        "schema_version": "2.6.1",
        "benchmark_id": BENCHMARK_ID,
        "case_study_id": "kaggle_battery",
        "input_path": "data/input.csv",
        "source_lineage_path": "data/lineage.json",
        "group_column": "battery_id",
        "time_column": "cycle_index",
        "target_column": "capacity_retention_percent",
        "target_unit": "percent",
        "horizon": 5,
        "lags": [1, 2, 3],
        "rolling_window": 5,
        "minimum_history": 5,
        "split_method": "group_kfold",
        "n_splits": 3,
        "random_seed": 42,
        "models": ["persistence", "ridge"],
        "ridge_alpha": 1.0,
        "plausibility_min": 0.0,
        "plausibility_max": 150.0,
        "large_change_threshold": 25.0,
        "duplicate_cycle_policy": "reject_trajectory",
        "unordered_cycle_policy": "stable_sort_with_audit",
        "credential_policy": {
            "store_credentials": False,
            "network_access_required": False,
        },
        "output_root": "outputs/v2_6_battery_generalization",
        "output_policy": "local_details_and_tracked_compact_summary",
    }
    payload.update(overrides)
    return payload


def _config(**overrides):
    return BatteryForecastConfig.from_mapping(_config_payload(**overrides))


def _frame(group_count=4, cycles=16):
    rows = []
    for group_index in range(group_count):
        for cycle in range(1, cycles + 1):
            rows.append(
                {
                    "battery_id": f"B{group_index:02d}",
                    "cycle_index": cycle,
                    "capacity_retention_percent": (
                        100.0 - 0.2 * cycle - 0.03 * group_index * cycle
                    ),
                }
            )
    return pd.DataFrame(rows)


def _write_repo(tmp_path, frame=None, config_payload=None):
    frame = _frame() if frame is None else frame
    config_payload = _config_payload() if config_payload is None else config_payload
    (tmp_path / "data").mkdir()
    (tmp_path / "configs").mkdir()
    frame.to_csv(tmp_path / "data/input.csv", index=False)
    (tmp_path / "data/lineage.json").write_text(
        json.dumps({"status": "synthetic_fixture"}),
        encoding="utf-8",
    )
    (tmp_path / "configs/config.json").write_text(
        json.dumps(config_payload),
        encoding="utf-8",
    )


def test_exact_horizon_alignment_and_past_only_lag_features():
    config = _config()
    forecast, exclusions = build_lagged_forecast_frame(_frame(), config)
    first = forecast.iloc[0]

    assert first["forecast_target_cycle"] - first["prediction_origin"] == 5
    assert first["feature_cutoff_cycle"] == first["prediction_origin"]
    source = _frame().query("battery_id == 'B00'").set_index("cycle_index")
    origin = int(first["prediction_origin"])
    assert first["capacity_current"] == pytest.approx(
        source.loc[origin, "capacity_retention_percent"]
    )
    for lag in (1, 2, 3):
        assert first[f"capacity_lag_{lag}"] == pytest.approx(
            source.loc[origin - lag, "capacity_retention_percent"]
        )
    assert sum(exclusions.values()) + len(forecast) == len(_frame())


def test_trailing_rolling_features_ignore_future_observations():
    config = _config()
    original = _frame()
    changed = original.copy()
    changed.loc[
        (changed["battery_id"] == "B00") & (changed["cycle_index"] > 8),
        "capacity_retention_percent",
    ] = 10000.0

    first, _ = build_lagged_forecast_frame(original, config)
    second, _ = build_lagged_forecast_frame(changed, config)
    columns = [
        "capacity_current",
        "capacity_lag_1",
        "capacity_lag_2",
        "capacity_lag_3",
        "capacity_rolling_mean_5",
        "capacity_rolling_std_5",
        "capacity_recent_slope_5",
    ]
    first_row = first.query("battery_id == 'B00' and prediction_origin == 8").iloc[0]
    second_row = second.query("battery_id == 'B00' and prediction_origin == 8").iloc[0]
    assert first_row[columns].tolist() == pytest.approx(second_row[columns].tolist())


def test_future_proxy_final_value_and_centered_rolling_columns_are_ignored():
    config = _config()
    source = _frame()
    source["future_capacity_proxy"] = source.groupby("battery_id")[
        "capacity_retention_percent"
    ].shift(-5)
    source["full_trajectory_final_capacity"] = source.groupby("battery_id")[
        "capacity_retention_percent"
    ].transform("last")
    source["centered_rolling_capacity"] = source.groupby("battery_id")[
        "capacity_retention_percent"
    ].transform(lambda values: values.rolling(5, center=True).mean())

    forecast, _ = build_lagged_forecast_frame(source, config)

    assert "future_capacity_proxy" not in forecast.columns
    assert "full_trajectory_final_capacity" not in forecast.columns
    assert "centered_rolling_capacity" not in forecast.columns


def test_group_splits_are_disjoint_and_deterministic():
    config = _config()
    forecast, _ = build_lagged_forecast_frame(_frame(), config)

    first = build_group_splits(forecast, config)
    second = build_group_splits(forecast, config)

    assert [item["test_group_references"] for item in first] == [
        item["test_group_references"] for item in second
    ]
    assert all(item["group_overlap_count"] == 0 for item in first)
    assert sum(item["test_rows"] for item in first) == len(forecast)


def test_evaluation_has_persistence_ridge_per_group_and_train_only_preprocessing():
    config = _config()
    forecast, _ = build_lagged_forecast_frame(_frame(), config)
    result = evaluate_forecast_frame(forecast, config)

    assert {row["model"] for row in result["aggregate_metrics"]} == {
        "persistence",
        "ridge",
    }
    assert len(result["per_group_metrics"]) == 8
    assert result["leakage_audit"]["group_overlap_count"] == 0
    assert result["leakage_audit"]["preprocessing_fit_scope"] == (
        "training_partition_only"
    )
    assert all(
        item["fit_row_count"] < len(forecast)
        for item in result["preprocessing_diagnostics"]
    )


def test_persistence_prediction_is_current_capacity():
    config = _config()
    forecast, _ = build_lagged_forecast_frame(_frame(), config)
    predictions = evaluate_forecast_frame(forecast, config)["predictions"]
    persistence = predictions.loc[predictions["model"] == "persistence"]

    assert persistence["prediction_raw"].to_numpy() == pytest.approx(
        persistence["capacity_current"].to_numpy()
    )


def test_short_missing_and_horizon_rows_are_excluded_with_reasons():
    frame = _frame(group_count=3, cycles=12)
    frame.loc[
        (frame["battery_id"] == "B00") & (frame["cycle_index"] == 8),
        "capacity_retention_percent",
    ] = np.nan
    forecast, exclusions = build_lagged_forecast_frame(frame, _config())

    assert exclusions["missing_current_target"] >= 1
    assert exclusions["horizon_target_unavailable"] >= 1
    assert exclusions["missing_required_lag"] >= 1
    assert len(forecast) + sum(exclusions.values()) == len(frame)


def test_duplicate_cycle_is_rejected_and_unordered_rows_are_stably_sorted():
    config = _config()
    duplicate = pd.concat([_frame(), _frame().iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="duplicate battery/cycle"):
        build_lagged_forecast_frame(duplicate, config)

    unordered = _frame().sample(frac=1.0, random_state=9).reset_index(drop=True)
    forecast, _ = build_lagged_forecast_frame(unordered, config)
    assert all(
        group["prediction_origin"].is_monotonic_increasing
        for _, group in forecast.groupby("battery_id")
    )


def test_invalid_group_identifier_is_rejected():
    frame = _frame()
    frame.loc[0, "battery_id"] = ""
    with pytest.raises(ValueError, match="group identifiers"):
        build_lagged_forecast_frame(frame, _config())


def test_run_is_deterministic_and_does_not_mutate_source(tmp_path):
    _write_repo(tmp_path)
    config = _config()
    source = tmp_path / "data/input.csv"
    before = source.read_bytes()

    execution = run_benchmark(
        config,
        tmp_path,
        write_outputs=False,
        write_tracked_summary=False,
    )

    result = execution["result"]
    assert result["deterministic_rerun_match"] is True
    assert result["first_run_checksum"] == result["second_run_checksum"]
    assert source.read_bytes() == before
    assert execution["network_called"] is False
    assert execution["credentials_read"] is False


def test_result_checksum_tampering_is_rejected(tmp_path):
    _write_repo(tmp_path)
    result = run_benchmark(
        _config(),
        tmp_path,
        write_outputs=False,
        write_tracked_summary=False,
    )["result"]
    assert validate_result_payload(result)["valid"] is True

    tampered = json.loads(json.dumps(result))
    tampered["baseline_comparison"]["mae_absolute_difference"] = 123.0
    validation = validate_result_payload(tampered)
    assert validation["valid"] is False
    assert "deterministic checksum mismatch" in validation["errors"]

    compact = compact_summary(result)
    assert validate_result_payload(compact)["valid"] is True
    assert compact["leakage_checks"]["group_overlap_count"] == 0
    assert not any(
        f"B{group_index:02d}" in json.dumps(compact)
        for group_index in range(4)
    )


def test_preview_reports_no_writes_or_model_execution(tmp_path):
    _write_repo(tmp_path)
    before = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))

    payload = preview_benchmark(_config(), tmp_path)

    after = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))
    assert payload["status"] == "ready"
    assert payload["writes_performed"] is False
    assert payload["model_executed"] is False
    assert payload["network_called"] is False
    assert before == after


def test_scientific_assessment_is_registered_without_zero_shot_claim(tmp_path):
    _write_repo(tmp_path)
    assessment = run_benchmark(
        _config(),
        tmp_path,
        write_outputs=False,
        write_tracked_summary=False,
    )["result"]["scientific_assessment"]

    assert assessment["status"] in {
        "supported",
        "diagnostic",
        "inconclusive",
        "unsupported",
    }
    assert assessment["observed_history_conditioned"] is True
    assert assessment["zero_shot"] is False
    assert assessment["engineering_decision_allowed"] is False
