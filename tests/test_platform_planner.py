from pathlib import Path

from src.platform_core.artifacts import build_default_artifact_registry
from src.platform_core.adapter_registry import build_default_adapter_registry
from src.platform_core.planner import build_dry_run_plan
from src.platform_core.registry import build_default_plugin_registry
from src.platform_core.trust_registry import build_default_trust_policy_registry
from src.platform_core.validation_registry import build_default_validation_policy_registry


def _registries():
    plugin_registry = build_default_plugin_registry()
    artifact_registry = build_default_artifact_registry()
    return (
        plugin_registry,
        artifact_registry,
        build_default_validation_policy_registry(),
        build_default_trust_policy_registry(),
        build_default_adapter_registry(plugin_registry, artifact_registry),
    )


def _config():
    return {
        "schema_version": "2.0",
        "pipeline_id": "reliability_demo",
        "case_study_id": "reliability",
        "plugin_id": "reliability",
        "adapter_id": "reliability_trust_closeout",
        "stage": "trust",
        "input_artifacts": ["reliability_v1_5_classification_metrics"],
        "tracked_outputs": ["reliability_v1_5_trust_summary"],
        "local_only_outputs": ["reliability_v1_5_classification_predictions"],
        "validator": "asset_time_combined_classification",
        "trust_policy": "reliability_asset_time_aware",
        "parameters": {"network_required": False, "model_training_required": False},
        "credential_policy": {"store_credentials": False},
        "dry_run": True,
    }


def test_dry_run_reports_manifest_ready_without_side_effects(tmp_path):
    before = set(tmp_path.iterdir())

    validation, plan = build_dry_run_plan(_config(), *_registries(), repo_root=Path.cwd())

    assert validation.valid
    assert plan.execution_status == "ready_for_dry_run_manifest"
    assert plan.adapter_id == "reliability_trust_closeout"
    assert plan.execution_allowed is False
    assert plan.network_requirement == "not_required"
    assert plan.raw_data_requirement == "not_required"
    assert plan.model_training_requirement == "not_required"
    assert set(tmp_path.iterdir()) == before


def test_dry_run_reports_missing_artifact_with_synthetic_repo_root(tmp_path):
    validation, plan = build_dry_run_plan(_config(), *_registries(), repo_root=tmp_path)

    assert validation.valid
    assert "blocked_missing_artifact" in plan.blocked_reasons
    assert plan.missing_inputs == ("reliability_v1_5_classification_metrics",)


def test_dry_run_blocks_network_or_model_training_requirement():
    config = _config()
    config["parameters"] = {"network_required": True, "model_training_required": True}

    validation, plan = build_dry_run_plan(config, *_registries(), repo_root=Path.cwd())

    assert validation.valid
    assert "blocked_network_required" in plan.blocked_reasons
    assert "blocked_model_training_required" in plan.blocked_reasons


def test_invalid_config_returns_blocked_invalid_config():
    config = _config()
    config["plugin_id"] = "missing"

    validation, plan = build_dry_run_plan(config, *_registries(), repo_root=Path.cwd())

    assert not validation.valid
    assert plan.execution_status == "blocked_invalid_config"
