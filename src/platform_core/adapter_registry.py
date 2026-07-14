"""Explicit registry for safe case-study stage adapters."""

from __future__ import annotations

from dataclasses import dataclass, field

from .adapters import AdapterExecutionPolicy, AdapterMetadata
from .artifacts import ArtifactRegistry
from .registry import PluginRegistry


@dataclass
class AdapterRegistry:
    """Deterministic adapter registry with no dynamic imports."""

    _adapters: dict[str, AdapterMetadata] = field(default_factory=dict)

    def register(
        self,
        adapter: AdapterMetadata,
        plugin_registry: PluginRegistry,
        artifact_registry: ArtifactRegistry,
    ) -> None:
        if adapter.adapter_id in self._adapters:
            raise ValueError(f"duplicate adapter_id: {adapter.adapter_id}")
        plugin = plugin_registry.get(adapter.plugin_id)
        if adapter.case_study_id != plugin.case_study_id:
            raise ValueError(
                f"adapter {adapter.adapter_id} case_study_id does not match plugin {adapter.plugin_id}"
            )
        if not plugin.supports_stage(adapter.stage):
            raise ValueError(f"plugin {adapter.plugin_id} does not support adapter stage {adapter.stage}")
        for artifact_id in adapter.required_artifacts + adapter.optional_artifacts + adapter.produced_artifacts:
            artifact = artifact_registry.get(artifact_id)
            if artifact.case_study_id != adapter.case_study_id:
                raise ValueError(
                    f"artifact {artifact_id} does not belong to adapter case_study_id {adapter.case_study_id}"
                )
        self._adapters[adapter.adapter_id] = adapter

    def get(self, adapter_id: str) -> AdapterMetadata:
        try:
            return self._adapters[adapter_id]
        except KeyError as exc:
            raise KeyError(f"unknown adapter_id: {adapter_id}") from exc

    def list_adapters(self, plugin_id: str | None = None) -> list[AdapterMetadata]:
        adapters = self._adapters.values()
        if plugin_id is not None:
            adapters = [adapter for adapter in adapters if adapter.plugin_id == plugin_id]
        return sorted(adapters, key=lambda adapter: adapter.adapter_id)

    def find_for_plugin_stage(self, plugin_id: str, stage: str) -> list[AdapterMetadata]:
        return [
            adapter
            for adapter in self.list_adapters(plugin_id)
            if adapter.stage == stage and adapter.execution_policy.safe_for_dry_run
        ]

    def snapshot(self, plugin_id: str | None = None) -> list[dict[str, object]]:
        return [adapter.to_dict() for adapter in self.list_adapters(plugin_id)]


def build_default_adapter_registry(
    plugin_registry: PluginRegistry,
    artifact_registry: ArtifactRegistry,
) -> AdapterRegistry:
    """Register manifest-only adapters for selected trust closeout stages."""

    registry = AdapterRegistry()
    disabled_dry_run_policy = AdapterExecutionPolicy(
        network_required=False,
        raw_data_required=False,
        model_training_required=False,
        writes_outputs=True,
        safe_for_dry_run=True,
        safe_for_manifest_only=True,
        execution_allowed=False,
    )
    for adapter in [
        AdapterMetadata(
            adapter_id="materials_project_trust_closeout",
            plugin_id="materials_project",
            case_study_id="materials_project",
            stage="trust",
            module_path="scripts/run_materials_project_v1_3_trust_analysis.py",
            callable_name="main",
            execution_mode="dry_run_safe",
            required_artifacts=("materials_project_v1_3_validation_metrics",),
            optional_artifacts=(),
            produced_artifacts=(
                "materials_project_v1_3_trust_conclusion",
                "materials_project_v1_3_claim_boundary",
            ),
            execution_policy=disabled_dry_run_policy,
            executable_status="executable_disabled",
            blocked_reasons=("actual_execution_disabled",),
            description=(
                "Manifest-only mapping for Materials Project v1.3 trust closeout. "
                "The original script remains canonical and is not executed by the platform scaffold."
            ),
        ),
        AdapterMetadata(
            adapter_id="smart_factory_trust_closeout",
            plugin_id="smart_factory",
            case_study_id="smart_factory",
            stage="trust",
            module_path="scripts/run_smart_factory_v1_4_trust_analysis.py",
            callable_name="main",
            execution_mode="dry_run_safe",
            required_artifacts=("smart_factory_v1_4_classification_metrics",),
            optional_artifacts=(),
            produced_artifacts=(
                "smart_factory_v1_4_trust_summary",
                "smart_factory_v1_4_claim_boundary",
                "smart_factory_v1_4_closeout_conclusion",
            ),
            execution_policy=disabled_dry_run_policy,
            executable_status="executable_disabled",
            blocked_reasons=("actual_execution_disabled",),
            description=(
                "Manifest-only mapping for Smart Factory v1.4 trust closeout. "
                "Actual trust execution remains disabled in the unified CLI."
            ),
        ),
        AdapterMetadata(
            adapter_id="reliability_trust_closeout",
            plugin_id="reliability",
            case_study_id="reliability",
            stage="trust",
            module_path="scripts/run_reliability_v1_5_trust_analysis.py",
            callable_name="main",
            execution_mode="dry_run_safe",
            required_artifacts=("reliability_v1_5_classification_metrics",),
            optional_artifacts=(),
            produced_artifacts=(
                "reliability_v1_5_trust_summary",
                "reliability_v1_5_claim_boundary",
                "reliability_v1_5_closeout_conclusion",
            ),
            execution_policy=disabled_dry_run_policy,
            executable_status="executable_disabled",
            blocked_reasons=("actual_execution_disabled",),
            description=(
                "Manifest-only mapping for Reliability v1.5 trust closeout. "
                "No model, raw data, or trust script execution occurs."
            ),
        ),
    ]:
        registry.register(adapter, plugin_registry, artifact_registry)
    return registry
