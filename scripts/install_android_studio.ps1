$ErrorActionPreference = "Stop"
$winget = Get-Command winget.exe -ErrorAction SilentlyContinue
if (-not $winget) {
    throw "winget is not available. Install 'App Installer' from Microsoft Store, then run this script again."
}

& $winget.Source install --id Google.AndroidStudio --exact `
    --accept-package-agreements --accept-source-agreements
if ($LASTEXITCODE -ne 0) {
    throw "Android Studio installation did not complete successfully."
}
Write-Output "Android Studio is installed. Start it once and complete the Standard SDK setup."
