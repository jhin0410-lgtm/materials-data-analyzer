import json
from dataclasses import replace
from pathlib import Path

import pytest

from src.platform_core.external_source_contracts import canonical_json_sha256
from src.platform_core.external_source_compatibility import (
    ExternalSourceCompatibilityResult,
    MATERIALS_ARTIFACT_KIND,
    adapt_tracked_external_source_artifact,
    build_compatibility_adapter_registry,
    select_compatibility_adapter,
    validate_compatibility_adapter_registry,
    validate_compatibility_config,
    validate_compatibility_summary,
)


SOURCE = Path("data/processed/materials_project_v2_2_4_structure_enrichment_summary.json")


def _config():
    return json.loads(
        Path("configs/examples/external_source_compatibility_audit.json").read_text(encoding="utf-8")
    )


def test_dispatch_rejects_unknown_unsupported_future_and_ambiguous_pairs():
    with pytest.raises(ValueError, match="unknown compatibility artifact kind"):
        select_compatibility_adapter("unknown_artifact", "1")
    with pytest.raises(ValueError, match="unsupported source version"):
        select_compatibility_adapter(MATERIALS_ARTIFACT_KIND, "2.2.3")
    with pytest.raises(ValueError, match="unsupported future version"):
        select_compatibility_adapter(MATERIALS_ARTIFACT_KIND, "9.0.0")

    records = build_compatibility_adapter_registry()
    materials = next(item for item in records if item.input_artifact_kind == MATERIALS_ARTIFACT_KIND)
    ambiguous = (*records, replace(materials, adapter_id="duplicate_materials_adapter_v1"))
    with pytest.raises(ValueError, match="ambiguous compatibility adapter registry"):
        select_compatibility_adapter(
            MATERIALS_ARTIFACT_KIND,
            "2.2.4",
            adapters=ambiguous,
        )
    assert validate_compatibility_adapter_registry(())["valid"] is False


def test_config_rejects_unknown_fields_absolute_paths_traversal_and_secrets():
    payload = _config()
    payload["surprise"] = True
    with pytest.raises(ValueError, match="unknown fields"):
        validate_compatibility_config(payload)

    payload = _config()
    payload["artifacts"][0]["input_path"] = "C:/Users/example/source.json"
    with pytest.raises(ValueError, match="absolute local path|absolute path"):
        validate_compatibility_config(payload)

    payload = _config()
    payload["artifacts"][0]["input_path"] = "../source.json"
    with pytest.raises(ValueError, match="path traversal|registered tracked artifact"):
        validate_compatibility_config(payload)

    payload = _config()
    payload["authorization"] = "Bearer abc.def.ghi"
    with pytest.raises(ValueError, match="unknown fields|credential"):
        validate_compatibility_config(payload)

    payload = _config()
    payload["artifacts"].pop()
    with pytest.raises(ValueError, match="exact registered adapter set"):
        validate_compatibility_config(payload)


def test_adapter_rejects_unknown_input_fields_and_version_changes(tmp_path):
    payload = json.loads(SOURCE.read_text(encoding="utf-8"))
    payload["unexpected"] = "not silently dropped"
    unknown = tmp_path / "unknown.json"
    unknown.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="unknown fields"):
        adapt_tracked_external_source_artifact(
            unknown,
            artifact_kind=MATERIALS_ARTIFACT_KIND,
            expected_version="2.2.4",
            input_artifact_ref="fixtures/unknown.json",
        )

    payload.pop("unexpected")
    payload["schema_version"] = "2.2.5"
    future = tmp_path / "future.json"
    future.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="unsupported future version"):
        adapt_tracked_external_source_artifact(
            future,
            artifact_kind=MATERIALS_ARTIFACT_KIND,
            expected_version="2.2.4",
            input_artifact_ref="fixtures/future.json",
        )


def test_adapter_rejects_claimed_source_mutation_and_secret_like_values(tmp_path):
    payload = json.loads(SOURCE.read_text(encoding="utf-8"))
    payload["original_target_overwritten"] = True
    mutated = tmp_path / "mutated.json"
    mutated.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="original target mutation"):
        adapt_tracked_external_source_artifact(
            mutated,
            artifact_kind=MATERIALS_ARTIFACT_KIND,
            expected_version="2.2.4",
            input_artifact_ref="fixtures/mutated.json",
        )

    payload["original_target_overwritten"] = False
    payload["provenance_policy"] = "api_key=secret-value"
    secret = tmp_path / "secret.json"
    secret.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="credential-like"):
        adapt_tracked_external_source_artifact(
            secret,
            artifact_kind=MATERIALS_ARTIFACT_KIND,
            expected_version="2.2.4",
            input_artifact_ref="fixtures/secret.json",
        )


def test_summary_validation_rejects_unknown_nested_adapter_fields():
    payload = json.loads(
        Path("data/processed/external_source_compatibility_audit_summary_v1.json").read_text(
            encoding="utf-8"
        )
    )
    payload["adapter_results"][0]["unexpected"] = "must not be silently dropped"
    without_checksum = dict(payload)
    without_checksum.pop("summary_checksum_sha256")
    payload["summary_checksum_sha256"] = canonical_json_sha256(without_checksum)
    with pytest.raises(ValueError, match="unknown fields"):
        validate_compatibility_summary(payload)


def test_result_and_summary_validation_enforce_registered_adapter_contracts():
    result = adapt_tracked_external_source_artifact(
        SOURCE,
        artifact_kind=MATERIALS_ARTIFACT_KIND,
        expected_version="2.2.4",
    ).to_dict()
    result["adapter_version"] = "2"
    without_checksum = dict(result)
    without_checksum.pop("result_checksum_sha256")
    result["result_checksum_sha256"] = canonical_json_sha256(without_checksum)
    with pytest.raises(ValueError, match="adapter version mismatch"):
        ExternalSourceCompatibilityResult.from_mapping(result)

    summary = json.loads(
        Path("data/processed/external_source_compatibility_audit_summary_v1.json").read_text(
            encoding="utf-8"
        )
    )
    summary["status"] = "fully_compatible"
    without_checksum = dict(summary)
    without_checksum.pop("summary_checksum_sha256")
    summary["summary_checksum_sha256"] = canonical_json_sha256(without_checksum)
    with pytest.raises(ValueError, match="overall status mismatch"):
        validate_compatibility_summary(summary)
