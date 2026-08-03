from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from test_nasa_review_disposition import _write_evidence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "run_nasa_pcoe_review_disposition.ps1"


def test_review_disposition_script_has_valid_powershell_syntax() -> None:
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


def test_review_disposition_script_initializes_existing_evidence(tmp_path: Path) -> None:
    executable = shutil.which("pwsh")
    if executable is None:
        pytest.skip("PowerShell is not installed in this environment")
    _write_evidence(tmp_path)

    completed = subprocess.run(
        [
            executable,
            "-NoProfile",
            "-NonInteractive",
            "-File",
            str(SCRIPT),
            "-Initialize",
            "-AnalysisOutput",
            str(tmp_path),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
    assert "worksheet_status: initialized" in completed.stdout
    assert "priority_battery_count: 2" in completed.stdout
    assert "automatic causal attribution" in completed.stdout
    assert (tmp_path / "tables" / "nasa_protocol_review_disposition.csv").is_file()
