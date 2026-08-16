from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop.action_authorization import (
    assess_current_action_authorization,
)
from materials_data_analyzer.research_loop.authorized_execution import (
    AuthorizedExecutionError,
    execute_authorized_action,
)
from materials_data_analyzer.research_loop.kernel import initialize_research_loop
from materials_data_analyzer.research_loop.nist_authenticated_request import (
    NistAuthenticatedRequestError,
    compile_nist_authenticated_request,
    verify_nist_authenticated_request,
)
from materials_data_analyzer.research_loop.planning_adapter import (
    plan_research_next_action,
)
from materials_data_analyzer.research_loop.planning_state import (
    build_research_planning_state,
)

ADAPTER = "nist-ambench-process-characterization"
ACTION = "nist_structural_design_simulation"


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_nist_structural_simulation_full_authenticated_typed_chain(
    tmp_path: Path,
) -> None:
    root = _root()
    objective = (
        root / "configs/research/nist_ambench_stage1_research_objective.v1.json"
    )
    registry = root / "configs/research/nist_ambench_stage1_action_registry.v1.json"
    spec = (
        root
        / "configs/research/nist_ambench_stage1_structural_design_simulation.v1.json"
    )
    mission = root / "configs/research/nist_ambench_stage1_structural_mission.v1.json"
    policy = (
        root
        / "configs/research/nist_ambench_stage1_request_delegation_policy.v1.json"
    )
    run = tmp_path / "run"
    initialize_research_loop(objective, run)

    decision = plan_research_next_action(
        ADAPTER,
        repository_root=root,
        research_run=run,
        action_registry_path=registry,
    )
    assert decision["selection_status"] == "ready_to_execute"
    assert decision["selected_action"]["action_type"] == ACTION
    assert decision["evidence_level"] == "Diagnostic"
    assert decision["maximum_allowed_use"] == "descriptive"

    state = build_research_planning_state(
        ADAPTER,
        repository_root=root,
        research_run=run,
        action_registry_path=registry,
    )
    assert state["stop_state"]["status"] == "continue"
    assert state["budget"]["actions_remaining"] == 1
    assert state["scientific_evidence_upgraded"] is False

    authorization = assess_current_action_authorization(
        ADAPTER,
        repository_root=root,
        research_run=run,
        action_registry_path=registry,
    )
    assert (
        authorization["authorization_status"]
        == "ready_for_explicit_execution_request"
    )
    assert authorization["automatic_execution_authorized"] is False

    expected_mission_sha = hashlib.sha256(mission.read_bytes()).hexdigest()
    compiled_dir = tmp_path / "compiled"
    compiled = compile_nist_authenticated_request(
        repository_root=root,
        mission_path=mission,
        expected_mission_sha256=expected_mission_sha,
        policy_id="nist-ambench-stage1-structural-simulation-request-v1",
        request_delegation_policy_path=policy,
        research_run=run,
        action_registry_path=registry,
        simulation_spec_path=spec,
        output_dir=compiled_dir,
    )
    request = compiled_dir / "execution_request.json"
    manifest = compiled_dir / "authenticated_request_manifest.json"
    assert compiled["authority_boundary"]["execution_authorized"] is False
    verified_request = verify_nist_authenticated_request(
        repository_root=root,
        mission_path=mission,
        expected_mission_sha256=expected_mission_sha,
        policy_id="nist-ambench-stage1-structural-simulation-request-v1",
        request_delegation_policy_path=policy,
        research_run=run,
        action_registry_path=registry,
        request_path=request,
        manifest_path=manifest,
    )
    assert verified_request["physical_evidence_requirement_satisfied"] is False

    execution = execute_authorized_action(
        ADAPTER,
        repository_root=root,
        research_run=run,
        action_registry_path=registry,
        request_path=request,
        expected_action_type=ACTION,
        expected_request_sha256=verified_request["request_binding"]["sha256"],
        expected_research_ledger_sha256=verified_request["ledger_sha256"],
    )
    assert execution["action_executed"] is True
    assert execution["transaction_recovered"] is False
    assert execution["output_ledger_transaction"] == "cleaned"
    assert execution["verifier_request_sha256_handoff_pinned"] is True
    assert execution["verifier_research_ledger_sha256_handoff_pinned"] is True
    assert execution["verified_report"]["valid"] is True
    assert execution["verified_report"]["required_real_trace_count"] == 9
    assert execution["verified_report"]["scientific_evidence_upgraded"] is False

    report = json.loads(
        Path(execution["action_report"]).read_text(encoding="utf-8")
    )
    assert report["physical_evidence_requirement"]["satisfied"] is False
    assert report["physical_evidence_requirement"]["required_real_trace_count"] == 9
    result = report["simulation_result"]
    assert result["simulation_spec_binding"]["sha256"] == report[
        "immutable_inputs"
    ][0]["sha256"]
    before = result["before"]["grid"]
    after = result["after_proposal"]["grid"]
    changes = {
        item["model"]: item for item in result["comparison"]["model_changes"]
    }
    assert before["total_replicates"] == 10
    assert after["total_replicates"] == 19
    assert changes["interaction"]["full_column_rank_before"] is False
    assert changes["interaction"]["full_column_rank_after"] is True
    assert changes["interaction"]["residual_df_after"] == 15
    assert changes["quadratic"]["full_column_rank_after"] is False
    assert result["scientific_boundary"]["synthetic_response_generated"] is False

    after_decision = plan_research_next_action(
        ADAPTER,
        repository_root=root,
        research_run=run,
        action_registry_path=registry,
    )
    assert after_decision["selection_status"] == "no_positive_value_action"
    assert after_decision["selected_action"] is None
    assert "nine real Stage 1 traces" in after_decision["reason"]

    after_state = build_research_planning_state(
        ADAPTER,
        repository_root=root,
        research_run=run,
        action_registry_path=registry,
    )
    assert after_state["stop_state"]["status"] == "terminal_for_current_scope"
    assert (
        after_state["evidence_gap"]["status"]
        == "physical_evidence_required_for_stronger_use"
    )
    assert after_state["claim_boundary"]["evidence_level"] == "Diagnostic"


