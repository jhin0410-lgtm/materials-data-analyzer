[CmdletBinding()]
param(
    [string]$PythonExecutable = "python",
    [string]$ImportOutput = "",
    [string]$AnalysisOutput = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$protocolAuditScript = Join-Path $PSScriptRoot "run_nasa_pcoe_protocol_audit.ps1"
$reviewEvidenceScript = Join-Path $PSScriptRoot "run_nasa_pcoe_review_evidence.ps1"

foreach ($requiredScript in @($protocolAuditScript, $reviewEvidenceScript)) {
    if (-not (Test-Path -LiteralPath $requiredScript -PathType Leaf)) {
        throw "Required NASA review workflow script not found: $requiredScript"
    }
}

Write-Host "Refreshing NASA PCoE protocol audit, import binding, review queue, and evidence packets..."
Write-Host "Existing artifacts only: no NASA archive import, feature extraction, model fitting, target repair, or battery filtering will be performed."

& $protocolAuditScript `
    -PythonExecutable $PythonExecutable `
    -ImportOutput $ImportOutput `
    -AnalysisOutput $AnalysisOutput

& $reviewEvidenceScript `
    -PythonExecutable $PythonExecutable `
    -ImportOutput $ImportOutput `
    -AnalysisOutput $AnalysisOutput

Write-Host "NASA PCoE review workflow completed."
