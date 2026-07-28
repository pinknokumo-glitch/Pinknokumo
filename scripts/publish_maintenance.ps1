param(
    [string]$Repository = "pinknokumo-glitch/Pinknokumo",
    [string]$Branch = "agent/pooled-backtest-comparison",
    [switch]$RunWorkflow,
    [switch]$RunAndroidBuild
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
    ".gitignore",
    ".github/workflows/daily.yml",
    ".github/workflows/evening.yml",
    ".github/workflows/android.yml",
    "android/app/src/main/AndroidManifest.xml",
    "android/app/build.gradle.kts",
    "android/app/src/main/java/jp/stockai/navigator/ApiClient.kt",
    "android/app/src/main/java/jp/stockai/navigator/FavoriteStore.kt",
    "android/app/src/main/java/jp/stockai/navigator/MainActivity.kt",
    "android/app/src/main/java/jp/stockai/navigator/SessionStore.kt",
    "android/app/src/main/java/jp/stockai/navigator/StockNotificationWorker.kt",
    "android/app/src/main/java/jp/stockai/navigator/SupabaseClient.kt",
    "api.py",
    "config/settings.yaml",
    "config/screening_options.yaml",
    "docs/SUPABASE_SETUP.md",
    "docs/ANDROID_DISTRIBUTION.md",
    "modules/backtest.py",
    "modules/backtest_history.py",
    "modules/batch_backtest.py",
    "modules/ai_comment.py",
    "modules/cloud_batch.py",
    "modules/cloud_candidates.py",
    "modules/cloud_preferences.py",
    "modules/data_loader.py",
    "modules/expectation.py",
    "modules/fundamentals.py",
    "modules/morning_candidates.py",
    "modules/pooled_backtest.py",
    "modules/cloud_results.py",
    "modules/screener.py",
    "modules/screening_options.py",
    "modules/screening_relaxation.py",
    "modules/technical.py",
    "requirements.txt",
    "scripts/run_daily_pipeline.py",
    "scripts/run_evening_universe.py",
    "scripts/run_cloud_user_screenings.py",
    "scripts/run_backtest_requests.py",
    "scripts/install_signed_android.ps1",
    "scripts/setup_android_signing.ps1",
    "scripts/update_signed_android.ps1",
    "scripts/publish_maintenance.ps1",
    "tests/test_batch_backtest.py",
    "tests/test_backtest_history.py",
    "tests/test_backtest.py",
    "tests/test_api.py",
    "tests/test_cloud_batch.py",
    "tests/test_cloud_preferences.py",
    "tests/test_cloud_candidates.py",
    "tests/test_supabase_schema.py",
    "tests/test_screening_relaxation.py",
    "supabase/screening_preferences.sql",
    "supabase/screening_results.sql",
    "supabase/screening_candidates.sql",
    "supabase/backtest_requests.sql",
    "supabase/ui_v03_upgrade.sql",
    "supabase/multi_user_upgrade.sql",
    "supabase/trade_strategy_upgrade.sql",
    "supabase/expectation_evaluation_upgrade.sql",
    "supabase/screening_results_update_grant.sql",
    "supabase/holding_period_upgrade.sql",
    "supabase/conditional_price_estimate_upgrade.sql",
    "supabase/screening_result_summary_upgrade.sql",
    "supabase/pooled_backtest_upgrade.sql",
    "tests/test_cloud_results.py",
    "tests/test_core.py",
    "tests/test_data_loader.py",
    "tests/test_pooled_backtest.py"
)
& $git add -- $publishFiles
if ($LASTEXITCODE -ne 0) { throw "Could not stage the maintenance files." }
$staged = (& $git diff --cached --name-only)
if ($staged) {
    & $git commit -m "Add pooled backtest comparison"
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
    # Remove tracking refs for branches deleted after previous PR merges.
    # Otherwise force-with-lease can reject reuse of the default branch as stale.
    & $git fetch --prune origin main
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
    --title "Simplify Android result cards and add watchlist" `
    --body "Shows score, average return, win rate, and maximum drawdown in compact result cards; adds tap-through technical/fundamental details and a per-user on-device monitoring list.").Trim()
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
    Write-Output "The morning candidate backtest and app-result workflow was started."
}
else {
    Write-Output "Workflow was not started."
}

if ($RunAndroidBuild) {
    & $gh workflow run android.yml --repo $Repository --ref main
    if ($LASTEXITCODE -ne 0) { throw "Could not start the Android APK build." }
    Start-Sleep -Seconds 3
    $androidRunId = (& $gh run list --repo $Repository --workflow android.yml --limit 1 `
        --json databaseId --jq '.[0].databaseId').Trim()
    Write-Output "Started Android APK build: $androidRunId"
    Write-Output "Build URL: https://github.com/$Repository/actions/runs/$androidRunId"
    Write-Output "Monitor with: gh run watch $androidRunId --repo $Repository"
}
