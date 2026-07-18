import json

import pytest

from src.platform_core.external_source_contracts import (
    ExternalDatasetSnapshotRecord,
    ExternalDistributionArtifactRecord,
    ExternalSourcePersistedRecord,
    ExternalSourceSystemRecord,
    build_external_source_contract_records,
    build_external_source_contract_summary,
    canonical_json_sha256,
    raw_bytes_sha256,
)


def test_external_source_concepts_remain_separate_records():
    records = build_external_source_contract_records()
    snapshot = records["snapshots"][0]
    distribution = records["distributions"][0]
    retrieval = records["retrieval_events"][0]

    assert snapshot.dataset_id
    assert distribution.snapshot_id == snapshot.snapshot_id or distribution.snapshot_id in {
        item.snapshot_id for item in records["snapshots"]
    }
    assert retrieval.retrieval_timestamp != snapshot.snapshot_date
    assert retrieval.distribution_id in {item.distribution_id for item in records["distributions"]}


def test_strict_record_rejects_unknown_fields_without_silent_drop():
    record = ExternalSourceSystemRecord.from_mapping(
        {
            "source_system_id": "fixture_source",
            "source_system_version": "1",
            "name": "Fixture",
            "publisher": "Fixture publisher",
            "source_kind": "official_repository",
            "domain_scope": ["fixture"],
            "official_landing_page": "https://example.invalid",
            "documentation_refs": [],
            "access_modes": ["metadata_only"],
            "authentication_requirement": "none",
            "authentication_environment_variable": None,
            "license_or_terms_refs": [],
            "update_policy": "fixed",
            "status": "fixture",
        }
    )
    payload = record.to_dict()
    payload["surprise"] = "must not disappear"

    with pytest.raises(ValueError, match="unknown fields"):
        ExternalSourceSystemRecord.from_mapping(payload)


def test_snapshot_identity_can_remain_explicitly_unresolved():
    record = ExternalDatasetSnapshotRecord(
        snapshot_id="fixture_snapshot",
        dataset_id="fixture_dataset",
        snapshot_version="unresolved",
        snapshot_date=None,
        version_semantics="retrieval does not identify a named release",
        authoritative_snapshot_status="snapshot_identity_unresolved",
        immediate_upstream_ref=None,
        schema_version_refs=(),
        declared_record_count=None,
        query_or_filter_scope="fixture",
        reproducibility_limitations=("named snapshot unavailable",),
        status="unresolved",
    )

    assert record.snapshot_date is None
    assert record.authoritative_snapshot_status == "snapshot_identity_unresolved"


def test_raw_byte_and_canonical_json_checksums_are_distinct_contracts():
    payload = {"b": 2, "a": 1}
    raw = b'{\n  "b": 2,\n  "a": 1\n}\n'

    assert raw_bytes_sha256(raw) != canonical_json_sha256(payload)
    assert canonical_json_sha256(payload) == canonical_json_sha256({"a": 1, "b": 2})


def test_persisted_record_rejects_future_version_and_checksum_mismatch():
    system = build_external_source_contract_records()
    snapshot = system["snapshots"][0]
    persisted = ExternalSourcePersistedRecord.from_record(snapshot)

    with pytest.raises(ValueError, match="future schema version"):
        ExternalSourcePersistedRecord(
            schema_id=persisted.schema_id,
            schema_version="2",
            record_type=persisted.record_type,
            record=persisted.record,
            canonical_json_sha256=persisted.canonical_json_sha256,
        )
    with pytest.raises(ValueError, match="checksum mismatch"):
        ExternalSourcePersistedRecord(
            schema_id=persisted.schema_id,
            schema_version="1",
            record_type=persisted.record_type,
            record=persisted.record,
            canonical_json_sha256="0" * 64,
        )


def test_distribution_rejects_absolute_and_traversal_paths():
    base = {
        "distribution_id": "fixture_distribution",
        "snapshot_id": "fixture_snapshot",
        "media_type": "application/json",
        "format": "json",
        "byte_size": 1,
        "raw_checksum_algorithm": "sha256",
        "raw_checksum_value": "a" * 64,
        "canonical_content_checksum_algorithm": None,
        "canonical_content_checksum_value": None,
        "access_url_ref": None,
        "compression_or_container": "none",
        "manifest_refs": (),
        "security_classification": "fixture",
        "status": "fixture",
    }
    for path in ("C:/Users/example/raw.json", "/tmp/raw.json", "../raw.json"):
        with pytest.raises(ValueError):
            ExternalDistributionArtifactRecord(local_artifact_ref=path, **base)


def test_external_source_summary_has_no_network_or_credentials():
    summary = build_external_source_contract_summary().to_dict()
    serialized = json.dumps(summary)

    assert summary["no_network_execution"] is True
    assert summary["credentials_persisted"] is False
    assert "snapshot_identity_unresolved" not in serialized or summary["unresolved_snapshot_ids"]
