param([Parameter(Mandatory = $true)][string]$Bundle)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$Executable = Join-Path $Bundle "抖音视频工具.exe"
$env:DOUYIN_PARSE_NO_BROWSER = "1"
$Process = Start-Process -FilePath $Executable -PassThru

try {
    $Deadline = (Get-Date).AddSeconds(30)
    do {
        Start-Sleep -Milliseconds 250
        try {
            $Health = Invoke-RestMethod -Uri "http://127.0.0.1:8787/health" -TimeoutSec 2
        } catch {
            $Health = $null
        }
    } while (-not $Health -and (Get-Date) -lt $Deadline -and -not $Process.HasExited)

    if (-not $Health) { throw "Built EXE did not expose /health." }
    if ($Health.status -ne "ok") { throw "Built EXE health status is not ok." }
    if (-not $Health.asr_model_ready) { throw "Built EXE cannot see the bundled ASR model." }
    Write-Host "Built Windows EXE runtime OK"
} finally {
    if (-not $Process.HasExited) { Stop-Process -Id $Process.Id -Force }
    Remove-Item Env:DOUYIN_PARSE_NO_BROWSER -ErrorAction SilentlyContinue
}
