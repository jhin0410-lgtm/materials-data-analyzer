import json
from pathlib import Path

from src.platform_core.adapter_registry import build_default_adapter_registry
from src.platform_core.artifacts import build_default_artifact_registry
from src.platform_core.config import validate_pipeline_config
from src.platform_core.executable_adapters import build_approved_adapter_callables
from src.platform_core.execution_policy import build_default_execution_policy_registry
from src.platform_core.execution_runtime import execute_adapter_runtime
from src.platform_core.planner import build_dry_run_plan
from src.platform_core.registry import build_default_plugin_registry
from src.platform_core.trust_registry import build_default_trust_policy_registry
from src.platform_core.validation_registry import build_default_validation_policy_registry


def _registries():
    plugin_registry = build_default_plugin_registry()
    artifact_registry = build_default_artifact_registry()
    validation_registry = build_default_validation_policy_registry()
    trust_registry = build_default_trust_policy_registry()
    adapter_registry = build_default_adapter_registry(plugin_registry, artifact_registry)
    execution_policy_registry = build_default_execution_policy_registry()
    return plugin_registry, artifact_registry, validation_registry, trust_registry, adapter_registry, execution_policy_registry


def _config():
    return {
        "schema_version": "2.0",
        "pipeline_id": "reliability_verify_test",
        "case_study_id": "reliability",
        "plugin_id": "reliability",
        "adapter_id": "reliability_trust_closeout",
        "stage": "trust",
        "execution_mode": "verify",
        "dry_run": False,
        "run_id": "test-reliability-verify",
        "output_directory": "outputs/platform_runs/test-reliability-verify",
        "input_artifacts": [
            "reliability_v1_5_classification_metrics",
            "reliability_v1_5_model_eligibility",
            "reliability_v1_5_validation_stability_summary",
            "reliability_v1_5_trust_summary",
            "reliability_v1_5_claim_boundary",
            "reliability_v1_5_closeout_conclusion",
        ],
        "validator": "asset_time_combined_classification",
        "trust_policy": "reliability_asset_time_aware",
        "credential_policy": {"store_credentials": False},
    }


def _write_reliability_compact_artifacts(root: Path):
    processed = root / "data" / "processed"
    processed.mkdir(parents=True)
    (processed / "reliability_v1_5_classification_metrics.csv").write_text(
        "metric,value\naverage_precision,0.1\n",
        encoding="utf-8",
    )
    (processed / "reliability_v1_5_model_eligibility.csv").write_text(
        "model_name,eligibility_status,representative_model_selected\n"
        "dummy_prior,descriptive_only,false\n"
        "random_forest,diagnostic_only,false\n",
        encoding="utf-8",
    )
    (processed / "reliability_v1_5_validation_stability_summary.csv").write_text(
        "model_name,primary_median_pr_auc\nrandom_forest,0.1\n",
        encoding="utf-8",
    )
    (processed / "reliability_v1_5_trust_summary.csv").write_text(
        "field,value,evidence\n"
        "representative_model_selected,false,none\n"
        "representative_model,none,none\n"
        "shap_status,deferred_not_justified,none\n"
        "survival_model_status,deferred_not_ready,none\n"
        "rul_model_status,deferred_not_ready,none\n"
        "combined_top_1_lift,62.9,none\n"
        "combined_top_1_precision,0.0703,none\n",
        encoding="utf-8",
    )
    (processed / "reliability_v1_5_claim_boundary.csv").write_text(
        "claim,status,evidence\n"
        "production-ready failure prediction,prohibited,no\n"
        "calibrated 7-day failure probability,prohibited,no\n"
        "survival probability or RUL estimate,prohibited,no\n",
        encoding="utf-8",
    )
    (processed / "reliability_v1_5_closeout_conclusion.csv").write_text(
        "field,value,evidence\n"
        "representative_model,none_selected,no\n"
        "v1_5_release_readiness,release_ready,yes\n",
        encoding="utf-8",
    )


def test_reliability_verify_runtime_writes_local_reports_only(tmp_path):
    _write_reliability_compact_artifacts(tmp_path)
    registries = _registries()
    validation = validate_pipeline_config(_config(), *registries[:5])
    _, plan = build_dry_run_plan(_config(), *registries[:5], repo_root=tmp_path)

    manifest, result = execute_adapter_runtime(
        config=_config(),
        validation=validation,
        plan=plan,
        plugin_registry=registries[0],
        adapter_registry=registries[4],
        artifact_registry=registries[1],
        trust_registry=registries[3],
        execution_policy_registry=registries[5],
        callables=build_approved_adapter_callables(),
        repository_root=tmp_path,
        execution_mode="verify",
        overwrite_manifest=True,
    )

    assert manifest["status"] == "verification_completed"
    assert manifest["lifecycle_events"][-1] == "verification_completed"
    assert manifest["side_effect_status"] == "allowed_outputs_only"
    assert result.metrics_summary["representative_model"] == "none_selected"
    report_path = tmp_path / result.produced_files[0]
    assert report_path.exists()
    assert json.loads(report_path.read_text(encoding="utf-8"))["status"] == "success"
    assert not (tmp_path / "data" / "raw").exists()
