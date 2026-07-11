"""Tests for generic classification trust-boundary summaries."""

from __future__ import annotations

import pandas as pd

from analyzers.classification_trust import (
    ClassificationTrustConfig,
    build_trust_outputs,
)


def _config() -> ClassificationTrustConfig:
    return ClassificationTrustConfig(
        case_study_version="test",
        source_artifact="relative/source.csv",
        source_sha256="abc123",
        baseline_model_name="dummy_prior",
        global_row_count=100,
        global_failure_count=10,
        min_temporal_pr_auc_lift_over_prevalence=0.08,
        min_final_pr_auc_lift_over_prevalence=0.08,
        min_temporal_dummy_lift_fold_rate=0.75,
        max_temporal_iqr_pr_auc=0.05,
        max_random_temporal_pr_auc_gap=0.05,
        min_threshold_recall=0.2,
        min_threshold_precision=0.1,
        min_supported_fold_count=2,
    )


def _metrics() -> pd.DataFrame:
    rows = []
    for split_id, dummy_ap, model_ap, test_failures in [
        ("fold_1", 0.10, 0.12, 2),
        ("fold_2", 0.10, 0.13, 3),
        ("final_holdout", 0.10, 0.11, 2),
    ]:
        for model, ap in [("dummy_prior", dummy_ap), ("weak_model", model_ap)]:
            rows.append(
                {
                    "case_study_version": "test",
                    "source_artifact": "relative/source.csv",
                    "source_sha256": "abc123",
                    "split_id": split_id,
                    "split_type": "chronological",
                    "validation_type": "primary_temporal",
                    "model_name": model,
                    "model_type": model,
                    "train_rows": 70,
                    "validation_rows": 0,
                    "test_rows": 10,
                    "train_failures": 8,
                    "validation_failures": 0,
                    "test_failures": test_failures,
                    "average_precision": ap,
                    "roc_auc": 0.5,
                    "recall": 0.0,
                    "precision": 0.0,
                    "mcc": 0.0,
                    "brier_score": 0.09,
                    "status": "valid",
                    "invalid_reason": "",
                }
            )
    for model, ap in [("dummy_prior", 0.10), ("weak_model", 0.30)]:
        rows.append(
            {
                "case_study_version": "test",
                "source_artifact": "relative/source.csv",
                "source_sha256": "abc123",
                "split_id": "random",
                "split_type": "random",
                "validation_type": "random_reference",
                "model_name": model,
                "model_type": model,
                "train_rows": 80,
                "validation_rows": 0,
                "test_rows": 20,
                "train_failures": 8,
                "validation_failures": 0,
                "test_failures": 2,
                "average_precision": ap,
                "roc_auc": 0.5,
                "recall": 0.0,
                "precision": 0.0,
                "mcc": 0.0,
                "brier_score": 0.09,
                "status": "valid",
                "invalid_reason": "",
            }
        )
    return pd.DataFrame(rows)


def _split_diagnostics() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "split_id": "fold_1",
                "validation_type": "primary_temporal",
                "train_rows": 70,
                "test_rows": 10,
                "leakage_status": "no_future_to_past",
            },
            {
                "split_id": "fold_2",
                "validation_type": "primary_temporal",
                "train_rows": 80,
                "test_rows": 10,
                "leakage_status": "no_future_to_past",
            },
            {
                "split_id": "final_holdout",
                "validation_type": "primary_temporal",
                "train_rows": 90,
                "test_rows": 10,
                "leakage_status": "no_future_to_past",
            },
        ]
    )


def _model_summary() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "model_name": "dummy_prior",
                "temporal_median_pr_auc": 0.10,
                "final_holdout_pr_auc": 0.10,
                "random_reference_pr_auc": 0.10,
                "dummy_temporal_median_pr_auc": 0.10,
            },
            {
                "model_name": "weak_model",
                "temporal_median_pr_auc": 0.12,
                "final_holdout_pr_auc": 0.11,
                "random_reference_pr_auc": 0.30,
                "dummy_temporal_median_pr_auc": 0.10,
            },
        ]
    )


def _gap() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "model_name": "weak_model",
                "metric": "average_precision",
                "random_reference_median": 0.30,
                "temporal_primary_median": 0.12,
                "random_minus_temporal_gap": 0.18,
                "interpretation": "large_random_temporal_gap_possible_nonstationarity",
            },
            {
                "model_name": "dummy_prior",
                "metric": "average_precision",
                "random_reference_median": 0.10,
                "temporal_primary_median": 0.10,
                "random_minus_temporal_gap": 0.0,
                "interpretation": "no_large_gap_signal",
            },
        ]
    )


