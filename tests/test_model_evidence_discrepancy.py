from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop.action_registry import load_action_registry
from materials_data_analyzer.research_loop.authorized_execution import execute_authorized_action
from materials_data_analyzer.research_loop.heat_execution_verifier import (
    verify_heat_execution_handoff,
)
from materials_data_analyzer.research_loop.hypothesis_portfolio import (
    build_hypothesis_portfolio,
)
from materials_data_analyzer.research_loop.kernel import initialize_research_loop
from materials_data_analyzer.research_loop.model_evidence_discrepancy import (
    ModelEvidenceDiscrepancyError,
    build_model_evidence_discrepancy_report,
    validate_model_evidence_discrepancy_report,
)
from materials_data_analyzer.research_loop.scientific_simulation_registry import (
    repository_heat_conduction_contract,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_REGISTRY = (
    REPO_ROOT / "configs/research/reference_heat_conduction_action_registry.v1.json"
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _solver_request(validation_tolerance: float = 0.1) -> dict:
    return {
        "schema_version": "1.0",
        "solver_id": "heat_conduction_1d_explicit_ftcs",
        "solver_version": "1.0",
        "units": {
            "length": "m",
            "time": "s",
            "temperature": "K",
            "thermal_diffusivity": "m^2/s",
        },
        "domain": {"length_m": 1.0, "node_count": 11},
        "time": {"duration_s": 1.0, "time_step_s": 0.1},
        "material": {"thermal_diffusivity_m2_s": 0.01},
        "initial_condition": {
            "kind": "sine_mode",
            "baseline_temperature_K": 300.0,
            "amplitude_K": 10.0,
        },
        "boundary_conditions": {
            "left": {"kind": "fixed_temperature", "temperature_K": 300.0},
            "right": {"kind": "fixed_temperature", "temperature_K": 300.0},
        },
        "validation": {
            "kind": "sine_eigenmode_analytical",
            "max_abs_error_tolerance_K": validation_tolerance,
        },
    }


def _model_fixture(
    tmp_path: Path,
    *,
    validation_tolerance: float = 0.1,
) -> dict[str, object]:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "scripts").mkdir()
    (root / "scripts/run_reference_heat_conduction_action.py").write_text(
        "# bound test entrypoint\n",
        encoding="utf-8",
    )
    registry_path = root / "reference_heat_registry.json"
    registry_path.write_bytes(SOURCE_REGISTRY.read_bytes())

    objective = root / "objective.json"
    objective.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "research_id": "model-evidence-discrepancy-test",
                "question": "Can the audited reference model be compared to bound evidence?",
                "metrics": {"primary": "discrepancy_diagnosis", "secondary": []},
                "constraints": ["no automatic scientific promotion"],
                "budget": {"maximum_actions": 2, "maximum_cost_units": 2},
                "stop_rules": ["stop after bounded comparison"],
            }
        ),
        encoding="utf-8",
    )
    run = root / "run"
    initialize_research_loop(objective, run)

    solver_request = root / "solver_request.json"
    solver_request.write_text(
        json.dumps(_solver_request(validation_tolerance)),
        encoding="utf-8",
    )
    registry = load_action_registry(registry_path, repository_root=root)
    contract = repository_heat_conduction_contract()
    execution_request = root / "execution_request.json"
    execution_request.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "action_id": "heat-reference-001",
                "action_type": "reference_heat_conduction_simulation",
                "action_version": "1.0",
                "research_run": str(run),
                "solver_request": str(solver_request),
                "expected_solver_request_sha256": _sha(solver_request),
                "expected_solver_implementation_sha256": (
                    contract.implementation_module_sha256
                ),
                "registry": str(registry_path),
                "repository_root": str(root),
                "expected_registry_sha256": registry["registry_sha256"],
            }
        ),
        encoding="utf-8",
    )
    handoff = verify_heat_execution_handoff(
        repository_root=root,
        research_run=run,
        action_registry_path=registry_path,
        request_path=execution_request,
    )
    execution = execute_authorized_action(
        "reference-heat-conduction",
        repository_root=root,
        research_run=run,
        action_registry_path=registry_path,
        request_path=execution_request,
        expected_action_type=handoff["action_type"],
        expected_request_sha256=handoff["request_sha256"],
        expected_research_ledger_sha256=handoff["research_ledger_sha256"],
    )
    report_path = Path(str(execution["action_report"]))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    result_path = Path(report["solver_result"]["path"])
    result = json.loads(result_path.read_text(encoding="utf-8"))
    model_value = (
        float(result["final_temperature_K"][5])
        if isinstance(result.get("final_temperature_K"), list)
        else 300.0
    )
    return {
        "root": root,
        "run": run,
        "execution_request": execution_request,
        "report_path": report_path,
        "result_path": result_path,
        "result": result,
        "model_value": model_value,
    }


