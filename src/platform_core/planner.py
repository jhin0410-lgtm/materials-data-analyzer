"""Dry-run planning for v2 platform configs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
    resource_budget: dict[str, Any]
    network_requirement: str
    model_training_requirement: str
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
            "resource_budget": self.resource_budget,
            "network_requirement": self.network_requirement,
            "model_training_requirement": self.model_training_requirement,
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
    repo_root: str | Path = ".",
) -> tuple[ConfigValidationResult, DryRunPlan]:
    """Build a dry-run plan without creating outputs or importing plugins."""

    validation = validate_pipeline_config(
        config=config,
        plugin_registry=plugin_registry,
        artifact_registry=artifact_registry,
        validation_registry=validation_registry,
        trust_registry=trust_registry,
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
            resource_budget=config.get("resource_budget", {}) if isinstance(config.get("resource_budget", {}), dict) else {},
            network_requirement="not_evaluated",
            model_training_requirement="not_evaluated",
            blocked_reasons=("blocked_invalid_config",),
            execution_status="blocked_invalid_config",
            warnings=validation.warnings,
        )

    plugin = plugin_registry.get(str(config["plugin_id"]))
    repo = Path(repo_root)
    required_inputs = _unique_sorted(list(plugin.required_artifacts) + list(config.get("input_artifacts", [])))
    tracked_outputs = _unique_sorted(list(plugin.tracked_artifacts) + list(config.get("tracked_outputs", [])))
    local_outputs = _unique_sorted(list(plugin.local_only_artifacts) + list(config.get("local_only_outputs", [])))

    missing_inputs: list[str] = []
    for artifact_id in required_inputs:
        artifact = artifact_registry.get(artifact_id)
        if not (repo / artifact.relative_path).exists():
            missing_inputs.append(artifact_id)

    network_required = bool(config.get("parameters", {}).get("network_required", False)) if isinstance(config.get("parameters", {}), dict) else False
    model_training_required = bool(config.get("parameters", {}).get("model_training_required", False)) if isinstance(config.get("parameters", {}), dict) else False

    blocked: list[str] = []
    if plugin.status != "runnable":
        blocked.append("blocked_plugin_not_runnable")
    if missing_inputs:
        blocked.append("blocked_missing_artifact")
    if network_required:
        blocked.append("blocked_network_required")
    if model_training_required:
        blocked.append("blocked_model_training_required")

    status = "ready" if not blocked else blocked[0]
    return validation, DryRunPlan(
        selected_plugin=plugin.plugin_id,
        selected_stage=str(config["stage"]),
        required_inputs=required_inputs,
        missing_inputs=tuple(sorted(missing_inputs)),
        expected_tracked_outputs=tracked_outputs,
        expected_local_only_outputs=local_outputs,
        validator=config.get("validator"),
        trust_policy=config.get("trust_policy"),
        resource_budget=config.get("resource_budget", {}) if isinstance(config.get("resource_budget", {}), dict) else {},
        network_requirement="required" if network_required else "not_required",
        model_training_requirement="required" if model_training_required else "not_required",
        blocked_reasons=tuple(blocked),
        execution_status=status,
        warnings=validation.warnings,
    )
