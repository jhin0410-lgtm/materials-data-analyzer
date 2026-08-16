from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop.mission_request_delegation_bridge import (
    MissionRequestDelegationBridgeError,
    authenticate_request_delegation_policy_under_expected_mission_root,
)
from materials_data_analyzer.research_loop.research_program import build_research_program

POLICY_ID = "bounded-request-delegation-v1"
SOURCE_POLICY_ID = "materials-project-structure-records-v1"
SOURCE_POLICY_SHA = "c" * 64


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _policy() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "policy_id": POLICY_ID,
        "adapter_id": "nasa-battery",
        "allowed_actions": [
            {
                "action_type": "audit_existing_battery_run",
                "action_version": "1.0",
                "max_cost_units": 2,
            },
            {
                "action_type": "target_reference_sensitivity",
                "action_version": "1.0",
                "max_cost_units": 4,
            },
        ],
        "max_cost_units_per_request": 5,
        "network_access": False,
        "physical_experiment_execution": False,
        "generic_command_execution": False,
        "limitations": [
            "This policy does not authorize execution.",
            "This policy does not authenticate human authorship.",
        ],
    }


def _mission(policy_sha: str, *, schema_version: str = "1.2") -> dict[str, object]:
    value: dict[str, object] = {
        "schema_version": schema_version,
        "mission_id": "mission-request-delegation-bridge-test",
        "mission": "Authenticate bounded request delegation under exact mission bytes.",
        "success_criteria": ["Only exact mission-pinned policy bytes qualify."],
        "constraints": ["Do not authorize execution."],
        "stop_rules": ["Stop on any trust-chain mismatch."],
        "autonomy_policy": {
            "goal_generation": "manual_only",
            "reasoning_proposals": "disabled",
            "typed_computational_actions": "disabled",
            "network_evidence_search": "disabled",
            "physical_experiment_execution": "disabled",
        },
        "workstreams": [
            {
                "workstream_id": "nist",
                "adapter_id": "nist-ambench-process-characterization",
                "priority": 90,
                "role": "delegation bridge regression",
                "enabled": False,
            }
        ],
        "source_trust_policy_pins": [
            {"policy_id": SOURCE_POLICY_ID, "sha256": SOURCE_POLICY_SHA}
        ],
    }
    if schema_version == "1.2":
        value["request_delegation_policy_pins"] = [
            {"policy_id": POLICY_ID, "sha256": policy_sha}
        ]
    return value


def _fixture(
    tmp_path: Path,
    *,
    policy_value: dict[str, object] | None = None,
) -> tuple[bytes, dict[str, object], bytes]:
    policy_bytes = _json_bytes(policy_value or _policy())
    mission_bytes = _json_bytes(_mission(hashlib.sha256(policy_bytes).hexdigest()))
    mission_path = tmp_path / "mission.json"
    mission_path.write_bytes(mission_bytes)
    program = build_research_program(mission_path, repository_root=tmp_path)
    return mission_bytes, program, policy_bytes


def _call(
    mission: bytes,
    program: dict[str, object],
    policy: bytes,
    **overrides: object,
) -> dict[str, object]:
    args: dict[str, object] = {
        "mission_bytes": mission,
        "expected_mission_sha256": hashlib.sha256(mission).hexdigest(),
        "program_state": program,
        "policy_id": POLICY_ID,
        "request_delegation_policy_bytes": policy,
    }
    args.update(overrides)
    return authenticate_request_delegation_policy_under_expected_mission_root(**args)  # type: ignore[arg-type]


def test_exact_chain_authenticates_policy_consistency_without_granting_authority(
    tmp_path: Path,
) -> None:
    mission, program, policy = _fixture(tmp_path)
    report = _call(mission, program, policy)
    assert report["mission_schema_version"] == "1.2"
    assert report["program_schema_version"] == "1.2"
    assert report["request_delegation_policy_id"] == POLICY_ID
    assert report["mission_bytes_match_supplied_expected_sha256"] is True
    assert report["program_projection_consistency_established"] is True
    assert report["request_delegation_policy_bytes_match_authenticated_pin"] is True
    for field in (
        "expected_mission_root_supplier_authenticated",
        "mission_authorship_authenticated",
        "delegation_policy_authorship_authenticated",
        "human_authorship_authenticated",
        "operator_identity_authenticated",
        "machine_request_authorship_authorized",
        "execution_authorized",
        "network_access_authorized",
        "physical_experiment_execution_authorized",
        "generic_command_execution_authorized",
        "scientific_evidence_upgraded",
        "scientific_status_changed",
        "empirical_authority_granted",
        "positive_closeout_granted",
    ):
        assert report[field] is False


