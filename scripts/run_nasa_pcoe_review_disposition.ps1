[CmdletBinding()]
param(
    [string]$PythonExecutable = "python",
    [string]$AnalysisOutput = "",
    [switch]$Initialize,
    [switch]$Finalize,
    [switch]$Overwrite,
    [string]$DispositionInput = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if ($Initialize -eq $Finalize) {
    throw "Specify exactly one of -Initialize or -Finalize."
}
if ($Overwrite -and -not $Initialize) {
    throw "-Overwrite is valid only with -Initialize."
}
if (-not [string]::IsNullOrWhiteSpace($DispositionInput) -and -not $Finalize) {
    throw "-DispositionInput is valid only with -Finalize."
}

$repositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
if ([string]::IsNullOrWhiteSpace($AnalysisOutput)) {
    $AnalysisOutput = Join-Path $repositoryRoot "outputs/nasa_pcoe_signal_enriched_battery_intelligence"
}
elseif (-not [System.IO.Path]::IsPathRooted($AnalysisOutput)) {
    $AnalysisOutput = [System.IO.Path]::GetFullPath(
        (Join-Path (Get-Location).Path $AnalysisOutput)
    )
}
if (-not [string]::IsNullOrWhiteSpace($DispositionInput) -and
    -not [System.IO.Path]::IsPathRooted($DispositionInput)) {
    $DispositionInput = [System.IO.Path]::GetFullPath(
        (Join-Path (Get-Location).Path $DispositionInput)
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
    $arguments = @(
        "-m",
        "materials_data_analyzer.nasa_review_disposition_cli",
        "--analysis-output",
        $AnalysisOutput
    )
    if ($Initialize) {
        Write-Host "Initializing reviewer-controlled NASA PCoE disposition worksheet..."
        $arguments += "--initialize"
        if ($Overwrite) {
            $arguments += "--overwrite"
        }
    }
    else {
        Write-Host "Validating and snapshotting NASA PCoE reviewer dispositions..."
        $arguments += "--finalize"
        if (-not [string]::IsNullOrWhiteSpace($DispositionInput)) {
            $arguments += @("--disposition-input", $DispositionInput)
        }
    }
    Write-Host "No model fitting, data repair, battery filtering, or automatic causal attribution will be performed."
    & $PythonExecutable @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "NASA PCoE review disposition failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
    $env:PYTHONPATH = $previousPythonPath
}
