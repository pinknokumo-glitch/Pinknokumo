param(
    [string]$Repository = "pinknokumo-glitch/Pinknokumo",
    [string]$Branch = "agent/cloud-daily-automation"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

function Resolve-Tool([string[]]$Candidates, [string]$Name) {
    foreach ($candidate in $Candidates) {
        if (-not $candidate) { continue }
        $command = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($command) { return $command.Source }
        if (Test-Path -LiteralPath $candidate) { return $candidate }
    }
    throw "$Name was not found."
}

function Get-DotEnvValue([string]$Name) {
    $line = Get-Content -LiteralPath (Join-Path $projectRoot ".env") -Encoding utf8 |
        Where-Object { $_ -match "^$([regex]::Escape($Name))=" } |
        Select-Object -First 1
    if (-not $line) { throw "$Name is missing from .env." }
    $value = $line.Substring($line.IndexOf("=") + 1).Trim()
    if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
        $value = $value.Substring(1, $value.Length - 2)
    }
    if (-not $value) { throw "$Name is empty in .env." }
    return $value
}

$gh = Resolve-Tool @("gh", "C:\Program Files\GitHub CLI\gh.exe") "GitHub CLI"
$git = Resolve-Tool @("git", "C:\Users\pinkn\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\git\cmd\git.exe") "Git"
$pythonCandidates = @(
    (Join-Path $projectRoot ".venv\Scripts\python.exe"),
    (Join-Path $projectRoot "work\.venv\Scripts\python.exe"),
    "python"
)
$python = Resolve-Tool $pythonCandidates "Python"

# The workspace may be created by the Codex sandbox account while this script runs as the Windows user.
# Trust only this exact project directory so Git's ownership protection remains active elsewhere.
$safeDirectory = $projectRoot.Replace('\', '/')
$configuredSafeDirectories = @(& $git config --global --get-all safe.directory 2>$null)
if ($configuredSafeDirectories -notcontains $safeDirectory) {
    & $git config --global --add safe.directory $safeDirectory
    if ($LASTEXITCODE -ne 0) { throw "Could not register the project as a safe Git directory." }
}

& $gh auth status -h github.com
if ($LASTEXITCODE -ne 0) { throw "GitHub CLI authentication is not valid." }

& $python scripts\audit_publish.py
if ($LASTEXITCODE -ne 0) { throw "Publish audit failed." }
& $python -m unittest discover -s tests -q
if ($LASTEXITCODE -ne 0) { throw "Tests failed." }

if (-not (Test-Path -LiteralPath ".git")) {
    & $git init -b main
}
$remotes = @(& $git remote)
if ($remotes -notcontains "origin") {
    & $git remote add origin "https://github.com/$Repository.git"
    if ($LASTEXITCODE -ne 0) { throw "Could not add the GitHub remote." }
} else {
    & $git remote set-url origin "https://github.com/$Repository.git"
    if ($LASTEXITCODE -ne 0) { throw "Could not update the GitHub remote." }
}

& $git fetch origin main
if ($LASTEXITCODE -ne 0) { throw "Could not fetch origin/main." }
& $git checkout -B $Branch origin/main
if ($LASTEXITCODE -ne 0) { throw "Could not create publication branch." }

if (-not (& $git config user.name)) { & $git config user.name "pinknokumo-glitch" }
if (-not (& $git config user.email)) { & $git config user.email "pinknokumo-glitch@users.noreply.github.com" }

& $git add -A
$staged = (& $git diff --cached --name-only)
if (-not $staged) { Write-Output "No source changes need publication." } else {
    Write-Output "Files prepared for publication:"
    $staged | ForEach-Object { Write-Output "- $_" }
    & $git commit -m "Add StockAI cloud daily automation"
    if ($LASTEXITCODE -ne 0) { throw "Commit failed." }
    & $git push --force-with-lease -u origin $Branch
    if ($LASTEXITCODE -ne 0) { throw "Push failed." }
}

$secretNames = @("JQUANTS_API_KEY", "LINE_CHANNEL_ACCESS_TOKEN", "LINE_RECIPIENT_ID")
foreach ($name in $secretNames) {
    $value = Get-DotEnvValue $name
    $value | & $gh secret set $name --repo $Repository
    if ($LASTEXITCODE -ne 0) { throw "Could not register GitHub secret $name." }
}
Write-Output "Registered required GitHub Secrets without displaying their values."

$existingPr = & $gh pr list --repo $Repository --head $Branch --state open --json number --jq '.[0].number'
if ($existingPr) {
    $prNumber = $existingPr
} else {
    $prUrl = & $gh pr create --repo $Repository --base main --head $Branch --title "Add StockAI cloud daily automation" --body "Adds the reviewed StockAI source, weekday 10:00 JST GitHub Actions workflow, database cache, chart publication, and LINE notification. Local secrets and runtime data are excluded."
    if ($LASTEXITCODE -ne 0) { throw "Pull request creation failed." }
    $prNumber = ($prUrl.TrimEnd('/') -split '/')[-1]
}

& $gh pr merge $prNumber --repo $Repository --squash --delete-branch
if ($LASTEXITCODE -ne 0) { throw "Pull request merge failed." }
Write-Output "Merged cloud automation into main."

& $gh workflow run daily.yml --repo $Repository
if ($LASTEXITCODE -ne 0) { throw "Workflow dispatch failed." }
Start-Sleep -Seconds 5
$runId = & $gh run list --repo $Repository --workflow daily.yml --limit 1 --json databaseId --jq '.[0].databaseId'
if ($runId) {
    Write-Output "Started workflow run: $runId"
    Write-Output "Monitor with: gh run watch $runId --repo $Repository"
} else {
    Write-Output "Workflow was dispatched. Check the GitHub Actions page for progress."
}
