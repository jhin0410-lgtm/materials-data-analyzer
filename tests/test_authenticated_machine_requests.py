from __future__ import annotations

import copy
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from materials_data_analyzer.research_loop import authenticated_request_compiler as compiler
from materials_data_analyzer.research_loop import authenticated_request_verifier as verifier
from materials_data_analyzer.research_loop.action_registry import describe_action, load_action_registry
from materials_data_analyzer.research_loop.kernel import ResearchLoopError, append_hypothesis, initialize_research_loop

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_REGISTRIES = {
    "planning": REPO_ROOT / "configs/research/nasa_research_action_registry.v1.json",
    "target": REPO_ROOT / "configs/research/nasa_target_reference_action_registry.v1.json",
    "protocol": REPO_ROOT / "configs/research/nasa_protocol_stratification_action_registry.v1.json",
    "external": REPO_ROOT / "configs/research/nasa_external_data_requirement_action_registry.v1.json",
}
POLICY_ID = "bounded-machine-request-policy-v1"


def _bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def _repo(tmp_path: Path) -> tuple[Path, dict[str, Path]]:
    root = tmp_path / "repo"
    (root / "configs/research").mkdir(parents=True)
    shutil.copy2(REPO_ROOT / "pyproject.toml", root / "pyproject.toml")
    registries: dict[str, Path] = {}
    for name, source in SOURCE_REGISTRIES.items():
        target = root / "configs/research" / source.name
        shutil.copy2(source, target)
        registries[name] = target
    # Strict registry validation requires every available source-script binding to exist.
    for path in registries.values():
        payload = json.loads(path.read_text(encoding="utf-8"))
        for action in payload["actions"]:
            binding = action.get("binding")
            if isinstance(binding, dict) and binding.get("kind") == "source_script" and isinstance(binding.get("path"), str):
                script = root / binding["path"]
                script.parent.mkdir(parents=True, exist_ok=True)
                script.write_text("# registry-binding placeholder for isolated contract test\n", encoding="utf-8")
    return root, registries


