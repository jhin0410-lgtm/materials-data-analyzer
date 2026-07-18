import copy

from src.platform_core.pgir_model_contracts import (
    DIFFUSION_MODEL_CONTRACT_ID,
    PGIRModelContract,
    build_diffusion_model_contract,
    validate_pgir_model_contract,
)
from src.platform_core.scientific_operator_registry import build_default_scientific_operator_registry
from src.platform_core.scientific_relations import default_scientific_relations
from src.platform_core.units import build_default_unit_registry


def test_registered_diffusion_model_contract_is_strict_and_dimensionally_valid():
    contract = build_diffusion_model_contract()
    result = validate_pgir_model_contract(contract)

    assert contract.model_contract_id == DIFFUSION_MODEL_CONTRACT_ID
    assert result["valid"] is True
    assert result["status"] == "valid"
    assert len(result["model_contract_checksum"]) == 64
    assert contract.analytical_reference_available is True


def test_model_contract_rejects_unknown_fields_and_unsupported_schema_version():
    payload = build_diffusion_model_contract().to_dict()
    payload["unknown_runtime_expression"] = "x"
    try:
        PGIRModelContract.from_mapping(payload)
    except ValueError as exc:
        assert "unknown fields" in str(exc)
    else:
        raise AssertionError("unknown contract field was silently dropped")

    payload = build_diffusion_model_contract().to_dict()
    payload["schema_version"] = "2"
    result = validate_pgir_model_contract(payload)
    assert result["status"] == "blocked_invalid_model_contract"


def test_model_contract_rejects_unregistered_relation_and_operator():
    payload = build_diffusion_model_contract().to_dict()
    payload["governing_relation_id"] = "unregistered.relation"
    assert validate_pgir_model_contract(payload)["valid"] is False

    payload = build_diffusion_model_contract().to_dict()
    payload["operator_requirements"][0]["operator_id"] = "unregistered_operator_v1"
    result = validate_pgir_model_contract(payload)
    assert result["valid"] is False


def test_diffusion_relation_and_exact_three_operators_are_registered():
    relation_ids = {item.relation_id for item in default_scientific_relations()}
    registry = build_default_scientific_operator_registry()
    operator_ids = {item.operator_id for item in registry.list_operators()}

    assert "pgir.diffusion_1d.homogeneous_zero_dirichlet" in relation_ids
    assert {
        "one_dimensional_diffusion_exact_propagator_v1",
        "one_dimensional_diffusion_ftcs_propagator_v1",
        "one_dimensional_diffusion_benchmark_evaluator_v1",
    } <= operator_ids
    assert registry.validate()["valid"] is True


def test_builtin_unit_registry_supports_explicit_diffusivity_without_symbolic_parser():
    registry = build_default_unit_registry()
    unit = registry.get("m^2/s")

    assert unit.dimension == "diffusivity"
    assert unit.base_unit == "m^2/s"


def test_model_contract_rejects_arbitrary_execution_metadata():
    payload = build_diffusion_model_contract().to_dict()
    payload = copy.deepcopy(payload)
    payload["operator_requirements"][0]["module_path"] = "user.module"
    result = validate_pgir_model_contract(payload)
    assert result["valid"] is False
    assert "unknown fields" in result["errors"][0]
