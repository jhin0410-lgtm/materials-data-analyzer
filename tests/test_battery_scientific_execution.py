from src.platform_core.scientific_execution import ScientificExecutionRequest, execute_scientific_request


def test_battery_cycle_fixture_converts_temperature_and_derives_retention():
    result = execute_scientific_request(
        ScientificExecutionRequest.from_config(
            {
                "execution_id": "battery_fixture",
                "knowledge_pack_id": "battery_degradation_basic_v1",
                "constraint_ids": [
                    "battery.capacity.non_negative",
                    "battery.coulombic_efficiency.bounds",
                    "battery.cycle_index.non_decreasing",
                    "battery.temperature.arrhenius_domain",
                ],
                "inputs": [
                    {"variable_id": "capacity", "value": [2.0, 1.98], "unit": "Ah"},
                    {"variable_id": "coulombic_efficiency", "value": [0.999, 1.001], "unit": "fraction"},
                    {"variable_id": "cycle_index", "value": [1, 2]},
                    {"variable_id": "temperature", "value": 25, "unit": "degC"},
                ],
                "metadata": {"baseline_capacity": 2.0},
                "requested_claim_ids": ["physically_consistent_input"],
            }
        )
    )

    assert result.derived_outputs["capacity_retention"] == [1.0, 0.99]
    assert any(item.variable_id == "temperature" and item.conversion_status == "converted" for item in result.unit_conversions)
    assert {claim.claim_id: claim.status for claim in result.claim_evaluations}["physically_consistent_input"] == "supported"
