from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from run_phase_a_e_acceptance import run_acceptance  # noqa: E402


def test_phase_a_e_acceptance_uses_real_case_and_preserves_empirical_gaps(
    tmp_path: Path,
) -> None:
    outputs = run_acceptance(tmp_path / "acceptance")
    summary = json.loads(outputs["summary"].read_text(encoding="utf-8"))
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))

    assert summary["status"] == "architecture_acceptance_passed_with_empirical_gaps"
    assert summary["architecture_acceptance_passed"] is True
    assert summary["scientific_hypothesis_verified"] is False
    assert summary["unresolved_github_issues"] == [76, 156]

    assert summary["phases"]["A"]["scientific_status_changed"] is False
    assert summary["phases"]["B"]["material_composition_known"] is False
    assert summary["phases"]["B"]["composition_inferred"] is False
    assert summary["phases"]["C"]["selected_analysis"] == (
        "design_identifiability_audit"
    )
    assert summary["phases"]["C"]["bounded_regression_authorized"] is False
    assert summary["phases"]["D"][
        "characterization_normalized_into_scientific_evidence"
    ] is False
    assert summary["phases"]["E"]["selected_candidate_id"] == (
        "stage_1_complete_observed_grid"
    )
    assert summary["phases"]["E"]["expected_information_gain"] == {
        "status": "not_quantified",
        "value": None,
    }
    assert summary["phases"]["E"]["second_executor_introduced"] is False
    assert summary["phases"]["E"][
        "physical_experiment_execution_authorized"
    ] is False

    boundary = summary["scientific_boundary"]
    assert boundary["network_required_for_acceptance"] is False
    assert boundary["synthetic_scientific_measurements_used"] is False
    assert boundary["missing_material_composition_inferred"] is False
    assert boundary["response_model_fitted"] is False
    assert boundary["causal_inference_performed"] is False
    assert boundary["optimization_performed"] is False
    assert boundary["expected_information_gain_quantified"] is False

    assert manifest["scientific_hypothesis_verified"] is False
    assert manifest["network_access_performed"] is False
    assert outputs["report"].is_file()
    assert outputs["run_manifest"].is_file()
