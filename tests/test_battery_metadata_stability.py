from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest

from src.platform_core.battery_metadata_stability import (
    STABILITY_STATUSES,
    _external_data_decision,
    _join_source_metadata,
    _policies_from_payload,
    consolidate_policy_events,
    load_audit_config,
    parse_nasa_date_vector,
    run_predeclared_sensitivity,
)
from src.platform_core.battery_trajectory_evaluator import (
    CapacityTrajectoryFinding,
    CapacityTrajectoryInput,
    evaluate_capacity_trajectory,
)


def _analysis_tables():
    metadata = pd.DataFrame(
        {
            "type": ["discharge", "discharge"],
            "start_time": ["[2008. 4. 2. 15. 25. 41.593]", "[2008 4 3 16 26 42.5]"],
            "ambient_temperature": [24.0, 24.0],
            "battery_id": ["BTEST", "BTEST"],
            "test_id": [1, 2],
            "uid": [10, 11],
            "filename": ["a.csv", "b.csv"],
            "Capacity": [2.0, 1.9],
        }
    )
    analysis = pd.DataFrame(
        {
            "battery_id": ["BTEST", "BTEST"],
            "cycle_index": [1, 2],
            "ambient_temperature_c": [24.0, 24.0],
            "discharge_capacity_ah": [2.0, 1.9],
            "source_filename": ["a.csv", "b.csv"],
            "uid": [10, 11],
            "test_id": [1, 2],
        }
    )
    features = pd.DataFrame(
        {
            "battery_id": ["BTEST", "BTEST"],
            "cycle_index": [1, 2],
            "source_filename": ["a.csv", "b.csv"],
            "uid": [10, 11],
            "test_id": [1, 2],
            "discharge_duration_s": [100.0, 110.0],
            "voltage_mean_v": [3.7, 3.6],
            "voltage_min_v": [3.0, 3.0],
            "voltage_max_v": [4.2, 4.2],
            "current_mean_a": [-2.0, -2.0],
            "current_min_a": [-2.1, -2.1],
            "current_max_a": [-1.9, -1.9],
            "temperature_mean_c": [25.0, 25.5],
            "temperature_min_c": [24.0, 24.0],
            "temperature_max_c": [27.0, 28.0],
            "temperature_rise_c": [3.0, 4.0],
            "raw_sample_count": [10, 11],
            "feature_extraction_status": ["ok", "ok"],
        }
    )
    protocol = {
        "BTEST": {
            "protocol_group_id": "readme_test",
            "protocol_document": "README_test.txt",
            "protocol_document_sha256": "a" * 64,
        }
    }
    return metadata, analysis, features, protocol


def _trajectory() -> CapacityTrajectoryInput:
    cycles = tuple(range(1, 9))
    capacities = (2.0, 1.99, 1.98, 1.85, 1.84, 1.83, 1.82, 1.81)
    return CapacityTrajectoryInput(
        trajectory_id="synthetic_trajectory",
        cell_id="BTEST",
        cycle_indices=cycles,
        capacities=capacities,
        capacity_units=("Ah",) * len(cycles),
        ordered_state_refs=tuple(f"battery_state_BTEST_{cycle:05d}" for cycle in cycles),
        reference_capacity_method="first_n_median",
        recorded_reference_capacity=1.98,
    )


def _finding(trajectory_id: str, start: int, category: str = "abrupt_capacity_drop_candidate"):
    return CapacityTrajectoryFinding(
        finding_id=f"finding_{trajectory_id}_{category}_{start}",
        trajectory_id=trajectory_id,
        finding_category=category,
        finding_status="descriptive_candidate",
        start_cycle_index=start,
        end_cycle_index=start,
        cycle_gap=1,
        normalized_magnitude=0.1,
        absolute_capacity_magnitude=0.1,
        threshold_used=0.01,
        threshold_id="synthetic_predeclared",
        threshold_semantics="algorithmic_detection_policy_not_measurement_uncertainty",
        protocol_context_available=True,
        temperature_context_available=True,
        interpretation="synthetic descriptive finding",
    )


def test_tracked_config_predeclares_one_factor_policies_and_disables_credentials():
    payload = load_audit_config("configs/examples/battery_source_metadata_stability_audit.json")
    policies = _policies_from_payload(payload)

    assert len(policies) == 9
    assert {policy.policy_axis for policy in policies} == {
        "baseline",
        "threshold",
        "reference",
        "window",
        "gap",
    }
    assert payload["credential_policy"] == {
        "store_credentials": False,
        "network_access_required": False,
    }
    assert payload["network_policy"]["automatic_download"] is False
    assert "threshold_optimization" in payload["prohibited_actions"]


def test_nasa_date_vector_parser_preserves_fractional_seconds_and_rejects_invalid():
    parsed = parse_nasa_date_vector("[2008. 4. 2. 15. 25. 41.593]")

    assert parsed == pd.Timestamp("2008-04-02 15:25:41.593")
    assert pd.isna(parse_nasa_date_vector("not-a-date"))


