import hashlib
import json
from pathlib import Path

from src.platform_core.external_source_compatibility import (
    BATTERY_ARTIFACT_KIND,
    DEFAULT_CONFIG_PATH,
    MATERIALS_ARTIFACT_KIND,
    TRACKED_SUMMARY_PATH,
    adapt_tracked_external_source_artifact,
    build_compatibility_adapter_registry,
    build_compatibility_audit_summary,
    load_compatibility_config,
    run_external_source_compatibility_audit,
    validate_compatibility_adapter_registry,
    validate_compatibility_summary,
)
from src.platform_core.external_source_contracts import canonical_json_sha256


MATERIALS_PATH = Path("data/processed/materials_project_v2_2_4_structure_enrichment_summary.json")
BATTERY_PATH = Path("data/processed/battery_v2_3_5_source_lineage_summary.json")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha(path: Path) -> str:
    return canonical_json_sha256(json.loads(path.read_text(encoding="utf-8")))


def test_adapter_registry_is_explicit_unique_and_deterministic():
    first = build_compatibility_adapter_registry()
    second = build_compatibility_adapter_registry()

    assert first == second
    assert [item.adapter_id for item in first] == sorted(item.adapter_id for item in first)
    assert len(first) == len({item.adapter_id for item in first}) == 2
    assert validate_compatibility_adapter_registry(first)["valid"] is True
    assert all(item.migration_performed is False for item in first)
    assert all(item.source_mutation_performed is False for item in first)


def test_materials_adapter_is_deterministic_and_preserves_unresolved_snapshot_fields():
    before = _sha(MATERIALS_PATH)
    first = adapt_tracked_external_source_artifact(
        MATERIALS_PATH,
        artifact_kind=MATERIALS_ARTIFACT_KIND,
        expected_version="2.2.4",
    )
    second = adapt_tracked_external_source_artifact(
        MATERIALS_PATH,
        artifact_kind=MATERIALS_ARTIFACT_KIND,
        expected_version="2.2.4",
    )

    assert first == second
    assert first.result_checksum_sha256 == second.result_checksum_sha256
    assert first.input_raw_bytes_sha256 != first.input_canonical_json_sha256
    assert first.compatibility_status == "compatible_with_restrictions"
    assert "named_dataset_snapshot_version" in first.unresolved_fields
    assert "api_client_version" in first.cannot_infer_fields
    assert "typed_local_derived_artifact_record" in first.blocked_or_unsupported_fields
    assert first.input_mutated is False
    assert _sha(MATERIALS_PATH) == before


def test_battery_adapter_remains_partial_without_default_filling():
    before = _sha(BATTERY_PATH)
    result = adapt_tracked_external_source_artifact(
        BATTERY_PATH,
        artifact_kind=BATTERY_ARTIFACT_KIND,
        expected_version="2.3.5",
    )

    assert result.compatibility_status == "partial"
    assert result.declared_mapping_status == "partial"
    assert {
        "official_nasa_snapshot_version",
        "original_retrieval_timestamp",
        "license_or_terms",
        "measurement_uncertainty",
        "calibration_metadata",
    }.issubset(result.unresolved_fields)
    assert result.network_called is False
    assert result.credentials_read is False
    assert result.credentials_persisted is False
    assert result.model_executed is False
    assert _sha(BATTERY_PATH) == before


def test_tracked_summary_matches_runtime_generation():
    config = load_compatibility_config(DEFAULT_CONFIG_PATH)
    results = [
        adapt_tracked_external_source_artifact(
            request.input_path,
            artifact_kind=request.artifact_kind,
            expected_version=request.expected_version,
            adapter_id=request.adapter_id,
            input_artifact_ref=request.input_path,
            audit_id=config.audit_id,
        )
        for request in config.artifacts
    ]
    expected = build_compatibility_audit_summary(config, results)
    tracked = json.loads(Path(TRACKED_SUMMARY_PATH).read_text(encoding="utf-8"))

    assert tracked == expected
    assert all("input_raw_bytes_sha256" not in row for row in tracked["adapter_results"])
    assert all("result_checksum_sha256" not in row for row in tracked["adapter_results"])
    assert validate_compatibility_summary(tracked)["valid"] is True
    assert tracked["compatibility_status_counts"] == {
        "blocked": 0,
        "compatible_with_restrictions": 1,
        "fully_compatible": 0,
        "partial": 1,
        "unsupported": 0,
    }
    assert tracked["trust_score_used"] is False


def test_clean_checkout_audit_requires_only_two_tracked_compact_inputs(tmp_path):
    for source in (MATERIALS_PATH, BATTERY_PATH):
        target = tmp_path / source
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    config = load_compatibility_config(DEFAULT_CONFIG_PATH)

    result = run_external_source_compatibility_audit(
        config,
        repo_root=tmp_path,
        execute=True,
        write_local=False,
        write_tracked=True,
    )

    assert result["status"] == "completed"
    assert result["written"] == [TRACKED_SUMMARY_PATH]
    assert not (tmp_path / "data/raw").exists()
    assert (tmp_path / TRACKED_SUMMARY_PATH).is_file()


def test_v2_2_and_v2_3_source_artifacts_keep_canonical_json_checksums():
    assert _canonical_sha(MATERIALS_PATH) == "0cb63a1da65c0e25bbc94995a907b583b7028cbd79c32bf1fc3fcda2d7503a38"
    assert _canonical_sha(BATTERY_PATH) == "fa43443ecc82f147fdc7117524c911d4ffd63be9b657993736f3bfd30c58e87a"
