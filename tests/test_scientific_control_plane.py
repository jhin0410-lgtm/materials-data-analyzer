from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop.scientific_control_plane import (
    ScientificControlPlaneError,
    build_scientific_control_plane_contract,
    project_legacy_mission_field,
    project_legacy_mission_item,
    project_legacy_mission_metadata,
    project_legacy_mission_workstream,
    validate_scientific_control_plane_contract,
)

_BASE_PATH = Path(__file__).with_name("scientific_control_plane_regression_base.py")
_SPEC = importlib.util.spec_from_file_location("_scientific_control_plane_regression_base", _BASE_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_base = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_base)

_REPLACED = {
    "test_real_legacy_mission_field_requires_exact_classified_projection",
    "test_every_real_legacy_mission_item_has_one_exact_projection",
    "test_legacy_mission_contract_exposes_exact_not_heuristic_projections",
}
for _name in dir(_base):
    if _name.startswith("test_") and _name not in _REPLACED:
        globals()[_name] = getattr(_base, _name)


def _mission_path() -> Path:
    return Path(__file__).resolve().parents[1] / "configs/research/autonomous_in625_production_mission.v1.json"


def _mission_bytes() -> bytes:
    return _mission_path().read_bytes()


def _mission() -> dict[str, object]:
    value = json.loads(_mission_bytes().decode("utf-8"))
    assert isinstance(value, dict)
    return value


def test_real_legacy_mission_field_requires_authenticated_whole_mission_projection() -> None:
    projected = project_legacy_mission_field(mission_bytes=_mission_bytes())
    assert projected["source_field"] == "mission"
    assert projected["science_projection"]
    assert projected["governance_projection"]
    assert projected["whole_mission_validated"] is True
    assert projected["scientific_status_promoted"] is False
    assert projected["execution_authority_granted"] is False

    tampered = _mission_bytes().replace(b"verified IN625", b"forged IN625", 1)
    with pytest.raises(ScientificControlPlaneError, match="frozen mission SHA-256"):
        project_legacy_mission_field(mission_bytes=tampered)


def test_every_real_legacy_mission_item_requires_whole_mission_binding() -> None:
    mission = _mission()
    for collection in ("success_criteria", "constraints", "stop_rules"):
        items = mission[collection]
        assert isinstance(items, list)
        for index, _item in enumerate(items):
            projection = project_legacy_mission_item(
                mission_bytes=_mission_bytes(),
                collection=collection,
                item_index=index,
            )
            assert projection["science_semantic"] or projection["governance_semantic"]
            assert projection["whole_mission_validated"] is True
            assert projection["scientific_status_promoted"] is False
            assert projection["execution_authority_granted"] is False


@pytest.mark.parametrize("malformed_index", [True, False, 0.0, 1.0])
def test_legacy_item_projection_rejects_non_integer_indexes(malformed_index: object) -> None:
    with pytest.raises(ScientificControlPlaneError, match="non-boolean integer"):
        project_legacy_mission_item(
            mission_bytes=_mission_bytes(),
            collection="success_criteria",
            item_index=malformed_index,  # type: ignore[arg-type]
        )


def test_execution_bearing_workstream_and_metadata_receive_exact_split_projections() -> None:
    mission = _mission()
    workstreams = mission["workstreams"]
    assert isinstance(workstreams, list) and len(workstreams) == 1
    workstream = project_legacy_mission_workstream(mission_bytes=_mission_bytes(), item_index=0)
    assert workstream["science_projection"]["scientific_goal_priority"] == 100
    assert workstream["science_projection"]["scientific_goal_enabled"] is True
    assert workstream["governance_projection"]["adapter_id"] == "materials-project-external-source"
    assert workstream["governance_projection"]["execution_route_enabled"] is True
    assert workstream["science_projection_may_modify_execution_policy"] is False

    metadata = mission["metadata"]
    assert isinstance(metadata, dict)
    observed = set()
    for key in metadata:
        projected = project_legacy_mission_metadata(
            mission_bytes=_mission_bytes(), source_key=key
        )
        assert projected["source_value"] == metadata[key]
        assert projected["science_semantic"] or projected["governance_semantic"]
        assert projected["whole_mission_validated"] is True
        assert projected["execution_authority_granted"] is False
        observed.add(key)
    assert observed == set(metadata)


def test_legacy_mission_contract_exposes_whole_binding_and_structured_projections() -> None:
    semantics = build_scientific_control_plane_contract()["mission_projection_semantics"]
    assert semantics["legacy_bounded_mission_is_composite"] is True
    assert semantics["real_legacy_mission_field_requires_classified_projection"] is True
    assert semantics["authenticated_whole_mission_binding_required"] is True
    assert semantics["structured_projection_required_for"] == ["workstreams", "metadata"]
    assert semantics["legacy_mission_raw_sha256"] == {
        "autonomous-in625-production-v1": (
            "7de1c78d1411805623a4687a6d1956517edc009abe5790a0870e89ab6ccb4e88"
        )
    }
    assert semantics["unknown_mission_field_or_item_projection"] == "unresolved_no_authority"
    assert semantics["science_projection_may_modify_execution_policy"] is False


def test_policy_authorized_closed_loop_records_actual_hard_action_limit() -> None:
    inventory = {
        item["surface_id"]: item
        for item in build_scientific_control_plane_contract()["controller_inventory"]
    }
    assert inventory["policy_authorized_closed_loop"]["automatic_looping"] is True
    assert inventory["policy_authorized_closed_loop"]["maximum_actions_per_call"] == 32


def test_control_plane_validation_rejects_bool_int_and_integral_float_type_drift() -> None:
    boolean_drift = copy.deepcopy(build_scientific_control_plane_contract())
    boolean_drift["authority_boundary"]["architecture_metadata_creates_empirical_evidence"] = 0
    with pytest.raises(ScientificControlPlaneError, match="authority_boundary drifted"):
        validate_scientific_control_plane_contract(boolean_drift)

    action_drift = copy.deepcopy(build_scientific_control_plane_contract())
    cycle = next(
        item for item in action_drift["controller_inventory"] if item["surface_id"] == "research_cycle"
    )
    cycle["maximum_actions_per_call"] = True
    with pytest.raises(ScientificControlPlaneError, match="controller_inventory drifted"):
        validate_scientific_control_plane_contract(action_drift)

    float_drift = copy.deepcopy(build_scientific_control_plane_contract())
    cycle = next(
        item for item in float_drift["controller_inventory"] if item["surface_id"] == "research_cycle"
    )
    cycle["maximum_actions_per_call"] = 1.0
    with pytest.raises(ScientificControlPlaneError, match="controller_inventory drifted"):
        validate_scientific_control_plane_contract(float_drift)
