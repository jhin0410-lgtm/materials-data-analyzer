[CmdletBinding()]
param(
    [string]$PythonExecutable = "python",
    [string]$RawDirectory = "",
    [string]$ImportOutput = "",
    [string]$AnalysisOutput = "",
    [int]$NSplits = 5,
    [int]$KneeBootstrapSamples = 200
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repositoryRoot = [System.IO.Path]::GetFullPath(
    (Join-Path $PSScriptRoot "..")
)

if ([string]::IsNullOrWhiteSpace($RawDirectory)) {
    $RawDirectory = Join-Path $repositoryRoot "data/raw/battery/nasa_pcoe"
}
elseif (-not [System.IO.Path]::IsPathRooted($RawDirectory)) {
    $RawDirectory = [System.IO.Path]::GetFullPath(
        (Join-Path (Get-Location).Path $RawDirectory)
    )
}

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

$archivePath = Join-Path $RawDirectory "5_Battery_Data_Set.zip"
$receiptPath = Join-Path $RawDirectory "retrieval_receipt.json"

foreach ($requiredPath in @($archivePath, $receiptPath)) {
    if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
        throw "Required NASA PCoE source artifact not found: $requiredPath"
    }
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
    Write-Host "[1/2] Importing official NASA PCoE archive with rated 2 Ah target reference..."
    $importArguments = @(
        "-m",
        "materials_data_analyzer.nasa_battery_cli",
        "--input",
        $archivePath,
        "--retrieval-receipt",
        $receiptPath,
        "--output",
        $ImportOutput,
        "--overwrite"
    )
    & $PythonExecutable @importArguments
    if ($LASTEXITCODE -ne 0) {
        throw "NASA PCoE import failed with exit code $LASTEXITCODE"
    }

    $cycleSummaryPath = Join-Path $ImportOutput "nasa_pcoe_cycle_summary.csv"
    $rawSignalPath = Join-Path $ImportOutput "nasa_pcoe_raw_signal.csv"
    $provenancePath = Join-Path $ImportOutput "nasa_pcoe_raw_signal_provenance.json"

    Write-Host "[2/2] Running signal-enriched battery intelligence and audits..."
    $analysisArguments = @(
        "-m",
        "materials_data_analyzer.battery_cli",
        "--cycle-summary",
        $cycleSummaryPath,
        "--raw-signal",
        $rawSignalPath,
        "--raw-signal-provenance",
        $provenancePath,
        "--output",
        $AnalysisOutput,
        "--n-splits",
        [string]$NSplits,
        "--knee-bootstrap-samples",
        [string]$KneeBootstrapSamples,
        "--overwrite"
    )
    & $PythonExecutable @analysisArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Battery Intelligence analysis failed with exit code $LASTEXITCODE"
    }

    $importManifestPath = Join-Path $ImportOutput "nasa_pcoe_import_manifest.json"
    $targetAuditPath = Join-Path $AnalysisOutput "reports/target_comparability_audit.json"
    $triagePath = Join-Path $AnalysisOutput "reports/battery_influence_triage.json"
    $closeoutPath = Join-Path $AnalysisOutput "reports/scientific_closeout.json"

    $importManifest = Get-Content -LiteralPath $importManifestPath -Raw -Encoding UTF8 |
        ConvertFrom-Json
    $targetAudit = Get-Content -LiteralPath $targetAuditPath -Raw -Encoding UTF8 |
        ConvertFrom-Json
    $triage = Get-Content -LiteralPath $triagePath -Raw -Encoding UTF8 |
        ConvertFrom-Json
    $closeout = Get-Content -LiteralPath $closeoutPath -Raw -Encoding UTF8 |
        ConvertFrom-Json

    Write-Host ""
    Write-Host "NASA PCoE pipeline complete"
    Write-Host "target_reference_method: $($importManifest.target_reference.method)"
    Write-Host "rated_capacity_ah: $($importManifest.target_reference.rated_capacity_ah)"
    Write-Host "target_comparability_flag_battery_count: $($targetAudit.target_comparability_flag_battery_count)"
    Write-Host "source_protocol_review_battery_count: $($triage.source_protocol_review_battery_count)"
    Write-Host "evidence_level: $($closeout.evidence_level)"
    Write-Host "import_output: $ImportOutput"
    Write-Host "analysis_output: $AnalysisOutput"
}
finally {
    Pop-Location
    $env:PYTHONPATH = $previousPythonPath
}