def test_nist_request_rejects_wrong_spec_and_execution_is_not_cross_adapter(
    tmp_path: Path,
) -> None:
    root = _root()
    objective = (
        root / "configs/research/nist_ambench_stage1_research_objective.v1.json"
    )
    registry = root / "configs/research/nist_ambench_stage1_action_registry.v1.json"
    mission = root / "configs/research/nist_ambench_stage1_structural_mission.v1.json"
    policy = (
        root
        / "configs/research/nist_ambench_stage1_request_delegation_policy.v1.json"
    )
    run = tmp_path / "run"
    initialize_research_loop(objective, run)
    wrong = tmp_path / "wrong.json"
    wrong.write_text("{}\n", encoding="utf-8")
    expected_mission_sha = hashlib.sha256(mission.read_bytes()).hexdigest()

    with pytest.raises(NistAuthenticatedRequestError):
        compile_nist_authenticated_request(
            repository_root=root,
            mission_path=mission,
            expected_mission_sha256=expected_mission_sha,
            policy_id="nist-ambench-stage1-structural-simulation-request-v1",
            request_delegation_policy_path=policy,
            research_run=run,
            action_registry_path=registry,
            simulation_spec_path=wrong,
            output_dir=tmp_path / "bad",
        )

    fake_request = tmp_path / "fake.json"
    fake_request.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "action_id": "x",
                "action_type": ACTION,
                "research_run": str(run),
                "simulation_spec": str(
                    root
                    / "configs/research/nist_ambench_stage1_structural_design_simulation.v1.json"
                ),
                "expected_simulation_spec_sha256": "0" * 64,
                "registry": str(registry),
                "repository_root": str(root),
                "expected_registry_sha256": "0" * 64,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(AuthorizedExecutionError):
        execute_authorized_action(
            "nasa-battery",
            repository_root=root,
            research_run=run,
            action_registry_path=registry,
            request_path=fake_request,
            expected_action_type=ACTION,
        )
