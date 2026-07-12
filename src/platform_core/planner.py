"""Dry-run planning for v2 platform configs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .adapter_registry import AdapterRegistry
from .artifacts import ArtifactRegistry
from .config import ConfigValidationResult, validate_pipeline_config
from .registry import PluginRegistry
from .trust_registry import TrustPolicyRegistry
from .validation_registry import ValidationPolicyRegistry


@dataclass(frozen=True)
class DryRunPlan:
    selected_plugin: str | None
    selected_stage: str | None
    required_inputs: tuple[str, ...]
    missing_inputs: tuple[str, ...]
    expected_tracked_outputs: tuple[str, ...]
    expected_local_only_outputs: tuple[str, ...]
    validator: str | None
    trust_policy: str | None
    adapter_id: str | None
    adapter_status: str | None
    execution_boundary: str
    resource_budget: dict[str, Any]
    network_requirement: str
    raw_data_requirement: str
    model_training_requirement: str
    writes_outputs: bool
    execution_allowed: bool
    existing_artifacts: tuple[str, ...]
    expected_outputs: tuple[str, ...]
    manifest_path: str | None
    blocked_reasons: tuple[str, ...]
    execution_status: str
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "selected_plugin": self.selected_plugin,
            "selected_stage": self.selected_stage,
            "required_inputs": list(self.required_inputs),
            "missing_inputs": list(self.missing_inputs),
            "expected_tracked_outputs": list(self.expected_tracked_outputs),
            "expected_local_only_outputs": list(self.expected_local_only_outputs),
            "validator": self.validator,
            "trust_policy": self.trust_policy,
            "adapter_id": self.adapter_id,
            "adapter_status": self.adapter_status,
            "execution_boundary": self.execution_boundary,
            "resource_budget": self.resource_budget,
            "network_requirement": self.network_requirement,
            "raw_data_requirement": self.raw_data_requirement,
            "model_training_requirement": self.model_training_requirement,
            "writes_outputs": self.writes_outputs,
            "execution_allowed": self.execution_allowed,
            "existing_artifacts": list(self.existing_artifacts),
            "expected_outputs": list(self.expected_outputs),
            "manifest_path": self.manifest_path,
            "blocked_reasons": list(self.blocked_reasons),
            "execution_status": self.execution_status,
            "warnings": list(self.warnings),
        }


def _unique_sorted(values: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted(dict.fromkeys(values)))


def build_dry_run_plan(
    config: dict[str, Any],
    plugin_registry: PluginRegistry,
    artifact_registry: ArtifactRegistry,
    validation_registry: ValidationPolicyRegistry,
    trust_registry: TrustPolicyRegistry,
    adapter_registry: AdapterRegistry | None = None,
    repo_root: str | Path = ".",
) -> tuple[ConfigValidationResult, DryRunPlan]:
    """Build a dry-run plan without creating outputs or importing plugins."""

    validation = validate_pipeline_config(
        config=config,
        plugin_registry=plugin_registry,
        artifact_registry=artifact_registry,
        validation_registry=validation_registry,
        trust_registry=trust_registry,
        adapter_registry=adapter_registry,
    )
    if not validation.valid:
        return validation, DryRunPlan(
            selected_plugin=config.get("plugin_id"),
            selected_stage=config.get("stage"),
            required_inputs=(),
            missing_inputs=(),
            expected_tracked_outputs=(),
            expected_local_only_outputs=(),
            validator=config.get("validator"),
            trust_policy=config.get("trust_policy"),
            adapter_id=config.get("adapter_id"),
            adapter_status=None,
            execution_boundary="not_evaluated",
            resource_budget=config.get("resource_budget", {}) if isinstance(config.get("resource_budget", {}), dict) else {},
            network_requirement="not_evaluated",
            raw_data_requirement="not_evaluated",
            model_training_requirement="not_evaluated",
            writes_outputs=False,
            execution_allowed=False,
            existing_artifacts=(),
            expected_outputs=(),
            manifest_path=config.get("manifest_output") if isinstance(config.get("manifest_output"), str) else None,
            blocked_reasons=("blocked_invalid_config",),
            execution_status="blocked_invalid_config",
            warnings=validation.warnings,
        )

    plugin = plugin_registry.get(str(config["plugin_id"]))
    repo = Path(repo_root)
    adapter = None
    adapter_blocked: list[str] = []
    if adapter_registry is None:
        adapter_blocked.append("blocked_adapter_registry_missing")
    elif config.get("adapter_id"):
        try:
            adapter = adapter_registry.get(str(config["adapter_id"]))
        except KeyError:
            adapter_blocked.append("blocked_adapter_not_registered")
    else:
        adapters = adapter_registry.find_for_plugin_stage(plugin.plugin_id, str(config["stage"]))
        if len(adapters) == 1:
            adapter = adapters[0]
        elif len(adapters) > 1:
            adapter_blocked.append("blocked_adapter_ambiguous")
        else:
            adapter_blocked.append("blocked_adapter_not_registered")

    adapter_required = list(adapter.required_artifacts) if adapter is not None else []
    adapter_produced = list(adapter.produced_artifacts) if adapter is not None else []
    required_inputs = _unique_sorted(list(plugin.required_artifacts) + adapter_required + list(config.get("input_artifacts", [])))
    tracked_outputs = _unique_sorted(list(plugin.tracked_artifacts) + adapter_produced + list(config.get("tracked_outputs", [])))
    local_outputs = _unique_sorted(list(plugin.local_only_artifacts) + list(config.get("local_only_outputs", [])))
    expected_outputs = _unique_sorted(list(tracked_outputs) + list(local_outputs))

    missing_inputs: list[str] = []
    existing_inputs: list[str] = []
    for artifact_id in required_inputs:
        artifact = artifact_registry.get(artifact_id)
        if (repo / artifact.relative_path).exists():
            existing_inputs.append(artifact_id)
        else:
            missing_inputs.append(artifact_id)

    parameters = config.get("parameters", {}) if isinstance(config.get("parameters", {}), dict) else {}
    adapter_policy = adapter.execution_policy if adapter is not None else None
    network_required = bool(parameters.get("network_required", False)) or bool(
        adapter_policy.network_required if adapter_policy is not None else False
    )
    raw_data_required = bool(parameters.get("raw_data_required", False)) or bool(
        adapter_policy.raw_data_required if adapter_policy is not None else False
    )
    model_training_required = bool(parameters.get("model_training_required", False)) or bool(
        adapter_policy.model_training_required if adapter_policy is not None else False
    )

    blocked: list[str] = []
    blocked.extend(adapter_blocked)
    if missing_inputs:
        blocked.append("blocked_missing_artifact")
    if network_required:
        blocked.append("blocked_network_required")
    if raw_data_required:
        blocked.append("blocked_raw_data_required")
    if model_training_required:
        blocked.append("blocked_model_training_required")

    execution_allowed = False
    writes_outputs = bool(adapter_policy.writes_outputs if adapter_policy is not None else False)
    if not blocked and adapter is not None:
        status = "ready_for_dry_run_manifest"
    else:
        status = blocked[0] if blocked else "blocked_adapter_not_registered"
    return validation, DryRunPlan(
        selected_plugin=plugin.plugin_id,
        selected_stage=str(config["stage"]),
        required_inputs=required_inputs,
        missing_inputs=tuple(sorted(missing_inputs)),
        expected_tracked_outputs=tracked_outputs,
        expected_local_only_outputs=local_outputs,
        validator=config.get("validator"),
        trust_policy=config.get("trust_policy"),
        adapter_id=adapter.adapter_id if adapter is not None else config.get("adapter_id"),
        adapter_status=adapter.executable_status if adapter is not None else None,
        execution_boundary="manifest_only_actual_execution_disabled" if adapter is not None else "not_available",
        resource_budget=config.get("resource_budget", {}) if isinstance(config.get("resource_budget", {}), dict) else {},
        network_requirement="required" if network_required else "not_required",
        raw_data_requirement="required" if raw_data_required else "not_required",
        model_training_requirement="required" if model_training_required else "not_required",
        writes_outputs=writes_outputs,
        execution_allowed=execution_allowed,
        existing_artifacts=tuple(sorted(existing_inputs)),
        expected_outputs=expected_outputs,
        manifest_path=config.get("manifest_output") if isinstance(config.get("manifest_output"), str) else None,
        blocked_reasons=tuple(blocked),
        execution_status=status,
        warnings=validation.warnings,
    )
