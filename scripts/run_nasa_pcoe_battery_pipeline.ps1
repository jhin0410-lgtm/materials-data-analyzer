[CmdletBinding()]
param(
    [string]$PythonExecutable = "python",
    [string]$RawDirectory = "",
    [string]$ImportOutput = "",
    [string]$AnalysisOutput = "",
    [int]$NSplits = 5,
    [int]$KneeBootstrapSamples = 200,
    [switch]$SummaryOnly
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Read-RequiredJson {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Required pipeline result artifact not found: $Path"
    }
    return Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
}

function Write-ModelMetricSummary {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Triage
    )

    foreach ($model in @("persistence", "ridge")) {
        $metrics = $Triage.model_metric_summary.$model
        if ($null -ne $metrics) {
            Write-Host "$($model)_row_weighted_mae: $($metrics.row_weighted_mae)"
            Write-Host "$($model)_battery_macro_mae: $($metrics.battery_macro_mae)"
            Write-Host "$($model)_evaluated_battery_count: $($metrics.evaluated_battery_count)"
        }
    }
}

function Write-DiagnosticReasonSummary {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PriorityPath
    )

    if (-not (Test-Path -LiteralPath $PriorityPath -PathType Leaf)) {
        throw "Required battery diagnostic priority table not found: $PriorityPath"
    }

    $rows = @(Import-Csv -LiteralPath $PriorityPath)
    $counts = @{}
    foreach ($row in $rows) {
        $text = [string]$row.diagnostic_flag_reasons
        if ([string]::IsNullOrWhiteSpace($text)) {
            continue
        }
        foreach ($reason in $text.Split(";", [System.StringSplitOptions]::RemoveEmptyEntries)) {
            $normalized = $reason.Trim()
            if ([string]::IsNullOrWhiteSpace($normalized)) {
                continue
            }
            if ($counts.ContainsKey($normalized)) {
                $counts[$normalized] += 1
            }
            else {
                $counts[$normalized] = 1
            }
        }
    }

    Write-Host "diagnostic_reason_counts:"
    if ($counts.Count -eq 0) {
        Write-Host "  none: 0"
        return
    }
    foreach ($entry in ($counts.GetEnumerator() | Sort-Object Name)) {
        Write-Host "  $($entry.Name): $($entry.Value)"
    }
}

