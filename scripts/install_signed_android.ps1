param(
    [string]$ApkPath = "",
    [switch]$ReplaceExisting,
    [switch]$StartEmulator,
    [string]$AvdName = "Pixel_9a"
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$androidSdk = Join-Path $env:LOCALAPPDATA "Android\Sdk"
$adb = Join-Path $androidSdk "platform-tools\adb.exe"
$emulator = Join-Path $androidSdk "emulator\emulator.exe"
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

function Get-AndroidDeviceRows {
    @(& $adb devices | Select-Object -Skip 1 | Where-Object {
        -not [string]::IsNullOrWhiteSpace($_)
    })
}

function Stop-StaleEmulator {
    $running = @(Get-Process -Name "emulator", "qemu-system-x86_64" `
        -ErrorAction SilentlyContinue)
    if ($running.Count -gt 0) {
        Write-Host "Stopping an offline Android emulator..."
        $running | Stop-Process -Force
        Start-Sleep -Seconds 2
    }
    $stillRunning = @(Get-Process -Name "emulator", "qemu-system-x86_64" `
        -ErrorAction SilentlyContinue)
    if ($stillRunning.Count -gt 0) {
        throw "The offline Android emulator could not be stopped."
    }
}

function Remove-StaleAvdLocks {
    $avdHome = $env:ANDROID_AVD_HOME
    if ([string]::IsNullOrWhiteSpace($avdHome)) {
        $avdHome = Join-Path $env:USERPROFILE ".android\avd"
    }
    $avdPath = Join-Path $avdHome "$AvdName.avd"
    if (-not (Test-Path -LiteralPath $avdPath)) {
        return
    }
    $resolvedHome = (Resolve-Path -LiteralPath $avdHome).Path
    $resolvedAvd = (Resolve-Path -LiteralPath $avdPath).Path
    if (-not $resolvedAvd.StartsWith(
        $resolvedHome + [IO.Path]::DirectorySeparatorChar,
        [StringComparison]::OrdinalIgnoreCase
    )) {
        throw "Refusing to clean emulator locks outside the Android AVD folder."
    }
    $locks = @(Get-ChildItem -LiteralPath $resolvedAvd -Force |
        Where-Object { $_.Name -like "*.lock" })
    foreach ($lock in $locks) {
        Remove-Item -LiteralPath $lock.FullName -Recurse -Force
    }
    if ($locks.Count -gt 0) {
        Write-Host "Removed $($locks.Count) stale emulator lock item(s)."
    }
}

$deviceLines = @(Get-ConnectedDevices)
if ($deviceLines.Count -eq 0 -and $StartEmulator) {
    if (-not (Test-Path -LiteralPath $emulator)) {
        throw "Android emulator was not found: $emulator"
    }
    if ([string]::IsNullOrWhiteSpace($env:ANDROID_AVD_HOME)) {
        $env:ANDROID_AVD_HOME = Join-Path $env:USERPROFILE ".android\avd"
    }
    $availableAvds = @(& $emulator -list-avds)
    if ($AvdName -notin $availableAvds) {
        throw "Android emulator was not found: $AvdName"
    }
    $offlineDevice = @(& $adb devices | Select-Object -Skip 1 |
        Where-Object { $_ -match "\soffline$" })
    if ($offlineDevice.Count -gt 0) {
        Write-Host "Detected an offline Android emulator."
    }
    Stop-StaleEmulator
    Remove-StaleAvdLocks
    Start-Process -FilePath $emulator `
        -ArgumentList @("-avd", $AvdName, "-no-snapshot-load")
    Write-Host "Cold-starting Android emulator: $AvdName"
    for ($attempt = 0; $attempt -lt 100; $attempt++) {
        Start-Sleep -Seconds 3
        $deviceLines = @(Get-ConnectedDevices)
        if ($deviceLines.Count -eq 1) { break }
    }
}
if ($deviceLines.Count -ne 1) {
    $deviceRows = @(Get-AndroidDeviceRows)
    if ($deviceRows -match "\sunauthorized$") {
        throw ("Android USB debugging is waiting for approval. " +
            "On the Android device, select Always allow from this computer, " +
            "tap Allow, and run this command again.")
    }
    if ($deviceRows -match "\soffline$") {
        throw ("The Android emulator is still offline after recovery. " +
            "Close it from Android Studio Device Manager and retry.")
    }
    throw "Connect exactly one Android device or start one emulator, then retry."
}

$bootCompleted = $false
for ($attempt = 0; $attempt -lt 120; $attempt++) {
    $bootState = (& $adb shell getprop sys.boot_completed 2>$null).Trim()
    if ($bootState -eq "1") {
        $bootCompleted = $true
        break
    }
    Start-Sleep -Seconds 2
}
if (-not $bootCompleted) {
    throw "The Android device connected but did not finish booting."
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
