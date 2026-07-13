import copy
import json
from pathlib import Path

from src.platform_core.adapter_registry import build_default_adapter_registry
from src.platform_core.artifacts import build_default_artifact_registry
from src.platform_core.case_study_registry import build_default_case_study_registry
from src.platform_core.onboarding import load_and_validate_onboarding_config, validate_onboarding_config
from src.platform_core.registry import build_default_plugin_registry
from src.platform_core.trust_registry import build_default_trust_policy_registry
from src.platform_core.validation_registry import build_default_validation_policy_registry


def _registries():
    plugin_registry = build_default_plugin_registry()
    artifact_registry = build_default_artifact_registry()
    validation_registry = build_default_validation_policy_registry()
    trust_registry = build_default_trust_policy_registry()
    adapter_registry = build_default_adapter_registry(plugin_registry, artifact_registry)
    case_study_registry = build_default_case_study_registry(
        plugin_registry,
        artifact_registry,
        validation_registry,
        trust_registry,
        adapter_registry,
    )
    return case_study_registry, validation_registry, trust_registry


def _example_config():
    return json.loads(Path("configs/examples/environmental_monitoring_onboarding.json").read_text(encoding="utf-8"))


def _validate(config):
    case_study_registry, validation_registry, trust_registry = _registries()
    return validate_onboarding_config(
        config,
        case_study_registry=case_study_registry,
        validation_registry=validation_registry,
        trust_registry=trust_registry,
    )


def test_environmental_onboarding_example_is_metadata_only_valid():
    result = load_and_validate_onboarding_config(
        "configs/examples/environmental_monitoring_onboarding.json",
        case_study_registry=_registries()[0],
        validation_registry=_registries()[1],
        trust_registry=_registries()[2],
    )

    assert result.valid is True
    assert result.status == "valid_metadata_only"
    assert result.readiness_matrix["adapter_mapped"] is False
    assert result.readiness_matrix["executable_allowed"] is False


def test_onboarding_rejects_duplicate_existing_case_study_id():
    config = _example_config()
    config["case_study_id"] = "reliability"

    result = _validate(config)

    assert not result.valid
    assert "case_study_id already registered: reliability" in result.errors


def test_time_aware_policy_requires_time_key():
    config = _example_config()
    config.pop("time_key")
    config.pop("time_key_unavailable_reason", None)

    result = _validate(config)

    assert not result.valid
    assert "time-aware validation policy requires time_key" in result.errors
    assert "time_key_unavailable_reason is required when time_key is unavailable" in result.errors


def test_group_aware_policy_requires_group_keys():
    config = _example_config()
    config["validation_policy"] = "group_aware_regression"
    config["group_keys"] = []
    config.pop("group_key_unavailable_reason", None)

    result = _validate(config)

    assert not result.valid
    assert "group-aware validation policy requires group_keys" in result.errors


def test_missing_trust_policy_blocks_execution_candidate():
    config = _example_config()
    config["trust_policy"] = "missing_policy"
    config["execution_candidate"] = True

    result = _validate(config)

    assert not result.valid
    assert result.status == "blocked_policy_mismatch"
    assert "unknown trust_policy: missing_policy" in result.errors


def test_execution_candidate_does_not_enable_execution():
    config = _example_config()
    config["execution_candidate"] = True

    result = _validate(config)

    assert result.valid
    assert result.status == "valid_execution_candidate"
    assert result.readiness_matrix["executable_allowed"] is False
    assert any("does not enable execution" in warning for warning in result.warnings)


def test_onboarding_load_rejects_non_object(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(["not", "object"]), encoding="utf-8")

    case_study_registry, validation_registry, trust_registry = _registries()

    try:
        load_and_validate_onboarding_config(
            path,
            case_study_registry=case_study_registry,
            validation_registry=validation_registry,
            trust_registry=trust_registry,
        )
    except ValueError as exc:
        assert "JSON object" in str(exc)
    else:
        raise AssertionError("non-object onboarding config should fail")


def test_onboarding_invalid_artifact_contracts_are_reported():
    config = copy.deepcopy(_example_config())
    config["artifact_definitions"][0]["path"] = "../outside.json"
    config["artifact_definitions"][1]["tracked_policy"] = "generated_compact"
    config["artifact_definitions"].append(copy.deepcopy(config["artifact_definitions"][0]))

    result = _validate(config)

    assert not result.valid
    assert any("path invalid" in error for error in result.errors)
    assert any("local_only/tracked conflict" in error for error in result.errors)
    assert any("duplicate artifact_id" in error for error in result.errors)
