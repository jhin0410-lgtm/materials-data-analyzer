from __future__ import annotations

import copy

import pytest

from src.loaders.characterization_evidence_ladder import LEVELS, evaluate_evidence_ladder
from src.materials_data_analyzer.research_loop.characterization_evidence_gap import (
    CharacterizationEvidenceGapError,
    build_characterization_evidence_gap,
)


def _state(supported_through: int) -> tuple[dict[str, object], dict[str, object]]:
    levels = {}
    for index, name in enumerate(LEVELS):
        supported = index <= supported_through
        levels[name] = {
            "assessment": "Supported" if supported else "Unsupported",
            "evidence": [f"evidence for {name}"] if supported else [],
            "limitations": [] if supported else [f"missing {name}"],
        }
    declaration = {
        "schema_version": "1.0",
        "declaration_id": "case-1",
        "subject": {
            "modality": "saed",
            "source_material_domain": "Co3O4",
            "target_material_domain": "Co3O4",
            "claim_scope": "material_validation",
        },
        "source_bindings": [
            {"role": "source_manifest", "sha256": "a" * 64},
            {"role": "analysis_manifest", "sha256": "b" * 64},
            {"role": "comparability_matrix", "sha256": "c" * 64},
        ],
        "levels": levels,
        "limitations": [],
    }
    assessment = evaluate_evidence_ladder(declaration)
    handoff = assessment["handoff"]
    record = {
        "contract": handoff["contract"],
        "schema_version": "1.0",
        "policy_version": assessment["policy_version"],
        "assessment": {"path": "assessment.json", "sha256": "d" * 64, "size_bytes": 1},
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
    return record, assessment


def _build(supported_through: int) -> dict[str, object]:
    record, assessment = _state(supported_through)
    return build_characterization_evidence_gap(
        scientific_evidence_ladder=record,
        scientific_evidence_ladder_assessment=assessment,
        source_bundle_manifest_sha256="e" * 64,
    )


def test_l6_blocker_compiles_to_independent_replication_gap() -> None:
    artifact = _build(5)
    gap = artifact["evidence_gap"]
    assert gap["evidence_level"] == "L6_independent_external_validation"
    assert gap["action_class_hint"] == "replication"
    assert "independent external characterization validation dataset" in gap["requirement"]
    assert "leakage" in " ".join(gap["satisfaction_criteria"]).lower()
    assert artifact["scientific_status_promoted"] is False
    assert artifact["downstream_use_authorized"] is False
    assert artifact["automatic_execution_authorized"] is False


def test_l1_blocker_requests_raw_identity_and_provenance() -> None:
    artifact = _build(0)
    gap = artifact["evidence_gap"]
    assert gap["evidence_level"] == "L1_raw_representation_identity"
    assert gap["action_class_hint"] == "external_evidence_search"
    assert "raw or lossless" in gap["requirement"]
    assert "SHA-256" in gap["requirement"]


def test_l8_blocker_requests_engineering_validation_not_claim_promotion() -> None:
    artifact = _build(7)
    gap = artifact["evidence_gap"]
    assert gap["evidence_level"] == "L8_engineering_decision_readiness"
    assert gap["action_class_hint"] == "physical_experiment_design"
    assert "decision thresholds" in gap["requirement"]
    assert gap["scientific_status_promoted"] is False
    assert gap["automatic_execution_authorized"] is False


def test_fully_supported_ladder_has_no_fabricated_successor_gap() -> None:
    artifact = _build(8)
    assert artifact["highest_contiguous_supported_level"] == "L8_engineering_decision_readiness"
    assert artifact["first_blocking_level"] is None
    assert artifact["evidence_gap"] is None
    assert artifact["planning_metadata_only"] is True


def test_gap_hash_binds_source_and_assessment_identity() -> None:
    record, assessment = _state(5)
    first = build_characterization_evidence_gap(
        scientific_evidence_ladder=record,
        scientific_evidence_ladder_assessment=assessment,
        source_bundle_manifest_sha256="e" * 64,
    )
    second = build_characterization_evidence_gap(
        scientific_evidence_ladder=record,
        scientific_evidence_ladder_assessment=assessment,
        source_bundle_manifest_sha256="f" * 64,
    )
    assert first["canonical_sha256"] != second["canonical_sha256"]


def test_spliced_record_and_assessment_are_rejected() -> None:
    record, assessment = _state(5)
    changed = copy.deepcopy(record)
    changed["assessment_sha256"] = "f" * 64
    with pytest.raises(CharacterizationEvidenceGapError, match="assessment SHA differs"):
        build_characterization_evidence_gap(
            scientific_evidence_ladder=changed,
            scientific_evidence_ladder_assessment=assessment,
            source_bundle_manifest_sha256="e" * 64,
        )

    promoted = copy.deepcopy(record)
    promoted["downstream_use_authorized"] = True
    with pytest.raises(CharacterizationEvidenceGapError, match="must not authorize"):
        build_characterization_evidence_gap(
            scientific_evidence_ladder=promoted,
            scientific_evidence_ladder_assessment=assessment,
            source_bundle_manifest_sha256="e" * 64,
        )
