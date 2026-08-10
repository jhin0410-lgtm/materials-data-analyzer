from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from loaders.characterization_bundle import BUNDLE_TYPE, MANIFEST_NAME, REPORT_NAME, SUMMARY_NAME
from loaders.characterization_features import REQUIRED_COLUMNS, sha256_file
from materials_data_analyzer.characterization_use_policy import (
    CharacterizationUsePolicyError,
    consume_characterization_bundle_for_use,
    evaluate_characterization_use,
)


def _record(path: Path) -> dict[str, object]:
    return {
        "path": path.name,
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
    }


def _policy(maximum: str = "descriptive") -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "maximum_allowed_use": maximum,
        "feature_stage": "derived",
        "evidence_level": "Diagnostic",
        "review_status": "reviewed",
        "independence_group_field": (
            "parent_specimen_id" if maximum == "association" else None
        ),
        "measurement_timing": "unknown",
        "causal_design_validated": False,
        "operational_validation_validated": False,
        "limitations": ["Diagnostic case for contract validation only."],
    }


def _write_valid_bundle(root: Path, *, policy: dict[str, object] | None) -> Path:
    root.mkdir(parents=True)
    feature_path = root / "characterization_features_long.csv"
    pd.DataFrame(
        [
            {
                "sample_id": "sample-a",
                "measurement_id": "sample-a-raman",
                "instrument": "raman",
                "feature_name": "candidate_count",
                "feature_label": None,
                "value": 2.0,
                "unit": "count",
                "method": "diagnostic_peak_detection",
                "source_file": "raman.txt",
                "source_sha256": "a" * 64,
                "preprocessing_id": "raman-preprocessing-v1",
                "quality_flag": "review_required",
            }
        ],
        columns=REQUIRED_COLUMNS,
    ).to_csv(feature_path, index=False)

    context_path = root / "sample_context.csv"
    pd.DataFrame(
        [
            {
                "sample_id": "sample-a",
                "parent_specimen_id": "parent-1",
                "material": "diagnostic material",
            }
        ]
    ).to_csv(context_path, index=False)

    source_manifest = root / "source.json"
    source_manifest.write_text('{"source":"public"}\n', encoding="utf-8")
    analysis_manifest = root / "analysis.json"
    analysis_manifest.write_text('{"analysis_count":1}\n', encoding="utf-8")
    comparability = root / "comparability.csv"
    pd.DataFrame(
        {"modality": ["raman"], "comparability_status": ["not_established"]}
    ).to_csv(comparability, index=False)

    manifest: dict[str, object] = {
        "schema_version": "1.0",
        "bundle_type": BUNDLE_TYPE,
        "case_id": "gated-characterization-test",
        "producer": {
            "repository": "jhin0410-lgtm/materials-characterization-analyzer",
            "software_versions": ["0.11.0"],
            "analysis_result_schema_versions": ["1.0"],
        },
        "join_contract": {
            "join_key": "sample_id",
            "row_order_join_allowed": False,
            "aggregation_performed": False,
            "missing_metadata_inferred": False,
        },
        "feature_table": {
            **_record(feature_path),
            "columns": REQUIRED_COLUMNS,
            "row_count": 1,
            "sample_count": 1,
            "measurement_count": 1,
            "instruments": ["raman"],
            "quality_flag_counts": {"review_required": 1},
            "source_sha256_record_count": 1,
            "preprocessing_id_record_count": 1,
        },
        "sample_context": {
            **_record(context_path),
            "columns": pd.read_csv(context_path).columns.tolist(),
            "row_count": 1,
        },
        "evidence_references": {
            "source_manifest": _record(source_manifest),
            "analysis_manifest": _record(analysis_manifest),
            "comparability_matrix": _record(comparability),
        },
        "scientific_closeout": {
            "evidence_level": "Diagnostic",
            "strongest_evidence": "Stable IDs and source hashes are preserved.",
            "primary_limitation": "No independent scientific validation.",
            "suitable_for": ["descriptive integration"],
            "unsuitable_for": ["predictive or engineering decisions"],
        },
    }
    if policy is not None:
        manifest["downstream_use_policy"] = policy
    manifest_path = root / "characterization_handoff_bundle.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest_path


def _write_process(
    path: Path,
    *,
    parent_specimen_id: str | None,
) -> Path:
    row: dict[str, object] = {
        "sample_id": "sample-a",
        "material": "diagnostic material",
        "process_temperature_c": 750.0,
    }
    if parent_specimen_id is not None:
        row["parent_specimen_id"] = parent_specimen_id
    pd.DataFrame([row]).to_csv(path, index=False)
    return path


