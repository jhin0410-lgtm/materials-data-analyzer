from __future__ import annotations

import copy

import pytest

from materials_data_analyzer.research_loop.delimited_structural_intake import (
    inspect_delimited_structure,
)
from materials_data_analyzer.research_loop.generic_semantic_lineage_proposal import (
    build_generic_semantic_lineage_proposal,
)
from materials_data_analyzer.research_loop.reviewed_resolution_compiler import (
    ReviewedResolutionCompilerError,
    build_reviewed_resolution_contract,
    compile_reviewed_resolution,
    verify_reviewed_resolution_contract,
)
from materials_data_analyzer.research_loop.scientific_review_release import (
    build_review_decision,
)


BODY = (
    b"sample_id,acquisition_id,value,uncertainty,lab_id,lot_id,build_id\n"
    b"s1,a1,1.20,0.10,lab-a,lot-1,build-1\n"
    b"s2,a2,1.40,0.20,lab-a,lot-1,build-2\n"
)


def _structure():
    return inspect_delimited_structure(BODY)


def _proposal(structure):
    return build_generic_semantic_lineage_proposal(
        candidate_id="candidate:generic-reviewed-resolution",
        structure=structure,
    )


def _semantic_resolution():
    return {
        "source_id": "source:reviewed-generic-fixture",
        "material": {
            "kind": "identity",
            "material_name": "Example Alloy",
            "declared_identifier": "EXAMPLE-ALLOY",
            "identity_basis": "source_declared_label",
        },
        "sample_id_column": 0,
        "sample_identity_authority": "authoritative_source_column",
        "property_name": "explicitly_resolved_property",
        "value_column": 2,
        "unit": "resolved-unit",
        "method": "resolved-method",
        "instrument_model": "resolved-instrument",
        "calibration_status": "not_reported_no_claim",
        "calibration_id": None,
        "process_signature": None,
        "standard_uncertainty": {"mode": "column", "column_index": 3},
    }


def _lineage_resolution():
    return {
        "specimen_id_column": 0,
        "specimen_identity_authority": "authoritative_source_column",
        "acquisition_id_column": 1,
        "acquisition_identity_authority": "authoritative_source_column",
        "lab_id_column": 4,
        "material_lot_id_column": 5,
        "build_or_synthesis_id_column": 6,
        "process_run_id_column": None,
    }


def _resolution(structure, proposal):
    return build_reviewed_resolution_contract(
        structure=structure,
        proposal=proposal,
        semantic_resolution=_semantic_resolution(),
        lineage_resolution=_lineage_resolution(),
    )


def _approved_resolution_decision(resolution):
    return build_review_decision(
        resolution["resolution_review_request"],
        reviewer_id="reviewer:test-fixture",
        decision="approved",
        allowed_uses=["scientific_intake"],
        excluded_uses=[],
        review_notes="Test fixture approval of exact resolved semantic and lineage contract.",
    )


def test_resolution_gets_new_exact_review_request_and_does_not_reuse_proposal_review():
    structure = _structure()
    proposal = _proposal(structure)
    resolution = _resolution(structure, proposal)

    assert resolution["evidence_artifact_sha256"] == structure["artifact_sha256"]
    assert resolution["proposal_packet_sha256"] == proposal["proposal_packet_sha256"]
    assert resolution["semantic_resolution_sha256"] != proposal["semantic_proposal_sha256"]
    assert resolution["lineage_resolution_sha256"] != proposal["lineage_proposal_sha256"]
    assert resolution["resolution_review_request"]["requested_uses"] == [
        "scientific_intake"
    ]
    assert (
        resolution["resolution_review_request"]["review_request_id"]
        != proposal["review_request"]["review_request_id"]
    )
    assert resolution["prior_unresolved_proposal_review_is_sufficient"] is False
    assert resolution["accepted_for_analysis"] is False
    assert resolution["scientific_support_established"] is False

    verified = verify_reviewed_resolution_contract(
        structure=structure,
        proposal=proposal,
        resolution_contract=resolution,
    )
    assert verified["exact_resolution_binding_verified"] is True


def test_unresolved_proposal_review_cannot_unlock_resolved_normalization():
    structure = _structure()
    proposal = _proposal(structure)
    resolution = _resolution(structure, proposal)
    old_decision = build_review_decision(
        proposal["review_request"],
        reviewer_id="reviewer:test-fixture",
        decision="approved",
        allowed_uses=["scientific_intake"],
        excluded_uses=[],
        review_notes="Approval of unresolved proposal only.",
    )

    with pytest.raises(
        ReviewedResolutionCompilerError,
        match="resolved scientific-intake review release verification failed",
    ):
        compile_reviewed_resolution(
            artifact_bytes=BODY,
            structure=structure,
            proposal=proposal,
            resolution_contract=resolution,
            review_decision=old_decision,
        )


