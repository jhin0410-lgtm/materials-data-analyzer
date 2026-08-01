from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "run_nasa_pcoe_battery_pipeline.ps1"


def test_nasa_pipeline_script_runs_import_analysis_and_audits() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'Join-Path $PSScriptRoot ".."' in text
    assert "5_Battery_Data_Set.zip" in text
    assert "retrieval_receipt.json" in text
    assert "materials_data_analyzer.nasa_battery_cli" in text
    assert "materials_data_analyzer.battery_cli" in text
    assert "--raw-signal-provenance" in text
    assert "--overwrite" in text
    assert "target_reference_method" in text
    assert "target_comparability_flag_battery_count" in text
    assert "source_protocol_review_battery_count" in text
    assert "PYTHONPATH" in text


def test_nasa_pipeline_script_has_valid_powershell_syntax() -> None:
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
