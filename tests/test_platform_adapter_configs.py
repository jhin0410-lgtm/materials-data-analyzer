from pathlib import Path

from src.platform_core.adapter_registry import build_default_adapter_registry
from src.platform_core.artifacts import build_default_artifact_registry
from src.platform_core.config import load_and_validate_pipeline_config
from src.platform_core.registry import build_default_plugin_registry
from src.platform_core.trust_registry import build_default_trust_policy_registry
from src.platform_core.validation_registry import build_default_validation_policy_registry


def test_manifest_example_configs_validate_with_adapter_registry():
    plugin_registry = build_default_plugin_registry()
    artifact_registry = build_default_artifact_registry()
    registries = (
        plugin_registry,
        artifact_registry,
        build_default_validation_policy_registry(),
        build_default_trust_policy_registry(),
        build_default_adapter_registry(plugin_registry, artifact_registry),
    )

    for path in sorted(Path("configs/examples").glob("*manifest_dry_run.json")):
        result = load_and_validate_pipeline_config(path, *registries)
        assert result.valid, (path, result.errors)


def test_manifest_example_configs_use_registry_adapter_ids_only():
    for path in sorted(Path("configs/examples").glob("*manifest_dry_run.json")):
        text = path.read_text(encoding="utf-8")
        assert "module_path" not in text
        assert "callable_name" not in text
        assert "adapter_id" in text
        assert "outputs/platform_runs" in text
