import pytest

from src.platform_core.execution_policy import AdapterPermission, build_default_execution_policy_registry


def test_only_reliability_verify_is_executable():
    registry = build_default_execution_policy_registry()

    reliability = registry.get("reliability_trust_closeout")
    materials = registry.get("materials_project_trust_closeout")
    smart = registry.get("smart_factory_trust_closeout")

    assert reliability.execution_allowed is True
    assert reliability.allowed_modes == ("verify",)
    assert reliability.network_allowed is False
    assert reliability.raw_data_allowed is False
    assert reliability.model_training_allowed is False
    assert reliability.process_spawn_allowed is False
    assert reliability.canonical_overwrite_allowed is False
    assert materials.execution_allowed is False
    assert smart.execution_allowed is False


def test_execution_policy_rejects_permission_elevation():
    with pytest.raises(ValueError, match="cannot enable network"):
        AdapterPermission(
            adapter_id="bad",
            execution_allowed=True,
            allowed_modes=("verify",),
            network_allowed=True,
        )

    with pytest.raises(ValueError, match="cannot spawn processes"):
        AdapterPermission(
            adapter_id="bad2",
            execution_allowed=True,
            allowed_modes=("verify",),
            process_spawn_allowed=True,
        )
