param(
    [string]$PythonPath = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$logDirectory = Join-Path $projectRoot "reports\logs"
New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$logPath = Join-Path $logDirectory "daily_$timestamp.log"

try {
    & (Join-Path $PSScriptRoot "run_daily.ps1") -PythonPath $PythonPath -Notify *>&1 |
        Tee-Object -FilePath $logPath
    if ($LASTEXITCODE -ne 0) {
        throw "Daily task failed with exit code $LASTEXITCODE."
    }
} catch {
    $_ | Out-String | Add-Content -Path $logPath -Encoding utf8
    throw
}

