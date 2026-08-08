from __future__ import annotations

import copy

import pytest

from materials_data_analyzer.research_loop.external_evidence_contract import (
    ExternalEvidenceContractError,
    evaluate_external_source_candidate,
)


def _requirement() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "requirement_id": "fixture-external-v1",
        "domain": "fixture-domain",
        "objective": "Test one source-disjoint candidate without acquiring its target data.",
        "scientific_evidence_level": "DevelopmentDiagnostic",
        "source_independence_required": True,
        "prohibited_source_systems": ["Original Source", "Original Source-derived mirror"],
        "required_metadata_checks": ["dataset_identity", "method_metadata"],
        "required_semantic_checks": ["target_definition", "target_unit"],
        "domain_requirements": {"target": "fixture_target"},
        "automatic_acquisition_authorized": False,
        "model_fit_authorized": False,
        "external_validation_claim_authorized": False,
        "source_binding": {"origin_sha256": "a" * 64},
        "scientific_boundary": ["Screen before acquisition."],
    }


def _candidate() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "candidate_id": "candidate-a",
        "title": "Independent fixture candidate",
        "source_system": "Independent Source",
        "availability": "available",
        "source_independence": "confirmed_independent",
        "license_status": "confirmed_reusable",
        "metadata_checks": {
            "dataset_identity": "confirmed_match",
            "method_metadata": "confirmed_match",
        },
        "semantic_checks": {
            "target_definition": "confirmed_match",
            "target_unit": "confirmed_match",
        },
        "notes": [],
    }


def test_fully_compatible_candidate_is_only_screening_eligible() -> None:
    result = evaluate_external_source_candidate(_requirement(), _candidate())

    assert result.disposition == "eligible"
    assert result.eligible_for_requirement is True
    assert result.source_independence_satisfied is True
    assert result.automatic_acquisition_authorized is False
    assert result.model_fit_authorized is False
    assert result.external_validation_claim_authorized is False
    assert "Predeclare and freeze" in result.next_action


def test_same_source_candidate_is_diagnostic_only() -> None:
    candidate = _candidate()
    candidate["source_system"] = "Original Source"
    candidate["source_independence"] = "confirmed_not_independent"

    result = evaluate_external_source_candidate(_requirement(), candidate)

    assert result.disposition == "diagnostic_only"
    assert result.eligible_for_requirement is False
    assert result.source_independence_satisfied is False


def test_confirmed_source_dependence_precedes_unresolved_secondary_checks() -> None:
    candidate = _candidate()
    candidate["source_independence"] = "confirmed_not_independent"
    candidate["metadata_checks"] = {
        "dataset_identity": "confirmed_match",
        "method_metadata": "unresolved",
    }
    candidate["semantic_checks"] = {
        "target_definition": "confirmed_match",
        "target_unit": "unresolved",
    }

    result = evaluate_external_source_candidate(_requirement(), candidate)

    assert result.disposition == "diagnostic_only"
    assert result.eligible_for_requirement is False
    assert result.source_independence_satisfied is False
    assert result.unresolved_metadata == ("method_metadata",)
    assert result.unresolved_semantics == ("target_unit",)


def test_confirmed_semantic_mismatch_is_scientifically_ineligible() -> None:
    candidate = _candidate()
    candidate["semantic_checks"] = {
        "target_definition": "confirmed_mismatch",
        "target_unit": "confirmed_match",
    }

    result = evaluate_external_source_candidate(_requirement(), candidate)

    assert result.disposition == "scientifically_ineligible"
    assert result.mismatches == ("target_definition",)
    assert result.model_fit_authorized is False


def test_unresolved_semantics_stop_before_acquisition() -> None:
    candidate = _candidate()
    candidate["semantic_checks"] = {
        "target_definition": "unresolved",
        "target_unit": "confirmed_match",
    }

    result = evaluate_external_source_candidate(_requirement(), candidate)

    assert result.disposition == "semantics_audit_required"
    assert result.unresolved_semantics == ("target_definition",)
    assert result.automatic_acquisition_authorized is False


def test_unresolved_provenance_is_metadata_incomplete() -> None:
    candidate = _candidate()
    candidate["source_independence"] = "unresolved"

    result = evaluate_external_source_candidate(_requirement(), candidate)

    assert result.disposition == "metadata_incomplete"
    assert result.source_independence_satisfied is False


def test_missing_required_check_fails_closed() -> None:
    candidate = copy.deepcopy(_candidate())
    metadata = candidate["metadata_checks"]
    assert isinstance(metadata, dict)
    del metadata["method_metadata"]

    with pytest.raises(ExternalEvidenceContractError, match="does not cover all required checks"):
        evaluate_external_source_candidate(_requirement(), candidate)


def test_requirement_cannot_authorize_model_fit_at_screening_stage() -> None:
    requirement = _requirement()
    requirement["model_fit_authorized"] = True

    with pytest.raises(ExternalEvidenceContractError, match="model_fit_authorized"):
        evaluate_external_source_candidate(requirement, _candidate())
