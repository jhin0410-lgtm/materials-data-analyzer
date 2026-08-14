from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from materials_data_analyzer.research_loop.action_registry import (
    describe_action,
    load_action_registry,
)
from materials_data_analyzer.research_loop import policy_request_compiler as compiler
from materials_data_analyzer.research_loop import policy_request_verifier as verifier


REPO_ROOT = Path(__file__).resolve().parents[1]
MISSION = REPO_ROOT / "configs/research/autonomous_materials_research_mission.v1.json"
PLANNING = REPO_ROOT / "configs/research/nasa_research_action_registry.v1.json"
TARGET = REPO_ROOT / "configs/research/nasa_target_reference_action_registry.v1.json"
PROTOCOL = REPO_ROOT / "configs/research/nasa_protocol_stratification_action_registry.v1.json"
EXTERNAL = REPO_ROOT / "configs/research/nasa_external_data_requirement_action_registry.v1.json"
LEDGER_SHA = "a" * 64


def _mission_sha() -> str:
    return hashlib.sha256(MISSION.read_bytes()).hexdigest()


def _registry(path: Path) -> dict[str, Any]:
    return load_action_registry(path, repository_root=REPO_ROOT)


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
    execution_registry_path: Path = PLANNING,
) -> dict[str, Any]:
    registry = _registry(execution_registry_path)
    contract = describe_action(registry, action_type)
    selected = {
        "action_type": action_type,
        "action_version": contract["version"],
        "availability": contract["availability"],
        "cost_units": contract["cost_units"],
        "execution_registry_id": registry["registry_id"],
        "execution_registry_path": str(execution_registry_path.resolve()),
        "execution_registry_sha256": registry["registry_sha256"],
    }
    return {
        "authorization_status": "ready_for_explicit_execution_request",
        "selected_action": selected,
        "execution_contract": {
            "registry_id": registry["registry_id"],
            "registry_sha256": registry["registry_sha256"],
            "registry_path": str(execution_registry_path.resolve()),
            "action_type": action_type,
            "action_version": contract["version"],
            "category": contract["category"],
            "cost_units": contract["cost_units"],
            "binding": dict(contract["binding"]),
            "verifier_checks": list(contract["verifier_checks"]),
            "prohibited_effects": list(contract["prohibited_effects"]),
        },
    }


def _hard_denied_authorization() -> dict[str, Any]:
    audit = _authorization()
    selected = dict(audit["selected_action"])
    selected.update(
        action_type="run_fixed_battery_intelligence",
        action_version="1.0",
        cost_units=10,
    )
    return {**audit, "selected_action": selected}


def _state(ledger_sha: str = LEDGER_SHA) -> dict[str, Any]:
    return {"ledger_sha256": ledger_sha, "actions": []}


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
    monkeypatch.setattr(
        compiler,
        "load_research_state",
        lambda *args, **kwargs: research_state,
    )
    monkeypatch.setattr(
        verifier,
        "load_research_state",
        lambda *args, **kwargs: research_state,
    )


def _compile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    action_type: str,
    execution_registry: Path,
    cost: int,
    action_inputs: dict[str, Path] | None,
) -> tuple[dict[str, Any], Path, Path, Path]:
    auth = _authorization(
        action_type=action_type,
        execution_registry_path=execution_registry,
    )
    _patch_current_state(monkeypatch, authorization=auth)
    policy = _policy(
        tmp_path,
        action_type=action_type,
        max_action_cost=cost,
    )
    research_run = tmp_path / "research-run"
    research_run.mkdir()
    output = tmp_path / "compiled-request"
    result = compiler.compile_policy_authorized_request(
        "nasa-battery",
        repository_root=REPO_ROOT,
        mission_path=MISSION,
        delegation_policy_path=policy,
        research_run=research_run,
        action_registry_path=PLANNING,
        output_dir=output,
        action_inputs=action_inputs,
    )
    return result, policy, research_run, output


def _verify(
    policy: Path,
    research_run: Path,
    output: Path,
) -> dict[str, Any]:
    return verifier.verify_policy_authorized_request(
        "nasa-battery",
        repository_root=REPO_ROOT,
        mission_path=MISSION,
        delegation_policy_path=policy,
        research_run=research_run,
        action_registry_path=PLANNING,
        request_path=output / "execution_request.json",
        manifest_path=output / "policy_request_manifest.json",
    )


