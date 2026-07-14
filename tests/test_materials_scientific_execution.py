from src.platform_core.scientific_execution import ScientificExecutionRequest, execute_scientific_request


def test_materials_composition_fixture_derives_weighted_descriptor():
    result = execute_scientific_request(
        ScientificExecutionRequest.from_config(
            {
                "execution_id": "materials_fixture",
                "knowledge_pack_id": "materials_basic_v1",
                "constraint_ids": [
                    "materials.composition_fraction.non_negative",
                    "materials.composition_fraction.sum_to_one",
                    "materials.energy_above_hull.non_negative_tolerance",
                ],
                "inputs": [
                    {"variable_id": "composition_fraction", "value": [0.5, 0.3, 0.2], "unit": "fraction"},
                    {"variable_id": "energy_above_hull_ev_atom", "value": -0.0000002, "unit": "eV"},
                ],
                "metadata": {"elements": ["Fe", "Si", "C"], "element_property_values": [1.26, 1.11, 0.67]},
                "requested_claim_ids": ["conservation_respected"],
            }
        )
    )

    assert result.derived_outputs["composition_weighted_property_mean"] > 0
    assert {claim.claim_id: claim.status for claim in result.claim_evaluations}["conservation_respected"] == "supported"


def test_materials_duplicate_elements_are_findings_not_synthesizability_claims():
    result = execute_scientific_request(
        ScientificExecutionRequest.from_config(
            {
                "execution_id": "materials_duplicate",
                "knowledge_pack_id": "materials_basic_v1",
                "constraint_ids": ["materials.composition_fraction.sum_to_one"],
                "inputs": [{"variable_id": "composition_fraction", "value": [0.5, 0.5], "unit": "fraction"}],
                "metadata": {"elements": ["Fe", "Fe"]},
            }
        )
    )

    assert any(finding.remediation_code == "deduplicate_composition_elements" for finding in result.findings)
