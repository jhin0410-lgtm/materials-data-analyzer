from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop.mission_source_trust_root import (
    MissionSourceTrustRootError,
    authenticate_mission_source_trust_policy_pin,
)
from materials_data_analyzer.research_loop.research_program import build_research_program


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _policy(policy_id: str = "mp-local-v1") -> bytes:
    return _json_bytes(
        {
            "schema_version": "1.0",
            "policy_id": policy_id,
            "rules": [{"opaque_until_qualification": True}],
            "limitations": [
                "Mission-root binding does not validate policy rule semantics."
            ],
        }
    )


def _mission(pins: list[dict[str, str]]) -> dict[str, object]:
    return {
        "schema_version": "1.1",
        "mission_id": "rooted-source-trust-test",
        "mission": "Bind source-trust policy bytes under an external mission root.",
        "success_criteria": ["Authenticate only the intended control-plane provenance."],
        "constraints": ["Do not infer external provider identity."],
        "stop_rules": ["Stop on any root or projection mismatch."],
        "autonomy_policy": {
            "goal_generation": "bounded_autonomous",
            "reasoning_proposals": "schema_validated",
            "typed_computational_actions": "explicit_request",
            "network_evidence_search": "explicit_authorization",
            "physical_experiment_execution": "external_only",
        },
        "workstreams": [
            {
                "workstream_id": "nist",
                "adapter_id": "nist-ambench-process-characterization",
                "priority": 1,
                "role": "root-test",
                "enabled": True,
            }
        ],
        "source_trust_policy_pins": pins,
    }


def _planning_state() -> dict[str, object]:
    return {
        "research_question": "Can the rooted policy pin be transported safely?",
        "current_blocker": {
            "kind": "evidence",
            "code": "root-test",
            "summary": "A bounded blocker exists.",
        },
        "evidence_gap": {"status": "open", "requirements": []},
        "stop_state": {
            "status": "continue",
            "selection_status": "ready_to_execute",
            "reason": "Test fixture.",
            "reopen_conditions": [],
        },
        "selected_action": None,
        "action_frontier": [],
        "claim_boundary": {},
        "evidence_bindings": [],
    }


def _program(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mission: dict[str, object],
) -> tuple[bytes, dict[str, object]]:
    mission_bytes = _json_bytes(mission)
    mission_path = tmp_path / "mission.json"
    mission_path.write_bytes(mission_bytes)
    monkeypatch.setattr(
        "materials_data_analyzer.research_loop.research_program.build_research_planning_state",
        lambda *args, **kwargs: _planning_state(),
    )
    program = build_research_program(mission_path, repository_root=tmp_path)
    return mission_bytes, program


def _happy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    policy_id: str = "mp-local-v1",
) -> tuple[bytes, bytes, dict[str, object]]:
    policy = _policy(policy_id)
    mission = _mission(
        [{"policy_id": policy_id, "sha256": hashlib.sha256(policy).hexdigest()}]
    )
    mission_bytes, program = _program(tmp_path, monkeypatch, mission)
    return mission_bytes, policy, program


def _authenticate(
    mission_bytes: bytes,
    policy: bytes,
    program: dict[str, object],
    *,
    policy_id: str = "mp-local-v1",
    expected_mission_sha256: str | None = None,
) -> dict[str, object]:
    return authenticate_mission_source_trust_policy_pin(
        mission_bytes=mission_bytes,
        expected_mission_sha256=(
            expected_mission_sha256 or hashlib.sha256(mission_bytes).hexdigest()
        ),
        program_state=program,
        policy_id=policy_id,
        source_trust_policy_bytes=policy,
    )


def test_authenticates_policy_pin_only_under_supplied_exact_mission_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mission_bytes, policy, program = _happy(tmp_path, monkeypatch)
    report = _authenticate(mission_bytes, policy, program)
    assert report["schema_version"] == "1.0"
    assert report["mission_bytes_match_supplied_root"] is True
    assert report["program_projection_matches_authenticated_mission"] is True
    assert report["policy_pin_provenance_authenticated_under_supplied_mission_root"] is True
    assert report["source_trust_policy_bytes_match_authenticated_pin"] is True
    assert report["source_trust_policy_semantics_validated"] is False
    assert report["expected_mission_root_provenance_authenticated_by_this_contract"] is False


@pytest.mark.parametrize(
    "field",
    [
        "full_program_state_provenance_reauthenticated",
        "local_record_reliance_qualified",
        "external_source_identity_authenticated",
        "external_source_credentials_authenticated",
        "historical_acquisition_event_authenticated",
        "transport_peer_identity_authenticated",
        "physical_origin_truth_authenticated",
        "scientific_result_validity_authenticated",
        "support_independence_established",
        "empirical_authority_granted",
        "scientific_status_changed",
        "execution_authorized",
        "positive_closeout_granted",
    ],
)
def test_never_overclaims_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
) -> None:
    mission_bytes, policy, program = _happy(tmp_path, monkeypatch)
    assert _authenticate(mission_bytes, policy, program)[field] is False


def test_rejects_wrong_supplied_mission_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mission_bytes, policy, program = _happy(tmp_path, monkeypatch)
    with pytest.raises(MissionSourceTrustRootError, match="supplied expected mission SHA"):
        _authenticate(
            mission_bytes,
            policy,
            program,
            expected_mission_sha256="0" * 64,
        )