def test_mission_byte_drift_and_noncanonical_root_fail_closed(tmp_path: Path) -> None:
    mission, program, policy = _fixture(tmp_path)
    with pytest.raises(MissionRequestDelegationBridgeError, match="mission bytes do not match"):
        _call(
            mission + b" ",
            program,
            policy,
            expected_mission_sha256=hashlib.sha256(mission).hexdigest(),
        )
    with pytest.raises(MissionRequestDelegationBridgeError, match="lowercase SHA-256"):
        _call(
            mission,
            program,
            policy,
            expected_mission_sha256=hashlib.sha256(mission).hexdigest().upper(),
        )


def test_duplicate_json_key_in_mission_fails_closed(tmp_path: Path) -> None:
    _, program, policy = _fixture(tmp_path)
    duplicate = b'{"schema_version":"1.2","schema_version":"1.2"}'
    with pytest.raises(MissionRequestDelegationBridgeError, match="duplicate JSON key"):
        _call(
            duplicate,
            program,
            policy,
            expected_mission_sha256=hashlib.sha256(duplicate).hexdigest(),
        )


def test_bridge_rejects_pre_1_2_mission_even_when_program_is_valid(tmp_path: Path) -> None:
    policy = _json_bytes(_policy())
    mission = _json_bytes(_mission(hashlib.sha256(policy).hexdigest(), schema_version="1.1"))
    path = tmp_path / "old-mission.json"
    path.write_bytes(mission)
    program = build_research_program(path, repository_root=tmp_path)
    with pytest.raises(MissionRequestDelegationBridgeError, match="requires mission schema_version 1.2"):
        _call(mission, program, policy)


def test_metadata_cannot_substitute_for_first_class_request_pin(tmp_path: Path) -> None:
    policy = _json_bytes(_policy())
    mission_value = _mission(hashlib.sha256(policy).hexdigest())
    pin = mission_value.pop("request_delegation_policy_pins")
    mission_value["metadata"] = {"request_delegation_policy_pins": pin}
    mission = _json_bytes(mission_value)
    path = tmp_path / "metadata-only.json"
    path.write_bytes(mission)
    program = build_research_program(path, repository_root=tmp_path)
    with pytest.raises(MissionRequestDelegationBridgeError, match="first-class"):
        _call(mission, program, policy)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("schema_version", "1.1", "schema_version"),
        ("program_policy_version", "2.0", "program_policy_version"),
    ],
)
def test_program_contract_versions_are_pinned(
    tmp_path: Path, field: str, value: str, message: str
) -> None:
    mission, program, policy = _fixture(tmp_path)
    mutated = copy.deepcopy(program)
    mutated[field] = value
    with pytest.raises(MissionRequestDelegationBridgeError, match=message):
        _call(mission, mutated, policy)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("binding", "mission binding"),
        ("mission", "normalized mission"),
        ("request_pin", "request-delegation"),
        ("source_pin", "source-trust"),
    ],
)
def test_program_projection_substitution_fails_closed(
    tmp_path: Path, mutation: str, message: str
) -> None:
    mission, program, policy = _fixture(tmp_path)
    mutated = copy.deepcopy(program)
    if mutation == "binding":
        mutated["mission_binding"]["sha256"] = "0" * 64  # type: ignore[index]
    elif mutation == "mission":
        mutated["mission"]["mission_id"] = "substituted"  # type: ignore[index]
    elif mutation == "request_pin":
        mutated["request_delegation_policy_pins"][0]["sha256"] = "0" * 64  # type: ignore[index]
    else:
        mutated["source_trust_policy_pins"][0]["sha256"] = "d" * 64  # type: ignore[index]
    with pytest.raises(MissionRequestDelegationBridgeError, match=message):
        _call(mission, mutated, policy)


def test_requested_policy_id_and_exact_policy_bytes_are_mission_pin_bound(tmp_path: Path) -> None:
    mission, program, policy = _fixture(tmp_path)
    with pytest.raises(MissionRequestDelegationBridgeError, match="match exactly one"):
        _call(mission, program, policy, policy_id="other-policy")
    with pytest.raises(MissionRequestDelegationBridgeError, match="do not match"):
        _call(mission, program, policy + b" ")


