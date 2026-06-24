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

function Get-PortPids {
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
        $pids = @()
        foreach ($line in $lines) {
            $parts = $line -split '\s+'
            $pid = $parts[-1]
            if ($pid -match '^\d+$') {
                $pids += [int]$pid
            }
        }
        return $pids | Sort-Object -Unique
    }
    return @()
}

function Get-ProcessInfo {
    param([int]$Pid)
    try {
        $proc = Get-Process -Id $Pid -ErrorAction SilentlyContinue
        if ($proc) {
            return "$($proc.ProcessName) (PID $Pid, Started: $($proc.StartTime))"
        }
    }
    catch { }
    return "PID $Pid (unable to get process info)"
}

function Kill-Pid {
    param([int]$Pid)
    $killed = $false

    # Method 1: taskkill /F (most forceful Windows command)
    try {
        $result = taskkill /F /PID $Pid 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Log "Killed PID $Pid (taskkill)"
            $killed = $true
            return $true
        }
    }
    catch { }

    # Method 2: Stop-Process -Force (PowerShell native)
    try {
        Stop-Process -Id $Pid -Force -ErrorAction Stop
        Write-Log "Killed PID $Pid (Stop-Process)"
        $killed = $true
        return $true
    }
    catch { }

    # Method 3: Kill process tree (handle child processes)
    try {
        $proc = Get-Process -Id $Pid -ErrorAction SilentlyContinue
        if ($proc) {
            # Get child processes
            $children = Get-CimInstance Win32_Process | Where-Object { $_.ParentProcessId -eq $Pid } | Select-Object -ExpandProperty ProcessId
            foreach ($childPid in $children) {
                try { taskkill /F /PID $childPid 2>&1 | Out-Null } catch { }
            }
            # Try taskkill again on parent
            taskkill /F /PID $Pid 2>&1 | Out-Null
            if ($LASTEXITCODE -eq 0) {
                Write-Log "Killed PID $Pid (with children)"
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
        $pids = Get-PortPids -PortNumber $PortNumber
        if (-not $pids -or $pids.Count -eq 0) {
            return $true
        }
        Start-Sleep -Milliseconds 500
        $elapsed += 0.5
    }
    return $false
}

# ========== Main ==========

Write-Log "Checking port $Port..."

$pids = Get-PortPids -PortNumber $Port
if (-not $pids -or $pids.Count -eq 0) {
    Write-Log "Port $Port is free."
    exit 0
}

Write-Log "Found processes occupying port $Port:"
foreach ($pid in $pids) {
    Write-Log "  $(Get-ProcessInfo -Pid $pid)"
}

$killedAny = $false
foreach ($pid in $pids) {
    Write-Log "Killing PID $pid..."
    $success = Kill-Pid -Pid $pid
    if ($success) {
        $killedAny = $true
    }
    else {
        Write-Log "  [WARNING] Failed to kill PID $pid (may need admin)"
    }
}

if ($killedAny) {
    # Wait for port to be released
    Write-Log "Waiting for port $Port to be released..."
    $freed = Wait-ForPortFree -PortNumber $Port -TimeoutSec ($WaitSeconds * 2)
    if (-not $freed) {
        Write-Log "  [WARNING] Port $Port still occupied after killing processes."
        Write-Log "  Process details:"
        $remainingPids = Get-PortPids -PortNumber $Port
        foreach ($remainingPid in $remainingPids) {
            Write-Log "    $(Get-ProcessInfo -Pid $remainingPid)"
        }
        exit 1
    }
    Write-Log "Port $Port is now free."
    exit 0
}
else {
    Write-Log "[ERROR] Could not kill any process on port $Port."
    Write-Log "Please run as Administrator or kill manually:"
    foreach ($pid in $pids) {
        Write-Log "  taskkill /F /PID $pid"
    }
    exit 1
}
