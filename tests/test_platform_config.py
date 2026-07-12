import json
from pathlib import Path

from src.platform_core.artifacts import build_default_artifact_registry
from src.platform_core.config import load_and_validate_pipeline_config, validate_pipeline_config
from src.platform_core.registry import build_default_plugin_registry
from src.platform_core.trust_registry import build_default_trust_policy_registry
from src.platform_core.validation_registry import build_default_validation_policy_registry


def _registries():
    return (
        build_default_plugin_registry(),
        build_default_artifact_registry(),
        build_default_validation_policy_registry(),
        build_default_trust_policy_registry(),
    )


def _valid_config():
    return {
        "schema_version": "2.0",
        "pipeline_id": "demo",
        "case_study_id": "reliability",
        "plugin_id": "reliability",
        "stage": "trust",
        "input_artifacts": ["reliability_v1_5_classification_metrics"],
        "tracked_outputs": ["reliability_v1_5_trust_summary"],
        "local_only_outputs": ["reliability_v1_5_classification_predictions"],
        "validator": "asset_time_combined_classification",
        "trust_policy": "reliability_asset_time_aware",
        "resource_budget": {"max_runtime_seconds": 0},
        "credential_policy": {"store_credentials": False},
        "dry_run": True,
    }


def test_example_configs_validate():
    registries = _registries()
    for path in sorted(Path("configs/examples").glob("*_dry_run.json")):
        result = load_and_validate_pipeline_config(path, *registries)
        assert result.valid, (path, result.errors)


def test_config_version_and_required_fields():
    config = _valid_config()
    del config["plugin_id"]
    config["schema_version"] = "1.0"

    result = validate_pipeline_config(config, *_registries())

    assert not result.valid
    assert "missing required field: plugin_id" in result.errors
    assert any("unsupported schema_version" in error for error in result.errors)


def test_config_rejects_unknown_policy_and_unknown_field():
    config = _valid_config()
    config["validator"] = "missing_policy"
    config["extra"] = "not allowed"

    result = validate_pipeline_config(config, *_registries())

    assert not result.valid
    assert "unknown validation policy: missing_policy" in result.errors
    assert "unknown fields: extra" in result.errors


def test_config_rejects_absolute_component_path_and_credentials():
    config = _valid_config()
    config["loader"] = {"relative_path": "C:/tmp/local.csv"}
    config["credential_policy"] = {"store_credentials": True}

    result = validate_pipeline_config(config, *_registries())

    assert not result.valid
    assert any("absolute paths" in error for error in result.errors)
    assert "credential_policy.store_credentials must not be true" in result.errors


def test_config_json_load_rejects_non_object(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(["not", "object"]), encoding="utf-8")

    try:
        load_and_validate_pipeline_config(path, *_registries())
    except ValueError as exc:
        assert "JSON object" in str(exc)
    else:
        raise AssertionError("non-object config should fail")
