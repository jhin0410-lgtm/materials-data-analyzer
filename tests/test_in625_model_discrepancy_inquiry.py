from __future__ import annotations

import copy
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop.evidence_packet import canonical_sha256
from materials_data_analyzer.research_loop.in625_model_discrepancy_inquiry import (
    In625ModelDiscrepancyInquiryError,
    run_in625_model_discrepancy_inquiry,
)


def _evaluation() -> dict:
    value = {
        "schema_version": "1.0",
        "policy_version": "1.0",
        "evaluation_type": "published_retrospective_amb2018_02_ac_comparison",
        "benchmark_contract_sha256": "a" * 64,
        "published_evidence_sha256": "b" * 64,
        "model_identity": {
            "model_id": "kollmannsberger-2019-anisotropic-conductivity",
            "model_class": "published_thermal_phase_change_anisotropic_conductivity",
            "computational_evidence_class": "published_computational_retrospective",
        },
        "calibration_record": {
            "parameter_fit_case_ids": ["B"],
            "reported_anisotropic_conductivity_scalars": {
                "theta_x": 1.0,
                "theta_y": 1.4,
                "theta_z": 0.9,
            },
            "parameters_reported_fixed_for_validation_case_ids": ["A", "C"],
        },
        "case_metrics": [
            {
                "case_id": "A",
                "responses": {
                    "width": {
                        "published_prediction_um": 146.4,
                        "observed_trace_mean_average_um": 144.86666666666667,
                        "observed_trace_mean_sample_sd_um": 3.0,
                        "observed_trace_mean_range_um": [142.0, 148.0],
                        "absolute_error_um": 1.5333333333333314,
                        "relative_error_fraction": 0.010584,
                        "absolute_error_over_trace_mean_sample_sd": 0.511111,
                        "prediction_within_observed_trace_mean_range": True,
                        "trace_spread_is_calibrated_uncertainty_interval": False,
                    },
                    "depth": {
                        "published_prediction_um": 44.6,
                        "observed_trace_mean_average_um": 42.5,
                        "observed_trace_mean_sample_sd_um": 2.0,
                        "observed_trace_mean_range_um": [40.0, 45.0],
                        "absolute_error_um": 2.1,
                        "relative_error_fraction": 0.049412,
                        "absolute_error_over_trace_mean_sample_sd": 1.05,
                        "prediction_within_observed_trace_mean_range": False,
                        "trace_spread_is_calibrated_uncertainty_interval": False,
                    },
                },
            },
            {
                "case_id": "C",
                "responses": {
                    "width": {
                        "published_prediction_um": 105.1,
                        "observed_trace_mean_average_um": 106.025,
                        "observed_trace_mean_sample_sd_um": 2.5,
                        "observed_trace_mean_range_um": [103.0, 109.0],
                        "absolute_error_um": 0.9250000000000114,
                        "relative_error_fraction": 0.008724,
                        "absolute_error_over_trace_mean_sample_sd": 0.37,
                        "prediction_within_observed_trace_mean_range": True,
                        "trace_spread_is_calibrated_uncertainty_interval": False,
                    },
                    "depth": {
                        "published_prediction_um": 27.3,
                        "observed_trace_mean_average_um": 29.6,
                        "observed_trace_mean_sample_sd_um": 1.8,
                        "observed_trace_mean_range_um": [27.0, 32.0],
                        "absolute_error_um": 2.3,
                        "relative_error_fraction": 0.077703,
                        "absolute_error_over_trace_mean_sample_sd": 1.277778,
                        "prediction_within_observed_trace_mean_range": False,
                        "trace_spread_is_calibrated_uncertainty_interval": False,
                    },
                },
            },
        ],
        "aggregate_ac_metrics": {
            "width_mae_um": 1.2291666666666714,
            "depth_mae_um": 2.2,
            "case_count": 2,
            "case_b_included": False,
        },
        "scientific_interpretation": {
            "parameter_fit_reported_case_b_only": True,
            "published_parameters_fixed_for_a_c": True,
            "strict_blind_model_selection_established": False,
            "eligible_as_strict_phase1_holdout_prediction": False,
            "eligible_as_retrospective_published_comparator": True,
        },
        "scientific_boundary": {
            "published_computational_result_is_empirical": False,
            "agreement_establishes_causality": False,
            "agreement_establishes_mechanistic_uniqueness": False,
            "prospective_blind_validation_established": False,
            "engineering_readiness_established": False,
            "scientific_status_promoted": False,
        },
    }
    value["evaluation_sha256"] = canonical_sha256(value)
    return value


