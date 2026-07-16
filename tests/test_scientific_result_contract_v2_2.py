from src.platform_core.scientific_execution import execute_scientific_config


def test_scientific_execution_result_accepts_optional_entity_quantity_fields():
    result = execute_scientific_config(
        {
            "schema_version": "2.1",
            "execution_id": "result_contract_v2_2",
            "knowledge_pack_id": "xrd_crystallography_basic_v1",
            "constraint_ids": ["xrd.bragg.geometry"],
            "inputs": [
                {"variable_id": "two_theta", "value": 44.7, "unit": "degree"},
                {"variable_id": "wavelength", "value": 1.5406, "unit": "angstrom"},
            ],
            "credential_policy": {"store_credentials": False},
        },
        persist=False,
    )
    payload = result.to_dict()

    assert payload["schema_version"] == "2.1"
    assert payload["output_entities"] == []
    assert payload["output_quantities"] == []
    assert payload["uncertainty_status"] == "not_evaluated"
    assert payload["relation_refs"] == []
    assert payload["operator_refs"] == []
