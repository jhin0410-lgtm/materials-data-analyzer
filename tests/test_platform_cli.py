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


def test_cli_list_plugins_human_output_deterministic():
    result = _run_cli("list-plugins")

    assert result.returncode == 0
    lines = result.stdout.strip().splitlines()
    assert [line.split("\t")[0] for line in lines] == [
        "battery_archive",
        "materials_project",
        "reliability",
        "smart_factory",
    ]


def test_cli_json_output_valid():
    result = _run_cli("--json", "inspect-plugin", "reliability")

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["plugin_id"] == "reliability"
    assert payload["status"] == "scaffolded"


def test_cli_validate_config_and_dry_run_json():
    config = "configs/examples/reliability_trust_dry_run.json"

    validate = _run_cli("--json", "validate-config", config)
    dry_run = _run_cli("--json", "dry-run", config)

    assert validate.returncode == 0
    assert json.loads(validate.stdout)["valid"] is True
    assert dry_run.returncode == 0
    payload = json.loads(dry_run.stdout)
    assert payload["dry_run_plan"]["execution_status"] == "blocked_plugin_not_runnable"


def test_cli_unknown_plugin_exits_nonzero():
    result = _run_cli("inspect-plugin", "missing")

    assert result.returncode == 2
    assert "unknown plugin_id" in result.stderr


def test_cli_show_policy_and_version():
    policy = _run_cli("--json", "show-policy", "reliability_asset_time_aware")
    version = _run_cli("--json", "show-version")

    assert policy.returncode == 0
    assert json.loads(policy.stdout)["policy_type"] == "trust"
    assert version.returncode == 0
    assert json.loads(version.stdout)["platform_version"] == "2.0.1-dev"
