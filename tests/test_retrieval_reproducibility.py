import hashlib
import json
from pathlib import Path

import pytest

from src.platform_core.external_source_contracts import canonical_json_sha256
from src.platform_core.retrieval_reproducibility import (
    DEFAULT_CONFIG_PATH,
    TRACKED_SUMMARY_PATH,
    RETRIEVAL_METADATA_FIELDS,
    build_retrieval_evidence_record,
    compare_retrieval_evidence,
    load_retrieval_reproducibility_config,
    run_retrieval_reproducibility_audit,
    validate_retrieval_reproducibility_summary,
)


MATERIALS_PATH = Path(
    "data/processed/materials_project_v2_2_4_structure_enrichment_summary.json"
)
BATTERY_PATH = Path("data/processed/battery_v2_3_5_source_lineage_summary.json")
COMPATIBILITY_PATH = Path(
    "data/processed/external_source_compatibility_audit_summary_v1.json"
)


def _metadata(**overrides):
    result = {
        "retrieval_timestamp": "2026-01-01T00:00:00Z",
        "client_name": "fixture-client",
        "client_version": "1.0",
        "endpoint_or_method": "fixture-endpoint",
        "query_or_parameters": {"ids": ["a", "b"]},
        "requested_entity_identifiers": ["a", "b"],
        "response_count": 2,
        "input_schema_version": "1",
        "transformation_boundary": "none",
    }
    result.update(overrides)
    return result


def _field_sources():
    fields = {
        "artifact_ref",
        "artifact_version",
        "retrieval_event_ref",
        "source_system_ref",
        "dataset_ref",
        "distribution_ref",
        "snapshot_ref",
        *RETRIEVAL_METADATA_FIELDS,
    }
    return {field: f"fixture.{field}" for field in fields}


def _evidence(
    evidence_id,
    artifact_ref,
    *,
    payload=None,
    artifact_bytes=None,
    metadata=None,
    case_study_id="fixture_domain",
    artifact_role="retrieved_json",
    independent=True,
    snapshot_ref="snapshot-1",
    missing=(),
):
    logical = {"rows": [1, 2]} if payload is None else payload
    raw = (
        json.dumps(logical, sort_keys=True).encode("utf-8")
        if artifact_bytes is None
        else artifact_bytes
    )
    event_number = "1" if evidence_id.endswith("left") else "2"
    return build_retrieval_evidence_record(
        evidence_id=evidence_id,
        case_study_id=case_study_id,
        artifact_role=artifact_role,
        artifact_kind="fixture_retrieval_json",
        artifact_version="1",
        artifact_ref=artifact_ref,
        artifact_bytes=raw,
        logical_payload=logical,
        source_system_ref="fixture_source",
        dataset_ref="fixture_dataset",
        distribution_ref="fixture_distribution",
        snapshot_ref=snapshot_ref,
        retrieval_event_ref=f"fixture_event_{event_number}",
        source_distribution_raw_sha256=None,
        retrieval_metadata=_metadata(
            **({"retrieval_timestamp": f"2026-01-0{event_number}T00:00:00Z"})
            if metadata is None
            else metadata
        ),
        known_missing_metadata=missing,
        evidence_field_sources=_field_sources(),
        independent_retrieval_event=independent,
        limitations=(),
    )


def _compare(left, right):
    return compare_retrieval_evidence(
        left,
        right,
        audit_id="fixture_retrieval_audit",
        pair_id="fixture_pair",
    )


def test_raw_and_canonical_checksums_are_distinct_and_logical_format_is_stable():
    logical = {"alpha": 1, "beta": [2, 3]}
    compact = b'{"alpha":1,"beta":[2,3]}\n'
    formatted = b'{\r\n  "beta": [2, 3],\r\n  "alpha": 1\r\n}\r\n'
    left = _evidence(
        "fixture_left",
        "fixtures/left.json",
        payload=logical,
        artifact_bytes=compact,
    )
    right = _evidence(
        "fixture_right",
        "fixtures/right.json",
        payload=logical,
        artifact_bytes=formatted,
    )

    assert left.artifact_raw_bytes_sha256 != right.artifact_raw_bytes_sha256
    assert left.canonical_logical_sha256 == right.canonical_logical_sha256
    assert _compare(left, right).final_assessment == "logically_reproducible"


def test_exact_content_changed_and_metadata_mismatch_assessments():
    raw = b'{"rows":[1,2]}'
    exact = _compare(
        _evidence("fixture_left", "fixtures/left.json", artifact_bytes=raw),
        _evidence("fixture_right", "fixtures/right.json", artifact_bytes=raw),
    )
    changed = _compare(
        _evidence("fixture_left", "fixtures/left.json"),
        _evidence(
            "fixture_right",
            "fixtures/right.json",
            payload={"rows": [1, 3]},
        ),
    )
    metadata = _compare(
        _evidence("fixture_left", "fixtures/left.json"),
        _evidence(
            "fixture_right",
            "fixtures/right.json",
            metadata={"client_version": "2.0"},
        ),
    )

    assert exact.final_assessment == "exact_reproducible"
    assert exact.raw_byte_match is True
    assert changed.final_assessment == "content_changed"
    assert changed.canonical_logical_match is False
    assert metadata.final_assessment == "metadata_mismatch"
    assert "client_version" in metadata.mismatched_metadata_fields


