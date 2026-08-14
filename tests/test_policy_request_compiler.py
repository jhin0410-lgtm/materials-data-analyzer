from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from materials_data_analyzer.research_loop.action_registry import load_action_registry
from materials_data_analyzer.research_loop import policy_request_compiler as compiler
from materials_data_analyzer.research_loop import policy_request_verifier as verifier


REPO_ROOT = Path(__file__).resolve().parents[1]
MISSION = REPO_ROOT / "configs/research/autonomous_materials_research_mission.v1.json"
REGISTRY = REPO_ROOT / "configs/research/nasa_research_action_registry.v1.json"
LEDGER_SHA = "a" * 64


def _mission_sha() -> str:
    return hashlib.sha256(MISSION.read_bytes()).hexdigest()


def _registry() -> dict[str, Any]:
    return load_action_registry(REGISTRY, repository_root=REPO_ROOT)


def _policy(
    tmp_path: Path,
    *,
    action_type: str = "audit_existing_battery_run",
    action_version: str = "1.0",
    max_action_cost: int = 2,
    network_access: bool = False,
) -> Path:
    path = tmp_path / "delegation.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "policy_id": "test-bounded-local-delegation",
                "mission_binding": {
                    "path": str(MISSION),
                    "sha256": _mission_sha(),
                },
                "adapter_id": "nasa-battery",
                "allowed_actions": [
                    {
                        "action_type": action_type,
                        "action_version": action_version,
                        "max_cost_units": max_action_cost,
                    }
                ],
                "max_cost_units_per_request": max(max_action_cost, 1),
                "network_access": network_access,
                "physical_experiment_execution": False,
                "generic_command_execution": False,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _authorization(
    *,
    action_type: str = "audit_existing_battery_run",
    action_version: str = "1.0",
    cost_units: int = 2,
) -> dict[str, Any]:
    registry = _registry()
    return {
        "authorization_status": "ready_for_explicit_execution_request",
        "selected_action": {
            "action_type": action_type,
            "action_version": action_version,
            "availability": "available",
            "cost_units": cost_units,
            "execution_registry_id": registry["registry_id"],
            "execution_registry_path": str(REGISTRY),
            "execution_registry_sha256": registry["registry_sha256"],
        },
    }


def _state(ledger_sha: str = LEDGER_SHA) -> dict[str, Any]:
    return {
        "ledger_sha256": ledger_sha,
        "actions": [],
    }


def _patch_current_state(
    monkeypatch: pytest.MonkeyPatch,
    *,
    authorization: dict[str, Any] | None = None,
    state: dict[str, Any] | None = None,
) -> None:
    auth = authorization or _authorization()
    research_state = state or _state()
    monkeypatch.setattr(
        compiler,
        "assess_current_action_authorization",
        lambda *args, **kwargs: auth,
    )
    monkeypatch.setattr(
        verifier,
        "assess_current_action_authorization",
        lambda *args, **kwargs: auth,
    )
    monkeypatch.setattr(compiler, "load_research_state", lambda *args, **kwargs: research_state)
    monkeypatch.setattr(verifier, "load_research_state", lambda *args, **kwargs: research_state)


def _compile_audit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[dict[str, Any], Path, Path, Path, Path]:
    _patch_current_state(monkeypatch)
    policy = _policy(tmp_path)
    research_run = tmp_path / "research-run"
    research_run.mkdir()
    analysis_run = tmp_path / "analysis-run"
    analysis_run.mkdir()
    output = tmp_path / "compiled-request"
    result = compiler.compile_policy_authorized_request(
        "nasa-battery",
        repository_root=REPO_ROOT,
        mission_path=MISSION,
        delegation_policy_path=policy,
        research_run=research_run,
        action_registry_path=REGISTRY,
        output_dir=output,
        action_inputs={"analysis_run": analysis_run},
    )
    return result, policy, research_run, analysis_run, output


