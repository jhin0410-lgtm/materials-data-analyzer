from src.platform_core.scientific_execution import ScientificExecutionRequest, execute_scientific_request


def test_scherrer_corrected_broadening_estimate_and_claim_boundary():
    result = execute_scientific_request(
        ScientificExecutionRequest.from_config(
            {
                "execution_id": "scherrer_corrected",
                "knowledge_pack_id": "xrd_crystallography_basic_v1",
                "constraint_ids": ["xrd.scherrer.preconditions"],
                "inputs": [
                    {"variable_id": "two_theta", "value": 44.7, "unit": "degree"},
                    {"variable_id": "wavelength", "value": 1.5406, "unit": "angstrom"},
                    {"variable_id": "fwhm", "value": 0.00314159, "unit": "rad"},
                    {"variable_id": "instrumental_broadening", "value": 0.001, "unit": "rad"},
                    {"variable_id": "shape_factor", "value": 0.9},
                ],
                "metadata": {"instrumental_broadening_corrected": True, "strain_broadening_separated": True},
                "requested_claim_ids": ["crystallite_size_estimated", "phase_identification_supported"],
            }
        )
    )

    assert result.derived_outputs["instrumental_correction_status"] == "instrumental_broadening_corrected"
    assert result.derived_outputs["crystallite_size_nm"] > 0
    claims = {claim.claim_id: claim.status for claim in result.claim_evaluations}
    assert claims["crystallite_size_estimated"] == "supported"
    assert claims["phase_identification_supported"] == "prohibited"


def test_scherrer_corrected_beta_invalid_when_instrumental_broadening_too_large():
    result = execute_scientific_request(
        ScientificExecutionRequest.from_config(
            {
                "execution_id": "scherrer_invalid_beta",
                "knowledge_pack_id": "xrd_crystallography_basic_v1",
                "constraint_ids": ["xrd.scherrer.preconditions"],
                "inputs": [
                    {"variable_id": "two_theta", "value": 44.7, "unit": "degree"},
                    {"variable_id": "wavelength", "value": 1.5406, "unit": "angstrom"},
                    {"variable_id": "fwhm", "value": 0.001, "unit": "rad"},
                    {"variable_id": "instrumental_broadening", "value": 0.002, "unit": "rad"},
                ],
            }
        )
    )

    assert result.overall_status in {"inconsistent", "unavailable"}
    assert result.derived_outputs["instrumental_correction_status"] == "invalid_corrected_beta"
