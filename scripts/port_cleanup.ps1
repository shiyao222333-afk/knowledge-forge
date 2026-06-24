# port_cleanup.ps1 - Robust port cleanup script
# Usage: powershell -File port_cleanup.ps1 -Port <port>
param(
    [int]$Port = 8080,
    [int]$MaxRetries = 3,
    [int]$WaitSeconds = 2
)

$ErrorActionPreference = "Stop"

function Write-Log($msg) {
    Write-Host "  $msg"
}

function Get-PortProcessIds {
    param([int]$PortNumber)
    # Use Get-NetTCPConnection (most reliable on Windows 8+)
    try {
        $conns = Get-NetTCPConnection -LocalPort $PortNumber -State Listen -ErrorAction SilentlyContinue
        if ($conns) {
            return $conns.OwningProcess | Sort-Object -Unique
        }
    }
    catch {
        # Fallback to netstat if Get-NetTCPConnection is not available
        $lines = netstat -ano | Select-String ":$PortNumber\s+.*LISTENING"
        $procIds = @()
        foreach ($line in $lines) {
            $parts = $line -split '\s+'
            $procId = $parts[-1]
            if ($procId -match '^\d+$') {
                $procIds += [int]$procId
            }
        }
        return $procIds | Sort-Object -Unique
    }
    return @()
}

function Get-ProcessDescription {
    param([int]$ProcessId)
    try {
        $proc = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
        if ($proc) {
            $startTimeStr = "unknown"
            try { $startTimeStr = $proc.StartTime } catch { }
            return "$($proc.ProcessName) (PID $ProcessId, Started: $startTimeStr)"
        }
    }
    catch { }
    return "PID $ProcessId (unable to get process info)"
}

function Kill-ProcessById {
    param([int]$ProcessId)
    
    # Method 1: taskkill /F (most forceful Windows command)
    try {
        $result = taskkill /F /PID $ProcessId 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Log "Killed PID $ProcessId (taskkill)"
            return $true
        }
    }
    catch { }

    # Method 2: Stop-Process -Force (PowerShell native)
    try {
        Stop-Process -Id $ProcessId -Force -ErrorAction Stop
        Write-Log "Killed PID $ProcessId (Stop-Process)"
        return $true
    }
    catch { }

    # Method 3: Kill process tree (handle child processes)
    try {
        $proc = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
        if ($proc) {
            # Get child processes
            $children = Get-CimInstance Win32_Process | Where-Object { $_.ParentProcessId -eq $ProcessId } | Select-Object -ExpandProperty ProcessId
            foreach ($childProcId in $children) {
                try { taskkill /F /PID $childProcId 2>&1 | Out-Null } catch { }
            }
            # Try taskkill again on parent
            taskkill /F /PID $ProcessId 2>&1 | Out-Null
            if ($LASTEXITCODE -eq 0) {
                Write-Log "Killed PID $ProcessId (with children)"
                return $true
            }
        }
    }
    catch { }

    return $false
}

function Wait-ForPortFree {
    param([int]$PortNumber, [int]$TimeoutSec)
    $elapsed = 0
    while ($elapsed -lt $TimeoutSec) {
        $procIds = Get-PortProcessIds -PortNumber $PortNumber
        if (-not $procIds -or $procIds.Count -eq 0) {
            return $true
        }
        Start-Sleep -Milliseconds 500
        $elapsed += 0.5
    }
    return $false
}

# ========== Main ==========

Write-Log "Checking port ${Port}..."

$procIds = Get-PortProcessIds -PortNumber $Port
if (-not $procIds -or $procIds.Count -eq 0) {
    Write-Log "Port ${Port} is free."
    exit 0
}

Write-Log "Found processes occupying port ${Port}:"
foreach ($procId in $procIds) {
    Write-Log "  $(Get-ProcessDescription -ProcessId $procId)"
}

$killedAny = $false
foreach ($procId in $procIds) {
    Write-Log "Killing PID $procId..."
    $success = Kill-ProcessById -ProcessId $procId
    if ($success) {
        $killedAny = $true
    }
    else {
        Write-Log "  [WARNING] Failed to kill PID $procId (may need admin)"
    }
}

if ($killedAny) {
    # Wait for port to be released
    Write-Log "Waiting for port ${Port} to be released..."
    $freed = Wait-ForPortFree -PortNumber $Port -TimeoutSec ($WaitSeconds * 2)
    if (-not $freed) {
        Write-Log "  [WARNING] Port ${Port} still occupied after killing processes."
        Write-Log "  Process details:"
        $remainingProcIds = Get-PortProcessIds -PortNumber $Port
        foreach ($remainingProcId in $remainingProcIds) {
            Write-Log "    $(Get-ProcessDescription -ProcessId $remainingProcId)"
        }
        exit 1
    }
    Write-Log "Port ${Port} is now free."
    exit 0
}
else {
    Write-Log "[ERROR] Could not kill any process on port ${Port}."
    Write-Log "Please run as Administrator or kill manually:"
    foreach ($procId in $procIds) {
        Write-Log "  taskkill /F /PID $procId"
    }
    exit 1
}
