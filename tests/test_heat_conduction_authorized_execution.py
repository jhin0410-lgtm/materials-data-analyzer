from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop.action_authorization import assess_current_action_authorization
from materials_data_analyzer.research_loop.action_registry import load_action_registry
from materials_data_analyzer.research_loop.authorized_execution import (
    AuthorizedExecutionError,
    execute_authorized_action,
)
from materials_data_analyzer.research_loop.heat_execution_verifier import verify_heat_execution_handoff
from materials_data_analyzer.research_loop.kernel import initialize_research_loop, load_research_state


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_REGISTRY = REPO_ROOT / "configs/research/reference_heat_conduction_action_registry.v1.json"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
    (root / "scripts/run_reference_heat_conduction_action.py").write_text("# bound test entrypoint\n", encoding="utf-8")
    registry_path = root / "reference_heat_registry.json"
    registry_path.write_bytes(SOURCE_REGISTRY.read_bytes())

    objective = root / "objective.json"
    objective.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "research_id": "heat-reference-test",
                "question": "Can the bounded reference heat solver reproduce its analytical benchmark?",
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
                "registry": str(registry_path),
                "repository_root": str(root),
                "expected_registry_sha256": registry["registry_sha256"],
            }
        ),
        encoding="utf-8",
    )
    return root, run, registry_path, execution_request


def test_heat_action_flows_through_planning_authorization_verifier_and_central_executor(tmp_path: Path) -> None:
    root, run, registry, request = _fixture(tmp_path)
    authorization = assess_current_action_authorization(
        "reference-heat-conduction",
        repository_root=root,
        research_run=run,
        action_registry_path=registry,
    )
    assert authorization["authorization_status"] == "ready_for_explicit_execution_request"
    assert authorization["automatic_execution_authorized"] is False

    handoff = verify_heat_execution_handoff(
        repository_root=root,
        research_run=run,
        action_registry_path=registry,
        request_path=request,
    )
    assert handoff["authorization_granted"] is False
    assert handoff["execution_performed"] is False

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
    assert result["verified_report"]["validation_state"] == "passed"
    assert result["verified_report"]["physics_solver"] is True
    assert result["empirical_validation_performed"] is False
    assert result["scientific_evidence_upgraded_by_orchestrator"] is False
    state = load_research_state(run)
    assert len(state["actions"]) == 1
    assert state["actions"][0]["action_type"] == "reference_heat_conduction_simulation"


def test_central_executor_rejects_missing_or_drifted_handoff_pins(tmp_path: Path) -> None:
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

    handoff = verify_heat_execution_handoff(
        repository_root=root,
        research_run=run,
        action_registry_path=registry,
        request_path=request,
    )
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
    with pytest.raises(Exception, match="solver request differs"):
        verify_heat_execution_handoff(
            repository_root=root,
            research_run=run,
            action_registry_path=registry,
            request_path=request,
        )
