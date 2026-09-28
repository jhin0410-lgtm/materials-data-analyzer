from __future__ import annotations

import copy
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop.evidence_packet import canonical_sha256
from materials_data_analyzer.research_loop.in625_model_holdout_benchmark import (
    In625ModelHoldoutBenchmarkError,
    build_case_b_persistence_baseline,
    build_in625_ambench_holdout_contract,
    evaluate_in625_ambench_holdout_predictions,
)


ROOT = Path(__file__).resolve().parents[1]


def _frozen() -> tuple[dict, dict]:
    contract = build_in625_ambench_holdout_contract(ROOT)
    baseline = build_case_b_persistence_baseline(
        contract,
        trusted_contract_sha256=canonical_sha256(contract),
    )
    return contract, baseline


def test_contract_exposes_case_b_response_only_and_freezes_ac_holdout() -> None:
    contract = build_in625_ambench_holdout_contract(ROOT)

    assert contract["partition"] == {
        "calibration_case_ids": ["B"],
        "holdout_case_ids": ["A", "C"],
        "partition_frozen_before_prediction": True,
        "holdout_response_values_exposed_in_contract": False,
    }
    assert contract["calibration_response"]["case_id"] == "B"
    assert contract["calibration_response"]["trace_count"] == 3
    assert contract["calibration_response"]["width"]["trace_mean_average_um"] == pytest.approx(
        123.46666666666667
    )
    assert contract["calibration_response"]["depth"]["trace_mean_average_um"] == pytest.approx(
        35.96666666666667
    )
    assert contract["holdout_response_binding"]["values_embedded"] is False

    # A/C process inputs are visible, but their response values are intentionally absent.
    cases = {item["case_id"]: item for item in contract["process_conditions"]}
    assert cases["A"]["actual_laser_power_w"] == 137.9
    assert cases["C"]["scan_speed_mm_s"] == 1200.0
    assert "147.933333" not in repr(contract)
    assert "106.025" not in repr(contract)


def test_case_b_persistence_baseline_never_consumes_holdout_responses() -> None:
    contract, baseline = _frozen()

    assert baseline["model"]["model_class"] == "diagnostic_persistence_baseline_not_physics"
    assert baseline["calibration_provenance"] == {
        "response_case_ids_used_for_fit": ["B"],
        "response_case_ids_used_for_model_selection": [],
        "response_case_ids_used_for_hyperparameter_tuning": [],
        "holdout_response_values_consumed_before_prediction_freeze": False,
    }
    assert {item["case_id"] for item in baseline["predictions"]} == {"A", "C"}
    assert {
        item["melt_pool_width_mean_um"] for item in baseline["predictions"]
    } == {pytest.approx(123.46666666666667)}
    assert {
        item["melt_pool_depth_mean_um"] for item in baseline["predictions"]
    } == {pytest.approx(35.96666666666667)}
    assert baseline["scientific_boundary"]["physics_model_claimed"] is False


def test_holdout_evaluation_opens_ac_only_after_prediction_freeze() -> None:
    contract, baseline = _frozen()
    result = evaluate_in625_ambench_holdout_predictions(
        contract,
        baseline,
        trusted_contract_sha256=canonical_sha256(contract),
        trusted_prediction_sha256=canonical_sha256(baseline),
        repository_root=ROOT,
    )

    by_case = {item["case_id"]: item for item in result["case_metrics"]}
    assert by_case["A"]["responses"]["width"]["observed_trace_mean_average_um"] == pytest.approx(
        147.93333333333334
    )
    assert by_case["C"]["responses"]["width"]["observed_trace_mean_average_um"] == pytest.approx(
        106.025
    )
    assert by_case["A"]["responses"]["width"]["absolute_error_um"] == pytest.approx(
        24.46666666666667
    )
    assert by_case["C"]["responses"]["depth"]["absolute_error_um"] == pytest.approx(
        6.366666666666667
    )
    assert result["aggregate_holdout_metrics"]["width_mae_um"] == pytest.approx(
        20.954166666666666
    )
    assert result["aggregate_holdout_metrics"]["depth_mae_um"] == pytest.approx(6.45)
    assert result["aggregate_holdout_metrics"]["calibration_case_included"] is False
    assert result["scientific_boundary"]["trace_spread_interpreted_as_confidence_interval"] is False
    assert result["scientific_boundary"]["scientific_status_promoted"] is False


def test_declared_holdout_leakage_fails_even_when_prediction_is_rehashed() -> None:
    contract, baseline = _frozen()
    forged = copy.deepcopy(baseline)
    forged["calibration_provenance"]["response_case_ids_used_for_fit"] = ["B", "A"]
    forged.pop("prediction_sha256")
    forged["prediction_sha256"] = canonical_sha256(forged)

    with pytest.raises(In625ModelHoldoutBenchmarkError, match="leakage"):
        evaluate_in625_ambench_holdout_predictions(
            contract,
            forged,
            trusted_contract_sha256=canonical_sha256(contract),
            trusted_prediction_sha256=canonical_sha256(forged),
            repository_root=ROOT,
        )


def test_prediction_mutation_after_external_freeze_fails() -> None:
    contract, baseline = _frozen()
    trusted_prediction = canonical_sha256(baseline)
    forged = copy.deepcopy(baseline)
    forged["predictions"][0]["melt_pool_width_mean_um"] += 1.0
    forged.pop("prediction_sha256")
    forged["prediction_sha256"] = canonical_sha256(forged)

    with pytest.raises(In625ModelHoldoutBenchmarkError, match="external freeze-root"):
        evaluate_in625_ambench_holdout_predictions(
            contract,
            forged,
            trusted_contract_sha256=canonical_sha256(contract),
            trusted_prediction_sha256=trusted_prediction,
            repository_root=ROOT,
        )


def test_contract_partition_rehash_cannot_cross_external_trust_root() -> None:
    contract, _baseline = _frozen()
    trusted_contract = canonical_sha256(contract)
    forged = copy.deepcopy(contract)
    forged["partition"]["calibration_case_ids"] = ["A", "B"]
    forged["partition"]["holdout_case_ids"] = ["C"]
    forged.pop("contract_sha256")
    forged["contract_sha256"] = canonical_sha256(forged)

    with pytest.raises(In625ModelHoldoutBenchmarkError, match="external trust-root"):
        build_case_b_persistence_baseline(
            forged,
            trusted_contract_sha256=trusted_contract,
        )


def test_tampered_source_table_fails_frozen_sha(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    source_dir = root / "data/case_studies/nist_ambench_2018_02"
    source_dir.mkdir(parents=True)
    for name in ("source_process_conditions.csv", "source_melt_pool_measurements.csv"):
        source = ROOT / "data/case_studies/nist_ambench_2018_02" / name
        (source_dir / name).write_bytes(source.read_bytes())

    response = source_dir / "source_melt_pool_measurements.csv"
    response.write_bytes(response.read_bytes() + b"\n")

    with pytest.raises(In625ModelHoldoutBenchmarkError, match="SHA drifted"):
        build_in625_ambench_holdout_contract(root)
