$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

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

$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $AssetsRoot "browsers"
& $Python -m playwright install chromium
& $Python packaging\windows\download_model.py --destination (Join-Path $AssetsRoot "models\faster-whisper-small")

& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --distpath $DistRoot `
    --workpath $PyInstallerRoot `
    packaging\windows\douyin_tool.spec

Copy-Item -Recurse -Force (Join-Path $ProjectRoot "web") (Join-Path $BundleRoot "web")
Copy-Item -Recurse -Force (Join-Path $AssetsRoot "models") (Join-Path $BundleRoot "models")
Copy-Item -Recurse -Force (Join-Path $AssetsRoot "browsers") (Join-Path $BundleRoot "browsers")

$Version = (& $Python -c "from app_meta import APP_VERSION; print(APP_VERSION)").Trim()
"抖音视频工具 v$Version`r`nCPU small 离线字幕版" | Set-Content -Encoding UTF8 (Join-Path $BundleRoot "版本说明.txt")
& $Python packaging\windows\verify_bundle.py $BundleRoot

$Archive = Join-Path $ReleaseRoot "抖音视频工具-v$Version-win64.zip"
if (Test-Path $Archive) { Remove-Item -Force $Archive }
Compress-Archive -Path (Join-Path $BundleRoot "*") -DestinationPath $Archive -CompressionLevel Optimal
Write-Host "Windows 绿色版已生成：$Archive"
