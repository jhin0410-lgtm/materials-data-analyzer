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

$sourcePrefix = $AnalysisOutput.TrimEnd(
    [System.IO.Path]::DirectorySeparatorChar,
    [System.IO.Path]::AltDirectorySeparatorChar
)
$pathComparison = if (
    [System.Environment]::OSVersion.Platform -eq [System.PlatformID]::Win32NT
) {
    [System.StringComparison]::OrdinalIgnoreCase
}
else {
    [System.StringComparison]::Ordinal
}
$sourcePrefixWithSeparator = $sourcePrefix + [System.IO.Path]::DirectorySeparatorChar
if (
    [string]::Equals($Destination, $sourcePrefix, $pathComparison) -or
    $Destination.StartsWith($sourcePrefixWithSeparator, $pathComparison)
) {
    throw "Audit bundle destination must be outside the analysis output directory: $Destination"
}

$destinationParent = Split-Path -Parent $Destination
if ([string]::IsNullOrWhiteSpace($destinationParent)) {
    throw "Audit bundle destination must have a parent directory: $Destination"
}
New-Item -ItemType Directory -Force -Path $destinationParent | Out-Null

$stagingRoot = Join-Path ([System.IO.Path]::GetTempPath()) (
    "materials-data-analyzer-nasa-audit-" + [System.Guid]::NewGuid().ToString("N")
)
$temporaryArchive = Join-Path $destinationParent (
    ".nasa-pcoe-full-audit-" + [System.Guid]::NewGuid().ToString("N") + ".tmp.zip"
)
$backupArchive = Join-Path $destinationParent (
    ".nasa-pcoe-full-audit-" + [System.Guid]::NewGuid().ToString("N") + ".backup.zip"
)
New-Item -ItemType Directory -Force -Path $stagingRoot | Out-Null

try {
    $files = @(
        Get-ChildItem -LiteralPath $AnalysisOutput -Recurse -File -Force |
            Sort-Object FullName
    )
    if ($files.Count -eq 0) {
        throw "NASA PCoE analysis output contains no files: $AnalysisOutput"
    }

    $reservedArchivePaths = [System.Collections.Generic.HashSet[string]]::new(
        [System.StringComparer]::OrdinalIgnoreCase
    )
    [void]$reservedArchivePaths.Add("_audit_bundle_inventory.csv")
    [void]$reservedArchivePaths.Add("_audit_bundle_readme.txt")

    $inventory = foreach ($file in $files) {
        $relativePath = $file.FullName.Substring($sourcePrefix.Length).TrimStart(
            [System.IO.Path]::DirectorySeparatorChar,
            [System.IO.Path]::AltDirectorySeparatorChar
        )
        $archivePath = $relativePath.Replace(
            [System.IO.Path]::DirectorySeparatorChar,
            "/"
        )
        if ($reservedArchivePaths.Contains($archivePath)) {
            throw "Analysis output collides with reserved audit bundle path: $archivePath"
        }

        $targetPath = Join-Path $stagingRoot $relativePath
        $targetParent = Split-Path -Parent $targetPath
        if (-not [string]::IsNullOrWhiteSpace($targetParent)) {
            New-Item -ItemType Directory -Force -Path $targetParent | Out-Null
        }
        Copy-Item -LiteralPath $file.FullName -Destination $targetPath -Force
        $stagedFile = Get-Item -LiteralPath $targetPath
        $hash = Get-FileHash -LiteralPath $targetPath -Algorithm SHA256
        [PSCustomObject]@{
            relative_path = $archivePath
            byte_count = [int64]$stagedFile.Length
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

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [System.IO.Compression.ZipFile]::CreateFromDirectory(
        $stagingRoot,
        $temporaryArchive,
        [System.IO.Compression.CompressionLevel]::Optimal,
        $false
    )
    if (-not (Test-Path -LiteralPath $temporaryArchive -PathType Leaf)) {
        throw "NASA PCoE temporary audit bundle was not created: $temporaryArchive"
    }
    $temporaryHash = (
        Get-FileHash -LiteralPath $temporaryArchive -Algorithm SHA256
    ).Hash.ToLowerInvariant()

    if (Test-Path -LiteralPath $Destination -PathType Leaf) {
        [System.IO.File]::Replace(
            $temporaryArchive,
            $Destination,
            $backupArchive,
            $true
        )
        if (Test-Path -LiteralPath $backupArchive -PathType Leaf) {
            Remove-Item -LiteralPath $backupArchive -Force
        }
    }
    else {
        [System.IO.File]::Move($temporaryArchive, $Destination)
    }

    if (-not (Test-Path -LiteralPath $Destination -PathType Leaf)) {
        throw "NASA PCoE full-audit bundle was not created: $Destination"
    }
    $bundleHash = (
        Get-FileHash -LiteralPath $Destination -Algorithm SHA256
    ).Hash.ToLowerInvariant()
    if ($bundleHash -ne $temporaryHash) {
        throw "NASA PCoE audit bundle hash changed during final placement"
    }

    Write-Host "analysis_output: $AnalysisOutput"
    Write-Host "source_file_count: $($files.Count)"
    Write-Host "audit_bundle: $Destination"
    Write-Host "audit_bundle_sha256: $bundleHash"
}
finally {
    if (Test-Path -LiteralPath $stagingRoot) {
        Remove-Item -LiteralPath $stagingRoot -Recurse -Force
    }
    if (Test-Path -LiteralPath $temporaryArchive -PathType Leaf) {
        Remove-Item -LiteralPath $temporaryArchive -Force
    }
    if (Test-Path -LiteralPath $backupArchive -PathType Leaf) {
        Remove-Item -LiteralPath $backupArchive -Force
    }
}
