param(
    [string]$Repository = "pinknokumo-glitch/Pinknokumo",
    [string]$Branch = "agent/two-stage-full-market-screening",
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

$sourceCommit = (& $git rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) { throw "Could not resolve the prepared commit." }
$preparedCommits = @(
    "6d1a64e1e848dddecbfb76cee69613a70c0dd0c2",
    "e2c6cbc230fd69526f95496382618f0323598032",
    "38a40fd3f18b38f7a9f15b0fe2a1b9805256b60e",
    $sourceCommit
)

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
    --title "Add two-stage full-market screening and Supabase preferences" `
    --body "Connects Android and daily runs to row-level-secured Supabase preferences, adds staged RSI relaxation, and expands screening to all current Prime, Standard, and Growth securities. A 17:17 JST workflow refreshes the full universe in bounded batches and saves a guarded candidate pool; the 10:07 JST workflow refreshes only those candidates before final screening and LINE delivery. Stale, incomplete, or failed price updates stop normal delivery. Credentials remain outside source control.").Trim()
if ($LASTEXITCODE -ne 0) { throw "Could not create the pull request." }
Write-Output "Created pull request: $prUrl"

& $gh pr merge $prUrl --repo $Repository --squash --delete-branch
if ($LASTEXITCODE -ne 0) { throw "Could not merge the pull request." }
Write-Output "Merged maintenance update into main."

if ($RunWorkflow) {
    & $gh workflow run evening.yml --repo $Repository --ref main
    if ($LASTEXITCODE -ne 0) { throw "Could not start the cloud workflow." }
    Start-Sleep -Seconds 3
    $runId = (& $gh run list --repo $Repository --workflow evening.yml --limit 1 --json databaseId --jq '.[0].databaseId').Trim()
    Write-Output "Started evening workflow run: $runId"
    Write-Output "Monitor with: gh run watch $runId --repo $Repository"
    Write-Output "The morning LINE workflow was not started."
}
else {
    Write-Output "Workflow was not started; no LINE notification was requested."
}
