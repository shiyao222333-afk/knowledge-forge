# cfg_check.ps1 - 检查 pipe_cfg.yaml 是否变更
param(
    [string]$CfgFile,
    [string]$StampFile
)

try {
    if (-not (Test-Path $CfgFile)) {
        Write-Host "  [!] pipe_cfg.yaml missing."
        exit 0
    }

    $cfgBytes  = [System.IO.File]::ReadAllBytes($CfgFile)
    $sha       = [System.Security.Cryptography.SHA256Managed]::new()
    $hashBytes = $sha.ComputeHash($cfgBytes)
    $sha.Dispose()
    $hash = [System.BitConverter]::ToString($hashBytes).Replace('-', '')

    $old = ''
    if (Test-Path $StampFile) {
        $old = [System.IO.File]::ReadAllText($StampFile).Trim()
    }

    if ($old -and $old -ne $hash) {
        Write-Host "  [NOTICE] pipe_cfg.yaml has changed since last run. Restart to apply new settings."
    }

    # 写入新哈希（确保目录存在）
    $dir = Split-Path $StampFile -Parent
    if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    [System.IO.File]::WriteAllText($StampFile, $hash)

    Write-Host "  Config check OK"
    exit 0
} catch {
    Write-Host "  Config check skipped ($_)"
    exit 0   # 配置检查失败不阻断启动
}
