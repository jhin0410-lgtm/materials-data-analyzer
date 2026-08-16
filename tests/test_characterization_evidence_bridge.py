from __future__ import annotations

import copy

import pytest

from materials_data_analyzer.research_loop.autonomous_inquiry import _canonical_sha256
from materials_data_analyzer.research_loop.characterization_evidence_bridge import (
    CharacterizationEvidenceBridgeError,
    LEVELS,
    apply_characterization_evidence_assessments,
    verify_characterization_evidence_assessment,
)
from materials_data_analyzer.research_loop.research_agent import (
    build_research_agent_iteration,
)


def _program() -> dict[str, object]:
    return {
        "mission": {
            "autonomy_policy": {
                "goal_generation": "bounded_autonomous",
                "reasoning_proposals": "schema_validated",
                "typed_computational_actions": "explicit_request",
                "network_evidence_search": "explicit_authorization",
                "physical_experiment_execution": "external_only",
            }
        },
        "generated_goals": [
            {
                "goal_id": "mission:characterization:resolve-current-blocker",
                "workstream_id": "characterization",
                "research_question": "What characterization evidence is missing?",
                "goal_statement": "Resolve the current characterization blocker.",
                "status": "active",
                "priority": 90,
                "evidence_requirements": ["Resolve the declared scientific evidence blocker"],
                "claim_boundary": {"scientific_status": "inconclusive"},
                "action_frontier": [],
            }
        ],
    }


