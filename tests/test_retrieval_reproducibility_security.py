import json
from pathlib import Path

import pytest

from src.platform_core.external_source_contracts import canonical_json_sha256
from src.platform_core.retrieval_reproducibility import (
    ASSESSMENT_STATUSES,
    RetrievalComparisonResult,
    RetrievalEvidenceRecord,
    build_retrieval_evidence_record,
    compare_retrieval_evidence,
    validate_retrieval_reproducibility_config,
    validate_retrieval_reproducibility_summary,
)


CONFIG = Path("configs/examples/retrieval_reproducibility_audit.json")
SUMMARY = Path("data/processed/retrieval_reproducibility_audit_summary_v1.json")


def _config():
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def _metadata():
    return {
        "retrieval_timestamp": "2026-01-01T00:00:00Z",
        "client_name": "fixture-client",
        "client_version": "1",
        "endpoint_or_method": "fixture-endpoint",
        "query_or_parameters": {"ids": ["a"]},
        "requested_entity_identifiers": ["a"],
        "response_count": 1,
        "input_schema_version": "1",
        "transformation_boundary": "none",
    }


def _field_sources():
    fields = {
        "artifact_ref",
        "artifact_version",
        "retrieval_event_ref",
        "source_system_ref",
        "dataset_ref",
        "distribution_ref",
        "snapshot_ref",
        *_metadata(),
    }
    return {field: f"fixture.{field}" for field in fields}


def _record(evidence_id, artifact_ref, event_ref, *, case_study_id="fixture"):
    payload = {"value": 1}
    return build_retrieval_evidence_record(
        evidence_id=evidence_id,
        case_study_id=case_study_id,
        artifact_role="retrieved_json",
        artifact_kind="fixture_json",
        artifact_version="1",
        artifact_ref=artifact_ref,
        artifact_bytes=json.dumps(payload).encode("utf-8"),
        logical_payload=payload,
        source_system_ref="fixture_source",
        dataset_ref="fixture_dataset",
        distribution_ref="fixture_distribution",
        snapshot_ref="fixture_snapshot",
        retrieval_event_ref=event_ref,
        source_distribution_raw_sha256=None,
        retrieval_metadata=_metadata(),
        known_missing_metadata=(),
        evidence_field_sources=_field_sources(),
        independent_retrieval_event=True,
        limitations=(),
    )


def test_config_rejects_unknown_fields_dynamic_execution_and_secrets():
    for field, value in (
        ("surprise", True),
        ("module_path", "user.module"),
        ("callable_name", "execute"),
        ("dynamic_import", "user.module"),
        ("python_expression", "__import__('os')"),
        ("eval", "payload"),
        ("exec", "payload"),
    ):
        payload = _config()
        payload[field] = value
        with pytest.raises(ValueError, match="unknown fields"):
            validate_retrieval_reproducibility_config(payload)

    for field, value in (
        ("authorization", "Bearer abc.def.ghi"),
        ("api_key", "secret-value"),
    ):
        payload = _config()
        payload[field] = value
        with pytest.raises(ValueError, match="unknown fields|secret|credential"):
            validate_retrieval_reproducibility_config(payload)


def test_config_rejects_unknown_nested_fields_versions_paths_and_pickle():
    payload = _config()
    payload["evidence"][0]["module_path"] = "user.module"
    with pytest.raises(ValueError, match="unknown fields"):
        validate_retrieval_reproducibility_config(payload)

    payload = _config()
    payload["evidence"][0]["callable_name"] = "execute"
    with pytest.raises(ValueError, match="unknown fields"):
        validate_retrieval_reproducibility_config(payload)

    for version, message in (("0", "unsupported source version"), ("2", "future version")):
        payload = _config()
        payload["schema_version"] = version
        with pytest.raises(ValueError, match=message):
            validate_retrieval_reproducibility_config(payload)

    payload = _config()
    payload["evidence"][0]["input_path"] = "C:/Users/example/input.json"
    with pytest.raises(ValueError, match="absolute local path|absolute path"):
        validate_retrieval_reproducibility_config(payload)

    payload = _config()
    payload["evidence"][0]["input_path"] = "../input.json"
    with pytest.raises(ValueError, match="path traversal|not registered"):
        validate_retrieval_reproducibility_config(payload)

    payload = _config()
    payload["evidence"][0]["input_path"] = "fixtures/input.pkl"
    with pytest.raises(ValueError, match="not registered"):
        validate_retrieval_reproducibility_config(payload)


