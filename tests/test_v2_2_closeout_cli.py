import json
import subprocess
import sys


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "src.cli", "--json", *args],
        check=True,
        text=True,
        capture_output=True,
    )


def test_v2_2_closeout_cli_commands_emit_json():
    commands = [
        "audit-v2-2-scientific-evidence",
        "show-v2-2-capability-matrix",
        "show-v2-2-claim-matrix",
        "show-v2-2-prediction-contexts",
        "show-v2-2-uncertainty-boundaries",
        "validate-v2-2-artifact-lineage",
        "validate-v2-2-result-preservation",
        "evaluate-v2-2-release-readiness",
    ]

    for command in commands:
        payload = json.loads(_run_cli(command).stdout)
        assert payload["schema_version"] == "2.2.6"


def test_v2_2_closeout_export_cli_is_deterministic():
    first = json.loads(_run_cli("export-v2-2-closeout-summary").stdout)
    second = json.loads(_run_cli("export-v2-2-closeout-summary").stdout)

    assert first["status"] == "exported"
    assert first["outputs"] == second["outputs"]
    assert first["release_readiness"] == "release_ready"