def _assessment(supported_through: int, *, declaration_id: str = "saed-case") -> dict[str, object]:
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
        "declaration_id": declaration_id,
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
    readiness_thresholds = {
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
        "declaration_sha256": _canonical_sha256(declaration),
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
            for field, threshold in readiness_thresholds.items()
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
    assessment["assessment_sha256"] = _canonical_sha256(assessment)
    return assessment


def test_consumer_independently_verifies_hashes_levels_readiness_and_handoff() -> None:
    verified = verify_characterization_evidence_assessment(_assessment(4))

    assert verified["highest_supported_level"] == "L4_method_algorithm_validation"
    assert verified["first_blocking_level"] == "L5_material_domain_validation"
    assert verified["scientific_status_promoted"] is False
    assert verified["downstream_use_authorized"] is False


def test_l4_cross_material_style_state_generates_l5_exact_material_search_gap() -> None:
    plan = build_research_agent_iteration(
        _program(), characterization_evidence_assessments=[_assessment(4)]
    )

    gap = next(
        item
        for item in plan["evidence_gaps"]
        if item.get("origin") == "independently_verified_characterization_evidence_ladder"
    )
    assert gap["blocking_level"] == "L5_material_domain_validation"
    assert gap["may_be_filled_by_synthetic_evidence"] is False
    action = next(
        item
        for item in plan["ranked_actions"]
        if item.get("origin") == "characterization_evidence_ladder"
    )
    assert action["action_class"] == "external_evidence_search"
    assert action["automatic_execution_authorized"] is False
    assert plan["characterization_evidence"]["downstream_use_authorized"] is False


def test_l5_exact_material_state_does_not_skip_l6_independence() -> None:
    plan = build_research_agent_iteration(
        _program(), characterization_evidence_assessments=[_assessment(5)]
    )
    gap = next(
        item
        for item in plan["evidence_gaps"]
        if item.get("origin") == "independently_verified_characterization_evidence_ladder"
    )

    assert gap["blocking_level"] == "L6_independent_external_validation"
    assert "development- and provenance-disjoint" in gap["requirement"]
    assert plan["autonomy_boundary"]["characterization_lower_level_evidence_promoted"] is False


def test_l8_complete_assessment_adds_no_false_gap() -> None:
    base = build_research_agent_iteration(_program())
    enriched = apply_characterization_evidence_assessments(base, [_assessment(8)])

    assert enriched["characterization_evidence"]["first_blocker_gaps_added"] == 0
    assert not any(
        item.get("origin") == "independently_verified_characterization_evidence_ladder"
        for item in enriched["evidence_gaps"]
    )


def test_assessment_content_tamper_is_rejected_even_when_summary_looks_valid() -> None:
    assessment = _assessment(4)
    assessment["declaration"]["subject"]["target_material_domain"] = "not-Co3O4"

    with pytest.raises(CharacterizationEvidenceBridgeError, match="assessment_sha256"):
        verify_characterization_evidence_assessment(assessment)


def test_false_readiness_and_handoff_promotion_are_rejected_with_rebound_hash() -> None:
    readiness = _assessment(4)
    readiness["readiness"]["independent_external_validation_ready"] = True
    readiness["assessment_sha256"] = _canonical_sha256(
        {key: value for key, value in readiness.items() if key != "assessment_sha256"}
    )
    with pytest.raises(CharacterizationEvidenceBridgeError, match="readiness mismatch"):
        verify_characterization_evidence_assessment(readiness)

    promoted = _assessment(4)
    promoted["handoff"]["scientific_status_promoted"] = True
    promoted["assessment_sha256"] = _canonical_sha256(
        {key: value for key, value in promoted.items() if key != "assessment_sha256"}
    )
    with pytest.raises(CharacterizationEvidenceBridgeError, match="must not promote"):
        verify_characterization_evidence_assessment(promoted)


def test_nonmonotonic_supported_level_is_rejected_after_rebinding_hashes() -> None:
    assessment = _assessment(3)
    assessment["declaration"]["levels"]["L5_material_domain_validation"] = {
        "assessment": "Supported",
        "evidence": ["invalid skipped-level evidence"],
        "limitations": [],
        "description": "invalid promotion",
    }
    assessment["declaration_sha256"] = _canonical_sha256(assessment["declaration"])
    assessment["assessment_sha256"] = _canonical_sha256(
        {key: value for key, value in assessment.items() if key != "assessment_sha256"}
    )

    with pytest.raises(CharacterizationEvidenceBridgeError, match="cannot be Supported"):
        verify_characterization_evidence_assessment(assessment)


def test_unchanged_full_research_state_stagnates_but_new_assessment_reopens_loop() -> None:
    first = build_research_agent_iteration(
        _program(), characterization_evidence_assessments=[_assessment(4)]
    )
    second = build_research_agent_iteration(
        _program(),
        characterization_evidence_assessments=[_assessment(4)],
        previous_plan=first,
    )

    assert second["selected_next_action"] is None
    assert second["stop_decision"]["reason"] == "stagnation_no_new_verified_research_state"

    changed = _assessment(5)
    third = build_research_agent_iteration(
        _program(),
        characterization_evidence_assessments=[changed],
        previous_plan=first,
    )
    assert third["research_state_binding_sha256"] != first["research_state_binding_sha256"]
    assert third["selected_next_action"] is not None
    assert third["stop_decision"]["stop"] is False


def test_multiple_assessments_are_checksum_bound_as_one_research_state() -> None:
    first_assessment = _assessment(4, declaration_id="saed")
    second_assessment = _assessment(5, declaration_id="tem")
    first = build_research_agent_iteration(
        _program(),
        characterization_evidence_assessments=[first_assessment, second_assessment],
    )
    changed_second = copy.deepcopy(second_assessment)
    changed_second["declaration"]["limitations"].append("new verified limitation")
    changed_second["declaration_sha256"] = _canonical_sha256(changed_second["declaration"])
    changed_second["assessment_sha256"] = _canonical_sha256(
        {key: value for key, value in changed_second.items() if key != "assessment_sha256"}
    )
    second = build_research_agent_iteration(
        _program(),
        characterization_evidence_assessments=[first_assessment, changed_second],
    )

    assert first["characterization_evidence"]["assessment_count"] == 2
    assert first["research_state_binding_sha256"] != second["research_state_binding_sha256"]
