import json
from pathlib import Path

from src.platform_core.run_registry import COMPARISON_STATUSES, REGISTRY_SCHEMA_VERSION, REPRODUCIBILITY_STATUSES


def test_platform_registry_schema_contract_matches_code():
    schema = json.loads(Path("data/platform/platform_registry_schema_v2.json").read_text(encoding="utf-8"))

    assert schema["storage_backend"] == "sqlite3"
    assert schema["local_only"] is True
    assert schema["database_schema_version"] == REGISTRY_SCHEMA_VERSION
    assert set(schema["reproducibility_statuses"]) == set(REPRODUCIBILITY_STATUSES)
    assert set(schema["run_comparison_statuses"]) == set(COMPARISON_STATUSES)
    assert "runs" in schema["tables"]
    assert "artifacts" in schema["tables"]
    assert "lineage" in schema["tables"]
    assert "warnings" in schema["tables"]


def test_platform_registry_schema_contains_security_policy():
    schema_text = Path("data/platform/platform_registry_schema_v2.json").read_text(encoding="utf-8").lower()

    assert "outputs/platform_registry" in schema_text
    assert "parameterized" in schema_text
    assert "network" in schema_text
    assert "model training" in schema_text
    assert "credentials" in schema_text
