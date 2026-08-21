from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import materials_data_analyzer.research_loop.planning_adapter as planning
from materials_data_analyzer.research_loop.action_authorization import (
    assess_current_action_authorization,
)
from materials_data_analyzer.research_loop.action_registry import load_action_registry
from materials_data_analyzer.research_loop.authorized_execution import (
    AuthorizedExecutionError,
    execute_authorized_action,
)
from materials_data_analyzer.research_loop.heat_conduction_action import (
    HeatConductionActionError,
    verify_heat_conduction_action_report_pinned,
)
from materials_data_analyzer.research_loop.heat_execution_verifier import (
    HeatExecutionVerifierError,
    verify_heat_execution_handoff,
)
from materials_data_analyzer.research_loop.kernel import (
    initialize_research_loop,
    load_research_state,
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


def _request_record(path: Path) -> dict[str, object]:
    resolved = path.resolve(strict=True)
    data = resolved.read_bytes()
    return {
        "path": str(resolved),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def _solver_request() -> dict:
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
            "max_abs_error_tolerance_K": 0.1,
        },
    }


def _fixture(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
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
                "research_id": "heat-reference-test",
                "question": (
                    "Can the bounded reference heat solver reproduce its analytical benchmark?"
                ),
                "metrics": {"primary": "numerical_validation", "secondary": []},
                "constraints": ["no empirical validity claim"],
                "budget": {"maximum_actions": 2, "maximum_cost_units": 2},
                "stop_rules": ["stop after bounded reference action"],
            }
        ),
        encoding="utf-8",
    )
    run = root / "run"
    initialize_research_loop(objective, run)

    solver_request = root / "solver_request.json"
    solver_request.write_text(json.dumps(_solver_request()), encoding="utf-8")
    registry = load_action_registry(registry_path, repository_root=root)
    solver_contract = repository_heat_conduction_contract()
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
                    solver_contract.implementation_module_sha256
                ),
                "registry": str(registry_path),
                "repository_root": str(root),
                "expected_registry_sha256": registry["registry_sha256"],
            }
        ),
        encoding="utf-8",
    )
    return root, run, registry_path, execution_request


def _verified_handoff(
    root: Path,
    run: Path,
    registry: Path,
    request: Path,
) -> dict:
    return verify_heat_execution_handoff(
        repository_root=root,
        research_run=run,
        action_registry_path=registry,
        request_path=request,
    )


def _execute(
    root: Path,
    run: Path,
    registry: Path,
    request: Path,
) -> dict:
    handoff = _verified_handoff(root, run, registry, request)
    return execute_authorized_action(
        "reference-heat-conduction",
        repository_root=root,
        research_run=run,
        action_registry_path=registry,
        request_path=request,
        expected_action_type=handoff["action_type"],
        expected_request_sha256=handoff["request_sha256"],
        expected_research_ledger_sha256=handoff["research_ledger_sha256"],
    )


def test_heat_planning_projection_preserves_stable_schema_and_solver_pin(
    tmp_path: Path,
) -> None:
    root, run, registry, _request = _fixture(tmp_path)
    decision = planning.plan_research_next_action(
        "reference-heat-conduction",
        repository_root=root,
        research_run=run,
        action_registry_path=registry,
    )
    assert set(decision) == {
        "schema_version",
        "adapter_id",
        "adapter_version",
        "domain",
        "selection_status",
        "selected_action",
        "candidates",
        "reason",
        "evidence_level",
        "maximum_allowed_use",
        "evidence_bindings",
        "network_access_performed",
        "action_executed",
        "model_fit_performed",
        "scientific_evidence_upgraded",
        "delegated_policy_version",
    }
    assert decision["schema_version"] == "1.0"
    assert decision["selection_status"] == "ready_to_execute"
    assert decision["maximum_allowed_use"] == "numerical_reference_validation_only"
    assert decision["network_access_performed"] is False
    assert decision["action_executed"] is False
    assert decision["model_fit_performed"] is False
    assert decision["scientific_evidence_upgraded"] is False
    contract = repository_heat_conduction_contract()
    assert (
        decision["selected_action"]["expected_solver_implementation_sha256"]
        == contract.implementation_module_sha256
    )
    implementation_bindings = [
        item
        for item in decision["evidence_bindings"]
        if item.get("role") == "reference_heat_solver_implementation"
    ]
    assert len(implementation_bindings) == 1
    assert implementation_bindings[0]["sha256"] == contract.implementation_module_sha256


