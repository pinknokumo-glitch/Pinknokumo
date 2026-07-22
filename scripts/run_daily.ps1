param(
    [string]$PythonPath = "",
    [switch]$Notify
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

if (-not $PythonPath) {
    $venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
    $workVenvPython = Join-Path $projectRoot "work\.venv\Scripts\python.exe"
    $PythonPath = if (Test-Path $venvPython) { $venvPython } elseif (Test-Path $workVenvPython) { $workVenvPython } else { "python" }
}

$arguments = @("scripts\run_daily_pipeline.py")
if ($Notify) { $arguments += "--notify" }
$previousPythonWarnings = $env:PYTHONWARNINGS
try {
    # Third-party deprecation warnings are informational and must not abort a scheduled PowerShell run.
    $env:PYTHONWARNINGS = "ignore::DeprecationWarning"
    & $PythonPath @arguments
    $pythonExitCode = $LASTEXITCODE
} finally {
    $env:PYTHONWARNINGS = $previousPythonWarnings
}
if ($pythonExitCode -ne 0) { throw "Daily pipeline failed with exit code $pythonExitCode." }

Write-Output "Daily StockAI update completed."
