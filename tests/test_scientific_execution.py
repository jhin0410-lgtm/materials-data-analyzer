import math
from pathlib import Path

from src.platform_core.scientific_execution import (
    ScientificExecutionRequest,
    execute_scientific_request,
)


def _execute(config):
    return execute_scientific_request(ScientificExecutionRequest.from_config(config))


def test_bragg_execution_derives_d_spacing_and_rejects_phase_claim():
    result = _execute(
        {
            "execution_id": "test_bragg",
            "knowledge_pack_id": "xrd_crystallography_basic_v1",
            "constraint_ids": ["xrd.bragg.geometry"],
            "inputs": [
                {"variable_id": "two_theta", "value": 44.7, "unit": "degree"},
                {"variable_id": "wavelength", "value": 1.5406, "unit": "angstrom"},
                {"variable_id": "supplied_d_spacing", "value": 2.026, "unit": "angstrom"},
            ],
            "metadata": {"d_spacing_tolerance_angstrom": 0.02},
            "requested_claim_ids": ["dimensionally_consistent", "phase_identification_supported"],
        }
    )

    assert result.overall_status == "conditionally_consistent"
    assert math.isclose(result.derived_outputs["derived_d_spacing_angstrom"], 2.0257010645945237)
    assert result.raw_data_read is False
    assert result.model_training_performed is False
    claims = {claim.claim_id: claim.status for claim in result.claim_evaluations}
    assert claims["dimensionally_consistent"] == "supported"
    assert claims["phase_identification_supported"] == "prohibited"
    assert result.execution_manifest["evidence_graph_edge_count"] > 0


def test_bragg_supplied_d_spacing_outside_tolerance_is_inconsistent():
    result = _execute(
        {
            "execution_id": "test_bragg_bad",
            "knowledge_pack_id": "xrd_crystallography_basic_v1",
            "constraint_ids": ["xrd.bragg.geometry"],
            "inputs": [
                {"variable_id": "two_theta", "value": 44.7, "unit": "degree"},
                {"variable_id": "wavelength", "value": 1.5406, "unit": "angstrom"},
                {"variable_id": "supplied_d_spacing", "value": 2.2, "unit": "angstrom"},
            ],
            "metadata": {"d_spacing_tolerance_angstrom": 0.005},
        }
    )

    assert result.overall_status == "inconsistent"
    assert result.derived_outputs["d_spacing_tolerance_status"] == "outside_tolerance"


def test_request_validation_rejects_paths_and_callable_fields():
    bad_path = {
        "execution_id": "bad",
        "knowledge_pack_id": "xrd_crystallography_basic_v1",
        "constraint_ids": ["xrd.bragg.geometry"],
        "inputs": [{"variable_id": "two_theta", "value": str(Path.cwd() / "raw.csv"), "unit": "degree"}],
    }
    bad_callable = dict(bad_path)
    bad_callable["inputs"] = [{"variable_id": "two_theta", "value": 44.7, "unit": "degree"}]
    bad_callable["callable_name"] = "danger"

    import pytest

    with pytest.raises(ValueError):
        ScientificExecutionRequest.from_config(bad_path)
    with pytest.raises(ValueError):
        ScientificExecutionRequest.from_config(bad_callable)