def _assessment(status: str) -> dict:
    support: list[str] = []
    contradiction: list[str] = []
    falsification: list[str] = []
    if status == "provisionally_supported":
        support = ["support-1"]
    elif status == "contradicted_within_verified_scope":
        contradiction = ["contradiction-1"]
    elif status == "falsified_within_verified_scope":
        falsification = ["falsification-1"]
    elif status == "contested":
        support = ["support-1"]
        contradiction = ["contradiction-1"]
    return {
        "node_id": "h1",
        "node_type": "hypothesis",
        "status": status,
        "verified_support_edges": support,
        "verified_contradiction_edges": contradiction,
        "verified_falsification_edges": falsification,
        "diagnostic_relation_edges": [],
        "final_positive_support_granted": False,
        "domain_closeout_required_for_positive_conclusion": (
            status == "provisionally_supported"
        ),
        "confidence_score": None,
    }


def _graph(status: str = "inconclusive") -> dict:
    assessment = _assessment(status)
    return {
        "schema_version": "1.0",
        "graph_policy_version": "1.0",
        "graph_id": "graph-model-evidence-1",
        "research_scope": "bounded model/evidence discrepancy diagnosis",
        "nodes": [
            {
                "node_id": "h1",
                "node_type": "hypothesis",
                "statement": "The model and empirical response agree in the declared regime.",
            }
        ],
        "edges": [],
        "assessments": [assessment],
        "conflict_count": int(status == "contested"),
        "falsified_count": int(status == "falsified_within_verified_scope"),
        "autonomy_boundary": {
            "proposal_relations_affect_status": False,
            "diagnostic_relations_affect_verified_status": False,
            "domain_verified_relations_require_checksum_bound_verifier_artifacts": True,
            "final_positive_support_is_automatic": False,
            "numeric_confidence_invented": False,
        },
    }


def _plan() -> dict:
    plan = {
        "schema_version": "1.0",
        "iteration_index": 1,
        "planning_budget": {"budget_units": 8.0, "minimum_utility": 0.01},
        "ranked_actions": [],
        "selected_next_action": None,
        "stop_decision": {"stop": False, "reason": "informative_action_available"},
    }
    plan["plan_sha256"] = _canonical_sha256(plan)
    return plan


def _portfolio(graph: dict) -> dict:
    return build_hypothesis_portfolio(graph, plan=_plan())


def _basis(root: Path) -> tuple[Path, Path]:
    domain = root / "domain_basis.txt"
    domain.write_text(
        "Domain-review fixture: declared 1D constant-property Dirichlet comparison scope.\n",
        encoding="utf-8",
    )
    prop = root / "property_basis.txt"
    prop.write_text(
        "Property-review fixture: explicit diffusivity basis for bounded test comparison.\n",
        encoding="utf-8",
    )
    return domain, prop


def _comparison_spec(
    root: Path,
    *,
    domain_status: str = "within_declared_scope",
    domain_authority: str = "domain_verified",
    property_authority: str = "domain_verified",
    property_sensitivity: str = "not_material",
    empirical_unit: str = "K",
    minimum_replicates: int = 2,
    protocol_id: str = "protocol-1",
) -> dict:
    domain, prop = _basis(root)
    domain_bindings = (
        [{"path": str(domain), "sha256": _sha(domain)}]
        if domain_authority == "domain_verified"
        else []
    )
    property_bindings = (
        [{"path": str(prop), "sha256": _sha(prop)}]
        if property_authority == "domain_verified"
        else []
    )
    return {
        "schema_version": "1.0",
        "target_node_id": "h1",
        "model_response": {
            "selector": "final_temperature_K",
            "index": 5,
            "response_name": "temperature",
            "unit": "K",
        },
        "empirical_response": {
            "response_name": "temperature",
            "unit": empirical_unit,
        },
        "tolerance": {
            "metric": "absolute_error",
            "value": 0.5,
            "unit": "K",
            "semantics": "absolute model/evidence difference at the declared response coordinate",
        },
        "model_domain": {
            "status": domain_status,
            "authority": domain_authority,
            "basis": "Explicitly bounded reference-model applicability assessment.",
            "bindings": domain_bindings,
        },
        "property_assessment": {
            "authority": property_authority,
            "sensitivity": property_sensitivity,
            "bindings": property_bindings,
        },
        "empirical_sufficiency": {
            "minimum_independent_replicates": minimum_replicates,
        },
        "required_context": {
            "protocol_id": protocol_id,
            "material_state_id": "state-1",
            "sample_identity": "sample-set-1",
            "conditions_id": "conditions-1",
        },
    }


