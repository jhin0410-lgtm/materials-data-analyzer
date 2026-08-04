[CmdletBinding()]
param(
    [string]$PythonExecutable = "python",
    [string]$ImportOutput = "",
    [string]$AnalysisOutput = "",
    [Parameter(Mandatory = $true)]
    [string]$DispositionInput,
    [string]$RawDirectory = "",
    [string]$Destination = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Resolve-RepositoryPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Value,
        [Parameter(Mandatory = $true)]
        [string]$DefaultRelativePath
    )

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return [System.IO.Path]::GetFullPath(
            (Join-Path $repositoryRoot $DefaultRelativePath)
        )
    }
    if ([System.IO.Path]::IsPathRooted($Value)) {
        return [System.IO.Path]::GetFullPath($Value)
    }
    return [System.IO.Path]::GetFullPath(
        (Join-Path (Get-Location).Path $Value)
    )
}

$repositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$reviewWorkflowScript = Join-Path $PSScriptRoot "run_nasa_pcoe_review_workflow.ps1"
$packageScript = Join-Path $PSScriptRoot "package_nasa_pcoe_full_audit.ps1"

foreach ($requiredScript in @($reviewWorkflowScript, $packageScript)) {
    if (-not (Test-Path -LiteralPath $requiredScript -PathType Leaf)) {
        throw "Required NASA closeout script not found: $requiredScript"
    }
}
if ([string]::IsNullOrWhiteSpace($DispositionInput)) {
    throw "Completed NASA disposition input must not be blank"
}

$ImportOutput = Resolve-RepositoryPath `
    -Value $ImportOutput `
    -DefaultRelativePath "data/processed/nasa_pcoe_battery_import"
$AnalysisOutput = Resolve-RepositoryPath `
    -Value $AnalysisOutput `
    -DefaultRelativePath "outputs/nasa_pcoe_signal_enriched_battery_intelligence"
$RawDirectory = Resolve-RepositoryPath `
    -Value $RawDirectory `
    -DefaultRelativePath "data/raw/battery/nasa_pcoe"
if ([System.IO.Path]::IsPathRooted($DispositionInput)) {
    $DispositionInput = [System.IO.Path]::GetFullPath($DispositionInput)
}
else {
    $DispositionInput = [System.IO.Path]::GetFullPath(
        (Join-Path (Get-Location).Path $DispositionInput)
    )
}
$Destination = Resolve-RepositoryPath `
    -Value $Destination `
    -DefaultRelativePath "outputs/nasa_pcoe_full_audit_bundle_post_remediation_closed.zip"

if (-not (Test-Path -LiteralPath $ImportOutput -PathType Container)) {
    throw "NASA PCoE import output directory not found: $ImportOutput"
}
if (-not (Test-Path -LiteralPath $AnalysisOutput -PathType Container)) {
    throw "NASA PCoE analysis output directory not found: $AnalysisOutput"
}
if (-not (Test-Path -LiteralPath $DispositionInput -PathType Leaf)) {
    throw "Completed NASA disposition input not found: $DispositionInput"
}
if (-not (Test-Path -LiteralPath $RawDirectory -PathType Container)) {
    throw "NASA PCoE raw source directory not found: $RawDirectory"
}