def test_heat_action_flows_through_planning_authorization_verifier_and_central_executor(
    tmp_path: Path,
) -> None:
    root, run, registry, request = _fixture(tmp_path)
    authorization = assess_current_action_authorization(
        "reference-heat-conduction",
        repository_root=root,
        research_run=run,
        action_registry_path=registry,
    )
    assert authorization["authorization_status"] == "ready_for_explicit_execution_request"
    assert authorization["automatic_execution_authorized"] is False
    contract = repository_heat_conduction_contract()
    assert (
        authorization["selected_action"]["expected_solver_implementation_sha256"]
        == contract.implementation_module_sha256
    )

    handoff = _verified_handoff(root, run, registry, request)
    assert handoff["authorization_granted"] is False
    assert handoff["execution_performed"] is False
    assert handoff["solver_implementation_sha256"] == contract.implementation_module_sha256

    result = execute_authorized_action(
        "reference-heat-conduction",
        repository_root=root,
        research_run=run,
        action_registry_path=registry,
        request_path=request,
        expected_action_type=handoff["action_type"],
        expected_request_sha256=handoff["request_sha256"],
        expected_research_ledger_sha256=handoff["research_ledger_sha256"],
    )
    assert result["action_executed"] is True
    assert result["verified_report"]["deterministic_recomputation_verified"] is True
    assert result["verified_report"]["ledger_artifact_binding_verified"] is True
    assert result["verified_report"]["validation_state"] == "passed"
    assert (
        result["verified_report"]["registered_outcome"]
        == "numerically_validated_reference_solution"
    )
    assert result["verified_report"]["physics_solver"] is True
    assert result["empirical_validation_performed"] is False
    assert result["scientific_evidence_upgraded_by_orchestrator"] is False
    state = load_research_state(run)
    assert len(state["actions"]) == 1
    assert state["actions"][0]["action_type"] == "reference_heat_conduction_simulation"
    assert state["actions"][0]["status"] == "completed"


def test_central_executor_rejects_missing_or_drifted_handoff_pins(
    tmp_path: Path,
) -> None:
    root, run, registry, request = _fixture(tmp_path)
    with pytest.raises(AuthorizedExecutionError, match="requires exact request"):
        execute_authorized_action(
            "reference-heat-conduction",
            repository_root=root,
            research_run=run,
            action_registry_path=registry,
            request_path=request,
            expected_action_type="reference_heat_conduction_simulation",
        )

    handoff = _verified_handoff(root, run, registry, request)
    with pytest.raises(AuthorizedExecutionError, match="request bytes differ"):
        execute_authorized_action(
            "reference-heat-conduction",
            repository_root=root,
            research_run=run,
            action_registry_path=registry,
            request_path=request,
            expected_action_type=handoff["action_type"],
            expected_request_sha256="0" * 64,
            expected_research_ledger_sha256=handoff["research_ledger_sha256"],
        )


def test_independent_verifier_detects_solver_request_tamper(tmp_path: Path) -> None:
    root, run, registry, request = _fixture(tmp_path)
    payload = json.loads(request.read_text(encoding="utf-8"))
    solver_path = Path(payload["solver_request"])
    solver = json.loads(solver_path.read_text(encoding="utf-8"))
    solver["initial_condition"]["amplitude_K"] = 12.0
    solver_path.write_text(json.dumps(solver), encoding="utf-8")
    with pytest.raises(HeatExecutionVerifierError, match="solver request differs"):
        _verified_handoff(root, run, registry, request)


def test_independent_verifier_detects_solver_implementation_pin_tamper(
    tmp_path: Path,
) -> None:
    root, run, registry, request = _fixture(tmp_path)
    payload = json.loads(request.read_text(encoding="utf-8"))
    payload["expected_solver_implementation_sha256"] = "0" * 64
    request.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(HeatExecutionVerifierError, match="solver implementation differs"):
        _verified_handoff(root, run, registry, request)


def test_numerical_validation_failure_is_retained_as_rejected_outcome(
    tmp_path: Path,
) -> None:
    root, run, registry, request = _fixture(tmp_path)
    execution = json.loads(request.read_text(encoding="utf-8"))
    solver_path = Path(execution["solver_request"])
    solver = json.loads(solver_path.read_text(encoding="utf-8"))
    solver["validation"]["max_abs_error_tolerance_K"] = 1.0e-20
    solver_path.write_text(json.dumps(solver), encoding="utf-8")
    execution["expected_solver_request_sha256"] = _sha(solver_path)
    request.write_text(json.dumps(execution), encoding="utf-8")

    result = _execute(root, run, registry, request)
    assert result["action_executed"] is True
    assert result["verified_report"]["validation_state"] == "failed"
    assert result["verified_report"]["registered_outcome"] == "numerical_validation_failed"
    assert result["scientific_evidence_upgraded_by_orchestrator"] is False
    state = load_research_state(run)
    assert len(state["actions"]) == 1
    assert state["actions"][0]["status"] == "rejected"


def test_report_tamper_cannot_be_recognized_against_immutable_ledger(
    tmp_path: Path,
) -> None:
    root, run, registry, request = _fixture(tmp_path)
    result = _execute(root, run, registry, request)
    report_path = Path(result["action_report"])
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["started_at_utc"] = "2000-01-01T00:00:00Z"
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    request_value = json.loads(request.read_text(encoding="utf-8"))
    with pytest.raises(
        HeatConductionActionError,
        match="immutable research-ledger bindings",
    ):
        verify_heat_conduction_action_report_pinned(
            report_path,
            request_value=request_value,
            request_path=request,
            request_record=_request_record(request),
        )
