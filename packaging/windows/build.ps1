param(
    [string]$MinimumVersion = "1.1.0",
    [switch]$BuildUpdatePackage
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
if ($PSVersionTable.PSVersion -lt [Version]"7.3") {
    throw "PowerShell 7.3 or newer is required to build the Windows bundle."
}
$PSNativeCommandUseErrorActionPreference = $true

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$BuildRoot = Join-Path $ProjectRoot "build"
$EnvironmentRoot = Join-Path $BuildRoot "windows-env"
$AssetsRoot = Join-Path $BuildRoot "windows-assets"
$PyInstallerRoot = Join-Path $BuildRoot "pyinstaller"
$DistRoot = Join-Path $ProjectRoot "dist"
$ReleaseRoot = Join-Path $ProjectRoot "releases"
$BundleRoot = Join-Path $DistRoot "抖音视频工具"

Set-Location $ProjectRoot
foreach ($Path in @($EnvironmentRoot, $AssetsRoot, $PyInstallerRoot, $DistRoot)) {
    if (Test-Path $Path) { Remove-Item -Recurse -Force $Path }
}
New-Item -ItemType Directory -Force $BuildRoot, $AssetsRoot, $ReleaseRoot | Out-Null

py -3.12 -m venv $EnvironmentRoot
$Python = Join-Path $EnvironmentRoot "Scripts\python.exe"
& $Python -m pip install --upgrade pip
& $Python -m pip install -r requirements-windows.lock
& $Python -m unittest discover -s tests -v
& (Get-Process -Id $PID).Path -NoProfile -ExecutionPolicy Bypass -File packaging\windows\test_update.ps1 -Python $Python

$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $AssetsRoot "browsers"
& $Python -m playwright install chromium
& $Python packaging\windows\download_model.py --model small --destination (Join-Path $AssetsRoot "models\faster-whisper-small")
& $Python packaging\windows\download_model.py --model medium --destination (Join-Path $AssetsRoot "models\faster-whisper-medium")

& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --distpath $DistRoot `
    --workpath $PyInstallerRoot `
    packaging\windows\douyin_tool.spec

Copy-Item -Recurse -Force (Join-Path $ProjectRoot "web") (Join-Path $BundleRoot "web")
Copy-Item -Recurse -Force (Join-Path $AssetsRoot "models") (Join-Path $BundleRoot "models")
Copy-Item -Recurse -Force (Join-Path $AssetsRoot "browsers") (Join-Path $BundleRoot "browsers")
Copy-Item -Force (Join-Path $PSScriptRoot "一键更新.bat") (Join-Path $BundleRoot "一键更新.bat")
Copy-Item -Force (Join-Path $PSScriptRoot "updater.ps1") (Join-Path $BundleRoot "updater.ps1")

$Version = (& $Python -c "from app_meta import APP_VERSION; print(APP_VERSION)").Trim()
"抖音视频工具 v$Version`r`nCPU small + medium 离线字幕版" | Set-Content -Encoding UTF8 (Join-Path $BundleRoot "版本说明.txt")
@{ version = $Version; update_protocol = 1 } | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $BundleRoot "version.json")
& $Python packaging\windows\verify_bundle.py $BundleRoot
& (Get-Process -Id $PID).Path -NoProfile -ExecutionPolicy Bypass -File packaging\windows\test_bundle_runtime.ps1 -Bundle $BundleRoot

$Archive = Join-Path $ReleaseRoot "抖音视频工具-v$Version-win64.zip"
if (Test-Path $Archive) { Remove-Item -Force $Archive }
Compress-Archive -Path (Join-Path $BundleRoot "*") -DestinationPath $Archive -CompressionLevel Optimal
Write-Host "Windows 绿色版已生成：$Archive"

if ($BuildUpdatePackage) {
    $UpdateArchive = Join-Path $ReleaseRoot "更新包-v$Version.zip"
    & $Python packaging\windows\build_update_package.py `
        --bundle $BundleRoot `
        --output $UpdateArchive `
        --version $Version `
        --minimum-version $MinimumVersion
    Write-Host "普通更新包已生成：$UpdateArchive"
}
