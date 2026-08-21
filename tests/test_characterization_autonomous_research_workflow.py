from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from loaders.characterization_bundle import BUNDLE_TYPE
from loaders.characterization_evidence_ladder import (
    CharacterizationEvidenceLadderError,
    LEVELS,
    _evaluate_raw_declaration,
    validate_characterization_evidence_ladder,
)
from loaders.characterization_features import REQUIRED_COLUMNS, sha256_file
from materials_data_analyzer.characterization_research_workflow import (
    EVIDENCE_GAP_NAME,
    LADDER_STATE_NAME,
    consume_characterization_bundle_for_autonomous_research,
)
from materials_data_analyzer.research_loop.characterization_evidence_gap import (
    build_characterization_evidence_gap,
)

CASE_ID = "autonomous-characterization-case"


def _record(path: Path) -> dict[str, object]:
    return {
        "path": path.name,
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
    }


def _write_bundle(
    root: Path,
    *,
    supported_through: int | None = 4,
    declaration_id: str = CASE_ID,
    modality: str = "raman",
    wrong_binding_role: str | None = None,
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
                "case_id": CASE_ID,
                "material": "target-material",
            }
        ]
    ).to_csv(context_path, index=False)

    source_manifest = root / "source_manifest.json"
    source_manifest.write_text(
        json.dumps({"source": "public", "sha256": "a" * 64}) + "\n",
        encoding="utf-8",
    )
    analysis_manifest = root / "analysis_manifest.json"
    analysis_manifest.write_text(
        json.dumps({"schema_version": "1.0", "analysis_count": 1}) + "\n",
        encoding="utf-8",
    )
    comparability = root / "comparability_matrix.csv"
    pd.DataFrame(
        {"modality": ["raman"], "comparability_status": ["not_established"]}
    ).to_csv(comparability, index=False)

    manifest: dict[str, object] = {
        "schema_version": "1.1" if supported_through is not None else "1.0",
        "bundle_type": BUNDLE_TYPE,
        "case_id": CASE_ID,
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
            "strongest_evidence": "Checksum-bound characterization feature handoff.",
            "primary_limitation": "Higher scientific evidence levels remain open.",
            "suitable_for": ["descriptive characterization evidence integration"],
            "unsuitable_for": ["causal attribution", "engineering release"],
        },
    }

    if supported_through is not None:
        evidence_paths = {
            "source_manifest": source_manifest,
            "analysis_manifest": analysis_manifest,
            "comparability_matrix": comparability,
        }
        bindings = {
            role: sha256_file(path) for role, path in evidence_paths.items()
        }
        if wrong_binding_role is not None:
            bindings[wrong_binding_role] = "f" * 64
        raw_declaration = {
            "schema_version": "1.0",
            "declaration_id": declaration_id,
            "subject": {
                "modality": modality,
                "source_material_domain": "reference-material",
                "target_material_domain": "target-material",
                "claim_scope": "method_validation",
            },
            "source_bindings": [
                {"role": role, "sha256": bindings[role]}
                for role in sorted(bindings)
            ],
            "levels": {
                level: {
                    "assessment": "Supported" if index <= supported_through else "Unsupported",
                    "evidence": [f"verified {level}"] if index <= supported_through else [],
                    "limitations": [] if index <= supported_through else [f"open {level}"],
                }
                for index, level in enumerate(LEVELS)
            },
            "limitations": ["Maturity assessment does not authorize downstream use."],
        }
        assessment = _evaluate_raw_declaration(raw_declaration)
        assessment_path = root / "evidence_ladder_assessment.json"
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

    manifest_path = root / "characterization_handoff_bundle.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest_path


def _validate_ladder(manifest_path: Path) -> dict[str, object]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    evidence_paths = {
        name: manifest_path.parent / record["path"]
        for name, record in manifest["evidence_references"].items()
    }
    state = validate_characterization_evidence_ladder(
        manifest=manifest,
        bundle_root=manifest_path.parent,
        evidence_paths=evidence_paths,
        instruments=["raman"],
    )
    assert state is not None
    return state


def test_consumer_replays_l4_and_maps_l5_target_material_gap(tmp_path: Path) -> None:
    state = _validate_ladder(_write_bundle(tmp_path / "producer", supported_through=4))

    assert state["highest_contiguous_supported_level"] == "L4_method_algorithm_validation"
    assert state["first_blocking_level"] == "L5_material_domain_validation"
    assert state["assessment_replayed"] is True
    assert state["case_id_bound"] is True
    assert state["source_digests_bound"] is True
    assert state["subject_modality_bound"] is True

    gap = build_characterization_evidence_gap(state)
    assert gap["status"] == "open_characterization_evidence_gap"
    assert gap["gap"]["requirement_code"] == "validate_target_material_domain"
    assert gap["gap"]["suggested_action_class"] == (
        "characterization_target_material_validation"
    )
    assert gap["planning_boundary"]["action_execution_authorized"] is False
    assert gap["planning_boundary"]["scientific_status_promoted"] is False
    assert len(gap["artifact_sha256"]) == 64