def test_audit_request_uses_explicit_registry_to_executor_input_alias(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis = tmp_path / "analysis"
    analysis.mkdir()
    result, policy, research_run, output = _compile(
        tmp_path,
        monkeypatch,
        action_type="audit_existing_battery_run",
        execution_registry=PLANNING,
        cost=2,
        action_inputs={"analysis_run": analysis},
    )
    request = json.loads((output / "execution_request.json").read_text())
    assert request["registry"] == str(PLANNING.resolve())
    assert request["analysis_run"] == str(analysis.resolve())
    assert "operator_acknowledgement" not in request
    assert result["registry_input_aliases"] == {"run_output": "analysis_run"}
    assert result["autonomy_boundary"]["execution_authorized_by_compiler"] is False

    verified = _verify(policy, research_run, output)
    assert verified["verification_status"] == "authorized_for_existing_typed_executor"
    assert verified["action_executed"] is False
    assert verified["scientific_evidence_upgraded"] is False


@pytest.mark.parametrize(
    ("action_type", "registry", "cost", "input_names"),
    [
        ("target_reference_sensitivity", TARGET, 4, ("analysis_run",)),
        ("protocol_stratification", PROTOCOL, 5, ("import_run", "analysis_run")),
    ],
)
def test_execution_registry_override_can_compile_when_current_planner_selected_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    action_type: str,
    registry: Path,
    cost: int,
    input_names: tuple[str, ...],
) -> None:
    inputs: dict[str, Path] = {}
    for name in input_names:
        path = tmp_path / name
        path.mkdir()
        inputs[name] = path
    result, policy, research_run, output = _compile(
        tmp_path,
        monkeypatch,
        action_type=action_type,
        execution_registry=registry,
        cost=cost,
        action_inputs=inputs,
    )
    request = json.loads((output / "execution_request.json").read_text())
    assert request["registry"] == str(registry.resolve())
    assert result["planning_registry_binding"]["path"] == str(PLANNING.resolve())
    assert result["execution_registry_binding"]["path"] == str(registry.resolve())

    verified = _verify(policy, research_run, output)
    assert verified["action_type"] == action_type
    assert verified["execution_registry_binding"]["path"] == str(registry.resolve())


def test_external_requirement_compiles_only_as_existing_typed_source_script_surface(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result, policy, research_run, output = _compile(
        tmp_path,
        monkeypatch,
        action_type="external_data_requirement_generation",
        execution_registry=EXTERNAL,
        cost=2,
        action_inputs=None,
    )
    request = json.loads((output / "execution_request.json").read_text())
    assert request["registry"] == str(EXTERNAL.resolve())
    assert result["registry_input_aliases"] == {}
    assert result["autonomy_boundary"]["network_access_authorized"] is False
    assert result["autonomy_boundary"]["generic_command_execution_authorized"] is False

    verified = _verify(policy, research_run, output)
    assert verified["action_type"] == "external_data_requirement_generation"
    assert verified["network_access_authorized"] is False
    assert verified["generic_command_execution_authorized"] is False


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
            action_registry_path=PLANNING,
            output_dir=tmp_path / "out",
        )


def test_compiler_hard_denies_model_evaluation_even_when_policy_lists_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_current_state(monkeypatch, authorization=_hard_denied_authorization())
    policy = _policy(
        tmp_path,
        action_type="run_fixed_battery_intelligence",
        max_action_cost=10,
    )
    run = tmp_path / "research-run"
    run.mkdir()
    with pytest.raises(compiler.PolicyRequestCompilerError, match="hard-denied"):
        compiler.compile_policy_authorized_request(
            "nasa-battery",
            repository_root=REPO_ROOT,
            mission_path=MISSION,
            delegation_policy_path=policy,
            research_run=run,
            action_registry_path=PLANNING,
            output_dir=tmp_path / "out",
        )


def test_compiler_rejects_network_capability_in_delegation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_current_state(monkeypatch)
    policy = _policy(tmp_path, network_access=True)
    run = tmp_path / "research-run"
    run.mkdir()
    analysis = tmp_path / "analysis"
    analysis.mkdir()
    with pytest.raises(compiler.PolicyRequestCompilerError, match="network_access=false"):
        compiler.compile_policy_authorized_request(
            "nasa-battery",
            repository_root=REPO_ROOT,
            mission_path=MISSION,
            delegation_policy_path=policy,
            research_run=run,
            action_registry_path=PLANNING,
            output_dir=tmp_path / "out",
            action_inputs={"analysis_run": analysis},
        )


