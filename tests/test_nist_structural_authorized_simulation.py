from __future__ import annotations

import json
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop.action_registry import load_action_registry
from materials_data_analyzer.research_loop.authorized_execution import (
    AuthorizedExecutionError,
    execute_authorized_action,
)
from materials_data_analyzer.research_loop.kernel import (
    initialize_research_loop,
    load_research_state,
)
from materials_data_analyzer.research_loop.nist_structural_research import (
    ACTION_TYPE,
    ADAPTER_ID,
    assess_nist_structural_action_authorization,
    build_nist_structural_planning_state,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
OBJECTIVE = REPO_ROOT / "configs/research/nist_ambench_structural_research_objective.v1.json"
REGISTRY = REPO_ROOT / "configs/research/nist_ambench_structural_action_registry.v1.json"
SIMULATION_CONFIG = REPO_ROOT / "configs/research/nist_ambench_stage1_structural_design_simulation.v1.json"


def _request(run: Path, path: Path, *, simulation_config: Path = SIMULATION_CONFIG) -> Path:
    registry = load_action_registry(REGISTRY, repository_root=REPO_ROOT)
    value = {
        "schema_version": "1.0",
        "action_id": "nist-structural-sim-001",
        "action_type": ACTION_TYPE,
        "research_run": str(run),
        "simulation_config": str(simulation_config),
        "registry": str(REGISTRY),
        "repository_root": str(REPO_ROOT),
        "expected_registry_sha256": registry["registry_sha256"],
    }
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return path


def test_planner_authorizes_only_one_response_free_structural_simulation(tmp_path: Path) -> None:
    run = tmp_path / "run"
    initialize_research_loop(OBJECTIVE, run)

    state = build_nist_structural_planning_state(
        repository_root=REPO_ROOT,
        research_run=run,
        action_registry_path=REGISTRY,
    )
    assert state["adapter_id"] == ADAPTER_ID
    assert state["selected_action"]["action_type"] == ACTION_TYPE
    assert state["selected_action"]["category"] == "simulation"
    assert state["selected_action"]["cost_units"] == 2
    assert state["stop_state"]["status"] == "continue"
    assert state["evidence_gap"]["status"] == "structural_simulation_needed"

    authorization = assess_nist_structural_action_authorization(
        repository_root=REPO_ROOT,
        research_run=run,
        action_registry_path=REGISTRY,
    )
    assert authorization["authorization_status"] == "ready_for_explicit_execution_request"
    assert authorization["automatic_execution_authorized"] is False
    assert authorization["scientific_evidence_upgraded"] is False


def test_common_executor_runs_nist_simulation_once_and_preserves_physical_blocker(tmp_path: Path) -> None:
    run = tmp_path / "run"
    initialize_research_loop(OBJECTIVE, run)
    request = _request(run, tmp_path / "request.json")

    result = execute_authorized_action(
        ADAPTER_ID,
        repository_root=REPO_ROOT,
        research_run=run,
        action_registry_path=REGISTRY,
        request_path=request,
        expected_action_type=ACTION_TYPE,
    )

    assert result["action_type"] == ACTION_TYPE
    assert result["actions_before"] == 0
    assert result["actions_after"] == 1
    assert result["maximum_actions_executed_per_invocation"] == 1
    assert result["generic_command_execution_available"] is False
    verified = result["verified_report"]
    assert verified["valid"] is True
    assert verified["physical_evidence_requirement_satisfied"] is False
    assert verified["scientific_evidence_upgraded"] is False

    state = load_research_state(run)
    assert state["status"] == "stopped"
    assert state["stop"]["reason_code"] == "physical_evidence_required"
    assert len(state["actions"]) == 1
    assert state["actions"][0]["action_type"] == ACTION_TYPE

    output = json.loads(
        (run / "actions/nist-structural-sim-001/structural_design_simulation.json").read_text(
            encoding="utf-8"
        )
    )
    before = {item["model"]: item for item in output["before"]["models"]}
    after = {item["model"]: item for item in output["after_proposal"]["models"]}
    assert output["before"]["grid"]["total_replicates"] == 10
    assert output["after_proposal"]["grid"]["total_replicates"] == 19
    assert output["before"]["grid"]["unique_cell_count"] == 3
    assert output["after_proposal"]["grid"]["unique_cell_count"] == 6
    assert before["interaction"]["matrix_rank"] == 3
    assert after["interaction"]["matrix_rank"] == 4
    assert after["interaction"]["full_column_rank"] is True
    assert after["interaction"]["residual_degrees_of_freedom"] == 15
    assert output["scientific_boundary"]["response_values_used"] is False
    assert output["scientific_boundary"]["synthetic_response_generated"] is False
    assert output["scientific_boundary"]["predictions_generated"] is False

    terminal = build_nist_structural_planning_state(
        repository_root=REPO_ROOT,
        research_run=run,
        action_registry_path=REGISTRY,
    )
    assert terminal["selected_action"] is None
    assert terminal["stop_state"]["status"] == "terminal_for_current_scope"
    assert terminal["evidence_gap"]["status"] == "physical_evidence_required_after_structural_simulation"

    with pytest.raises(AuthorizedExecutionError):
        execute_authorized_action(
            ADAPTER_ID,
            repository_root=REPO_ROOT,
            research_run=run,
            action_registry_path=REGISTRY,
            request_path=request,
            expected_action_type=ACTION_TYPE,
        )
    assert len(load_research_state(run)["actions"]) == 1


def test_executor_rejects_simulation_config_not_selected_by_planner(tmp_path: Path) -> None:
    run = tmp_path / "run"
    initialize_research_loop(OBJECTIVE, run)
    alternate = REPO_ROOT / "configs/research/nist_ambench_structural_research_objective.v1.json"
    request = _request(run, tmp_path / "wrong-config-request.json", simulation_config=alternate)

    with pytest.raises(AuthorizedExecutionError, match="simulation_config does not match planner selection"):
        execute_authorized_action(
            ADAPTER_ID,
            repository_root=REPO_ROOT,
            research_run=run,
            action_registry_path=REGISTRY,
            request_path=request,
            expected_action_type=ACTION_TYPE,
        )
    assert load_research_state(run)["actions"] == []


def test_registry_preserves_non_empirical_simulation_boundary() -> None:
    registry = load_action_registry(REGISTRY, repository_root=REPO_ROOT)
    action = next(item for item in registry["actions"] if item["action_type"] == ACTION_TYPE)
    assert action["category"] == "simulation"
    assert action["availability"] == "available"
    assert action["cost_units"] == 2
    prohibited = set(action["prohibited_effects"])
    assert "response_value_synthesis" in prohibited
    assert "synthetic_trace_substitution" in prohibited
    assert "scientific_evidence_promotion" in prohibited
    assert "physical_acquisition_requirement_satisfaction" in prohibited
