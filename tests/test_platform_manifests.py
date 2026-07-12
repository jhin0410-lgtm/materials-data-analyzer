import json

import pytest

from src.platform_core.adapter_registry import build_default_adapter_registry
from src.platform_core.artifacts import build_default_artifact_registry
from src.platform_core.config import validate_pipeline_config
from src.platform_core.manifests import (
    build_run_manifest,
    calculate_config_sha256,
    load_run_manifest,
    validate_run_manifest,
    write_run_manifest,
)
from src.platform_core.planner import build_dry_run_plan
from src.platform_core.registry import build_default_plugin_registry
from src.platform_core.trust_registry import build_default_trust_policy_registry
from src.platform_core.validation_registry import build_default_validation_policy_registry


def _registries():
    plugin_registry = build_default_plugin_registry()
    artifact_registry = build_default_artifact_registry()
    validation_registry = build_default_validation_policy_registry()
    trust_registry = build_default_trust_policy_registry()
    adapter_registry = build_default_adapter_registry(plugin_registry, artifact_registry)
    return plugin_registry, artifact_registry, validation_registry, trust_registry, adapter_registry


def _config():
    return {
        "schema_version": "2.0",
        "pipeline_id": "reliability_test",
        "case_study_id": "reliability",
        "plugin_id": "reliability",
        "adapter_id": "reliability_trust_closeout",
        "stage": "trust",
        "input_artifacts": ["reliability_v1_5_classification_metrics"],
        "tracked_outputs": ["reliability_v1_5_trust_summary"],
        "validator": "asset_time_combined_classification",
        "trust_policy": "reliability_asset_time_aware",
        "credential_policy": {"store_credentials": False},
        "dry_run": True,
    }


def _write_required_artifact(tmp_path):
    path = tmp_path / "data" / "processed" / "reliability_v1_5_classification_metrics.csv"
    path.parent.mkdir(parents=True)
    path.write_text("metric,value\naverage_precision,0.1\n", encoding="utf-8")


def test_config_hash_is_deterministic():
    config = _config()
    reordered = json.loads(json.dumps(config, sort_keys=True))

    assert calculate_config_sha256(config) == calculate_config_sha256(reordered)


def test_manifest_build_and_validate_without_absolute_paths(tmp_path):
    _write_required_artifact(tmp_path)
    registries = _registries()
    validation, plan = build_dry_run_plan(_config(), *registries, repo_root=tmp_path)

    manifest = build_run_manifest(
        _config(),
        validation,
        plan,
        registries[1],
        registries[3],
        repo_root=tmp_path,
        timestamp="2026-07-13T00:00:00Z",
        code_commit="abc123",
    )

    assert manifest["status"] == "dry_run_completed"
    assert manifest["adapter_id"] == "reliability_trust_closeout"
    assert manifest["execution_boundary"]["execution_allowed"] is False
    validate_run_manifest(manifest)
    assert "C:/" not in json.dumps(manifest)
    assert "password" not in json.dumps(manifest).lower()


def test_manifest_write_is_atomic_and_overwrite_guarded(tmp_path):
    _write_required_artifact(tmp_path)
    registries = _registries()
    validation, plan = build_dry_run_plan(_config(), *registries, repo_root=tmp_path)
    manifest = build_run_manifest(
        _config(),
        validation,
        plan,
        registries[1],
        registries[3],
        repo_root=tmp_path,
        timestamp="2026-07-13T00:00:00Z",
        code_commit="abc123",
    )

    target = write_run_manifest(manifest, tmp_path, "outputs/platform_runs/demo/run_manifest.json")

    assert target.exists()
    assert load_run_manifest(target)["run_id"] == manifest["run_id"]
    with pytest.raises(FileExistsError):
        write_run_manifest(manifest, tmp_path, "outputs/platform_runs/demo/run_manifest.json")


def test_manifest_rejects_absolute_and_traversal_output(tmp_path):
    registries = _registries()
    validation = validate_pipeline_config(_config(), *registries)
    _, plan = build_dry_run_plan(_config(), *registries, repo_root=tmp_path)
    manifest = build_run_manifest(
        _config(),
        validation,
        plan,
        registries[1],
        registries[3],
        repo_root=tmp_path,
        timestamp="2026-07-13T00:00:00Z",
        code_commit="abc123",
    )

    with pytest.raises(ValueError, match="absolute paths"):
        write_run_manifest(manifest, tmp_path, "C:/tmp/run_manifest.json")
    with pytest.raises(ValueError, match="path traversal"):
        write_run_manifest(manifest, tmp_path, "../run_manifest.json")


def test_manifest_rejects_credential_like_content():
    manifest = {
        "run_id": "demo",
        "pipeline_id": "demo",
        "plugin_id": "demo",
        "adapter_id": "demo",
        "stage": "trust",
        "config_sha256": "abc",
        "code_commit": "abc",
        "status": "dry_run_completed",
        "dry_run": True,
        "warnings": [],
        "errors": ["token=bad"],
        "claim_boundary": {},
    }

    with pytest.raises(ValueError, match="credential-like"):
        validate_run_manifest(manifest)
