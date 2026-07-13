"""Configuration loading and validation for the v2 scaffold."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .adapter_registry import AdapterRegistry
from .artifacts import ArtifactRegistry, validate_relative_path
from .plugins import ALLOWED_STAGES
from .registry import PluginRegistry
from .trust_registry import TrustPolicyRegistry
from .validation_registry import ValidationPolicyRegistry


SUPPORTED_CONFIG_SCHEMA_VERSION = "2.0"

REQUIRED_CONFIG_FIELDS = (
    "schema_version",
    "pipeline_id",
    "case_study_id",
    "plugin_id",
    "stage",
)

ALLOWED_CONFIG_FIELDS = {
    "schema_version",
    "pipeline_id",
    "case_study_id",
    "plugin_id",
    "stage",
    "input_artifacts",
    "output_artifacts",
    "local_only_outputs",
    "tracked_outputs",
    "connector",
    "loader",
    "readiness_analyzer",
    "feature_builder",
    "validator",
    "trust_policy",
    "parameters",
    "random_state",
    "resource_budget",
    "provenance_policy",
    "credential_policy",
    "dry_run",
    "adapter_id",
    "write_manifest",
    "manifest_output",
    "run_id",
    "overwrite_manifest",
    "execution_mode",
    "require_clean_tree",
    "verify_canonical_outputs",
    "output_directory",
    "resource_budget_override",
    "stop_conditions",
}

LIST_FIELDS = {
    "input_artifacts",
    "output_artifacts",
    "local_only_outputs",
    "tracked_outputs",
    "stop_conditions",
}


@dataclass(frozen=True)
class ConfigValidationResult:
    valid: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    config: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "valid": self.valid,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "config": self.config,
        }


def load_json_config(config_path: str | Path) -> dict[str, Any]:
    path = Path(config_path)
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("pipeline config must be a JSON object")
    return data


def validate_pipeline_config(
    config: dict[str, Any],
    plugin_registry: PluginRegistry,
    artifact_registry: ArtifactRegistry,
    validation_registry: ValidationPolicyRegistry,
    trust_registry: TrustPolicyRegistry,
    adapter_registry: AdapterRegistry | None = None,
) -> ConfigValidationResult:
    errors: list[str] = []
    warnings: list[str] = []

    unknown_fields = sorted(set(config) - ALLOWED_CONFIG_FIELDS)
    if unknown_fields:
        errors.append(f"unknown fields: {', '.join(unknown_fields)}")

    for field in REQUIRED_CONFIG_FIELDS:
        if field not in config:
            errors.append(f"missing required field: {field}")

    if config.get("schema_version") != SUPPORTED_CONFIG_SCHEMA_VERSION:
        errors.append(
            f"unsupported schema_version: {config.get('schema_version')!r}; expected {SUPPORTED_CONFIG_SCHEMA_VERSION}"
        )

    stage = config.get("stage")
    if stage is not None and stage not in ALLOWED_STAGES:
        errors.append(f"unsupported stage: {stage}")

    plugin = None
    plugin_id = config.get("plugin_id")
    if plugin_id is not None:
        try:
            plugin = plugin_registry.get(str(plugin_id))
        except KeyError:
            errors.append(f"unknown plugin_id: {plugin_id}")

    if plugin is not None:
        if config.get("case_study_id") != plugin.case_study_id:
            errors.append(
                f"case_study_id {config.get('case_study_id')!r} does not match plugin {plugin.plugin_id}"
            )
        if stage is not None and not plugin.supports_stage(str(stage)):
            errors.append(f"plugin {plugin.plugin_id} does not support stage {stage}")

    adapter_id = config.get("adapter_id")
    if adapter_id:
        if adapter_registry is None:
            warnings.append("adapter_id provided but adapter registry was not supplied")
        else:
            try:
                adapter = adapter_registry.get(str(adapter_id))
            except KeyError:
                errors.append(f"unknown adapter_id: {adapter_id}")
            else:
                if plugin is not None and adapter.plugin_id != plugin.plugin_id:
                    errors.append(f"adapter {adapter.adapter_id} does not belong to plugin {plugin.plugin_id}")
                if stage is not None and adapter.stage != stage:
                    errors.append(f"adapter {adapter.adapter_id} does not support stage {stage}")

    for field in LIST_FIELDS:
        value = config.get(field, [])
        if not isinstance(value, list):
            errors.append(f"{field} must be a list")
            continue
        for item in value:
            if not isinstance(item, str):
                errors.append(f"{field} entries must be strings")

    artifact_fields = ("input_artifacts", "output_artifacts", "local_only_outputs", "tracked_outputs")
    for field in artifact_fields:
        for artifact_id in config.get(field, []) if isinstance(config.get(field, []), list) else []:
            if not isinstance(artifact_id, str):
                continue
            try:
                artifact = artifact_registry.get(artifact_id)
            except KeyError:
                errors.append(f"unknown artifact_id in {field}: {artifact_id}")
                continue
            if plugin is not None and artifact.case_study_id != plugin.case_study_id:
                errors.append(f"artifact {artifact_id} does not belong to case_study_id {plugin.case_study_id}")

    validator = config.get("validator")
    if validator:
        try:
            validation_registry.get(str(validator))
        except KeyError:
            errors.append(f"unknown validation policy: {validator}")

    trust_policy = config.get("trust_policy")
    if trust_policy:
        try:
            trust_registry.get(str(trust_policy))
        except KeyError:
            errors.append(f"unknown trust policy: {trust_policy}")

    resource_budget = config.get("resource_budget", {})
    if resource_budget and not isinstance(resource_budget, dict):
        errors.append("resource_budget must be an object")
    elif isinstance(resource_budget, dict):
        for key, value in sorted(resource_budget.items()):
            if isinstance(value, (int, float)) and value < 0:
                errors.append(f"resource_budget.{key} must be non-negative")

    credential_policy = config.get("credential_policy", {})
    if credential_policy and not isinstance(credential_policy, dict):
        errors.append("credential_policy must be an object")
    elif isinstance(credential_policy, dict):
        if credential_policy.get("store_credentials") is True:
            errors.append("credential_policy.store_credentials must not be true")

    for field in ("write_manifest", "overwrite_manifest", "require_clean_tree", "verify_canonical_outputs"):
        if field in config and not isinstance(config[field], bool):
            errors.append(f"{field} must be a boolean")

    for field in ("manifest_output", "run_id", "adapter_id", "execution_mode", "output_directory"):
        if field in config and config[field] is not None and not isinstance(config[field], str):
            errors.append(f"{field} must be a string")

    if config.get("execution_mode") and config["execution_mode"] not in {"verify", "isolated_run"}:
        errors.append(f"unsupported execution_mode: {config['execution_mode']}")

    manifest_output = config.get("manifest_output")
    if manifest_output:
        try:
            validate_relative_path(str(manifest_output))
        except ValueError as exc:
            errors.append(f"manifest_output invalid: {exc}")

    output_directory = config.get("output_directory")
    if output_directory:
        try:
            validate_relative_path(str(output_directory))
        except ValueError as exc:
            errors.append(f"output_directory invalid: {exc}")

    if config.get("resource_budget_override") and not isinstance(config["resource_budget_override"], dict):
        errors.append("resource_budget_override must be an object")
    elif isinstance(config.get("resource_budget_override"), dict):
        base_budget = config.get("resource_budget", {})
        if not isinstance(base_budget, dict):
            errors.append("resource_budget must be an object when resource_budget_override is used")
        else:
            for key, value in sorted(config["resource_budget_override"].items()):
                if not isinstance(value, (int, float)) or value < 0:
                    errors.append(f"resource_budget_override.{key} must be a non-negative number")
                    continue
                base_value = base_budget.get(key)
                if isinstance(base_value, (int, float)) and value > base_value:
                    errors.append(f"resource_budget_override.{key} cannot be less strict than resource_budget.{key}")

    forbidden_permission_fields = {
        "execution_allowed",
        "network_allowed",
        "raw_data_allowed",
        "model_training_allowed",
        "process_spawn_allowed",
        "canonical_overwrite_allowed",
    }
    for field in sorted(forbidden_permission_fields & set(config)):
        errors.append(f"{field} cannot be set by config")

    for field in ("connector", "loader", "readiness_analyzer", "feature_builder"):
        value = config.get(field)
        if isinstance(value, dict):
            path = value.get("relative_path")
            if path:
                try:
                    validate_relative_path(str(path))
                except ValueError as exc:
                    errors.append(f"{field}.relative_path invalid: {exc}")

    if config.get("dry_run") is not True and not config.get("execution_mode"):
        warnings.append("dry_run=false is only supported with an explicit execution_mode")

    return ConfigValidationResult(valid=not errors, errors=tuple(errors), warnings=tuple(warnings), config=config)


def load_and_validate_pipeline_config(
    config_path: str | Path,
    plugin_registry: PluginRegistry,
    artifact_registry: ArtifactRegistry,
    validation_registry: ValidationPolicyRegistry,
    trust_registry: TrustPolicyRegistry,
    adapter_registry: AdapterRegistry | None = None,
) -> ConfigValidationResult:
    config = load_json_config(config_path)
    return validate_pipeline_config(
        config,
        plugin_registry,
        artifact_registry,
        validation_registry,
        trust_registry,
        adapter_registry,
    )
