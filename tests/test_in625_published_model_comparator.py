from __future__ import annotations

import copy
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop.evidence_packet import canonical_sha256
from materials_data_analyzer.research_loop.in625_model_holdout_benchmark import (
    build_in625_ambench_holdout_contract,
)
from materials_data_analyzer.research_loop.in625_published_model_comparator import (
    In625PublishedComparatorError,
    evaluate_kollmannsberger_retrospective_comparator,
)


ROOT = Path(__file__).resolve().parents[1]


def _published_fixture() -> dict:
    evidence = {
        "schema_version": "1.0",
        "policy_version": "1.0",
        "evidence_type": "published_retrospective_model_prediction_source",
        "source_bindings": [
            {
                "source_id": "fixture-source",
                "sha256": "a" * 64,
                "raw_source_bytes_persisted": False,
            }
        ],
        "article_identity": {
            "title": "fixture",
            "doi": "10.1007/s40192-019-00132-9",
            "authors": ["fixture"],
            "publication_year": 2019,
        },
        "model_identity": {
            "model_id": "kollmannsberger-2019-anisotropic-conductivity",
            "model_class": (
                "published_thermal_phase_change_anisotropic_conductivity"
            ),
            "computational_evidence_class": (
                "published_computational_retrospective"
            ),
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
        "published_predictions": [
            {
                "case_id": "A",
                "melt_pool_length_um": 304.0,
                "melt_pool_width_mean_um": 146.4,
                "melt_pool_depth_mean_um": 44.6,
            },
            {
                "case_id": "B",
                "melt_pool_length_um": 362.0,
                "melt_pool_width_mean_um": 123.7,
                "melt_pool_depth_mean_um": 36.1,
            },
            {
                "case_id": "C",
                "melt_pool_length_um": 346.0,
                "melt_pool_width_mean_um": 105.1,
                "melt_pool_depth_mean_um": 27.3,
            },
        ],
        "retrospective_scope": {
            "case_b_parameter_calibration_reported": True,
            "a_c_parameters_reported_fixed_after_case_b_calibration": True,
            "strict_prospective_holdout_model_selection_established": False,
            "reason": "fixture",
            "eligible_claim": "retrospective_published_model_comparison",
            "ineligible_claim": "strict_blind_holdout_validation",
        },
        "authority_boundary": {
            "empirical_measurement_created": False,
            "published_values_promoted_to_empirical": False,
            "strict_blind_validation_claimed": False,
            "engineering_readiness_established": False,
            "scientific_status_promoted": False,
        },
    }
    evidence["report_sha256"] = canonical_sha256(evidence)
    return evidence


def test_retrospective_comparator_reports_small_ac_errors_without_blind_claim() -> None:
    contract = build_in625_ambench_holdout_contract(ROOT)
    evidence = _published_fixture()
    result = evaluate_kollmannsberger_retrospective_comparator(
        contract,
        evidence,
        trusted_contract_sha256=canonical_sha256(contract),
        trusted_evidence_sha256=canonical_sha256(evidence),
        repository_root=str(ROOT),
    )

    by_case = {item["case_id"]: item for item in result["case_metrics"]}
    assert by_case["A"]["responses"]["width"]["absolute_error_um"] == pytest.approx(
        1.5333333333333314
    )
    assert by_case["A"]["responses"]["depth"]["absolute_error_um"] == pytest.approx(
        2.1
    )
    assert by_case["C"]["responses"]["width"]["absolute_error_um"] == pytest.approx(
        0.9250000000000114
    )
    assert by_case["C"]["responses"]["depth"]["absolute_error_um"] == pytest.approx(
        2.3
    )
    assert result["aggregate_ac_metrics"]["width_mae_um"] == pytest.approx(
        1.2291666666666714
    )
    assert result["aggregate_ac_metrics"]["depth_mae_um"] == pytest.approx(2.2)
    assert (
        result["scientific_interpretation"][
            "strict_blind_model_selection_established"
        ]
        is False
    )
    assert (
        result["scientific_interpretation"][
            "eligible_as_retrospective_published_comparator"
        ]
        is True
    )
    assert (
        result["scientific_boundary"]["prospective_blind_validation_established"]
        is False
    )
    assert result["scientific_boundary"]["scientific_status_promoted"] is False


def test_rehashed_strict_blind_promotion_is_rejected_by_scope_contract() -> None:
    contract = build_in625_ambench_holdout_contract(ROOT)
    evidence = _published_fixture()
    forged = copy.deepcopy(evidence)
    forged["retrospective_scope"][
        "strict_prospective_holdout_model_selection_established"
    ] = True
    forged["retrospective_scope"]["eligible_claim"] = (
        "strict_blind_holdout_validation"
    )
    forged.pop("report_sha256")
    forged["report_sha256"] = canonical_sha256(forged)

    with pytest.raises(
        In625PublishedComparatorError,
        match="retrospective boundary drifted",
    ):
        evaluate_kollmannsberger_retrospective_comparator(
            contract,
            forged,
            trusted_contract_sha256=canonical_sha256(contract),
            trusted_evidence_sha256=canonical_sha256(forged),
            repository_root=str(ROOT),
        )


def test_external_evidence_root_rejects_rehashed_prediction_mutation() -> None:
    contract = build_in625_ambench_holdout_contract(ROOT)
    evidence = _published_fixture()
    trusted = canonical_sha256(evidence)
    forged = copy.deepcopy(evidence)
    forged["published_predictions"][0]["melt_pool_width_mean_um"] = 100.0
    forged.pop("report_sha256")
    forged["report_sha256"] = canonical_sha256(forged)

    with pytest.raises(In625PublishedComparatorError, match="external trust-root"):
        evaluate_kollmannsberger_retrospective_comparator(
            contract,
            forged,
            trusted_contract_sha256=canonical_sha256(contract),
            trusted_evidence_sha256=trusted,
            repository_root=str(ROOT),
        )


def test_missing_ac_prediction_fails_closed() -> None:
    contract = build_in625_ambench_holdout_contract(ROOT)
    evidence = _published_fixture()
    evidence["published_predictions"] = [
        item
        for item in evidence["published_predictions"]
        if item["case_id"] != "C"
    ]
    evidence.pop("report_sha256")
    evidence["report_sha256"] = canonical_sha256(evidence)

    with pytest.raises(
        In625PublishedComparatorError,
        match="A/C prediction coverage incomplete",
    ):
        evaluate_kollmannsberger_retrospective_comparator(
            contract,
            evidence,
            trusted_contract_sha256=canonical_sha256(contract),
            trusted_evidence_sha256=canonical_sha256(evidence),
            repository_root=str(ROOT),
        )
