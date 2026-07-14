from pathlib import Path

import pytest

from src.platform_core.scientific_execution import (
    ScientificExecutionRequest,
    write_scientific_outputs,
    execute_scientific_request,
)


def test_output_path_policy_rejects_absolute_and_traversal(tmp_path):
    result = execute_scientific_request(
        ScientificExecutionRequest.from_config(
            {
                "execution_id": "path_policy",
                "knowledge_pack_id": "xrd_crystallography_basic_v1",
                "constraint_ids": ["xrd.bragg.geometry"],
                "inputs": [
                    {"variable_id": "two_theta", "value": 44.7, "unit": "degree"},
                    {"variable_id": "wavelength", "value": 1.5406, "unit": "angstrom"},
                ],
            }
        )
    )
    with pytest.raises(ValueError):
        write_scientific_outputs(result, repo_root=tmp_path, output_dir="../bad")
    with pytest.raises(ValueError):
        write_scientific_outputs(result, repo_root=tmp_path, output_dir=str(Path(tmp_path) / "abs"))


def test_scientific_execution_does_not_accept_raw_tables_or_expressions():
    config = {
        "execution_id": "bad_raw_table",
        "knowledge_pack_id": "xrd_crystallography_basic_v1",
        "constraint_ids": ["xrd.bragg.geometry"],
        "inputs": [{"variable_id": "two_theta", "value": "1,2,3\n4,5,6", "unit": "degree"}],
    }
    with pytest.raises(ValueError):
        ScientificExecutionRequest.from_config(config)
