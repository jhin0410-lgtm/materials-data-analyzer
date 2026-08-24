from __future__ import annotations

import copy

import pytest

from materials_data_analyzer.research_loop.canonical_research_run import (
    CanonicalResearchRunError,
    DERIVED_PROJECTIONS,
    GOVERNANCE_STATE_COLLECTIONS,
    RESEARCH_RUN_SECTIONS,
    RUN_LIFECYCLE_STATES,
    SCIENTIFIC_STATE_COLLECTIONS,
    SCIENTIFIC_STOP_DISPOSITIONS,
    build_canonical_research_run_contract,
    validate_canonical_research_run_contract,
)


def test_research_run_contract_is_deterministic_and_valid() -> None:
    first = build_canonical_research_run_contract()
    second = build_canonical_research_run_contract()

    assert first == second
    assert validate_canonical_research_run_contract(first) == first


def test_research_run_partitions_science_governance_lifecycle_and_stop_orthogonally() -> None:
    assert RESEARCH_RUN_SECTIONS == (
        "identity",
        "scientific_state",
        "governance_state",
        "run_lifecycle",
        "scientific_stop_disposition",
        "derived_projections",
    )
    assert "hypothesis" in SCIENTIFIC_STATE_COLLECTIONS
    assert "inference" in SCIENTIFIC_STATE_COLLECTIONS
    assert "comparability_assessment" in SCIENTIFIC_STATE_COLLECTIONS
    assert "uncertainty_state" in SCIENTIFIC_STATE_COLLECTIONS
    assert "authorization_records" in GOVERNANCE_STATE_COLLECTIONS
    assert "mission_governance_policy" in GOVERNANCE_STATE_COLLECTIONS
    assert "transaction_integrity_state" in GOVERNANCE_STATE_COLLECTIONS
    assert "lifecycle_event_records" in GOVERNANCE_STATE_COLLECTIONS
    assert "characterization_l0_l8" in DERIVED_PROJECTIONS


def test_operational_lifecycle_is_not_scientific_stop_semantics() -> None:
    assert "active" in RUN_LIFECYCLE_STATES
    assert "blocked" in RUN_LIFECYCLE_STATES
    assert "interrupted" in RUN_LIFECYCLE_STATES
    assert "execution_failed" in RUN_LIFECYCLE_STATES
    assert "converged" not in RUN_LIFECYCLE_STATES

    assert "continue" in SCIENTIFIC_STOP_DISPOSITIONS
    assert "undetermined" in SCIENTIFIC_STOP_DISPOSITIONS
    assert "converged" in SCIENTIFIC_STOP_DISPOSITIONS
    assert "irreducible_uncertainty" in SCIENTIFIC_STOP_DISPOSITIONS
    assert "execution_failed" not in SCIENTIFIC_STOP_DISPOSITIONS


def test_each_run_section_has_explicit_authority_source() -> None:
    contract = build_canonical_research_run_contract()
    sources = contract["section_authority_sources"]
    assert set(sources) == set(RESEARCH_RUN_SECTIONS)
    assert sources["scientific_state"] == (
        "validated_evidence_packets_and_authority_bearing_epistemic_updates"
    )
    assert sources["governance_state"] == (
        "authenticated_policy_authorization_execution_and_audit_records"
    )
    assert sources["run_lifecycle"] == "authenticated_operational_lifecycle_events"
    assert sources["scientific_stop_disposition"] == (
        "science_plane_assessment_over_validated_scientific_state"
    )
    assert sources["derived_projections"] == "non_authoritative_projection_of_canonical_state"


def test_authentication_diagnostic_transition_projection_and_governance_cannot_promote_science() -> None:
    contract = build_canonical_research_run_contract()
    authority = contract["authority_invariants"]

    assert authority[
        "scientific_state_reconstructed_from_validated_evidence_packets_and_authority_bearing_epistemic_updates"
    ] is True
    assert authority[
        "authenticated_artifact_alone_enters_authoritative_scientific_state"
    ] is False
    assert authority[
        "diagnostic_transition_alone_enters_authoritative_scientific_state"
    ] is False
    assert authority[
        "governance_state_reconstructed_from_authenticated_policy_authorization_and_execution_records"
    ] is True
    assert authority["run_lifecycle_reconstructed_from_authenticated_operational_events"] is True
    assert authority["run_lifecycle_implies_scientific_stop_disposition"] is False
    assert authority["scientific_stop_disposition_is_operational_lifecycle_state"] is False
    assert authority["derived_projection_is_authoritative_scientific_truth"] is False
    assert authority["derived_projection_grants_execution_authority"] is False
    assert authority["governance_success_promotes_scientific_status"] is False
    assert authority["science_selection_grants_execution_authority"] is False


def test_historical_replay_is_preserved_without_promoting_operational_stops() -> None:
    compatibility = build_canonical_research_run_contract()["compatibility_invariants"]

    assert compatibility["historical_artifacts_rewritten"] is False
    assert compatibility["historical_hashes_recomputed"] is False
    assert compatibility["legacy_state_remains_replayable"] is True
    assert compatibility["legacy_operational_stop_is_not_assumed_scientific_stop"] is True
    assert compatibility["migration_requires_explicit_compatibility_projection"] is True


def test_research_run_contract_rejects_authority_drift() -> None:
    contract = copy.deepcopy(build_canonical_research_run_contract())
    contract["authority_invariants"]["governance_success_promotes_scientific_status"] = True

    with pytest.raises(CanonicalResearchRunError, match="drifted"):
        validate_canonical_research_run_contract(contract)


def test_research_run_contract_rejects_lifecycle_scientific_stop_conflation() -> None:
    contract = copy.deepcopy(build_canonical_research_run_contract())
    contract["run_lifecycle_states"].append("converged")

    with pytest.raises(CanonicalResearchRunError, match="drifted"):
        validate_canonical_research_run_contract(contract)


def test_research_run_contract_rejects_unknown_fields() -> None:
    contract = build_canonical_research_run_contract()
    contract["extra"] = True

    with pytest.raises(CanonicalResearchRunError, match="exact keys"):
        validate_canonical_research_run_contract(contract)
