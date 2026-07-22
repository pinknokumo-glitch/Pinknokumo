param([string]$TaskName = "StockAI Navigator Daily")

$ErrorActionPreference = "Stop"
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($null -eq $task) {
    Write-Output "Scheduled task '$TaskName' is not installed. No change was needed."
    exit 0
}
if ($task.State -eq "Disabled") {
    Write-Output "Scheduled task '$TaskName' is already disabled."
    exit 0
}
Disable-ScheduledTask -TaskName $TaskName | Out-Null
Write-Output "Disabled scheduled task '$TaskName'. GitHub Actions remains the active scheduler."
