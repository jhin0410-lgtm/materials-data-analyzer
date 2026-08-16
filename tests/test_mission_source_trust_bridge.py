from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop import mission_source_trust_bridge as bridge
from materials_data_analyzer.research_loop.acquisition_source_trust_policy import (
    qualify_acquisition_record_under_pinned_policy,
)
from materials_data_analyzer.research_loop.mission_source_trust_bridge import (
    MissionSourceTrustBridgeError,
    qualify_acquisition_record_under_expected_mission_policy,
)
from materials_data_analyzer.research_loop.research_program import (
    build_research_program,
)

POLICY_ID = "materials-project-structure-records-v1"


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _acquisition_fixture(*, policy_id: str = POLICY_ID) -> tuple[bytes, bytes, bytes, bytes]:
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
        "acquisition_id": "mp-acq-bridge-1",
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
        "limitations": ["Local acquisition records are not provider credentials."],
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
        "limitations": ["Local reliance is not external provider authentication."],
    }
    return evidence, manifest_bytes, _json_bytes(declaration), _json_bytes(policy)


def _mission(*, policy_id: str, policy_sha256: str, include_pin: bool = True) -> dict[str, object]:
    value: dict[str, object] = {
        "schema_version": "1.1",
        "mission_id": "mission-source-trust-bridge-test",
        "mission": "Bind local acquisition reliance to an externally supplied mission root.",
        "success_criteria": ["Only the exact mission-pinned source trust policy may qualify the record."],
        "constraints": ["Do not infer scientific or execution authority."],
        "stop_rules": ["Stop on any mission, program, policy, or acquisition mismatch."],
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
                "role": "bridge regression",
                "enabled": False,
            }
        ],
    }
    if include_pin:
        value["source_trust_policy_pins"] = [
            {"policy_id": policy_id, "sha256": policy_sha256}
        ]
    return value


def _program_fixture(
    tmp_path: Path,
    *,
    policy_id: str = POLICY_ID,
    policy_bytes: bytes | None = None,
    include_pin: bool = True,
) -> tuple[bytes, dict[str, object], bytes, bytes, bytes, bytes]:
    evidence, manifest, declaration, default_policy = _acquisition_fixture()
    selected_policy = default_policy if policy_bytes is None else policy_bytes
    mission = _mission(
        policy_id=policy_id,
        policy_sha256=hashlib.sha256(selected_policy).hexdigest(),
        include_pin=include_pin,
    )
    mission_bytes = _json_bytes(mission)
    mission_path = tmp_path / "mission.json"
    mission_path.write_bytes(mission_bytes)
    program = build_research_program(mission_path, repository_root=tmp_path)
    return mission_bytes, program, evidence, manifest, declaration, selected_policy


def _qualify(tmp_path: Path) -> dict[str, object]:
    mission, program, evidence, manifest, declaration, policy = _program_fixture(tmp_path)
    return qualify_acquisition_record_under_expected_mission_policy(
        mission_bytes=mission,
        expected_mission_sha256=hashlib.sha256(mission).hexdigest(),
        program_state=program,
        policy_id=POLICY_ID,
        evidence_bytes=evidence,
        acquisition_manifest_bytes=manifest,
        acquisition_declaration_bytes=declaration,
        source_trust_policy_bytes=policy,
    )


def test_qualifies_only_under_exact_mission_root_without_broadening_authority(
    tmp_path: Path,
) -> None:
    report = _qualify(tmp_path)
    assert report["schema_version"] == "1.0"
    assert report["mission_bytes_match_supplied_expected_sha256"] is True
    assert report["program_projection_consistency_established"] is True
    assert report["source_trust_policy_pin_bound_under_supplied_expected_mission_sha256"] is True
    assert report["selected_source_trust_policy_pin"]["policy_id"] == POLICY_ID
    assert report["expected_mission_sha256_provenance_authenticated_by_this_contract"] is False
    assert report["mission_authorship_authenticated"] is False
    assert report["program_state_provenance_independently_authenticated"] is False
    assert report["external_source_identity_authenticated"] is False
    assert report["empirical_authority_granted"] is False
    assert report["execution_authorized"] is False
    assert report["positive_closeout_granted"] is False
    nested = report["acquisition_qualification"]
    assert nested["local_record_reliance_qualified_under_supplied_pin"] is True
    assert nested["expected_policy_pin_provenance_authenticated_by_this_contract"] is False


