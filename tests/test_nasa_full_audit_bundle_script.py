from __future__ import annotations

import csv
import io
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

from test_nasa_review_disposition import _write_evidence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "package_nasa_pcoe_full_audit.ps1"


def test_full_audit_bundle_script_has_valid_powershell_syntax() -> None:
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


def test_full_audit_bundle_contains_all_analysis_output_files(tmp_path: Path) -> None:
    executable = shutil.which("pwsh")
    if executable is None:
        pytest.skip("PowerShell is not installed in this environment")
    analysis_output = tmp_path / "analysis"
    _write_evidence(analysis_output)
    extra = analysis_output / "reports" / "nested" / "diagnostic.txt"
    extra.parent.mkdir(parents=True)
    extra.write_text("diagnostic evidence\n", encoding="utf-8")
    destination = tmp_path / "nasa_full_audit.zip"

    completed = subprocess.run(
        [
            executable,
            "-NoProfile",
            "-NonInteractive",
            "-File",
            str(SCRIPT),
            "-AnalysisOutput",
            str(analysis_output),
            "-Destination",
            str(destination),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
    assert "source_file_count: 4" in completed.stdout
    assert "audit_bundle_sha256:" in completed.stdout
    assert destination.is_file()

    with zipfile.ZipFile(destination) as archive:
        names = {name.replace("\\", "/") for name in archive.namelist()}
        assert "run_manifest.json" in names
        assert "tables/nasa_protocol_review_evidence.csv" in names
        assert "reports/nasa_protocol_review_evidence.json" in names
        assert "reports/nested/diagnostic.txt" in names
        assert "_audit_bundle_inventory.csv" in names
        assert "_audit_bundle_readme.txt" in names
        inventory_text = archive.read("_audit_bundle_inventory.csv").decode("utf-8-sig")

    rows = list(csv.DictReader(io.StringIO(inventory_text)))
    assert len(rows) == 4
    assert {row["relative_path"] for row in rows} == {
        "run_manifest.json",
        "tables/nasa_protocol_review_evidence.csv",
        "reports/nasa_protocol_review_evidence.json",
        "reports/nested/diagnostic.txt",
    }
    assert all(len(row["sha256"]) == 64 for row in rows)
