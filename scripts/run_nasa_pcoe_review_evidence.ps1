[CmdletBinding()]
param(
    [string]$PythonExecutable = "python",
    [string]$ImportOutput = "",
    [string]$AnalysisOutput = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repositoryRoot = [System.IO.Path]::GetFullPath(
    (Join-Path $PSScriptRoot "..")
)

if ([string]::IsNullOrWhiteSpace($ImportOutput)) {
    $ImportOutput = Join-Path $repositoryRoot "data/processed/nasa_pcoe_battery_import"
}
elseif (-not [System.IO.Path]::IsPathRooted($ImportOutput)) {
    $ImportOutput = [System.IO.Path]::GetFullPath(
        (Join-Path (Get-Location).Path $ImportOutput)
    )
}

if ([string]::IsNullOrWhiteSpace($AnalysisOutput)) {
    $AnalysisOutput = Join-Path $repositoryRoot "outputs/nasa_pcoe_signal_enriched_battery_intelligence"
}
elseif (-not [System.IO.Path]::IsPathRooted($AnalysisOutput)) {
    $AnalysisOutput = [System.IO.Path]::GetFullPath(
        (Join-Path (Get-Location).Path $AnalysisOutput)
    )
}

$previousPythonPath = $env:PYTHONPATH
$sourcePath = Join-Path $repositoryRoot "src"
if ([string]::IsNullOrWhiteSpace($previousPythonPath)) {
    $env:PYTHONPATH = $sourcePath
}
else {
    $env:PYTHONPATH = "$sourcePath$([System.IO.Path]::PathSeparator)$previousPythonPath"
}

Push-Location $repositoryRoot
try {
    Write-Host "Building NASA PCoE battery review evidence..."
    Write-Host "Existing import, protocol-audit, review-queue, and validation artifacts will be read without model fitting or data repair."
    $arguments = @(
        "-m",
        "materials_data_analyzer.nasa_review_evidence_cli",
        "--import-output",
        $ImportOutput,
        "--analysis-output",
        $AnalysisOutput
    )
    & $PythonExecutable @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "NASA PCoE battery review evidence failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
    $env:PYTHONPATH = $previousPythonPath
}
