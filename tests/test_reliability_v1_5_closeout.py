from __future__ import annotations

from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]


TRUST_OUTPUTS = [
    "reliability_v1_5_model_eligibility.csv",
    "reliability_v1_5_validation_stability_summary.csv",
    "reliability_v1_5_weighting_dependency_summary.csv",
    "reliability_v1_5_resource_boundary.csv",
    "reliability_v1_5_operational_boundary.csv",
    "reliability_v1_5_claim_boundary.csv",
    "reliability_v1_5_trust_summary.csv",
    "reliability_v1_5_closeout_conclusion.csv",
]


def test_reliability_v1_5_closeout_outputs_are_compact_and_parseable() -> None:
    for name in TRUST_OUTPUTS:
        path = ROOT / "data" / "processed" / name
        df = pd.read_csv(path)
        assert not df.empty, name
        assert path.stat().st_size < 1_000_000, name
        assert None not in df.columns, name


def test_reliability_v1_5_closeout_outputs_do_not_leak_local_or_raw_identity() -> None:
    forbidden = [
        "KAGGLE_KEY=",
        "KAGGLE_USERNAME=",
        "password=",
        "secret=",
        "token=",
        "C:\\",
        "/Users/",
        "/home/",
        "serial_number",
    ]
    for name in TRUST_OUTPUTS:
        text = (ROOT / "data" / "processed" / name).read_text(encoding="utf-8")
        lowered = text.lower()
        for marker in forbidden:
            assert marker.lower() not in lowered, name


def test_reliability_v1_5_closeout_conclusion_is_release_ready_without_representative() -> None:
    conclusion = {
        row["field"]: row["value"]
        for _, row in pd.read_csv(
            ROOT / "data" / "processed" / "reliability_v1_5_closeout_conclusion.csv"
        ).iterrows()
    }

    assert conclusion["v1_5_release_readiness"] == "release_ready"
    assert conclusion["representative_model"] == "none_selected"
    assert conclusion["representative_model_selected"] == "false"
    assert conclusion["not_allowed_use"] == "production_alert_or_maintenance_automation"


def test_reliability_v1_5_trust_script_does_not_fit_models() -> None:
    script = (ROOT / "scripts" / "run_reliability_v1_5_trust_analysis.py").read_text(
        encoding="utf-8"
    )

    assert "sklearn" not in script
    assert ".fit(" not in script
    assert "predict_proba" not in script
    assert "import shap" not in script.lower()
    assert "read_csv(input_paths[\"classification_metrics\"])" in script