function Write-ProtocolAuditSummary {
    param(
        [Parameter(Mandatory = $true)]
        [object]$ProtocolAudit
    )

    $summary = $ProtocolAudit
    if ($null -eq $summary.protocol_audit_status) {
        throw "NASA protocol audit JSON is missing required top-level summary fields"
    }

    Write-Host "protocol_audit_available: True"
    Write-Host "protocol_audit_status: $($summary.protocol_audit_status)"
    Write-Host "predictive_evidence_level: $($summary.predictive_evidence_level)"
    Write-Host "reference_start_context_battery_count: $($summary.reference_start_context_battery_count)"
    Write-Host "reference_context_only_battery_count: $($summary.reference_context_only_battery_count)"
    Write-Host "source_quality_issue_battery_count: $($summary.source_quality_issue_battery_count)"
    Write-Host "trajectory_continuity_issue_battery_count: $($summary.trajectory_continuity_issue_battery_count)"
    Write-Host "structural_or_coverage_issue_battery_count: $($summary.structural_or_coverage_issue_battery_count)"
    Write-Host "disproportionate_error_influence_battery_count: $($summary.disproportionate_error_influence_battery_count)"
    Write-Host "ridge_improvement_vs_persistence_percent: $($summary.ridge_improvement_vs_persistence_percent)"
    Write-Host "ridge_better_than_persistence_battery_count: $($summary.ridge_better_than_persistence_battery_count)"
    Write-Host "supported_temperature_stratum_count: $($summary.supported_temperature_stratum_count)"
}

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
    if (-not $SummaryOnly) {
        foreach ($requiredPath in @($archivePath, $receiptPath)) {
            if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
                throw "Required NASA PCoE source artifact not found: $requiredPath"
            }
        }

        Write-Host "[1/3] Importing official NASA PCoE archive with rated 2 Ah target reference..."
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

        Write-Host "[2/3] Running signal-enriched battery intelligence and audits..."
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

        Write-Host "[3/3] Running protocol-aware post-hoc audit..."
        $protocolAuditArguments = @(
            "-m",
            "materials_data_analyzer.nasa_protocol_audit_cli",
            "--import-output",
            $ImportOutput,
            "--analysis-output",
            $AnalysisOutput
        )
        & $PythonExecutable @protocolAuditArguments
        if ($LASTEXITCODE -ne 0) {
            throw "NASA PCoE protocol audit failed with exit code $LASTEXITCODE"
        }
    }
    else {
        Write-Host "Summary-only mode: existing import and analysis artifacts will not be recomputed."
    }

    $importManifestPath = Join-Path $ImportOutput "nasa_pcoe_import_manifest.json"
    $targetAuditPath = Join-Path $AnalysisOutput "reports/target_comparability_audit.json"
    $triagePath = Join-Path $AnalysisOutput "reports/battery_influence_triage.json"
    $closeoutPath = Join-Path $AnalysisOutput "reports/scientific_closeout.json"
    $priorityPath = Join-Path $AnalysisOutput "tables/battery_diagnostic_priority.csv"
    $signalComparisonPath = Join-Path $AnalysisOutput "reports/signal_feature_comparison.json"
    $protocolAuditPath = Join-Path $AnalysisOutput "reports/nasa_protocol_audit.json"

    $importManifest = Read-RequiredJson -Path $importManifestPath
    $targetAudit = Read-RequiredJson -Path $targetAuditPath
    $triage = Read-RequiredJson -Path $triagePath
    $closeout = Read-RequiredJson -Path $closeoutPath

    Write-Host ""
    Write-Host "NASA PCoE pipeline summary"
    Write-Host "analysis_recomputed: $(-not $SummaryOnly)"
    Write-Host "protocol_audit_recomputed: $(-not $SummaryOnly)"
    Write-Host "target_reference_method: $($importManifest.target_reference.method)"
    Write-Host "rated_capacity_ah: $($importManifest.target_reference.rated_capacity_ah)"
    Write-Host "retrieval_receipt_verified: $($importManifest.retrieval_receipt_verified)"
    Write-Host "imported_discharge_operation_count: $($importManifest.imported_discharge_operation_count)"
    Write-Host "excluded_discharge_operation_count: $($importManifest.excluded_discharge_operation_count)"
    Write-Host "invalid_capacity_operation_count: $($importManifest.invalid_capacity_operation_count)"
    Write-Host "target_comparability_flag_battery_count: $($targetAudit.target_comparability_flag_battery_count)"
    Write-Host "reference_consistency_flag_battery_count: $($targetAudit.reference_consistency_flag_battery_count)"
    Write-Host "cycle_gap_battery_count: $($targetAudit.cycle_gap_battery_count)"
    Write-Host "large_adjacent_target_jump_battery_count: $($targetAudit.large_adjacent_target_jump_battery_count)"
    Write-Host "outside_plausibility_target_count: $($targetAudit.outside_plausibility_target_count)"
    Write-Host "pooled_error_stability_status: $($targetAudit.pooled_error_stability_status)"
    Write-Host "source_protocol_review_battery_count: $($triage.source_protocol_review_battery_count)"
    Write-Host "target_or_continuity_flag_battery_count: $($triage.target_or_continuity_flag_battery_count)"
    Write-Host "disproportionate_error_contributor_battery_count: $($triage.disproportionate_error_contributor_battery_count)"
    Write-Host "unevaluated_battery_count: $($triage.unevaluated_battery_count)"
    Write-ModelMetricSummary -Triage $triage

    if (Test-Path -LiteralPath $signalComparisonPath -PathType Leaf) {
        $signalComparison = Read-RequiredJson -Path $signalComparisonPath
        Write-Host "capacity_only_ridge_mae: $($signalComparison.capacity_only_ridge_mae)"
        Write-Host "signal_enriched_ridge_mae: $($signalComparison.signal_enriched_ridge_mae)"
        Write-Host "signal_enriched_improvement_percent: $($signalComparison.improvement_percent)"
    }

    if (Test-Path -LiteralPath $protocolAuditPath -PathType Leaf) {
        $protocolAudit = Read-RequiredJson -Path $protocolAuditPath
        Write-ProtocolAuditSummary -ProtocolAudit $protocolAudit
    }
    else {
        Write-Host "protocol_audit_available: False"
    }

    Write-DiagnosticReasonSummary -PriorityPath $priorityPath
    Write-Host "evidence_level: $($closeout.evidence_level)"
    Write-Host "import_output: $ImportOutput"
    Write-Host "analysis_output: $AnalysisOutput"
}
finally {
    Pop-Location
    $env:PYTHONPATH = $previousPythonPath
}