def test_compiler_authors_exact_audit_request_without_human_acknowledgement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result, policy, research_run, analysis_run, output = _compile_audit(
        tmp_path,
        monkeypatch,
    )
    request_path = output / "execution_request.json"
    manifest_path = output / "policy_request_manifest.json"
    request = json.loads(request_path.read_text(encoding="utf-8"))

    assert request == {
        "schema_version": "1.0",
        "action_id": request["action_id"],
        "action_type": "audit_existing_battery_run",
        "research_run": str(research_run.resolve()),
        "analysis_run": str(analysis_run.resolve()),
        "registry": str(REGISTRY.resolve()),
        "repository_root": str(REPO_ROOT.resolve()),
        "expected_registry_sha256": _registry()["registry_sha256"],
    }
    assert "operator_acknowledgement" not in request
    assert request["action_id"].startswith("policy-")
    assert result["autonomy_boundary"]["execution_authorized_by_compiler"] is False
    assert result["autonomy_boundary"]["human_acknowledgement_generated"] is False

    verified = verifier.verify_policy_authorized_request(
        "nasa-battery",
        repository_root=REPO_ROOT,
        mission_path=MISSION,
        delegation_policy_path=policy,
        research_run=research_run,
        action_registry_path=REGISTRY,
        request_path=request_path,
        manifest_path=manifest_path,
    )
    assert verified["verification_status"] == "authorized_for_existing_typed_executor"
    assert verified["automatic_execution_permitted_under_delegation"] is True
    assert verified["action_executed"] is False
    assert verified["scientific_evidence_upgraded"] is False


def test_compiler_refuses_to_guess_action_specific_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_current_state(monkeypatch)
    policy = _policy(tmp_path)
    research_run = tmp_path / "research-run"
    research_run.mkdir()

    with pytest.raises(
        compiler.PolicyRequestInputBindingRequired,
        match="compiler will not guess: analysis_run",
    ):
        compiler.compile_policy_authorized_request(
            "nasa-battery",
            repository_root=REPO_ROOT,
            mission_path=MISSION,
            delegation_policy_path=policy,
            research_run=research_run,
            action_registry_path=REGISTRY,
            output_dir=tmp_path / "out",
        )


def test_compiler_hard_denies_model_evaluation_even_if_policy_lists_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authorization = _authorization(
        action_type="run_fixed_battery_intelligence",
        action_version="1.0",
        cost_units=10,
    )
    _patch_current_state(monkeypatch, authorization=authorization)
    policy = _policy(
        tmp_path,
        action_type="run_fixed_battery_intelligence",
        max_action_cost=10,
    )
    research_run = tmp_path / "research-run"
    research_run.mkdir()

    with pytest.raises(compiler.PolicyRequestCompilerError, match="hard-denied"):
        compiler.compile_policy_authorized_request(
            "nasa-battery",
            repository_root=REPO_ROOT,
            mission_path=MISSION,
            delegation_policy_path=policy,
            research_run=research_run,
            action_registry_path=REGISTRY,
            output_dir=tmp_path / "out",
        )


