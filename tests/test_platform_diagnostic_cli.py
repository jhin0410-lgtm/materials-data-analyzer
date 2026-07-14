import json
import subprocess
import sys
import uuid


def _run_cli(*args):
    return subprocess.run(
        [sys.executable, "-m", "src.cli", *args],
        check=False,
        capture_output=True,
        text=True,
    )


def test_diagnostic_cli_end_to_end_with_registered_dry_run():
    suffix = uuid.uuid4().hex
    registry_path = f"outputs/platform_registry/test_diagnostic_cli_{suffix}.sqlite3"
    manifest_path = f"outputs/platform_runs/test-diagnostic-cli-{suffix}/run_manifest.json"
    dry_run = _run_cli(
        "--json",
        "dry-run",
        "configs/examples/reliability_trust_manifest_dry_run.json",
        "--write-manifest",
        "--manifest-out",
        manifest_path,
        "--overwrite",
        "--register-run",
        "--registry-path",
        registry_path,
    )
    assert dry_run.returncode == 0, dry_run.stderr
    run_id = json.loads(dry_run.stdout)["registry_result"]["run_id"]

    diagnose = _run_cli("--json", "diagnose-run", run_id, "--registry-path", registry_path)
    assert diagnose.returncode in {0, 10, 11}, diagnose.stderr
    diagnostic_payload = json.loads(diagnose.stdout)
    assert diagnostic_payload["evaluation"]["run_id"] == run_id
    assert diagnostic_payload["findings"]

    show = _run_cli("--json", "show-diagnostics", run_id, "--registry-path", registry_path)
    assert show.returncode == 0, show.stderr
    assert json.loads(show.stdout)["evaluation"]["run_id"] == run_id

    findings = _run_cli("--json", "list-findings", "--run-id", run_id, "--registry-path", registry_path)
    assert findings.returncode == 0
    assert json.loads(findings.stdout)

    gaps = _run_cli("--json", "list-evidence-gaps", run_id, "--registry-path", registry_path)
    assert gaps.returncode == 0
    assert isinstance(json.loads(gaps.stdout), list)

    claim = _run_cli("--json", "evaluate-claim", run_id, "production_deployment", "--registry-path", registry_path)
    assert claim.returncode == 10
    assert json.loads(claim.stdout)["status"] in {"prohibited", "unsupported"}

    validate = _run_cli("--json", "diagnostics-validate", "--registry-path", registry_path)
    assert validate.returncode == 0
    assert json.loads(validate.stdout)["valid"] is True

    export = _run_cli("--json", "diagnostics-export", "--registry-path", registry_path, "--overwrite")
    assert export.returncode == 0
    assert json.loads(export.stdout)["json_path"].startswith("outputs/platform_registry/exports/diagnostics/")


def test_diagnostic_cli_unknown_run_uses_run_not_found_exit_code():
    suffix = uuid.uuid4().hex
    registry_path = f"outputs/platform_registry/test_diagnostic_missing_{suffix}.sqlite3"

    result = _run_cli("--json", "diagnose-run", "missing-run", "--registry-path", registry_path)

    assert result.returncode == 12
    assert json.loads(result.stdout)["status"] == "diagnose_run_failed"
