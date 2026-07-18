import json
from pathlib import Path

from src.platform_core.pgir_governance import (
    build_representation_governance,
    build_schema_ownership_registry,
    evaluate_pgir_readiness,
    validate_schema_governance,
)


def test_schema_ownership_registry_has_unique_schema_ids_and_separate_versions():
    records = build_schema_ownership_registry()
    validation = validate_schema_governance(records)

    assert validation["valid"] is True
    assert len({record.schema_id for record in records}) == len(records)
    assert all(not record.current_version.startswith("v") for record in records)
    assert all(record.owner_module.startswith("src.platform_core") for record in records)


def test_representation_governance_keeps_runtime_and_persistence_separate():
    governance = build_representation_governance()

    assert governance["status"] == "accepted_for_v2_3"
    assert governance["compatibility_policy"]["mass_rename_prohibited"] is True
    assert governance["compatibility_policy"]["persisted_schema_ids_remain_stable"] is True
    assert governance["security_policy"]["live_python_object_persistence"] is False
    assert governance["security_policy"]["binary_python_object_serialization"] is False
    assert "silent field dropping prohibited" in governance["rules"]


def test_pgir_readiness_is_governance_ready_without_model_or_solver_execution():
    decision = evaluate_pgir_readiness().to_dict()

    assert decision["status"] == "pgir_governance_ready"
    assert decision["valid"] is True
    assert decision["readiness_summary"]["scientific_recomputation_performed"] is False
    assert decision["readiness_summary"]["api_or_network_called"] is False
    assert decision["readiness_summary"]["model_or_solver_executed"] is False
    assert decision["gates"]["domain_semantics_preserved"] is True
    assert decision["gates"]["future_only_capabilities_marked"] is True


def test_schema_and_governance_compact_artifacts_parse():
    for path in [
        Path("data/platform/pgir_schema_ownership_registry_v1.json"),
        Path("data/platform/pgir_representation_governance_v1.json"),
    ]:
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["schema_version"] == "2.3.1"
        assert payload["status"] == "accepted_for_v2_3"
