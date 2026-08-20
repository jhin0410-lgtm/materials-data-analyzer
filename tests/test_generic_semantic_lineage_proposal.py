from __future__ import annotations

import copy

import pytest

from materials_data_analyzer.research_loop.delimited_structural_intake import (
    inspect_delimited_structure,
)
from materials_data_analyzer.research_loop.generic_semantic_lineage_proposal import (
    GenericSemanticLineageProposalError,
    build_generic_semantic_lineage_proposal,
    verify_generic_semantic_lineage_proposal,
)


def _structure():
    return inspect_delimited_structure(
        b"sample_id,replicate,time_s,temperature_c,voltage_v\n"
        b"s1,r1,0.0,600,1.01\n"
        b"s1,r1,0.2,600,1.00\n"
    )


def test_generic_structure_builds_proposal_only_review_packet():
    structure = _structure()

    packet = build_generic_semantic_lineage_proposal(
        candidate_id="candidate:unseen-table",
        structure=structure,
    )

    semantic = packet["semantic_proposal"]
    lineage = packet["lineage_proposal"]
    request = packet["review_request"]
    assert packet["evidence_artifact_sha256"] == structure["artifact_sha256"]
    assert semantic["candidate_identity_columns"] == [0]
    assert semantic["candidate_replicate_columns"] == [1]
    assert semantic["candidate_time_columns"] == [2]
    assert semantic["candidate_temperature_columns"] == [3]
    assert semantic["candidate_measurement_columns"] == [4]
    assert "sample_id" in semantic["unresolved_normalized_measurement_fields"]
    assert "unit" in semantic["unresolved_normalized_measurement_fields"]
    assert semantic["units_inferred"] is False
    assert semantic["sample_identity_inferred"] is False
    assert semantic["proposal_accepted"] is False
    assert lineage["identity_like_source_columns_proposal_only"] == [0]
    assert lineage["replicate_like_source_columns_proposal_only"] == [1]
    assert lineage["replicate_independence_established"] is False
    assert lineage["independence_level"] == "unresolved"
    assert lineage["filename_or_row_number_used_as_identity"] is False
    assert request["requested_uses"] == ["scientific_intake"]
    assert request["semantic_contract_sha256"] == packet["semantic_proposal_sha256"]
    assert request["lineage_sha256"] == packet["lineage_proposal_sha256"]
    assert request["intake_artifact_sha256"] == packet["structural_intake_sha256"]
    assert packet["human_review_decision_created"] is False
    assert packet["human_review_blocker_released"] is False
    assert packet["proposal_can_instantiate_normalized_measurement"] is False
    assert packet["proposal_can_instantiate_observation_lineage"] is False
    assert packet["accepted_for_analysis"] is False
    assert packet["scientific_support_established"] is False
    assert packet["scientific_status_changed"] is False


def test_exact_proposal_verifier_detects_semantic_lineage_or_structure_mutation():
    structure = _structure()
    packet = build_generic_semantic_lineage_proposal(
        candidate_id="candidate:unseen-table",
        structure=structure,
    )

    verified = verify_generic_semantic_lineage_proposal(
        structure=structure,
        proposal=packet,
    )
    assert verified["exact_structure_binding_verified"] is True
    assert verified["human_review_blocker_released"] is False

    mutated_semantic = copy.deepcopy(packet)
    mutated_semantic["semantic_proposal"]["units_inferred"] = True
    with pytest.raises(GenericSemanticLineageProposalError, match="proposal bytes differ"):
        verify_generic_semantic_lineage_proposal(
            structure=structure,
            proposal=mutated_semantic,
        )

    mutated_lineage = copy.deepcopy(packet)
    mutated_lineage["lineage_proposal"]["specimen_id_assigned"] = True
    with pytest.raises(GenericSemanticLineageProposalError, match="proposal bytes differ"):
        verify_generic_semantic_lineage_proposal(
            structure=structure,
            proposal=mutated_lineage,
        )

    changed_structure = inspect_delimited_structure(
        b"sample_id,replicate,time_s,temperature_c,voltage_v\n"
        b"s1,r1,0.0,600,1.02\n"
        b"s1,r1,0.2,600,1.00\n"
    )
    with pytest.raises(GenericSemanticLineageProposalError, match="proposal bytes differ"):
        verify_generic_semantic_lineage_proposal(
            structure=changed_structure,
            proposal=packet,
        )


def test_structure_that_claims_scientific_acceptance_cannot_generate_proposal():
    structure = _structure()
    structure["accepted_for_analysis"] = True

    with pytest.raises(GenericSemanticLineageProposalError, match="proposal-only boundary"):
        build_generic_semantic_lineage_proposal(
            candidate_id="candidate:unseen-table",
            structure=structure,
        )
