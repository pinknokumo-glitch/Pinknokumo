param(
    [string]$Repository = "pinknokumo-glitch/Pinknokumo",
    [switch]$StartEmulator,
    [string]$AvdName = "Pixel_9a"
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$downloadRoot = Join-Path (Split-Path $root -Parent) "StockAI-Downloads"
$gh = (Get-Command gh.exe -ErrorAction Stop).Source

& $gh auth status
if ($LASTEXITCODE -ne 0) {
    throw "GitHub CLI is not authenticated. Run: gh auth login -h github.com"
}

$runJson = & $gh run list `
    --repo $Repository `
    --workflow android.yml `
    --status success `
    --limit 1 `
    --json databaseId,url,headSha
if ($LASTEXITCODE -ne 0) {
    throw "Could not find the latest successful Android build."
}
$runs = @($runJson | ConvertFrom-Json)
if ($runs.Count -eq 0) {
    throw "No successful Android APK build is available."
}
$run = $runs[0]
$target = Join-Path $downloadRoot ([string]$run.databaseId)
New-Item -ItemType Directory -Path $target -Force | Out-Null

if (-not (Get-ChildItem -LiteralPath $target -Filter "*.apk" -File -ErrorAction SilentlyContinue)) {
    & $gh run download $run.databaseId `
        --repo $Repository `
        --name "StockAI-Navigator-Android" `
        --dir $target
    if ($LASTEXITCODE -ne 0) {
        throw "Could not download the signed Android artifact."
    }
}

$apk = Get-ChildItem -LiteralPath $target -Filter "StockAI-Navigator-*.apk" -File |
    Select-Object -First 1
if (-not $apk) {
    throw "The downloaded artifact does not contain a StockAI APK."
}
$checksumPath = "$($apk.FullName).sha256"
if (-not (Test-Path -LiteralPath $checksumPath)) {
    throw "The APK checksum file is missing."
}
$expected = ((Get-Content -LiteralPath $checksumPath -Raw).Trim() -split "\s+")[0]
$actual = (Get-FileHash -LiteralPath $apk.FullName -Algorithm SHA256).Hash
if ($actual -ne $expected.ToUpperInvariant()) {
    throw "APK checksum verification failed."
}

Write-Host "Verified APK: $($apk.FullName)"
$installer = Join-Path $PSScriptRoot "install_signed_android.ps1"
$installerArgs = @{
    ApkPath = $apk.FullName
    AvdName = $AvdName
}
if ($StartEmulator) {
    $installerArgs["StartEmulator"] = $true
}
& $installer @installerArgs
if ($LASTEXITCODE -ne 0) {
    throw "Signed APK update failed."
}
Write-Host "Updated from GitHub Actions run: $($run.url)"
