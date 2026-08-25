param([Parameter(Mandatory = $true)][string]$Python)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$TestRoot = Join-Path ([IO.Path]::GetTempPath()) ("douyin-update-test-" + [guid]::NewGuid().ToString('N'))
$InstallRoot = Join-Path $TestRoot "install"
$NewBundle = Join-Path $TestRoot "new-bundle"
$UpdateZip = Join-Path $TestRoot "更新包-v1.1.1.zip"

try {
    New-Item -ItemType Directory -Force -Path `
        (Join-Path $InstallRoot "_internal"), `
        (Join-Path $InstallRoot "web"), `
        (Join-Path $InstallRoot "data\transcripts"), `
        (Join-Path $InstallRoot "models"), `
        (Join-Path $NewBundle "_internal"), `
        (Join-Path $NewBundle "web") | Out-Null
    Set-Content -Encoding UTF8 (Join-Path $InstallRoot "抖音视频工具.exe") "old-exe"
    Set-Content -Encoding UTF8 (Join-Path $InstallRoot "_internal\old.dll") "old-runtime"
    Set-Content -Encoding UTF8 (Join-Path $InstallRoot "web\index.html") "old-web"
    Set-Content -Encoding UTF8 (Join-Path $InstallRoot "version.json") '{"version":"1.1.0"}'
    Set-Content -Encoding UTF8 (Join-Path $InstallRoot "data\transcripts\keep.json") "keep-data"
    Set-Content -Encoding UTF8 (Join-Path $InstallRoot "models\keep.bin") "keep-model"

    Set-Content -Encoding UTF8 (Join-Path $NewBundle "抖音视频工具.exe") "new-exe"
    Set-Content -Encoding UTF8 (Join-Path $NewBundle "_internal\new.dll") "new-runtime"
    Set-Content -Encoding UTF8 (Join-Path $NewBundle "web\index.html") "new-web"
    Set-Content -Encoding UTF8 (Join-Path $NewBundle "version.json") '{"version":"1.1.1"}'

    & $Python (Join-Path $PSScriptRoot "build_update_package.py") `
        --bundle $NewBundle --output $UpdateZip --version 1.1.1 --minimum-version 1.1.0
    if ($LASTEXITCODE -ne 0) { throw "生成测试更新包失败" }

    $PowerShell = (Get-Process -Id $PID).Path
    & $PowerShell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "更新工具.ps1") `
        -InstallRoot $InstallRoot -Package $UpdateZip -NoRestart
    if ($LASTEXITCODE -ne 0) { throw "更新器测试执行失败" }

    if ((Get-Content -Raw (Join-Path $InstallRoot "抖音视频工具.exe")).Trim() -ne "new-exe") { throw "EXE 未更新" }
    if (-not (Test-Path (Join-Path $InstallRoot "_internal\new.dll"))) { throw "运行时未更新" }
    if (-not (Test-Path (Join-Path $InstallRoot "data\transcripts\keep.json"))) { throw "字幕数据被覆盖" }
    if (-not (Test-Path (Join-Path $InstallRoot "models\keep.bin"))) { throw "模型被覆盖" }
    if (-not (Test-Path (Join-Path $InstallRoot "_rollback\抖音视频工具.exe"))) { throw "旧版本未保留到回滚目录" }
    Write-Host "Windows offline updater OK"
} finally {
    if (Test-Path $TestRoot) { Remove-Item -Recurse -Force $TestRoot }
}
