from __future__ import annotations

import copy
import json
from pathlib import Path

import pandas as pd
import pytest

from src.loaders.characterization_bundle import (
    BUNDLE_TYPE,
    EVIDENCE_LADDER_BUNDLE_SCHEMA_VERSION,
    SUMMARY_NAME,
    consume_characterization_bundle,
    validate_characterization_bundle,
)
from src.loaders.characterization_evidence_ladder import (
    LEVELS,
    evaluate_characterization_evidence_ladder,
)
from src.loaders.characterization_features import REQUIRED_COLUMNS, sha256_file
from src.materials_data_analyzer.research_loop.characterization_evidence_gap import (
    build_characterization_evidence_gap,
)


def _record(path: Path) -> dict[str, object]:
    return {
        "path": path.name,
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
    }


def _write_bundle(root: Path) -> Path:
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
        [{"sample_id": "sample-a", "material": "Co3O4"}]
    ).to_csv(context_path, index=False)

    source_manifest = root / "source_manifest.json"
    source_manifest.write_text(json.dumps({"source": "public", "sha256": "a" * 64}), encoding="utf-8")
    analysis_manifest = root / "analysis_manifest.json"
    analysis_manifest.write_text(json.dumps({"analysis_count": 1}), encoding="utf-8")
    comparability = root / "comparability_matrix.csv"
    pd.DataFrame(
        {"modality": ["raman"], "comparability_status": ["not_established"]}
    ).to_csv(comparability, index=False)

    manifest = {
        "schema_version": "1.0",
        "bundle_type": BUNDLE_TYPE,
        "case_id": "characterization-ladder-consumer-case",
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
            "columns": ["sample_id", "material"],
            "row_count": 1,
        },
        "evidence_references": {
            "source_manifest": _record(source_manifest),
            "analysis_manifest": _record(analysis_manifest),
            "comparability_matrix": _record(comparability),
        },
        "scientific_closeout": {
            "evidence_level": "Diagnostic",
            "suitable_for": ["contract validation"],
            "unsuitable_for": ["engineering release"],
        },
    }
    path = root / "characterization_handoff_bundle.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _level(assessment: str) -> dict[str, object]:
    return {
        "assessment": assessment,
        "evidence": ["verified evidence"] if assessment == "Supported" else [],
        "limitations": [],
    }


