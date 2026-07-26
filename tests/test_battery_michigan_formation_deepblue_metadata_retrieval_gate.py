from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from src.platform_core import battery_michigan_formation_deepblue_metadata_retrieval_gate as mod


def _dataset(*, embedded: bool = True) -> dict:
    file_sets = [
        {
            "id": "abc123456",
            "title": ["Fast Formation Data"],
            "label": "fast_formation_data.zip",
            "date_uploaded": "2021-09-22",
            "date_modified": "2021-09-22",
            "file_size": 2500000000,
            "file_size_human_readable": "2.33 GB",
            "checksum_algorithm": "SHA-256",
            "checksum_value": "a" * 64,
            "original_checksum": "b" * 64,
            "mime_type": "application/zip",
            "creator": ["must not be retained"],
            "depositor": "must-not-be-retained@example.com",
            "description": ["must not be retained"],
        },
        {
            "id": "def123456",
            "title": ["README"],
            "label": "README.md",
            "date_uploaded": "2021-09-22",
            "date_modified": "2022-11-17",
            "file_size": 12000,
            "file_size_human_readable": "11.72 KB",
            "checksum_algorithm": "SHA-256",
            "checksum_value": "c" * 64,
            "original_checksum": "d" * 64,
            "mime_type": "text/markdown",
            "creator": ["must not be retained"],
        },
    ]
    value = {
        "id": mod.DATASET_ID,
        "title": [mod.DATASET_TITLE],
        "doi": f"https://doi.org/{mod.DATASET_DOI}",
        "total_file_count": 2,
        "total_file_size": 2500012000,
        "total_file_size_human_readable": "2.33 GB",
        "file_set_ids": ["abc123456", "def123456"],
        "authoremail": "must-not-be-retained@example.com",
        "depositor": "must-not-be-retained@example.com",
        "description": ["must not be retained"],
    }
    if embedded:
        value["file_sets"] = file_sets
    return value


def _contract() -> dict:
    return json.loads(Path(mod.DEFAULT_CONTRACT_PATH).read_text(encoding="utf-8"))


def _evidence() -> dict:
    return json.loads(Path(mod.DEFAULT_EVIDENCE_PATH).read_text(encoding="utf-8"))


def _preservation() -> dict:
    return {
        "v2_6_12_checksum_verified": True,
        "v2_6_12_overall_status": "provider_package_structure_recovered_exact_manifest_not_established_gate_not_passed",
        "model_or_metric_change_performed": False,
    }


