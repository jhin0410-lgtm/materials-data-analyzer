from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

import pandas as pd
import pytest

from loaders.characterization_bundle import (
    consume_characterization_bundle,
    validate_characterization_bundle,
)
from loaders.characterization_evidence_ladder import (
    LADDER_HANDOFF_CONTRACT,
    LADDER_RECORD_SCHEMA_VERSION,
    LEVELS,
    evaluate_scientific_evidence_ladder,
)


COLUMNS = [
    "sample_id",
    "measurement_id",
    "instrument",
    "feature_name",
    "feature_label",
    "value",
    "unit",
    "method",
    "source_file",
    "source_sha256",
    "preprocessing_id",
    "quality_flag",
]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _record(path: Path) -> dict[str, object]:
    return {
        "path": path.name,
        "sha256": _sha(path),
        "size_bytes": path.stat().st_size,
    }


def _write_bundle(tmp_path: Path, *, with_ladder: bool) -> Path:
    feature_path = tmp_path / "characterization_features_long.csv"
    context_path = tmp_path / "sample_context.csv"
    source_path = tmp_path / "source_manifest.json"
    analysis_path = tmp_path / "analysis_manifest.json"
    matrix_path = tmp_path / "comparability_matrix.csv"

    feature = {
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
    table = pd.DataFrame([feature], columns=COLUMNS)
    table.to_csv(feature_path, index=False, lineterminator="\n")
    context = pd.DataFrame(
        [
            {
                "sample_id": "sample-a",
                "case_id": "case-1",
                "material": "target-material",
            }
        ]
    )
    context.to_csv(context_path, index=False, lineterminator="\n")
    source_path.write_text(
        json.dumps({"source": "public", "sha256": "a" * 64}) + "\n",
        encoding="utf-8",
    )
    analysis_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "analysis_count": 1,
                "analyses": [
                    {
                        "schema_version": "1.0",
                        "software_version": "0.10.0",
                        "features": [feature],
                    }
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    pd.DataFrame(
        {"sample_id": ["sample-a"], "modality": ["raman"]}
    ).to_csv(matrix_path, index=False, lineterminator="\n")

    feature_record = {
        **_record(feature_path),
        "columns": COLUMNS,
        "row_count": 1,
        "sample_count": 1,
        "measurement_count": 1,
        "instruments": ["raman"],
        "quality_flag_counts": dict(Counter(["review_required"])),
        "source_sha256_record_count": 1,
        "preprocessing_id_record_count": 1,
    }
    manifest: dict[str, object] = {
        "schema_version": "1.1" if with_ladder else "1.0",
        "bundle_type": "materials_characterization_feature_handoff",
        "case_id": "case-1",
        "producer": {
            "repository": "jhin0410-lgtm/materials-characterization-analyzer",
            "software_versions": ["0.10.0"],
            "analysis_result_schema_versions": ["1.0"],
        },
        "join_contract": {
            "join_key": "sample_id",
            "row_order_join_allowed": False,
            "aggregation_performed": False,
            "missing_metadata_inferred": False,
        },
        "feature_table": feature_record,
        "sample_context": {
            **_record(context_path),
            "columns": context.columns.tolist(),
            "row_count": 1,
        },
        "evidence_references": {
            "source_manifest": _record(source_path),
            "analysis_manifest": _record(analysis_path),
            "comparability_matrix": _record(matrix_path),
        },
        "scientific_closeout": {
            "evidence_level": "Diagnostic",
            "strongest_evidence": "Method path is reproducible.",
            "primary_limitation": "Target-material validation remains open.",
            "suitable_for": ["descriptive characterization review"],
            "unsuitable_for": ["engineering release"],
        },
    }

    if with_ladder:
        manifest["evidence_identity_binding_contract"] = {
            "schema_version": "1.0",
            "required": True,
        }
        levels: dict[str, dict[str, object]] = {}
        for index, level in enumerate(LEVELS):
            supported = index <= 4
            levels[level] = {
                "assessment": "Supported" if supported else "Unsupported",
                "evidence": [f"verified {level}"] if supported else [],
                "limitations": [] if supported else [f"missing {level}"],
            }
        assessment = evaluate_scientific_evidence_ladder(
            {
                "schema_version": "1.0",
                "declaration_id": "case-1",
                "subject": {
                    "modality": "raman",
                    "source_material_domain": "reference-material",
                    "target_material_domain": "target-material",
                    "claim_scope": "method_validation",
                },
                "source_bindings": [
                    {"role": "source_manifest", "sha256": _sha(source_path)},
                    {"role": "analysis_manifest", "sha256": _sha(analysis_path)},
                    {"role": "comparability_matrix", "sha256": _sha(matrix_path)},
                ],
                "levels": levels,
                "limitations": ["maturity metadata only"],
            }
        )
        ladder_path = tmp_path / "scientific_evidence_ladder_assessment.json"
        ladder_path.write_text(
            json.dumps(assessment, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        declaration = assessment["declaration"]
        handoff = assessment["handoff"]
        assert isinstance(declaration, dict)
        assert isinstance(handoff, dict)
        manifest["scientific_evidence_ladder"] = {
            "contract": LADDER_HANDOFF_CONTRACT,
            "schema_version": LADDER_RECORD_SCHEMA_VERSION,
            "policy_version": assessment["policy_version"],
            "assessment": _record(ladder_path),
            "declaration_id": declaration["declaration_id"],
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

    manifest_path = tmp_path / "characterization_handoff_bundle.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest_path


def test_schema_11_bundle_exposes_independently_verified_ladder(tmp_path: Path) -> None:
    manifest = _write_bundle(tmp_path, with_ladder=True)

    bundle = validate_characterization_bundle(manifest)

    assert bundle.manifest["schema_version"] == "1.1"
    assert bundle.evidence_identity_binding["semantic_identity_binding_verified"] is True
    assert bundle.scientific_evidence_ladder is not None
    assert bundle.scientific_evidence_ladder["first_blocking_level"] == (
        "L5_material_domain_validation"
    )
    assert bundle.scientific_evidence_ladder["contract"] == LADDER_HANDOFF_CONTRACT
    assert bundle.scientific_evidence_ladder_binding == {
        "case_id_bound": True,
        "required_source_roles": [
            "analysis_manifest",
            "comparability_matrix",
            "source_manifest",
        ],
        "source_digests_bound": True,
        "subject_modality_bound": True,
        "bundle_instruments": ["raman"],
    }


def test_schema_11_ladder_requires_semantic_evidence_identity_binding(tmp_path: Path) -> None:
    manifest_path = _write_bundle(tmp_path, with_ladder=True)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.pop("evidence_identity_binding_contract")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="require evidence_identity_binding_contract"):
        validate_characterization_bundle(manifest_path)


def test_schema_10_bundle_remains_legacy_compatible(tmp_path: Path) -> None:
    manifest = _write_bundle(tmp_path, with_ladder=False)

    bundle = validate_characterization_bundle(manifest)

    assert bundle.manifest["schema_version"] == "1.0"
    assert bundle.scientific_evidence_ladder is None
    assert bundle.scientific_evidence_ladder_binding is None


def test_schema_11_consumer_outputs_preserve_verified_ladder(tmp_path: Path) -> None:
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir()
    manifest = _write_bundle(bundle_dir, with_ladder=True)
    output = tmp_path / "consumer-output"

    outputs = consume_characterization_bundle(manifest, output)
    summary = json.loads(outputs["cross_repository_summary"].read_text(encoding="utf-8"))
    consumer_manifest = json.loads(
        outputs["cross_repository_manifest"].read_text(encoding="utf-8")
    )

    assert summary["scientific_evidence_ladder"]["first_blocking_level"] == (
        "L5_material_domain_validation"
    )
    assert summary["software_validation"][
        "scientific_evidence_ladder_independently_replayed"
    ] is True
    assert summary["software_validation"][
        "scientific_evidence_ladder_authorized_downstream_use"
    ] is False
    assert consumer_manifest["scientific_evidence_ladder"] == summary[
        "scientific_evidence_ladder"
    ]


def test_schema_10_cannot_smuggle_ladder_field(tmp_path: Path) -> None:
    manifest_path = _write_bundle(tmp_path, with_ladder=True)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["schema_version"] = "1.0"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="1.0 must not contain"):
        validate_characterization_bundle(manifest_path)


def test_schema_11_requires_ladder_field(tmp_path: Path) -> None:
    manifest_path = _write_bundle(tmp_path, with_ladder=False)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["schema_version"] = "1.1"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="1.1 requires"):
        validate_characterization_bundle(manifest_path)