def test_insufficient_and_not_comparable_are_first_class_results():
    insufficient = _compare(
        _evidence(
            "fixture_left",
            "fixtures/left.json",
            independent=False,
            snapshot_ref=None,
            missing=("snapshot_ref",),
        ),
        _evidence(
            "fixture_right",
            "fixtures/right.json",
            independent=False,
            snapshot_ref=None,
            missing=("snapshot_ref",),
        ),
    )
    not_comparable = _compare(
        _evidence("fixture_left", "fixtures/left.json"),
        _evidence(
            "fixture_right",
            "fixtures/right.json",
            artifact_role="different_artifact_role",
        ),
    )

    assert insufficient.final_assessment == "insufficient_evidence"
    assert "independent_retrieval_event_not_established" in (
        insufficient.blocked_comparison_reasons
    )
    assert "snapshot_ref" in insufficient.unresolved_metadata_fields
    assert not_comparable.final_assessment == "not_comparable"
    assert not_comparable.comparison_eligible is False


def test_comparison_is_deterministic_and_rejects_cross_domain_and_self_comparison():
    left = _evidence("fixture_left", "fixtures/left.json")
    right = _evidence("fixture_right", "fixtures/right.json")
    first = _compare(left, right)
    second = _compare(left, right)

    assert first == second
    assert first.result_checksum_sha256 == second.result_checksum_sha256

    with pytest.raises(ValueError, match="cross-domain"):
        _compare(
            left,
            _evidence(
                "fixture_right",
                "fixtures/right.json",
                case_study_id="different_domain",
            ),
        )
    with pytest.raises(ValueError, match="same evidence"):
        _compare(left, left)
    with pytest.raises(ValueError, match="same-file self-comparison"):
        _compare(
            left,
            _evidence(
                "fixture_right",
                "fixtures/left.json",
                metadata={"retrieval_timestamp": "2026-01-01T00:00:00Z"},
            ),
        )


def test_real_tracked_readiness_is_raw_free_and_insufficient_for_each_domain(tmp_path):
    for source in (
        MATERIALS_PATH,
        BATTERY_PATH,
        COMPATIBILITY_PATH,
        Path(DEFAULT_CONFIG_PATH),
    ):
        target = tmp_path / source
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    config = load_retrieval_reproducibility_config(tmp_path / DEFAULT_CONFIG_PATH)
    before = {
        path: hashlib.sha256((tmp_path / path).read_bytes()).hexdigest()
        for path in (MATERIALS_PATH, BATTERY_PATH, COMPATIBILITY_PATH)
    }

    result = run_retrieval_reproducibility_audit(
        config,
        repo_root=tmp_path,
        execute=True,
        write_local=False,
        write_tracked=True,
    )
    after = {
        path: hashlib.sha256((tmp_path / path).read_bytes()).hexdigest()
        for path in (MATERIALS_PATH, BATTERY_PATH, COMPATIBILITY_PATH)
    }

    assert result["assessment"] == "insufficient_evidence"
    assert before == after
    assert result["written"] == [TRACKED_SUMMARY_PATH]
    assert not (tmp_path / "data/raw").exists()
    assert not (tmp_path / "outputs").exists()
    summary = result["summary"]
    assert [row["case_study_id"] for row in summary["case_study_results"]] == [
        "battery",
        "materials_project",
    ]
    assert all(
        row["assessment_status"] == "insufficient_evidence"
        and row["valid_comparison_pair_exists"] is False
        for row in summary["case_study_results"]
    )
    assert all(
        "artifact_raw_bytes_sha256" not in row
        and "source_distribution_raw_sha256" not in row
        for row in summary["case_study_results"]
    )
    assert summary["compatibility_context"]["battery_status"] == "partial"
    assert summary["compatibility_context"]["materials_status"] == (
        "compatible_with_restrictions"
    )


def test_tracked_summary_matches_runtime_generation_and_is_deterministic():
    config = load_retrieval_reproducibility_config(DEFAULT_CONFIG_PATH)
    first = run_retrieval_reproducibility_audit(
        config,
        execute=True,
        write_local=False,
        write_tracked=False,
    )
    second = run_retrieval_reproducibility_audit(
        config,
        execute=True,
        write_local=False,
        write_tracked=False,
    )
    tracked = json.loads(Path(TRACKED_SUMMARY_PATH).read_text(encoding="utf-8"))

    assert first["summary"] == second["summary"] == tracked
    assert validate_retrieval_reproducibility_summary(tracked)["valid"] is True
    assert tracked["summary_checksum_sha256"] == canonical_json_sha256(
        {key: value for key, value in tracked.items() if key != "summary_checksum_sha256"}
    )
