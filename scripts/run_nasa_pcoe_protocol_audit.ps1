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
    Write-Host "Running NASA PCoE protocol-aware post-hoc audit..."
    Write-Host "No import or model fitting will be performed."
    $arguments = @(
        "-m",
        "materials_data_analyzer.nasa_protocol_audit_cli",
        "--import-output",
        $ImportOutput,
        "--analysis-output",
        $AnalysisOutput
    )
    & $PythonExecutable @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "NASA PCoE protocol audit failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
    $env:PYTHONPATH = $previousPythonPath
}
