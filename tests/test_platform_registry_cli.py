import json
import subprocess
import sys
import uuid
from pathlib import Path

import pytest


def _run_cli(*args):
    return subprocess.run(
        [sys.executable, "-m", "src.cli", *args],
        check=False,
        capture_output=True,
        text=True,
    )


def test_registry_cli_smoke_with_dry_run_registration():
    suffix = uuid.uuid4().hex
    registry_path = f"outputs/platform_registry/test_cli_registry_{suffix}.sqlite3"
    manifest_path = f"outputs/platform_runs/test-cli-registry-{suffix}/run_manifest.json"
    init = _run_cli("--json", "registry-init", "--registry-path", registry_path)
    assert init.returncode == 0
    assert json.loads(init.stdout)["schema_version"] == 3

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
    payload = json.loads(dry_run.stdout)
    assert payload["registry_result"]["status"] in {"ingested", "idempotent"}
    run_id = payload["registry_result"]["run_id"]

    list_runs = _run_cli("--json", "registry-list-runs", "--registry-path", registry_path)
    assert list_runs.returncode == 0
    assert any(run["run_id"] == run_id for run in json.loads(list_runs.stdout))

    show = _run_cli("--json", "registry-show-run", run_id, "--registry-path", registry_path)
    assert show.returncode == 0
    assert json.loads(show.stdout)["run"]["run_id"] == run_id

    artifacts = _run_cli("--json", "registry-list-artifacts", "--run-id", run_id, "--registry-path", registry_path)
    assert artifacts.returncode == 0
    artifact_payload = json.loads(artifacts.stdout)
    assert artifact_payload

    lineage = _run_cli("--json", "registry-lineage", artifact_payload[-1]["artifact_record_id"], "--registry-path", registry_path)
    assert lineage.returncode == 0
    assert "artifact" in json.loads(lineage.stdout)

    repro = _run_cli("--json", "registry-reproducibility", run_id, "--registry-path", registry_path)
    assert repro.returncode == 0
    assert json.loads(repro.stdout)["status"] in {
        "reproducible_verified",
        "reproducible_partial",
        "unverifiable_missing_input",
        "unverifiable_code_commit",
    }

    validate = _run_cli("--json", "registry-validate", "--registry-path", registry_path)
    assert validate.returncode == 0
    assert json.loads(validate.stdout)["valid"] is True

    export = _run_cli("--json", "registry-export", "--registry-path", registry_path, "--overwrite")
    assert export.returncode == 0
    export_payload = json.loads(export.stdout)
    assert export_payload["json_path"].startswith("outputs/platform_registry/exports/")
    assert Path(export_payload["json_path"]).exists()


def test_registry_cli_rejects_absolute_registry_path():
    result = _run_cli(
        "--json",
        "registry-init",
        "--registry-path",
        "C:/tmp/platform_registry.sqlite3",
    )

    assert result.returncode == 9
    assert json.loads(result.stdout)["status"] == "registry_init_failed"


def test_execute_register_run_keeps_existing_behavior_available():
    status = subprocess.run(["git", "status", "--porcelain"], check=False, capture_output=True, text=True)
    if status.stdout.strip():
        pytest.skip("controlled execute requires a clean tracked working tree")
    registry_path = f"outputs/platform_registry/test_execute_registry_{uuid.uuid4().hex}.sqlite3"
    result = _run_cli(
        "--json",
        "execute",
        "configs/examples/reliability_trust_verify_run.json",
        "--mode",
        "verify",
        "--overwrite",
        "--register-run",
        "--registry-path",
        registry_path,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "verification_completed"
    assert payload["registry_result"]["status"] in {"ingested", "idempotent"}
