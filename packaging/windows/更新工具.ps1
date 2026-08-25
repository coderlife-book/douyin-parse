param(
    [string]$InstallRoot = $PSScriptRoot,
    [string]$Package = "",
    [switch]$NoRestart
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$ProtectedNames = @(
    "config.json", "data", "downloads", "models", "browsers",
    "一键更新.bat", "更新工具.ps1", "_rollback", "update-temp"
)
$ExecutableName = "抖音视频工具.exe"

function Resolve-UpdatePackage {
    param([string]$Root, [string]$ExplicitPackage)
    if ($ExplicitPackage) {
        return (Resolve-Path $ExplicitPackage).Path
    }
    $Candidates = Get-ChildItem -Path $Root -Filter "更新包-v*.zip" -File | ForEach-Object {
        if ($_.BaseName -match '^更新包-v(?<version>\d+\.\d+\.\d+)$') {
            [PSCustomObject]@{ File = $_; Version = [version]$Matches.version }
        }
    } | Sort-Object Version -Descending
    if (-not $Candidates) { throw "程序目录中没有找到 更新包-vX.Y.Z.zip" }
    return $Candidates[0].File.FullName
}

function Assert-SafeRelativePath {
    param([string]$RelativePath)
    $Normalized = $RelativePath.Replace('\', '/')
    if (
        [string]::IsNullOrWhiteSpace($Normalized) -or
        $Normalized.StartsWith('/') -or
        $Normalized -match '^[A-Za-z]:' -or
        $Normalized -match '(^|/)\.\.(/|$)'
    ) { throw "更新包包含非法路径：$RelativePath" }
    $TopLevel = ($Normalized -split '/')[0]
    if ($ProtectedNames -contains $TopLevel) { throw "更新包试图覆盖受保护数据：$TopLevel" }
    return $Normalized
}

function Assert-SafeZipEntries {
    param([string]$PackagePath)
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $Archive = [System.IO.Compression.ZipFile]::OpenRead($PackagePath)
    try {
        foreach ($Entry in $Archive.Entries) {
            $Name = $Entry.FullName.Replace('\', '/')
            if (
                $Name.StartsWith('/') -or
                $Name -match '^[A-Za-z]:' -or
                $Name -match '(^|/)\.\.(/|$)'
            ) { throw "更新 ZIP 包含非法路径：$Name" }
        }
    } finally {
        $Archive.Dispose()
    }
}

function Assert-ManifestFiles {
    param([string]$Root, [object]$Manifest, [bool]$RequireExactSet)
    $ExpectedPaths = @()
    foreach ($File in @($Manifest.files)) {
        $Relative = Assert-SafeRelativePath ([string]$File.path)
        $ExpectedPaths += $Relative
        $FullPath = Join-Path $Root ($Relative.Replace('/', [IO.Path]::DirectorySeparatorChar))
        if (-not (Test-Path -LiteralPath $FullPath -PathType Leaf)) {
            throw "更新文件不存在：$Relative"
        }
        $ActualSize = (Get-Item -LiteralPath $FullPath).Length
        if ($ActualSize -ne [long]$File.size) { throw "更新文件大小校验失败：$Relative" }
        $ActualHash = (Get-FileHash -LiteralPath $FullPath -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($ActualHash -ne ([string]$File.sha256).ToLowerInvariant()) {
            throw "更新文件哈希校验失败：$Relative"
        }
    }
    if ($RequireExactSet) {
        $ActualPaths = @(Get-ChildItem -LiteralPath $Root -Recurse -File | ForEach-Object {
            $_.FullName.Substring($Root.Length).TrimStart('\', '/').Replace('\', '/')
        })
        $Difference = Compare-Object ($ExpectedPaths | Sort-Object) ($ActualPaths | Sort-Object)
        if ($Difference) { throw "更新负载包含未登记文件" }
    }
}

function Restore-Rollback {
    param([string]$Root, [string]$RollbackRoot, [string[]]$CoreNames)
    foreach ($Name in $CoreNames) {
        $Current = Join-Path $Root $Name
        if (Test-Path -LiteralPath $Current) { Remove-Item -LiteralPath $Current -Recurse -Force }
    }
    if (Test-Path -LiteralPath $RollbackRoot) {
        Get-ChildItem -LiteralPath $RollbackRoot -Force | ForEach-Object {
            Move-Item -LiteralPath $_.FullName -Destination $Root -Force
        }
    }
}

function Invoke-OfflineUpdate {
    param([string]$Root, [string]$PackagePath)
    $Root = (Resolve-Path $Root).Path
    $PackagePath = (Resolve-Path $PackagePath).Path
    Assert-SafeZipEntries $PackagePath

    $TempRoot = Join-Path $Root ("update-temp-" + [guid]::NewGuid().ToString('N'))
    $RollbackRoot = Join-Path $Root "_rollback"
    New-Item -ItemType Directory -Path $TempRoot | Out-Null
    $CoreNames = @()
    $ReplacementStarted = $false
    try {
        Expand-Archive -LiteralPath $PackagePath -DestinationPath $TempRoot -Force
        $ManifestPath = Join-Path $TempRoot "update-manifest.json"
        $PayloadRoot = Join-Path $TempRoot "payload"
        if (-not (Test-Path -LiteralPath $ManifestPath -PathType Leaf)) { throw "更新包缺少 update-manifest.json" }
        if (-not (Test-Path -LiteralPath $PayloadRoot -PathType Container)) { throw "更新包缺少 payload 目录" }
        $Manifest = Get-Content -LiteralPath $ManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ([int]$Manifest.protocol -ne 1) { throw "不支持的更新协议：$($Manifest.protocol)" }
        Assert-ManifestFiles $PayloadRoot $Manifest $true

        $CurrentVersionPath = Join-Path $Root "version.json"
        $CurrentVersion = [version]"0.0.0"
        if (Test-Path -LiteralPath $CurrentVersionPath -PathType Leaf) {
            $CurrentInfo = Get-Content -LiteralPath $CurrentVersionPath -Raw -Encoding UTF8 | ConvertFrom-Json
            $CurrentVersion = [version]$CurrentInfo.version
        }
        $TargetVersion = [version]$Manifest.version
        $MinimumVersion = [version]$Manifest.minimum_version
        if ($TargetVersion -le $CurrentVersion) { throw "目标版本 $TargetVersion 不高于当前版本 $CurrentVersion" }
        if ($CurrentVersion -lt $MinimumVersion) { throw "当前版本 $CurrentVersion 低于最低升级版本 $MinimumVersion" }

        $CoreNames = @($Manifest.files | ForEach-Object {
            (Assert-SafeRelativePath ([string]$_.path) -split '/')[0]
        } | Sort-Object -Unique)
        Get-Process -Name ([IO.Path]::GetFileNameWithoutExtension($ExecutableName)) -ErrorAction SilentlyContinue |
            Stop-Process -Force -ErrorAction SilentlyContinue

        if (Test-Path -LiteralPath $RollbackRoot) { Remove-Item -LiteralPath $RollbackRoot -Recurse -Force }
        New-Item -ItemType Directory -Path $RollbackRoot | Out-Null
        $ReplacementStarted = $true
        foreach ($Name in $CoreNames) {
            $Current = Join-Path $Root $Name
            $Replacement = Join-Path $PayloadRoot $Name
            if (Test-Path -LiteralPath $Current) {
                Move-Item -LiteralPath $Current -Destination $RollbackRoot -Force
            }
            Move-Item -LiteralPath $Replacement -Destination $Root -Force
        }
        Assert-ManifestFiles $Root $Manifest $false
        Write-Host "更新成功：$CurrentVersion -> $TargetVersion" -ForegroundColor Green
    } catch {
        if ($ReplacementStarted) { Restore-Rollback $Root $RollbackRoot $CoreNames }
        throw
    } finally {
        if (Test-Path -LiteralPath $TempRoot) { Remove-Item -LiteralPath $TempRoot -Recurse -Force }
    }
}

try {
    $ResolvedRoot = (Resolve-Path $InstallRoot).Path
    $ResolvedPackage = Resolve-UpdatePackage $ResolvedRoot $Package
    Write-Host "正在校验更新包：$ResolvedPackage"
    Invoke-OfflineUpdate $ResolvedRoot $ResolvedPackage
    if (-not $NoRestart) {
        $Executable = Join-Path $ResolvedRoot $ExecutableName
        if (Test-Path -LiteralPath $Executable -PathType Leaf) { Start-Process -FilePath $Executable }
    }
    exit 0
} catch {
    Write-Host ("更新失败：" + $_.Exception.Message) -ForegroundColor Red
    exit 1
}
