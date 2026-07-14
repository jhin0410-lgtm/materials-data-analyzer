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


def test_cli_list_case_studies_human_output_deterministic():
    result = _run_cli("list-case-studies")

    assert result.returncode == 0
    lines = result.stdout.strip().splitlines()
    assert [line.split("\t")[0] for line in lines] == [
        "battery_archive",
        "materials_project",
        "reliability",
        "smart_factory",
    ]


def test_cli_inspect_case_study_json():
    result = _run_cli("--json", "inspect-case-study", "reliability")

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["case_study_id"] == "reliability"
    assert payload["onboarding_status"] == "execution_candidate"
    assert payload["executable_stages"] == ["trust"]


def test_cli_list_case_study_stages_json():
    result = _run_cli("--json", "list-case-study-stages", "materials_project")

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    trust = next(item for item in payload if item["stage"] == "trust")
    assert trust["adapter_id"] == "materials_project_trust_closeout"
    assert trust["execution_boundary"] == "adapter_mapped_execution_disabled"


def test_cli_validate_and_plan_onboarding_json():
    config = "configs/examples/environmental_monitoring_onboarding.json"
    validate = _run_cli("--json", "validate-onboarding", config)
    plan = _run_cli("--json", "onboarding-plan", config)

    assert validate.returncode == 0
    assert json.loads(validate.stdout)["status"] == "valid_metadata_only"
    assert plan.returncode == 0
    payload = json.loads(plan.stdout)
    assert payload["plugin"] == "not_registered"
    assert payload["artifact_count"] == 3
    assert payload["stage_readiness"]["trust"]["execution_allowed"] is False


def test_cli_unknown_case_study_exits_nonzero():
    result = _run_cli("inspect-case-study", "missing")

    assert result.returncode == 3
    assert "unknown case_study_id" in result.stderr


def test_existing_reliability_execute_verify_still_passes(tmp_path):
    run_id = "test-v204-backcompat"
    output_dir = f"outputs/platform_runs/{run_id}"
    config = json.loads(Path("configs/examples/reliability_trust_verify_run.json").read_text(encoding="utf-8"))
    config["require_clean_tree"] = False
    config_path = tmp_path / "verify_config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    manifest = Path(output_dir) / "run_manifest.json"
    if manifest.exists():
        manifest.unlink()

    result = _run_cli(
        "--json",
        "execute",
        str(config_path),
        "--mode",
        "verify",
        "--run-id",
        run_id,
        "--output-dir",
        output_dir,
        "--overwrite",
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "verification_completed"
    assert payload["manifest"]["adapter_id"] == "reliability_trust_closeout"
