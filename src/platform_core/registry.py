"""Explicit case-study plugin registry."""

from __future__ import annotations

from dataclasses import dataclass, field

from .plugins import PluginMetadata


@dataclass
class PluginRegistry:
    """Deterministic explicit registry for platform plugins."""

    _plugins: dict[str, PluginMetadata] = field(default_factory=dict)

    def register(self, plugin: PluginMetadata) -> None:
        if plugin.plugin_id in self._plugins:
            raise ValueError(f"duplicate plugin_id: {plugin.plugin_id}")
        self._plugins[plugin.plugin_id] = plugin

    def get(self, plugin_id: str) -> PluginMetadata:
        try:
            return self._plugins[plugin_id]
        except KeyError as exc:
            raise KeyError(f"unknown plugin_id: {plugin_id}") from exc

    def list_plugins(self) -> list[PluginMetadata]:
        return [self._plugins[key] for key in sorted(self._plugins)]

    def validate_stage_support(self, plugin_id: str, stage: str) -> None:
        plugin = self.get(plugin_id)
        if not plugin.supports_stage(stage):
            raise ValueError(f"plugin {plugin_id} does not support stage {stage}")

    def snapshot(self) -> list[dict[str, object]]:
        return [plugin.to_dict() for plugin in self.list_plugins()]


def build_default_plugin_registry() -> PluginRegistry:
    """Build the built-in metadata registry without importing case-study scripts."""

    registry = PluginRegistry()
    registry.register(
        PluginMetadata(
            plugin_id="battery_archive",
            case_study_id="battery_archive",
            description=(
                "Battery Archive cycle-data case study metadata. Existing scripts "
                "remain the source-specific orchestration layer."
            ),
            supported_stages=("acquisition", "normalization", "readiness", "closeout"),
            entrypoints={
                "acquisition": "scripts/build_battery_archive_cycle_inventory.py",
                "normalization": "scripts/build_battery_archive_cycle_normalized.py",
                "closeout": "scripts/build_battery_archive_case_study.py",
            },
            required_artifacts=("battery_archive_cycle_file_inventory",),
            produced_artifacts=("battery_archive_reliability_group_summary",),
            local_only_artifacts=("battery_archive_analysis_ready",),
            tracked_artifacts=("battery_archive_cycle_file_inventory",),
            validation_policy_id="group_aware_regression",
            trust_policy_id=None,
            status="scaffolded",
        )
    )
    registry.register(
        PluginMetadata(
            plugin_id="materials_project",
            case_study_id="materials_project",
            description=(
                "Materials Project descriptive screening and group-aware validation "
                "case-study metadata."
            ),
            supported_stages=("acquisition", "normalization", "validation", "trust", "closeout"),
            entrypoints={
                "acquisition": "scripts/acquire_materials_project_v1_3.py",
                "validation": "scripts/run_materials_project_v1_3_validation.py",
                "trust": "scripts/run_materials_project_v1_3_trust_analysis.py",
            },
            required_artifacts=("materials_project_v1_3_validation_metrics",),
            produced_artifacts=("materials_project_v1_3_trust_conclusion",),
            local_only_artifacts=("materials_project_v1_3_validation_predictions",),
            tracked_artifacts=("materials_project_v1_3_trust_conclusion",),
            validation_policy_id="group_aware_regression",
            trust_policy_id="materials_group_generalization",
            status="scaffolded",
        )
    )
    registry.register(
        PluginMetadata(
            plugin_id="smart_factory",
            case_study_id="smart_factory",
            description=(
                "Smart Factory / UCI SECOM process-quality case-study metadata "
                "with time-aware validation and trust closeout."
            ),
            supported_stages=("acquisition", "normalization", "readiness", "validation", "trust", "closeout"),
            entrypoints={
                "acquisition": "scripts/build_smart_factory_v1_4_acquisition.py",
                "validation": "scripts/run_smart_factory_v1_4_classification.py",
                "trust": "scripts/run_smart_factory_v1_4_trust_analysis.py",
            },
            required_artifacts=("smart_factory_v1_4_classification_metrics",),
            produced_artifacts=("smart_factory_v1_4_trust_summary",),
            local_only_artifacts=("smart_factory_v1_4_classification_predictions",),
            tracked_artifacts=("smart_factory_v1_4_trust_summary",),
            validation_policy_id="time_aware_classification",
            trust_policy_id="smart_factory_time_aware",
            status="scaffolded",
        )
    )
    registry.register(
        PluginMetadata(
            plugin_id="reliability",
            case_study_id="reliability",
            description=(
                "Backblaze reliability/risk case-study metadata with asset/time-aware "
                "validation and trust-boundary closeout."
            ),
            supported_stages=("acquisition", "normalization", "readiness", "feature_build", "validation", "trust", "closeout"),
            entrypoints={
                "acquisition": "scripts/build_reliability_v1_5_acquisition.py",
                "normalization": "scripts/build_reliability_v1_5_full_year.py",
                "validation": "scripts/run_reliability_v1_5_classification.py",
                "trust": "scripts/run_reliability_v1_5_trust_analysis.py",
            },
            required_artifacts=("reliability_v1_5_classification_metrics",),
            produced_artifacts=("reliability_v1_5_trust_summary",),
            local_only_artifacts=(
                "reliability_v1_5_backblaze_analysis_ready",
                "reliability_v1_5_horizon_7d_lookback_7d_dataset",
                "reliability_v1_5_classification_predictions",
            ),
            tracked_artifacts=("reliability_v1_5_trust_summary",),
            validation_policy_id="asset_time_combined_classification",
            trust_policy_id="reliability_asset_time_aware",
            status="scaffolded",
        )
    )
    return registry
