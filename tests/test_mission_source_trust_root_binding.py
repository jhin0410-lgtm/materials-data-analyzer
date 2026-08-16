from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop import research_program
from materials_data_analyzer.research_loop.mission_source_trust_root_binding import (
    MissionSourceTrustRootBindingError,
    qualify_acquisition_record_under_supplied_mission_root,
)
from materials_data_analyzer.research_loop.research_program import (
    build_research_program,
)


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _acquisition_fixture(
    *, policy_id: str = "materials-project-structure-records-v1",
) -> tuple[bytes, bytes, bytes, bytes]:
    evidence = b"provider-response-bytes\x00\x03"
    evidence_sha = hashlib.sha256(evidence).hexdigest()
    manifest = {
        "artifact": {"sha256": evidence_sha},
        "source": {
            "system": "Materials Project",
            "version": "2026.08.01",
            "endpoint": "materials.summary.search",
        },
        "retrieval": {"status": "success", "network_performed": True},
    }
    manifest_bytes = _json_bytes(manifest)
    declaration = {
        "schema_version": "1.0",
        "acquisition_id": "mp-acq-root-1",
        "evidence_artifact_sha256": evidence_sha,
        "acquisition_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "evidence_role": "external_structure_record",
        "manifest_evidence_sha256_pointer": "/artifact/sha256",
        "manifest_claim_bindings": [
            {
                "claim": "source_system",
                "json_pointer": "/source/system",
                "expected_value": "Materials Project",
            },
            {
                "claim": "source_version",
                "json_pointer": "/source/version",
                "expected_value": "2026.08.01",
            },
            {
                "claim": "retrieval_endpoint",
                "json_pointer": "/source/endpoint",
                "expected_value": "materials.summary.search",
            },
            {
                "claim": "retrieval_status",
                "json_pointer": "/retrieval/status",
                "expected_value": "success",
            },
            {
                "claim": "network_performed",
                "json_pointer": "/retrieval/network_performed",
                "expected_value": True,
            },
        ],
        "limitations": ["Local provenance does not authenticate provider identity."],
    }
    policy = {
        "schema_version": "1.0",
        "policy_id": policy_id,
        "rules": [
            {
                "rule_id": "mp-summary-success",
                "evidence_role": "external_structure_record",
                "required_manifest_claims": [
                    {
                        "claim": "source_system",
                        "json_pointer": "/source/system",
                        "allowed_values": ["Materials Project"],
                    },
                    {
                        "claim": "source_version",
                        "json_pointer": "/source/version",
                        "allowed_values": ["2026.08.01"],
                    },
                    {
                        "claim": "retrieval_endpoint",
                        "json_pointer": "/source/endpoint",
                        "allowed_values": ["materials.summary.search"],
                    },
                    {
                        "claim": "retrieval_status",
                        "json_pointer": "/retrieval/status",
                        "allowed_values": ["success"],
                    },
                    {
                        "claim": "network_performed",
                        "json_pointer": "/retrieval/network_performed",
                        "allowed_values": [True],
                    },
                ],
            }
        ],
        "limitations": ["Local qualification is not external-source authentication."],
    }
    return evidence, manifest_bytes, _json_bytes(declaration), _json_bytes(policy)


def _mission(policy_id: str, policy_sha: str) -> dict[str, object]:
    return {
        "schema_version": "1.1",
        "mission_id": "rooted-acquisition-trust-test",
        "mission": "Qualify one exact acquisition record under a mission-rooted local policy.",
        "success_criteria": ["Keep provenance and scientific authority separate."],
        "constraints": ["Do not infer provider identity from local metadata."],
        "stop_rules": ["Stop on any root, pin, or exact-record mismatch."],
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
                "role": "root-binding regression",
                "enabled": True,
            }
        ],
        "source_trust_policy_pins": [
            {"policy_id": policy_id, "sha256": policy_sha}
        ],
    }


def _planning_state() -> dict[str, object]:
    return {
        "research_question": "Can exact local acquisition reliance be rooted safely?",
        "current_blocker": {
            "kind": "provenance",
            "code": "root-binding",
            "summary": "A supplied mission root must bind the local policy pin.",
        },
        "evidence_gap": {"status": "open", "requirements": []},
        "stop_state": {
            "status": "continue",
            "selection_status": "ready_to_execute",
            "reason": "Regression fixture.",
            "reopen_conditions": [],
        },
        "selected_action": None,
        "action_frontier": [],
        "claim_boundary": {},
        "evidence_bindings": [],
    }


