from __future__ import annotations

import copy

import pytest

from materials_data_analyzer.research_loop.canonical_research_run import (
    CanonicalResearchRunError,
    DERIVED_PROJECTIONS,
    GOVERNANCE_STATE_COLLECTIONS,
    RESEARCH_RUN_SECTIONS,
    SCIENTIFIC_STATE_COLLECTIONS,
    build_canonical_research_run_contract,
    validate_canonical_research_run_contract,
)


def test_research_run_contract_is_deterministic_and_valid() -> None:
    first = build_canonical_research_run_contract()
    second = build_canonical_research_run_contract()

    assert first == second
    assert validate_canonical_research_run_contract(first) == first


def test_research_run_has_one_explicit_state_partition() -> None:
    assert RESEARCH_RUN_SECTIONS == (
        "identity",
        "scientific_state",
        "governance_state",
        "derived_projections",
        "terminal_state",
    )
    assert "hypothesis" in SCIENTIFIC_STATE_COLLECTIONS
    assert "comparability_assessment" in SCIENTIFIC_STATE_COLLECTIONS
    assert "uncertainty_state" in SCIENTIFIC_STATE_COLLECTIONS
    assert "authorization_records" in GOVERNANCE_STATE_COLLECTIONS
    assert "transaction_integrity_state" in GOVERNANCE_STATE_COLLECTIONS
    assert "characterization_l0_l8" in DERIVED_PROJECTIONS


def test_projection_and_governance_cannot_promote_scientific_truth() -> None:
    contract = build_canonical_research_run_contract()
    authority = contract["authority_invariants"]

    assert authority[
        "scientific_state_reconstructed_from_authenticated_evidence_and_epistemic_events"
    ] is True
    assert authority[
        "governance_state_reconstructed_from_authenticated_policy_authorization_and_execution_records"
    ] is True
    assert authority["derived_projection_is_authoritative_scientific_truth"] is False
    assert authority["derived_projection_grants_execution_authority"] is False
    assert authority["governance_success_promotes_scientific_status"] is False
    assert authority["science_selection_grants_execution_authority"] is False


def test_historical_replay_is_preserved() -> None:
    compatibility = build_canonical_research_run_contract()["compatibility_invariants"]

    assert compatibility["historical_artifacts_rewritten"] is False
    assert compatibility["historical_hashes_recomputed"] is False
    assert compatibility["legacy_state_remains_replayable"] is True
    assert compatibility["migration_requires_explicit_compatibility_projection"] is True


def test_research_run_contract_rejects_authority_drift() -> None:
    contract = copy.deepcopy(build_canonical_research_run_contract())
    contract["authority_invariants"]["governance_success_promotes_scientific_status"] = True

    with pytest.raises(CanonicalResearchRunError, match="drifted"):
        validate_canonical_research_run_contract(contract)


def test_research_run_contract_rejects_unknown_fields() -> None:
    contract = build_canonical_research_run_contract()
    contract["extra"] = True

    with pytest.raises(CanonicalResearchRunError, match="exact keys"):
        validate_canonical_research_run_contract(contract)
