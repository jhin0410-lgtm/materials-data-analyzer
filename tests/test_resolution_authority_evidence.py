from __future__ import annotations

import copy
import hashlib

import pytest

from materials_data_analyzer.research_loop.delimited_structural_intake import (
    inspect_delimited_structure,
)
from materials_data_analyzer.research_loop.generic_semantic_lineage_proposal import (
    build_generic_semantic_lineage_proposal,
)
from materials_data_analyzer.research_loop.resolution_authority_evidence import (
    ResolutionAuthorityEvidenceError,
    build_authority_review_decision,
    build_authority_review_request,
    build_resolution_authority_packet,
    compile_authority_bound_delimited_resolution,
    verify_resolution_authority_packet,
)
from materials_data_analyzer.research_loop.reviewed_resolution_compiler import (
    build_reviewed_resolution_contract,
)
from materials_data_analyzer.research_loop.scientific_review_release import (
    build_review_decision,
)


BODY = (
    b"sample_id,acquisition_id,value\n"
    b"s1,a1,1.2\n"
    b"s2,a2,1.4\n"
)
AUTHORITY = (
    b"Material identity: Example Alloy / EXAMPLE-ALLOY.\n"
    b"Column sample_id is the physical sample and specimen identifier.\n"
    b"Column acquisition_id is the acquisition identifier.\n"
    b"Column value is the explicitly resolved property.\n"
    b"Reported unit: resolved-unit.\n"
    b"Measurement method: resolved-method.\n"
    b"Instrument model: resolved-instrument.\n"
)


def _structure():
    return inspect_delimited_structure(BODY)


def _proposal(structure):
    return build_generic_semantic_lineage_proposal(
        candidate_id="candidate:authority-bound-fixture",
        structure=structure,
    )


def _semantic():
    return {
        "source_id": "source:authority-bound-fixture",
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
        "standard_uncertainty": {"mode": "none"},
    }


def _lineage():
    return {
        "specimen_id_column": 0,
        "specimen_identity_authority": "authoritative_source_column",
        "acquisition_id_column": 1,
        "acquisition_identity_authority": "authoritative_source_column",
        "lab_id_column": None,
        "material_lot_id_column": None,
        "build_or_synthesis_id_column": None,
        "process_run_id_column": None,
    }


def _resolution(structure, proposal):
    return build_reviewed_resolution_contract(
        structure=structure,
        proposal=proposal,
        semantic_resolution=_semantic(),
        lineage_resolution=_lineage(),
    )


def _record(claim_kind, authorized_value, witness):
    start = AUTHORITY.index(witness.encode("utf-8"))
    end = start + len(witness.encode("utf-8"))
    return {
        "claim_kind": claim_kind,
        "authorized_value": authorized_value,
        "authority_artifact_sha256": hashlib.sha256(AUTHORITY).hexdigest(),
        "byte_start": start,
        "byte_end": end,
        "witness_text": witness,
    }


def _records():
    semantic = _semantic()
    lineage = _lineage()
    return [
        _record(
            "material_identity",
            semantic["material"],
            "Material identity: Example Alloy / EXAMPLE-ALLOY.",
        ),
        _record(
            "sample_identity",
            {"column_index": semantic["sample_id_column"]},
            "Column sample_id is the physical sample and specimen identifier.",
        ),
        _record(
            "specimen_identity",
            {"column_index": lineage["specimen_id_column"]},
            "Column sample_id is the physical sample and specimen identifier.",
        ),
        _record(
            "acquisition_identity",
            {"column_index": lineage["acquisition_id_column"]},
            "Column acquisition_id is the acquisition identifier.",
        ),
        _record(
            "property_semantics",
            {
                "property_name": semantic["property_name"],
                "value_column": semantic["value_column"],
            },
            "Column value is the explicitly resolved property.",
        ),
        _record("unit", semantic["unit"], "Reported unit: resolved-unit."),
        _record("method", semantic["method"], "Measurement method: resolved-method."),
        _record(
            "instrument_model",
            semantic["instrument_model"],
            "Instrument model: resolved-instrument.",
        ),
    ]


def _authority_packet(resolution):
    digest = hashlib.sha256(AUTHORITY).hexdigest()
    return build_resolution_authority_packet(
        resolution_contract=resolution,
        authority_records=_records(),
        authority_artifacts={digest: AUTHORITY},
    )


def _base_review(resolution):
    return build_review_decision(
        resolution["resolution_review_request"],
        reviewer_id="reviewer:resolution",
        decision="approved",
        allowed_uses=["scientific_intake"],
        excluded_uses=[],
        review_notes="Approve exact resolved mapping fixture only.",
    )


def _authority_review(resolution, packet):
    request = build_authority_review_request(
        resolution_contract=resolution,
        authority_packet=packet,
    )
    return build_authority_review_decision(
        request,
        reviewer_id="reviewer:authority",
        decision="approved",
        review_notes="Approve exact source authority witnesses for fixture only.",
    )


