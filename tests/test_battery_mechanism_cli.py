import json
import subprocess
import sys
from pathlib import Path


def _run_cli(*args):
    result = subprocess.run(
        [sys.executable, "-m", "src.cli", *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def test_battery_mechanism_cli_lists_and_inspects_candidates():
    listing = _run_cli("--json", "list-battery-mechanism-candidates")
    inspected = _run_cli("--json", "inspect-battery-mechanism-candidate", "arrhenius_temperature_dependence")

    assert listing["status"] == "available"
    assert listing["model_or_solver_executed"] is False
    assert inspected["candidate"]["mechanism_id"] == "arrhenius_temperature_dependence"
    assert inspected["candidate"]["possible_operator_role"] == "Evaluator"


def test_battery_mechanism_cli_audits_without_network_or_solver():
    condition = _run_cli("--json", "audit-battery-condition-coverage", "configs/examples/battery_mechanism_candidate_audit.json")
    protocol = _run_cli("--json", "audit-battery-protocol-comparability", "configs/examples/battery_protocol_comparability_audit.json")
    identifiability = _run_cli("--json", "assess-battery-mechanism-identifiability", "configs/examples/battery_mechanism_candidate_audit.json")

    assert condition["status"] == "audited"
    assert protocol["status"] == "audited"
    assert identifiability["status"] == "assessed"
    assert condition["network_called"] is False
    assert protocol["model_or_solver_executed"] is False
    diffusion = {item["mechanism_id"]: item for item in identifiability["identifiability"]}["diffusion_transport"]
    assert diffusion["overall_status"] == "not_identifiable_from_current_data"


def test_battery_mechanism_cli_exports_and_validates_compact_output():
    export = _run_cli("--json", "export-battery-mechanism-audit-summary", "--tracked-only")
    decision = _run_cli(
        "--json",
        "validate-battery-mechanism-audit",
        "data/processed/battery_v2_3_3_operator_selection_decision.json",
    )
    selected = _run_cli("--json", "select-battery-bounded-evaluator", "configs/examples/battery_mechanism_operator_selection.json")
    gaps = _run_cli("--json", "show-battery-mechanism-evidence-gaps")

    assert export["status"] == "exported"
    assert export["local_outputs"] == {}
    assert decision["valid"] is True
    assert selected["status"] == "descriptive_evaluator_only"
    assert selected["selected_evaluator_id"] == "battery_capacity_trajectory_consistency_evaluator_v1"
    assert any(gap["gap_id"] == "gap_electrode_geometry" for gap in gaps["evidence_gaps"])
    assert not Path("outputs/battery_mechanism_audit_v2_3/cli_unexpected").exists()
