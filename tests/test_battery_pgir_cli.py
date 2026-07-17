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


def test_pgir_cli_validates_example_declaration_and_transition():
    declaration = _run_cli("--json", "validate-pgir-representation", "configs/examples/pgir_representation_conformance.json")
    transition = _run_cli("--json", "validate-pgir-transition", "configs/examples/pgir_transition_validation.json")

    assert declaration["valid"] is True
    assert transition["transition_allowed"] is True


def test_battery_pgir_cli_preview_has_no_side_effects(tmp_path):
    marker = Path("outputs/battery_pgir_v2_3/cli_preview_marker")
    if marker.exists():
        marker.unlink()

    payload = _run_cli("--json", "preview-battery-observation-build", "configs/examples/battery_observation_build.json")

    assert payload["status"] == "preview"
    assert payload["writes_outputs"] is False
    assert payload["network_called"] is False
    assert not marker.exists()


def test_battery_pgir_cli_build_and_validate_local_only_outputs():
    build = _run_cli("--json", "build-battery-cycle-observations", "configs/examples/battery_observation_build.json")
    validate = _run_cli(
        "--json",
        "validate-battery-cycle-observations",
        "outputs/battery_pgir_v2_3/observations/cycle_observations.jsonl",
    )

    assert build["status"] == "built"
    assert build["local_only"] is True
    assert validate["valid"] is True
    assert validate["entity_count"] == build["observation_count"]


def test_battery_pgir_cli_exports_compact_summary_without_row_payload():
    export = _run_cli("--json", "export-battery-pgir-summary")
    readiness = json.loads(Path("data/processed/battery_v2_3_pgir_readiness_decision.json").read_text(encoding="utf-8"))

    assert export["status"] == "exported"
    assert readiness["prediction_ready"] is False
    assert "battery_obs_" not in json.dumps(readiness)