def test_exact_source_join_recovers_only_supported_metadata():
    metadata, analysis, features, protocol = _analysis_tables()

    recovered = _join_source_metadata(metadata, analysis, features, protocol)

    assert recovered["cycle_start_timestamp"].notna().all()
    assert recovered["source_capacity_match"].all()
    assert recovered["ambient_temperature_match"].all()
    assert recovered["protocol_group_id"].tolist() == ["readme_test", "readme_test"]
    assert recovered["source_uncertainty_status"].eq("unavailable").all()
    assert recovered.loc[0, "elapsed_seconds_since_first_discharge"] == pytest.approx(0.0)
    assert recovered.loc[1, "discharge_duration_s"] == pytest.approx(110.0)


def test_source_join_rejects_missing_or_ambiguous_lineage():
    metadata, analysis, features, protocol = _analysis_tables()
    analysis.loc[1, "uid"] = 999
    with pytest.raises(ValueError, match="do not all map"):
        _join_source_metadata(metadata, analysis, features, protocol)

    metadata, analysis, features, protocol = _analysis_tables()
    metadata = pd.concat([metadata, metadata.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="must be unique"):
        _join_source_metadata(metadata, analysis, features, protocol)


def test_sensitivity_uses_predeclared_policies_without_overwriting_source_reference():
    payload = load_audit_config("configs/examples/battery_source_metadata_stability_audit.json")
    policies = _policies_from_payload(payload)
    trajectory = _trajectory()
    timestamps = pd.date_range("2008-01-01", periods=8, freq="D")
    recovered = pd.DataFrame(
        {
            "battery_id": ["BTEST"] * 8,
            "cycle_index": list(range(1, 9)),
            "cycle_start_timestamp": timestamps,
            "source_ambient_temperature_c": [24.0] * 8,
            "protocol_group_id": ["readme_test"] * 8,
        }
    )

    rows = run_predeclared_sensitivity([trajectory], recovered, policies)

    assert len(rows) == 9
    assert all(row["source_reference_overwritten"] is False for row in rows)
    assert sum(row["alternative_reference_audit"] for row in rows) == 2
    baseline = next(row for row in rows if row["policy_id"] == "baseline_v2_3_4")
    assert baseline["result"].reference_capacity == pytest.approx(1.98)
    assert baseline["result"].physical_elapsed_time_available is True


def test_event_consolidation_assigns_all_four_predeclared_stability_classes():
    base = evaluate_capacity_trajectory(_trajectory())
    policy_rows = []
    for index in range(9):
        findings = [_finding(base.trajectory_id, 1)]
        if index < 5:
            findings.append(_finding(base.trajectory_id, 10))
        if index in {1, 2}:
            findings.append(_finding(base.trajectory_id, 20))
        if index == 8:
            findings.append(_finding(base.trajectory_id, 30))
        result = replace(
            base,
            findings=tuple(findings),
            finding_counts={"abrupt_capacity_drop_candidate": len(findings)},
        )
        policy_rows.append(
            {
                "policy_id": "baseline_v2_3_4" if index == 0 else f"policy_{index}",
                "policy_axis": "baseline" if index == 0 else "threshold",
                "result": result,
            }
        )

    events = consolidate_policy_events(
        policy_rows,
        baseline_policy_id="baseline_v2_3_4",
        stable_ratio=1.0,
        restricted_ratio=0.5,
        minimum_policy_support=3,
        adjacency_cycles=0,
    )

    assert {event["stability_status"] for event in events} == set(STABILITY_STATUSES)
    assert {event["start_cycle_index"]: event["stability_status"] for event in events} == {
        1: "stable_across_policies",
        10: "stable_with_restrictions",
        20: "policy_sensitive",
        30: "insufficient_support",
    }


def test_external_source_routing_is_selective_and_never_downloads():
    decision = _external_data_decision({"source_evidence_checksum": "b" * 64})
    routing = {row["source"]: row for row in decision["preferred_routing"]}

    assert decision["automatic_download_performed"] is False
    assert decision["heterogeneous_dataset_combination_allowed"] is False
    assert routing["NASA PCoE"]["automatic_download"] is False
    assert routing["NIST OAR"]["role"] == "dataset discovery and metadata catalog only"
    assert routing["NREL_API_KEY"]["applicable"] is False
    assert routing["NVD_API_KEY"]["applicable"] is False


def test_module_contains_no_network_training_solver_or_dynamic_execution():
    text = Path("src/platform_core/battery_metadata_stability.py").read_text(encoding="utf-8")

    for fragment in (
        "import requests",
        "import urllib",
        "import socket",
        "import subprocess",
        "import importlib",
        "eval(",
        "exec(",
        ".fit(",
        ".predict(",
    ):
        assert fragment not in text