def test_rejects_noncanonical_supplied_mission_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mission_bytes, policy, program = _happy(tmp_path, monkeypatch)
    with pytest.raises(MissionSourceTrustRootError, match="lowercase SHA-256"):
        _authenticate(
            mission_bytes,
            policy,
            program,
            expected_mission_sha256=hashlib.sha256(mission_bytes).hexdigest().upper(),
        )


def test_rejects_duplicate_keys_in_exact_mission_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mission_bytes, policy, program = _happy(tmp_path, monkeypatch)
    text = mission_bytes.decode()
    text = text.replace(
        '"schema_version":"1.1"',
        '"schema_version":"1.1","schema_version":"1.1"',
        1,
    )
    tampered = text.encode()
    with pytest.raises(MissionSourceTrustRootError, match="duplicate JSON key"):
        _authenticate(tampered, policy, program)


def test_legacy_mission_cannot_authenticate_policy_pin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mission = _mission([])
    mission["schema_version"] = "1.0"
    mission.pop("source_trust_policy_pins")
    mission_bytes, program = _program(tmp_path, monkeypatch, mission)
    with pytest.raises(MissionSourceTrustRootError, match="mission schema_version 1.1"):
        _authenticate(mission_bytes, _policy(), program)


def test_metadata_only_pin_cannot_be_selected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = _policy()
    mission = _mission([])
    mission.pop("source_trust_policy_pins")
    mission["metadata"] = {
        "source_trust_policy_pins": [
            {"policy_id": "mp-local-v1", "sha256": hashlib.sha256(policy).hexdigest()}
        ]
    }
    mission_bytes, program = _program(tmp_path, monkeypatch, mission)
    with pytest.raises(MissionSourceTrustRootError, match="no first-class"):
        _authenticate(mission_bytes, policy, program)


def test_rejects_program_schema_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mission_bytes, policy, program = _happy(tmp_path, monkeypatch)
    program["schema_version"] = "1.0"
    with pytest.raises(MissionSourceTrustRootError, match="schema_version must be 1.1"):
        _authenticate(mission_bytes, policy, program)


def test_rejects_program_mission_binding_sha_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mission_bytes, policy, program = _happy(tmp_path, monkeypatch)
    program["mission_binding"]["sha256"] = "0" * 64
    with pytest.raises(MissionSourceTrustRootError, match="mission binding"):
        _authenticate(mission_bytes, policy, program)


def test_rejects_authority_field_in_program_mission_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mission_bytes, policy, program = _happy(tmp_path, monkeypatch)
    program["mission_binding"]["trusted"] = True
    with pytest.raises(MissionSourceTrustRootError, match="exact key set"):
        _authenticate(mission_bytes, policy, program)


def test_program_normalized_mission_comparison_is_type_strict(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mission_bytes, policy, program = _happy(tmp_path, monkeypatch)
    program["mission"]["workstreams"][0]["priority"] = True
    with pytest.raises(MissionSourceTrustRootError, match="normalized mission"):
        _authenticate(mission_bytes, policy, program)


def test_rejects_projected_pin_reordering(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _policy("first")
    second = _policy("second")
    mission = _mission(
        [
            {"policy_id": "first", "sha256": hashlib.sha256(first).hexdigest()},
            {"policy_id": "second", "sha256": hashlib.sha256(second).hexdigest()},
        ]
    )
    mission_bytes, program = _program(tmp_path, monkeypatch, mission)
    program["source_trust_policy_pins"] = list(
        reversed(program["source_trust_policy_pins"])
    )
    with pytest.raises(MissionSourceTrustRootError, match="projected policy pins"):
        _authenticate(mission_bytes, first, program, policy_id="first")


def test_rejects_policy_bytes_not_matching_authenticated_pin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mission_bytes, _, program = _happy(tmp_path, monkeypatch)
    with pytest.raises(MissionSourceTrustRootError, match="do not match.*mission policy pin"):
        _authenticate(mission_bytes, _policy("different"), program)


def test_rejects_policy_internal_id_different_from_selected_pin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = _policy("internal-id")
    mission = _mission(
        [{"policy_id": "selected-id", "sha256": hashlib.sha256(policy).hexdigest()}]
    )
    mission_bytes, program = _program(tmp_path, monkeypatch, mission)
    with pytest.raises(MissionSourceTrustRootError, match="internal policy_id"):
        _authenticate(
            mission_bytes,
            policy,
            program,
            policy_id="selected-id",
        )


def test_rejects_unknown_authority_field_in_policy_envelope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy_object = json.loads(_policy())
    policy_object["provider_authenticated"] = True
    policy = _json_bytes(policy_object)
    mission = _mission(
        [{"policy_id": "mp-local-v1", "sha256": hashlib.sha256(policy).hexdigest()}]
    )
    mission_bytes, program = _program(tmp_path, monkeypatch, mission)
    with pytest.raises(MissionSourceTrustRootError, match="exact key set"):
        _authenticate(mission_bytes, policy, program)


def test_rejects_program_projected_pin_substitution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mission_bytes, policy, program = _happy(tmp_path, monkeypatch)
    altered = copy.deepcopy(program["source_trust_policy_pins"])
    altered[0]["sha256"] = "0" * 64
    program["source_trust_policy_pins"] = altered
    with pytest.raises(MissionSourceTrustRootError, match="projected policy pins"):
        _authenticate(mission_bytes, policy, program)
