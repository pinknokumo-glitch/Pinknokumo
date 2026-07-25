param(
    [string]$ApkPath = "",
    [switch]$ReplaceExisting,
    [switch]$StartEmulator,
    [string]$AvdName = "Pixel_9a"
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$adb = "C:\Users\pinkn\AppData\Local\Android\Sdk\platform-tools\adb.exe"
$emulator = "C:\Users\pinkn\AppData\Local\Android\Sdk\emulator\emulator.exe"
$packageName = "jp.stockai.navigator"

if (-not (Test-Path -LiteralPath $adb)) {
    throw "adb was not found: $adb"
}
if ([string]::IsNullOrWhiteSpace($ApkPath)) {
    $downloadRoot = Join-Path (Split-Path $root -Parent) "StockAI-Downloads"
    $latestApk = Get-ChildItem -LiteralPath $downloadRoot -Recurse `
        -Filter "StockAI-Navigator-*.apk" -File -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if (-not $latestApk) {
        throw "No signed StockAI APK was found under: $downloadRoot"
    }
    $ApkPath = $latestApk.FullName
}
if (-not (Test-Path -LiteralPath $ApkPath)) {
    throw "APK was not found: $ApkPath"
}

function Get-ConnectedDevices {
    @(& $adb devices | Select-Object -Skip 1 | Where-Object {
        $_ -match "\sdevice$"
    })
}

$deviceLines = @(Get-ConnectedDevices)
if ($deviceLines.Count -eq 0 -and $StartEmulator) {
    if (-not (Test-Path -LiteralPath $emulator)) {
        throw "Android emulator was not found: $emulator"
    }
    $env:ANDROID_AVD_HOME = "C:\Users\pinkn\.android\avd"
    $availableAvds = @(& $emulator -list-avds)
    if ($AvdName -notin $availableAvds) {
        throw "Android emulator was not found: $AvdName"
    }
    Start-Process -FilePath $emulator -ArgumentList @("-avd", $AvdName)
    Write-Host "Starting Android emulator: $AvdName"
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        Start-Sleep -Seconds 3
        $deviceLines = @(Get-ConnectedDevices)
        if ($deviceLines.Count -eq 1) { break }
    }
}
if ($deviceLines.Count -ne 1) {
    throw "Connect exactly one Android device or start one emulator, then retry."
}

if ($ReplaceExisting) {
    & $adb uninstall $packageName | Out-Host
    if ($LASTEXITCODE -ne 0) {
        Write-Host "The existing app was not installed or could not be removed."
    }
}

$installOutput = (& $adb install -r $ApkPath 2>&1 | Out-String)
Write-Host $installOutput.Trim()
if ($LASTEXITCODE -ne 0) {
    if ($installOutput -match "INSTALL_FAILED_UPDATE_INCOMPATIBLE") {
        throw ("The existing debug app uses a different signature. " +
            "Run this script again with -ReplaceExisting. " +
            "That one-time option removes local login and notification settings.")
    }
    throw "APK installation failed."
}

& $adb shell monkey -p $packageName -c android.intent.category.LAUNCHER 1 | Out-Null
Write-Host "Installed and opened: $ApkPath"