def test_retrospective_discrepancy_reaches_critic_and_selects_evidence_search(
    tmp_path: Path,
) -> None:
    evaluation = _evaluation()
    result = run_in625_model_discrepancy_inquiry(
        evaluation,
        trusted_evaluation_sha256=canonical_sha256(evaluation),
        output_root=tmp_path / "inquiry",
    )

    assert len(result["competing_hypotheses"]) == 4
    assert all(
        item["verified_positive"] is False
        for item in result["competing_hypotheses"]
    )
    assert (
        result["bounded_interpretation"][
            "retrospective_prediction_measurement_comparison_performed"
        ]
        is True
    )
    assert (
        result["bounded_interpretation"][
            "predictions_inside_observed_trace_mean_range_count"
        ]
        == 2
    )
    assert (
        result["bounded_interpretation"][
            "all_predictions_inside_observed_trace_mean_ranges"
        ]
        is False
    )
    assert (
        result["bounded_interpretation"]["prospective_blind_validation_established"]
        is False
    )
    assert result["bounded_interpretation"]["generalizable_physics_established"] is False

    plan = result["plan"]
    assert plan["scientific_critic_adapter"]["current_public_critic_contract_consumed"] is True
    assert plan["selected_next_action"]["action_class"] == "external_evidence_search"
    assert plan["selected_next_action"]["automatic_execution_authorized"] is False
    generated_searches = [
        item
        for item in plan["self_generated_gap_actions"]
        if item["action_class"] == "external_evidence_search"
    ]
    assert len(generated_searches) >= 2
    assert result["authority_boundary"]["hypothesis_truth_established"] is False
    assert result["authority_boundary"]["scientific_status_promoted"] is False


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        (
            ("calibration_record", "parameter_fit_case_ids"),
            ["B", "A"],
            "calibration partition drifted",
        ),
        (
            ("calibration_record", "parameters_reported_fixed_for_validation_case_ids"),
            ["A"],
            "calibration partition drifted",
        ),
        (
            ("scientific_interpretation", "strict_blind_model_selection_established"),
            True,
            "interpretation boundary drifted",
        ),
        (
            ("scientific_boundary", "prospective_blind_validation_established"),
            True,
            "scientific authority was widened",
        ),
        (
            ("scientific_boundary", "engineering_readiness_established"),
            True,
            "scientific authority was widened",
        ),
        (
            ("scientific_boundary", "scientific_status_promoted"),
            True,
            "scientific authority was widened",
        ),
    ],
)
def test_rehashed_comparator_promotion_fails_closed(
    tmp_path: Path,
    path: tuple[str, str],
    value: object,
    message: str,
) -> None:
    evaluation = _evaluation()
    forged = copy.deepcopy(evaluation)
    forged[path[0]][path[1]] = value
    forged.pop("evaluation_sha256")
    forged["evaluation_sha256"] = canonical_sha256(forged)

    with pytest.raises(In625ModelDiscrepancyInquiryError, match=message):
        run_in625_model_discrepancy_inquiry(
            forged,
            trusted_evaluation_sha256=canonical_sha256(forged),
            output_root=tmp_path / f"forged-{path[1]}",
        )


def test_external_root_rejects_rehashed_evaluation_mutation(tmp_path: Path) -> None:
    evaluation = _evaluation()
    trusted = canonical_sha256(evaluation)
    forged = copy.deepcopy(evaluation)
    forged["aggregate_ac_metrics"]["width_mae_um"] = 0.0
    forged.pop("evaluation_sha256")
    forged["evaluation_sha256"] = canonical_sha256(forged)

    with pytest.raises(In625ModelDiscrepancyInquiryError, match="external trust-root"):
        run_in625_model_discrepancy_inquiry(
            forged,
            trusted_evaluation_sha256=trusted,
            output_root=tmp_path / "forged-root",
        )


def test_duplicate_or_missing_holdout_case_fails_closed(tmp_path: Path) -> None:
    evaluation = _evaluation()
    forged = copy.deepcopy(evaluation)
    forged["case_metrics"][1]["case_id"] = "A"
    forged.pop("evaluation_sha256")
    forged["evaluation_sha256"] = canonical_sha256(forged)

    with pytest.raises(
        In625ModelDiscrepancyInquiryError,
        match="exactly one A and one C",
    ):
        run_in625_model_discrepancy_inquiry(
            forged,
            trusted_evaluation_sha256=canonical_sha256(forged),
            output_root=tmp_path / "duplicate-case",
        )
