from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop.authorized_execution import (
    AuthorizedExecutionError,
    execute_authorized_action,
)
from materials_data_analyzer.research_loop.kernel import (
    initialize_research_loop,
    load_research_state,
)
from materials_data_analyzer.research_loop.nist_authenticated_request import (
    compile_nist_authenticated_request,
    verify_nist_authenticated_request,
)
from materials_data_analyzer.research_loop.nist_structural_design_action import (
    NistStructuralDesignActionError,
)

ADAPTER = "nist-ambench-process-characterization"
ACTION = "nist_structural_design_simulation"
POLICY_ID = "nist-ambench-stage1-structural-simulation-request-v1"


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def _prepared_request(tmp_path: Path) -> tuple[Path, Path, Path, Path, dict]:
    root = _root()
    objective = root / "configs/research/nist_ambench_stage1_research_objective.v1.json"
    registry = root / "configs/research/nist_ambench_stage1_action_registry.v1.json"
    spec = root / "configs/research/nist_ambench_stage1_structural_design_simulation.v1.json"
    mission = root / "configs/research/nist_ambench_stage1_structural_mission.v1.json"
    policy = root / "configs/research/nist_ambench_stage1_request_delegation_policy.v1.json"
    run = tmp_path / "run"
    initialize_research_loop(objective, run)

    expected_mission_sha = hashlib.sha256(mission.read_bytes()).hexdigest()
    compiled_dir = tmp_path / "compiled"
    compile_nist_authenticated_request(
        repository_root=root,
        mission_path=mission,
        expected_mission_sha256=expected_mission_sha,
        policy_id=POLICY_ID,
        request_delegation_policy_path=policy,
        research_run=run,
        action_registry_path=registry,
        simulation_spec_path=spec,
        output_dir=compiled_dir,
    )
    request = compiled_dir / "execution_request.json"
    manifest = compiled_dir / "authenticated_request_manifest.json"
    verified = verify_nist_authenticated_request(
        repository_root=root,
        mission_path=mission,
        expected_mission_sha256=expected_mission_sha,
        policy_id=POLICY_ID,
        request_delegation_policy_path=policy,
        research_run=run,
        action_registry_path=registry,
        request_path=request,
        manifest_path=manifest,
    )
    return root, run, registry, request, verified


def test_nist_executor_pins_verified_request_and_preexecution_ledger(tmp_path: Path) -> None:
    root, run, registry, request, verified = _prepared_request(tmp_path)

    result = execute_authorized_action(
        ADAPTER,
        repository_root=root,
        research_run=run,
        action_registry_path=registry,
        request_path=request,
        expected_action_type=ACTION,
        expected_request_sha256=verified["request_binding"]["sha256"],
        expected_research_ledger_sha256=verified["ledger_sha256"],
    )

    assert result["action_executed"] is True
    assert result["transaction_recovered"] is False
    assert result["output_ledger_transaction"] == "cleaned"
    assert result["verifier_request_sha256_handoff_pinned"] is True
    assert result["verifier_research_ledger_sha256_handoff_pinned"] is True
    assert not (run / ".action_output_ledger_transactions").exists()


def test_nist_executor_rejects_stale_verifier_handoff_pins(tmp_path: Path) -> None:
    root, run, registry, request, verified = _prepared_request(tmp_path)

    with pytest.raises(AuthorizedExecutionError, match="execution request bytes differ"):
        execute_authorized_action(
            ADAPTER,
            repository_root=root,
            research_run=run,
            action_registry_path=registry,
            request_path=request,
            expected_action_type=ACTION,
            expected_request_sha256="0" * 64,
            expected_research_ledger_sha256=verified["ledger_sha256"],
        )

    with pytest.raises(AuthorizedExecutionError, match="research ledger changed"):
        execute_authorized_action(
            ADAPTER,
            repository_root=root,
            research_run=run,
            action_registry_path=registry,
            request_path=request,
            expected_action_type=ACTION,
            expected_request_sha256=verified["request_binding"]["sha256"],
            expected_research_ledger_sha256="0" * 64,
        )

    assert load_research_state(run)["actions"] == []
    assert not (run / ".action_output_ledger_transactions").exists()


def test_nist_executor_recovers_committed_ledger_after_verifier_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, run, registry, request, verified = _prepared_request(tmp_path)

    import materials_data_analyzer.research_loop.nist_authorized_execution as nist_execution

    original_verifier = nist_execution.verify_nist_structural_design_report_pinned

    def fail_after_commit(*args, **kwargs):
        raise NistStructuralDesignActionError("forced verifier failure after ledger commit")

    monkeypatch.setattr(
        nist_execution,
        "verify_nist_structural_design_report_pinned",
        fail_after_commit,
    )
    with pytest.raises(NistStructuralDesignActionError, match="forced verifier failure"):
        execute_authorized_action(
            ADAPTER,
            repository_root=root,
            research_run=run,
            action_registry_path=registry,
            request_path=request,
            expected_action_type=ACTION,
            expected_request_sha256=verified["request_binding"]["sha256"],
            expected_research_ledger_sha256=verified["ledger_sha256"],
        )

    failed_state = load_research_state(run)
    assert len(failed_state["actions"]) == 1
    assert (run / ".action_output_ledger_transactions").is_dir()

    monkeypatch.setattr(
        nist_execution,
        "verify_nist_structural_design_report_pinned",
        original_verifier,
    )
    recovered = execute_authorized_action(
        ADAPTER,
        repository_root=root,
        research_run=run,
        action_registry_path=registry,
        request_path=request,
        expected_action_type=ACTION,
        expected_request_sha256=verified["request_binding"]["sha256"],
        expected_research_ledger_sha256=verified["ledger_sha256"],
    )

    assert recovered["action_executed"] is False
    assert recovered["transaction_recovered"] is True
    assert recovered["transaction_recovery_stage"] == "ledger_committed"
    assert recovered["verified_report"]["valid"] is True
    assert len(load_research_state(run)["actions"]) == 1
    assert not (run / ".action_output_ledger_transactions").exists()
