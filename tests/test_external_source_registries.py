import json
from pathlib import Path

from src.platform_core.external_source_contracts import (
    build_external_dataset_registry,
    build_external_source_system_registry,
    external_source_registry_payloads,
    validate_external_source_registries,
)
from src.platform_core.pgir_governance import build_schema_ownership_registry


SCHEMAS = (
    "external_source_system_schema_v1.json",
    "external_dataset_schema_v1.json",
    "external_dataset_snapshot_schema_v1.json",
    "external_distribution_artifact_schema_v1.json",
    "external_retrieval_event_schema_v1.json",
    "external_source_provenance_assessment_schema_v1.json",
)


def test_external_source_registries_are_unique_and_deterministic():
    systems = build_external_source_system_registry()
    datasets = build_external_dataset_registry()

    assert [item.source_system_id for item in systems] == sorted(item.source_system_id for item in systems)
    assert len({item.source_system_id for item in systems}) == len(systems) == 5
    assert len({item.dataset_id for item in datasets}) == len(datasets) == 2
    assert validate_external_source_registries()["valid"] is True
    assert external_source_registry_payloads() == external_source_registry_payloads()


def test_actual_and_future_source_boundaries_are_explicit():
    systems = {item.source_system_id: item for item in build_external_source_system_registry()}

    assert systems["materials_project"].status == "actual_bounded_retrieval_evidence"
    assert systems["nasa_battery_kaggle_upstream"].source_kind == "immediate_upstream_archive"
    for source_id in ("nist_oar", "nrel_api", "nvd"):
        assert systems[source_id].status == "future_declared_no_retrieval_or_integration_evidence"


def test_tracked_registries_match_runtime_payloads():
    for registry_id, expected in external_source_registry_payloads().items():
        actual = json.loads(Path(f"data/platform/{registry_id}.json").read_text(encoding="utf-8"))
        assert actual == expected


def test_external_source_schemas_parse_and_are_owned_by_pgir_registry():
    ownership = {item.schema_id: item for item in build_schema_ownership_registry()}
    for name in SCHEMAS:
        payload = json.loads(Path("data/platform", name).read_text(encoding="utf-8"))
        schema_id = name.removesuffix(".json")
        assert payload["schema_id"] == schema_id
        assert payload["schema_version"] == "1"
        assert payload["compatibility_policy"]["unknown_fields"] == "reject"
        assert schema_id in ownership
        assert ownership[schema_id].owner_module == "src.platform_core.external_source_contracts"


def test_future_sources_have_no_dataset_snapshot_or_retrieval_records():
    payload = external_source_registry_payloads()["external_source_contract_registry_v1"]
    assert payload["future_source_policy"] == {
        "source_system_ids": ["nist_oar", "nrel_api", "nvd"],
        "retrieval_event_count": 0,
        "dataset_snapshot_count": 0,
        "successful_integration_evidence": False,
    }
