import json
import subprocess
import sys
from pathlib import Path


def _run_cli(*args):
    return subprocess.run([sys.executable, "-m", "src.cli", *args], check=False, capture_output=True, text=True)


def test_scientific_execution_cli_preview_execute_persist_and_output():
    registry_path = "outputs/platform_registry/test_science_cli.sqlite3"
    registry_file = Path(registry_path)
    if registry_file.exists():
        registry_file.unlink()
    execution = _run_cli(
        "--json",
        "execute-scientific-check",
        "configs/examples/xrd_bragg_consistent_check.json",
        "--registry-path",
        registry_path,
        "--persist",
        "--output-dir",
        "outputs/platform_science/test_cli_bragg",
        "--overwrite",
    )
    assert execution.returncode == 0, execution.stderr
    payload = json.loads(execution.stdout)
    assert payload["scientific_recomputation_performed"] is True
    result_path = Path("outputs/platform_science/test_cli_bragg/scientific_result.json")
    assert result_path.exists()

    shown = _run_cli("--json", "show-scientific-execution", "xrd_bragg_consistent_check", "--registry-path", registry_path)
    findings = _run_cli("--json", "list-scientific-findings", "--execution-id", "xrd_bragg_consistent_check", "--registry-path", registry_path)
    claim = _run_cli("--json", "evaluate-scientific-claim", "xrd_bragg_consistent_check", "phase_identification_supported", "--registry-path", registry_path)
    validation = _run_cli("--json", "validate-scientific-result", str(result_path))

    assert shown.returncode == 0
    assert json.loads(shown.stdout)["execution"]["status"] == "conditionally_consistent"
    assert findings.returncode == 0 and json.loads(findings.stdout)
    assert json.loads(claim.stdout)["status"] == "prohibited"
    assert validation.returncode == 0


def test_scientific_execution_cli_preview_has_no_output_side_effect(tmp_path):
    before = set(Path("outputs/platform_science").glob("preview_no_write*")) if Path("outputs/platform_science").exists() else set()
    preview = _run_cli("--json", "preview-scientific-check", "configs/examples/xrd_bragg_consistent_check.json")
    after = set(Path("outputs/platform_science").glob("preview_no_write*")) if Path("outputs/platform_science").exists() else set()

    assert preview.returncode == 0
    assert before == after
    assert json.loads(preview.stdout)["raw_data_read"] is False
    del tmp_path
