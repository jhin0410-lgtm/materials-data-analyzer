from src.platform_core.scientific_execution import ScientificExecutionRequest, execute_scientific_request


def test_unit_normalization_converts_degree_to_rad_for_scherrer():
    request = ScientificExecutionRequest.from_config(
        {
            "execution_id": "scherrer_units",
            "knowledge_pack_id": "xrd_crystallography_basic_v1",
            "constraint_ids": ["xrd.scherrer.preconditions"],
            "inputs": [
                {"variable_id": "two_theta", "value": 44.7, "unit": "degree"},
                {"variable_id": "wavelength", "value": 0.15406, "unit": "nm"},
                {"variable_id": "fwhm", "value": 0.18, "unit": "degree"},
            ],
            "requested_claim_ids": ["crystallite_size_estimated"],
        }
    )
    result = execute_scientific_request(request)

    conversions = {item.variable_id: item for item in result.unit_conversions}
    assert conversions["wavelength"].conversion_status == "converted"
    assert conversions["fwhm"].conversion_status == "converted"
    assert result.derived_outputs["instrumental_correction_status"] == "uncorrected_estimate"
    assert result.derived_outputs["crystallite_size_nm"] > 0


def test_missing_or_incompatible_unit_blocks_registered_evaluator():
    request = ScientificExecutionRequest.from_config(
        {
            "execution_id": "bad_units",
            "knowledge_pack_id": "xrd_crystallography_basic_v1",
            "constraint_ids": ["xrd.bragg.geometry"],
            "inputs": [
                {"variable_id": "two_theta", "value": 44.7},
                {"variable_id": "wavelength", "value": 1.5406, "unit": "degree"},
            ],
        }
    )
    result = execute_scientific_request(request)

    assert result.overall_status in {"inconsistent", "unavailable"}
    statuses = {item.variable_id: item.conversion_status for item in result.unit_conversions}
    assert statuses["two_theta"] == "missing_unit"
    assert statuses["wavelength"] == "incompatible_unit"