Write-Host "Refreshing protocol audit, import binding, review queue, and evidence..."
& $reviewWorkflowScript `
    -PythonExecutable $PythonExecutable `
    -ImportOutput $ImportOutput `
    -AnalysisOutput $AnalysisOutput

$evidencePath = Join-Path $AnalysisOutput "tables/nasa_protocol_review_evidence.csv"
if (-not (Test-Path -LiteralPath $evidencePath -PathType Leaf)) {
    throw "NASA review evidence was not generated: $evidencePath"
}
$evidenceHash = (
    Get-FileHash -LiteralPath $evidencePath -Algorithm SHA256
).Hash.ToLowerInvariant()

$dispositionRows = @(Import-Csv -LiteralPath $DispositionInput)
if ($dispositionRows.Count -eq 0) {
    throw "Completed NASA disposition contains no rows: $DispositionInput"
}
$boundHashes = @(
    $dispositionRows |
        ForEach-Object { [string]$_.source_evidence_sha256 } |
        Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
        ForEach-Object { $_.Trim().ToLowerInvariant() } |
        Sort-Object -Unique
)
if ($boundHashes.Count -ne 1 -or $boundHashes[0] -ne $evidenceHash) {
    throw (
        "Disposition evidence binding does not match the refreshed evidence. " +
        "expected=$evidenceHash observed=$($boundHashes -join ',')"
    )
}
$dispositionHash = (
    Get-FileHash -LiteralPath $DispositionInput -Algorithm SHA256
).Hash.ToLowerInvariant()

Write-Host "Finalizing the evidence-bound 34-battery disposition..."
$previousPythonPath = $env:PYTHONPATH
$sourcePath = Join-Path $repositoryRoot "src"
if ([string]::IsNullOrWhiteSpace($previousPythonPath)) {
    $env:PYTHONPATH = $sourcePath
}
else {
    $env:PYTHONPATH = "$sourcePath$([System.IO.Path]::PathSeparator)$previousPythonPath"
}
try {
    & $PythonExecutable `
        -m materials_data_analyzer.nasa_review_disposition_cli `
        --analysis-output $AnalysisOutput `
        --finalize `
        --disposition-input $DispositionInput
    if ($LASTEXITCODE -ne 0) {
        throw "NASA disposition finalization failed with exit code $LASTEXITCODE"
    }
}
finally {
    $env:PYTHONPATH = $previousPythonPath
}

$finalDisposition = Join-Path $AnalysisOutput "tables/nasa_protocol_review_disposition_final.csv"
$finalReport = Join-Path $AnalysisOutput "reports/nasa_protocol_review_disposition.json"
foreach ($requiredOutput in @($finalDisposition, $finalReport)) {
    if (-not (Test-Path -LiteralPath $requiredOutput -PathType Leaf)) {
        throw "NASA disposition finalization output not found: $requiredOutput"
    }
}
$report = Get-Content -LiteralPath $finalReport -Raw -Encoding UTF8 | ConvertFrom-Json
$summary = if ($null -ne $report.summary) { $report.summary } else { $report }
if ([string]$summary.disposition_status -ne "complete") {
    throw "NASA disposition is not complete after finalization"
}
if ([int]$summary.pending_battery_count -ne 0) {
    throw "NASA disposition still contains pending batteries"
}
if ([int]$summary.reviewed_battery_count -ne 34) {
    throw "NASA disposition must contain exactly 34 reviewed batteries"
}

Write-Host "Packaging the final self-contained closed audit bundle..."
& $packageScript `
    -PythonExecutable $PythonExecutable `
    -AnalysisOutput $AnalysisOutput `
    -ImportOutput $ImportOutput `
    -RawDirectory $RawDirectory `
    -DispositionInput $DispositionInput `
    -Destination $Destination

if (-not (Test-Path -LiteralPath $Destination -PathType Leaf)) {
    throw "Final NASA closed audit bundle was not created: $Destination"
}
$bundleHash = (
    Get-FileHash -LiteralPath $Destination -Algorithm SHA256
).Hash.ToLowerInvariant()

Write-Host "NASA PCoE audit closeout completed."
Write-Host "review_evidence: $evidencePath"
Write-Host "review_evidence_sha256: $evidenceHash"
Write-Host "disposition_input: $DispositionInput"
Write-Host "disposition_input_sha256: $dispositionHash"
Write-Host "reviewed_battery_count: 34"
Write-Host "pending_battery_count: 0"
Write-Host "predictive_evidence_level: $([string]$summary.predictive_evidence_level)"
Write-Host "closed_audit_bundle: $Destination"
Write-Host "closed_audit_bundle_sha256: $bundleHash"
Write-Host "scientific_boundary: closeout and packaging do not establish external validation, causality, or engineering readiness"
