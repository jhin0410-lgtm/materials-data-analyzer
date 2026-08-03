from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "run_nasa_pcoe_review_workflow.ps1"


def test_review_workflow_script_has_valid_powershell_syntax() -> None:
    executable = shutil.which("pwsh")
    if executable is None:
        pytest.skip("PowerShell is not installed in this environment")
    command = (
        "$tokens = $null; $errors = $null; "
        f"[System.Management.Automation.Language.Parser]::ParseFile('{SCRIPT.as_posix()}', "
        "[ref]$tokens, [ref]$errors) | Out-Null; "
        "if ($errors.Count -gt 0) { "
        "$errors | ForEach-Object { Write-Error $_ }; exit 1 }"
    )
    completed = subprocess.run(
        [executable, "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_review_workflow_runs_audit_before_evidence_and_forwards_paths(
    tmp_path: Path,
) -> None:
    executable = shutil.which("pwsh")
    if executable is None:
        pytest.skip("PowerShell is not installed in this environment")

    workflow = tmp_path / SCRIPT.name
    shutil.copyfile(SCRIPT, workflow)
    log_path = tmp_path / "workflow.log"
    import_output = tmp_path / "import output"
    analysis_output = tmp_path / "analysis output"

    fake_script = """[CmdletBinding()]
param(
    [string]$PythonExecutable = "python",
    [string]$ImportOutput = "",
    [string]$AnalysisOutput = ""
)
Add-Content -LiteralPath $env:MDA_REVIEW_WORKFLOW_TEST_LOG -Value (
    "{stage}|$PythonExecutable|$ImportOutput|$AnalysisOutput"
)
"""
    (tmp_path / "run_nasa_pcoe_protocol_audit.ps1").write_text(
        fake_script.format(stage="audit"), encoding="utf-8"
    )
    (tmp_path / "run_nasa_pcoe_review_evidence.ps1").write_text(
        fake_script.format(stage="evidence"), encoding="utf-8"
    )

    environment = os.environ.copy()
    environment["MDA_REVIEW_WORKFLOW_TEST_LOG"] = str(log_path)
    completed = subprocess.run(
        [
            executable,
            "-NoProfile",
            "-NonInteractive",
            "-File",
            str(workflow),
            "-PythonExecutable",
            "test-python",
            "-ImportOutput",
            str(import_output),
            "-AnalysisOutput",
            str(analysis_output),
        ],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
    assert log_path.read_text(encoding="utf-8").splitlines() == [
        f"audit|test-python|{import_output}|{analysis_output}",
        f"evidence|test-python|{import_output}|{analysis_output}",
    ]
    assert "Existing artifacts only" in completed.stdout
    assert "NASA PCoE review workflow completed." in completed.stdout
