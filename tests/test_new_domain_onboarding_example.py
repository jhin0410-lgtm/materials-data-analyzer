import json
from pathlib import Path

from src.platform_core.adapter_registry import build_default_adapter_registry
from src.platform_core.artifacts import build_default_artifact_registry
from src.platform_core.case_study_registry import build_default_case_study_registry
from src.platform_core.onboarding import load_and_validate_onboarding_config
from src.platform_core.registry import build_default_plugin_registry
from src.platform_core.trust_registry import build_default_trust_policy_registry
from src.platform_core.validation_registry import build_default_validation_policy_registry


def _registries():
    plugin_registry = build_default_plugin_registry()
    artifact_registry = build_default_artifact_registry()
    validation_registry = build_default_validation_policy_registry()
    trust_registry = build_default_trust_policy_registry()
    adapter_registry = build_default_adapter_registry(plugin_registry, artifact_registry)
    return (
        build_default_case_study_registry(
            plugin_registry,
            artifact_registry,
            validation_registry,
            trust_registry,
            adapter_registry,
        ),
        validation_registry,
        trust_registry,
    )


def test_environmental_example_is_not_registered_or_executable():
    config = json.loads(Path("configs/examples/environmental_monitoring_onboarding.json").read_text(encoding="utf-8"))
    case_study_registry, validation_registry, trust_registry = _registries()
    result = load_and_validate_onboarding_config(
        "configs/examples/environmental_monitoring_onboarding.json",
        case_study_registry=case_study_registry,
        validation_registry=validation_registry,
        trust_registry=trust_registry,
    )

    assert config.get("plugin_id") is None
    assert config.get("adapter_id") is None
    assert result.valid
    assert result.status == "valid_metadata_only"
    assert result.readiness_matrix["executable_allowed"] is False


def test_onboarding_schema_json_parse_and_names_required_statuses():
    schema = json.loads(Path("data/platform/case_study_onboarding_schema_v2.json").read_text(encoding="utf-8"))

    assert schema["schema_version"] == "2.0"
    assert "case_study_id" in schema["required_fields"]
    assert "valid_metadata_only" in schema["status_values"]
    assert "production_ready is not an onboarding status." in schema["policy_rules"]
