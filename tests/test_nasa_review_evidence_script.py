from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from nasa_review_evidence_queue_fixture import PROJECT_ROOT, SCRIPT
from nasa_review_evidence_run_fixture import _write_run


def test_review_evidence_script_has_valid_powershell_syntax() -> None:
    executable = shutil.which("pwsh")
    if executable is None:
        pytest.skip("PowerShell is not installed in this environment")
    command = (
        "$tokens = $null; $errors = $null; "
        f"[System.Management.Automation.Language.Parser]::ParseFile('{SCRIPT.as_posix()}', "
        "[ref]$tokens, [ref]$errors) | Out-Null; "
        "if ($errors.Count -gt 0) { $errors | ForEach-Object { Write-Error $_ }; exit 1 }"
    )
    completed = subprocess.run(
        [executable, "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_review_evidence_script_executes_existing_artifacts(tmp_path: Path) -> None:
    executable = shutil.which("pwsh")
    if executable is None:
        pytest.skip("PowerShell is not installed in this environment")
    import_output = tmp_path / "import"
    analysis_output = tmp_path / "analysis"
    _write_run(import_output, analysis_output)

    completed = subprocess.run(
        [
            executable,
            "-NoProfile",
            "-NonInteractive",
            "-File",
            str(SCRIPT),
            "-ImportOutput",
            str(import_output),
            "-AnalysisOutput",
            str(analysis_output),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    assert "without model fitting or data repair" in completed.stdout
    assert "review_evidence_status: Diagnostic" in completed.stdout
    assert "priority_battery_ids: A,B" in completed.stdout
    assert (
        analysis_output / "reports" / "nasa_protocol_review_evidence.json"
    ).is_file()
