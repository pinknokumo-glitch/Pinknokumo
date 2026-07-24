param(
    [string]$Repository = "pinknokumo-glitch/Pinknokumo",
    [string]$Branch = "agent/candidate-backtest-notifications",
    [switch]$RunWorkflow
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $root

$git = (Get-Command git.exe -ErrorAction Stop).Source
$gh = (Get-Command gh.exe -ErrorAction Stop).Source
$python = Join-Path $root "work\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Python environment not found: $python"
}

& $git config --global --add safe.directory ($root -replace '\\', '/')
& $gh auth status
if ($LASTEXITCODE -ne 0) { throw "GitHub CLI is not authenticated." }

& $python scripts\audit_publish.py
if ($LASTEXITCODE -ne 0) { throw "Publish audit failed." }

$env:PYTHONWARNINGS = "ignore::DeprecationWarning"
& $python -m unittest discover -s tests -q
if ($LASTEXITCODE -ne 0) { throw "Tests failed." }

$publishFiles = @(
    ".github/workflows/daily.yml",
    "modules/batch_backtest.py",
    "scripts/run_daily_pipeline.py",
    "scripts/publish_maintenance.ps1",
    "tests/test_batch_backtest.py"
)
& $git add -- $publishFiles
if ($LASTEXITCODE -ne 0) { throw "Could not stage the maintenance files." }
$staged = (& $git diff --cached --name-only)
if ($staged) {
    & $git commit -m "Add candidate backtesting to LINE notifications"
    if ($LASTEXITCODE -ne 0) { throw "Could not create the prepared commit." }
}

$sourceCommit = (& $git rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) { throw "Could not resolve the prepared commit." }
$preparedCommits = @($sourceCommit)

$runtimeFiles = @(Get-ChildItem (Join-Path $root "work") -Filter "daily_report_*.json" -File -ErrorAction SilentlyContinue)
$backupDir = Join-Path $root "data\publish-maintenance-backup"
if ($runtimeFiles.Count -gt 0) {
    New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
    foreach ($file in $runtimeFiles) { Move-Item -LiteralPath $file.FullName -Destination $backupDir -Force }
}
try {
    & $git fetch origin main
    if ($LASTEXITCODE -ne 0) { throw "Could not fetch origin/main." }
    & $git switch -C $Branch origin/main
    if ($LASTEXITCODE -ne 0) { throw "Could not create the maintenance branch." }
    foreach ($commit in $preparedCommits) {
        & $git cherry-pick $commit
        if ($LASTEXITCODE -ne 0) { throw "Could not apply prepared commit: $commit" }
    }
}
finally {
    if (Test-Path $backupDir) {
        Get-ChildItem -LiteralPath $backupDir -File | ForEach-Object {
            Move-Item -LiteralPath $_.FullName -Destination (Join-Path $root "work") -Force
        }
        Remove-Item -LiteralPath $backupDir -Force
    }
}
& $git push --force-with-lease -u origin $Branch
if ($LASTEXITCODE -ne 0) { throw "Could not push the maintenance branch." }

$prUrl = (& $gh pr create --repo $Repository --base main --head $Branch `
    --title "Add candidate backtesting to LINE notifications" `
    --body "Backtests only stocks that match the effective screening stage, including automatically relaxed rules. The refreshed expectation scores and historical statistics are then used to rerank candidates and populate each LINE commentary without backtesting the full market every morning.").Trim()
if ($LASTEXITCODE -ne 0) { throw "Could not create the pull request." }
Write-Output "Created pull request: $prUrl"

& $gh pr merge $prUrl --repo $Repository --squash --delete-branch
if ($LASTEXITCODE -ne 0) { throw "Could not merge the pull request." }
Write-Output "Merged maintenance update into main."

if ($RunWorkflow) {
    & $gh workflow run daily.yml --repo $Repository --ref main
    if ($LASTEXITCODE -ne 0) { throw "Could not start the cloud workflow." }
    Start-Sleep -Seconds 3
    $runId = (& $gh run list --repo $Repository --workflow daily.yml --limit 1 --json databaseId --jq '.[0].databaseId').Trim()
    Write-Output "Started daily workflow run: $runId"
    Write-Output "Monitor with: gh run watch $runId --repo $Repository"
    Write-Output "The morning candidate backtest and LINE workflow was started."
}
else {
    Write-Output "Workflow was not started; no LINE notification was requested."
}
