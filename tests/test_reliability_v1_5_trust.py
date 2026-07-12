from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]


def test_reliability_v1_5_trust_spec_is_parseable_and_bounded() -> None:
    spec_path = ROOT / "data" / "case_studies" / "reliability" / "trust_spec_v1_5.json"
    spec = json.loads(spec_path.read_text(encoding="utf-8"))

    assert spec["case_study_version"] == "v1.5.5"
    assert spec["task"]["horizon_days"] == 7
    assert spec["task"]["lookback_days"] == 7
    assert spec["model_eligibility_rules"]["production_ready_status_exists"] is False
    assert spec["explainability_decision"]["shap_status"] == "deferred_not_justified"
    assert "calibrated 7-day failure probability" in spec["prohibited_claims"]
    assert "survival probability" in spec["prohibited_claims"]
    text = spec_path.read_text(encoding="utf-8")
    assert "KAGGLE_KEY" not in text
    assert "KAGGLE_USERNAME" not in text
    assert "secret=" not in text.lower()
    assert "token=" not in text.lower()
    assert not any(marker in text for marker in ["C:\\", "/Users/", "/home/"])


def test_reliability_v1_5_model_eligibility_preserves_none_representative() -> None:
    path = ROOT / "data" / "processed" / "reliability_v1_5_model_eligibility.csv"
    df = pd.read_csv(path)

    required = {
        "model_name",
        "feature_set",
        "weighting_policy",
        "input_model_status",
        "eligibility_status",
        "representative_model_selected",
        "top_1_precision",
        "top_1_lift",
        "rejection_reasons",
    }
    assert required.issubset(df.columns)
    assert len(df) == 16
    assert not df["representative_model_selected"].astype(bool).any()
    assert set(df["eligibility_status"]) == {"descriptive_only", "diagnostic_only"}
    non_dummy = df[~df["model_name"].eq("dummy_prior")]
    assert non_dummy["rejection_reasons"].str.contains("resource_limited").all()


def test_reliability_v1_5_trust_summary_matches_v154_reference_metrics() -> None:
    summary = {
        row["field"]: row["value"]
        for _, row in pd.read_csv(
            ROOT / "data" / "processed" / "reliability_v1_5_trust_summary.csv"
        ).iterrows()
    }

    assert summary["representative_model_selected"] == "false"
    assert summary["representative_model"] == "none"
    assert summary["combined_top_1_reference_model"] == (
        "random_forest|smart_plus_safe_operational_metadata|asset_balanced"
    )
    assert abs(float(summary["combined_top_1_precision"]) - 0.0702576) < 1e-6
    assert abs(float(summary["combined_top_1_lift"]) - 62.9233) < 1e-4
    assert abs(float(summary["combined_top_1_failed_asset_capture"]) - 0.846154) < 1e-6
    assert summary["survival_model_status"] == "deferred_not_ready"
    assert summary["rul_model_status"] == "deferred_not_ready"
    assert summary["shap_status"] == "deferred_not_justified"


def test_reliability_v1_5_claim_boundary_blocks_overclaims() -> None:
    claims = pd.read_csv(ROOT / "data" / "processed" / "reliability_v1_5_claim_boundary.csv")
    prohibited = set(claims[claims["status"].eq("prohibited")]["claim"])

    assert "production-ready failure prediction" in prohibited
    assert "calibrated 7-day failure probability" in prohibited
    assert "maintenance recommendation or replacement automation" in prohibited
    assert "survival probability or RUL estimate" in prohibited
    assert "84.6 percent prediction success" in prohibited
