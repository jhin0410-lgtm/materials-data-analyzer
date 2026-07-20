import json
from pathlib import Path

import pandas as pd
import pytest

from src.platform_core.battery_pgir_adapters import (
    DEFAULT_KAGGLE_SUMMARY,
    audit_local_battery_data,
    assess_battery_mechanism_readiness,
    build_battery_observations,
    build_battery_operational_states,
    build_battery_trajectories,
    cycle_row_to_observation,
    export_tracked_battery_pgir_summaries,
    load_battery_pgir_summary,
    load_battery_cycle_summary,
    observation_to_operational_state,
    readiness_decision,
    run_battery_pgir_pipeline,
    states_to_trajectory,
    validate_battery_entities,
)


def _rows():
    return pd.DataFrame(
        [
            {
                "battery_id": "B0005",
                "cycle_index": 1,
                "ambient_temperature_c": 24.0,
                "discharge_capacity_ah": 1.8,
                "reference_capacity_ah": 1.9,
                "reference_capacity_method": "first_valid_cycle",
                "capacity_retention_percent": 94.7,
                "retention_quality_flag": "valid",
            },
            {
                "battery_id": "B0005",
                "cycle_index": 2,
                "ambient_temperature_c": 24.0,
                "discharge_capacity_ah": 1.7,
                "reference_capacity_ah": 1.9,
                "reference_capacity_method": "first_valid_cycle",
                "capacity_retention_percent": 89.5,
                "retention_quality_flag": "valid",
            },
            {
                "battery_id": "B0006",
                "cycle_index": 1,
                "ambient_temperature_c": 24.0,
                "discharge_capacity_ah": 1.6,
                "reference_capacity_ah": 1.8,
                "reference_capacity_method": "first_valid_cycle",
                "capacity_retention_percent": 88.9,
                "retention_quality_flag": "valid",
            },
        ]
    )


def test_actual_processed_battery_source_is_audited_without_network_or_model():
    audit = audit_local_battery_data()

    assert audit.source_path == DEFAULT_KAGGLE_SUMMARY
    assert audit.cell_count == 34
    assert audit.cycle_count == 2495
    assert audit.to_dict()["network_called"] is False
    assert audit.to_dict()["model_or_solver_executed"] is False


def test_cycle_row_maps_to_observation_with_units_and_unavailable_uncertainty():
    observation = cycle_row_to_observation(_rows().iloc[0].to_dict())

    payload = observation.to_dict()

    assert observation.entity_type == "MeasurementSeriesEntity"
    assert payload["attributes"]["pgir_role"] == "Observation"
    assert payload["attributes"]["quantity_roles"][0]["unit"] == "Ah"
    assert payload["attributes"]["quantity_roles"][0]["uncertainty"]["kind"] == "unavailable"
    assert "internal lithium concentration" in payload["attributes"]["prohibited_interpretations"]
    assert "diffusion_coefficient_value" not in json.dumps(payload)


def test_observation_becomes_bounded_operational_state_not_latent_state():
    state = observation_to_operational_state(cycle_row_to_observation(_rows().iloc[0].to_dict()))

    attrs = state.to_dict()["attributes"]

    assert state.entity_type == "StateEntity"
    assert attrs["state_scope"] == "operational_state_summary"
    assert attrs["conditions"]["complete_electrochemical_state"] is False
    assert "lithium_inventory_value" not in json.dumps(state.to_dict()).lower()


def test_trajectory_requires_one_cell_monotonic_unique_cycle_indices():
    observations = build_battery_observations(_rows().iloc[:2])
    states = build_battery_operational_states(observations)

    trajectory = states_to_trajectory(states)

    assert trajectory.entity_type == "TrajectoryEntity"
    assert trajectory.attributes["state_count"] == 2
    with pytest.raises(ValueError, match="mix battery cell IDs"):
        states_to_trajectory(build_battery_operational_states(build_battery_observations(_rows())))
    with pytest.raises(ValueError, match="duplicate cycle_index"):
        states_to_trajectory([states[0], states[0]])


def test_battery_entities_validate_and_large_series_are_artifact_referenced():
    observations = build_battery_observations(_rows())
    states = build_battery_operational_states(observations)
    trajectories = build_battery_trajectories(states)

    assert validate_battery_entities(observations, "MeasurementSeriesEntity")["valid"] is True
    assert validate_battery_entities(states, "StateEntity")["valid"] is True
    assert validate_battery_entities(trajectories, "TrajectoryEntity")["valid"] is True
    assert trajectories[0].artifact_refs


def test_mechanism_readiness_does_not_execute_arrhenius_diffusion_or_prediction():
    result = run_battery_pgir_pipeline(limit_rows=20, write_local=False)

    rows = result["mechanism_rows"]
    by_id = {row["mechanism_id"]: row for row in rows}

    assert by_id["arrhenius_temperature_dependence"]["execution_performed"] is False
    assert by_id["arrhenius_temperature_dependence"]["readiness_status"] == "not_identifiable_from_current_data"
    assert by_id["diffusion_transport"]["execution_performed"] is False
    assert "no spatial concentration field" in by_id["diffusion_transport"]["reason"]
    assert result["readiness_decision"]["solver_or_model_executed"] is False
    assert result["readiness_decision"]["prediction_ready"] is False


def test_battery_pipeline_writes_only_ignored_local_outputs(tmp_path):
    repo = tmp_path
    source = repo / DEFAULT_KAGGLE_SUMMARY
    source.parent.mkdir(parents=True)
    _rows().to_csv(source, index=False)

    result = run_battery_pgir_pipeline(repo, output_root="outputs/battery_pgir_v2_3", write_local=True)

    assert result["readiness_decision"]["observation_count"] == 3
    assert (repo / "outputs/battery_pgir_v2_3/observations/cycle_observations.jsonl").exists()
    assert not (repo / "data/processed/battery_v2_3_representation_coverage.csv").exists()


def test_tracked_summary_export_is_compact_and_row_level_free(tmp_path):
    source = tmp_path / DEFAULT_KAGGLE_SUMMARY
    source.parent.mkdir(parents=True)
    source.write_bytes(Path(DEFAULT_KAGGLE_SUMMARY).read_bytes())

    export = export_tracked_battery_pgir_summaries(tmp_path)
    summary = load_battery_pgir_summary(tmp_path)

    assert export["status"] == "exported"
    assert summary["status"] == "available"
    assert summary["readiness_decision"]["observation_count"] == 2495
    tracked_text = (tmp_path / "data/processed/battery_v2_3_pgir_readiness_decision.json").read_text(
        encoding="utf-8"
    )
    assert "battery_obs_" not in tracked_text
    assert ("C:" + "/") not in tracked_text


def test_load_cycle_summary_rejects_missing_required_columns(tmp_path):
    bad = tmp_path / DEFAULT_KAGGLE_SUMMARY
    bad.parent.mkdir(parents=True)
    pd.DataFrame([{"battery_id": "B0005"}]).to_csv(bad, index=False)

    with pytest.raises(ValueError, match="missing columns"):
        load_battery_cycle_summary(tmp_path)