def test_exact_reviewed_resolution_compiles_strict_measurements_and_lineage_only():
    structure = _structure()
    proposal = _proposal(structure)
    resolution = _resolution(structure, proposal)
    decision = _approved_resolution_decision(resolution)

    manifest = compile_reviewed_resolution(
        artifact_bytes=BODY,
        structure=structure,
        proposal=proposal,
        resolution_contract=resolution,
        review_decision=decision,
    )

    assert manifest["human_review_blocker_released"] is True
    assert manifest["normalized_record_count"] == 2
    assert manifest["rejected_row_count"] == 0
    assert manifest["all_source_rows_normalized"] is True
    assert [record["record_locator"] for record in manifest["records"]] == [
        "data_row:1",
        "data_row:2",
    ]
    first = manifest["records"][0]
    assert first["measurement"]["sample_id"] == "s1"
    assert first["measurement"]["property_name"] == "explicitly_resolved_property"
    assert first["measurement"]["value"] == pytest.approx(1.20)
    assert first["measurement"]["unit"] == "resolved-unit"
    assert first["measurement"]["standard_uncertainty"] == pytest.approx(0.10)
    assert first["measurement"]["source_artifact_sha256"] == structure["artifact_sha256"]
    assert first["lineage"]["specimen_id"] == "s1"
    assert first["lineage"]["acquisition_id"] == "a1"
    assert first["lineage"]["material_lot_id"] == "lot-1"
    assert first["lineage"]["build_or_synthesis_id"] == "build-1"
    assert manifest["effective_independent_unit"]["unique_specimens"] == 2
    assert manifest["effective_independent_unit"]["unique_acquisitions"] == 2
    assert manifest["effective_independent_unit"]["unique_builds_or_syntheses"] == 2
    assert manifest["effective_independent_unit"]["naive_row_count_is_independence_count"] is False
    assert manifest["record_locator_is_physical_identity"] is False
    assert manifest["measurement_id_is_physical_independence_proof"] is False
    assert manifest["candidate_id_used_as_sample_or_specimen_identity"] is False
    assert manifest["accepted_for_analysis"] is False
    assert manifest["review_approval_is_scientific_support"] is False
    assert manifest["scientific_support_established"] is False
    assert manifest["hypothesis_support_established"] is False
    assert manifest["cross_source_comparability_established"] is False
    assert manifest["scientific_status_changed"] is False
    assert len(manifest["normalized_evidence_manifest_sha256"]) == 64


def test_artifact_resolution_and_review_mutations_fail_closed():
    structure = _structure()
    proposal = _proposal(structure)
    resolution = _resolution(structure, proposal)
    decision = _approved_resolution_decision(resolution)

    mutated_body = BODY.replace(b"1.20", b"1.21")
    with pytest.raises(ReviewedResolutionCompilerError, match="artifact bytes differ"):
        compile_reviewed_resolution(
            artifact_bytes=mutated_body,
            structure=structure,
            proposal=proposal,
            resolution_contract=resolution,
            review_decision=decision,
        )

    mutated_resolution = copy.deepcopy(resolution)
    mutated_resolution["semantic_resolution_contract"]["resolution"]["unit"] = "other-unit"
    with pytest.raises(ReviewedResolutionCompilerError, match="resolution bytes differ"):
        compile_reviewed_resolution(
            artifact_bytes=BODY,
            structure=structure,
            proposal=proposal,
            resolution_contract=mutated_resolution,
            review_decision=decision,
        )

    mutated_decision = copy.deepcopy(decision)
    mutated_decision["review_notes"] = "Changed after exact review."
    with pytest.raises(
        ReviewedResolutionCompilerError,
        match="resolved scientific-intake review release verification failed",
    ):
        compile_reviewed_resolution(
            artifact_bytes=BODY,
            structure=structure,
            proposal=proposal,
            resolution_contract=resolution,
            review_decision=mutated_decision,
        )


def test_physical_identity_requires_explicit_authoritative_source_columns():
    structure = _structure()
    proposal = _proposal(structure)
    semantic = _semantic_resolution()
    lineage = _lineage_resolution()

    semantic["sample_identity_authority"] = "row_number"
    with pytest.raises(ReviewedResolutionCompilerError, match="sample identity requires"):
        build_reviewed_resolution_contract(
            structure=structure,
            proposal=proposal,
            semantic_resolution=semantic,
            lineage_resolution=lineage,
        )

    semantic = _semantic_resolution()
    lineage["specimen_identity_authority"] = "candidate_id"
    with pytest.raises(ReviewedResolutionCompilerError, match="specimen identity requires"):
        build_reviewed_resolution_contract(
            structure=structure,
            proposal=proposal,
            semantic_resolution=semantic,
            lineage_resolution=lineage,
        )


def test_invalid_rows_are_explicitly_rejected_and_never_make_manifest_analysis_ready():
    body = (
        b"sample_id,acquisition_id,value,uncertainty,lab_id,lot_id,build_id\n"
        b"s1,a1,1.20,0.10,lab-a,lot-1,build-1\n"
        b"s2,a2,not-a-number,0.20,lab-a,lot-1,build-2\n"
    )
    structure = inspect_delimited_structure(body)
    proposal = _proposal(structure)
    resolution = _resolution(structure, proposal)
    decision = _approved_resolution_decision(resolution)

    manifest = compile_reviewed_resolution(
        artifact_bytes=body,
        structure=structure,
        proposal=proposal,
        resolution_contract=resolution,
        review_decision=decision,
    )

    assert manifest["normalized_record_count"] == 1
    assert manifest["rejected_row_count"] == 1
    assert manifest["all_source_rows_normalized"] is False
    assert manifest["rejected_rows"][0]["record_locator"] == "data_row:2"
    assert manifest["accepted_for_analysis"] is False
    assert manifest["scientific_support_established"] is False


def test_calibration_contract_cannot_claim_identifier_without_exact_identifier():
    structure = _structure()
    proposal = _proposal(structure)
    semantic = _semantic_resolution()
    semantic["calibration_status"] = "explicit_identifier"

    with pytest.raises(ReviewedResolutionCompilerError, match="requires calibration_id"):
        build_reviewed_resolution_contract(
            structure=structure,
            proposal=proposal,
            semantic_resolution=semantic,
            lineage_resolution=_lineage_resolution(),
        )