def test_rejects_noncanonical_expected_mission_sha(tmp_path: Path) -> None:
    mission, program, evidence, manifest, declaration, policy = _program_fixture(tmp_path)
    with pytest.raises(MissionSourceTrustBridgeError, match="lowercase SHA-256"):
        qualify_acquisition_record_under_expected_mission_policy(
            mission_bytes=mission,
            expected_mission_sha256=hashlib.sha256(mission).hexdigest().upper(),
            program_state=program,
            policy_id=POLICY_ID,
            evidence_bytes=evidence,
            acquisition_manifest_bytes=manifest,
            acquisition_declaration_bytes=declaration,
            source_trust_policy_bytes=policy,
        )


def test_rejects_mission_byte_drift_against_supplied_root(tmp_path: Path) -> None:
    mission, program, evidence, manifest, declaration, policy = _program_fixture(tmp_path)
    with pytest.raises(MissionSourceTrustBridgeError, match="mission bytes do not match"):
        qualify_acquisition_record_under_expected_mission_policy(
            mission_bytes=mission + b" ",
            expected_mission_sha256=hashlib.sha256(mission).hexdigest(),
            program_state=program,
            policy_id=POLICY_ID,
            evidence_bytes=evidence,
            acquisition_manifest_bytes=manifest,
            acquisition_declaration_bytes=declaration,
            source_trust_policy_bytes=policy,
        )


def test_new_self_consistent_mission_root_cannot_reuse_old_program_projection(tmp_path: Path) -> None:
    mission, program, evidence, manifest, declaration, policy = _program_fixture(tmp_path)
    replacement = json.loads(mission)
    replacement["metadata"] = {"revision": "attacker-selected-new-root"}
    replacement_bytes = _json_bytes(replacement)
    with pytest.raises(MissionSourceTrustBridgeError, match="mission binding"):
        qualify_acquisition_record_under_expected_mission_policy(
            mission_bytes=replacement_bytes,
            expected_mission_sha256=hashlib.sha256(replacement_bytes).hexdigest(),
            program_state=program,
            policy_id=POLICY_ID,
            evidence_bytes=evidence,
            acquisition_manifest_bytes=manifest,
            acquisition_declaration_bytes=declaration,
            source_trust_policy_bytes=policy,
        )


def test_duplicate_keys_in_authenticated_mission_fail_closed(tmp_path: Path) -> None:
    _, program, evidence, manifest, declaration, policy = _program_fixture(tmp_path)
    duplicate = b'{"schema_version":"1.1","schema_version":"1.1"}'
    with pytest.raises(MissionSourceTrustBridgeError, match="duplicate JSON key"):
        qualify_acquisition_record_under_expected_mission_policy(
            mission_bytes=duplicate,
            expected_mission_sha256=hashlib.sha256(duplicate).hexdigest(),
            program_state=program,
            policy_id=POLICY_ID,
            evidence_bytes=evidence,
            acquisition_manifest_bytes=manifest,
            acquisition_declaration_bytes=declaration,
            source_trust_policy_bytes=policy,
        )


