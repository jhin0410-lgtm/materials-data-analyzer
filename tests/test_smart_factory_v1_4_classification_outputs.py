"""Tests for tracked Smart Factory v1.4.4 classification outputs."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROCESSED = PROJECT_ROOT / "data" / "processed"


METRICS_PATH = PROCESSED / "smart_factory_v1_4_classification_metrics.csv"
SPLIT_PATH = PROCESSED / "smart_factory_v1_4_classification_split_diagnostics.csv"
MODEL_PATH = PROCESSED / "smart_factory_v1_4_classification_model_summary.csv"
GAP_PATH = PROCESSED / "smart_factory_v1_4_random_temporal_gap.csv"
THRESHOLD_PATH = PROCESSED / "smart_factory_v1_4_threshold_summary.csv"
ERROR_PATH = PROCESSED / "smart_factory_v1_4_error_structure_summary.csv"
CONCLUSION_PATH = PROCESSED / "smart_factory_v1_4_classification_conclusion.csv"


def test_classification_metric_output_schema_and_validation_types() -> None:
    metrics = pd.read_csv(METRICS_PATH)

    required = {
        "split_id",
        "split_type",
        "validation_type",
        "model_name",
        "average_precision",
        "roc_auc",
        "brier_score",
        "threshold_policy",
        "status",
    }
    assert required.issubset(metrics.columns)
    assert {"primary_temporal", "random_reference"}.issubset(set(metrics["validation_type"]))
    assert metrics["status"].eq("valid").all()


def test_split_diagnostics_preserve_time_order_and_sample_separation() -> None:
    split = pd.read_csv(SPLIT_PATH)
    primary = split[split["validation_type"].eq("primary_temporal")]

    assert not primary.empty
    assert primary["sample_overlap_count"].eq(0).all()
    assert primary["temporal_overlap"].eq("none").all()
    assert primary["leakage_status"].eq("no_future_to_past").all()
    assert split[split["validation_type"].eq("random_reference")]["primary_evidence"].eq(False).all()


def test_model_summary_keeps_conservative_status_boundary() -> None:
    model_summary = pd.read_csv(MODEL_PATH)

    assert set(model_summary["model_status"]).issubset(
        {
            "descriptive_only",
            "diagnostic_only",
            "limited_predictive_evidence",
            "candidate_for_further_validation",
        }
    )
    assert not model_summary["selected_representative_model"].astype(str).str.lower().eq("true").any()


def test_random_temporal_gap_records_primary_metric_gap() -> None:
    gap = pd.read_csv(GAP_PATH)
    pr_auc = gap[gap["metric"].eq("average_precision")]

    assert not pr_auc.empty
    assert "random_minus_temporal_gap" in gap.columns
    assert pr_auc["interpretation"].notna().all()


def test_threshold_summary_uses_fixed_threshold_without_test_tuning() -> None:
    threshold = pd.read_csv(THRESHOLD_PATH)

    assert threshold["threshold"].eq(0.5).all()
    assert threshold["threshold_selected_using_test_labels"].eq(False).all()
    assert threshold["threshold_selection_policy"].eq("fixed_default_0_5").all()


def test_error_structure_summary_contains_temporal_and_missingness_strata() -> None:
    error = pd.read_csv(ERROR_PATH)

    assert {"all", "temporal_block", "missingness_quantile", "threshold_sensitivity"}.issubset(
        set(error["summary_type"])
    )
    assert {"false_negative_count", "false_positive_count", "score_median"}.issubset(
        error.columns
    )


def test_classification_conclusion_contains_claim_boundary() -> None:
    conclusion = pd.read_csv(CONCLUSION_PATH).set_index("field")

    assert conclusion.loc["primary_evidence", "value"] == "chronological_time_aware_validation"
    assert conclusion.loc["random_reference", "value"] == "optimistic_reference_only"
    assert conclusion.loc["group_aware_evidence", "value"] == "not_available"
    assert conclusion.loc["calibration_claim", "value"] == "uncalibrated_score_only"


def test_tracked_outputs_have_no_absolute_paths_or_credentials() -> None:
    for path in [
        METRICS_PATH,
        SPLIT_PATH,
        MODEL_PATH,
        GAP_PATH,
        THRESHOLD_PATH,
        ERROR_PATH,
        CONCLUSION_PATH,
    ]:
        text = path.read_text(encoding="utf-8")
        assert "C:\\" not in text
        assert "/home/" not in text
        assert "/Users/" not in text
        assert "api_key" not in text.lower()
        assert "secret" not in text.lower()
        assert "token" not in text.lower()
