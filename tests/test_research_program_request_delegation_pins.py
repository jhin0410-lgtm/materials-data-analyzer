from __future__ import annotations

import json
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop import mission_source_trust_bridge as source_bridge
from materials_data_analyzer.research_loop.mission_source_trust_bridge import (
    MissionSourceTrustBridgeError,
)
from materials_data_analyzer.research_loop.research_program import (
    LEGACY_MISSION_SCHEMA_VERSION,
    LEGACY_PROGRAM_SCHEMA_VERSION,
    MISSION_SCHEMA_VERSION,
    MISSION_SUPPORTED_SCHEMA_VERSIONS,
    PROGRAM_SCHEMA_VERSION,
    PROGRAM_SUPPORTED_SCHEMA_VERSIONS,
    SOURCE_TRUST_MISSION_SCHEMA_VERSION,
    ResearchProgramError,
    build_research_program,
    validate_research_mission,
)

SOURCE_POLICY_ID = "materials-project-structure-records-v1"
SOURCE_POLICY_SHA = "a" * 64
REQUEST_POLICY_ID = "request-delegation-policy-v1"
REQUEST_POLICY_SHA = "b" * 64


def _mission(schema_version: str) -> dict[str, object]:
    return {
        "schema_version": schema_version,
        "mission_id": "request-delegation-pin-test",
        "mission": "Validate versioned mission policy-pin namespaces without granting execution authority.",
        "success_criteria": [
            "Only schema-authorized first-class policy-pin namespaces are accepted."
        ],
        "constraints": ["Policy pins are data bindings only."],
        "stop_rules": ["Stop on any malformed or ambiguous policy pin."],
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
                "role": "schema regression",
                "enabled": False,
            }
        ],
    }


def _source_pin() -> dict[str, str]:
    return {"policy_id": SOURCE_POLICY_ID, "sha256": SOURCE_POLICY_SHA}


def _request_pin() -> dict[str, str]:
    return {"policy_id": REQUEST_POLICY_ID, "sha256": REQUEST_POLICY_SHA}


def _build(tmp_path: Path, mission: dict[str, object]) -> dict[str, object]:
    mission_path = tmp_path / "mission.json"
    mission_path.write_text(json.dumps(mission), encoding="utf-8")
    return build_research_program(mission_path, repository_root=tmp_path)


def test_schema_version_sets_preserve_all_prior_mission_and_program_versions() -> None:
    assert LEGACY_MISSION_SCHEMA_VERSION == "1.0"
    assert SOURCE_TRUST_MISSION_SCHEMA_VERSION == "1.1"
    assert MISSION_SCHEMA_VERSION == "1.2"
    assert MISSION_SUPPORTED_SCHEMA_VERSIONS == ("1.0", "1.1", "1.2")
    assert LEGACY_PROGRAM_SCHEMA_VERSION == "1.1"
    assert PROGRAM_SCHEMA_VERSION == "1.2"
    assert PROGRAM_SUPPORTED_SCHEMA_VERSIONS == ("1.1", "1.2")


@pytest.mark.parametrize("schema_version", ["1.0", "1.1", "1.2"])
def test_all_supported_mission_versions_remain_valid_without_optional_pins(
    schema_version: str,
) -> None:
    normalized = validate_research_mission(_mission(schema_version))
    assert normalized["schema_version"] == schema_version
    assert "source_trust_policy_pins" not in normalized
    assert "request_delegation_policy_pins" not in normalized


def test_source_trust_pins_remain_valid_in_1_1_and_1_2() -> None:
    for schema_version in ("1.1", "1.2"):
        mission = _mission(schema_version)
        mission["source_trust_policy_pins"] = [_source_pin()]
        normalized = validate_research_mission(mission)
        assert normalized["source_trust_policy_pins"] == [_source_pin()]


def test_source_trust_pins_remain_forbidden_in_1_0() -> None:
    mission = _mission("1.0")
    mission["source_trust_policy_pins"] = [_source_pin()]
    with pytest.raises(ResearchProgramError, match="source_trust_policy_pins requires"):
        validate_research_mission(mission)


def test_request_delegation_pins_are_valid_only_in_1_2() -> None:
    mission = _mission("1.2")
    mission["request_delegation_policy_pins"] = [_request_pin()]
    normalized = validate_research_mission(mission)
    assert normalized["request_delegation_policy_pins"] == [_request_pin()]

    for schema_version in ("1.0", "1.1"):
        older = _mission(schema_version)
        older["request_delegation_policy_pins"] = [_request_pin()]
        with pytest.raises(
            ResearchProgramError,
            match="request_delegation_policy_pins requires mission schema_version 1.2",
        ):
            validate_research_mission(older)


def test_explicit_request_delegation_pin_list_must_be_nonempty() -> None:
    mission = _mission("1.2")
    mission["request_delegation_policy_pins"] = []
    with pytest.raises(ResearchProgramError, match="must be a non-empty list"):
        validate_research_mission(mission)


