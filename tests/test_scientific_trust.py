from src.platform_core.run_registry import get_scientific_trust_evaluation, store_scientific_trust_evaluation
from src.platform_core.scientific_execution import (
    ScientificExecutionRequest,
    execute_scientific_request,
    get_scientific_execution,
    persist_scientific_execution,
)
from src.platform_core.scientific_feature_registry import build_default_scientific_feature_registry
from src.platform_core.scientific_trust import (
    classify_constraint_roles,
    constraint_role_snapshot,
    evaluate_feature_candidate_against_execution,
    evaluate_scientific_trust,
)


def _bragg_request():
    return ScientificExecutionRequest.from_config(
        {
            "execution_id": "trust_bragg",
            "knowledge_pack_id": "xrd_crystallography_basic_v1",
            "constraint_ids": ["xrd.bragg.geometry"],
            "inputs": [
                {"variable_id": "two_theta", "value": 44.7, "unit": "degree"},
                {"variable_id": "wavelength", "value": 1.5406, "unit": "angstrom"},
            ],
            "requested_claim_ids": ["dimensionally_consistent", "phase_identification_supported"],
            "persist_findings": True,
        }
    )


def _persisted_bragg(tmp_path):
    request = _bragg_request()
    result = execute_scientific_request(request)
    registry_path = "outputs/platform_registry/trust.sqlite3"
    persist_scientific_execution(request, result, repo_root=tmp_path, registry_path=registry_path)
    return get_scientific_execution("trust_bragg", repo_root=tmp_path, registry_path=registry_path), registry_path


def test_scientific_trust_evidence_levels_and_claim_boundaries(tmp_path):
    execution, _ = _persisted_bragg(tmp_path)

    evaluation = evaluate_scientific_trust(execution)
    payload = evaluation.to_dict()
    claims = {row["claim_id"]: row["status"] for row in payload["claim_boundaries"]}

    assert payload["evidence_level"] == "bounded_quantity_estimated"
    assert claims["lattice_spacing_estimated"] == "supported_with_limits"
    assert claims["physics_informed_feature_available"] == "supported_with_limits"
    assert claims["physics_informed_feature_used"] == "prohibited"
    assert claims["phase_identification_supported"] == "prohibited"
    assert claims["particle_size_estimated"] == "prohibited"
    assert "independently_validated" not in payload["allowed_claims"]


def test_feature_eligibility_uses_execution_variables_without_computing_values(tmp_path):
    execution, _ = _persisted_bragg(tmp_path)
    registry = build_default_scientific_feature_registry()

    bragg = evaluate_feature_candidate_against_execution(registry.get("xrd.bragg_d_spacing"), execution)
    scherrer = evaluate_feature_candidate_against_execution(registry.get("xrd.scherrer_crystallite_size"), execution)

    assert bragg.eligibility_status == "eligible_bounded"
    assert scherrer.eligibility_status == "unavailable_missing_variable"
    assert "missing_variable:fwhm" in scherrer.reason_codes


def test_constraint_role_classification_rejects_hard_battery_monotonic_model_constraint():
    registry = build_default_scientific_feature_registry().constraint_registry
    cycle = registry.get("battery.cycle_index.non_decreasing")
    arrhenius = registry.get("battery.temperature.arrhenius_domain")

    cycle_roles = {row.role for row in classify_constraint_roles(cycle)}
    arrhenius_rows = classify_constraint_roles(arrhenius)

    assert "validation_only" in cycle_roles
    assert any(row.role == "model_constraint_candidate" and row.eligibility_status == "blocked_invalid_assumption" for row in arrhenius_rows)


def test_scientific_trust_persistence_is_idempotent(tmp_path):
    execution, registry_path = _persisted_bragg(tmp_path)
    payload = evaluate_scientific_trust(execution).to_dict()

    first = store_scientific_trust_evaluation(payload, repo_root=tmp_path, registry_path=registry_path)
    second = store_scientific_trust_evaluation(payload, repo_root=tmp_path, registry_path=registry_path)
    stored = get_scientific_trust_evaluation(payload["evaluation_id"], repo_root=tmp_path, registry_path=registry_path)

    assert first["status"] == "stored"
    assert second["status"] == "idempotent"
    assert stored["evaluation"]["evidence_level"] == "bounded_quantity_estimated"
    assert stored["feature_eligibility"]
    assert stored["claim_boundaries"]


def test_constraint_role_snapshot_is_machine_readable():
    registry = build_default_scientific_feature_registry().constraint_registry
    snapshot = constraint_role_snapshot(registry)

    assert any(row["constraint_id"] == "xrd.bragg.geometry" and row["role"] == "derived_feature_candidate" for row in snapshot)
    assert any(row["constraint_id"] == "materials.composition_fraction.sum_to_one" and row["role"] == "post_prediction_check" for row in snapshot)