def test_all_positive_resolution_claims_require_exact_authority_witnesses():
    structure = _structure()
    proposal = _proposal(structure)
    resolution = _resolution(structure, proposal)
    packet = _authority_packet(resolution)

    assert packet["all_positive_resolution_claims_source_authorized"] is True
    assert packet["missing_required_authority"] == []
    assert packet["authority_conflicts"] == []
    assert len(packet["authority_records"]) == 8
    assert packet["authority_review_released"] is False
    assert packet["scientific_support_established"] is False
    assert len(packet["authority_packet_sha256"]) == 64

    verified = verify_resolution_authority_packet(
        resolution_contract=resolution,
        authority_packet=packet,
        authority_artifacts={hashlib.sha256(AUTHORITY).hexdigest(): AUTHORITY},
    )
    assert verified["exact_authority_binding_verified"] is True


def test_missing_conflicting_and_mutated_authority_fail_closed():
    structure = _structure()
    proposal = _proposal(structure)
    resolution = _resolution(structure, proposal)
    digest = hashlib.sha256(AUTHORITY).hexdigest()

    with pytest.raises(ResolutionAuthorityEvidenceError, match="missing"):
        build_resolution_authority_packet(
            resolution_contract=resolution,
            authority_records=_records()[:-1],
            authority_artifacts={digest: AUTHORITY},
        )

    conflicting = _records()
    conflicting.append(
        _record("unit", "wrong-unit", "Reported unit: resolved-unit.")
    )
    with pytest.raises(ResolutionAuthorityEvidenceError, match="conflicts"):
        build_resolution_authority_packet(
            resolution_contract=resolution,
            authority_records=conflicting,
            authority_artifacts={digest: AUTHORITY},
        )

    packet = _authority_packet(resolution)
    mutated_authority = AUTHORITY.replace(b"resolved-unit", b"changed-unit!")
    with pytest.raises(ResolutionAuthorityEvidenceError, match="do not match"):
        verify_resolution_authority_packet(
            resolution_contract=resolution,
            authority_packet=packet,
            authority_artifacts={digest: mutated_authority},
        )


def test_authority_change_regenerates_exact_review_request():
    structure = _structure()
    proposal = _proposal(structure)
    resolution = _resolution(structure, proposal)
    packet = _authority_packet(resolution)
    request = build_authority_review_request(
        resolution_contract=resolution,
        authority_packet=packet,
    )

    alternate = AUTHORITY + b"Additional exact source context.\n"
    alt_digest = hashlib.sha256(alternate).hexdigest()
    records = copy.deepcopy(_records())
    for item in records:
        item["authority_artifact_sha256"] = alt_digest
    alternate_packet = build_resolution_authority_packet(
        resolution_contract=resolution,
        authority_records=records,
        authority_artifacts={alt_digest: alternate},
    )
    alternate_request = build_authority_review_request(
        resolution_contract=resolution,
        authority_packet=alternate_packet,
    )

    assert alternate_packet["authority_packet_sha256"] != packet["authority_packet_sha256"]
    assert alternate_request["authority_review_request_id"] != request["authority_review_request_id"]


def test_two_exact_reviews_are_required_before_authority_bound_normalization():
    structure = _structure()
    proposal = _proposal(structure)
    resolution = _resolution(structure, proposal)
    packet = _authority_packet(resolution)
    base_decision = _base_review(resolution)
    authority_decision = _authority_review(resolution, packet)
    digest = hashlib.sha256(AUTHORITY).hexdigest()

    manifest = compile_authority_bound_delimited_resolution(
        artifact_bytes=BODY,
        structure=structure,
        proposal=proposal,
        resolution_contract=resolution,
        resolution_review_decision=base_decision,
        authority_packet=packet,
        authority_artifacts={digest: AUTHORITY},
        authority_review_decision=authority_decision,
    )

    assert manifest["normalized_record_count"] == 2
    assert manifest["all_positive_resolution_claims_source_authorized"] is True
    assert manifest["authority_review_is_scientific_support"] is False
    assert manifest["scientific_support_established"] is False
    assert manifest["accepted_for_analysis"] is False
    assert manifest["scientific_status_changed"] is False

    rejected_authority = build_authority_review_decision(
        build_authority_review_request(
            resolution_contract=resolution,
            authority_packet=packet,
        ),
        reviewer_id="reviewer:authority",
        decision="rejected",
        review_notes="Reject exact authority evidence fixture.",
    )
    with pytest.raises(ResolutionAuthorityEvidenceError, match="does not release"):
        compile_authority_bound_delimited_resolution(
            artifact_bytes=BODY,
            structure=structure,
            proposal=proposal,
            resolution_contract=resolution,
            resolution_review_decision=base_decision,
            authority_packet=packet,
            authority_artifacts={digest: AUTHORITY},
            authority_review_decision=rejected_authority,
        )


def test_authority_review_mutation_fails_exact_release_verification():
    structure = _structure()
    proposal = _proposal(structure)
    resolution = _resolution(structure, proposal)
    packet = _authority_packet(resolution)
    decision = _authority_review(resolution, packet)
    mutated = copy.deepcopy(decision)
    mutated["review_notes"] = "Changed after authority review."

    with pytest.raises(ResolutionAuthorityEvidenceError, match="release ID"):
        compile_authority_bound_delimited_resolution(
            artifact_bytes=BODY,
            structure=structure,
            proposal=proposal,
            resolution_contract=resolution,
            resolution_review_decision=_base_review(resolution),
            authority_packet=packet,
            authority_artifacts={hashlib.sha256(AUTHORITY).hexdigest(): AUTHORITY},
            authority_review_decision=mutated,
        )
