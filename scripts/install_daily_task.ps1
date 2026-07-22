param(
    [ValidatePattern('^([01]\d|2[0-3]):[0-5]\d$')]
    [string]$Time = "18:00",
    [string]$TaskName = "StockAI Navigator Daily"
)

$ErrorActionPreference = "Stop"
$runner = Join-Path $PSScriptRoot "run_scheduled_daily.ps1"
if (-not (Test-Path -LiteralPath $runner)) {
    throw "Scheduled runner was not found: $runner"
}

$actionArguments = "-NoProfile -ExecutionPolicy Bypass -File `"$runner`""
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $actionArguments
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At $Time
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 2)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
Write-Output "Installed task '$TaskName' for weekdays at $Time."
