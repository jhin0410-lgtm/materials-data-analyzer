import sqlite3

from src.platform_core.run_registry import get_schema_version
from src.platform_core.scientific_execution import (
    ScientificExecutionRequest,
    execute_scientific_request,
    get_scientific_claim_evaluation,
    get_scientific_execution,
    list_scientific_findings,
    persist_scientific_execution,
    validate_scientific_registry,
)


def _request():
    return ScientificExecutionRequest.from_config(
        {
            "execution_id": "persist_bragg",
            "knowledge_pack_id": "xrd_crystallography_basic_v1",
            "constraint_ids": ["xrd.bragg.geometry"],
            "inputs": [
                {"variable_id": "two_theta", "value": 44.7, "unit": "degree"},
                {"variable_id": "wavelength", "value": 1.5406, "unit": "angstrom"},
            ],
            "requested_claim_ids": ["dimensionally_consistent"],
            "persist_findings": True,
        }
    )


def test_scientific_execution_persistence_is_idempotent(tmp_path):
    request = _request()
    result = execute_scientific_request(request)
    registry_path = "outputs/platform_registry/science.sqlite3"

    stored = persist_scientific_execution(request, result, repo_root=tmp_path, registry_path=registry_path)
    again = persist_scientific_execution(request, result, repo_root=tmp_path, registry_path=registry_path)

    assert stored["status"] == "stored"
    assert again["status"] == "idempotent"
    payload = get_scientific_execution("persist_bragg", repo_root=tmp_path, registry_path=registry_path)
    assert payload["execution"]["status"] == result.overall_status
    assert list_scientific_findings(execution_id="persist_bragg", repo_root=tmp_path, registry_path=registry_path)
    assert get_scientific_claim_evaluation("persist_bragg", "dimensionally_consistent", repo_root=tmp_path, registry_path=registry_path)["status"] == "supported"
    assert validate_scientific_registry(repo_root=tmp_path, registry_path=registry_path)["valid"] is True


def test_registry_schema_migrates_v2_to_v4_with_scientific_tables(tmp_path):
    db_path = tmp_path / "outputs" / "platform_registry" / "legacy_v2.sqlite3"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "CREATE TABLE registry_metadata (metadata_id INTEGER PRIMARY KEY CHECK (metadata_id = 1), schema_version INTEGER NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO registry_metadata(metadata_id, schema_version, created_at, updated_at) VALUES (1, 2, '2026-07-14T00:00:00Z', '2026-07-14T00:00:00Z')"
        )

    assert get_schema_version(tmp_path, "outputs/platform_registry/legacy_v2.sqlite3") == 4
    with sqlite3.connect(db_path) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {
        "scientific_executions",
        "scientific_findings",
        "scientific_claim_evaluations",
        "scientific_unit_conversions",
        "scientific_trust_evaluations",
        "scientific_constraint_eligibility",
        "scientific_feature_eligibility",
        "scientific_claim_boundaries",
    } <= tables


def test_registry_schema_migrates_v3_to_v4_with_trust_tables(tmp_path):
    db_path = tmp_path / "outputs" / "platform_registry" / "legacy_v3.sqlite3"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "CREATE TABLE registry_metadata (metadata_id INTEGER PRIMARY KEY CHECK (metadata_id = 1), schema_version INTEGER NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO registry_metadata(metadata_id, schema_version, created_at, updated_at) VALUES (1, 3, '2026-07-14T00:00:00Z', '2026-07-14T00:00:00Z')"
        )

    assert get_schema_version(tmp_path, "outputs/platform_registry/legacy_v3.sqlite3") == 4
    with sqlite3.connect(db_path) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {
        "scientific_trust_evaluations",
        "scientific_constraint_eligibility",
        "scientific_feature_eligibility",
        "scientific_claim_boundaries",
    } <= tables