def test_compiler_refuses_typed_executor_when_runtime_registry_is_still_planned(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authorization = _authorization(
        action_type="target_reference_sensitivity",
        action_version="1.0",
        cost_units=4,
    )
    _patch_current_state(monkeypatch, authorization=authorization)
    policy = _policy(
        tmp_path,
        action_type="target_reference_sensitivity",
        max_action_cost=4,
    )
    research_run = tmp_path / "research-run"
    research_run.mkdir()
    analysis_run = tmp_path / "analysis-run"
    analysis_run.mkdir()

    with pytest.raises(
        compiler.PolicyRequestCompilerError,
        match="runtime registry action is not available",
    ):
        compiler.compile_policy_authorized_request(
            "nasa-battery",
            repository_root=REPO_ROOT,
            mission_path=MISSION,
            delegation_policy_path=policy,
            research_run=research_run,
            action_registry_path=REGISTRY,
            output_dir=tmp_path / "out",
            action_inputs={"analysis_run": analysis_run},
        )


def test_compiler_refuses_delegation_that_enables_network_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_current_state(monkeypatch)
    policy = _policy(tmp_path, network_access=True)
    research_run = tmp_path / "research-run"
    research_run.mkdir()
    analysis_run = tmp_path / "analysis-run"
    analysis_run.mkdir()

    with pytest.raises(
        compiler.PolicyRequestCompilerError,
        match="network_access=false",
    ):
        compiler.compile_policy_authorized_request(
            "nasa-battery",
            repository_root=REPO_ROOT,
            mission_path=MISSION,
            delegation_policy_path=policy,
            research_run=research_run,
            action_registry_path=REGISTRY,
            output_dir=tmp_path / "out",
            action_inputs={"analysis_run": analysis_run},
        )


def test_verifier_rejects_request_mutation_after_compilation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, policy, research_run, _, output = _compile_audit(tmp_path, monkeypatch)
    request_path = output / "execution_request.json"
    manifest_path = output / "policy_request_manifest.json"
    request = json.loads(request_path.read_text(encoding="utf-8"))
    request["action_id"] = "policy-tampered"
    request_path.write_text(json.dumps(request, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(
        verifier.PolicyRequestVerificationError,
        match="manifest request checksum mismatch",
    ):
        verifier.verify_policy_authorized_request(
            "nasa-battery",
            repository_root=REPO_ROOT,
            mission_path=MISSION,
            delegation_policy_path=policy,
            research_run=research_run,
            action_registry_path=REGISTRY,
            request_path=request_path,
            manifest_path=manifest_path,
        )


def test_verifier_rejects_research_ledger_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, policy, research_run, _, output = _compile_audit(tmp_path, monkeypatch)
    monkeypatch.setattr(
        verifier,
        "load_research_state",
        lambda *args, **kwargs: _state("b" * 64),
    )

    with pytest.raises(
        verifier.PolicyRequestVerificationError,
        match="research ledger changed after request compilation",
    ):
        verifier.verify_policy_authorized_request(
            "nasa-battery",
            repository_root=REPO_ROOT,
            mission_path=MISSION,
            delegation_policy_path=policy,
            research_run=research_run,
            action_registry_path=REGISTRY,
            request_path=output / "execution_request.json",
            manifest_path=output / "policy_request_manifest.json",
        )


def test_verifier_rejects_selected_action_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, policy, research_run, _, output = _compile_audit(tmp_path, monkeypatch)
    drifted = _authorization(
        action_type="run_fixed_battery_intelligence",
        action_version="1.0",
        cost_units=10,
    )
    monkeypatch.setattr(
        verifier,
        "assess_current_action_authorization",
        lambda *args, **kwargs: drifted,
    )

    with pytest.raises(
        verifier.PolicyRequestVerificationError,
        match="outside independent safe allowlist",
    ):
        verifier.verify_policy_authorized_request(
            "nasa-battery",
            repository_root=REPO_ROOT,
            mission_path=MISSION,
            delegation_policy_path=policy,
            research_run=research_run,
            action_registry_path=REGISTRY,
            request_path=output / "execution_request.json",
            manifest_path=output / "policy_request_manifest.json",
        )


def test_verifier_rejects_duplicate_request_json_keys(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, policy, research_run, _, output = _compile_audit(tmp_path, monkeypatch)
    request_path = output / "execution_request.json"
    manifest_path = output / "policy_request_manifest.json"
    request_path.write_text(
        '{"schema_version":"1.0","schema_version":"1.0"}\n',
        encoding="utf-8",
    )

    with pytest.raises(
        verifier.PolicyRequestVerificationError,
        match="duplicate JSON key",
    ):
        verifier.verify_policy_authorized_request(
            "nasa-battery",
            repository_root=REPO_ROOT,
            mission_path=MISSION,
            delegation_policy_path=policy,
            research_run=research_run,
            action_registry_path=REGISTRY,
            request_path=request_path,
            manifest_path=manifest_path,
        )


def test_compiler_refuses_existing_output_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_current_state(monkeypatch)
    policy = _policy(tmp_path)
    research_run = tmp_path / "research-run"
    research_run.mkdir()
    analysis_run = tmp_path / "analysis-run"
    analysis_run.mkdir()
    output = tmp_path / "out"
    output.mkdir()

    with pytest.raises(compiler.PolicyRequestCompilerError, match="output_dir already exists"):
        compiler.compile_policy_authorized_request(
            "nasa-battery",
            repository_root=REPO_ROOT,
            mission_path=MISSION,
            delegation_policy_path=policy,
            research_run=research_run,
            action_registry_path=REGISTRY,
            output_dir=output,
            action_inputs={"analysis_run": analysis_run},
        )