def test_metadata_cannot_substitute_for_first_class_policy_pin(tmp_path: Path) -> None:
    evidence, manifest, declaration, policy = _acquisition_fixture()
    mission = _mission(
        policy_id=POLICY_ID,
        policy_sha256=hashlib.sha256(policy).hexdigest(),
        include_pin=False,
    )
    mission["metadata"] = {
        "source_trust_policy_pins": [
            {"policy_id": POLICY_ID, "sha256": hashlib.sha256(policy).hexdigest()}
        ]
    }
    mission_bytes = _json_bytes(mission)
    mission_path = tmp_path / "mission-metadata-only.json"
    mission_path.write_bytes(mission_bytes)
    program = build_research_program(mission_path, repository_root=tmp_path)
    with pytest.raises(MissionSourceTrustBridgeError, match="first-class"):
        qualify_acquisition_record_under_expected_mission_policy(
            mission_bytes=mission_bytes,
            expected_mission_sha256=hashlib.sha256(mission_bytes).hexdigest(),
            program_state=program,
            policy_id=POLICY_ID,
            evidence_bytes=evidence,
            acquisition_manifest_bytes=manifest,
            acquisition_declaration_bytes=declaration,
            source_trust_policy_bytes=policy,
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("schema_version", "1.2", "schema_version"),
        ("program_policy_version", "2.0", "program_policy_version"),
    ],
)
def test_program_contract_versions_are_pinned_fail_closed(
    tmp_path: Path,
    field: str,
    value: str,
    message: str,
) -> None:
    mission, program, evidence, manifest, declaration, policy = _program_fixture(tmp_path)
    mutated = copy.deepcopy(program)
    mutated[field] = value
    with pytest.raises(MissionSourceTrustBridgeError, match=message):
        qualify_acquisition_record_under_expected_mission_policy(
            mission_bytes=mission,
            expected_mission_sha256=hashlib.sha256(mission).hexdigest(),
            program_state=mutated,
            policy_id=POLICY_ID,
            evidence_bytes=evidence,
            acquisition_manifest_bytes=manifest,
            acquisition_declaration_bytes=declaration,
            source_trust_policy_bytes=policy,
        )


def test_program_mission_binding_substitution_fails_closed(tmp_path: Path) -> None:
    mission, program, evidence, manifest, declaration, policy = _program_fixture(tmp_path)
    mutated = copy.deepcopy(program)
    mutated["mission_binding"]["sha256"] = "0" * 64
    with pytest.raises(MissionSourceTrustBridgeError, match="mission binding"):
        qualify_acquisition_record_under_expected_mission_policy(
            mission_bytes=mission,
            expected_mission_sha256=hashlib.sha256(mission).hexdigest(),
            program_state=mutated,
            policy_id=POLICY_ID,
            evidence_bytes=evidence,
            acquisition_manifest_bytes=manifest,
            acquisition_declaration_bytes=declaration,
            source_trust_policy_bytes=policy,
        )


def test_program_normalized_mission_substitution_fails_closed(tmp_path: Path) -> None:
    mission, program, evidence, manifest, declaration, policy = _program_fixture(tmp_path)
    mutated = copy.deepcopy(program)
    mutated["mission"]["mission_id"] = "substituted"
    with pytest.raises(MissionSourceTrustBridgeError, match="normalized mission"):
        qualify_acquisition_record_under_expected_mission_policy(
            mission_bytes=mission,
            expected_mission_sha256=hashlib.sha256(mission).hexdigest(),
            program_state=mutated,
            policy_id=POLICY_ID,
            evidence_bytes=evidence,
            acquisition_manifest_bytes=manifest,
            acquisition_declaration_bytes=declaration,
            source_trust_policy_bytes=policy,
        )


def test_program_projected_policy_pin_substitution_fails_closed(tmp_path: Path) -> None:
    mission, program, evidence, manifest, declaration, policy = _program_fixture(tmp_path)
    mutated = copy.deepcopy(program)
    mutated["source_trust_policy_pins"][0]["sha256"] = "0" * 64
    with pytest.raises(MissionSourceTrustBridgeError, match="projected source trust policy pins"):
        qualify_acquisition_record_under_expected_mission_policy(
            mission_bytes=mission,
            expected_mission_sha256=hashlib.sha256(mission).hexdigest(),
            program_state=mutated,
            policy_id=POLICY_ID,
            evidence_bytes=evidence,
            acquisition_manifest_bytes=manifest,
            acquisition_declaration_bytes=declaration,
            source_trust_policy_bytes=policy,
        )


