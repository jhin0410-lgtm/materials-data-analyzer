from __future__ import annotations

import pandas as pd

from analyzers.reliability_trust import (
    ReliabilityTrustConfig,
    build_reliability_trust_outputs,
)


def _config() -> ReliabilityTrustConfig:
    return ReliabilityTrustConfig(
        case_study_version="v-test",
        source_artifact="data/processed/local_feature_dataset.csv",
        source_sha256="abc123",
        baseline_model_name="dummy_prior",
        eligible_origins=1000,
        positive_rows=10,
        positive_assets=5,
        total_assets=100,
    )


def _combo_rows(model_name: str, feature_set: str, weighting: str) -> list[dict[str, object]]:
    values = {
        "primary_asset_disjoint": 0.05 if model_name != "dummy_prior" else 0.01,
        "primary_time_aware": 0.06 if model_name != "dummy_prior" else 0.01,
        "primary_combined_asset_time": 0.07 if model_name != "dummy_prior" else 0.01,
        "optimistic_random_reference": 0.16 if model_name != "dummy_prior" else 0.01,
    }
    rows = []
    for validation_type, ap in values.items():
        split_id = {
            "primary_asset_disjoint": "asset_disjoint_stratified_80_20",
            "primary_time_aware": "final_month_holdout",
            "primary_combined_asset_time": "combined_asset_disjoint_future_holdout",
            "optimistic_random_reference": "stratified_random_row_reference_80_20",
        }[validation_type]
        rows.append(
            {
                "case_study_version": "v-test",
                "source_artifact": "data/processed/local_feature_dataset.csv",
                "source_sha256": "abc123",
                "split_id": split_id,
                "split_type": "combined_asset_time",
                "validation_type": validation_type,
                "claim_scope": "diagnostic",
                "feature_set": feature_set,
                "weighting_policy": weighting,
                "model_name": model_name,
                "model_type": model_name,
                "train_rows": 800,
                "validation_rows": 0,
                "test_rows": 200,
                "train_assets": 80,
                "validation_assets": 0,
                "test_assets": 20,
                "train_positives": 8,
                "validation_positives": 0,
                "test_positives": 2,
                "train_positive_assets": 4,
                "test_positive_assets": 1,
                "train_date_start": "2020-01-01",
                "train_date_end": "2020-02-01",
                "test_date_start": "2020-02-02",
                "test_date_end": "2020-02-10",
                "asset_overlap_count": 0,
                "temporal_overlap": "none",
                "sample_overlap_count": 0,
                "leakage_status": "asset_overlap_0",
                "feasibility_status": "feasible",
                "primary_evidence": validation_type != "optimistic_random_reference",
                "original_numeric_feature_count": 5,
                "original_categorical_feature_count": 1,
                "retained_numeric_feature_count": 5,
                "retained_categorical_feature_count": 1,
                "removed_all_missing_count": 0,
                "removed_high_missing_count": 0,
                "removed_constant_count": 0,
                "near_constant_retained_count": 0,
                "training_subsample_status": "subsampled_training"
                if model_name != "dummy_prior"
                else "not_subsampled",
                "fit_train_rows": 100 if model_name != "dummy_prior" else 800,
                "fit_train_assets": 80,
                "fit_train_positives": 8,
                "test_set_subsampled": False,
                "true_negative": 190,
                "false_positive": 8,
                "false_negative": 1,
                "true_positive": 1,
                "balanced_accuracy": 0.74,
                "mcc": 0.12,
                "f1": 0.18,
                "precision": 0.11,
                "recall": 0.50,
                "specificity": 0.96,
                "negative_predictive_value": 0.99,
                "accuracy": 0.95,
                "threshold": 0.5,
                "threshold_policy": "fixed_default_0_5",
                "predicted_positive_rate": 0.05,
                "test_prevalence": 0.01,
                "average_precision": ap,
                "average_precision_status": "valid",
                "roc_auc": 0.8,
                "roc_auc_status": "valid",
                "brier_score": 0.12,
                "log_loss": 0.3,
                "log_loss_status": "valid",
                "status": "valid",
                "invalid_reason": "",
            }
        )
    return rows


