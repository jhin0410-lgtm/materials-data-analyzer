from src.platform_core.scientific_entities import validate_entity_payload


def test_trajectory_entity_metadata_contract_is_schema_readiness_only():
    payload = {
        "entity_id": "trajectory_demo",
        "entity_type": "TrajectoryEntity",
        "schema_id": "scientific_entity_schema_v2",
        "schema_version": "2.2.2",
        "domain": "dynamic_physics_synthetic",
        "attributes": {
            "ordered_state_refs": ["state:0", "state:1"],
            "time_axis": {"unit": "s"},
            "transition_operator_refs": ["operator:metadata_only"],
            "solver_metadata": {"implemented": False},
            "numerical_tolerance": {"status": "metadata_only"},
            "convergence_status": "not_run",
        },
        "artifact_refs": ["outputs/synthetic/trajectory.json"],
    }

    result = validate_entity_payload(payload)

    assert result.valid is True
    assert result.validation_status in {"valid", "warning"}
