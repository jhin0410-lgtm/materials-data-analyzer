[CmdletBinding()]
param(
    [string]$AnalysisOutput = "",
    [string]$Destination = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
if ([string]::IsNullOrWhiteSpace($AnalysisOutput)) {
    $AnalysisOutput = Join-Path $repositoryRoot "outputs/nasa_pcoe_signal_enriched_battery_intelligence"
}
elseif (-not [System.IO.Path]::IsPathRooted($AnalysisOutput)) {
    $AnalysisOutput = [System.IO.Path]::GetFullPath(
        (Join-Path (Get-Location).Path $AnalysisOutput)
    )
}
else {
    $AnalysisOutput = [System.IO.Path]::GetFullPath($AnalysisOutput)
}

if (-not (Test-Path -LiteralPath $AnalysisOutput -PathType Container)) {
    throw "NASA PCoE analysis output directory not found: $AnalysisOutput"
}

$manifestPath = Join-Path $AnalysisOutput "run_manifest.json"
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
    throw "NASA PCoE run manifest not found: $manifestPath"
}

if ([string]::IsNullOrWhiteSpace($Destination)) {
    $Destination = Join-Path $repositoryRoot "outputs/nasa_pcoe_full_audit_bundle.zip"
}
elseif (-not [System.IO.Path]::IsPathRooted($Destination)) {
    $Destination = [System.IO.Path]::GetFullPath(
        (Join-Path (Get-Location).Path $Destination)
    )
}
else {
    $Destination = [System.IO.Path]::GetFullPath($Destination)
}

$destinationParent = Split-Path -Parent $Destination
if (-not [string]::IsNullOrWhiteSpace($destinationParent)) {
    New-Item -ItemType Directory -Force -Path $destinationParent | Out-Null
}

$sourcePrefix = $AnalysisOutput.TrimEnd(
    [System.IO.Path]::DirectorySeparatorChar,
    [System.IO.Path]::AltDirectorySeparatorChar
)
$stagingRoot = Join-Path ([System.IO.Path]::GetTempPath()) (
    "materials-data-analyzer-nasa-audit-" + [System.Guid]::NewGuid().ToString("N")
)
New-Item -ItemType Directory -Force -Path $stagingRoot | Out-Null

try {
    $destinationFullPath = [System.IO.Path]::GetFullPath($Destination)
    $files = @(
        Get-ChildItem -LiteralPath $AnalysisOutput -Recurse -File -Force |
            Where-Object {
                [System.IO.Path]::GetFullPath($_.FullName) -ne $destinationFullPath
            } |
            Sort-Object FullName
    )
    if ($files.Count -eq 0) {
        throw "NASA PCoE analysis output contains no files: $AnalysisOutput"
    }

    $inventory = foreach ($file in $files) {
        $relativePath = $file.FullName.Substring($sourcePrefix.Length).TrimStart(
            [System.IO.Path]::DirectorySeparatorChar,
            [System.IO.Path]::AltDirectorySeparatorChar
        )
        $targetPath = Join-Path $stagingRoot $relativePath
        $targetParent = Split-Path -Parent $targetPath
        if (-not [string]::IsNullOrWhiteSpace($targetParent)) {
            New-Item -ItemType Directory -Force -Path $targetParent | Out-Null
        }
        Copy-Item -LiteralPath $file.FullName -Destination $targetPath -Force
        $hash = Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256
        [PSCustomObject]@{
            relative_path = $relativePath.Replace(
                [System.IO.Path]::DirectorySeparatorChar,
                "/"
            )
            byte_count = [int64]$file.Length
            sha256 = $hash.Hash.ToLowerInvariant()
        }
    }

    $inventoryPath = Join-Path $stagingRoot "_audit_bundle_inventory.csv"
    $inventory | Export-Csv -LiteralPath $inventoryPath -NoTypeInformation -Encoding UTF8

    $readmePath = Join-Path $stagingRoot "_audit_bundle_readme.txt"
    @(
        "NASA PCoE full-audit bundle",
        "source_analysis_output=$AnalysisOutput",
        "created_at_utc=$([DateTime]::UtcNow.ToString('o'))",
        "source_file_count=$($files.Count)",
        "inventory_file=_audit_bundle_inventory.csv",
        "scope=all generated files under the analysis output directory",
        "scientific_boundary=Bundling does not validate, repair, filter, refit, or establish causality."
    ) | Set-Content -LiteralPath $readmePath -Encoding UTF8

    if (Test-Path -LiteralPath $Destination -PathType Leaf) {
        Remove-Item -LiteralPath $Destination -Force
    }
    Compress-Archive -Path (Join-Path $stagingRoot "*") -DestinationPath $Destination -Force

    if (-not (Test-Path -LiteralPath $Destination -PathType Leaf)) {
        throw "NASA PCoE full-audit bundle was not created: $Destination"
    }

    $bundleHash = Get-FileHash -LiteralPath $Destination -Algorithm SHA256
    Write-Host "analysis_output: $AnalysisOutput"
    Write-Host "source_file_count: $($files.Count)"
    Write-Host "audit_bundle: $Destination"
    Write-Host "audit_bundle_sha256: $($bundleHash.Hash.ToLowerInvariant())"
}
finally {
    if (Test-Path -LiteralPath $stagingRoot) {
        Remove-Item -LiteralPath $stagingRoot -Recurse -Force
    }
}
