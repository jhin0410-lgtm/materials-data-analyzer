from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from src.loaders.characterization_evidence_ladder import (
    LEVELS,
    evaluate_evidence_ladder,
)
from src.loaders.characterization_features import REQUIRED_COLUMNS, sha256_file
from src.loaders.characterization_research_bundle import (
    consume_characterization_research_bundle,
    validate_characterization_research_bundle,
)


def _record(path: Path) -> dict[str, object]:
    return {
        "path": path.name,
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
    }


def _level(assessment: str) -> dict[str, object]:
    return {
        "assessment": assessment,
        "evidence": ["fixture evidence"] if assessment == "Supported" else [],
        "limitations": [] if assessment == "Supported" else ["fixture blocker"],
    }


def _write_bundle(
    root: Path,
    *,
    supported_through: int | None = 5,
    schema_version: str = "1.1",
    include_ladder: bool = True,
) -> Path:
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
                "source_file": "producer-local/raman.txt",
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
                "material": "Co3O4",
                "independence_group": "parent-1",
            }
        ]
    ).to_csv(context_path, index=False)
    source = root / "source_manifest.json"
    source.write_text(json.dumps({"source": "public", "raw_sha256": "a" * 64}) + "\n")
    analysis = root / "analysis_manifest.json"
    analysis.write_text(json.dumps({"analysis_count": 1}) + "\n")
    comparability = root / "comparability_matrix.csv"
    pd.DataFrame(
        [{"modality": "raman", "comparability_status": "not_established"}]
    ).to_csv(comparability, index=False)

    manifest: dict[str, object] = {
        "schema_version": schema_version,
        "bundle_type": "materials_characterization_feature_handoff",
        "case_id": "case-1",
        "producer": {
            "repository": "jhin0410-lgtm/materials-characterization-analyzer",
            "software_versions": ["test"],
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
            "source_manifest": _record(source),
            "analysis_manifest": _record(analysis),
            "comparability_matrix": _record(comparability),
        },
        "scientific_closeout": {
            "evidence_level": "Diagnostic",
            "strongest_evidence": "fixture interoperability",
            "primary_limitation": "fixture is not empirical validation",
            "suitable_for": ["software contract testing"],
            "unsuitable_for": ["scientific inference", "engineering release"],
        },
    }

    if include_ladder:
        levels = {}
        for index, name in enumerate(LEVELS):
            levels[name] = _level(
                "Supported"
                if supported_through is not None and index <= supported_through
                else "Unsupported"
            )
        evidence_records = manifest["evidence_references"]
        assert isinstance(evidence_records, dict)
        declaration = {
            "schema_version": "1.0",
            "declaration_id": "case-1",
            "subject": {
                "modality": "raman",
                "source_material_domain": "Co3O4",
                "target_material_domain": "Co3O4",
                "claim_scope": "material_validation",
            },
            "source_bindings": [
                {"role": role, "sha256": evidence_records[role]["sha256"]}
                for role in (
                    "source_manifest",
                    "analysis_manifest",
                    "comparability_matrix",
                )
            ],
            "levels": levels,
            "limitations": ["software fixture; not new empirical evidence"],
        }
        assessment = evaluate_evidence_ladder(declaration)
        assessment_path = root / "scientific_evidence_ladder_assessment.json"
        assessment_path.write_text(
            json.dumps(assessment, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        handoff = assessment["handoff"]
        manifest["scientific_evidence_ladder"] = {
            "contract": handoff["contract"],
            "schema_version": "1.0",
            "policy_version": assessment["policy_version"],
            "assessment": _record(assessment_path),
            "declaration_id": assessment["declaration"]["declaration_id"],
            "declaration_sha256": assessment["declaration_sha256"],
            "assessment_sha256": assessment["assessment_sha256"],
            "subject": handoff["subject"],
            "source_bindings": handoff["source_bindings"],
            "highest_contiguous_supported_level": assessment[
                "highest_contiguous_supported_level"
            ],
            "first_blocking_level": assessment["first_blocking_level"],
            "readiness": assessment["readiness"],
            "scientific_status_promoted": False,
            "downstream_use_authorized": False,
            "lower_level_evidence_preserved": True,
        }

    path = root / "characterization_handoff_bundle.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _refresh_ladder_file_record(manifest_path: Path) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    record = manifest["scientific_evidence_ladder"]
    assessment = manifest_path.parent / record["assessment"]["path"]
    record["assessment"] = _record(assessment)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


def test_schema_11_ladder_is_independently_replayed_and_consumed(tmp_path: Path) -> None:
    manifest = _write_bundle(tmp_path / "producer")

    bundle = validate_characterization_research_bundle(manifest)

    assert bundle.scientific_evidence_ladder is not None
    assert bundle.scientific_evidence_ladder["first_blocking_level"] == (
        "L6_independent_external_validation"
    )
    assert bundle.scientific_evidence_ladder_assessment is not None
    assert bundle.scientific_evidence_ladder_assessment["readiness"][
        "material_domain_validation_ready"
    ] is True
    assert bundle.scientific_evidence_ladder_assessment["readiness"][
        "independent_external_validation_ready"
    ] is False

    output = tmp_path / "consumer"
    outputs = consume_characterization_research_bundle(manifest, output)
    summary = json.loads(outputs["cross_repository_summary"].read_text(encoding="utf-8"))
    consumer_manifest = json.loads(
        outputs["cross_repository_manifest"].read_text(encoding="utf-8")
    )
    assert summary["producer_bundle"]["schema_version"] == "1.1"
    assert summary["producer_bundle"]["sha256"] == sha256_file(manifest)
    assert summary["scientific_evidence_ladder"]["independently_replayed"] is True
    assert summary["scientific_evidence_ladder"]["first_blocking_level"] == (
        "L6_independent_external_validation"
    )
    assert summary["scientific_evidence_ladder"]["scientific_status_promoted"] is False
    assert consumer_manifest["input_bundle"]["sha256"] == sha256_file(manifest)
    assert consumer_manifest["scientific_evidence_ladder"] == summary[
        "scientific_evidence_ladder"
    ]


def test_legacy_schema_10_remains_supported(tmp_path: Path) -> None:
    manifest = _write_bundle(
        tmp_path / "producer",
        schema_version="1.0",
        include_ladder=False,
    )
    bundle = validate_characterization_research_bundle(manifest)
    assert bundle.scientific_evidence_ladder is None
    assert bundle.manifest["schema_version"] == "1.0"


def test_schema_extension_is_version_gated(tmp_path: Path) -> None:
    with_ladder = _write_bundle(
        tmp_path / "with-ladder",
        schema_version="1.0",
        include_ladder=True,
    )
    with pytest.raises(ValueError, match="requires bundle schema_version 1.1"):
        validate_characterization_research_bundle(with_ladder)

    without_ladder = _write_bundle(
        tmp_path / "without-ladder",
        schema_version="1.1",
        include_ladder=False,
    )
    with pytest.raises(ValueError, match="requires scientific_evidence_ladder"):
        validate_characterization_research_bundle(without_ladder)


def test_assessment_byte_tamper_is_rejected(tmp_path: Path) -> None:
    manifest = _write_bundle(tmp_path / "producer")
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assessment_path = manifest.parent / payload["scientific_evidence_ladder"]["assessment"]["path"]
    assessment_path.write_text(assessment_path.read_text() + " ", encoding="utf-8")
    with pytest.raises(ValueError, match="checksum mismatch"):
        validate_characterization_research_bundle(manifest)


def test_rehashed_assessment_summary_substitution_is_rejected(tmp_path: Path) -> None:
    manifest = _write_bundle(tmp_path / "producer")
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assessment_path = manifest.parent / payload["scientific_evidence_ladder"]["assessment"]["path"]
    assessment = json.loads(assessment_path.read_text(encoding="utf-8"))
    assessment["handoff"]["first_blocking_level"] = "L7_replicated_multisource_support"
    assessment_path.write_text(json.dumps(assessment, indent=2, sort_keys=True) + "\n")
    _refresh_ladder_file_record(manifest)
    with pytest.raises(ValueError, match="deterministic replay"):
        validate_characterization_research_bundle(manifest)


def test_case_source_and_subject_substitutions_fail_closed(tmp_path: Path) -> None:
    case_manifest = _write_bundle(tmp_path / "case")
    payload = json.loads(case_manifest.read_text(encoding="utf-8"))
    payload["case_id"] = "different-case"
    case_manifest.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    with pytest.raises(ValueError, match="declaration_id must equal bundle case_id"):
        validate_characterization_research_bundle(case_manifest)

    source_manifest = _write_bundle(tmp_path / "source")
    payload = json.loads(source_manifest.read_text(encoding="utf-8"))
    payload["scientific_evidence_ladder"]["source_bindings"][0]["sha256"] = "f" * 64
    source_manifest.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    with pytest.raises(ValueError, match="manifest summary does not match"):
        validate_characterization_research_bundle(source_manifest)

    subject_manifest = _write_bundle(tmp_path / "subject")
    payload = json.loads(subject_manifest.read_text(encoding="utf-8"))
    payload["scientific_evidence_ladder"]["subject"]["modality"] = "tem"
    subject_manifest.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    with pytest.raises(ValueError, match="manifest summary does not match"):
        validate_characterization_research_bundle(subject_manifest)


def test_nonmonotonic_declaration_cannot_be_replayed(tmp_path: Path) -> None:
    manifest = _write_bundle(tmp_path / "producer")
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assessment_path = manifest.parent / payload["scientific_evidence_ladder"]["assessment"]["path"]
    assessment = json.loads(assessment_path.read_text(encoding="utf-8"))
    assessment["declaration"]["levels"]["L6_independent_external_validation"]["assessment"] = "Unsupported"
    assessment["declaration"]["levels"]["L7_replicated_multisource_support"]["assessment"] = "Supported"
    assessment["declaration"]["levels"]["L7_replicated_multisource_support"]["evidence"] = ["bad promotion"]
    assessment_path.write_text(json.dumps(assessment, indent=2, sort_keys=True) + "\n")
    _refresh_ladder_file_record(manifest)
    with pytest.raises(ValueError, match="cannot be Supported"):
        validate_characterization_research_bundle(manifest)