def _threshold() -> pd.DataFrame:
    rows = []
    for split_id in ["fold_1", "fold_2", "final_holdout"]:
        for model in ["dummy_prior", "weak_model"]:
            rows.append(
                {
                    "split_id": split_id,
                    "validation_type": "primary_temporal",
                    "model_name": model,
                    "true_positive": 0,
                    "false_positive": 1,
                    "false_negative": 2,
                    "true_negative": 7,
                    "recall": 0.0,
                    "precision": 0.0,
                    "specificity": 0.875,
                    "negative_predictive_value": 0.777,
                    "f1": 0.0,
                    "mcc": 0.0,
                    "threshold": 0.5,
                    "status": "valid",
                }
            )
    return pd.DataFrame(rows)


def _empty_error() -> pd.DataFrame:
    return pd.DataFrame(
        [{"summary_type": "all", "model_name": "weak_model", "split_id": "fold_1"}]
    )


def _conclusion() -> pd.DataFrame:
    return pd.DataFrame([{"field": "representative_model", "value": "none"}])


def test_trust_outputs_compute_prevalence_and_dummy_lift() -> None:
    outputs = build_trust_outputs(
        metrics=_metrics(),
        split_diagnostics=_split_diagnostics(),
        model_summary=_model_summary(),
        random_temporal_gap=_gap(),
        threshold_summary=_threshold(),
        error_structure=_empty_error(),
        classification_conclusion=_conclusion(),
        config=_config(),
    )
    eligibility = outputs["model_eligibility"].set_index("model_name")

    assert eligibility.loc["weak_model", "prevalence_baseline"] == 0.10
    assert eligibility.loc["weak_model", "temporal_lift_over_prevalence"] > 0
    assert "random_temporal_gap_too_large" in eligibility.loc["weak_model", "rejection_reasons"]


def test_temporal_stability_records_iqr_and_supported_folds() -> None:
    outputs = build_trust_outputs(
        metrics=_metrics(),
        split_diagnostics=_split_diagnostics(),
        model_summary=_model_summary(),
        random_temporal_gap=_gap(),
        threshold_summary=_threshold(),
        error_structure=_empty_error(),
        classification_conclusion=_conclusion(),
        config=_config(),
    )
    stability = outputs["temporal_stability_summary"].set_index("model_name")

    assert stability.loc["weak_model", "supported_fold_count"] == 3
    assert stability.loc["weak_model", "temporal_iqr_pr_auc"] >= 0


def test_representative_model_none_when_gate_fails() -> None:
    outputs = build_trust_outputs(
        metrics=_metrics(),
        split_diagnostics=_split_diagnostics(),
        model_summary=_model_summary(),
        random_temporal_gap=_gap(),
        threshold_summary=_threshold(),
        error_structure=_empty_error(),
        classification_conclusion=_conclusion(),
        config=_config(),
    )
    eligibility = outputs["model_eligibility"]

    assert not eligibility["representative_model_selected"].any()
    assert eligibility.set_index("model_name").loc["weak_model", "eligibility_status"] == "diagnostic_only"


def test_claim_and_operational_boundaries_are_machine_readable() -> None:
    outputs = build_trust_outputs(
        metrics=_metrics(),
        split_diagnostics=_split_diagnostics(),
        model_summary=_model_summary(),
        random_temporal_gap=_gap(),
        threshold_summary=_threshold(),
        error_structure=_empty_error(),
        classification_conclusion=_conclusion(),
        config=_config(),
    )

    claims = outputs["claim_boundary"]
    operational = outputs["operational_boundary"]
    assert {"allowed", "prohibited"}.issubset(set(claims["status"]))
    assert "calibration" in set(operational["boundary_type"])
    assert "drift_model" in set(operational["boundary_type"])
    assert "explainability" in set(operational["boundary_type"])


def test_closeout_conclusion_marks_release_ready_for_diagnostic_closeout() -> None:
    outputs = build_trust_outputs(
        metrics=_metrics(),
        split_diagnostics=_split_diagnostics(),
        model_summary=_model_summary(),
        random_temporal_gap=_gap(),
        threshold_summary=_threshold(),
        error_structure=_empty_error(),
        classification_conclusion=_conclusion(),
        config=_config(),
    )

    closeout = outputs["closeout_conclusion"].set_index("field")
    assert closeout.loc["v1_4_release_readiness", "value"] == "release_ready"
    assert closeout.loc["representative_model", "value"] == "none"
