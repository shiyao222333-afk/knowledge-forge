@echo off
REM ============================================================
REM  Citrinitas · 熔知 - One-Click Launcher
REM ============================================================
setlocal enabledelayedexpansion

set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"

echo.
echo ╔══════════════════════════════════════════════════╗
echo ║   Citrinitas · 熔知  v1.0.0                      ║
echo ╚══════════════════════════════════════════════════╝
echo.

REM ============================================================
REM  Step 1: 清理旧进程
REM ============================================================
echo [1/8] Cleaning up stale processes...
for /f "tokens=5" %%a in ('netstat -ano 2^>NUL ^| findstr ":8080 " ^| findstr "LISTENING"') do (
    echo   Killing old process on port 8080 [PID %%a]
    taskkill /PID %%a /F 2>NUL
    timeout /t 2 /nobreak > nul
)
echo   OK

REM ============================================================
REM  Step 2: 检查 Python 环境 + 依赖完整性 (P1-6)
REM ============================================================
echo.
echo [2/8] Checking Python environment...

if not exist "venv\Scripts\python.exe" (
    echo   [ERROR] Virtual environment not found.
    echo   Please run: install.ps1
    pause
    exit /b 1
)

REM 关键包导入测试
echo   Verifying packages...
set "PKG_OK=1"
venv\Scripts\python.exe -c "import nicegui, qdrant_client, openai, pypdf, docx, watchdog, jieba, yaml, dotenv" 2>NUL
if %ERRORLEVEL% NEQ 0 (
    echo   [WARNING] Some packages are missing.
    echo   Please run: install.ps1
    set "PKG_OK=0"
)
if !PKG_OK! EQU 1 echo   All packages OK

REM ============================================================
REM  Step 3: 配置变更检测 (P2-6)
REM 首次启动或 pipe_cfg.yaml 变更时提醒重启
REM ============================================================
echo.
echo [3/8] Checking config changes...
set "CFG_FILE=%PROJECT_DIR%pipe_cfg.yaml"
set "CFG_STAMP=%PROJECT_DIR%local_data\pipe_cfg_stamp.txt"

if not exist "%CFG_FILE%" (
    echo   [!] pipe_cfg.yaml missing. Please run install.ps1.
    goto :skip_cfg_check
)

if not exist "%PROJECT_DIR%local_data" mkdir "%PROJECT_DIR%local_data"

REM 计算当前配置哈希，对比上次存储的哈希
powershell -Command ^
  "$cfg = [System.IO.File]::ReadAllBytes($env:CFG_FILE); $hash = [System.BitConverter]::ToString((New-Object System.Security.Cryptography.SHA256Managed).ComputeHash($cfg)).Replace('-','');" ^
  "$old=''; if (Test-Path $env:CFG_STAMP) { $old = [System.IO.File]::ReadAllText($env:CFG_STAMP).Trim() };" ^
  "if ($old -and $old -ne $hash) { Write-Host '  [NOTICE] pipe_cfg.yaml has changed since last run. Restart to apply new settings.' };" ^
  "[System.IO.File]::WriteAllText($env:CFG_STAMP, $hash)"
if %ERRORLEVEL% EQU 0 (
    echo   Config check OK
) else (
    echo   Config check skipped ^(PowerShell error^)
)

:skip_cfg_check

REM ============================================================
REM  Step 4: 检查 Ollama (P0-4)
REM ============================================================
echo.
echo [4/8] Checking Ollama...

where ollama >NUL 2>NUL
if %ERRORLEVEL% EQU 0 (
    REM Ollama installed, check if running
    ollama list >NUL 2>NUL
    if %ERRORLEVEL% EQU 0 (
        echo   Ollama is running
        echo   Checking embed model...
        ollama list 2>NUL | findstr /C:"qwen3-embedding" >NUL
        if %ERRORLEVEL% EQU 0 (
            echo   Embed model ready (qwen3-embedding)
        ) else (
            echo   [!] Embed model not found. Please run: ollama pull qwen3-embedding:4b
        )
    ) else (
        echo   [!] Ollama installed but not running. Start Ollama first.
        echo   Vector embedding will not work without Ollama.
    )
) else (
    echo   [!] Ollama not installed. Vector embedding will not work.
    echo   Install from: https://ollama.com
)

