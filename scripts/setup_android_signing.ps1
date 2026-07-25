param(
    [string]$Repository = "pinknokumo-glitch/Pinknokumo",
    [string]$Alias = "stockai",
    [string]$JavaHome = "C:\Program Files\Android\Android Studio\jbr"
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$signingDir = Join-Path $root "android\signing"
$keystorePath = Join-Path $signingDir "stockai-release.jks"
$keytool = Join-Path $JavaHome "bin\keytool.exe"

if (-not (Test-Path -LiteralPath $keytool)) {
    throw "keytool was not found: $keytool"
}
$gh = (Get-Command gh.exe -ErrorAction Stop).Source
& $gh auth status
if ($LASTEXITCODE -ne 0) {
    throw "GitHub CLI is not authenticated. Run: gh auth login -h github.com"
}

function ConvertTo-PlainText([Security.SecureString]$SecureValue) {
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureValue)
    try {
        [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    }
}

function Set-GitHubSecret([string]$Name, [string]$Value) {
    $Value | & $gh secret set $Name --repo $Repository
    if ($LASTEXITCODE -ne 0) {
        throw "Could not register GitHub Secret: $Name"
    }
}

Write-Host "Enter one Android signing password. Keep it for all future app updates."
$passwordSecure = Read-Host "Signing password (8 or more characters)" -AsSecureString
$storePassword = ConvertTo-PlainText $passwordSecure
$keyPassword = $storePassword

try {
    if ($storePassword.Length -lt 8 -or $keyPassword.Length -lt 8) {
        throw "The password must contain at least 8 characters."
    }
    New-Item -ItemType Directory -Path $signingDir -Force | Out-Null
    if (-not (Test-Path -LiteralPath $keystorePath)) {
        & $keytool -genkeypair `
            -keystore $keystorePath `
            -storepass $storePassword `
            -keypass $keyPassword `
            -alias $Alias `
            -storetype JKS `
            -keyalg RSA `
            -keysize 4096 `
            -validity 10000 `
            -dname "CN=StockAI Navigator,O=StockAI,C=JP"
        if ($LASTEXITCODE -ne 0) { throw "Could not create the signing key." }
        Write-Host "Created the signing key: $keystorePath"
    }
    else {
        & $keytool -list -keystore $keystorePath -storepass $storePassword -alias $Alias | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "Could not validate the existing signing key or password."
        }
        Write-Host "Reusing the existing signing key."
    }

    $keystoreBase64 = [Convert]::ToBase64String(
        [IO.File]::ReadAllBytes($keystorePath)
    )
    Set-GitHubSecret "ANDROID_KEYSTORE_BASE64" $keystoreBase64
    Set-GitHubSecret "ANDROID_KEYSTORE_PASSWORD" $storePassword
    Set-GitHubSecret "ANDROID_KEY_ALIAS" $Alias
    Set-GitHubSecret "ANDROID_KEY_PASSWORD" $keyPassword

    Write-Host "Registered all Android signing GitHub Secrets."
    Write-Host "IMPORTANT: Back up android\signing\stockai-release.jks in a secure location."
}
finally {
    $storePassword = $null
    $keyPassword = $null
    $keystoreBase64 = $null
}
