from __future__ import annotations

import copy

import pytest

from materials_data_analyzer.research_loop.characterization_evidence_bridge import (
    CharacterizationEvidenceBridgeError,
    LEVELS,
)
from materials_data_analyzer.research_loop.evidence_packet import canonical_sha256
from materials_data_analyzer.research_loop.evidence_provider_contract import (
    EvidenceProviderContractError,
    adapt_authenticated_planning_gaps,
    adapt_characterization_provider_state,
    aggregate_provider_requirements,
    validate_provider_state,
    verify_authenticated_planning_provider_state,
    verify_characterization_provider_state,
    verify_provider_requirement_aggregate,
)


def _assessment(supported_through: int) -> dict[str, object]:
    levels: dict[str, dict[str, object]] = {}
    first_blocker = None
    for index, level in enumerate(LEVELS):
        supported = index <= supported_through
        if not supported and first_blocker is None:
            first_blocker = level
        levels[level] = {
            "assessment": "Supported" if supported else "Inconclusive",
            "evidence": [f"verified evidence for {level}"] if supported else [],
            "limitations": [] if supported else [f"missing evidence for {level}"],
            "description": f"producer description for {level}",
        }

    declaration = {
        "schema_version": "1.0",
        "declaration_id": "saed-provider-case",
        "subject": {
            "claim_scope": "material_validation",
            "modality": "SAED",
            "source_material_domain": "Co3O4",
            "target_material_domain": "Co3O4",
        },
        "source_bindings": [
            {"role": "source_manifest", "sha256": "a" * 64},
            {"role": "analysis_report", "sha256": "b" * 64},
        ],
        "levels": levels,
        "limitations": [],
    }
    highest = LEVELS[supported_through] if supported_through >= 0 else None
    thresholds = {
        "raw_representation_ready": 1,
        "acquisition_provenance_ready": 2,
        "instrument_calibration_ready": 3,
        "method_validation_ready": 4,
        "material_domain_validation_ready": 5,
        "independent_external_validation_ready": 6,
        "replicated_multisource_support_ready": 7,
        "engineering_decision_ready": 8,
    }
    assessment: dict[str, object] = {
        "schema_version": "1.0",
        "policy_version": "1.0",
        "declaration": declaration,
        "declaration_sha256": canonical_sha256(declaration),
        "highest_contiguous_supported_level": highest,
        "highest_contiguous_supported_index": supported_through,
        "first_blocking_level": first_blocker,
        "non_supported_levels": [
            {
                "level": level,
                "assessment": levels[level]["assessment"],
                "limitations": levels[level]["limitations"],
            }
            for level in LEVELS[supported_through + 1 :]
        ],
        "readiness": {
            field: supported_through >= threshold
            for field, threshold in thresholds.items()
        },
        "handoff": {
            "contract": "materials-characterization-scientific-evidence-ladder",
            "schema_version": "1.0",
            "subject": declaration["subject"],
            "source_bindings": declaration["source_bindings"],
            "highest_supported_level": highest,
            "first_blocking_level": first_blocker,
            "scientific_status_promoted": False,
            "downstream_use_authorized": False,
            "lower_level_evidence_preserved": True,
        },
        "policy_boundary": {
            "cross_material_proxy_promoted_to_target_material_validation": False,
            "software_validation_promoted_to_measurement_truth": False,
            "simulation_promoted_to_empirical_truth": False,
            "independence_inferred_from_file_count": False,
            "engineering_readiness_inferred": False,
        },
    }
    assessment["assessment_sha256"] = canonical_sha256(assessment)
    return assessment


def _planning_state() -> dict[str, object]:
    return {
        "source_discrepancy_report_sha256": "c" * 64,
        "fresh_plan_sha256": "d" * 64,
        "unresolved_evidence_gaps": [
            {
                "gap_id": "calibration-gap",
                "requirement": "Acquire experiment-scoped calibration evidence.",
                "action_class": "external_evidence_search",
            }
        ],
        "review_queue": [],
        "blockers": {
            "failed_discrepancy_gates": ["calibration"],
            "diagnosis_types": ["evidence_gap"],
            "external_or_authorization_required_objective_ids": [],
            "planner_stop": None,
        },
        "state_semantics": "verified_planning_context_snapshot_not_scientific_truth",
    }


