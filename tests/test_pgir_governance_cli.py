import json
import shutil
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


def test_pgir_cli_commands_emit_json_without_side_effects():
    output_dir = Path("outputs/platform_pgir/cli_no_write_check")
    if output_dir.exists():
        shutil.rmtree(output_dir)

    commands = [
        ("list-pgir-concepts",),
        ("inspect-pgir-concept", "observation"),
        ("show-pgir-mapping",),
        ("validate-pgir-mapping",),
        ("show-pgir-representation-levels",),
        ("show-pgir-schema-ownership",),
        ("validate-pgir-schema-governance",),
        ("show-pgir-capability-stages",),
        ("evaluate-pgir-readiness",),
    ]
    for command in commands:
        result = _run_cli("--json", *command)
        assert result.returncode == 0, result.stderr
        json.loads(result.stdout)

    assert not output_dir.exists()


def test_pgir_cli_export_writes_only_local_summary_and_rejects_bad_paths():
    output = Path("outputs/platform_pgir/test_pgir_governance_summary.json")
    if output.exists():
        output.unlink()

    exported = _run_cli("--json", "export-pgir-governance-summary", "--output", output.as_posix())
    assert exported.returncode == 0, exported.stderr
    payload = json.loads(exported.stdout)
    assert payload["status"] == "exported"
    written = json.loads(output.read_text(encoding="utf-8"))
    assert written["status"] == "pgir_governance_ready"
    assert written["execution_boundary"]["model_training_performed"] is False
    output.unlink()

    rejected = _run_cli("--json", "export-pgir-governance-summary", "--output", "../bad.json")
    assert rejected.returncode != 0
    assert json.loads(rejected.stdout)["status"] == "pgir_export_failed"


def test_pgir_cli_unknown_concept_is_rejected():
    result = _run_cli("--json", "inspect-pgir-concept", "missing_concept")

    assert result.returncode != 0
    assert json.loads(result.stdout)["status"] == "unknown_pgir_concept"
