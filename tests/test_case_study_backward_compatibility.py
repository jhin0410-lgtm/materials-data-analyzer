import importlib
import json
from pathlib import Path

from src.platform_core.adapter_registry import build_default_adapter_registry
from src.platform_core.artifacts import build_default_artifact_registry
from src.platform_core.case_study_registry import build_default_case_study_registry
from src.platform_core.registry import build_default_plugin_registry
from src.platform_core.trust_registry import build_default_trust_policy_registry
from src.platform_core.validation_registry import build_default_validation_policy_registry


def test_stdlib_platform_and_pandas_imports_are_unaffected():
    stdlib_platform = importlib.import_module("platform")
    pandas = importlib.import_module("pandas")

    assert hasattr(stdlib_platform, "system")
    assert pandas.__name__ == "pandas"
    assert not Path("src/platform").exists()


def test_case_study_registry_snapshot_matches_default_registry_core_fields():
    plugin_registry = build_default_plugin_registry()
    artifact_registry = build_default_artifact_registry()
    validation_registry = build_default_validation_policy_registry()
    trust_registry = build_default_trust_policy_registry()
    adapter_registry = build_default_adapter_registry(plugin_registry, artifact_registry)
    registry = build_default_case_study_registry(
        plugin_registry,
        artifact_registry,
        validation_registry,
        trust_registry,
        adapter_registry,
    )
    snapshot = json.loads(Path("data/platform/case_study_registry_snapshot_v2.json").read_text(encoding="utf-8"))
    expected = {item["case_study_id"]: item for item in registry.completeness_snapshot()}
    observed = {item["case_study_id"]: item for item in snapshot["case_studies"]}

    assert sorted(observed) == sorted(expected)
    for case_study_id, observed_item in observed.items():
        expected_item = expected[case_study_id]
        assert observed_item["status"] == expected_item["status"]
        assert observed_item["mapped_stages"] == expected_item["mapped_stages"]
        assert observed_item["executable_stages"] == expected_item["executable_stages"]
        assert observed_item["artifact_count"] == expected_item["artifact_count"]
        assert observed_item["onboarding_status"] == expected_item["onboarding_status"]