def _rehash_provider(state: dict[str, object]) -> dict[str, object]:
    state = copy.deepcopy(state)
    state.pop("provider_state_sha256", None)
    state["provider_state_sha256"] = canonical_sha256(state)
    return state


def _rehash_aggregate(value: dict[str, object]) -> dict[str, object]:
    value = copy.deepcopy(value)
    value.pop("aggregate_sha256", None)
    value["aggregate_sha256"] = canonical_sha256(value)
    return value


def test_characterization_adapter_preserves_verified_first_blocker_without_authority() -> None:
    state = adapt_characterization_provider_state(_assessment(4))

    assert state["provider"]["provider_id"] == "characterization-evidence-ladder"
    assert state["readiness"] == {
        "status": "blocked",
        "maturity_label": "L4_method_algorithm_validation",
        "maturity_index": 4,
        "first_blocker": "L5_material_domain_validation",
    }
    assert len(state["unresolved_requirements"]) == 1
    requirement = state["unresolved_requirements"][0]
    assert requirement["requirement_class"] == "evidence_acquisition"
    assert requirement["action_class"] == "evidence_acquisition"
    assert requirement["automatic_execution_authorized"] is False
    assert set(state["authority_boundary"].values()) == {False, True}
    assert state["authority_boundary"]["planning_metadata_only"] is True
    assert state["authority_boundary"]["empirical_evidence_created"] is False
    assert {item["sha256"] for item in state["source_bindings"]} >= {
        "a" * 64,
        "b" * 64,
    }


def test_pre_l0_characterization_state_uses_null_generic_maturity_index() -> None:
    state = adapt_characterization_provider_state(_assessment(-1))
    assert state["readiness"]["status"] == "blocked"
    assert state["readiness"]["maturity_label"] is None
    assert state["readiness"]["maturity_index"] is None
    assert state["readiness"]["first_blocker"] == "L0_software_integration"


def test_complete_characterization_state_adds_no_false_requirement() -> None:
    state = adapt_characterization_provider_state(_assessment(8))
    assert state["readiness"]["status"] == "ready"
    assert state["readiness"]["first_blocker"] is None
    assert state["unresolved_requirements"] == []


def test_characterization_adapter_rejects_tampered_domain_assessment() -> None:
    assessment = _assessment(4)
    assessment["declaration"]["subject"]["target_material_domain"] = "forged"
    with pytest.raises(CharacterizationEvidenceBridgeError, match="assessment_sha256"):
        adapt_characterization_provider_state(assessment)


def test_rehashed_characterization_provider_substitution_fails_domain_replay() -> None:
    assessment = _assessment(4)
    state = adapt_characterization_provider_state(assessment)
    forged = copy.deepcopy(state)
    forged["source_bindings"][1]["sha256"] = "e" * 64
    forged = _rehash_provider(forged)

    assert validate_provider_state(forged)["source_bindings"][1]["sha256"] == "e" * 64
    with pytest.raises(
        EvidenceProviderContractError,
        match="verified domain recomputation",
    ):
        verify_characterization_provider_state(forged, assessment)


def test_authenticated_planning_adapter_normalizes_gap_without_execution_authority() -> None:
    state = _planning_state()
    trusted = canonical_sha256(state)
    provider = adapt_authenticated_planning_gaps(
        state,
        trusted_state_sha256=trusted,
    )
    requirement = provider["unresolved_requirements"][0]
    assert requirement["requirement_id"] == "calibration-gap"
    assert requirement["action_class"] == "evidence_acquisition"
    assert requirement["source_binding_ids"] == ["authenticated-planning-state"]
    assert provider["readiness"]["status"] == "blocked"
    assert provider["authority_boundary"]["execution_authorized"] is False


