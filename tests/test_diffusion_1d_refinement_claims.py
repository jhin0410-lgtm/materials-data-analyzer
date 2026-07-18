import json
from pathlib import Path

from src.platform_core.diffusion_1d_benchmark import (
    build_compact_execution_summary,
    build_trust_summary,
    evaluate_diffusion_claims,
    run_diffusion_benchmark,
    run_refinement_audit,
    validate_preserved_v2_4_1_results,
)


def _load(name):
    return json.loads(Path(name).read_text(encoding="utf-8"))


def test_predeclared_refinement_strictly_reduces_error_without_order_claim():
    audit = run_refinement_audit(_load("configs/examples/pgir_diffusion_1d_refinement_audit.json"))
    errors = [row["l2_error_final_profile"] for row in audit["cases"]]

    assert [row["case_id"] for row in audit["cases"]] == ["coarse", "medium", "fine"]
    assert errors[0] > errors[1] > errors[2]
    assert audit["fine_error_lower_than_coarse"] is True
    assert audit["exact_convergence_order_claimed"] is False
    assert len({round(row["stability_ratio"], 12) for row in audit["cases"]}) == 1


def test_claim_matrix_supports_only_bounded_benchmark_evidence():
    execution = run_diffusion_benchmark(_load("configs/examples/pgir_diffusion_1d_benchmark.json"))
    refinement = run_refinement_audit(_load("configs/examples/pgir_diffusion_1d_refinement_audit.json"))
    claims = evaluate_diffusion_claims(execution, refinement)
    matrix = {item["claim_id"]: item for item in claims["evidence"]}

    assert matrix["bounded_model_contract_execution"]["supported"] is True
    assert matrix["declared_refinement_reduces_error"]["supported"] is True
    assert matrix["battery_diffusion_mechanism"]["status"] == "prohibited"
    assert matrix["real_material_diffusivity"]["status"] == "prohibited"
    assert matrix["cross_domain_physical_operator_reuse"]["supported"] is False
    assert matrix["independent_validation"]["supported"] is False
    assert matrix["production_validation"]["supported"] is False


def test_pgir_conformance_promotes_only_bounded_result_artifacts():
    execution = run_diffusion_benchmark(_load("configs/examples/pgir_diffusion_1d_benchmark.json"))
    conformance = execution["pgir_conformance"]

    assert conformance["status"] == "bounded_pgir_execution_conformant"
    assert conformance["valid"] is True
    assert conformance["result_maturity"] == "scientifically_evaluated"
    assert all(item["valid"] for item in conformance["declarations"])
    assert all(item["transition_allowed"] for item in conformance["transitions"])
    assert conformance["capability"]["status"] == "eligible"
    assert conformance["platform_wide_independent_validation"] is False
    assert conformance["platform_wide_production_validation"] is False


def test_complete_benchmark_rerun_has_identical_execution_checksum():
    config = _load("configs/examples/pgir_diffusion_1d_benchmark.json")
    first = run_diffusion_benchmark(config)
    second = run_diffusion_benchmark(config)
    assert first["execution_checksum_sha256"] == second["execution_checksum_sha256"]


def test_trust_summary_records_physical_execution_without_cross_domain_promotion():
    execution = run_diffusion_benchmark(_load("configs/examples/pgir_diffusion_1d_benchmark.json"))
    refinement = run_refinement_audit(_load("configs/examples/pgir_diffusion_1d_refinement_audit.json"))
    trust = build_trust_summary(execution, refinement)

    assert trust["status"] == "bounded_benchmark_validated"
    assert trust["physical_operator_execution_demonstrated"] is True
    assert trust["cross_domain_physical_operator_reuse"] is False
    assert trust["independent_validation"] is False
    assert trust["production_validation"] is False


def test_compact_summary_excludes_local_field_arrays():
    execution = run_diffusion_benchmark(_load("configs/examples/pgir_diffusion_1d_benchmark.json"))
    compact = build_compact_execution_summary(execution)
    serialized = json.dumps(compact, sort_keys=True)

    assert '"values"' not in serialized
    assert "exact" not in compact
    assert "numerical" not in compact
    assert "evaluation" not in compact
    assert compact["field_arrays_tracked"] is False
    claims = evaluate_diffusion_claims(compact)
    assert claims["evidence"][0]["supported"] is True


def test_v2_4_1_canonical_artifacts_remain_preserved():
    result = validate_preserved_v2_4_1_results()
    assert result["status"] == "preserved"
    assert all(item["preserved"] for item in result["checks"])