def test_consumer_maps_l6_to_independent_external_validation(tmp_path: Path) -> None:
    state = _validate_ladder(_write_bundle(tmp_path / "producer", supported_through=5))
    gap = build_characterization_evidence_gap(state)

    assert state["first_blocking_level"] == "L6_independent_external_validation"
    assert gap["gap"]["requirement_code"] == "acquire_independent_external_validation"
    assert gap["gap"]["suggested_action_class"] == (
        "characterization_independent_validation_acquisition"
    )


def test_public_workflow_persists_ladder_and_gap_without_authorization(tmp_path: Path) -> None:
    manifest_path = _write_bundle(tmp_path / "producer", supported_through=4)
    output = tmp_path / "consumer"

    outputs = consume_characterization_bundle_for_autonomous_research(
        manifest_path,
        output,
    )

    assert outputs["characterization_evidence_ladder_state"].name == LADDER_STATE_NAME
    assert outputs["characterization_research_evidence_gap"].name == EVIDENCE_GAP_NAME
    gap = json.loads((output / EVIDENCE_GAP_NAME).read_text(encoding="utf-8"))
    assert gap["gap"]["blocking_level"] == "L5_material_domain_validation"
    assert gap["planning_boundary"]["action_execution_authorized"] is False
    summary = json.loads(
        outputs["cross_repository_summary"].read_text(encoding="utf-8")
    )
    architecture = summary["autonomous_research_scientist"]
    assert architecture["planning_boundary"][
        "existing_research_loop_authorization_required"
    ] is True
    consumer_manifest = json.loads(
        outputs["cross_repository_manifest"].read_text(encoding="utf-8")
    )
    assert consumer_manifest["output_sha256"][
        "characterization_research_evidence_gap"
    ] == sha256_file(output / EVIDENCE_GAP_NAME)


def test_legacy_bundle_without_ladder_remains_descriptively_consumable(tmp_path: Path) -> None:
    manifest_path = _write_bundle(tmp_path / "producer", supported_through=None)
    outputs = consume_characterization_bundle_for_autonomous_research(
        manifest_path,
        tmp_path / "consumer",
    )

    ladder_state = json.loads(
        outputs["characterization_evidence_ladder_state"].read_text(encoding="utf-8")
    )
    assert ladder_state["present"] is False
    assert "characterization_research_evidence_gap" not in outputs


def test_case_source_and_modality_substitution_fail_before_outputs(tmp_path: Path) -> None:
    case_manifest = _write_bundle(
        tmp_path / "case",
        declaration_id="different-case",
    )
    with pytest.raises(CharacterizationEvidenceLadderError, match="declaration_id"):
        consume_characterization_bundle_for_autonomous_research(
            case_manifest,
            tmp_path / "case-consumer",
        )
    assert not (tmp_path / "case-consumer").exists()

    source_manifest = _write_bundle(
        tmp_path / "source",
        wrong_binding_role="comparability_matrix",
    )
    with pytest.raises(CharacterizationEvidenceLadderError, match="source binding mismatch"):
        consume_characterization_bundle_for_autonomous_research(
            source_manifest,
            tmp_path / "source-consumer",
        )
    assert not (tmp_path / "source-consumer").exists()

    modality_manifest = _write_bundle(tmp_path / "modality", modality="xrd")
    with pytest.raises(CharacterizationEvidenceLadderError, match="subject.modality"):
        consume_characterization_bundle_for_autonomous_research(
            modality_manifest,
            tmp_path / "modality-consumer",
        )
    assert not (tmp_path / "modality-consumer").exists()


def test_assessment_and_manifest_summary_tampering_fail_closed(tmp_path: Path) -> None:
    assessment_manifest = _write_bundle(tmp_path / "assessment")
    assessment_path = assessment_manifest.parent / "evidence_ladder_assessment.json"
    assessment_path.write_text(
        assessment_path.read_text(encoding="utf-8") + " ",
        encoding="utf-8",
    )
    with pytest.raises(CharacterizationEvidenceLadderError, match="checksum mismatch"):
        consume_characterization_bundle_for_autonomous_research(
            assessment_manifest,
            tmp_path / "assessment-consumer",
        )

    summary_manifest = _write_bundle(tmp_path / "summary")
    manifest = json.loads(summary_manifest.read_text(encoding="utf-8"))
    manifest["scientific_evidence_ladder"]["first_blocking_level"] = (
        "L8_engineering_decision_readiness"
    )
    summary_manifest.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(CharacterizationEvidenceLadderError, match="manifest summary"):
        consume_characterization_bundle_for_autonomous_research(
            summary_manifest,
            tmp_path / "summary-consumer",
        )
