from __future__ import annotations

import csv
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "close_nasa_pcoe_audit.ps1"


def _powershell() -> str:
    executable = shutil.which("pwsh")
    if executable is None:
        pytest.skip("PowerShell is not installed in this environment")
    return executable


def _write_fake_checkout(
    tmp_path: Path,
    *,
    matching_binding: bool = True,
    use_default_paths: bool = False,
) -> dict[str, Path]:
    root = tmp_path / "repo"
    scripts = root / "scripts"
    analysis_name = (
        "nasa_pcoe_signal_enriched_battery_intelligence"
        if use_default_paths
        else "analysis"
    )
    import_name = "nasa_pcoe_battery_import" if use_default_paths else "import"
    destination_name = (
        "nasa_pcoe_full_audit_bundle_post_remediation_closed.zip"
        if use_default_paths
        else "closed.zip"
    )
    analysis = root / "outputs" / analysis_name
    import_output = root / "data" / "processed" / import_name
    raw_directory = root / "data" / "raw" / "battery" / "nasa_pcoe"
    disposition = root / "completed_disposition.csv"
    destination = root / "outputs" / destination_name
    for path in (
        scripts,
        analysis / "tables",
        analysis / "reports",
        import_output,
        raw_directory,
    ):
        path.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SCRIPT, scripts / SCRIPT.name)

    evidence = analysis / "tables" / "nasa_protocol_review_evidence.csv"
    evidence.write_text("battery_id\nB0001\n", encoding="utf-8")
    evidence_hash = hashlib.sha256(evidence.read_bytes()).hexdigest()
    bound_hash = evidence_hash if matching_binding else "0" * 64
    with disposition.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["source_evidence_sha256"])
        writer.writeheader()
        writer.writerow({"source_evidence_sha256": bound_hash})

    review_script = (
        "[CmdletBinding()]\n"
        "param([string]$PythonExecutable,[string]$ImportOutput,"
        "[string]$AnalysisOutput)\n"
        "$root = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))\n"
        "Add-Content -LiteralPath (Join-Path $root 'order.log') "
        "-Value 'review'\n"
    )
    (scripts / "run_nasa_pcoe_review_workflow.ps1").write_text(
        review_script, encoding="utf-8"
    )

    package_script = (
        "[CmdletBinding()]\n"
        "param([string]$PythonExecutable,[string]$AnalysisOutput,"
        "[string]$ImportOutput,[string]$RawDirectory,"
        "[string]$DispositionInput,[string]$Destination)\n"
        "$root = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))\n"
        "Add-Content -LiteralPath (Join-Path $root 'order.log') "
        "-Value 'package'\n"
        "$parent = Split-Path -Parent $Destination\n"
        "New-Item -ItemType Directory -Force -Path $parent | Out-Null\n"
        "Set-Content -LiteralPath $Destination -Value 'closed bundle' "
        "-Encoding UTF8\n"
    )
    (scripts / "package_nasa_pcoe_full_audit.ps1").write_text(
        package_script, encoding="utf-8"
    )

    package = root / "src" / "materials_data_analyzer"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    fake_cli = (
        "from __future__ import annotations\n"
        "import argparse, json\n"
        "from pathlib import Path\n"
        "parser = argparse.ArgumentParser()\n"
        "parser.add_argument('--analysis-output', required=True)\n"
        "parser.add_argument('--finalize', action='store_true')\n"
        "parser.add_argument('--disposition-input', required=True)\n"
        "args = parser.parse_args()\n"
        "root = Path(args.analysis_output)\n"
        "(root / 'tables').mkdir(parents=True, exist_ok=True)\n"
        "(root / 'reports').mkdir(parents=True, exist_ok=True)\n"
        "(root / 'tables' / 'nasa_protocol_review_disposition_final.csv')"
        ".write_text('battery_id\\nB0001\\n', encoding='utf-8')\n"
        "summary = {'disposition_status': 'complete', "
        "'reviewed_battery_count': 34, 'pending_battery_count': 0, "
        "'predictive_evidence_level': 'Unsupported'}\n"
        "(root / 'reports' / 'nasa_protocol_review_disposition.json')"
        ".write_text(json.dumps({'summary': summary}), encoding='utf-8')\n"
        "order = Path(__file__).resolve().parents[2] / 'order.log'\n"
        "with order.open('a', encoding='utf-8') as handle:\n"
        "    handle.write('finalize\\n')\n"
    )
    (package / "nasa_review_disposition_cli.py").write_text(
        fake_cli, encoding="utf-8"
    )
    return {
        "root": root,
        "script": scripts / SCRIPT.name,
        "analysis": analysis,
        "import": import_output,
        "raw": raw_directory,
        "disposition": disposition,
        "destination": destination,
    }


def _run_closeout(
    paths: dict[str, Path], *, use_default_paths: bool = False
) -> subprocess.CompletedProcess[str]:
    command = [
        _powershell(),
        "-NoProfile",
        "-NonInteractive",
        "-File",
        str(paths["script"]),
        "-PythonExecutable",
        sys.executable,
        "-DispositionInput",
        str(paths["disposition"]),
    ]
    if not use_default_paths:
        command.extend(
            [
                "-ImportOutput",
                str(paths["import"]),
                "-AnalysisOutput",
                str(paths["analysis"]),
                "-RawDirectory",
                str(paths["raw"]),
                "-Destination",
                str(paths["destination"]),
            ]
        )
    return subprocess.run(
        command,
        cwd=paths["root"],
        capture_output=True,
        text=True,
        check=False,
    )


def test_closeout_script_has_valid_powershell_syntax() -> None:
    executable = _powershell()
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


def test_closeout_orders_review_finalize_and_package(tmp_path: Path) -> None:
    paths = _write_fake_checkout(tmp_path)

    completed = _run_closeout(paths)

    assert completed.returncode == 0, completed.stderr or completed.stdout
    assert paths["destination"].is_file()
    order = (paths["root"] / "order.log").read_text(encoding="utf-8").splitlines()
    assert order == ["review", "finalize", "package"]
    assert "reviewed_battery_count: 34" in completed.stdout
    assert "pending_battery_count: 0" in completed.stdout
    assert "predictive_evidence_level: Unsupported" in completed.stdout
    assert "closed_audit_bundle_sha256:" in completed.stdout


def test_closeout_uses_repository_defaults_when_optional_paths_are_omitted(
    tmp_path: Path,
) -> None:
    paths = _write_fake_checkout(tmp_path, use_default_paths=True)

    completed = _run_closeout(paths, use_default_paths=True)

    assert completed.returncode == 0, completed.stderr or completed.stdout
    assert paths["destination"].is_file()
    order = (paths["root"] / "order.log").read_text(encoding="utf-8").splitlines()
    assert order == ["review", "finalize", "package"]
    assert str(paths["analysis"]) in completed.stdout
    assert str(paths["destination"]) in completed.stdout


def test_closeout_rejects_stale_disposition_binding(tmp_path: Path) -> None:
    paths = _write_fake_checkout(tmp_path, matching_binding=False)

    completed = _run_closeout(paths)

    assert completed.returncode != 0
    assert "Disposition evidence binding does not match" in (
        completed.stderr + completed.stdout
    )
    order = (paths["root"] / "order.log").read_text(encoding="utf-8").splitlines()
    assert order == ["review"]
    assert not paths["destination"].exists()