def _attach_ladder(manifest_path: Path, *, supported_through: int) -> dict[str, object]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    declaration = {
        "schema_version": "1.0",
        "declaration_id": manifest["case_id"],
        "subject": {
            "modality": "raman",
            "source_material_domain": "Co3O4",
            "target_material_domain": "Co3O4",
            "claim_scope": "material_validation",
        },
        "source_bindings": [
            {
                "role": role,
                "sha256": manifest["evidence_references"][role]["sha256"],
            }
            for role in ("source_manifest", "analysis_manifest", "comparability_matrix")
        ],
        "levels": {
            level: _level("Supported" if index <= supported_through else "Unsupported")
            for index, level in enumerate(LEVELS)
        },
        "limitations": [],
    }
    assessment = evaluate_characterization_evidence_ladder(declaration)
    assessment_path = manifest_path.parent / "scientific_evidence_ladder_assessment.json"
    assessment_path.write_text(
        json.dumps(assessment, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    manifest["schema_version"] = EVIDENCE_LADDER_BUNDLE_SCHEMA_VERSION
    manifest["scientific_evidence_ladder"] = {
        "contract": "materials-characterization-scientific-evidence-ladder",
        "schema_version": "1.0",
        "policy_version": assessment["policy_version"],
        "assessment": _record(assessment_path),
        "declaration_id": assessment["declaration"]["declaration_id"],
        "declaration_sha256": assessment["declaration_sha256"],
        "assessment_sha256": assessment["assessment_sha256"],
        "subject": assessment["handoff"]["subject"],
        "source_bindings": assessment["handoff"]["source_bindings"],
        "highest_contiguous_supported_level": assessment[
            "highest_contiguous_supported_level"
        ],
        "first_blocking_level": assessment["first_blocking_level"],
        "readiness": assessment["readiness"],
        "scientific_status_promoted": False,
        "downstream_use_authorized": False,
        "lower_level_evidence_preserved": True,
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return assessment


def test_legacy_schema_1_0_remains_valid_without_ladder(tmp_path: Path) -> None:
    manifest = _write_bundle(tmp_path / "bundle")
    validated = validate_characterization_bundle(manifest)
    assert validated.evidence_ladder_path is None
    assert validated.evidence_ladder_record is None
    assert validated.evidence_ladder_assessment is None


def test_schema_1_1_independently_replays_ladder_and_exports_state(tmp_path: Path) -> None:
    manifest = _write_bundle(tmp_path / "bundle")
    expected = _attach_ladder(manifest, supported_through=5)

    validated = validate_characterization_bundle(manifest)
    assert validated.evidence_ladder_path is not None
    assert validated.evidence_ladder_assessment == expected
    assert validated.evidence_ladder_assessment["first_blocking_level"] == (
        "L6_independent_external_validation"
    )
    assert validated.evidence_ladder_record["scientific_status_promoted"] is False
    assert validated.evidence_ladder_record["downstream_use_authorized"] is False

    output = tmp_path / "consumer"
    consume_characterization_bundle(manifest, output)
    summary = json.loads((output / SUMMARY_NAME).read_text(encoding="utf-8"))
    assert summary["scientific_evidence_ladder"]["present"] is True
    assert summary["scientific_evidence_ladder"]["verified"] is True
    assert summary["scientific_evidence_ladder"]["assessment"][
        "assessment_sha256"
    ] == expected["assessment_sha256"]
    assert summary["software_validation"][
        "scientific_evidence_ladder_independently_replayed"
    ] is True


def test_l6_blocker_becomes_deterministic_external_validation_gap(tmp_path: Path) -> None:
    manifest = _write_bundle(tmp_path / "bundle")
    _attach_ladder(manifest, supported_through=5)
    assessment = validate_characterization_bundle(manifest).evidence_ladder_assessment
    assert assessment is not None

    first = build_characterization_evidence_gap(
        bundle_manifest_path=manifest,
        ladder_assessment=assessment,
    )
    second = build_characterization_evidence_gap(
        bundle_manifest_path=manifest,
        ladder_assessment=assessment,
    )
    assert first == second
    assert first["first_blocking_level"] == "L6_independent_external_validation"
    assert first["suggested_action_class"] == (
        "characterization_independent_external_validation"
    )
    assert "independent external validation set" in first["next_evidence_requirement"]
    assert first["scientific_status_promoted"] is False
    assert first["empirical_evidence_created"] is False
    assert first["downstream_use_authorized"] is False


def test_complete_ladder_has_no_maturity_gap_but_grants_no_authority(tmp_path: Path) -> None:
    manifest = _write_bundle(tmp_path / "bundle")
    _attach_ladder(manifest, supported_through=8)
    assessment = validate_characterization_bundle(manifest).evidence_ladder_assessment
    assert assessment is not None
    gap = build_characterization_evidence_gap(
        bundle_manifest_path=manifest,
        ladder_assessment=assessment,
    )
    assert gap["status"] == "no_unresolved_characterization_maturity_blocker"
    assert gap["first_blocking_level"] is None
    assert gap["suggested_action_class"] is None
    assert gap["downstream_use_authorized"] is False


def test_schema_version_and_ladder_presence_are_fail_closed(tmp_path: Path) -> None:
    manifest = _write_bundle(tmp_path / "bundle")
    _attach_ladder(manifest, supported_through=5)
    payload = json.loads(manifest.read_text(encoding="utf-8"))

    legacy_with_ladder = copy.deepcopy(payload)
    legacy_with_ladder["schema_version"] = "1.0"
    manifest.write_text(json.dumps(legacy_with_ladder), encoding="utf-8")
    with pytest.raises(ValueError, match="schema-1.0.*must not contain"):
        validate_characterization_bundle(manifest)

    v11_without_ladder = copy.deepcopy(payload)
    v11_without_ladder.pop("scientific_evidence_ladder")
    manifest.write_text(json.dumps(v11_without_ladder), encoding="utf-8")
    with pytest.raises(ValueError, match="schema-1.1.*requires"):
        validate_characterization_bundle(manifest)


def test_ladder_artifact_tamper_and_manifest_summary_substitution_fail_closed(
    tmp_path: Path,
) -> None:
    manifest = _write_bundle(tmp_path / "bundle")
    _attach_ladder(manifest, supported_through=5)
    clean_manifest = json.loads(manifest.read_text(encoding="utf-8"))
    assessment_path = manifest.parent / "scientific_evidence_ladder_assessment.json"
    clean_assessment_text = assessment_path.read_text(encoding="utf-8")

    assessment = json.loads(clean_assessment_text)
    assessment["declaration"]["limitations"].append("post-hoc mutation")
    assessment_path.write_text(json.dumps(assessment), encoding="utf-8")
    with pytest.raises(ValueError, match="checksum mismatch"):
        validate_characterization_bundle(manifest)

    assessment_path.write_text(clean_assessment_text, encoding="utf-8")
    substituted = copy.deepcopy(clean_manifest)
    substituted["scientific_evidence_ladder"]["first_blocking_level"] = (
        "L7_replicated_multisource_support"
    )
    manifest.write_text(json.dumps(substituted), encoding="utf-8")
    with pytest.raises(ValueError, match="manifest summary does not match"):
        validate_characterization_bundle(manifest)


def test_replayed_assessment_rejects_nonmonotonic_supported_level(tmp_path: Path) -> None:
    manifest = _write_bundle(tmp_path / "bundle")
    _attach_ladder(manifest, supported_through=4)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assessment_path = manifest.parent / "scientific_evidence_ladder_assessment.json"
    assessment = json.loads(assessment_path.read_text(encoding="utf-8"))
    assessment["declaration"]["levels"]["L6_independent_external_validation"][
        "assessment"
    ] = "Supported"
    assessment["declaration"]["levels"]["L6_independent_external_validation"][
        "evidence"
    ] = ["invalid skipped-level support"]
    assessment_path.write_text(json.dumps(assessment), encoding="utf-8")
    payload["scientific_evidence_ladder"]["assessment"] = _record(assessment_path)
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="cannot be Supported"):
        validate_characterization_bundle(manifest)
