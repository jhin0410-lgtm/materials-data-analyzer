from __future__ import annotations

import json
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop.action_authorization import (
    ActionAuthorizationError,
    assess_action_authorization,
    assess_current_action_authorization,
)
from materials_data_analyzer.research_loop.action_registry import (
    describe_action,
    load_action_registry,
)


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_REGISTRY = ROOT / "configs/research/nasa_protocol_stratification_action_registry.v1.json"
PLANNING_REGISTRY = ROOT / "configs/research/nasa_research_action_registry.v1.json"
EXTERNAL_REQUIREMENT_REGISTRY = (
    ROOT / "configs/research/nasa_external_data_requirement_action_registry.v1.json"
)


def _state_from_contract(
    registry_path: Path,
    action_type: str,
    *,
    repository_root: Path = ROOT,
    actions_remaining: int = 2,
    cost_units_remaining: int = 10,
) -> dict[str, object]:
    registry = load_action_registry(registry_path, repository_root=repository_root)
    contract = describe_action(registry, action_type)
    return {
        "adapter_id": "nasa-battery",
        "domain": "battery_degradation",
        "selected_action": {
            "action_type": action_type,
            "action_version": contract["version"],
            "availability": contract["availability"],
            "cost_units": contract["cost_units"],
            "priority_score": 100,
            "trigger": "test_trigger",
            "rationale": "test rationale",
            "execution_registry_id": registry["registry_id"],
            "execution_registry_sha256": registry["registry_sha256"],
            "execution_registry_path": registry["registry_path"],
        },
        "evidence_gap": {
            "status": "action_expected_to_reduce_uncertainty",
            "requirements": [],
        },
        "stop_state": {
            "status": "continue",
            "selection_status": "ready_to_execute",
            "reason": "typed action selected",
            "reopen_conditions": [],
        },
        "budget": {
            "actions_remaining": actions_remaining,
            "cost_units_remaining": cost_units_remaining,
        },
    }


def test_available_typed_action_is_ready_for_explicit_request_only() -> None:
    state = _state_from_contract(PROTOCOL_REGISTRY, "protocol_stratification")

    result = assess_action_authorization(state, repository_root=ROOT)

    assert result["authorization_status"] == "ready_for_explicit_execution_request"
    assert result["execution_registry_verified"] is True
    assert result["selected_action_binding_verified"] is True
    assert result["budget_verified"] is True
    assert result["explicit_execution_request_required"] is True
    assert result["automatic_execution_authorized"] is False
    assert result["action_executed"] is False
    assert result["scientific_evidence_upgraded"] is False
    assert result["execution_contract"]["binding"]["kind"] == "installed_command"


def test_registry_sha_drift_fails_closed() -> None:
    state = _state_from_contract(PROTOCOL_REGISTRY, "protocol_stratification")
    state["selected_action"]["execution_registry_sha256"] = "0" * 64  # type: ignore[index]

    with pytest.raises(ActionAuthorizationError, match="SHA-256"):
        assess_action_authorization(state, repository_root=ROOT)


def test_action_version_drift_fails_closed() -> None:
    state = _state_from_contract(PROTOCOL_REGISTRY, "protocol_stratification")
    state["selected_action"]["action_version"] = "999"  # type: ignore[index]

    with pytest.raises(ActionAuthorizationError, match="version"):
        assess_action_authorization(state, repository_root=ROOT)


def test_action_cost_drift_fails_closed() -> None:
    state = _state_from_contract(PROTOCOL_REGISTRY, "protocol_stratification")
    state["selected_action"]["cost_units"] = 999  # type: ignore[index]

    with pytest.raises(ActionAuthorizationError, match="cost"):
        assess_action_authorization(state, repository_root=ROOT)


def test_planned_action_is_not_authorized() -> None:
    state = _state_from_contract(PLANNING_REGISTRY, "feature_family_ablation")

    result = assess_action_authorization(state, repository_root=ROOT)

    assert result["authorization_status"] == "denied_action_not_available"
    assert result["automatic_execution_authorized"] is False


def test_source_script_symlink_escape_is_denied(
    tmp_path: Path,
) -> None:
    repository_root = tmp_path / "repo"
    scripts = repository_root / "scripts"
    scripts.mkdir(parents=True)
    outside_script = tmp_path / "outside.py"
    outside_script.write_text("print('outside')\n", encoding="utf-8")
    bound_script = scripts / "run.py"
    try:
        bound_script.symlink_to(outside_script)
    except OSError as exc:
        pytest.skip(f"symlink creation is unavailable on this platform: {exc}")

    payload = json.loads(EXTERNAL_REQUIREMENT_REGISTRY.read_text(encoding="utf-8"))
    payload["actions"][0]["binding"]["path"] = "scripts/run.py"
    registry_path = repository_root / "registry.json"
    registry_path.write_text(json.dumps(payload), encoding="utf-8")
    state = _state_from_contract(
        registry_path,
        "external_data_requirement_generation",
        repository_root=repository_root,
    )

    with pytest.raises(ActionAuthorizationError, match="outside repository root"):
        assess_action_authorization(state, repository_root=repository_root)


def test_action_budget_exhaustion_denies_request() -> None:
    state = _state_from_contract(
        PROTOCOL_REGISTRY,
        "protocol_stratification",
        actions_remaining=0,
    )

    result = assess_action_authorization(state, repository_root=ROOT)

    assert result["authorization_status"] == "denied_action_budget_exhausted"
    assert result["execution_registry_verified"] is True
    assert result["budget_verified"] is False


def test_cost_budget_exhaustion_denies_request() -> None:
    state = _state_from_contract(
        PROTOCOL_REGISTRY,
        "protocol_stratification",
        cost_units_remaining=0,
    )

    result = assess_action_authorization(state, repository_root=ROOT)

    assert result["authorization_status"] == "denied_cost_budget_exceeded"
    assert result["automatic_execution_authorized"] is False


def test_terminal_state_is_not_authorizable() -> None:
    state = _state_from_contract(PROTOCOL_REGISTRY, "protocol_stratification")
    state["selected_action"] = None
    state["stop_state"] = {
        "status": "terminal_for_current_scope",
        "selection_status": "no_positive_value_action",
        "reason": "closed",
        "reopen_conditions": ["new evidence"],
    }

    result = assess_action_authorization(state, repository_root=ROOT)

    assert result["authorization_status"] == "not_authorizable_current_state"
    assert result["automatic_execution_authorized"] is False


def test_current_materials_project_state_is_not_authorizable() -> None:
    result = assess_current_action_authorization(
        "materials-project-external-source",
        repository_root=ROOT,
    )

    assert result["authorization_status"] == "not_authorizable_current_state"
    assert result["selected_action"] is None


def test_current_tm_fe_si_state_is_not_authorizable() -> None:
    result = assess_current_action_authorization(
        "tm-fe-si-descriptive",
        repository_root=ROOT,
    )

    assert result["authorization_status"] == "not_authorizable_current_state"
    assert result["automatic_execution_authorized"] is False
