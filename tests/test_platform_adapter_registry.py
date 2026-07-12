import pytest

from src.platform_core.adapter_registry import AdapterRegistry, build_default_adapter_registry
from src.platform_core.adapters import AdapterMetadata
from src.platform_core.artifacts import ArtifactMetadata, ArtifactRegistry, build_default_artifact_registry
from src.platform_core.plugins import PluginMetadata
from src.platform_core.registry import PluginRegistry, build_default_plugin_registry


def _minimal_registries():
    plugin_registry = PluginRegistry()
    artifact_registry = ArtifactRegistry()
    plugin_registry.register(
        PluginMetadata(
            plugin_id="demo",
            case_study_id="demo",
            description="demo",
            supported_stages=("trust",),
        )
    )
    artifact_registry.register(
        ArtifactMetadata(
            artifact_id="demo_input",
            case_study_id="demo",
            stage="trust",
            relative_path="data/processed/demo_input.csv",
            artifact_type="summary",
            format="csv",
            tracked_policy="generated_compact",
            local_only=False,
        )
    )
    return plugin_registry, artifact_registry


def _adapter(**overrides):
    values = {
        "adapter_id": "demo_trust",
        "plugin_id": "demo",
        "case_study_id": "demo",
        "stage": "trust",
        "module_path": "scripts/demo.py",
        "callable_name": "main",
        "execution_mode": "dry_run_safe",
        "required_artifacts": ("demo_input",),
    }
    values.update(overrides)
    return AdapterMetadata(**values)


def test_default_adapter_listing_is_deterministic():
    plugin_registry = build_default_plugin_registry()
    artifact_registry = build_default_artifact_registry()
    registry = build_default_adapter_registry(plugin_registry, artifact_registry)

    assert [adapter.adapter_id for adapter in registry.list_adapters()] == [
        "materials_project_trust_closeout",
        "reliability_trust_closeout",
        "smart_factory_trust_closeout",
    ]


def test_duplicate_and_unknown_adapter_rejected():
    plugin_registry, artifact_registry = _minimal_registries()
    registry = AdapterRegistry()
    adapter = _adapter()
    registry.register(adapter, plugin_registry, artifact_registry)

    with pytest.raises(ValueError, match="duplicate adapter_id"):
        registry.register(adapter, plugin_registry, artifact_registry)
    with pytest.raises(KeyError, match="unknown adapter_id"):
        registry.get("missing")


def test_plugin_adapter_stage_and_artifact_mismatch_rejected():
    plugin_registry, artifact_registry = _minimal_registries()
    registry = AdapterRegistry()

    with pytest.raises(ValueError, match="does not support adapter stage"):
        registry.register(_adapter(stage="validation"), plugin_registry, artifact_registry)

    with pytest.raises(KeyError, match="unknown artifact_id"):
        registry.register(_adapter(required_artifacts=("missing",)), plugin_registry, artifact_registry)


def test_find_for_plugin_stage_returns_dry_run_safe_adapter():
    plugin_registry, artifact_registry = _minimal_registries()
    registry = AdapterRegistry()
    registry.register(_adapter(), plugin_registry, artifact_registry)

    matches = registry.find_for_plugin_stage("demo", "trust")

    assert [adapter.adapter_id for adapter in matches] == ["demo_trust"]