def test_policy_internal_id_must_match_mission_pin(tmp_path: Path) -> None:
    policy_value = _policy()
    policy_value["policy_id"] = "different-internal-id"
    policy = _json_bytes(policy_value)
    mission = _json_bytes(_mission(hashlib.sha256(policy).hexdigest()))
    path = tmp_path / "mission.json"
    path.write_bytes(mission)
    program = build_research_program(path, repository_root=tmp_path)
    with pytest.raises(MissionRequestDelegationBridgeError, match="policy ID does not match"):
        _call(mission, program, policy)


def test_policy_duplicate_keys_and_circular_binding_field_fail_closed(tmp_path: Path) -> None:
    duplicate = (
        b'{"schema_version":"1.0","schema_version":"1.0",'
        b'"policy_id":"bounded-request-delegation-v1"}'
    )
    mission = _json_bytes(_mission(hashlib.sha256(duplicate).hexdigest()))
    path = tmp_path / "duplicate.json"
    path.write_bytes(mission)
    program = build_research_program(path, repository_root=tmp_path)
    with pytest.raises(MissionRequestDelegationBridgeError, match="duplicate JSON key"):
        _call(mission, program, duplicate)

    circular = _policy()
    circular["mission_binding"] = {"sha256": "0" * 64}
    circular_bytes = _json_bytes(circular)
    mission2 = _json_bytes(_mission(hashlib.sha256(circular_bytes).hexdigest()))
    path2 = tmp_path / "circular.json"
    path2.write_bytes(mission2)
    program2 = build_research_program(path2, repository_root=tmp_path)
    with pytest.raises(MissionRequestDelegationBridgeError, match="unknown keys"):
        _call(mission2, program2, circular_bytes)


def test_policy_schema_and_duplicate_actions_fail_closed(tmp_path: Path) -> None:
    bad_schema = _policy()
    bad_schema["schema_version"] = "1.1"
    mission, program, policy = _fixture(tmp_path, policy_value=bad_schema)
    with pytest.raises(MissionRequestDelegationBridgeError, match="policy schema_version"):
        _call(mission, program, policy)

    duplicate_actions = _policy()
    actions = duplicate_actions["allowed_actions"]
    assert isinstance(actions, list)
    actions.append(copy.deepcopy(actions[0]))
    mission2, program2, policy2 = _fixture(tmp_path, policy_value=duplicate_actions)
    with pytest.raises(MissionRequestDelegationBridgeError, match="duplicate action/version"):
        _call(mission2, program2, policy2)


@pytest.mark.parametrize("field", ["max_cost_units_per_request", "action_cost"])
@pytest.mark.parametrize("value", [0, -1, True])
def test_cost_caps_must_be_positive_integers(tmp_path: Path, field: str, value: object) -> None:
    policy_value = _policy()
    if field == "max_cost_units_per_request":
        policy_value[field] = value
    else:
        actions = policy_value["allowed_actions"]
        assert isinstance(actions, list)
        actions[0]["max_cost_units"] = value
    mission, program, policy = _fixture(tmp_path, policy_value=policy_value)
    with pytest.raises(MissionRequestDelegationBridgeError, match="positive integer"):
        _call(mission, program, policy)


@pytest.mark.parametrize(
    "field",
    ["network_access", "physical_experiment_execution", "generic_command_execution"],
)
def test_permissive_policy_capabilities_fail_closed(tmp_path: Path, field: str) -> None:
    policy_value = _policy()
    policy_value[field] = True
    mission, program, policy = _fixture(tmp_path, policy_value=policy_value)
    with pytest.raises(MissionRequestDelegationBridgeError, match=f"{field}=false"):
        _call(mission, program, policy)


def test_limitations_required_and_metadata_cannot_substitute_or_grant_authority(tmp_path: Path) -> None:
    missing = _policy()
    del missing["network_access"]
    missing["metadata"] = {"network_access": False}
    mission, program, policy = _fixture(tmp_path, policy_value=missing)
    with pytest.raises(MissionRequestDelegationBridgeError, match="missing required keys"):
        _call(mission, program, policy)

    empty = _policy()
    empty["limitations"] = []
    mission2, program2, policy2 = _fixture(tmp_path, policy_value=empty)
    with pytest.raises(MissionRequestDelegationBridgeError, match="limitations must be"):
        _call(mission2, program2, policy2)

    opaque = _policy()
    opaque["metadata"] = {
        "execution_authorized": True,
        "machine_request_authorship_authorized": True,
    }
    mission3, program3, policy3 = _fixture(tmp_path, policy_value=opaque)
    report = _call(mission3, program3, policy3)
    assert report["normalized_request_delegation_policy"]["metadata"] == opaque["metadata"]  # type: ignore[index]
    assert report["execution_authorized"] is False
    assert report["machine_request_authorship_authorized"] is False
