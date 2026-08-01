from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "download_nasa_pcoe_battery_dataset.ps1"


def test_nasa_download_script_preserves_transport_provenance_contract() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "https://phm-datasets.s3.amazonaws.com/NASA/5.+Battery+Data+Set.zip" in text
    assert "Get-FileHash" in text
    assert "archive_sha256" in text
    assert ".partial" in text
    assert "ZipFile]::OpenRead" in text
    assert "store_credentials = $false" in text
    assert "send_credentials = $false" in text
    assert "UTF8Encoding]::new($false)" in text


def test_nasa_download_script_has_valid_powershell_syntax() -> None:
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
