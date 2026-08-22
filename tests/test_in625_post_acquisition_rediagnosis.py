from __future__ import annotations

import hashlib
import json

import pytest

from materials_data_analyzer.research_loop.in625_post_acquisition_rediagnosis import (
    In625PostAcquisitionRediagnosisError,
    build_in625_post_acquisition_rediagnosis,
)

SOURCE_ID = "zenodo-20503603-in625-lpbf-publication-supplement"
ARCHIVE_SHA = "389602211b440cab5142c4071cb3c697702431d9b3aad2dfe2e6500de0a72907"


def _canonical_sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _authorization() -> dict[str, object]:
    value: dict[str, object] = {
        "schema_version": "1.0",
        "policy_version": "1.0",
        "authorization_status": "authorized_exact_archive_download",
        "source_id": SOURCE_ID,
        "zenodo_record_id": "20503603",
        "source_config_sha256": "1" * 64,
        "metadata_sha256": "2" * 64,
        "readme_sha256": "3" * 64,
        "readme_manifest_sha256": "4" * 64,
        "archive": {
            "file_name": "Dataset.zip",
            "download_url": "https://zenodo.org/api/records/20503603/files/Dataset.zip/content",
            "allowed_hosts": ["zenodo.org"],
            "expected_size_bytes": 180726708,
            "provider_checksum_algorithm": "md5",
            "provider_checksum_digest": "54601f974a9590be104cf1e3090b68bd",
            "expected_sha256": ARCHIVE_SHA,
        },
        "preconditions_verified": {
            "exact_repository_source_config": True,
            "exact_live_zenodo_record": True,
            "exact_readme_bytes": True,
            "open_license_identity": True,
            "archive_provider_identity": True,
            "project_archive_sha256_pre_pinned": True,
            "https_exact_host_restriction": True,
        },
        "network_execution_authorized": True,
        "network_access_performed": False,
        "archive_bytes_observed": False,
        "scientific_status_changed": False,
    }
    value["authorization_sha256"] = _canonical_sha(value)
    return value


def _receipt(authorization_sha: str) -> dict[str, object]:
    value: dict[str, object] = {
        "schema_version": "1.0",
        "policy_version": "1.0",
        "authorization_sha256": authorization_sha,
        "source_id": SOURCE_ID,
        "zenodo_record_id": "20503603",
        "archive": {
            "path": "/tmp/Dataset.zip",
            "file_name": "Dataset.zip",
            "size_bytes": 180726708,
            "provider_md5": "54601f974a9590be104cf1e3090b68bd",
            "sha256": ARCHIVE_SHA,
            "requested_url": "https://zenodo.org/api/records/20503603/files/Dataset.zip/content",
            "final_url": "https://zenodo.org/api/records/20503603/files/Dataset.zip/content",
            "content_type": "application/octet-stream",
        },
        "network_execution_authorized": True,
        "network_access_performed": True,
        "exact_host_restriction_enforced": True,
        "byte_count_verified": True,
        "provider_checksum_verified": True,
        "project_sha256_verified": True,
        "scientific_boundary": {
            "source_provenance_established_by_successful_download": True,
            "sample_identity_established": False,
            "measurement_semantics_interpreted": False,
            "replicate_independence_established": False,
            "direct_nist_condition_comparability_established": False,
            "empirical_model_validation_established": False,
            "hypothesis_truth_established": False,
            "positive_scientific_closeout_established": False,
            "automatic_scientific_promotion": False,
        },
    }
    value["receipt_sha256"] = _canonical_sha(value)
    return value


def _execution() -> dict[str, object]:
    return {
        "request_sha256": "5" * 64,
        "verified_report": {
            "registered_outcome": "verified_external_source_archive_registered",
            "archive_sha256": ARCHIVE_SHA,
            "source_provenance_verified": True,
            "direct_condition_comparability_established": False,
            "empirical_model_validation_established": False,
            "scientific_status_changed": False,
        },
    }


def _tensile() -> dict[str, object]:
    value: dict[str, object] = {
        "schema_version": "1.0",
        "source_id": SOURCE_ID,
        "source_archive_sha256": ARCHIVE_SHA,
        "policy": {"path": "/tmp/policy.json", "sha256": "6" * 64},
        "workbook": {"path": "/tmp/Tensile tests.xlsx", "sha256": "7" * 64, "bytes": 25660091},
        "documentation": {"path": "/tmp/README.txt", "sha256": "8" * 64, "bytes": 1255, "encoding": "cp1250"},
        "sheet_count": 7,
        "parallel_test_block_count": 19,
        "measurement_row_count": 200289,
        "cell_count_observed": 2400000,
        "sheets": [],
        "row_artifact": {"path": "/tmp/rows.jsonl", "sha256": "9" * 64, "bytes": 123, "row_count": 200289},
        "reviewed_semantics": {
            "sheet_condition_semantics_from_source_readme": True,
            "measurement_columns_from_exact_workbook_header": True,
            "locale_decimal_normalization_applied": True,
            "formula_evaluation_performed": False,
            "number_format_interpretation_performed": False,
            "parallel_test_independence_established": False,
        },
        "scientific_boundaries": {
            "real_row_level_external_measurements_observed": True,
            "direct_nist_condition_comparability_established": False,
            "empirical_model_validation_established": False,
            "hypothesis_truth_established": False,
            "positive_scientific_closeout_established": False,
            "automatic_scientific_promotion": False,
        },
    }
    value["manifest_sha256"] = _canonical_sha(value)
    return value