def test_public_workflow_records_eligibility_in_all_audit_outputs(tmp_path: Path) -> None:
    manifest = _write_valid_bundle(
        tmp_path / "producer",
        policy=_policy(),
    )
    output = tmp_path / "consumer"

    outputs = consume_characterization_bundle_for_use(
        manifest,
        output,
        requested_use="descriptive",
    )

    eligibility = json.loads(outputs["use_eligibility"].read_text(encoding="utf-8"))
    summary = json.loads((output / SUMMARY_NAME).read_text(encoding="utf-8"))
    consumer_manifest = json.loads((output / MANIFEST_NAME).read_text(encoding="utf-8"))
    report = (output / REPORT_NAME).read_text(encoding="utf-8")

    assert eligibility["allowed"] is True
    assert eligibility["split_group_binding"]["source"] == "not_required"
    assert summary["downstream_use_eligibility"]["requested_use"] == "descriptive"
    assert consumer_manifest["downstream_use_eligibility"]["allowed"] is True
    assert "Downstream Use Eligibility" in report
    for name, filename in consumer_manifest["outputs"].items():
        assert consumer_manifest["output_sha256"][name] == sha256_file(
            output / filename
        )


def test_association_requires_matching_independent_split_group(tmp_path: Path) -> None:
    manifest = _write_valid_bundle(
        tmp_path / "producer",
        policy=_policy("association"),
    )

    missing = evaluate_characterization_use(
        manifest,
        requested_use="association",
    )
    mismatch = evaluate_characterization_use(
        manifest,
        requested_use="association",
        split_group_field="sample_id",
    )
    allowed = evaluate_characterization_use(
        manifest,
        requested_use="association",
        split_group_field="parent_specimen_id",
    )

    assert missing.allowed is False
    assert "association or stronger use requires --split-group-field" in missing.reasons
    assert mismatch.allowed is False
    assert allowed.allowed is True


def test_external_process_cannot_redefine_independence_group(tmp_path: Path) -> None:
    manifest = _write_valid_bundle(
        tmp_path / "producer",
        policy=_policy("association"),
    )
    process = _write_process(
        tmp_path / "process.csv",
        parent_specimen_id="consumer-redefined-parent",
    )
    output = tmp_path / "consumer"

    with pytest.raises(ValueError, match="attempts to redefine.*parent_specimen_id"):
        consume_characterization_bundle_for_use(
            manifest,
            output,
            process_table_path=process,
            requested_use="association",
            split_group_field="parent_specimen_id",
        )

    assert not output.exists()


def test_matching_external_independence_group_is_checksum_bound(tmp_path: Path) -> None:
    manifest = _write_valid_bundle(
        tmp_path / "producer",
        policy=_policy("association"),
    )
    process = _write_process(tmp_path / "process.csv", parent_specimen_id="parent-1")
    output = tmp_path / "consumer"

    outputs = consume_characterization_bundle_for_use(
        manifest,
        output,
        process_table_path=process,
        requested_use="association",
        split_group_field="parent_specimen_id",
    )

    eligibility = json.loads(outputs["use_eligibility"].read_text(encoding="utf-8"))
    binding = eligibility["split_group_binding"]
    assert binding == {
        "required": True,
        "field": "parent_specimen_id",
        "source": "external_process_matches_bundle_context",
        "external_values_compared": True,
        "mismatch_count": 0,
        "sample_count": 1,
    }


def test_missing_external_independence_group_is_injected_from_bundle(tmp_path: Path) -> None:
    manifest = _write_valid_bundle(
        tmp_path / "producer",
        policy=_policy("association"),
    )
    process = _write_process(tmp_path / "process.csv", parent_specimen_id=None)
    output = tmp_path / "consumer"

    outputs = consume_characterization_bundle_for_use(
        manifest,
        output,
        process_table_path=process,
        requested_use="association",
        split_group_field="parent_specimen_id",
    )

    eligibility = json.loads(outputs["use_eligibility"].read_text(encoding="utf-8"))
    assert eligibility["split_group_binding"]["source"] == "bundle_context_injected"
    validated_process = pd.read_csv(outputs["validated_process_input"])
    assert validated_process.loc[0, "parent_specimen_id"] == "parent-1"


def test_blocked_association_creates_no_output(tmp_path: Path) -> None:
    manifest = _write_valid_bundle(
        tmp_path / "producer",
        policy=_policy("association"),
    )
    output = tmp_path / "consumer"

    with pytest.raises(CharacterizationUsePolicyError, match="blocked"):
        consume_characterization_bundle_for_use(
            manifest,
            output,
            requested_use="association",
        )

    assert not output.exists()


def test_duplicate_manifest_keys_are_rejected(tmp_path: Path) -> None:
    manifest = tmp_path / "characterization_handoff_bundle.json"
    manifest.write_text(
        '{"scientific_closeout":{"evidence_level":"Diagnostic"},'
        '"downstream_use_policy":null,"downstream_use_policy":null}',
        encoding="utf-8",
    )

    with pytest.raises(CharacterizationUsePolicyError, match="duplicate JSON key"):
        evaluate_characterization_use(manifest)
