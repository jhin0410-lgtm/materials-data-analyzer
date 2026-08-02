[CmdletBinding()]
param(
    [string]$PythonExecutable = "python",
    [string]$AnalysisOutput = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repositoryRoot = [System.IO.Path]::GetFullPath(
    (Join-Path $PSScriptRoot "..")
)

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
    Write-Host "Building NASA PCoE focused review queue..."
    Write-Host "Existing protocol-audit artifacts will be read without import or model fitting."
    $arguments = @(
        "-m",
        "materials_data_analyzer.nasa_review_queue_cli",
        "--analysis-output",
        $AnalysisOutput
    )
    & $PythonExecutable @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "NASA PCoE focused review queue failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
    $env:PYTHONPATH = $previousPythonPath
}
