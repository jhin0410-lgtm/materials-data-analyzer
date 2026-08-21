from __future__ import annotations

import hashlib
import json

import materials_data_analyzer.research_loop.validated_recursive_cycle_planning as planning
from materials_data_analyzer.research_loop.recursive_resource_budget import (
    DEFAULT_RECURSIVE_LIMITS,
)


def _sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _self_hashed_artifact(*, embedded_limits: dict) -> dict:
    value = {
        "schema_version": planning.VALIDATED_RECURSIVE_PLANNING_SCHEMA_VERSION,
        "policy_version": planning.VALIDATED_RECURSIVE_PLANNING_POLICY_VERSION,
        "handoff_verification": {},
        "planner_verification": {},
        "recursive_checkpoint": {},
        "recursive_resource_budget": {"limits": dict(embedded_limits)},
        "predecessor_validation": None,
        "autonomy_boundary": {},
    }
    value["validated_checkpoint_sha256"] = _sha(value)
    return value


def _validate_with_fake_reconstruction(monkeypatch, artifact: dict, **kwargs):
    captured: dict = {}

    def fake_build(**build_kwargs):
        captured.update(build_kwargs)
        return artifact

    monkeypatch.setattr(
        planning,
        "build_validated_recursive_planning_checkpoint",
        fake_build,
    )
    result = planning.validate_validated_recursive_planning_checkpoint(
        artifact,
        planning_handoff={},
        source_discrepancy_report={},
        source_evaluated_graph={},
        fresh_plan={},
        planner_program_state={},
        **kwargs,
    )
    return result, captured


def test_validator_never_uses_embedded_limits_as_its_own_authority(monkeypatch) -> None:
    forged = {
        "max_cycles": 1000,
        "max_action_slots": 1000,
        "max_planned_cost_units": 1_000_000.0,
    }
    artifact = _self_hashed_artifact(embedded_limits=forged)

    _result, captured = _validate_with_fake_reconstruction(monkeypatch, artifact)

    assert captured["recursive_limits"] == DEFAULT_RECURSIVE_LIMITS
    assert captured["recursive_limits"] != forged


def test_explicit_expected_limits_are_forwarded_to_reconstruction(monkeypatch) -> None:
    expected = {
        "max_cycles": 3,
        "max_action_slots": 2,
        "max_planned_cost_units": 5.0,
    }
    artifact = _self_hashed_artifact(embedded_limits=expected)

    _result, captured = _validate_with_fake_reconstruction(
        monkeypatch,
        artifact,
        recursive_limits=expected,
    )

    assert captured["recursive_limits"] == expected