def test_requested_policy_id_must_be_the_authenticated_mission_pin(tmp_path: Path) -> None:
    mission, program, evidence, manifest, declaration, policy = _program_fixture(tmp_path)
    with pytest.raises(MissionSourceTrustBridgeError, match="match exactly one"):
        qualify_acquisition_record_under_expected_mission_policy(
            mission_bytes=mission,
            expected_mission_sha256=hashlib.sha256(mission).hexdigest(),
            program_state=program,
            policy_id="other-policy",
            evidence_bytes=evidence,
            acquisition_manifest_bytes=manifest,
            acquisition_declaration_bytes=declaration,
            source_trust_policy_bytes=policy,
        )


def test_policy_byte_drift_cannot_be_reauthorized_by_the_bridge(tmp_path: Path) -> None:
    mission, program, evidence, manifest, declaration, policy = _program_fixture(tmp_path)
    with pytest.raises(MissionSourceTrustBridgeError, match="mission-pinned"):
        qualify_acquisition_record_under_expected_mission_policy(
            mission_bytes=mission,
            expected_mission_sha256=hashlib.sha256(mission).hexdigest(),
            program_state=program,
            policy_id=POLICY_ID,
            evidence_bytes=evidence,
            acquisition_manifest_bytes=manifest,
            acquisition_declaration_bytes=declaration,
            source_trust_policy_bytes=policy + b" ",
        )


def test_policy_internal_id_must_match_authenticated_mission_pin(tmp_path: Path) -> None:
    evidence, manifest, declaration, other_policy = _acquisition_fixture(
        policy_id="different-internal-policy-id"
    )
    mission = _mission(
        policy_id=POLICY_ID,
        policy_sha256=hashlib.sha256(other_policy).hexdigest(),
    )
    mission_bytes = _json_bytes(mission)
    mission_path = tmp_path / "mission-policy-id-mismatch.json"
    mission_path.write_bytes(mission_bytes)
    program = build_research_program(mission_path, repository_root=tmp_path)
    with pytest.raises(MissionSourceTrustBridgeError, match="policy ID"):
        qualify_acquisition_record_under_expected_mission_policy(
            mission_bytes=mission_bytes,
            expected_mission_sha256=hashlib.sha256(mission_bytes).hexdigest(),
            program_state=program,
            policy_id=POLICY_ID,
            evidence_bytes=evidence,
            acquisition_manifest_bytes=manifest,
            acquisition_declaration_bytes=declaration,
            source_trust_policy_bytes=other_policy,
        )


def test_downstream_qualification_authority_expansion_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mission, program, evidence, manifest, declaration, policy = _program_fixture(tmp_path)
    real = qualify_acquisition_record_under_pinned_policy(
        evidence_bytes=evidence,
        acquisition_manifest_bytes=manifest,
        acquisition_declaration_bytes=declaration,
        source_trust_policy_bytes=policy,
        expected_source_trust_policy_sha256=hashlib.sha256(policy).hexdigest(),
    )
    expanded = dict(real)
    expanded["execution_authorized"] = True
    monkeypatch.setattr(
        bridge,
        "qualify_acquisition_record_under_pinned_policy",
        lambda **kwargs: expanded,
    )
    with pytest.raises(MissionSourceTrustBridgeError, match="broadened"):
        qualify_acquisition_record_under_expected_mission_policy(
            mission_bytes=mission,
            expected_mission_sha256=hashlib.sha256(mission).hexdigest(),
            program_state=program,
            policy_id=POLICY_ID,
            evidence_bytes=evidence,
            acquisition_manifest_bytes=manifest,
            acquisition_declaration_bytes=declaration,
            source_trust_policy_bytes=policy,
        )


