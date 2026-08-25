param(
    [string]$InstallRoot = $PSScriptRoot,
    [string]$Package = "",
    [switch]$NoRestart
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Join-UnicodeChars {
    param([int[]]$CodePoints)
    return -join @($CodePoints | ForEach-Object { [char]$_ })
}

$ExecutableName = (Join-UnicodeChars @(0x6296, 0x97F3, 0x89C6, 0x9891, 0x5DE5, 0x5177)) + ".exe"
$ReleaseNotesName = (Join-UnicodeChars @(0x7248, 0x672C, 0x8BF4, 0x660E)) + ".txt"
$ProtectedNames = @(
    "config.json", "douyin_cookie.txt", "data", "downloads", "models", "browsers",
    "updater.ps1", "_rollback"
)
$AllowedCoreNames = @("_internal", "web", $ExecutableName, "version.json", $ReleaseNotesName)

function Resolve-UpdatePackage {
    param([string]$Root, [string]$ExplicitPackage)
    if ($ExplicitPackage) {
        return (Resolve-Path $ExplicitPackage).Path
    }
    $Candidates = Get-ChildItem -Path $Root -Filter "*.zip" -File | ForEach-Object {
        if ($_.BaseName -match '-v(?<version>\d+\.\d+\.\d+)$') {
            [PSCustomObject]@{ File = $_; Version = [version]$Matches.version }
        }
    } | Sort-Object Version -Descending
    if (-not $Candidates) { throw "No update package matching *-vX.Y.Z.zip was found." }
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
    ) { throw "Unsafe update path: $RelativePath" }
    $TopLevel = ($Normalized -split '/')[0]
    if ($ProtectedNames -contains $TopLevel) { throw "Protected path in update payload: $TopLevel" }
    if ($AllowedCoreNames -notcontains $TopLevel) { throw "Unexpected top-level update path: $TopLevel" }
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
            ) { throw "Unsafe ZIP path: $Name" }
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
            throw "Missing update file: $Relative"
        }
        $ActualSize = (Get-Item -LiteralPath $FullPath).Length
        if ($ActualSize -ne [long]$File.size) { throw "Update size mismatch: $Relative" }
        $ActualHash = (Get-FileHash -LiteralPath $FullPath -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($ActualHash -ne ([string]$File.sha256).ToLowerInvariant()) {
            throw "Update hash mismatch: $Relative"
        }
    }
    if ($RequireExactSet) {
        $ActualPaths = @(Get-ChildItem -LiteralPath $Root -Recurse -File | ForEach-Object {
            $_.FullName.Substring($Root.Length).TrimStart('\', '/').Replace('\', '/')
        })
        $Difference = Compare-Object ($ExpectedPaths | Sort-Object) ($ActualPaths | Sort-Object)
        if ($Difference) { throw "Update payload contains unregistered files." }
    }
}

function Restore-Rollback {
    param(
        [string]$Root,
        [string]$RollbackRoot,
        [string[]]$InstalledNames,
        [string[]]$BackedUpNames
    )
    foreach ($Name in $InstalledNames) {
        $Current = Join-Path $Root $Name
        if (Test-Path -LiteralPath $Current) { Remove-Item -LiteralPath $Current -Recurse -Force }
    }
    foreach ($Name in $BackedUpNames) {
        $Backup = Join-Path $RollbackRoot $Name
        if (Test-Path -LiteralPath $Backup) {
            Move-Item -LiteralPath $Backup -Destination $Root -Force
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
    $BackedUpNames = @()
    $InstalledNames = @()
    try {
        Expand-Archive -LiteralPath $PackagePath -DestinationPath $TempRoot -Force
        $ManifestPath = Join-Path $TempRoot "update-manifest.json"
        $PayloadRoot = Join-Path $TempRoot "payload"
        if (-not (Test-Path -LiteralPath $ManifestPath -PathType Leaf)) { throw "Missing update-manifest.json." }
        if (-not (Test-Path -LiteralPath $PayloadRoot -PathType Container)) { throw "Missing payload directory." }
        $Manifest = Get-Content -LiteralPath $ManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ([int]$Manifest.protocol -ne 1) { throw "Unsupported update protocol: $($Manifest.protocol)" }
        Assert-ManifestFiles $PayloadRoot $Manifest $true

        $CurrentVersionPath = Join-Path $Root "version.json"
        $CurrentVersion = [version]"0.0.0"
        if (Test-Path -LiteralPath $CurrentVersionPath -PathType Leaf) {
            $CurrentInfo = Get-Content -LiteralPath $CurrentVersionPath -Raw -Encoding UTF8 | ConvertFrom-Json
            $CurrentVersion = [version]$CurrentInfo.version
        }
        $TargetVersion = [version]$Manifest.version
        $MinimumVersion = [version]$Manifest.minimum_version
        if ($TargetVersion -le $CurrentVersion) { throw "Target version must be newer than current version." }
        if ($CurrentVersion -lt $MinimumVersion) { throw "Current version is below the minimum update version." }

        $CoreNames = @($Manifest.files | ForEach-Object {
            (Assert-SafeRelativePath ([string]$_.path) -split '/')[0]
        } | Sort-Object -Unique)
        Get-Process -Name ([IO.Path]::GetFileNameWithoutExtension($ExecutableName)) -ErrorAction SilentlyContinue |
            Stop-Process -Force -ErrorAction SilentlyContinue

        if (Test-Path -LiteralPath $RollbackRoot) { Remove-Item -LiteralPath $RollbackRoot -Recurse -Force }
        New-Item -ItemType Directory -Path $RollbackRoot | Out-Null
        foreach ($Name in $CoreNames) {
            $Current = Join-Path $Root $Name
            if (Test-Path -LiteralPath $Current) {
                Move-Item -LiteralPath $Current -Destination $RollbackRoot -Force
                $BackedUpNames += $Name
            }
        }

        $TestFailAfter = -1
        if ($env:DOUYIN_UPDATE_TEST_FAIL_AFTER_INSTALL) {
            $TestFailAfter = [int]$env:DOUYIN_UPDATE_TEST_FAIL_AFTER_INSTALL
        }
        foreach ($Name in $CoreNames) {
            $Replacement = Join-Path $PayloadRoot $Name
            Move-Item -LiteralPath $Replacement -Destination $Root -Force
            $InstalledNames += $Name
            if ($TestFailAfter -ge 0 -and $InstalledNames.Count -ge $TestFailAfter) {
                throw "Injected update failure."
            }
        }
        Assert-ManifestFiles $Root $Manifest $false
        Write-Host "Update succeeded: $CurrentVersion -> $TargetVersion" -ForegroundColor Green
    } catch {
        Restore-Rollback $Root $RollbackRoot $InstalledNames $BackedUpNames
        throw
    } finally {
        if (Test-Path -LiteralPath $TempRoot) { Remove-Item -LiteralPath $TempRoot -Recurse -Force }
    }
}

try {
    $ResolvedRoot = (Resolve-Path $InstallRoot).Path
    $ResolvedPackage = Resolve-UpdatePackage $ResolvedRoot $Package
    Write-Host "Validating update package: $ResolvedPackage"
    Invoke-OfflineUpdate $ResolvedRoot $ResolvedPackage
    if (-not $NoRestart) {
        $Executable = Join-Path $ResolvedRoot $ExecutableName
        if (Test-Path -LiteralPath $Executable -PathType Leaf) { Start-Process -FilePath $Executable }
    }
    exit 0
} catch {
    Write-Host ("Update failed: " + $_.Exception.Message) -ForegroundColor Red
    exit 1
}