def test_planning_adapter_uses_fixed_provider_identity() -> None:
    state = _planning_state()
    provider = adapt_authenticated_planning_gaps(
        state,
        trusted_state_sha256=canonical_sha256(state),
    )
    assert provider["provider"]["provider_id"] == "validated-recursive-planning"


def test_planning_state_substitution_is_rejected_against_external_trust_root() -> None:
    state = _planning_state()
    trusted = canonical_sha256(state)
    forged = copy.deepcopy(state)
    forged["unresolved_evidence_gaps"][0]["requirement"] = "Forged easier requirement."

    with pytest.raises(
        EvidenceProviderContractError,
        match="external trust-root",
    ):
        adapt_authenticated_planning_gaps(
            forged,
            trusted_state_sha256=trusted,
        )


def test_rehashed_planning_provider_tamper_fails_recomputation() -> None:
    planning = _planning_state()
    trusted = canonical_sha256(planning)
    provider = adapt_authenticated_planning_gaps(
        planning,
        trusted_state_sha256=trusted,
    )
    forged = copy.deepcopy(provider)
    forged["unresolved_requirements"][0]["action_class"] = "analysis"
    forged["unresolved_requirements"][0]["requirement_class"] = "analysis"
    forged = _rehash_provider(forged)

    with pytest.raises(
        EvidenceProviderContractError,
        match="authenticated state recomputation",
    ):
        verify_authenticated_planning_provider_state(
            forged,
            planning,
            trusted_state_sha256=trusted,
        )


def test_provider_state_rejects_boolean_and_float_authority_or_maturity_aliases() -> None:
    state = adapt_characterization_provider_state(_assessment(4))

    promoted = copy.deepcopy(state)
    promoted["authority_boundary"]["empirical_evidence_created"] = 0
    promoted = _rehash_provider(promoted)
    with pytest.raises(EvidenceProviderContractError, match="authority boundary"):
        validate_provider_state(promoted)

    floated = copy.deepcopy(state)
    floated["readiness"]["maturity_index"] = 4.0
    floated = _rehash_provider(floated)
    with pytest.raises(EvidenceProviderContractError, match="exact non-negative integer"):
        validate_provider_state(floated)


def test_provider_aggregation_is_deterministic_and_preserves_sha_ancestry() -> None:
    characterization = adapt_characterization_provider_state(_assessment(4))
    planning = _planning_state()
    planning_provider = adapt_authenticated_planning_gaps(
        planning,
        trusted_state_sha256=canonical_sha256(planning),
    )

    first = aggregate_provider_requirements([characterization, planning_provider])
    second = aggregate_provider_requirements([planning_provider, characterization])

    assert first == second
    assert len(first["requirements"]) == 2
    assert first["authority_boundary"]["planning_metadata_only"] is True
    assert first["authority_boundary"]["scientific_status_promoted"] is False
    assert {item["provider_state_sha256"] for item in first["provider_state_sha256s"]} == {
        characterization["provider_state_sha256"],
        planning_provider["provider_state_sha256"],
    }


def test_rehashed_aggregate_tamper_fails_provider_state_recomputation() -> None:
    characterization = adapt_characterization_provider_state(_assessment(4))
    planning = _planning_state()
    planning_provider = adapt_authenticated_planning_gaps(
        planning,
        trusted_state_sha256=canonical_sha256(planning),
    )
    aggregate = aggregate_provider_requirements([characterization, planning_provider])
    forged = copy.deepcopy(aggregate)
    forged["requirements"][0]["requirement"]["description"] = "forged"
    forged = _rehash_aggregate(forged)

    with pytest.raises(
        EvidenceProviderContractError,
        match="provider-state recomputation",
    ):
        verify_provider_requirement_aggregate(
            forged,
            [characterization, planning_provider],
        )


def test_duplicate_provider_identity_is_rejected_by_aggregate() -> None:
    state = adapt_characterization_provider_state(_assessment(4))
    with pytest.raises(EvidenceProviderContractError, match="unique provider ids"):
        aggregate_provider_requirements([state, state])
