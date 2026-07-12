import pytest

from src.platform_core.plugins import PluginMetadata
from src.platform_core.registry import PluginRegistry, build_default_plugin_registry


def test_default_plugin_listing_is_deterministic():
    registry = build_default_plugin_registry()

    plugin_ids = [plugin.plugin_id for plugin in registry.list_plugins()]

    assert plugin_ids == ["battery_archive", "materials_project", "reliability", "smart_factory"]


def test_duplicate_plugin_rejected():
    registry = PluginRegistry()
    plugin = PluginMetadata(
        plugin_id="demo",
        case_study_id="demo_case",
        description="demo",
        supported_stages=("trust",),
    )

    registry.register(plugin)

    with pytest.raises(ValueError, match="duplicate plugin_id"):
        registry.register(plugin)


def test_unknown_plugin_rejected():
    registry = build_default_plugin_registry()

    with pytest.raises(KeyError, match="unknown plugin_id"):
        registry.get("missing")


def test_unsupported_stage_rejected():
    registry = build_default_plugin_registry()

    with pytest.raises(ValueError, match="does not support stage"):
        registry.validate_stage_support("battery_archive", "trust")


def test_plugin_metadata_rejects_duplicate_or_invalid_stage():
    with pytest.raises(ValueError, match="unsupported stages"):
        PluginMetadata(
            plugin_id="bad",
            case_study_id="bad",
            description="bad",
            supported_stages=("not_a_stage",),
        )

    with pytest.raises(ValueError, match="duplicate stages"):
        PluginMetadata(
            plugin_id="bad2",
            case_study_id="bad",
            description="bad",
            supported_stages=("trust", "trust"),
        )
