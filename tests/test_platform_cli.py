import json
import subprocess
import sys
from pathlib import Path


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
    assert payload["status"] == "dry_run_ready"


def test_cli_validate_config_and_dry_run_json():
    config = "configs/examples/reliability_trust_dry_run.json"

    validate = _run_cli("--json", "validate-config", config)
    dry_run = _run_cli("--json", "dry-run", config)

    assert validate.returncode == 0
    assert json.loads(validate.stdout)["valid"] is True
    assert dry_run.returncode == 0
    payload = json.loads(dry_run.stdout)
    assert payload["dry_run_plan"]["execution_status"] == "ready_for_dry_run_manifest"
    assert payload["dry_run_plan"]["execution_allowed"] is False


def test_cli_list_and_inspect_adapters():
    listed = _run_cli("list-adapters")
    inspected = _run_cli("--json", "inspect-adapter", "reliability_trust_closeout")

    assert listed.returncode == 0
    assert "reliability_trust_closeout" in listed.stdout
    assert inspected.returncode == 0
    payload = json.loads(inspected.stdout)
    assert payload["adapter_id"] == "reliability_trust_closeout"
    assert payload["execution_allowed"] is False


def test_cli_dry_run_manifest_round_trip(tmp_path):
    manifest_out = tmp_path / "manifest.json"
    result = _run_cli(
        "--json",
        "dry-run",
        "configs/examples/reliability_trust_dry_run.json",
        "--write-manifest",
        "--manifest-out",
        str(manifest_out),
    )

    assert result.returncode == 2
    assert "manifest_error" in json.loads(result.stdout)

    relative_manifest = "outputs/platform_runs/test-cli-manifest/run_manifest.json"
    result = _run_cli(
        "--json",
        "dry-run",
        "configs/examples/reliability_trust_dry_run.json",
        "--write-manifest",
        "--manifest-out",
        relative_manifest,
        "--overwrite",
    )
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["run_manifest"]["status"] == "dry_run_completed"
    validate = _run_cli("--json", "validate-manifest", relative_manifest)
    shown = _run_cli("--json", "show-manifest", relative_manifest)
    assert validate.returncode == 0
    assert json.loads(validate.stdout)["valid"] is True
    assert shown.returncode == 0
    assert json.loads(shown.stdout)["adapter_id"] == "reliability_trust_closeout"


def test_cli_dry_run_manifest_config_is_side_effect_free_without_flag(tmp_path):
    config = json.loads(Path("configs/examples/reliability_trust_manifest_dry_run.json").read_text(encoding="utf-8"))
    config["run_id"] = "test-cli-no-write"
    config["manifest_output"] = "outputs/platform_runs/test-cli-no-write/run_manifest.json"
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    manifest_path = Path(config["manifest_output"])
    if manifest_path.exists():
        manifest_path.unlink()

    result = _run_cli("--json", "dry-run", str(path))

    assert result.returncode == 0
    assert json.loads(result.stdout)["manifest_path"] == config["manifest_output"]
    assert not manifest_path.exists()


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
    assert json.loads(version.stdout)["platform_version"] == "2.0.2-dev"