def _frames() -> dict[str, pd.DataFrame]:
    combos = [
        ("dummy_prior", "smart_only_conservative", "asset_balanced"),
        ("dummy_prior", "smart_only_conservative", "raw_row"),
        ("random_forest", "smart_only_conservative", "asset_balanced"),
        ("random_forest", "smart_only_conservative", "raw_row"),
    ]
    metrics_rows = [row for combo in combos for row in _combo_rows(*combo)]
    metrics = pd.DataFrame(metrics_rows)
    model_summary = (
        metrics.groupby(["model_name", "feature_set", "weighting_policy"], as_index=False)
        .agg(
            primary_median_pr_auc=("average_precision", "median"),
            combined_pr_auc=("average_precision", "max"),
            random_reference_pr_auc=("average_precision", "max"),
            primary_median_roc_auc=("roc_auc", "median"),
            primary_median_mcc=("mcc", "median"),
            primary_median_recall=("recall", "median"),
            primary_median_precision=("precision", "median"),
            primary_median_brier_score=("brier_score", "median"),
        )
    )
    model_summary["model_status"] = "candidate_for_further_validation"
    model_summary.loc[model_summary["model_name"].eq("dummy_prior"), "model_status"] = "diagnostic_only"
    model_summary["selected_representative_model"] = False
    model_summary["dummy_primary_median_pr_auc"] = 0.01
    model_summary["primary_pr_auc_improvement_vs_dummy"] = (
        model_summary["primary_median_pr_auc"] - 0.01
    )
    model_summary["random_primary_pr_auc_gap"] = 0.08
    model_summary["resource_status"] = "resource_limited_subsampled_training"
    model_summary.loc[model_summary["model_name"].eq("dummy_prior"), "resource_status"] = "not_subsampled"
    model_summary["decision_basis"] = "synthetic"
    top_rows = []
    for model, feature, weighting in combos:
        for fraction in [0.001, 0.005, 0.01, 0.05]:
            top_rows.append(
                {
                    "case_study_version": "v-test",
                    "source_artifact": "data/processed/local_feature_dataset.csv",
                    "source_sha256": "abc123",
                    "split_id": "combined_asset_disjoint_future_holdout",
                    "split_type": "combined_asset_time",
                    "validation_type": "primary_combined_asset_time",
                    "claim_scope": "diagnostic",
                    "feature_set": feature,
                    "weighting_policy": weighting,
                    "model_name": model,
                    "model_type": model,
                    "split_rows": 200,
                    "top_fraction": fraction,
                    "top_n": max(1, int(200 * fraction)),
                    "positive_rows_in_top": 1 if model != "dummy_prior" else 0,
                    "precision_at_top_fraction": 0.5 if model != "dummy_prior" else 0.0,
                    "lift_over_prevalence": 50.0 if model != "dummy_prior" else 0.0,
                    "failed_asset_capture_rate": 0.4 if model != "dummy_prior" else 0.0,
                    "status": "valid",
                }
            )
    split_diagnostics = pd.DataFrame(
        [
            {
                "split_id": "combined_asset_disjoint_future_holdout",
                "split_type": "combined_asset_time",
                "train_rows": 800,
                "test_rows": 200,
                "train_assets": 80,
                "test_assets": 20,
                "train_positives": 8,
                "test_positives": 2,
                "asset_overlap_count": 0,
                "temporal_overlap": "none",
                "leakage_status": "asset_overlap_0",
            }
        ]
    )
    event = pd.DataFrame(
        [
            {
                "failure_followed_by_later_observation_asset_count": 1,
                "failure_asset_missing_previous_history_count": 1,
            }
        ]
    )
    readiness = pd.DataFrame([{"overall_readiness": "conditionally_ready"}])
    censoring = pd.DataFrame(
        [{"censoring_status": "administrative_end_of_archive", "asset_count": 10}]
    )
    conclusion = pd.DataFrame(
        [{"field": "representative_model", "value": "none_selected", "evidence": "test"}]
    )
    return {
        "metrics": metrics,
        "split_diagnostics": split_diagnostics,
        "model_summary": model_summary,
        "top_risk_summary": pd.DataFrame(top_rows),
        "threshold_summary": metrics.copy(),
        "error_structure_summary": metrics[["model_name", "feature_set", "weighting_policy"]].head(1),
        "classification_conclusion": conclusion,
        "full_readiness_summary": readiness,
        "event_integrity_summary": event,
        "censoring_summary": censoring,
    }


def test_reliability_trust_marks_resource_limited_models_diagnostic_only() -> None:
    outputs = build_reliability_trust_outputs(config=_config(), **_frames())

    eligibility = outputs["model_eligibility"]
    non_dummy = eligibility[~eligibility["model_name"].eq("dummy_prior")]

    assert non_dummy["eligibility_status"].eq("diagnostic_only").all()
    assert not eligibility["representative_model_selected"].astype(bool).any()
    assert non_dummy["rejection_reasons"].str.contains("resource_limited").all()


def test_reliability_trust_records_prevalence_lift_and_random_gap() -> None:
    outputs = build_reliability_trust_outputs(config=_config(), **_frames())

    eligibility = outputs["model_eligibility"]
    rf = eligibility[eligibility["model_name"].eq("random_forest")].iloc[0]
    stability = outputs["validation_stability_summary"]

    assert rf["prevalence_baseline"] == 0.01
    assert rf["lift_over_prevalence_ratio"] > 1
    assert "random_optimistic" in set(stability["stability_status"])


def test_reliability_trust_outputs_claim_boundaries_and_deferrals() -> None:
    outputs = build_reliability_trust_outputs(config=_config(), **_frames())

    claims = outputs["claim_boundary"]
    operational = outputs["operational_boundary"]
    closeout = {row["field"]: row["value"] for _, row in outputs["closeout_conclusion"].iterrows()}

    assert "calibrated 7-day failure probability" in set(claims["claim"])
    assert "prohibited" in set(claims["status"])
    assert "shap_deferred_not_justified" in set(operational["status"])
    assert closeout["representative_model"] == "none_selected"