def test_schemas_are_valid():
    for name in (
        "battery_michigan_formation_deepblue_metadata_retrieval_config_schema_v1.json",
        "battery_michigan_formation_deepblue_metadata_retrieval_contract_schema_v1.json",
        "battery_deepblue_rest_api_metadata_evidence_schema_v1.json",
        "battery_michigan_formation_deepblue_metadata_retrieval_result_schema_v1.json",
    ):
        value = json.loads((Path("data/platform") / name).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(value)


def test_config_contract_and_evidence_checksums():
    config = mod.load_config()
    contract = _contract()
    evidence = _evidence()
    assert config["execution_policy"]["metadata_get_only"] is True
    assert mod.canonical_checksum(contract) == mod.EXPECTED_CONTRACT_CHECKSUM
    assert mod.canonical_checksum(evidence) == mod.EXPECTED_EVIDENCE_CHECKSUM
    mod.validate_contract(contract)
    mod.validate_api_evidence(evidence)


def test_pending_result_is_deterministic_and_non_networked():
    result = mod._pending_result(mod.EXPECTED_CONTRACT_CHECKSUM, mod.EXPECTED_EVIDENCE_CHECKSUM, _preservation())
    mod.validate_result(result)
    assert result["retrieval_status"] == "pending_local_metadata_retrieval"
    assert result["network_called"] is False
    assert result["network_call_count"] == 0
    assert result["deterministic_result_checksum"] == "ea35e4a5dbd7e1233750aac795d6b112750e0f0de9a564467c1cfea660a16eef"


def test_embedded_file_set_metadata_is_recovered_without_extra_calls():
    raw = json.dumps(_dataset(embedded=True)).encode("utf-8")
    calls: list[str] = []

    def fake_fetch(url: str, max_bytes: int, timeout: int):
        calls.append(url)
        assert len(raw) <= max_bytes
        assert timeout == 30
        return raw, "application/json"

    result = mod._actual_result(_contract(), _evidence(), _preservation(), fake_fetch)
    mod.validate_result(result, allow_pending=False)
    assert calls == [mod.DATASET_URL]
    assert result["network_call_count"] == 1
    assert result["metadata_completeness"]["repository_checksums_recovered"] is True
    assert result["decision"]["overall_status"] == "top_level_file_set_metadata_recovered_internal_manifest_not_established"
    text = json.dumps(result)
    assert "must-not-be-retained" not in text
    assert "authoremail" not in text
    assert "depositor" not in text
    assert result["raw_response_retained"] is False
    assert result["provider_file_payload_read"] is False


def test_file_set_endpoint_fallback_is_bounded_to_two_requests():
    dataset = _dataset(embedded=False)
    file_sets = _dataset(embedded=True)["file_sets"]
    payloads = {
        mod.DATASET_URL: json.dumps(dataset).encode("utf-8"),
        mod.FILE_SET_URL_TEMPLATE.format(file_set_id="abc123456"): json.dumps(file_sets[0]).encode("utf-8"),
        mod.FILE_SET_URL_TEMPLATE.format(file_set_id="def123456"): json.dumps(file_sets[1]).encode("utf-8"),
    }
    calls: list[str] = []

    def fake_fetch(url: str, max_bytes: int, timeout: int):
        calls.append(url)
        return payloads[url], "application/json"

    result = mod._actual_result(_contract(), _evidence(), _preservation(), fake_fetch)
    assert len(calls) == 3
    assert result["network_call_count"] == 3
    assert [item["id"] for item in result["file_set_records"]] == ["abc123456", "def123456"]
    assert all(item["record_source"] == "file_set_endpoint" for item in result["file_set_response_audits"])


@pytest.mark.parametrize(
    "url,file_set_id",
    [
        ("http://deepblue.lib.umich.edu/data/concern/data_sets/b2773w109.json", None),
        ("https://example.com/data/concern/data_sets/b2773w109.json", None),
        ("https://deepblue.lib.umich.edu/data/downloads/abc123456.json", "abc123456"),
        ("https://deepblue.lib.umich.edu/data/concern/data_sets/b2773w109/zip_download.json", None),
        ("https://deepblue.lib.umich.edu/data/concern/data_sets/b2773w109.json?x=1", None),
        ("https://deepblue.lib.umich.edu/data/concern/file_sets/../../secret.json", "abc123456"),
    ],
)
def test_unsafe_urls_are_rejected(url: str, file_set_id: str | None):
    with pytest.raises(mod.MetadataRetrievalError):
        mod._safe_url(url, file_set_id=file_set_id)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.__setitem__("id", "wrong"),
        lambda value: value.__setitem__("doi", "10.0000/wrong"),
        lambda value: value.__setitem__("title", ["Wrong title"]),
        lambda value: value.__setitem__("total_file_count", 3),
        lambda value: value.__setitem__("file_set_ids", ["abc123456", "abc123456"]),
        lambda value: value.__setitem__("file_set_ids", ["bad", "def123456"]),
    ],
)
def test_dataset_identity_mutations_fail_closed(mutation):
    value = _dataset()
    mutation(value)
    raw = json.dumps(value).encode("utf-8")

    def fake_fetch(url: str, max_bytes: int, timeout: int):
        return raw, "application/json"

    with pytest.raises(mod.MetadataRetrievalError):
        mod._actual_result(_contract(), _evidence(), _preservation(), fake_fetch)


def test_missing_checksums_stays_diagnostic_and_does_not_infer():
    value = _dataset()
    value["file_sets"][0]["checksum_algorithm"] = None
    value["file_sets"][0]["checksum_value"] = None
    raw = json.dumps(value).encode("utf-8")

    def fake_fetch(url: str, max_bytes: int, timeout: int):
        return raw, "application/json"

    result = mod._actual_result(_contract(), _evidence(), _preservation(), fake_fetch)
    mod.validate_result(result, allow_pending=False)
    assert result["metadata_completeness"]["repository_checksums_recovered"] is False
    assert result["decision"]["overall_status"] == "top_level_file_set_metadata_partial_internal_manifest_not_established"
    assert result["missing_metadata_inferred"] is False
    assert result["candidate_admitted"] is False


def test_result_rejects_scientific_promotion():
    raw = json.dumps(_dataset()).encode("utf-8")

    def fake_fetch(url: str, max_bytes: int, timeout: int):
        return raw, "application/json"

    result = mod._actual_result(_contract(), _evidence(), _preservation(), fake_fetch)
    promoted = copy.deepcopy(result)
    promoted["decision"]["internal_provider_manifest"] = "established"
    promoted["deterministic_result_checksum"] = mod.canonical_checksum(promoted)
    with pytest.raises(ValueError):
        mod.validate_result(promoted, allow_pending=False)
    promoted = copy.deepcopy(result)
    promoted["candidate_admitted"] = True
    promoted["deterministic_result_checksum"] = mod.canonical_checksum(promoted)
    with pytest.raises(ValueError):
        mod.validate_result(promoted, allow_pending=False)


def test_path_escape_is_rejected(tmp_path: Path):
    with pytest.raises(ValueError):
        mod.repo_path(tmp_path, "../escape.json")
