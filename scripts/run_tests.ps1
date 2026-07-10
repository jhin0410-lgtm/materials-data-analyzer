param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$PytestArgs
)

$ErrorActionPreference = "Stop"

$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptPath
$tempRoot = Join-Path $repoRoot "outputs\pytest-temp"
$runId = "{0:yyyyMMdd-HHmmss}-{1}" -f (Get-Date), $PID
$runTemp = Join-Path $tempRoot $runId

New-Item -ItemType Directory -Path $runTemp -Force | Out-Null

$tempRootFull = [System.IO.Path]::GetFullPath($tempRoot)
$runTempFull = [System.IO.Path]::GetFullPath($runTemp)
if (-not $runTempFull.StartsWith($tempRootFull, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to use pytest temp path outside outputs/pytest-temp: $runTempFull"
}

$previousTemp = $env:TEMP
$previousTmp = $env:TMP
$exitCode = 0

try {
    $env:TEMP = $runTempFull
    $env:TMP = $runTempFull

    Push-Location $repoRoot
    try {
        & python -m pytest --basetemp $runTempFull @PytestArgs
        $exitCode = $LASTEXITCODE
    }
    finally {
        Pop-Location
    }
}
finally {
    $env:TEMP = $previousTemp
    $env:TMP = $previousTmp

    if (Test-Path -LiteralPath $runTempFull) {
        Remove-Item -LiteralPath $runTempFull -Recurse -Force
    }
}

exit $exitCode