def test_downstream_qualification_schema_growth_requires_reaudit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mission, program, evidence, manifest, declaration, policy = _program_fixture(tmp_path)
    real = qualify_acquisition_record_under_pinned_policy(
        evidence_bytes=evidence,
        acquisition_manifest_bytes=manifest,
        acquisition_declaration_bytes=declaration,
        source_trust_policy_bytes=policy,
        expected_source_trust_policy_sha256=hashlib.sha256(policy).hexdigest(),
    )
    expanded = dict(real)
    expanded["new_authority_surface"] = False
    monkeypatch.setattr(
        bridge,
        "qualify_acquisition_record_under_pinned_policy",
        lambda **kwargs: expanded,
    )
    with pytest.raises(MissionSourceTrustBridgeError, match="exact key set"):
        qualify_acquisition_record_under_expected_mission_policy(
            mission_bytes=mission,
            expected_mission_sha256=hashlib.sha256(mission).hexdigest(),
            program_state=program,
            policy_id=POLICY_ID,
            evidence_bytes=evidence,
            acquisition_manifest_bytes=manifest,
            acquisition_declaration_bytes=declaration,
            source_trust_policy_bytes=policy,
        )



@pytest.mark.parametrize(
    "field",
    [
        "mission_bytes",
        "evidence_bytes",
        "acquisition_manifest_bytes",
        "acquisition_declaration_bytes",
        "source_trust_policy_bytes",
    ],
)
def test_exact_byte_inputs_fail_closed_with_bridge_error(
    tmp_path: Path,
    field: str,
) -> None:
    mission, program, evidence, manifest, declaration, policy = _program_fixture(tmp_path)
    values: dict[str, object] = {
        "mission_bytes": mission,
        "expected_mission_sha256": hashlib.sha256(mission).hexdigest(),
        "program_state": program,
        "policy_id": POLICY_ID,
        "evidence_bytes": evidence,
        "acquisition_manifest_bytes": manifest,
        "acquisition_declaration_bytes": declaration,
        "source_trust_policy_bytes": policy,
    }
    values[field] = "not-bytes"
    with pytest.raises(
        MissionSourceTrustBridgeError,
        match=rf"{field} must be exact bytes",
    ):
        qualify_acquisition_record_under_expected_mission_policy(**values)  # type: ignore[arg-type]


def test_non_mapping_program_state_fails_closed_with_bridge_error(tmp_path: Path) -> None:
    mission, _, evidence, manifest, declaration, policy = _program_fixture(tmp_path)
    with pytest.raises(MissionSourceTrustBridgeError, match="program_state must be an object"):
        qualify_acquisition_record_under_expected_mission_policy(
            mission_bytes=mission,
            expected_mission_sha256=hashlib.sha256(mission).hexdigest(),
            program_state="not-an-object",  # type: ignore[arg-type]
            policy_id=POLICY_ID,
            evidence_bytes=evidence,
            acquisition_manifest_bytes=manifest,
            acquisition_declaration_bytes=declaration,
            source_trust_policy_bytes=policy,
        )


def test_program_projection_comparison_is_type_strict_for_bool_int_alias(
    tmp_path: Path,
) -> None:
    mission, program, evidence, manifest, declaration, policy = _program_fixture(tmp_path)
    mutated = copy.deepcopy(program)
    # Exact mission has enabled=False. Python equality treats False == 0, so a normal
    # dict comparison would accept this type substitution even though JSON semantics differ.
    mutated["mission"]["workstreams"][0]["enabled"] = 0
    with pytest.raises(MissionSourceTrustBridgeError, match="normalized mission"):
        qualify_acquisition_record_under_expected_mission_policy(
            mission_bytes=mission,
            expected_mission_sha256=hashlib.sha256(mission).hexdigest(),
            program_state=mutated,
            policy_id=POLICY_ID,
            evidence_bytes=evidence,
            acquisition_manifest_bytes=manifest,
            acquisition_declaration_bytes=declaration,
            source_trust_policy_bytes=policy,
        )
