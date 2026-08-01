param(
    [string]$OutputDirectory = "data/raw/battery/nasa_pcoe",
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
Add-Type -AssemblyName System.IO.Compression.FileSystem

$sourceUrl = "https://phm-datasets.s3.amazonaws.com/NASA/5.+Battery+Data+Set.zip"
$repositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
if ($PSBoundParameters.ContainsKey("OutputDirectory")) {
    if ([System.IO.Path]::IsPathRooted($OutputDirectory)) {
        $outputRoot = [System.IO.Path]::GetFullPath($OutputDirectory)
    }
    else {
        $outputRoot = [System.IO.Path]::GetFullPath(
            (Join-Path (Get-Location).Path $OutputDirectory)
        )
    }
}
else {
    $outputRoot = [System.IO.Path]::GetFullPath(
        (Join-Path $repositoryRoot $OutputDirectory)
    )
}
$archivePath = Join-Path $outputRoot "5_Battery_Data_Set.zip"
$partialPath = "$archivePath.partial"
$receiptPath = Join-Path $outputRoot "retrieval_receipt.json"

New-Item -ItemType Directory -Force -Path $outputRoot | Out-Null

if ((Test-Path $archivePath) -and -not $Force) {
    throw "Archive already exists: $archivePath. Use -Force to replace it explicitly."
}

if (Test-Path $partialPath) {
    Remove-Item -Force $partialPath
}

$startedAt = [DateTimeOffset]::UtcNow
$zipEntryCount = 0
try {
    Invoke-WebRequest -Uri $sourceUrl -OutFile $partialPath

    $partialFile = Get-Item $partialPath
    if ($partialFile.Length -le 0) {
        throw "Downloaded archive is empty: $partialPath"
    }

    $zip = [System.IO.Compression.ZipFile]::OpenRead($partialPath)
    try {
        $zipEntryCount = $zip.Entries.Count
        if ($zipEntryCount -le 0) {
            throw "Downloaded ZIP contains no entries: $partialPath"
        }
    }
    finally {
        $zip.Dispose()
    }

    Move-Item -Force $partialPath $archivePath
}
catch {
    if (Test-Path $partialPath) {
        Remove-Item -Force $partialPath
    }
    throw
}
$completedAt = [DateTimeOffset]::UtcNow

$file = Get-Item $archivePath
$sha256 = (Get-FileHash -Path $archivePath -Algorithm SHA256).Hash.ToLowerInvariant()

$receipt = [ordered]@{
    schema_version = "1.0"
    source_name = "NASA PCoE Li-ion Battery Aging Datasets"
    source_url = $sourceUrl
    retrieved_at = $completedAt.ToString("o")
    retrieval_started_at = $startedAt.ToString("o")
    archive_path = $file.FullName
    archive_filename = $file.Name
    archive_sha256 = $sha256
    size_bytes = $file.Length
    zip_entry_count = $zipEntryCount
    credential_policy = [ordered]@{
        network_access_required = $true
        send_credentials = $false
        store_credentials = $false
    }
    note = "The receipt records transport provenance only. Import and scientific admission remain separate checks."
}

$receiptJson = $receipt | ConvertTo-Json -Depth 6
$utf8WithoutBom = [System.Text.UTF8Encoding]::new($false)
[System.IO.File]::WriteAllText($receiptPath, $receiptJson, $utf8WithoutBom)

Write-Output "archive: $archivePath"
Write-Output "sha256: $sha256"
Write-Output "receipt: $receiptPath"