def test_verifier_rejects_request_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis = tmp_path / "analysis"
    analysis.mkdir()
    _, policy, run, output = _compile(
        tmp_path,
        monkeypatch,
        action_type="audit_existing_battery_run",
        execution_registry=PLANNING,
        cost=2,
        action_inputs={"analysis_run": analysis},
    )
    request_path = output / "execution_request.json"
    request = json.loads(request_path.read_text())
    request["action_id"] = "policy-tampered"
    request_path.write_text(json.dumps(request, indent=2) + "\n")
    with pytest.raises(
        verifier.PolicyRequestVerificationError,
        match="manifest request checksum mismatch",
    ):
        _verify(policy, run, output)


def test_verifier_rejects_ledger_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis = tmp_path / "analysis"
    analysis.mkdir()
    _, policy, run, output = _compile(
        tmp_path,
        monkeypatch,
        action_type="audit_existing_battery_run",
        execution_registry=PLANNING,
        cost=2,
        action_inputs={"analysis_run": analysis},
    )
    monkeypatch.setattr(
        verifier,
        "load_research_state",
        lambda *args, **kwargs: _state("b" * 64),
    )
    with pytest.raises(
        verifier.PolicyRequestVerificationError,
        match="research ledger changed after request compilation",
    ):
        _verify(policy, run, output)


def test_verifier_rejects_selected_execution_registry_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis = tmp_path / "analysis"
    analysis.mkdir()
    _, policy, run, output = _compile(
        tmp_path,
        monkeypatch,
        action_type="audit_existing_battery_run",
        execution_registry=PLANNING,
        cost=2,
        action_inputs={"analysis_run": analysis},
    )
    monkeypatch.setattr(
        verifier,
        "assess_current_action_authorization",
        lambda *args, **kwargs: _authorization(
            action_type="target_reference_sensitivity",
            execution_registry_path=TARGET,
        ),
    )
    with pytest.raises(
        verifier.PolicyRequestVerificationError,
        match=r"manifest\.execution_registry_binding path mismatch|manifest selected-action fingerprint mismatch",
    ):
        _verify(policy, run, output)


def test_verifier_rejects_manifest_registry_raw_byte_binding_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis = tmp_path / "analysis"
    analysis.mkdir()
    _, policy, run, output = _compile(
        tmp_path,
        monkeypatch,
        action_type="audit_existing_battery_run",
        execution_registry=PLANNING,
        cost=2,
        action_inputs={"analysis_run": analysis},
    )
    manifest_path = output / "policy_request_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["planning_registry_binding"]["file_sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    with pytest.raises(
        verifier.PolicyRequestVerificationError,
        match="planning_registry_binding raw bytes changed",
    ):
        _verify(policy, run, output)


def test_verifier_rejects_duplicate_request_json_keys(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis = tmp_path / "analysis"
    analysis.mkdir()
    _, policy, run, output = _compile(
        tmp_path,
        monkeypatch,
        action_type="audit_existing_battery_run",
        execution_registry=PLANNING,
        cost=2,
        action_inputs={"analysis_run": analysis},
    )
    (output / "execution_request.json").write_text(
        '{"schema_version":"1.0","schema_version":"1.0"}\n'
    )
    with pytest.raises(
        verifier.PolicyRequestVerificationError,
        match="duplicate JSON key",
    ):
        _verify(policy, run, output)


def test_compiler_refuses_existing_output_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_current_state(monkeypatch)
    policy = _policy(tmp_path)
    run = tmp_path / "research-run"
    run.mkdir()
    analysis = tmp_path / "analysis"
    analysis.mkdir()
    output = tmp_path / "out"
    output.mkdir()
    with pytest.raises(compiler.PolicyRequestCompilerError, match="output_dir already exists"):
        compiler.compile_policy_authorized_request(
            "nasa-battery",
            repository_root=REPO_ROOT,
            mission_path=MISSION,
            delegation_policy_path=policy,
            research_run=run,
            action_registry_path=PLANNING,
            output_dir=output,
            action_inputs={"analysis_run": analysis},
        )