def _valid_inputs():
    authorization = _authorization()
    return authorization, _receipt(str(authorization["authorization_sha256"])), _execution(), _tensile()


def test_post_acquisition_rediagnosis_moves_from_availability_to_comparability() -> None:
    authorization, receipt, execution, tensile = _valid_inputs()
    result = build_in625_post_acquisition_rediagnosis(
        network_authorization=authorization,
        network_receipt=receipt,
        typed_execution_result=execution,
        reviewed_tensile_manifest=tensile,
    )
    assert result["resolved_blockers"][0]["code"] == "empirical_evidence_not_acquired"
    assert result["resolved_blockers"][0]["resolved"] is True
    assert result["current_blocker"]["code"] == "cross_source_physical_comparability_not_established"
    assert result["next_action"]["action_class"] == "reviewed_physical_comparability_assessment"
    assert result["stop_state"]["status"] == "continue"
    assert result["stop_state"]["positive_scientific_closeout"] is False
    assert result["evidence_state"]["real_row_level_measurements_observed"] is True
    assert result["evidence_state"]["replicate_independence_established"] is False
    assert result["scientific_status_changed"] is False


def test_post_acquisition_rediagnosis_rejects_receipt_substitution() -> None:
    authorization, receipt, execution, tensile = _valid_inputs()
    receipt["authorization_sha256"] = "a" * 64
    receipt["receipt_sha256"] = _canonical_sha({k: v for k, v in receipt.items() if k != "receipt_sha256"})
    with pytest.raises(In625PostAcquisitionRediagnosisError, match="not bound"):
        build_in625_post_acquisition_rediagnosis(
            network_authorization=authorization,
            network_receipt=receipt,
            typed_execution_result=execution,
            reviewed_tensile_manifest=tensile,
        )


def test_post_acquisition_rediagnosis_rejects_archive_substitution() -> None:
    authorization, receipt, execution, tensile = _valid_inputs()
    execution["verified_report"]["archive_sha256"] = "b" * 64
    with pytest.raises(In625PostAcquisitionRediagnosisError, match="registration boundary"):
        build_in625_post_acquisition_rediagnosis(
            network_authorization=authorization,
            network_receipt=receipt,
            typed_execution_result=execution,
            reviewed_tensile_manifest=tensile,
        )


def test_post_acquisition_rediagnosis_rejects_independence_claim() -> None:
    authorization, receipt, execution, tensile = _valid_inputs()
    tensile["reviewed_semantics"]["parallel_test_independence_established"] = True
    tensile["manifest_sha256"] = _canonical_sha({k: v for k, v in tensile.items() if k != "manifest_sha256"})
    with pytest.raises(In625PostAcquisitionRediagnosisError, match="over-claimed"):
        build_in625_post_acquisition_rediagnosis(
            network_authorization=authorization,
            network_receipt=receipt,
            typed_execution_result=execution,
            reviewed_tensile_manifest=tensile,
        )


def test_post_acquisition_rediagnosis_rejects_positive_comparability_claim() -> None:
    authorization, receipt, execution, tensile = _valid_inputs()
    tensile["scientific_boundaries"]["direct_nist_condition_comparability_established"] = True
    tensile["manifest_sha256"] = _canonical_sha({k: v for k, v in tensile.items() if k != "manifest_sha256"})
    with pytest.raises(In625PostAcquisitionRediagnosisError, match="widens scientific authority"):
        build_in625_post_acquisition_rediagnosis(
            network_authorization=authorization,
            network_receipt=receipt,
            typed_execution_result=execution,
            reviewed_tensile_manifest=tensile,
        )


def test_post_acquisition_rediagnosis_rejects_tampered_manifest_digest() -> None:
    authorization, receipt, execution, tensile = _valid_inputs()
    tensile["measurement_row_count"] = 1
    with pytest.raises(In625PostAcquisitionRediagnosisError, match="canonical SHA-256"):
        build_in625_post_acquisition_rediagnosis(
            network_authorization=authorization,
            network_receipt=receipt,
            typed_execution_result=execution,
            reviewed_tensile_manifest=tensile,
        )
