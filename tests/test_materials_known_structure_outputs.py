import json
from pathlib import Path

import pandas as pd


PROCESSED = Path("data/processed")


def test_v2_2_5_compact_outputs_parse_and_preserve_boundaries():
    decision = json.loads((PROCESSED / "materials_v2_2_5_predictive_value_decision.json").read_text(encoding="utf-8"))
    cohort_summary = json.loads((PROCESSED / "materials_v2_2_5_known_structure_cohort_summary.json").read_text(encoding="utf-8"))
    feature_evidence = json.loads((PROCESSED / "materials_v2_2_5_feature_use_evidence.json").read_text(encoding="utf-8"))
    comparison = pd.read_csv(PROCESSED / "materials_v2_2_5_predictive_comparison_summary.csv")
    paired = pd.read_csv(PROCESSED / "materials_v2_2_5_paired_metric_summary.csv")
    uncertainty = pd.read_csv(PROCESSED / "materials_v2_2_5_prediction_uncertainty_summary.csv")
    feature_snapshot = pd.read_csv(PROCESSED / "materials_v2_2_5_feature_set_snapshot.csv")

    assert decision["schema_version"] == "2.2.5"
    assert decision["prediction_context"] == "known_structure_post_relaxation"
    assert decision["target_source"] == "original_v1_3_energy_above_hull"
    assert decision["representative_model_selected"] is False
    assert decision["representative_model"] == "none"
    assert decision["claim_boundary"]["graph_model_used"] is False
    assert decision["claim_boundary"]["gnn_model"] is False
    assert decision["claim_boundary"]["DFT_replacement"] is False
    assert decision["structure_predictive_value_status"] in {
        "structure_predictive_value_supported",
        "structure_predictive_value_limited",
        "random_only_structure_improvement",
        "structure_performance_degraded",
        "no_material_structure_improvement",
    }
    assert cohort_summary["cohort_rows"] == 838
    assert cohort_summary["snapshot_aligned_rows"] == 838
    assert feature_evidence["graph_model_used"] is False
    assert set(comparison["metric"]) >= {"mae", "rmse", "r2"}
    assert {"A_vs_D", "B_vs_E"}.issubset(set(paired["comparison_id"]))
    assert uncertainty["uncertainty_status"].eq("prediction_interval_evaluated").all()
    assert not feature_snapshot["feature_id"].str.contains("graph|target|energy_above_hull", case=False, regex=True).any()


def test_v2_2_5_tracked_outputs_have_no_row_level_structures_or_secrets():
    forbidden = [
        "MP_API_KEY",
        "KAGGLE_KEY",
        "fractional_coordinates",
        '"sites": [',
        "C:/",
        "C:\\",
        "/Users/",
    ]
    for path in PROCESSED.glob("materials_v2_2_5*"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for token in forbidden:
            assert token not in text
