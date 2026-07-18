import json

import pytest

from src.platform_core.external_source_contracts import (
    ExternalRetrievalEventRecord,
    ExternalSourcePersistedRecord,
    ExternalSourceSystemRecord,
    build_external_source_contract_records,
    build_external_source_system_registry,
    external_source_registry_payloads,
)


def _system_payload():
    return build_external_source_system_registry()[0].to_dict()


def test_environment_variable_name_is_allowed_but_credential_value_is_rejected():
    payload = _system_payload()
    assert payload["authentication_environment_variable"] == "MP_API_KEY"

    payload["authentication_environment_variable"] = "actual-secret-value"
    with pytest.raises(ValueError, match="environment-variable names"):
        ExternalSourceSystemRecord.from_mapping(payload)


def test_authorization_header_and_signed_query_secret_are_rejected():
    record = ExternalSourcePersistedRecord.from_record(build_external_source_system_registry()[0])
    for secret_payload in (
        {**record.record, "documentation_refs": ["Bearer abc.def.ghi"]},
        {**record.record, "official_landing_page": "https://example.invalid/?api_key=secret"},
    ):
        with pytest.raises(ValueError, match="credential-like"):
            ExternalSourcePersistedRecord(
                schema_id=record.schema_id,
                schema_version="1",
                record_type=record.record_type,
                record=secret_payload,
                canonical_json_sha256="0" * 64,
            )


def test_retrieval_authentication_mode_requires_matching_environment_metadata():
    payload = build_external_source_contract_records()["retrieval_events"][0].to_dict()

    payload["authentication_environment_variable"] = None
    with pytest.raises(ValueError, match="must name its environment variable"):
        ExternalRetrievalEventRecord.from_mapping(payload)

    payload["authentication_mode"] = "none"
    payload["authentication_environment_variable"] = "MP_API_KEY"
    with pytest.raises(ValueError, match="conflicts with authentication mode"):
        ExternalRetrievalEventRecord.from_mapping(payload)


def test_persisted_records_reject_absolute_paths_outside_path_specific_fields():
    payload = _system_payload()
    payload["documentation_refs"] = ["/tmp/source-doc.json"]

    with pytest.raises(ValueError, match="absolute local path"):
        ExternalSourceSystemRecord.from_mapping(payload)


def test_registry_payload_has_no_secret_values_or_user_paths():
    serialized = json.dumps(external_source_registry_payloads(), sort_keys=True)

    assert "Bearer " not in serialized
    assert "Authorization" not in serialized
    assert "C:/Users/" not in serialized
    assert "C:\\Users\\" not in serialized
    assert "MP_API_KEY" in serialized
    assert "NVD_API_KEY" in serialized
    assert "NREL_API_KEY" in serialized