def _fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    mission_policy_id: str = "materials-project-structure-records-v1",
    policy_internal_id: str | None = None,
) -> dict[str, object]:
    internal_id = policy_internal_id or mission_policy_id
    evidence, manifest, declaration, policy = _acquisition_fixture(policy_id=internal_id)
    mission = _mission(mission_policy_id, hashlib.sha256(policy).hexdigest())
    mission_bytes = _json_bytes(mission)
    mission_path = tmp_path / "mission.json"
    mission_path.write_bytes(mission_bytes)
    monkeypatch.setattr(
        research_program,
        "build_research_planning_state",
        lambda *args, **kwargs: _planning_state(),
    )
    program = build_research_program(mission_path, repository_root=tmp_path)
    return {
        "mission_bytes": mission_bytes,
        "program_state": program,
        "expected_mission_sha256": hashlib.sha256(mission_bytes).hexdigest(),
        "policy_id": mission_policy_id,
        "source_trust_policy_bytes": policy,
        "evidence_bytes": evidence,
        "acquisition_manifest_bytes": manifest,
        "acquisition_declaration_bytes": declaration,
    }


def _qualify(values: dict[str, object]) -> dict[str, object]:
    return qualify_acquisition_record_under_supplied_mission_root(**values)  # type: ignore[arg-type]


def test_qualifies_local_record_only_under_exact_supplied_mission_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = _qualify(_fixture(tmp_path, monkeypatch))
    assert report["schema_version"] == "1.0"
    assert report["binding_policy_version"] == "1.0"
    assert report["mission_policy_pin_authenticated_under_supplied_root"] is True
    assert report["policy_internal_identity_matches_authenticated_mission_pin"] is True
    assert report["local_record_reliance_qualified_under_supplied_mission_root"] is True
    assert report["matched_source_trust_rule_id"] == "mp-summary-success"
    assert report["recorded_source_system"] == "Materials Project"


@pytest.mark.parametrize(
    "field",
    [
        "expected_mission_root_provenance_authenticated_by_this_contract",
        "full_program_state_provenance_reauthenticated",
        "repository_or_release_identity_authenticated",
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
def test_never_overclaims_broader_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
) -> None:
    report = _qualify(_fixture(tmp_path, monkeypatch))
    assert report[field] is False


def test_rejects_policy_identity_alias_even_when_policy_sha_is_exactly_pinned(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = _fixture(
        tmp_path,
        monkeypatch,
        mission_policy_id="mission-policy-id",
        policy_internal_id="different-internal-policy-id",
    )
    with pytest.raises(
        MissionSourceTrustRootBindingError,
        match="internal identity does not match",
    ):
        _qualify(values)


def test_rejects_program_policy_version_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = _fixture(tmp_path, monkeypatch)
    program = copy.deepcopy(values["program_state"])
    program["program_policy_version"] = "9.9"
    values["program_state"] = program
    with pytest.raises(MissionSourceTrustRootBindingError, match="program_policy_version"):
        _qualify(values)


def test_rejects_wrong_supplied_mission_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = _fixture(tmp_path, monkeypatch)
    values["expected_mission_sha256"] = "0" * 64
    with pytest.raises(MissionSourceTrustRootBindingError, match="do not match"):
        _qualify(values)


def test_rejects_program_mission_binding_sha_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = _fixture(tmp_path, monkeypatch)
    program = copy.deepcopy(values["program_state"])
    program["mission_binding"]["sha256"] = "0" * 64
    values["program_state"] = program
    with pytest.raises(MissionSourceTrustRootBindingError, match="mission_binding SHA"):
        _qualify(values)


def test_rejects_unknown_authority_field_in_program_mission_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = _fixture(tmp_path, monkeypatch)
    program = copy.deepcopy(values["program_state"])
    program["mission_binding"]["trusted"] = True
    values["program_state"] = program
    with pytest.raises(MissionSourceTrustRootBindingError, match="exactly path and sha256"):
        _qualify(values)


def test_rejects_projected_pin_substitution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = _fixture(tmp_path, monkeypatch)
    program = copy.deepcopy(values["program_state"])
    program["source_trust_policy_pins"][0]["sha256"] = "0" * 64
    values["program_state"] = program
    with pytest.raises(MissionSourceTrustRootBindingError, match="do not exactly agree"):
        _qualify(values)


@pytest.mark.parametrize(
    "field",
    [
        "mission_bytes",
        "source_trust_policy_bytes",
        "evidence_bytes",
        "acquisition_manifest_bytes",
        "acquisition_declaration_bytes",
    ],
)
def test_exact_byte_inputs_fail_closed_with_domain_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
) -> None:
    values = _fixture(tmp_path, monkeypatch)
    values[field] = "not-bytes"
    with pytest.raises(MissionSourceTrustRootBindingError, match=f"{field} must be exact bytes"):
        _qualify(values)


def test_duplicate_json_keys_in_exact_mission_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = _fixture(tmp_path, monkeypatch)
    original = values["mission_bytes"]
    assert isinstance(original, bytes)
    duplicate = original.replace(
        b'"schema_version":"1.1"',
        b'"schema_version":"1.1","schema_version":"1.1"',
        1,
    )
    values["mission_bytes"] = duplicate
    values["expected_mission_sha256"] = hashlib.sha256(duplicate).hexdigest()
    with pytest.raises(MissionSourceTrustRootBindingError, match="duplicate JSON key"):
        _qualify(values)
