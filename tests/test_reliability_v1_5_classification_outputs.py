from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from analyzers.asset_temporal_classification import (  # noqa: E402
    build_asset_time_gap_summary,
    build_classification_conclusion,
    build_model_summary,
)


def _metrics() -> pd.DataFrame:
    rows = []
    for split, validation, ap in [
        ("asset_disjoint_stratified_80_20", "primary_asset_disjoint", 0.05),
        ("final_month_holdout", "primary_time_aware", 0.04),
        ("combined_asset_disjoint_future_holdout", "primary_combined_asset_time", 0.02),
        ("stratified_random_row_reference_80_20", "optimistic_random_reference", 0.15),
    ]:
        rows.append(
            {
                "case_study_version": "v1.5.4",
                "source_artifact": "local",
                "source_sha256": "sha",
                "split_id": split,
                "split_type": "synthetic",
                "validation_type": validation,
                "claim_scope": "synthetic",
                "feature_set": "smart_only_conservative",
                "weighting_policy": "asset_balanced",
                "model_name": "logistic_regression",
                "model_type": "logistic_regression",
                "status": "valid",
                "training_subsample_status": "subsampled_training",
                "average_precision": ap,
                "roc_auc": 0.6,
                "mcc": 0.1,
                "recall": 0.2,
                "precision": 0.01,
                "brier_score": 0.02,
            }
        )
        rows.append({**rows[-1], "model_name": "dummy_prior", "model_type": "dummy_prior", "average_precision": 0.01})
    return pd.DataFrame(rows)


def test_model_summary_never_selects_representative_model() -> None:
    summary = build_model_summary(_metrics())

    assert "selected_representative_model" in summary.columns
    assert not summary["selected_representative_model"].any()
    assert set(summary["model_status"]).issubset(
        {
            "descriptive_only",
            "diagnostic_only",
            "limited_predictive_evidence",
            "candidate_for_further_validation",
            "resource_limited",
            "not_run",
        }
    )


def test_random_primary_gap_summary_marks_random_reference() -> None:
    gap = build_asset_time_gap_summary(_metrics())

    assert "random_minus_primary_gap" in gap.columns
    assert gap["interpretation"].astype(str).str.contains("random_reference").any()


def test_conclusion_records_claim_boundary() -> None:
    metrics = _metrics()
    model_summary = build_model_summary(metrics)
    split_diagnostics = pd.DataFrame(
        [
            {
                "validation_type": "primary_combined_asset_time",
                "split_id": "combined_asset_disjoint_future_holdout",
            }
        ]
    )
    conclusion = build_classification_conclusion(metrics, model_summary, split_diagnostics)

    assert "representative_model" in set(conclusion["field"])
    assert "prohibited_claim" in set(conclusion["field"])
    assert conclusion["value"].astype(str).str.contains("calibrated_probability").any()


def test_compact_outputs_are_machine_readable(tmp_path: Path) -> None:
    output = tmp_path / "metrics.csv"
    _metrics().to_csv(output, index=False)
    parsed = pd.read_csv(output)

    assert not parsed.empty
    assert not any(str(column).startswith("Unnamed:") for column in parsed.columns)
