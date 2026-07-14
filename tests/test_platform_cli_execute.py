import json
import subprocess
import sys


def _run_cli(*args):
    return subprocess.run(
        [sys.executable, "-m", "src.cli", *args],
        check=False,
        capture_output=True,
        text=True,
    )


def test_cli_lists_executable_adapter_policy():
    result = _run_cli("--json", "show-execution-policy", "reliability_trust_closeout")

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["execution_allowed"] is True
    assert payload["allowed_modes"] == ["verify"]
    assert payload["network_allowed"] is False
    assert payload["raw_data_allowed"] is False


def test_cli_execute_blocks_disabled_adapter():
    result = _run_cli(
        "--json",
        "execute",
        "configs/examples/materials_project_trust_manifest_dry_run.json",
        "--mode",
        "verify",
    )

    assert result.returncode == 4
    payload = json.loads(result.stdout)
    assert payload["adapter_id"] == "materials_project_trust_closeout"