def test_config_rejects_self_and_ambiguous_optional_pairs():
    pair = {
        "pair_id": "fixture_pair",
        "case_study_id": "fixture",
        "left_evidence_path": "fixtures/left.json",
        "right_evidence_path": "fixtures/right.json",
    }
    payload = _config()
    payload["optional_comparison_pairs"] = [
        {**pair, "right_evidence_path": "fixtures/left.json"}
    ]
    with pytest.raises(ValueError, match="self-comparison"):
        validate_retrieval_reproducibility_config(payload)

    payload = _config()
    payload["optional_comparison_pairs"] = [
        pair,
        {**pair, "pair_id": "fixture_pair_duplicate"},
    ]
    with pytest.raises(ValueError, match="ambiguous evidence pair"):
        validate_retrieval_reproducibility_config(payload)

    payload = _config()
    payload["optional_comparison_pairs"] = [
        {**pair, "left_evidence_path": "../left.json"}
    ]
    with pytest.raises(ValueError, match="path traversal"):
        validate_retrieval_reproducibility_config(payload)


def test_evidence_and_comparison_reject_unknown_fields_and_checksum_tampering():
    left = _record("fixture_left", "fixtures/left.json", "event_left")
    right = _record("fixture_right", "fixtures/right.json", "event_right")

    evidence = left.to_dict()
    evidence["unexpected"] = True
    with pytest.raises(ValueError, match="unknown fields"):
        RetrievalEvidenceRecord.from_mapping(evidence)

    evidence = left.to_dict()
    evidence["record_checksum_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="checksum mismatch"):
        RetrievalEvidenceRecord.from_mapping(evidence)

    result = compare_retrieval_evidence(
        left,
        right,
        audit_id="fixture_audit",
        pair_id="fixture_pair",
    ).to_dict()
    result["result_checksum_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="checksum mismatch"):
        RetrievalComparisonResult.from_mapping(result)

    result = compare_retrieval_evidence(
        left,
        right,
        audit_id="fixture_audit",
        pair_id="fixture_pair",
    ).to_dict()
    result["final_assessment"] = "production_ready"
    unsigned = dict(result)
    unsigned.pop("result_checksum_sha256")
    result["result_checksum_sha256"] = canonical_json_sha256(unsigned)
    with pytest.raises(ValueError, match="unregistered"):
        RetrievalComparisonResult.from_mapping(result)


def test_evidence_rejects_unknown_nested_metadata_and_old_or_future_versions():
    evidence = _record("fixture_left", "fixtures/left.json", "event_left").to_dict()
    evidence["retrieval_metadata"]["unexpected"] = True
    unsigned = dict(evidence)
    unsigned.pop("record_checksum_sha256")
    evidence["record_checksum_sha256"] = canonical_json_sha256(unsigned)
    with pytest.raises(ValueError, match="unknown fields"):
        RetrievalEvidenceRecord.from_mapping(evidence)

    for version, message in (("0", "unsupported source version"), ("2", "future version")):
        evidence = _record(
            "fixture_left", "fixtures/left.json", "event_left"
        ).to_dict()
        evidence["schema_version"] = version
        unsigned = dict(evidence)
        unsigned.pop("record_checksum_sha256")
        evidence["record_checksum_sha256"] = canonical_json_sha256(unsigned)
        with pytest.raises(ValueError, match=message):
            RetrievalEvidenceRecord.from_mapping(evidence)


def test_cross_domain_comparison_is_rejected():
    with pytest.raises(ValueError, match="cross-domain"):
        compare_retrieval_evidence(
            _record(
                "fixture_left",
                "fixtures/left.json",
                "event_left",
                case_study_id="domain_a",
            ),
            _record(
                "fixture_right",
                "fixtures/right.json",
                "event_right",
                case_study_id="domain_b",
            ),
            audit_id="fixture_audit",
            pair_id="fixture_pair",
        )


def test_tracked_summary_rejects_tampering_unknown_fields_and_statuses():
    payload = json.loads(SUMMARY.read_text(encoding="utf-8"))
    payload["summary_checksum_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="checksum mismatch"):
        validate_retrieval_reproducibility_summary(payload)

    payload = json.loads(SUMMARY.read_text(encoding="utf-8"))
    payload["unexpected"] = True
    with pytest.raises(ValueError, match="unknown fields"):
        validate_retrieval_reproducibility_summary(payload)

    payload = json.loads(SUMMARY.read_text(encoding="utf-8"))
    payload["status"] = "production_ready"
    unsigned = dict(payload)
    unsigned.pop("summary_checksum_sha256")
    payload["summary_checksum_sha256"] = canonical_json_sha256(unsigned)
    with pytest.raises(ValueError, match="unregistered"):
        validate_retrieval_reproducibility_summary(payload)

    assert "production_ready" not in ASSESSMENT_STATUSES