def _objective(root: Path) -> Path:
    path = root / "objective.json"
    path.write_text(json.dumps({
        "schema_version": "1.0",
        "research_id": "authenticated-request-test",
        "question": "Can bounded request authorship remain fail-closed?",
        "metrics": {"primary": "contract_integrity", "secondary": ["reproducibility"]},
        "constraints": ["No execution from request compiler."],
        "budget": {"maximum_actions": 20, "maximum_cost_units": 100},
        "stop_rules": ["Stop on any authority-chain mismatch."],
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _policy(action_type: str, cost: int, *, network: bool = False) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "policy_id": POLICY_ID,
        "adapter_id": "nasa-battery",
        "allowed_actions": [{"action_type": action_type, "action_version": "1.0", "max_cost_units": cost}],
        "max_cost_units_per_request": cost,
        "network_access": network,
        "physical_experiment_execution": False,
        "generic_command_execution": False,
        "limitations": [
            "Only bounded request authorship may become eligible.",
            "Execution and scientific authority remain separately denied.",
        ],
    }


def _mission(policy_sha: str) -> dict[str, object]:
    return {
        "schema_version": "1.2",
        "mission_id": "authenticated-request-test",
        "mission": "Bind machine-authored request bytes to an externally supplied mission root.",
        "success_criteria": ["Compiler and verifier independently authenticate exact delegation bytes."],
        "constraints": ["Never synthesize operator acknowledgement."],
        "stop_rules": ["Stop on any mission, policy, registry, ledger, or request drift."],
        "autonomy_policy": {
            "goal_generation": "manual_only",
            "reasoning_proposals": "disabled",
            "typed_computational_actions": "explicit_request",
            "network_evidence_search": "disabled",
            "physical_experiment_execution": "disabled",
        },
        "workstreams": [{
            "workstream_id": "nasa",
            "adapter_id": "nasa-battery",
            "priority": 90,
            "role": "request-authorship regression",
            "enabled": False,
        }],
        "request_delegation_policy_pins": [{"policy_id": POLICY_ID, "sha256": policy_sha}],
    }


def _authorization(root: Path, registry_path: Path, action_type: str, *, selected_changes: dict[str, object] | None = None) -> dict[str, Any]:
    registry = load_action_registry(registry_path, repository_root=root)
    contract = describe_action(registry, action_type)
    selected: dict[str, object] = {
        "action_type": action_type,
        "action_version": contract["version"],
        "availability": contract["availability"],
        "cost_units": contract["cost_units"],
        "execution_registry_id": registry["registry_id"],
        "execution_registry_path": str(registry_path.resolve()),
        "execution_registry_sha256": registry["registry_sha256"],
    }
    if selected_changes:
        selected.update(selected_changes)
    return {
        "authorization_status": "ready_for_explicit_execution_request",
        "selected_action": selected,
        "execution_contract": {
            "registry_id": registry["registry_id"],
            "registry_sha256": registry["registry_sha256"],
            "registry_path": str(registry_path.resolve()),
            "action_type": action_type,
            "action_version": contract["version"],
            "category": contract["category"],
            "cost_units": contract["cost_units"],
            "binding": dict(contract["binding"]),
            "verifier_checks": list(contract["verifier_checks"]),
            "prohibited_effects": list(contract["prohibited_effects"]),
        },
    }


def _patch_auth(monkeypatch: pytest.MonkeyPatch, value: dict[str, Any]) -> None:
    monkeypatch.setattr(
        compiler.action_authorization_module,
        "assess_current_action_authorization",
        lambda *args, **kwargs: copy.deepcopy(value),
    )


def _fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    action_type: str = "audit_existing_battery_run",
    registry_name: str = "planning",
    cost: int = 2,
    input_names: tuple[str, ...] = ("analysis_run",),
) -> dict[str, Any]:
    root, registries = _repo(tmp_path)
    run = root / "run"
    initialize_research_loop(_objective(root), run)
    policy_file = root / "policy.json"
    policy_bytes = _bytes(_policy(action_type, cost))
    policy_file.write_bytes(policy_bytes)
    mission_file = root / "mission.json"
    mission_bytes = _bytes(_mission(hashlib.sha256(policy_bytes).hexdigest()))
    mission_file.write_bytes(mission_bytes)
    authorization = _authorization(root, registries[registry_name], action_type)
    _patch_auth(monkeypatch, authorization)
    inputs: dict[str, Path] = {}
    for name in input_names:
        path = root / f"input-{name}"
        path.mkdir()
        inputs[name] = path
    output = root / "compiled"
    result = compiler.compile_authenticated_machine_request(
        "nasa-battery",
        repository_root=root,
        mission_path=mission_file,
        expected_mission_sha256=hashlib.sha256(mission_bytes).hexdigest(),
        policy_id=POLICY_ID,
        request_delegation_policy_path=policy_file,
        research_run=run,
        planning_registry_path=registries["planning"],
        output_dir=output,
        action_inputs=inputs,
    )
    return {
        "root": root,
        "registries": registries,
        "run": run,
        "policy": policy_file,
        "policy_bytes": policy_bytes,
        "mission": mission_file,
        "mission_bytes": mission_bytes,
        "expected": hashlib.sha256(mission_bytes).hexdigest(),
        "authorization": authorization,
        "inputs": inputs,
        "output": output,
        "result": result,
    }


def _verify(fx: dict[str, Any]) -> dict[str, Any]:
    return verifier.verify_authenticated_machine_request(
        "nasa-battery",
        repository_root=fx["root"],
        mission_path=fx["mission"],
        expected_mission_sha256=fx["expected"],
        policy_id=POLICY_ID,
        request_delegation_policy_path=fx["policy"],
        research_run=fx["run"],
        planning_registry_path=fx["registries"]["planning"],
        request_path=fx["output"] / "execution_request.json",
        manifest_path=fx["output"] / "authenticated_request_manifest.json",
    )


def test_happy_path_is_request_authorship_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fx = _fixture(tmp_path, monkeypatch)
    request = json.loads((fx["output"] / "execution_request.json").read_text())
    boundary = fx["result"]["authority_boundary"]
    assert request["action_type"] == "audit_existing_battery_run"
    assert "operator_acknowledgement" not in request
    assert fx["result"]["registry_input_aliases"] == {"run_output": "analysis_run"}
    assert boundary["machine_request_authorship_permitted_under_supplied_external_mission_root"] is True
    for field in (
        "expected_mission_root_supplier_authenticated",
        "human_authorship_authenticated",
        "operator_identity_authenticated",
        "operator_acknowledgement_synthesized",
        "execution_authorized",
        "action_executed",
        "network_access_authorized",
        "physical_experiment_execution_authorized",
        "generic_command_execution_authorized",
        "model_fitting_authorized",
        "scientific_evidence_upgraded",
        "scientific_status_changed",
        "empirical_authority_granted",
        "positive_closeout_granted",
    ):
        assert boundary[field] is False
    report = _verify(fx)
    assert report["verification_status"] == "bounded_machine_request_verified_eligible_for_existing_typed_executor"
    assert report["execution_authorized"] is False
    assert report["human_authorship_authenticated"] is False
    assert report["operator_acknowledgement_synthesized"] is False
    assert report["scientific_evidence_upgraded"] is False


@pytest.mark.parametrize(
    ("action_type", "registry_name", "cost", "inputs"),
    [
        ("target_reference_sensitivity", "target", 4, ("analysis_run",)),
        ("protocol_stratification", "protocol", 5, ("import_run", "analysis_run")),
        ("external_data_requirement_generation", "external", 2, ()),
    ],
)
def test_only_current_typed_executor_surfaces_compile_and_verify(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    action_type: str,
    registry_name: str,
    cost: int,
    inputs: tuple[str, ...],
) -> None:
    fx = _fixture(tmp_path, monkeypatch, action_type=action_type, registry_name=registry_name, cost=cost, input_names=inputs)
    assert fx["result"]["planning_registry_binding"]["path"] == str(fx["registries"]["planning"].resolve())
    assert fx["result"]["execution_registry_binding"]["path"] == str(fx["registries"][registry_name].resolve())
    assert _verify(fx)["action_type"] == action_type


def test_compiler_and_verifier_each_rerun_external_root_bridge(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    real = compiler.delegation_bridge_module.authenticate_request_delegation_policy_under_expected_mission_root

    def counted(*args: object, **kwargs: object) -> dict[str, Any]:
        calls.append("bridge")
        return real(*args, **kwargs)

    monkeypatch.setattr(compiler.delegation_bridge_module, "authenticate_request_delegation_policy_under_expected_mission_root", counted)
    fx = _fixture(tmp_path, monkeypatch)
    assert calls == ["bridge"]
    _verify(fx)
    assert calls == ["bridge", "bridge"]


def test_mission_root_mission_bytes_and_policy_bytes_are_exact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fx = _fixture(tmp_path, monkeypatch)
    with pytest.raises(ResearchLoopError, match="mission bytes do not match"):
        verifier.verify_authenticated_machine_request(
            "nasa-battery",
            repository_root=fx["root"],
            mission_path=fx["mission"],
            expected_mission_sha256="0" * 64,
            policy_id=POLICY_ID,
            request_delegation_policy_path=fx["policy"],
            research_run=fx["run"],
            planning_registry_path=fx["registries"]["planning"],
            request_path=fx["output"] / "execution_request.json",
            manifest_path=fx["output"] / "authenticated_request_manifest.json",
        )
    fx["mission"].write_bytes(fx["mission_bytes"] + b" ")
    with pytest.raises(ResearchLoopError):
        _verify(fx)
    fx["mission"].write_bytes(fx["mission_bytes"])
    fx["policy"].write_bytes(fx["policy_bytes"] + b" ")
    with pytest.raises(ResearchLoopError):
        _verify(fx)


@pytest.mark.parametrize(
    ("selected_changes", "message"),
    [
        ({"action_version": "9.9"}, "allowlist|version"),
        ({"cost_units": 99}, "cost"),
        ({"availability": "planned"}, "availability"),
    ],
)
def test_selection_version_cost_and_availability_drift_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    selected_changes: dict[str, object],
    message: str,
) -> None:
    root, registries = _repo(tmp_path)
    run = root / "run"
    initialize_research_loop(_objective(root), run)
    policy_file = root / "policy.json"
    policy_bytes = _bytes(_policy("audit_existing_battery_run", 99))
    policy_file.write_bytes(policy_bytes)
    mission_file = root / "mission.json"
    mission_bytes = _bytes(_mission(hashlib.sha256(policy_bytes).hexdigest()))
    mission_file.write_bytes(mission_bytes)
    _patch_auth(monkeypatch, _authorization(root, registries["planning"], "audit_existing_battery_run", selected_changes=selected_changes))
    analysis = root / "analysis"
    analysis.mkdir()
    with pytest.raises(ResearchLoopError, match=message):
        compiler.compile_authenticated_machine_request(
            "nasa-battery", repository_root=root, mission_path=mission_file,
            expected_mission_sha256=hashlib.sha256(mission_bytes).hexdigest(), policy_id=POLICY_ID,
            request_delegation_policy_path=policy_file, research_run=run,
            planning_registry_path=registries["planning"], output_dir=root / "out",
            action_inputs={"analysis_run": analysis},
        )


def test_planning_raw_bytes_and_execution_semantics_are_bound(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fx = _fixture(tmp_path, monkeypatch)
    planning = fx["registries"]["planning"]
    planning.write_bytes(planning.read_bytes() + b"\n")
    with pytest.raises(ResearchLoopError, match="raw registry bytes"):
        _verify(fx)

    fx2 = _fixture(tmp_path / "execution", monkeypatch, action_type="target_reference_sensitivity", registry_name="target", cost=4)
    target = fx2["registries"]["target"]
    payload = json.loads(target.read_text())
    for action in payload["actions"]:
        if action["action_type"] == "target_reference_sensitivity":
            action["cost_units"] = 99
            break
    target.write_text(json.dumps(payload, indent=2) + "\n")
    with pytest.raises(ResearchLoopError, match="registry|cost"):
        _verify(fx2)


def test_valid_ledger_drift_invalidates_compiled_request(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fx = _fixture(tmp_path, monkeypatch)
    append_hypothesis(
        fx["run"],
        hypothesis_id="post-compile-drift",
        statement="A new valid ledger event makes the prior request stale.",
        rationale="The deterministic request identity is ledger-bound.",
    )
    with pytest.raises(ResearchLoopError, match="ledger changed after request compilation"):
        _verify(fx)


def test_missing_extra_and_substituted_inputs_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, registries = _repo(tmp_path)
    run = root / "run"
    initialize_research_loop(_objective(root), run)
    policy_file = root / "policy.json"
    policy_bytes = _bytes(_policy("audit_existing_battery_run", 2))
    policy_file.write_bytes(policy_bytes)
    mission_file = root / "mission.json"
    mission_bytes = _bytes(_mission(hashlib.sha256(policy_bytes).hexdigest()))
    mission_file.write_bytes(mission_bytes)
    _patch_auth(monkeypatch, _authorization(root, registries["planning"], "audit_existing_battery_run"))
    with pytest.raises(compiler.AuthenticatedRequestInputBindingRequired, match="will not guess"):
        compiler.compile_authenticated_machine_request(
            "nasa-battery", repository_root=root, mission_path=mission_file,
            expected_mission_sha256=hashlib.sha256(mission_bytes).hexdigest(), policy_id=POLICY_ID,
            request_delegation_policy_path=policy_file, research_run=run,
            planning_registry_path=registries["planning"], output_dir=root / "missing",
        )
    analysis = root / "analysis"
    extra = root / "extra"
    analysis.mkdir(); extra.mkdir()
    with pytest.raises(ResearchLoopError, match="outside audited"):
        compiler.compile_authenticated_machine_request(
            "nasa-battery", repository_root=root, mission_path=mission_file,
            expected_mission_sha256=hashlib.sha256(mission_bytes).hexdigest(), policy_id=POLICY_ID,
            request_delegation_policy_path=policy_file, research_run=run,
            planning_registry_path=registries["planning"], output_dir=root / "extra-out",
            action_inputs={"analysis_run": analysis, "unexpected": extra},
        )

    fx = _fixture(tmp_path / "substitute", monkeypatch)
    replacement = fx["root"] / "replacement"
    replacement.mkdir()
    request_path = fx["output"] / "execution_request.json"
    request = json.loads(request_path.read_text())
    request["analysis_run"] = str(replacement)
    raw = _bytes(request)
    request_path.write_bytes(raw)
    manifest_path = fx["output"] / "authenticated_request_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["request_binding"]["sha256"] = hashlib.sha256(raw).hexdigest()
    manifest["request_binding"]["bytes"] = len(raw)
    manifest_path.write_bytes(_bytes(manifest))
    with pytest.raises(ResearchLoopError, match="typed inputs|action_id|deterministic"):
        _verify(fx)


def test_alias_request_mutation_duplicate_json_and_compiler_verifier_disagreement_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fx = _fixture(tmp_path, monkeypatch)
    manifest_path = fx["output"] / "authenticated_request_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["registry_input_aliases"] = {"run_output": "wrong"}
    manifest_path.write_bytes(_bytes(manifest))
    with pytest.raises(ResearchLoopError, match="aliases"):
        _verify(fx)

    fx2 = _fixture(tmp_path / "request", monkeypatch)
    request_path = fx2["output"] / "execution_request.json"
    request = json.loads(request_path.read_text())
    request["action_id"] = "delegated-tampered"
    request_path.write_bytes(_bytes(request))
    with pytest.raises(ResearchLoopError, match="request checksum"):
        _verify(fx2)

    fx3 = _fixture(tmp_path / "duplicate", monkeypatch)
    (fx3["output"] / "execution_request.json").write_bytes(b'{"schema_version":"1.0","schema_version":"1.0"}\n')
    with pytest.raises(ResearchLoopError, match="duplicate JSON key"):
        _verify(fx3)

    monkeypatch.setattr(compiler, "_action_id", lambda **kwargs: "delegated-" + "0" * 40)
    fx4 = _fixture(tmp_path / "disagree", monkeypatch)
    with pytest.raises(ResearchLoopError, match="independent deterministic derivation"):
        _verify(fx4)


def test_policy_cannot_enable_denied_action_or_network_capability(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, registries = _repo(tmp_path)
    run = root / "run"
    initialize_research_loop(_objective(root), run)
    denied = "run_fixed_battery_intelligence"
    policy_file = root / "denied-policy.json"
    policy_bytes = _bytes(_policy(denied, 10))
    policy_file.write_bytes(policy_bytes)
    mission_file = root / "denied-mission.json"
    mission_bytes = _bytes(_mission(hashlib.sha256(policy_bytes).hexdigest()))
    mission_file.write_bytes(mission_bytes)
    _patch_auth(monkeypatch, _authorization(root, registries["planning"], denied))
    with pytest.raises(ResearchLoopError, match="hard-denied"):
        compiler.compile_authenticated_machine_request(
            "nasa-battery", repository_root=root, mission_path=mission_file,
            expected_mission_sha256=hashlib.sha256(mission_bytes).hexdigest(), policy_id=POLICY_ID,
            request_delegation_policy_path=policy_file, research_run=run,
            planning_registry_path=registries["planning"], output_dir=root / "denied-out",
        )

    network_policy = root / "network-policy.json"
    network_bytes = _bytes(_policy("audit_existing_battery_run", 2, network=True))
    network_policy.write_bytes(network_bytes)
    network_mission = root / "network-mission.json"
    network_mission_bytes = _bytes(_mission(hashlib.sha256(network_bytes).hexdigest()))
    network_mission.write_bytes(network_mission_bytes)
    _patch_auth(monkeypatch, _authorization(root, registries["planning"], "audit_existing_battery_run"))
    analysis = root / "network-analysis"; analysis.mkdir()
    with pytest.raises(ResearchLoopError, match="network_access=false"):
        compiler.compile_authenticated_machine_request(
            "nasa-battery", repository_root=root, mission_path=network_mission,
            expected_mission_sha256=hashlib.sha256(network_mission_bytes).hexdigest(), policy_id=POLICY_ID,
            request_delegation_policy_path=network_policy, research_run=run,
            planning_registry_path=registries["planning"], output_dir=root / "network-out",
            action_inputs={"analysis_run": analysis},
        )


def test_downstream_authorization_executor_version_drift_and_output_overwrite_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, registries = _repo(tmp_path)
    run = root / "run"
    initialize_research_loop(_objective(root), run)
    policy_file = root / "policy.json"
    policy_bytes = _bytes(_policy("audit_existing_battery_run", 2))
    policy_file.write_bytes(policy_bytes)
    mission_file = root / "mission.json"
    mission_bytes = _bytes(_mission(hashlib.sha256(policy_bytes).hexdigest()))
    mission_file.write_bytes(mission_bytes)
    _patch_auth(monkeypatch, _authorization(root, registries["planning"], "audit_existing_battery_run"))
    analysis = root / "analysis"; analysis.mkdir()
    monkeypatch.setattr(compiler.action_authorization_module, "AUTHORIZATION_POLICY_VERSION", "9.9")
    with pytest.raises(ResearchLoopError, match="authorization policy version drifted"):
        compiler.compile_authenticated_machine_request(
            "nasa-battery", repository_root=root, mission_path=mission_file,
            expected_mission_sha256=hashlib.sha256(mission_bytes).hexdigest(), policy_id=POLICY_ID,
            request_delegation_policy_path=policy_file, research_run=run,
            planning_registry_path=registries["planning"], output_dir=root / "bad-auth",
            action_inputs={"analysis_run": analysis},
        )
    monkeypatch.setattr(compiler.action_authorization_module, "AUTHORIZATION_POLICY_VERSION", "1.1")
    output = root / "compiled"
    compiler.compile_authenticated_machine_request(
        "nasa-battery", repository_root=root, mission_path=mission_file,
        expected_mission_sha256=hashlib.sha256(mission_bytes).hexdigest(), policy_id=POLICY_ID,
        request_delegation_policy_path=policy_file, research_run=run,
        planning_registry_path=registries["planning"], output_dir=output,
        action_inputs={"analysis_run": analysis},
    )
    before = ((output / "execution_request.json").read_bytes(), (output / "authenticated_request_manifest.json").read_bytes())
    with pytest.raises(ResearchLoopError, match="output_dir already exists"):
        compiler.compile_authenticated_machine_request(
            "nasa-battery", repository_root=root, mission_path=mission_file,
            expected_mission_sha256=hashlib.sha256(mission_bytes).hexdigest(), policy_id=POLICY_ID,
            request_delegation_policy_path=policy_file, research_run=run,
            planning_registry_path=registries["planning"], output_dir=output,
            action_inputs={"analysis_run": analysis},
        )
    assert before == ((output / "execution_request.json").read_bytes(), (output / "authenticated_request_manifest.json").read_bytes())
    monkeypatch.setattr(verifier.authorized_execution_module, "EXECUTION_POLICY_VERSION", "9.9")
    with pytest.raises(ResearchLoopError, match="executor policy version drifted"):
        verifier.verify_authenticated_machine_request(
            "nasa-battery", repository_root=root, mission_path=mission_file,
            expected_mission_sha256=hashlib.sha256(mission_bytes).hexdigest(), policy_id=POLICY_ID,
            request_delegation_policy_path=policy_file, research_run=run,
            planning_registry_path=registries["planning"], request_path=output / "execution_request.json",
            manifest_path=output / "authenticated_request_manifest.json",
        )
