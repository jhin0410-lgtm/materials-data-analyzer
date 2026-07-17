import json
from pathlib import Path

import pytest

from src.platform_core.pgir_conformance import (
    PGIRRepresentationDeclaration,
    assess_maturity,
    check_context_compatibility,
    conformance_summary,
    evaluate_capability,
    validate_declaration,
    validate_transition,
)


def _declaration(**overrides):
    payload = {
        "declaration_id": "battery_observation_demo",
        "declaration_version": "1",
        "pgir_concept_id": "observation",
        "representation_schema_id": "battery_cycle_observation_schema_v1",
        "representation_schema_version": "1",
        "entity_or_artifact_ref": "battery_obs_B0005_00001",
        "domain_context": "battery",
        "measurement_context": "cycle_discharge_summary",
        "temporal_context": "ordered_cycle_index",
        "current_maturity_level": "dimensionally_valid",
        "claimed_capabilities": ["tabular_summary"],
        "evidence_refs": ["schema_validation", "source_field_mapping", "units_available_or_dimensionless"],
        "uncertainty_refs": ["source_uncertainty_unavailable"],
    }
    payload.update(overrides)
    return PGIRRepresentationDeclaration.from_mapping(payload)


def test_representation_declaration_validates_registered_concept_and_schema():
    declaration = _declaration()

    findings = validate_declaration(declaration)

    assert findings == ()


def test_unknown_schema_and_missing_context_are_blockers():
    declaration = _declaration(
        representation_schema_id="missing_schema_v1",
        measurement_context="unavailable",
    )

    finding_ids = {finding.finding_id for finding in validate_declaration(declaration)}

    assert {"unknown_schema", "missing_measurement_context"} <= finding_ids


def test_maturity_aliases_are_normalized_and_jump_requires_evidence():
    declaration = _declaration(current_maturity_level="L2")

    assessment = assess_maturity(declaration, requested_maturity_level="L5", evidence={"schema_validation": True})

    assert assessment.current_maturity_level == "schema_valid"
    assert assessment.requested_maturity_level == "physically_admissible"
    assert assessment.promotion_allowed is False
    assert "registered_admissibility_checks" in assessment.missing_evidence


def test_global_confidence_is_not_maturity_evidence():
    declaration = _declaration(evidence_refs=["global_confidence_score_0_91"])

    finding_ids = {finding.finding_id for finding in validate_declaration(declaration)}

    assert "global_confidence_score_rejected" in finding_ids


def test_observation_cannot_be_reused_as_latent_state_or_internal_field():
    declaration = _declaration()

    state_result = check_context_compatibility(declaration, {"requested_concept": "state"})
    field_result = check_context_compatibility(
        declaration,
        {"context_id": "internal_concentration_field", "mechanism_context": "particle_diffusion"},
    )

    assert state_result.status == "prohibited_reuse"
    assert field_result.status == "prohibited_reuse"
    assert {finding.finding_id for finding in state_result.findings} == {"observation_not_state"}


def test_transition_requires_registered_transformer_and_correct_context():
    missing = validate_transition({"transition_id": "ad_hoc_observation_to_state"})
    latent_state = validate_transition(
        {
            "transition_id": "battery_cycle_observation_to_operational_state_v1",
            "metadata_available": ["cycle_index", "capacity_observation", "unit_metadata"],
            "output_context": "latent_electrochemical_state",
        }
    )
    allowed = validate_transition(
        {
            "transition_id": "battery_cycle_observation_to_operational_state_v1",
            "metadata_available": ["cycle_index", "capacity_observation", "unit_metadata"],
            "output_context": "operational_state_summary",
        }
    )

    assert missing.transition_allowed is False
    assert latent_state.transition_allowed is False
    assert allowed.transition_allowed is True


def test_capability_gate_blocks_lower_maturity_and_unknown_capability():
    low = _declaration(current_maturity_level="semantically_mapped")

    blocked = evaluate_capability(low, "bounded_physical_validation")
    unknown = evaluate_capability(low, "production_ready")

    assert blocked.status == "blocked_low_maturity"
    assert unknown.status == "blocked_unknown_capability"


def test_conformance_summary_counts_blockers():
    declaration = _declaration(evidence_refs=["global_confidence_score"])
    context_result = check_context_compatibility(declaration, {"requested_concept": "state"})
    summary = conformance_summary((declaration,), context_results=(context_result,))

    assert summary.valid is False
    assert summary.incompatible_context_count == 1
    assert summary.to_dict()["execution_boundary"]["model_or_solver_executed"] is False


def test_example_declaration_config_validates_without_credentials_or_absolute_paths():
    path = Path("configs/examples/pgir_representation_conformance.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    declaration = PGIRRepresentationDeclaration.from_mapping(payload["declaration"])

    assert validate_declaration(declaration) == ()
    assert ("C:" + "/") not in path.read_text(encoding="utf-8")
    assert ("MP_" + "API_KEY") not in path.read_text(encoding="utf-8")