def _empirical(
    root: Path,
    *,
    model_value: float,
    delta: float,
    evidence_id: str = "evidence-1",
    unit: str = "K",
    replicates: int = 2,
    independence_verified: bool = True,
    assessment_level: str = "domain_verified",
    protocol_id: str = "protocol-1",
    filename: str = "empirical.json",
) -> Path:
    path = root / filename
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "evidence_id": evidence_id,
                "target_node_id": "h1",
                "response": {
                    "name": "temperature",
                    "value": model_value + delta,
                    "unit": unit,
                },
                "independent_replicates": replicates,
                "replication_independence_verified": independence_verified,
                "provenance": {
                    "assessment_level": assessment_level,
                    "source_identity": f"source:{evidence_id}",
                    "protocol_id": protocol_id,
                    "material_state_id": "state-1",
                    "sample_identity": "sample-set-1",
                    "conditions_id": "conditions-1",
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def _build(
    model: dict[str, object],
    *,
    graph: dict | None = None,
    evidence: Path | None = None,
    spec: dict | None = None,
    portfolio: dict | None = None,
    previous_report: dict | None = None,
) -> dict:
    root = Path(model["root"])
    graph_value = graph or _graph()
    evidence_path = evidence or _empirical(
        root,
        model_value=float(model["model_value"]),
        delta=2.0,
    )
    spec_value = spec or _comparison_spec(root)
    return build_model_evidence_discrepancy_report(
        model_adapter_id="reference-heat-conduction",
        action_report_path=Path(model["report_path"]),
        execution_request_path=Path(model["execution_request"]),
        empirical_evidence_path=evidence_path,
        comparison_spec=spec_value,
        evaluated_graph=graph_value,
        target_node_id="h1",
        artifact_root=root,
        hypothesis_portfolio=portfolio,
        previous_report=previous_report,
    )


def _diagnosis_types(report: dict) -> set[str]:
    return {str(item["diagnosis_type"]) for item in report["diagnoses"]}


def test_fully_admissible_mismatch_reaches_empirical_model_discrepancy(
    tmp_path: Path,
) -> None:
    model = _model_fixture(tmp_path)
    graph = _graph()
    portfolio = _portfolio(graph)
    report = _build(model, graph=graph, portfolio=portfolio)

    assert _diagnosis_types(report) == {"empirical_model_discrepancy"}
    assert report["quantitative_comparison"]["performed"] is True
    assert report["gates"]["numerical_validity"]["passed"] is True
    assert report["gates"]["model_domain"]["passed"] is True
    assert report["gates"]["property_authority"]["passed"] is True
    assert report["gates"]["comparability"]["passed"] is True
    assert report["gates"]["empirical_sufficiency"]["passed"] is True
    assert report["ranked_next_actions"][0]["action_class"] == "discriminating_analysis"
    assert report["autonomy_boundary"]["scientific_status_changed"] is False
    assert report["autonomy_boundary"]["automatic_execution_authorized"] is False

    validation = validate_model_evidence_discrepancy_report(
        report,
        evaluated_graph=graph,
        hypothesis_portfolio=portfolio,
    )
    assert validation["report_sha256"] == report["report_sha256"]
    assert validation["artifact_bindings_reverified"] is True


def test_agreement_never_auto_confirms_hypothesis(tmp_path: Path) -> None:
    model = _model_fixture(tmp_path)
    root = Path(model["root"])
    graph = _graph()
    evidence = _empirical(
        root,
        model_value=float(model["model_value"]),
        delta=0.1,
    )
    report = _build(model, graph=graph, evidence=evidence)

    assert _diagnosis_types(report) == {"agreement_within_declared_tolerance"}
    assert report["stop_recommendation"]["positive_scientific_closeout_granted"] is False
    assert report["autonomy_boundary"]["model_agreement_confirms_hypothesis"] is False
    assert report["epistemic_assessment"]["status"] == "inconclusive"


def test_numerical_validation_failure_blocks_empirical_interpretation(
    tmp_path: Path,
) -> None:
    model = _model_fixture(tmp_path, validation_tolerance=1.0e-20)
    report = _build(model)

    assert "numerical_invalidity" in _diagnosis_types(report)
    assert "empirical_model_discrepancy" not in _diagnosis_types(report)
    assert report["quantitative_comparison"]["performed"] is False
    invalid = next(
        item
        for item in report["diagnoses"]
        if item["diagnosis_type"] == "numerical_invalidity"
    )
    assert invalid["blocks_empirical_falsification"] is True
    assert report["ranked_next_actions"][0]["action_class"] == "numerical_validation"


def test_out_of_domain_model_is_not_empirical_falsification(tmp_path: Path) -> None:
    model = _model_fixture(tmp_path)
    root = Path(model["root"])
    spec = _comparison_spec(root, domain_status="outside_declared_scope")
    report = _build(model, spec=spec)

    assert "model_domain_mismatch" in _diagnosis_types(report)
    assert "empirical_model_discrepancy" not in _diagnosis_types(report)
    assert report["quantitative_comparison"]["performed"] is False


def test_property_uncertainty_prioritizes_sensitivity_and_property_evidence(
    tmp_path: Path,
) -> None:
    model = _model_fixture(tmp_path)
    root = Path(model["root"])
    spec = _comparison_spec(
        root,
        property_authority="unverified",
        property_sensitivity="not_assessed",
    )
    report = _build(model, spec=spec)

    assert "parameter_or_property_uncertainty" in _diagnosis_types(report)
    classes = {item["action_class"] for item in report["ranked_next_actions"]}
    assert "sensitivity_analysis" in classes
    assert "external_evidence_search" in classes
    assert report["quantitative_comparison"]["performed"] is False


@pytest.mark.parametrize(
    ("evidence_protocol", "empirical_unit"),
    [
        ("different-protocol", "K"),
        ("protocol-1", "degC"),
    ],
)
def test_protocol_or_unit_drift_is_preserved_as_noncomparable(
    tmp_path: Path,
    evidence_protocol: str,
    empirical_unit: str,
) -> None:
    model = _model_fixture(tmp_path)
    root = Path(model["root"])
    evidence = _empirical(
        root,
        model_value=float(model["model_value"]),
        delta=2.0,
        unit=empirical_unit,
        protocol_id=evidence_protocol,
    )
    spec = _comparison_spec(root)
    report = _build(model, evidence=evidence, spec=spec)

    assert "provenance_or_protocol_incompatibility" in _diagnosis_types(report)
    assert "empirical_model_discrepancy" not in _diagnosis_types(report)
    assert report["gates"]["comparability"]["passed"] is False
    assert report["quantitative_comparison"]["performed"] is False


def test_insufficient_empirical_replication_remains_insufficient(
    tmp_path: Path,
) -> None:
    model = _model_fixture(tmp_path)
    root = Path(model["root"])
    evidence = _empirical(
        root,
        model_value=float(model["model_value"]),
        delta=2.0,
        replicates=1,
        independence_verified=False,
    )
    report = _build(model, evidence=evidence)

    assert "insufficient_empirical_evidence" in _diagnosis_types(report)
    assert "empirical_model_discrepancy" not in _diagnosis_types(report)
    assert report["gates"]["empirical_sufficiency"]["passed"] is False


def test_empirical_artifact_tamper_fails_report_revalidation(tmp_path: Path) -> None:
    model = _model_fixture(tmp_path)
    root = Path(model["root"])
    graph = _graph()
    evidence = _empirical(
        root,
        model_value=float(model["model_value"]),
        delta=2.0,
    )
    report = _build(model, graph=graph, evidence=evidence)
    payload = json.loads(evidence.read_text(encoding="utf-8"))
    payload["response"]["value"] += 5.0
    evidence.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(
        ModelEvidenceDiscrepancyError,
        match="empirical_evidence current bytes differ",
    ):
        validate_model_evidence_discrepancy_report(
            report,
            evaluated_graph=graph,
        )


def test_solver_result_tamper_fails_through_audited_model_verifier(
    tmp_path: Path,
) -> None:
    model = _model_fixture(tmp_path)
    graph = _graph()
    report = _build(model, graph=graph)
    result_path = Path(model["result_path"])
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    payload["final_temperature_K"][5] += 1.0
    result_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(Exception, match="solver result|immutable research-ledger|differs"):
        validate_model_evidence_discrepancy_report(
            report,
            evaluated_graph=graph,
        )


def test_target_substitution_and_portfolio_tamper_fail_closed(tmp_path: Path) -> None:
    model = _model_fixture(tmp_path)
    graph = _graph()
    portfolio = _portfolio(graph)
    report = _build(model, graph=graph, portfolio=portfolio)

    changed_graph = json.loads(json.dumps(graph))
    changed_graph["nodes"][0]["statement"] = "substituted target statement"
    with pytest.raises(
        ModelEvidenceDiscrepancyError,
        match="portfolio is not bound|target identity|statement",
    ):
        validate_model_evidence_discrepancy_report(
            report,
            evaluated_graph=changed_graph,
            hypothesis_portfolio=portfolio,
        )

    tampered_portfolio = json.loads(json.dumps(portfolio))
    tampered_portfolio["hypotheses"][0]["statement"] = "tampered"
    with pytest.raises(
        ModelEvidenceDiscrepancyError,
        match="portfolio canonical SHA-256",
    ):
        validate_model_evidence_discrepancy_report(
            report,
            evaluated_graph=graph,
            hypothesis_portfolio=tampered_portfolio,
        )


def test_recursive_handoff_preserves_ancestry_and_rediagnoses_new_evidence(
    tmp_path: Path,
) -> None:
    model = _model_fixture(tmp_path)
    root = Path(model["root"])
    graph = _graph()
    first_evidence = _empirical(
        root,
        model_value=float(model["model_value"]),
        delta=2.0,
        evidence_id="evidence-round-1",
        replicates=1,
        independence_verified=False,
        filename="empirical-round-1.json",
    )
    first = _build(model, graph=graph, evidence=first_evidence)
    assert "insufficient_empirical_evidence" in _diagnosis_types(first)
    assert first["ranked_next_actions"][0]["action_class"] == "replication"

    second_evidence = _empirical(
        root,
        model_value=float(model["model_value"]),
        delta=2.0,
        evidence_id="evidence-round-2",
        replicates=3,
        independence_verified=True,
        filename="empirical-round-2.json",
    )
    second = _build(
        model,
        graph=graph,
        evidence=second_evidence,
        previous_report=first,
    )
    assert second["iteration_index"] == 2
    assert second["ancestry"]["previous_report_sha256"] == first["report_sha256"]
    assert (
        "insufficient_empirical_evidence"
        in second["ancestry"]["prior_diagnosis_types"]
    )
    assert _diagnosis_types(second) == {"empirical_model_discrepancy"}
    assert second["quantitative_comparison"]["performed"] is True

    validation = validate_model_evidence_discrepancy_report(
        second,
        evaluated_graph=graph,
        previous_report=first,
    )
    assert validation["iteration_index"] == 2


def test_falsified_portfolio_cannot_be_reactivated_by_model_agreement(
    tmp_path: Path,
) -> None:
    model = _model_fixture(tmp_path)
    root = Path(model["root"])
    graph = _graph("falsified_within_verified_scope")
    portfolio = _portfolio(graph)
    evidence = _empirical(
        root,
        model_value=float(model["model_value"]),
        delta=0.1,
    )
    report = _build(
        model,
        graph=graph,
        evidence=evidence,
        portfolio=portfolio,
    )

    assert "agreement_within_declared_tolerance" in _diagnosis_types(report)
    assert (
        report["stop_recommendation"]["recommendation"]
        == "preserve_falsification_and_reframe"
    )
    assert report["ranked_next_actions"][0]["action_class"] == "hypothesis_reframe"
    assert report["autonomy_boundary"]["model_agreement_confirms_hypothesis"] is False


def test_previous_report_content_tamper_breaks_recursive_ancestry(tmp_path: Path) -> None:
    model = _model_fixture(tmp_path)
    root = Path(model["root"])
    graph = _graph()
    evidence = _empirical(
        root,
        model_value=float(model["model_value"]),
        delta=2.0,
        replicates=1,
        filename="empirical-first.json",
    )
    first = _build(model, graph=graph, evidence=evidence)
    first["stop_recommendation"]["rationale"] = "tampered ancestry"

    second_evidence = _empirical(
        root,
        model_value=float(model["model_value"]),
        delta=2.0,
        evidence_id="second",
        filename="empirical-second.json",
    )
    with pytest.raises(
        ModelEvidenceDiscrepancyError,
        match="previous_discrepancy_report canonical SHA-256",
    ):
        _build(
            model,
            graph=graph,
            evidence=second_evidence,
            previous_report=first,
        )