REM  LLM API 可用性检查 (P1-11: classify_document 依赖)
if exist "%PROJECT_DIR%.env" (
    powershell -Command ^
      "$key=''; $url=''; Get-Content '%PROJECT_DIR%.env' | ForEach-Object { if ($_ -match '^KB_LLM_API_KEY=(.+)$') { $key=$Matches[1] } elseif ($_ -match '^KB_LLM_BASE_URL=(.+)$') { $url=$Matches[1] } }; " ^
      "if ($key) { Write-Host '  LLM API key configured' } else { Write-Host '  [!] LLM API key not set' }; " ^
      "if ($key -and $url) { " ^
      "  try { $null = Invoke-WebRequest -Uri '$url/models' -Method GET -Headers @{Authorization='Bearer '+$key} -TimeoutSec 5 -ErrorAction Stop; Write-Host '  LLM API reachable' } catch { Write-Host '  [!] LLM API unreachable:' $_.Exception.Message }; " ^
      "} elseif ($key) { Write-Host '  [!] KB_LLM_BASE_URL not set, skipping API check' }"
) else (
    echo   [!] .env not found. LLM API key not configured.
    echo   AI classification will not work.
)

REM ============================================================
REM  Step 5: 启动 Qdrant
REM ============================================================
echo.
echo [5/8] Starting Qdrant...

tasklist /FI "IMAGENAME eq qdrant.exe" 2>NUL | find /I "qdrant.exe" >NUL
if %ERRORLEVEL% NEQ 0 (
    if exist "D:\qdrant\qdrant.exe" (
        echo   Launching Qdrant...
        powershell -Command "Start-Process 'D:\qdrant\qdrant.exe' -ArgumentList '--config-path','D:\qdrant\config\config.yaml' -WindowStyle Hidden"
    ) else (
        echo   [!] Qdrant not found at D:\qdrant\qdrant.exe
        echo   Vector search disabled. Please install Qdrant.
        set "QDRANT_SKIP=1"
        goto :skip_qdrant
    )
) else (
    echo   Qdrant already running (checking health...)
    set "QDRANT_SKIP=0"
    goto :check_qdrant_health
)

REM ============================================================
REM  Step 5b: Qdrant 健康检查 — 轮询 /health (P0-3)
REM ============================================================
:check_qdrant_health
set /a QDRANT_RETRY=0
:retry_qdrant
timeout /t 2 /nobreak > nul
set /a QDRANT_RETRY+=1
powershell -Command "try { (Invoke-WebRequest -Uri 'http://127.0.0.1:6333/health' -TimeoutSec 2).Content } catch { exit 1 }" >NUL 2>NUL
if %ERRORLEVEL% EQU 0 (
    echo   Qdrant healthy ^(port 6333^)
    goto :skip_qdrant
)
if !QDRANT_RETRY! LSS 30 (
    echo   Waiting for Qdrant... ^(!QDRANT_RETRY!/30^)
    goto :retry_qdrant
)
echo   [ERROR] Qdrant did not start within 60 seconds.
echo   Please check D:\qdrant\qdrant.exe manually.
pause
exit /b 1

:skip_qdrant

REM ============================================================
REM  Step 6: 守望文件夹守护进程 (A4 — 由 main.py 内部启动)
REM ============================================================
echo.
echo [6/8] Watch folder: enabled
echo   Drop files into data\watch\ and they will be auto-ingested.
echo   data\watch_processed\ = success    data\watch_dead_letter\ = need attention

REM ============================================================
REM  Step 7: 显示配置摘要
REM ============================================================
echo.
echo [7/8] Configuration summary:
echo   Web UI:      http://127.0.0.1:8080
echo   Qdrant:      http://127.0.0.1:6333
echo   Embed model: qwen3-embedding:4b
echo   Config:      pipe_cfg.yaml ^(tuneables^) + .env ^(secrets^)
echo   Watch dir:   %PROJECT_DIR%data\watch\

REM ============================================================
REM  Step 8: 启动 Web UI
REM ============================================================
echo.
echo [8/8] Starting Web UI...
echo.
echo   Press Ctrl+C to stop all services.
echo ═══════════════════════════════════════════════════════
echo.

venv\Scripts\python.exe main.py
set EXIT_CODE=%errorlevel%

echo.
echo   Web UI stopped.

REM ============================================================
REM 优雅关闭 (P2-4)
REM 顺序：守望守护进程(随main退出) → Web UI(已退出) → Qdrant → (Ollama不关)
REM ============================================================
echo.
echo Shutting down services...

REM Qdrant
tasklist /FI "IMAGENAME eq qdrant.exe" 2>NUL | find /I "qdrant.exe" >NUL
if %ERRORLEVEL% EQU 0 (
    echo   Stopping Qdrant...
    taskkill /FI "IMAGENAME eq qdrant.exe" /F 2>NUL
    echo   Qdrant stopped.
) else (
    echo   Qdrant already stopped.
)

echo.
echo ═══════════════════════════════════════════════════════
echo   All services stopped. Goodbye!
echo ═══════════════════════════════════════════════════════
pause
