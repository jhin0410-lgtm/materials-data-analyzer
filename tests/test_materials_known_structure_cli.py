import json
import subprocess
import sys


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "src.cli", "--json", *args],
        check=True,
        capture_output=True,
        text=True,
    )


def test_known_structure_cli_show_validate_and_claim_boundary():
    shown = json.loads(_run_cli("show-materials-known-structure-comparison", "latest").stdout)
    validated = json.loads(
        _run_cli(
            "validate-materials-known-structure-result",
            "data/processed/materials_v2_2_5_predictive_value_decision.json",
        ).stdout
    )
    claim = json.loads(
        _run_cli(
            "evaluate-materials-structure-predictive-claim",
            "data/processed/materials_v2_2_5_predictive_value_decision.json",
        ).stdout
    )
    uncertainty = json.loads(
        _run_cli(
            "show-materials-prediction-uncertainty",
            "data/processed/materials_v2_2_5_prediction_uncertainty_summary.csv",
        ).stdout
    )

    assert shown["schema_version"] == "2.2.5"
    assert validated["valid"] is True
    assert claim["representative_model_selected"] is False
    assert "DFT_replacement" in claim["prohibited_claims"]
    assert uncertainty["interpretation"] == "prediction_interval_diagnostic_not_dft_uncertainty"
