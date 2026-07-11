"""Tests for Smart Factory v1.4.5 trust closeout artifacts."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = PROJECT_ROOT / "data" / "case_studies" / "smart_factory" / "trust_spec_v1_4.json"
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "run_smart_factory_v1_4_trust_analysis.py"
PROCESSED = PROJECT_ROOT / "data" / "processed"


def _load_spec() -> dict:
    return json.loads(SPEC_PATH.read_text(encoding="utf-8"))


def _load_script_module():
    spec = importlib.util.spec_from_file_location("smart_factory_v14_trust", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_trust_spec_contains_predeclared_rules_and_boundaries() -> None:
    spec = _load_spec()

    assert spec["case_study_version"] == "v1.4.5"
    assert spec["model_eligibility_rules"]["production_ready_status_exists"] is False
    assert spec["threshold_rules"]["test_label_threshold_tuning"] is False
    assert spec["calibration_boundary"]["calibrated_probability_claim"] is False
    assert spec["drift_anomaly_decision"]["drift_model"] == "deferred"
    assert spec["explainability_decision"]["shap_status"] == "deferred_not_justified"


def test_trust_script_does_not_import_network_or_model_training_clients() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "urllib" not in source
    assert "requests" not in source
    assert "httpx" not in source
    assert "fit(" not in source
    assert "predict(" not in source


def test_trust_output_schemas_and_model_statuses() -> None:
    eligibility = pd.read_csv(PROCESSED / "smart_factory_v1_4_model_eligibility.csv")
    trust = pd.read_csv(PROCESSED / "smart_factory_v1_4_trust_summary.csv").set_index("field")

    assert {
        "model_name",
        "temporal_median_pr_auc",
        "prevalence_baseline",
        "eligibility_status",
        "representative_model_selected",
        "rejection_reasons",
    }.issubset(eligibility.columns)
    non_dummy = eligibility[~eligibility["model_name"].eq("dummy_prior")]
    assert non_dummy["eligibility_status"].eq("diagnostic_only").all()
    assert not eligibility["representative_model_selected"].astype(bool).any()
    assert trust.loc["representative_model_selected", "value"] == "false"


def test_operational_boundary_records_calibration_spc_and_shap_decisions() -> None:
    boundary = pd.read_csv(PROCESSED / "smart_factory_v1_4_operational_boundary.csv")
    statuses = dict(zip(boundary["boundary_type"], boundary["status"]))

    assert statuses["calibration"] == "uncalibrated_score_only"
    assert statuses["capability_indices"] == "not_ready_no_specification_limits"
    assert statuses["drift_model"] == "deferred"
    assert statuses["anomaly_model"] == "deferred"
    assert statuses["explainability"] == "shap_deferred_not_justified"


def test_claim_boundary_has_allowed_and_prohibited_claims() -> None:
    claims = pd.read_csv(PROCESSED / "smart_factory_v1_4_claim_boundary.csv")

    assert {"allowed", "prohibited"}.issubset(set(claims["status"]))
    prohibited = set(claims.loc[claims["status"].eq("prohibited"), "claim"])
    assert "production-ready model" in prohibited
    assert "calibrated probability" in prohibited
    assert "causal root cause" in prohibited


def test_trust_outputs_have_no_absolute_paths_or_auth_material() -> None:
    for path in [
        PROCESSED / "smart_factory_v1_4_model_eligibility.csv",
        PROCESSED / "smart_factory_v1_4_temporal_stability_summary.csv",
        PROCESSED / "smart_factory_v1_4_operational_boundary.csv",
        PROCESSED / "smart_factory_v1_4_claim_boundary.csv",
        PROCESSED / "smart_factory_v1_4_trust_summary.csv",
        PROCESSED / "smart_factory_v1_4_closeout_conclusion.csv",
    ]:
        text = path.read_text(encoding="utf-8")
        assert "C:\\" not in text
        assert "/home/" not in text
        assert "/Users/" not in text
        assert "api_key" not in text.lower()
        assert "secret" not in text.lower()
        assert "token" not in text.lower()
        assert "password" not in text.lower()


def test_trust_script_summary_uses_existing_outputs_without_raw_data() -> None:
    module = _load_script_module()
    spec = _load_spec()
    paths = {name: Path(path) for name, path in spec["input_artifacts"].items()}

    metrics = pd.read_csv(paths["classification_metrics"])
    split = pd.read_csv(paths["classification_split_diagnostics"])
    model = pd.read_csv(paths["classification_model_summary"])

    module.validate_required_columns(metrics, split, model)