@pytest.mark.parametrize(
    ("pins", "message"),
    [
        (
            [
                _request_pin(),
                {"policy_id": REQUEST_POLICY_ID, "sha256": "c" * 64},
            ],
            "duplicate request delegation policy policy_id",
        ),
        (
            [
                _request_pin(),
                {"policy_id": "request-delegation-policy-v2", "sha256": REQUEST_POLICY_SHA},
            ],
            "duplicate request delegation policy sha256",
        ),
    ],
)
def test_request_delegation_duplicate_id_or_sha_fails_closed(
    pins: list[dict[str, str]],
    message: str,
) -> None:
    mission = _mission("1.2")
    mission["request_delegation_policy_pins"] = pins
    with pytest.raises(ResearchProgramError, match=message):
        validate_research_mission(mission)


@pytest.mark.parametrize(
    ("pin", "message"),
    [
        (
            {"policy_id": REQUEST_POLICY_ID, "sha256": REQUEST_POLICY_SHA.upper()},
            "lowercase SHA-256",
        ),
        (
            {"policy_id": f" {REQUEST_POLICY_ID}", "sha256": REQUEST_POLICY_SHA},
            "without surrounding whitespace",
        ),
        (
            {
                "policy_id": REQUEST_POLICY_ID,
                "sha256": REQUEST_POLICY_SHA,
                "source": {"url": "https://example.invalid/policy.json"},
            },
            "unknown keys",
        ),
    ],
)
def test_request_delegation_pin_shape_is_strict(
    pin: dict[str, object],
    message: str,
) -> None:
    mission = _mission("1.2")
    mission["request_delegation_policy_pins"] = [pin]
    with pytest.raises(ResearchProgramError, match=message):
        validate_research_mission(mission)


def test_metadata_cannot_substitute_for_first_class_request_delegation_pins(
    tmp_path: Path,
) -> None:
    mission = _mission("1.2")
    mission["metadata"] = {"request_delegation_policy_pins": [_request_pin()]}
    normalized = validate_research_mission(mission)
    assert "request_delegation_policy_pins" not in normalized

    program = _build(tmp_path, mission)
    assert program["schema_version"] == "1.2"
    assert program["request_delegation_policy_pins"] == []


def test_cross_namespace_policy_id_collision_fails_closed() -> None:
    mission = _mission("1.2")
    mission["source_trust_policy_pins"] = [_source_pin()]
    mission["request_delegation_policy_pins"] = [
        {"policy_id": SOURCE_POLICY_ID, "sha256": REQUEST_POLICY_SHA}
    ]
    with pytest.raises(ResearchProgramError, match="must not reuse policy_id"):
        validate_research_mission(mission)


def test_cross_namespace_policy_sha_collision_fails_closed() -> None:
    mission = _mission("1.2")
    mission["source_trust_policy_pins"] = [_source_pin()]
    mission["request_delegation_policy_pins"] = [
        {"policy_id": REQUEST_POLICY_ID, "sha256": SOURCE_POLICY_SHA}
    ]
    with pytest.raises(ResearchProgramError, match="must not reuse sha256"):
        validate_research_mission(mission)


@pytest.mark.parametrize(
    ("mission_version", "expected_program_version"),
    [("1.0", "1.1"), ("1.1", "1.1"), ("1.2", "1.2")],
)
def test_program_schema_version_tracks_authority_relevant_mission_version(
    tmp_path: Path,
    mission_version: str,
    expected_program_version: str,
) -> None:
    program = _build(tmp_path, _mission(mission_version))
    assert program["schema_version"] == expected_program_version
    if expected_program_version == "1.1":
        assert "request_delegation_policy_pins" not in program
    else:
        assert program["request_delegation_policy_pins"] == []


def test_program_1_2_projects_request_delegation_pins_as_data_only(tmp_path: Path) -> None:
    mission = _mission("1.2")
    mission["source_trust_policy_pins"] = [_source_pin()]
    mission["request_delegation_policy_pins"] = [_request_pin()]
    program = _build(tmp_path, mission)

    assert program["schema_version"] == "1.2"
    assert program["mission"]["request_delegation_policy_pins"] == [_request_pin()]
    assert program["request_delegation_policy_pins"] == [_request_pin()]
    assert program["source_trust_policy_pins"] == [_source_pin()]
    boundary = program["autonomy_boundary"]
    assert boundary["typed_action_execution_performed"] is False
    assert boundary["network_access_performed"] is False
    assert boundary["physical_experiment_execution_available"] is False
    assert boundary["scientific_evidence_upgraded"] is False


def test_existing_source_trust_bridge_rejects_mission_1_2() -> None:
    mission = _mission("1.2")
    mission["source_trust_policy_pins"] = [_source_pin()]
    raw = (json.dumps(mission, sort_keys=True, separators=(",", ":")) + "\n").encode()
    with pytest.raises(
        MissionSourceTrustBridgeError,
        match="requires mission schema_version 1.1",
    ):
        source_bridge._normalized_mission(raw)
