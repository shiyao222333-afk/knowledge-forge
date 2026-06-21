@echo off
REM ============================================================
REM  Citrinitas · 熔知 - One-Click Launcher
REM ============================================================

set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"

echo =========================================
echo   Citrinitas · 熔知
echo =========================================
echo.

REM --- Step 1: Clean up stale processes ---
echo [1/4] Cleaning up stale processes...
for /f "tokens=5" %%a in ('netstat -ano 2^>NUL ^| findstr ":8080 " ^| findstr "LISTENING"') do (
    echo   Killing old process on port 8080 [PID %%a]
    taskkill /PID %%a /F 2>NUL
    timeout /t 2 /nobreak > nul
)
echo   OK

REM --- Step 2: Check Python venv ---
echo.
echo [2/4] Python environment...
if not exist "venv\Scripts\python.exe" (
    echo   [ERROR] venv\Scripts\python.exe not found
    echo   Please run: python -m venv venv
    echo   Then: venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)
echo   OK

REM --- Step 3: Auto-start Qdrant ---
echo.
echo [3/4] Qdrant...
tasklist /FI "IMAGENAME eq qdrant.exe" 2>NUL | find /I "qdrant.exe" >NUL
if %ERRORLEVEL% NEQ 0 (
    if exist "D:\qdrant\qdrant.exe" (
        powershell -Command "Start-Process 'D:\qdrant\qdrant.exe' -ArgumentList '--config-path','D:\qdrant\config\config.yaml' -WindowStyle Hidden"
        echo   Qdrant started (port 6333)
        timeout /t 3 /nobreak > nul
    ) else (
        echo   [!] Qdrant not found - vector search disabled
    )
) else (
    echo   Qdrant already running
)

REM --- Step 4: Start Web UI ---
echo.
echo [4/4] Starting Web UI...
echo.
echo   URL: http://127.0.0.1:8080
echo   Press Ctrl+C to stop, or close this window.
echo.

venv\Scripts\python.exe main.py
set EXIT_CODE=%errorlevel%

echo.
echo   Web UI stopped.

REM --- Cleanup: Stop Qdrant ---
echo.
echo Stopping Qdrant...
taskkill /FI "IMAGENAME eq qdrant.exe" /F 2>NUL
if %ERRORLEVEL% EQU 0 (
    echo   Qdrant stopped.
) else (
    echo   Qdrant already stopped or not running.
)

echo.
echo [process exited, code=%EXIT_CODE%]
pause
